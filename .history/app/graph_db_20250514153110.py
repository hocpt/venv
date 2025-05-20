# hpt3/app/graph_db.py
import traceback
from neo4j import GraphDatabase, Driver, Session, Transaction, basic_auth
# KHÔNG import current_app trực tiếp ở đây nếu không cần thiết trong các hàm context-safe
from flask import g # Vẫn cần g để lưu driver
# Import logging tiêu chuẩn
import logging
from datetime import datetime, timezone
import json
import neo4j
from neo4j.exceptions import ServiceUnavailable, CypherTypeError, CypherSyntaxError,Neo4jError
from neo4j.spatial import Point
from flask import current_app
# Lấy logger cho module này
log = logging.getLogger(__name__) # Dùng logger chuẩn

# --- Quản lý Driver ---
def get_driver() -> Driver | None:
    """Lấy Neo4j Driver từ Flask app context 'g' hoặc tạo mới."""
    # Việc truy cập config qua current_app ở đây THƯỜNG an toàn
    # VÌ hàm này được gọi BÊN TRONG các hàm execute_read/write,
    # mà các hàm đó lại được gọi TỪ route handler (có context)
    # Tuy nhiên, để chắc chắn hơn, có thể truyền app config khi init nếu cần.
    # Tạm thời giữ lại current_app ở đây vì nó thường hoạt động.
    from flask import current_app # Import local nếu cần
    if 'neo4j_driver' not in g:
        try:
            uri = current_app.config.get('NEO4J_URI')
            user = current_app.config.get('NEO4J_USER')
            password = current_app.config.get('NEO4J_PASSWORD')
            if not all([uri, user, password]):
                log.error("Neo4j config missing (URI, USER, PASSWORD)") # <<< Dùng log chuẩn
                return None
            g.neo4j_driver = GraphDatabase.driver(uri, auth=basic_auth(user, password))
            log.info("Neo4j Driver created and stored in app context 'g'.") # <<< Dùng log chuẩn
        except NameError: # Bắt lỗi nếu current_app không tồn tại
             log.error("Cannot access current_app. Ensure get_driver is called within Flask context.")
             return None
        except Exception as e:
            log.error(f"Failed to create Neo4j Driver: {e}", exc_info=True) # <<< Dùng log chuẩn
            return None
    return g.neo4j_driver

def close_driver(e=None):
    """Đóng Neo4j Driver khi app context bị teardown."""
    driver = g.pop('neo4j_driver', None)
    if driver is not None:
        try:
            driver.close()
            log.info("Neo4j Driver closed.") # <<< Dùng log chuẩn
        except Exception as e:
            log.error(f"Error closing Neo4j Driver: {e}", exc_info=True) # <<< Dùng log chuẩn

def init_app(app):
    """Đăng ký hàm teardown để đóng driver khi app kết thúc."""
    app.teardown_appcontext(close_driver)
    # Ở đây có thể dùng app.logger vì app được truyền vào
    app.logger.info("Neo4j Driver teardown registered.")

# --- Ví dụ Hàm thực thi transaction ĐỌC ---
def execute_read(cypher: str, params: dict = None):
    driver = get_driver()
    if not driver: return None
    try:
        with driver.session() as session:
            result = session.execute_read(lambda tx: [r.data() for r in tx.run(cypher, params or {})])
            return result
    except Exception as e:
        log.error(f"Neo4j read query failed: {e}\nQuery: {cypher}\nParams: {params}", exc_info=True) # <<< Dùng log chuẩn
        return None

# --- Ví dụ Hàm thực thi transaction GHI ---
def execute_write(cypher: str, params: dict = None):
    driver = get_driver()
    if not driver: return False
    try:
        with driver.session() as session:
            session.execute_write(lambda tx: tx.run(cypher, params or {}).consume())
        return True
    except Exception as e:
        log.error(f"Neo4j write query failed: {e}\nQuery: {cypher}\nParams: {params}", exc_info=True) # <<< Dùng log chuẩn
        return False

# hpt3/app/graph_db.py
# ... (các hàm get_driver, close_driver, init_app, execute_read, execute_write đã có) ...

def create_or_update_screen_node(screen_id: str, app_name: str, properties: dict):
    """
    Tạo Node Screen mới nếu chưa tồn tại, hoặc cập nhật thuộc tính nếu đã tồn tại.
    'screen_id' là định danh duy nhất (ví dụ: hash cấu trúc).
    'appName' là định danh ứng dụng (ví dụ: package name).
    'properties' chứa các thông tin khác như activityName, structureHash, aiSummary...
    """
    if not screen_id or not app_name:
        log.error("graph_db.create_or_update_screen_node: screen_id and app_name are required.")
        return False

    properties['appName'] = app_name # Đảm bảo appName có trong properties
    properties['lastSeen'] = datetime.now(timezone.utc).isoformat()
    node_props = properties.copy()
    node_props.pop('screenId', None) # Không lưu screenId như một property riêng trong node
    node_props = {k: v for k, v in node_props.items() if v is not None}

    # MERGE dựa trên screenId VÀ appName
    cypher = """
    MERGE (s:Screen {screenId: $screenId, appName: $appName})
    ON CREATE SET s = $props, s.createdAt = datetime(), s.screenId = $screenId, s.appName = $appName
    ON MATCH SET s += $props, s.updatedAt = datetime()
    RETURN s.screenId as id
    """
    params = {"screenId": screen_id, "appName": app_name, "props": node_props}

    success = execute_write(cypher, params)
    if not success:
        log.error(f"Failed to create/update Screen node: {screen_id} for app: {app_name}")
    # else: # Bỏ bớt log debug cho gọn
        # log.debug(f"Successfully created/updated Screen node: {screen_id} for app: {app_name}")
    return success

def create_or_update_transition_relationship(source_screen_id: str, target_screen_id: str, app_name: str, action_data: dict):
    """
    Tạo hoặc cập nhật quan hệ TRANSITION giữa hai Screen node CỦA CÙNG MỘT APP.
    SỬA LỖI: Xây dựng pattern MERGE động để tránh lỗi NULL property.
    """
    if not all([source_screen_id, target_screen_id, app_name, action_data]):
         log.error("Missing parameters for graph_db.create_transition_relationship.")
         return False

    # --- Xử lý identity_props (Chỉ lấy các giá trị không None) ---
    identity_props = {
        "actionType": action_data.get("actionType"),
        "onElementId": action_data.get("onElementId"),
        "onElementText": action_data.get("onElementText"),
        "onElementClass": action_data.get("onElementClass")
    }
    # identityPropsClean chỉ chứa các key có giá trị không phải None
    identityPropsClean = {k: v for k, v in identity_props.items() if v is not None}

    if not identityPropsClean.get('actionType'): # Vẫn yêu cầu phải có actionType
         log.warning(f"Cannot MERGE transition: 'actionType' is missing in action_data: {action_data}")
         return False

    # --- Xử lý update_props (Giữ nguyên) ---
    update_props = action_data.copy()
    update_props['lastTransitionTime'] = datetime.now(timezone.utc).isoformat()
    for key in identityPropsClean: update_props.pop(key, None)
    update_props_clean = {k: v for k, v in update_props.items() if v is not None}

    # === SỬA CÁCH XÂY DỰNG CYPHER VÀ PARAMS ===
    # 1. Tạo phần properties cho MERGE một cách động
    merge_pattern_props_list = []
    params = { # Khởi tạo params cơ bản
        "sourceId": source_screen_id,
        "targetId": target_screen_id,
        "appName": app_name,
        "updatePropsClean": update_props_clean
    }
    # Thêm từng thuộc tính định danh vào pattern và params
    for key, value in identityPropsClean.items():
        param_name = f"p_{key}" # Tạo tên param duy nhất, ví dụ p_actionType
        merge_pattern_props_list.append(f"{key}: ${param_name}")
        params[param_name] = value # Thêm vào dict params

    # Nối các phần tử lại thành chuỗi pattern properties: {key1: $p_key1, key2: $p_key2}
    merge_pattern_props_str = "{" + ", ".join(merge_pattern_props_list) + "}"

    # 2. Tạo câu lệnh Cypher hoàn chỉnh với pattern properties động
    cypher = f"""
    MATCH (source:Screen {{screenId: $sourceId, appName: $appName}}), (target:Screen {{screenId: $targetId, appName: $appName}})
    MERGE (source)-[r:TRANSITION {merge_pattern_props_str}]->(target)
    ON CREATE SET r = $updatePropsClean, r.count = 1, r.createdAt = datetime()
    ON MATCH SET r += $updatePropsClean, r.count = coalesce(r.count, 0) + 1, r.updatedAt = datetime()
    RETURN r
    """
    # ======================================

    # Gọi execute_write (đã sửa để log lỗi tốt hơn)
    log.debug(f"Executing Cypher for TRANSITION: {cypher}") # Log câu Cypher cuối cùng
    log.debug(f"Executing with Params: {params}") # Log params cuối cùng
    success = execute_write(cypher, params)
    if not success:
        # Log lỗi đã được thực hiện bên trong execute_write
        log.error(f"execute_write returned False for TRANSITION from {source_screen_id} to {target_screen_id}.")
    # else:
        # log.debug(f"Successfully created/updated TRANSITION from {source_screen_id} to {target_screen_id} for app {app_name}")
    return success
# ... (các hàm graph_db khác) ...

# Hàm execute_write đã sửa để log lỗi tốt hơn
def execute_write(cypher: str, params: dict = None):
    driver = get_driver()
    if not driver: return False
    try:
        with driver.session() as session:
            def write_transaction(tx, cypher_code, parameters):
                result = tx.run(cypher_code, parameters)
                result.consume()
            session.write_transaction(write_transaction, cypher, params or {})
        return True
    except Exception as e:
        log.error(f"Neo4j write query failed: {type(e).__name__} - {e}", exc_info=True)
        log.error(f"Failing Cypher: {cypher}")
        log.error(f"Failing Params: {params}") # In ra params gây lỗi
        return False


# --- Cập nhật các hàm truy vấn để có thể lọc theo appName (Ví dụ) ---
def find_screen_node(screen_id: str, app_name: str) -> dict | None: # <<< Thêm app_name
    """Tìm node Screen theo screenId và appName."""
    cypher = "MATCH (s:Screen {screenId: $screenId, appName: $appName}) RETURN s"
    params = {"screenId": screen_id, "appName": app_name}
    results = execute_read(cypher, params)
    if results:
        return results[0].get('s')
    return None

def get_all_screen_ids(app_name: str | None = None) -> list[str] | None: # <<< Thêm app_name tùy chọn
    """Lấy screenId, có thể lọc theo appName."""
    if app_name:
        cypher = "MATCH (s:Screen {appName: $appName}) RETURN s.screenId as screenId ORDER BY s.screenId"
        params = {"appName": app_name}
    else:
        cypher = "MATCH (s:Screen) RETURN s.screenId as screenId ORDER BY s.appName, s.screenId"
        params = None
    results = execute_read(cypher, params)
    if results:
        return [r.get('screenId') for r in results if r.get('screenId')]
    elif results == []:
        return []
    else:
        return None
# --- Các hàm Truy vấn Neo4j cho Planner ---

def get_screen_properties(screen_id: str, app_name: str) -> dict | None:
    """
    Lấy các thuộc tính (properties) của một Screen node bằng screenId và appName.
    Bao gồm cả 'rawStateSample' nếu có.
    """
    log.debug(f"Querying screen properties for screenId: {screen_id}, appName: {app_name}")
    cypher = """
    MATCH (s:Screen {screenId: $screenId, appName: $appName})
    RETURN properties(s) as props
    """
    # Lưu ý: Thuộc tính trả về từ Neo4j driver có thể hơi khác dict chuẩn Python
    # result là list chứa 1 dict {'props': {...}}
    results = execute_read(cypher, {"screenId": screen_id, "appName": app_name})
    if results:
        # Chuyển đổi kiểu dữ liệu Node Properties sang dict Python chuẩn nếu cần
        screen_props = results[0].get('props', {})
        # Parse lại rawStateSample nếu nó là chuỗi JSON
        raw_state_str = screen_props.get('rawStateSample')
        if raw_state_str and isinstance(raw_state_str, str):
            try:
                screen_props['processed_ui_state'] = json.loads(raw_state_str)
            except json.JSONDecodeError:
                 log.warning(f"Could not parse rawStateSample JSON for screen {screen_id}")
                 screen_props['processed_ui_state'] = None # Hoặc giữ nguyên chuỗi
        return screen_props
    else:
        log.warning(f"Screen node not found for screenId: {screen_id}, appName: {app_name}")
        return None



def get_app_name_from_account(account_id: str) -> str | None:
    # Hàm này cần kết nối CSDL PostgreSQL (dùng db_postgres)
    # và truy vấn bảng 'accounts' để lấy 'platform'
    # Ví dụ đơn giản (cần hoàn thiện):
    # platform = db_postgres.get_account_platform(account_id) # Giả sử có hàm này
    # if platform == 'tiktok': return 'com.ss.android.ugc.trill'
    # elif platform == 'facebook': return 'com.facebook.katana'
    # else: return None
    # Tạm thời trả về None, bạn cần hoàn thiện logic này
    log.warning(f"get_app_name_from_account not fully implemented for account {account_id}. Returning None.")
    return None

def merge_screen(screen_id: str, app_name: str, activity_name: str | None,
                 extracted_elements: list, 
                 # log_id: int | None, # Bỏ nếu không dùng trực tiếp để liên kết
                 screenshot_path: str | None = None,
                 screen_width: int | None = None, screen_height: int | None = None,
                 is_defined_by_pie: bool = False # Quan trọng để đặt status
                 ) -> bool:
    """
    Tạo hoặc cập nhật Node Screen và các Element của nó.
    - screen_id: ID của màn hình (có thể là defined_screen_id hoặc unknown_id).
    - is_defined_by_pie: True nếu screen_id này đến từ một PIE definition.
    - extracted_elements: list các dictionary element đã được chuẩn hóa từ utils.process_raw_ui_state.
    """
    logger = current_app.logger
    if not screen_id or not app_name:
        logger.error("merge_screen: screen_id và app_name là bắt buộc.")
        return False
    
    logger.info(f"[GraphDB merge_screen] Bắt đầu cho ScreenID: {screen_id}, App: {app_name}, IsDefined: {is_defined_by_pie}")
    logger.debug(f"  Screenshot: {screenshot_path}, Width: {screen_width}, Height: {screen_height}")
    logger.debug(f"  Số lượng elements nhận được: {len(extracted_elements if extracted_elements else [])}")

    driver = get_driver()
    if not driver:
        logger.error("merge_screen: Neo4j driver không khả dụng.")
        return False

    current_time_utc = datetime.now(timezone.utc) # Dùng đối tượng datetime
    screen_status_val = 'defined' if is_defined_by_pie else 'provisional_unknown'

    # --- Chuẩn bị thuộc tính cho Node :Screen ---
    # Thuộc tính sẽ được set khi node TẠO MỚI (ON CREATE)
    props_for_screen_create = {
        "app_name": app_name, # Vẫn cần app_name để query và có thể là một phần của key tổng hợp nếu screen_id không global unique
        "activity_name": activity_name or 'UnknownActivity',
        "screenshot_path": screenshot_path,
        "width": screen_width,
        "height": screen_height,
        "status": screen_status_val,
        "node_classification": None, # Admin sẽ gán sau
        "element_count": len(extracted_elements) if extracted_elements else 0, # Số element được cung cấp lần này
        "last_seen": current_time_utc # Sẽ được chuyển đổi bởi driver hoặc dùng datetime() của Cypher
        # created_at sẽ được SET bằng Cypher datetime()
    }
    # Loại bỏ các key có giá trị None khỏi dict sẽ truyền vào Cypher
    props_for_screen_create_clean = {k: v for k, v in props_for_screen_create.items() if v is not None}

    # Thuộc tính sẽ được CẬP NHẬT nếu node ĐÃ TỒN TẠI (ON MATCH)
    props_for_screen_match = {
        "activity_name": activity_name or 'UnknownActivity', # Có thể cập nhật nếu client gửi activity khác
        "screenshot_path": screenshot_path, # Luôn cập nhật ảnh mới nhất
        "width": screen_width, 
        "height": screen_height,
        "element_count": len(extracted_elements) if extracted_elements else 0,
        "last_seen": current_time_utc
        # status và node_classification sẽ được xử lý cẩn thận hơn trong Cypher khi MATCH
        # updated_at sẽ được SET bằng Cypher datetime()
    }
    props_for_screen_match_clean = {k: v for k, v in props_for_screen_match.items() if v is not None}

    # --- Chuẩn bị standardized_elements cho Neo4j ---
    # Đảm bảo tất cả giá trị trong list này là kiểu nguyên thủy Neo4j hỗ trợ
    standardized_elements_for_tx = []
    if extracted_elements:
        for el_data in extracted_elements:
            if isinstance(el_data, dict) and el_data.get('element_id'):
                coords = el_data.get('coordinates') # dict {x, y}
                coord_x_val = None
                coord_y_val = None
                if isinstance(coords, dict) and coords.get('x') is not None and coords.get('y') is not None:
                    try:
                        coord_x_val = int(coords['x'])
                        coord_y_val = int(coords['y'])
                    except (ValueError, TypeError):
                        logger.warning(f"Giá trị coordinates không hợp lệ cho element_id '{el_data.get('element_id')}': {coords}")
                
                bounds_val = el_data.get('bounds') # dict {left, top, right, bottom}
                bounds_dict_for_neo4j = None
                if isinstance(bounds_val, dict):
                    try:
                        temp_bounds = {
                            "left": int(bounds_val["left"]) if bounds_val.get("left") is not None else None,
                            "top": int(bounds_val["top"]) if bounds_val.get("top") is not None else None,
                            "right": int(bounds_val["right"]) if bounds_val.get("right") is not None else None,
                            "bottom": int(bounds_val["bottom"]) if bounds_val.get("bottom") is not None else None,
                        }
                        # Chỉ giữ lại nếu có đủ 4 giá trị và chúng hợp lệ
                        if all(temp_bounds[k] is not None for k in ["left", "top", "right", "bottom"]):
                             bounds_dict_for_neo4j = {k:v for k,v in temp_bounds.items() if v is not None}
                        if not bounds_dict_for_neo4j: bounds_dict_for_neo4j = None
                    except (ValueError, TypeError, KeyError):
                        logger.warning(f"Giá trị bounds không hợp lệ cho element_id '{el_data.get('element_id')}': {bounds_val}")
                
                std_el = {
                    'element_id': el_data['element_id'], # ID ổn định đã tạo (resource-id, text, etc.)
                    'identifier_type': el_data.get('identifier_type'),
                    'element_type': el_data.get('element_type'),
                    'text_content': el_data.get('text_content'),
                    'coordinate_x': coord_x_val, # Số nguyên hoặc None
                    'coordinate_y': coord_y_val, # Số nguyên hoặc None
                    'bounds': bounds_dict_for_neo4j, # Dict các số nguyên hoặc None
                    # Các thuộc tính is_clickable_observed, is_editable_observed có thể thêm ở đây nếu client gửi
                    # 'is_clickable_observed': el_data.get('is_clickable_observed', False), 
                    # 'is_editable_observed': el_data.get('is_editable_observed', False),
                    # 'last_seen_timestamp': current_time_utc.isoformat() # Có thể không cần cho từng element
                }
                # Chỉ thêm các key có giá trị không phải None vào dict cuối cùng cho Neo4j
                standardized_elements_for_tx.append({k:v for k,v in std_el.items() if v is not None})
    
    if standardized_elements_for_tx:
        logger.debug(f"  merge_screen: Sample standardized element 0 data: {standardized_elements_for_tx[0]}")

    # Lấy tên DB từ config
    db_name_neo4j = current_app.config.get('NEO4J_DATABASE', 'neo4j')

    try:
        with driver.session(database=db_name_neo4j) as session:
            # Định nghĩa hàm con để thực thi bên trong transaction
            def merge_screen_and_elements_tx(tx: Transaction, 
                                             screen_id_param: str, 
                                             props_create_param: dict, 
                                             props_match_param: dict, 
                                             elements_param_list: list, 
                                             is_defined_by_pie_param: bool):
                
                tx_logger = current_app.logger # Dùng logger của app
                tx_logger.debug(f"  TX merge_screen: screen_id='{screen_id_param}', is_defined={is_defined_by_pie_param}")
                # tx_logger.debug(f"    props_create_param: {props_create_param}")
                # tx_logger.debug(f"    props_match_param: {props_match_param}")

                # Câu lệnh Cypher cho Screen Node
                # screen_id_param được dùng trong MERGE (s:Screen {screen_id: $screenIdVal})
                # propsForCreate và propsForMatch KHÔNG chứa screen_id nữa
                # $now_param sẽ được truyền vào từ Python là đối tượng datetime của Neo4j
                screen_query = """
                MERGE (s:Screen {screen_id: $screenIdVal})
                ON CREATE SET 
                    s = $propsForCreate, 
                    s.screen_id = $screenIdVal, // Đảm bảo screen_id được set đúng khi CREATE
                    s.created_at = $now_param 
                ON MATCH SET 
                    s += $propsForMatch,
                    // Xử lý status cẩn thận khi MATCH
                    s.status = CASE 
                                   WHEN $isDefinedByPieParam THEN 'defined' // Nếu PIE khớp, luôn là 'defined'
                                   WHEN s.status = 'defined' THEN 'defined' // Nếu đã defined, giữ nguyên
                                   ELSE 'provisional_unknown' // Còn lại là unknown
                               END,
                    s.updated_at = $now_param
                RETURN s.screen_id AS merged_screen_id, s.status AS final_status
                """
                screen_run_params = {
                    "screenIdVal": screen_id_param,
                    "propsForCreate": props_create_param,
                    "propsForMatch": props_match_param,
                    "isDefinedByPieParam": is_defined_by_pie_param,
                    "now_param": current_time_utc # Truyền đối tượng datetime Python, driver sẽ xử lý
                }
                # tx_logger.debug(f"  Running Screen Query: {screen_query.strip()} \n  Params: {json.dumps(screen_run_params, default=str)}")
                
                screen_result = tx.run(screen_query, screen_run_params)
                merged_id_record = screen_result.single()

                if not merged_id_record or not merged_id_record["merged_screen_id"]:
                    tx_logger.error(f"  TX: Thất bại khi MERGE Screen node với ID: {screen_id_param}")
                    # Ném Exception ở đây sẽ khiến transaction rollback
                    raise Neo4jError(f"Thất bại khi MERGE Screen node với ID: {screen_id_param}") 
                
                tx_logger.info(f"  TX: MERGE Screen node '{merged_id_record['merged_screen_id']}' thành công, final status: '{merged_id_record['final_status']}'.")

                # Xóa các quan hệ :HAS_ELEMENT cũ trước khi tạo mới để đảm bảo danh sách element là mới nhất
                # Điều này quan trọng nếu cấu trúc UI thay đổi và một số element cũ không còn nữa
                delete_rels_query = """
                MATCH (s:Screen {screen_id: $screenIdVal})-[r:HAS_ELEMENT]->(e:Element)
                DELETE r
                """
                # Có thể cần xóa cả những Element node mồ côi nếu muốn, nhưng phức tạp hơn.
                # Tạm thời chỉ xóa quan hệ.
                # tx_logger.debug(f"  TX: Deleting old :HAS_ELEMENT relationships for screen {screen_id_param}")
                tx.run(delete_rels_query, screenIdVal=screen_id_param).consume()


                # Merge Element Nodes và Relationships :HAS_ELEMENT
                if elements_param_list:
                    # tx_logger.debug(f"  TX: Bắt đầu merge {len(elements_param_list)} elements cho screen {screen_id_param}")
                    for i, element_data_item in enumerate(elements_param_list):
                        element_id_val = element_data_item.get('element_id')
                        if not element_id_val: 
                            tx_logger.warning(f"  TX: Bỏ qua element thứ {i+1} do thiếu element_id.")
                            continue
                        
                        # Các thuộc tính của element để SET (không bao gồm key của MERGE)
                        element_props_for_set = {k: v for k, v in element_data_item.items() 
                                                 if k not in ['element_id', 'screen_id']} # screen_id không phải thuộc tính của Element

                        element_query = """
                        MATCH (s:Screen {screen_id: $screenIdVal})
                        // MERGE Element dựa trên screen_id và element_id của nó
                        MERGE (e:Element {screen_id: $screenIdVal, element_id: $elementIdVal}) 
                        ON CREATE SET 
                            e = $propsForElementSet, 
                            e.element_id = $elementIdVal, // Đảm bảo set khi CREATE
                            e.screen_id = $screenIdVal,   // Đảm bảo set khi CREATE
                            e.created_at = $now_param
                        ON MATCH SET 
                            e += $propsForElementSet, 
                            e.updated_at = $now_param
                        MERGE (s)-[r:HAS_ELEMENT]->(e) // Luôn tạo/khớp quan hệ này
                        """
                        element_run_params = {
                            "screenIdVal": screen_id_param,
                            "elementIdVal": element_id_val,
                            "propsForElementSet": element_props_for_set,
                            "now_param": current_time_utc
                        }
                        # tx_logger.debug(f"  TX: Element {i+1} ('{element_id_val}') Query Params: {json.dumps(element_run_params, default=str)}")
                        tx.run(element_query, element_run_params).consume()
                # Kết thúc vòng lặp element
                tx_logger.info(f"  TX: Hoàn thành merge elements cho screen {screen_id_param}")

            # Gọi hàm transaction
            session.write_transaction(
                merge_screen_and_elements_tx,
                screen_id, 
                props_for_screen_create_clean, 
                props_for_screen_match_clean,  
                standardized_elements_for_tx,
                is_defined_by_pie 
            )
            logger.info(f"[GraphDB merge_screen] Hoàn thành thành công cho ScreenID: {screen_id}")
            return True

    except Neo4jError as db_err: # Bắt lỗi Neo4j cụ thể (bao gồm CypherTypeError)
        logger.error(f"Lỗi Neo4j cụ thể (merge_screen cho {screen_id}): Code={db_err.code}, Message={db_err.message}", exc_info=False)
        logger.error(f"  Dữ liệu screen_id: {screen_id}")
        logger.error(f"  Dữ liệu props_for_create_clean: {json.dumps(props_for_screen_create_clean, default=str)}")
        logger.error(f"  Dữ liệu props_for_screen_match_clean: {json.dumps(props_for_screen_match_clean, default=str)}")
        logger.error(f"  Dữ liệu is_defined_by_pie: {is_defined_by_pie}")
        if standardized_elements_for_tx:
            logger.error(f"  Dữ liệu standardized_elements_for_tx (sample): {json.dumps(standardized_elements_for_tx[0] if standardized_elements_for_tx else [], default=str)}")
        return False
    except Exception as e:
        logger.error(f"Lỗi không mong muốn trong Neo4j Transaction (merge_screen cho {screen_id}): {type(e).__name__} - {e}", exc_info=True)
        return False
# ... (các hàm get_driver, close_driver, init_app, execute_read, execute_write, merge_screen, etc. giữ nguyên) ...

# Thêm/Sửa trong file htp6/app/graph_db.py
# ... (imports và các hàm khác) ...

def merge_transition(source_screen_id: str, target_screen_id: str, app_name: str,
                     action_details: dict, result_status: str, log_id: int | None) -> bool:
    """
    Tạo hoặc cập nhật cạnh TRANSITION với các thuộc tính nguyên thủy.
    Đảm bảo lưu 'element_id' một cách nhất quán.
    """
    logger = current_app.logger if current_app else log
    if not all([source_screen_id, target_screen_id, app_name, action_details]):
        logger.error("merge_transition: source_id, target_id, app_name, and action_details are required.")
        return False

    driver = get_driver()
    if not driver: return False

    # --- 1. Chuẩn bị thuộc tính ---
    action_type = action_details.get('actionType')
    # === LẤY ELEMENT ID NHẤT QUÁN ===
    # Ưu tiên 'element_id' nếu có, fallback về 'onElementId'
    element_id_to_use = action_details.get('element_id') or action_details.get('onElementId')
    identifier_type = action_details.get('identifier_type')
    macro_code = action_details.get('macro_code')
    element_text = action_details.get('element_text') or action_details.get('onElementText')
    params_json_str = json.dumps(action_details.get('params')) if action_details.get('params') else None

    # Thuộc tính để MERGE (xác định cạnh)
    merge_props = {
        'actionType': action_type,
        'element_id': element_id_to_use, # <<< Dùng ID đã lấy
        'identifier_type': identifier_type
    }
    merge_props = {k: v for k, v in merge_props.items() if v is not None}

    if not merge_props.get('actionType'):
        logger.warning(f"Cannot MERGE transition: 'actionType' missing. Details: {action_details}")
        return False
    # Có thể bỏ qua kiểm tra element_id/identifier_type cho action 'back'/'swipe'
    if merge_props['actionType'] not in ['NAV_GO_BACK', 'UI_SWIPE_UP', 'UI_SWIPE_DOWN'] and not merge_props.get('element_id'):
         logger.warning(f"Cannot MERGE transition: Missing 'element_id' for actionType '{merge_props['actionType']}'. Details: {action_details}")
         # return False # Xem xét có nên báo lỗi không nếu thiếu ID cho click/input

    # Thuộc tính để SET/UPDATE
    update_props = {
        'macro_code': macro_code,
        'element_text': element_text,
        'params_json_str': params_json_str,
        # Thêm các thuộc tính nguyên thủy khác nếu cần
    }
    update_props = {k: v for k, v in update_props.items() if v is not None}

    current_time = datetime.now(timezone.utc)
    is_success = (result_status == 'success')

    # --- 2. Xây dựng Cypher ---
    merge_pattern_props_list = []
    params = {
        "sourceId": source_screen_id, "targetId": target_screen_id, "appName": app_name,
        "updateProps": update_props, "success": is_success, "logId": log_id, "now": current_time
    }
    for key, value in merge_props.items():
        param_name = f"p_{key}"
        merge_pattern_props_list.append(f"`{key}`: ${param_name}") # Dùng backtick
        params[param_name] = value

    merge_pattern_props_str = "{" + ", ".join(merge_pattern_props_list) + "}" if merge_pattern_props_list else ""

    # Đảm bảo `element_id` được SET cả khi CREATE và MATCH
    cypher = f"""
    MATCH (a:Screen {{screen_id: $sourceId, app_name: $appName}}),
          (b:Screen {{screen_id: $targetId, app_name: $appName}})
    MERGE (a)-[r:TRANSITION {merge_pattern_props_str}]->(b)
    ON CREATE SET
        r += $updateProps,
        // === ĐẢM BẢO SET element_id KHI CREATE ===
        r.element_id = $p_element_id,
        // ========================================
        r.status = 'provisional',
        r.attempt_count = 1,
        r.success_count = CASE WHEN $success THEN 1 ELSE 0 END,
        r.first_seen = $now,
        r.last_seen = $now,
        r.last_successful_log_id = CASE WHEN $success THEN $logId ELSE null END,
        r.created_at = $now
    ON MATCH SET
        r += $updateProps,
        // === ĐẢM BẢO SET element_id KHI MATCH (nếu cần cập nhật) ===
        // Thường không cần cập nhật element_id khi MATCH vì nó là phần của key
        // r.element_id = $p_element_id,
        // =======================================================
        r.attempt_count = coalesce(r.attempt_count, 0) + 1,
        r.success_count = coalesce(r.success_count, 0) + CASE WHEN $success THEN 1 ELSE 0 END,
        r.last_seen = $now,
        r.last_successful_log_id = CASE WHEN $success THEN $logId ELSE r.last_successful_log_id END,
        r.updated_at = $now
    RETURN r
    """
    # Thêm p_element_id vào params nếu nó tồn tại trong merge_props
    if 'element_id' in merge_props:
        params['p_element_id'] = merge_props['element_id']
    else:
        # Xử lý trường hợp không có element_id (ví dụ: back, swipe)
        # Đặt giá trị placeholder hoặc đảm bảo query không bị lỗi
        params['p_element_id'] = None # Hoặc một giá trị đặc biệt nếu cần

    # --- 3. Thực thi ---
    logger.debug(f"Executing Cypher for TRANSITION:\n{cypher}")
    logger.debug(f"Executing with Params: {params}")
    success = execute_write(cypher, params)
    if not success:
        logger.error(f"execute_write returned False for TRANSITION from {source_screen_id} to {target_screen_id}.")
    else:
        logger.info(f"Successfully merged TRANSITION from {source_screen_id} to {target_screen_id} for app {app_name}")

    return success



def get_outgoing_transitions(screen_id: str, app_name: str) -> list[dict] | None:
    """
    Lấy danh sách các thuộc tính của các quan hệ TRANSITION đi ra
    từ một Screen node cụ thể. Đảm bảo lấy đúng 'element_id'.
    """
    logger = current_app.logger if current_app else log # Sửa logger
    logger.debug(f"Querying outgoing transitions for screenId: {screen_id}, appName: {app_name}")
    # === SỬA LẠI QUERY ĐỂ LẤY ĐÚNG THUỘC TÍNH ===
    # Lấy tất cả thuộc tính để đảm bảo không thiếu gì
    cypher = """
    MATCH (s:Screen {screen_id: $screenId, app_name: $appName})-[r:TRANSITION]->(t:Screen)
    RETURN properties(r) as props
    """
    # ==========================================
    results = execute_read(cypher, {"screenId": screen_id, "appName": app_name})
    if results is not None:
        # Trả về list các dict chứa thuộc tính của mỗi quan hệ
        transitions_data = [record.get('props', {}) for record in results]
        logger.debug(f"Found {len(transitions_data)} outgoing transitions for {screen_id}. Sample: {transitions_data[:2]}")
        return transitions_data
    else:
        logger.error(f"Failed to query outgoing transitions for screen {screen_id}, app {app_name}")
        return None

# ...

# ... (các hàm khác) ...



def update_element_interaction_stats(screen_id: str, element_id: str, identifier_type: str, success: bool) -> bool:
    """
    Cập nhật attempt_count, success_count và is_clickable_observed/is_editable_observed
    cho một element cụ thể trong list 'elements' của node Screen.
    """
    logger = current_app.logger if current_app else print
    if not screen_id or not element_id:
        logger.error("update_element_interaction_stats: screen_id and element_id are required.")
        return False

    driver = get_driver()
    if not driver: return False

    try:
        with driver.session(database=current_app.config.get('NEO4J_DATABASE', 'neo4j')) as session:
            # Cách tiếp cận: Đọc list elements, sửa trong Python, ghi lại toàn bộ list
            # 1. Đọc list elements hiện tại
            read_query = "MATCH (s:Screen {screen_id: $screen_id}) RETURN s.elements AS elements"
            result = session.run(read_query, screen_id=screen_id)
            record = result.single()
            if not record or record["elements"] is None:
                logger.warning(f"Screen node {screen_id} not found or has no elements list to update stats.")
                # Có thể coi là thành công vì không có gì để update, hoặc false nếu muốn bắt buộc node tồn tại
                return True # Hoặc False

            current_elements = record["elements"]
            updated = False
            new_elements_list = []

            # 2. Tìm và cập nhật element trong Python
            found_element = False
            for element in current_elements:
                # Đảm bảo element là dict và có element_id
                if isinstance(element, dict) and element.get('element_id') == element_id:
                    found_element = True
                    element['attempt_count'] = element.get('attempt_count', 0) + 1
                    if success:
                        element['success_count'] = element.get('success_count', 0) + 1
                        # Giả sử click/input thành công nghĩa là nó có thể tương tác được
                        if identifier_type and 'input' in identifier_type.lower(): # Ví dụ heuristic đơn giản
                             element['is_editable_observed'] = True
                        else:
                             element['is_clickable_observed'] = True
                    element['last_seen_timestamp'] = datetime.now(timezone.utc) # Cập nhật luôn timestamp?
                    updated = True
                new_elements_list.append(element) # Thêm lại vào list mới (dù có sửa hay không)

            if not found_element:
                 logger.warning(f"Element '{element_id}' not found within elements list of screen '{screen_id}' to update stats.")
                 # Quyết định xem có nên trả về True hay False ở đây
                 return True # Tạm coi là thành công nếu không tìm thấy element để update

            # 3. Ghi lại toàn bộ list elements nếu có thay đổi
            if updated:
                write_query = "MATCH (s:Screen {screen_id: $screen_id}) SET s.elements = $elements_list"
                session.run(write_query, screen_id=screen_id, elements_list=new_elements_list)
                logger.debug(f"Updated interaction stats for element '{element_id}' on screen '{screen_id}'. Success: {success}")

            return True
    except ServiceUnavailable as e:
        logger.error(f"Neo4j Connection Error (update_element_stats): {e}")
        return False
    except Exception as e:
        logger.error(f"Neo4j Error (update_element_stats for {screen_id}/{element_id}): {e}", exc_info=True)
        return False

def get_screen_with_elements(screen_id: str) -> dict | None:
    # ... (logic dùng screen_id) ...
    driver = get_driver()
    if not driver: return None
    try:
        with driver.session(database=current_app.config.get('NEO4J_DATABASE', 'neo4j')) as session:
             result = session.run("MATCH (s:Screen {screen_id: $screen_id}) RETURN s", screen_id=screen_id) # Dùng screen_id
             record = result.single()
             # ... (xử lý record như trước) ...
             if record and record['s']: return dict(record['s'])
             return None
    # ... (xử lý exception) ...
    except Exception as e: return None

def update_element_classification(screen_id, element_id, classification):
    """Cập nhật classification cho một element cụ thể trong list elements của Screen."""
    driver = get_driver()
    with driver.session() as session:
        # Query này hơi phức tạp vì cần cập nhật một item trong list
        query = """
            MATCH (s:Screen {screen_id: $screen_id})
            // Giải nén list elements, tìm element cần cập nhật, tạo lại list mới
            WITH s, [el IN s.elements WHERE el.element_id = $element_id |
                el { .*, classification: $classification } // Cập nhật classification
            ] AS updated_elements,
            [el IN s.elements WHERE el.element_id <> $element_id] AS other_elements
            // Kết hợp lại thành list cuối cùng
            SET s.elements = other_elements + def merge_screen
            RETURN count(s) as updated_count
        """
        result = session.run(query,
                             screen_id=screen_id,
                             element_id=element_id,
                             classification=classification)
        return result.single()["updated_count"] > 0

def get_transitions_from_screen(screen_id):
    """Lấy tất cả các cạnh TRANSITION đi ra từ một Screen node."""
    driver = get_driver()
    with driver.session() as session:
        result = session.run(
            """
            MATCH (a:Screen {screen_id: $screen_id})-[r:TRANSITION]->(b:Screen)
            RETURN type(r) as type, properties(r) as properties, b.screen_id as target_screen_id
            """,
            screen_id=screen_id
        )
        # Chuyển đổi kết quả thành list các dict dễ sử dụng
        transitions = []
        for record in result:
            transition_data = dict(record['properties'])
            transition_data['type'] = record['type']
            transition_data['target_screen_id'] = record['target_screen_id']
            transitions.append(transition_data)
        return transitions



def get_app_graph_data(app_name: str) -> dict | None:
    """
    Lấy dữ liệu nodes (Screen) và edges (TRANSITION) chuẩn hóa cho Cytoscape.js.
    Đã sửa để trả về các thuộc tính cạnh riêng lẻ.
    """
    logger = current_app.logger if current_app else log
    logger.info(f"Getting graph data for app: '{app_name}'")
    if not app_name: return {"nodes": [], "edges": []}

    driver = get_driver()
    if not driver: return None

    cy_elements = {"nodes": [], "edges": []}
    node_ids_found = set()

    try:
        db_name = current_app.config.get('NEO4J_DATABASE', 'neo4j') if current_app else 'neo4j'
        with driver.session(database=db_name) as session:
            # 1. Lấy nodes Screen (Giữ nguyên query node)
            node_query = """
                MATCH (n:Screen {app_name: $app_name})
                WHERE n.screen_id IS NOT NULL
                RETURN n.screen_id AS id,
                       n.activity_name AS activity,
                       n.status AS status,
                       n.element_count AS element_count
                ORDER BY n.screen_id
            """
            logger.debug(f"Executing Node Query for app '{app_name}':\n{node_query}")
            nodes_result = session.run(node_query, app_name=app_name)
            processed_nodes = 0
            for record in nodes_result:
                node_id = record["id"]
                element_count = record["element_count"] if record["element_count"] is not None else 0
                node_data = {
                    "id": node_id,
                    "activity": record["activity"],
                    "status": record["status"],
                    "element_count": element_count,
                    "label": node_id[:8] + '...' if node_id and len(node_id) > 8 else node_id
                }
                node_data_clean = {k: v for k, v in node_data.items() if v is not None}
                cy_elements["nodes"].append({"data": node_data_clean})
                processed_nodes += 1
                node_ids_found.add(node_id)
            logger.info(f"Processed {processed_nodes} nodes for app '{app_name}'.")

            # 2. Lấy edges TRANSITION - === SỬA QUERY CẠNH ===
            edge_query = """
                MATCH (a:Screen {app_name: $app_name})-[r:TRANSITION]->(b:Screen {app_name: $app_name})
                WHERE a.screen_id IS NOT NULL AND b.screen_id IS NOT NULL
                RETURN a.screen_id AS source,
                       b.screen_id AS target,
                       // Lấy các thuộc tính nguyên thủy trực tiếp từ cạnh 'r'
                       r.actionType AS action_type,
                       r.macro_code AS macro_code,
                       r.element_id AS element_id, // ID của element đã tương tác
                       r.identifier_type AS identifier_type,
                       r.element_text AS element_text, // Text của element (nếu có)
                       r.status AS status,
                       r.attempt_count AS attempt_count,
                       r.success_count AS success_count,
                       r.params_json_str AS params_json, // Lấy chuỗi JSON params
                       elementId(r) AS neo4j_edge_id
            """
            # ============================================
            logger.debug(f"Executing Edge Query for app '{app_name}':\n{edge_query}")
            edges_result = session.run(edge_query, app_name=app_name)

            processed_edges = 0
            edge_counter = 0
            for record in edges_result:
                edge_counter += 1
                source_id = record["source"]
                target_id = record["target"]

                if source_id not in node_ids_found or target_id not in node_ids_found:
                    logger.warning(f"Skipping edge {record['neo4j_edge_id']} because source '{source_id}' or target '{target_id}' node was not found/valid.")
                    continue

                edge_id = f"edge_{record['neo4j_edge_id']}" if record['neo4j_edge_id'] else f"edge_{source_id}_{target_id}_{edge_counter}"

                # Tạo edge_data từ các thuộc tính đã lấy
                edge_data = {
                    "id": edge_id,
                    "source": source_id,
                    "target": target_id,
                    "action_type": record["action_type"],
                    "macro_code": record["macro_code"],
                    "element_id": record["element_id"], # <<< Giờ đã có trực tiếp
                    "identifier_type": record["identifier_type"],
                    "element_text": record["element_text"],
                    "status": record["status"],
                    "attempt_count": record["attempt_count"],
                    "success_count": record["success_count"],
                    "params_json": record["params_json"] # Truyền chuỗi JSON
                    # Thêm các thuộc tính khác nếu cần
                }
                # Loại bỏ các key có giá trị None trước khi gửi cho Cytoscape
                edge_data_clean = {k: v for k, v in edge_data.items() if v is not None}
                cy_elements["edges"].append({"data": edge_data_clean})
                processed_edges += 1

            logger.info(f"Processed {processed_edges} valid edges for app '{app_name}'.")

    except CypherSyntaxError as syn_err: # Bắt đúng lỗi Cypher
        logger.error(f"Neo4j Cypher Syntax Error (get_app_graph_data): {syn_err}")
        if 'edge_query' in locals(): logger.error(f"Failed Edge Query:\n{edge_query}")
        elif 'node_query' in locals(): logger.error(f"Failed Node Query:\n{node_query}")
        return None
    except ServiceUnavailable as e:
        logger.error(f"Neo4j Connection Error (get_app_graph_data): {e}")
        return None
    except Exception as e:
        logger.error(f"Neo4j Unexpected Error (get_app_graph_data): {e}", exc_info=True)
        return None

    logger.info(f"GraphDB: Final result has {len(cy_elements['nodes'])} nodes and {len(cy_elements['edges'])} edges for app '{app_name}'.")
    return cy_elements

# ... (các hàm khác) ...


def get_distinct_app_names() -> list[str] | None:
    """Lấy danh sách các app_name duy nhất từ các Screen node."""
    driver = get_driver()
    try:
        with driver.session() as session:
            query = "MATCH (n:Screen) WHERE n.app_name IS NOT NULL RETURN DISTINCT n.app_name AS appName ORDER BY appName"
            result = session.run(query)
            app_names = [record["appName"] for record in result]
            return app_names
    except ServiceUnavailable as e:
        print(f"Neo4j Error (get_distinct_app_names): Connection error - {e}")
        return None
    except Exception as e:
        print(f"Neo4j Error (get_distinct_app_names): Unexpected error - {e}")
        return None

def get_screen_nodes_for_management(app_name: str | None, 
                                    filter_status: str | None, 
                                    page: int = 1, 
                                    per_page: int = 15) -> tuple[list[dict] | None, int | None]:
    logger = current_app.logger
    driver = get_driver()
    if not driver:
        logger.error("get_screen_nodes_for_management: Neo4j driver not available.")
        return None, None

    nodes_list = []
    total_items = 0

    skip = (page - 1) * per_page

    # Xây dựng mệnh đề WHERE động
    where_clauses = []
    params = {"skip_val": skip, "limit_val": per_page}

    if app_name:
        where_clauses.append("s.app_name = $app_name_param")
        params["app_name_param"] = app_name

    if filter_status and filter_status != 'all':
        # Giả sử status 'unknown' được lưu là 'provisional_unknown'
        actual_filter_status = 'provisional_unknown' if filter_status == 'unknown' else filter_status
        where_clauses.append("s.status = $status_param")
        params["status_param"] = actual_filter_status

    where_statement = ""
    if where_clauses:
        where_statement = "WHERE " + " AND ".join(where_clauses)

    # Query đếm tổng số items khớp điều kiện
    count_query = f"""
        MATCH (s:Screen)
        {where_statement}
        RETURN count(s) AS total
    """
    # Query lấy dữ liệu trang
    data_query = f"""
        MATCH (s:Screen)
        {where_statement}
        RETURN 
            s.screen_id AS screen_id, 
            s.app_name AS app_name, 
            s.activity_name AS activity_name, 
            s.status AS status, 
            s.screenshot_path AS screenshot_path, 
            s.created_at AS created_at, 
            s.last_seen AS last_seen,
            s.width AS width,
            s.height AS height,
            s.node_classification AS node_classification,
            s.element_count AS defined_element_count, // Số element được định nghĩa/lưu lúc merge
            size([(s)-[:HAS_ELEMENT]->(e) | e]) as actual_element_count_rel, // Số element thực tế có quan hệ
            size([(s)<-[:TRANSITION]-(any_source) | any_source]) as incoming_transitions_count,
            size([(s)-[:TRANSITION]->(any_target) | any_target]) as outgoing_transitions_count
        ORDER BY s.last_seen DESC
        SKIP $skip_val LIMIT $limit_val
    """

    try:
        db_name = current_app.config.get('NEO4J_DATABASE', 'neo4j')
        with driver.session(database=db_name) as session:
            # Thực thi query đếm
            # logger.debug(f"Executing count query for node management: {count_query} with params {params}")
            count_result = session.run(count_query, params)
            total_record = count_result.single()
            if total_record:
                total_items = total_record["total"]

            if total_items > 0:
                # logger.debug(f"Executing data query for node management: {data_query} with params {params}")
                data_result = session.run(data_query, params)
                for record in data_result:
                    node_dict = dict(record) 
                    for dt_field in ['created_at', 'last_seen']: # Thêm các trường datetime khác nếu có
                        if node_dict.get(dt_field):
                            raw_dt_val = node_dict[dt_field]
                            try:
                                if hasattr(raw_dt_val, 'to_native') and callable(raw_dt_val.to_native):
                                    native_dt = raw_dt_val.to_native()
                                    if isinstance(native_dt, datetime): # Kiểm tra kết quả của to_native()
                                        if native_dt.tzinfo is None:
                                            native_dt = native_dt.replace(tzinfo=timezone.utc)
                                        node_dict[dt_field] = native_dt.isoformat()
                                    else: # Nếu to_native không trả về datetime (ví dụ Date, Time)
                                        node_dict[dt_field] = str(native_dt) 
                                elif isinstance(raw_dt_val, datetime): # Nếu đã là datetime của Python
                                    if raw_dt_val.tzinfo is None:
                                        raw_dt_val = raw_dt_val.replace(tzinfo=timezone.utc)
                                    node_dict[dt_field] = raw_dt_val.isoformat()
                                else: # Fallback nếu không phải các kiểu trên
                                    node_dict[dt_field] = str(raw_dt_val)
                            except Exception as e_dt_convert:
                                logger.warning(f"Could not convert datetime field '{dt_field}' (value: {raw_dt_val}) to ISO string: {e_dt_convert}")
                                node_dict[dt_field] = str(raw_dt_val) # Giữ lại dạng string nếu lỗi
                    nodes_list.append(node_dict)
        # logger.debug(f"get_screen_nodes_for_management: Fetched {len(nodes_list)} nodes for page {page}. Total items: {total_items}")
        return nodes_list, total_items
    except Exception as e:
        logger.error(f"Lỗi khi lấy screen nodes cho management: {e}", exc_info=True)
        return None, None

def update_node_classification_in_neo4j(screen_id: str, app_name: str, node_classification: str | None) -> bool:
    logger = current_app.logger
    driver = get_driver()
    if not driver:
        logger.error("update_node_classification_in_neo4j: Neo4j driver not available.")
        return False

    cypher = """
    MATCH (s:Screen {screen_id: $screen_id_param, app_name: $app_name_param})
    SET s.node_classification = $classification_param, s.updated_at = datetime()
    RETURN count(s) as updated_count
    """
    params = {
        "screen_id_param": screen_id,
        "app_name_param": app_name,
        "classification_param": node_classification # Có thể là None để xóa phân loại
    }
    if node_classification is not None:
        cypher = """
        MATCH (s:Screen {screen_id: $screen_id_param, app_name: $app_name_param})
        SET s.node_classification = $classification_param, s.updated_at = datetime()
        RETURN count(s) as updated_count
        """
        params = {
            "screen_id_param": screen_id,
            "app_name_param": app_name,
            "classification_param": node_classification
        }
    else: # Nếu muốn xóa phân loại
        cypher = """
        MATCH (s:Screen {screen_id: $screen_id_param, app_name: $app_name_param})
        REMOVE s.node_classification
        SET s.updated_at = datetime()
        RETURN count(s) as updated_count 
        """ # Cần kiểm tra xem node có thuộc tính đó không trước khi remove để tránh lỗi nếu không có.
          # Hoặc đơn giản là SET s.node_classification = null
        # An toàn hơn:
        # cypher = """
        # MATCH (s:Screen {screen_id: $screen_id_param, app_name: $app_name_param})
        # SET s.node_classification = NULL, s.updated_at = datetime()
        # RETURN count(s) as updated_count
        # """
        params = {
            "screen_id_param": screen_id,
            "app_name_param": app_name
            # "classification_param": None # không cần nếu dùng REMOVE hoặc SET NULL
        }
    try:
        db_name = current_app.config.get('NEO4J_DATABASE', 'neo4j')
        with driver.session(database=db_name) as session:
            result = session.run(cypher, params)
            record = result.single()
            if record and record["updated_count"] > 0:
                logger.info(f"Updated node_classification for {app_name}/{screen_id} to '{node_classification}'")
                return True
            else:
                # Kiểm tra xem node có tồn tại không
                check_exists_query = "MATCH (s:Screen {screen_id: $sid, app_name: $an}) RETURN count(s) as c"
                check_result = session.run(check_exists_query, sid=screen_id, an=app_name).single()
                if check_result and check_result["c"] > 0:
                     logger.info(f"Node {app_name}/{screen_id} exists, classification set to '{node_classification}' (no change or already null).")
                     return True # Coi như thành công nếu node tồn tại và giá trị đã là null/không đổi
                logger.warning(f"Node not found or not updated for classification: {app_name}/{screen_id}")
                return False
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật node_classification cho {app_name}/{screen_id}: {e}", exc_info=True)
        return False
    
def delete_screen_node_logic(screen_id: str, app_name: str) -> tuple[bool, str | None]:
    logger = current_app.logger
    driver = get_driver()
    if not driver:
        return False, "Neo4j driver not available."

    # Câu lệnh Cypher để xóa node Screen, các Element của nó,
    # và tất cả các quan hệ TRANSITION đi vào hoặc đi ra khỏi nó.
    # Quan hệ HAS_ELEMENT sẽ tự động bị xóa khi Element node bị xóa (nếu dùng DETACH DELETE e).
    cypher_delete_screen_elements_transitions = """
    MATCH (s:Screen {screen_id: $screen_id_param, app_name: $app_name_param})
    // Xóa các element của screen này và quan hệ HAS_ELEMENT
    OPTIONAL MATCH (s)-[he_rel:HAS_ELEMENT]->(e:Element)
    DETACH DELETE e
    // Xóa chính screen node và tất cả các quan hệ còn lại của nó (bao gồm TRANSITION)
    DETACH DELETE s
    RETURN count(s) as deleted_screen_count // Trả về số lượng screen đã xóa để xác nhận
    """
    params = {"screen_id_param": screen_id, "app_name_param": app_name}

    try:
        db_name = current_app.config.get('NEO4J_DATABASE', 'neo4j')
        deleted_count = 0
        with driver.session(database=db_name) as session:
            # Chạy trong một transaction để đảm bảo tính toàn vẹn
            def transaction_delete(tx, cypher, params_dict):
                result = tx.run(cypher, params_dict)
                record = result.single()
                return record["deleted_screen_count"] if record else 0

            deleted_count = session.write_transaction(transaction_delete, cypher_delete_screen_elements_transitions, params)

        if deleted_count > 0:
            logger.info(f"Successfully deleted Screen node '{screen_id}' for app '{app_name}' and its related elements/transitions.")
            return True, None
        else:
            logger.warning(f"Screen node '{screen_id}' for app '{app_name}' not found for deletion or already deleted.")
            return False, "Node không tìm thấy hoặc đã được xóa."
    except Exception as e:
        logger.error(f"Lỗi khi xóa Screen node '{screen_id}' for app '{app_name}': {e}", exc_info=True)
        return False, f"Lỗi server khi xóa Node: {str(e)}"

def get_elements_for_screen(tx, screen_id):
    """
    Lấy danh sách các elements cho một screen_id cụ thể.
    Chuyển đổi các thuộc tính thời gian sang chuỗi ISO 8601.
    """
    # Hãy đảm bảo bạn chỉ RETURN các thuộc tính thực sự cần thiết cho frontend.
    # Nếu có thuộc tính nào đó là ZonedDateTime và không cần thiết, hãy loại bỏ nó khỏi query.
    query = """
        MATCH (s:Screen {screen_id: $screen_id})-[:HAS_ELEMENT]->(e:Element)
        RETURN e.element_id AS element_id,
               e.bounds_left AS bounds_left, e.bounds_top AS bounds_top,
               e.bounds_right AS bounds_right, e.bounds_bottom AS bounds_bottom,
               e.coordinate_x AS coordinate_x, e.coordinate_y AS coordinate_y,
               e.element_type AS element_type, e.text_content AS text_content
            //   , e.created_at AS created_at // Ví dụ: nếu bạn có trường timestamp
    """
    elements = []
    try:
        results = tx.run(query, screen_id=screen_id)
        for record in results:
            # Chuyển đổi record thành dictionary và xử lý các kiểu dữ liệu
            element_data = _convert_neo4j_record_to_dict(record)
            elements.append(element_data)
        
        # Ghi log dữ liệu elements sau khi xử lý (nếu cần gỡ lỗi)
        # current_app.logger.debug(f"Processed elements for screen {screen_id}: {elements}")
        
        return elements
    except AttributeError as ae:
        # Ghi log lỗi AttributeError cụ thể này nếu nó xảy ra trong quá trình xử lý record
        error_message = f"AttributeError trong get_elements_for_screen khi xử lý record cho screen_id '{screen_id}': {str(ae)}"
        if current_app: # Kiểm tra current_app có tồn tại không (nếu hàm này được gọi ngoài context Flask)
            current_app.logger.error(error_message)
        else:
            print(error_message) # Fallback to print if no app context
        raise # Ném lại lỗi để được bắt ở tầng gọi API
    except Exception as e:
        error_message = f"Lỗi không xác định trong get_elements_for_screen cho screen_id '{screen_id}': {str(e)}"
        if current_app:
            current_app.logger.error(error_message, exc_info=True)
        else:
            print(error_message)
        raise


def update_screen_node_properties_by_id(screen_id_to_update: str, app_name: str, properties_to_set: dict) -> tuple[bool, str | None]:
    logger = current_app.logger
    driver = get_driver()
    if not driver:
        logger.error("update_screen_node_properties_by_id: Neo4j driver not available.")
        return False, "Neo4j driver not available."

    if not screen_id_to_update or not app_name or not properties_to_set:
        return False, "Thiếu screen_id, app_name hoặc properties để cập nhật."

    # Đảm bảo không cố gắng cập nhật các key chính một cách không an toàn
    properties_to_set.pop('screen_id', None) 
    properties_to_set.pop('app_name', None)
    properties_to_set['updated_at'] = datetime.now(timezone.utc).isoformat()


    cypher = """
    MATCH (s:Screen {screen_id: $screen_id_param, app_name: $app_name_param})
    SET s += $props_to_set 
    RETURN count(s) as updated_count
    """
    params = {
        "screen_id_param": screen_id_to_update,
        "app_name_param": app_name,
        "props_to_set": properties_to_set
    }
    
    try:
        db_name = current_app.config.get('NEO4J_DATABASE', 'neo4j')
        with driver.session(database=db_name) as session:
            result = session.run(cypher, params)
            record = result.single()
            if record and record["updated_count"] > 0:
                logger.info(f"Updated properties for node {app_name}/{screen_id_to_update} with: {properties_to_set}")
                return True, None
            else:
                logger.warning(f"Node not found or no properties updated for: {app_name}/{screen_id_to_update}")
                return False, "Node không tìm thấy hoặc không có thuộc tính nào được cập nhật."
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật thuộc tính node {app_name}/{screen_id_to_update}: {e}", exc_info=True)
        return False, f"Lỗi server khi cập nhật thuộc tính Node: {str(e)}"

def _convert_neo4j_record_to_dict(record):
    """
    Chuyển đổi một đối tượng neo4j.Record thành một dictionary,
    xử lý cẩn thận các kiểu dữ liệu thời gian và các kiểu dữ liệu đặc biệt khác của Neo4j.
    """
    data = {}
    for key, value in record.items():
        if value is None:
            data[key] = None
        elif hasattr(value, 'isoformat'): # Dùng cho các đối tượng datetime-like (bao gồm neo4j.time.DateTime, py_datetime)
            data[key] = value.isoformat()
        elif hasattr(value, 'to_native') and callable(value.to_native):
            # Dùng cho các kiểu neo4j.time.Date, neo4j.time.Time, neo4j.time.LocalDateTime
            # to_native() sẽ chuyển chúng thành các đối tượng date, time, datetime của Python
            native_value = value.to_native()
            if hasattr(native_value, 'isoformat'): # Nếu kết quả là datetime, chuyển sang ISO
                data[key] = native_value.isoformat()
            else: # Nếu là date hoặc time đơn thuần, chuyển sang string
                data[key] = str(native_value)
        elif isinstance(value, (list, dict)):
            # Xử lý đệ quy cho list hoặc dict nếu cần, mặc dù ở đây có thể không cần thiết
            # cho các thuộc tính element đơn giản.
            data[key] = value # Giả sử list/dict chứa các kiểu đơn giản
        else:
            # Các kiểu dữ liệu cơ bản khác (string, number, boolean)
            data[key] = value
    return data

def convert_unknown_node_to_defined_simple(unknown_screen_id: str, app_name: str, 
                                           new_defined_screen_id: str, 
                                           new_status: str = 'defined') -> tuple[bool, str | None]:
    logger = current_app.logger
    driver = get_driver()
    if not driver: return False, "Neo4j driver not available"

    # Kiểm tra xem new_defined_screen_id đã tồn tại chưa (cho app_name đó)
    # Nếu đã tồn tại, không nên gán trùng, báo lỗi.
    check_query = "MATCH (s:Screen {screen_id: $defined_id, app_name: $app}) RETURN s"
    existing_node = execute_read(check_query, {"defined_id": new_defined_screen_id, "app": app_name})
    if existing_node:
        logger.error(f"Không thể đổi tên node {unknown_screen_id} thành {new_defined_screen_id} vì ID này đã được sử dụng bởi node khác trong app {app_name}.")
        return False, f"Defined Screen ID '{new_defined_screen_id}' đã tồn tại cho app '{app_name}'."

    # Chỉ cập nhật node hiện tại
    # Lưu ý: Việc đổi ID của một node hiện có và giữ nguyên các cạnh là không đơn giản trong Cypher.
    # Cách tiếp cận này chỉ đổi thuộc tính screen_id và status.
    # Các cạnh vẫn trỏ đến node vật lý cũ, nhưng giờ node đó có screen_id mới.
    # Điều này có thể hoạt động nếu các query sau này luôn MATCH node theo screen_id mới.
    cypher_update = """
    MATCH (s:Screen {screen_id: $old_id, app_name: $app_name_param})
    WHERE s.status = 'provisional_unknown' OR s.status = 'unknown_temporary' // Chỉ cho phép đổi từ trạng thái unknown
    SET s.screen_id = $new_id, 
        s.status = $new_status,
        s.updated_at = datetime()
    RETURN s.screen_id as updated_id, s.status as updated_status
    """
    params = {
        "old_id": unknown_screen_id,
        "app_name_param": app_name,
        "new_id": new_defined_screen_id,
        "new_status": new_status
    }
    try:
        db_name = current_app.config.get('NEO4J_DATABASE', 'neo4j')
        with driver.session(database=db_name) as session:
            result = session.run(cypher_update, params)
            record = result.single()
            if record and record["updated_id"] == new_defined_screen_id:
                logger.info(f"Node Neo4j '{unknown_screen_id}' đã được cập nhật thành screen_id '{new_defined_screen_id}' và status '{new_status}'.")
                return True, None
            else:
                logger.warning(f"Không thể cập nhật Node Neo4j '{unknown_screen_id}' (có thể không ở trạng thái unknown hoặc không tìm thấy).")
                return False, f"Node '{unknown_screen_id}' không thể cập nhật (có thể không ở trạng thái unknown)."
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật Node Neo4j từ unknown sang defined: {e}", exc_info=True)
        return False, str(e)



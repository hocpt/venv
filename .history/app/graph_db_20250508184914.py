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
from neo4j.exceptions import ServiceUnavailable, CypherTypeError , CypherSyntaxError
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
                 extracted_elements: list, log_id: int | None, screenshot_path: str | None = None) -> bool:
    """
    Tạo hoặc cập nhật node Screen với tên thuộc tính chuẩn hóa (snake_case).
    Lưu trữ danh sách element đã chuẩn hóa thành chuỗi JSON 'elements_data_json'.
    """
    # Lấy logger (ưu tiên logger của Flask app nếu có)
    logger = current_app.logger if current_app else log

    # === LOG 1: Bắt đầu hàm ===
    logger.debug(f"[merge_screen] Bắt đầu xử lý cho screen_id: {screen_id}, app: {app_name}")
    logger.debug(f"[merge_screen] screenshot_path nhận được: '{screenshot_path}'")

    # Kiểm tra tham số bắt buộc
    if not screen_id or not app_name:
        logger.error("[merge_screen] Lỗi: screen_id và app_name là bắt buộc.")
        return False

    # Lấy driver Neo4j
    driver = get_driver()
    if not driver:
        logger.error("[merge_screen] Lỗi: Không lấy được Neo4j driver.")
        return False

    # Lấy thời gian hiện tại (UTC)
    current_time_utc = datetime.now(timezone.utc)
    current_time_iso = current_time_utc.isoformat() # Dùng ISO string cho timestamp trong element list

    # --- Bước 1: Chuẩn hóa danh sách elements ---
    standardized_elements = []
    if extracted_elements and isinstance(extracted_elements, list):
        logger.debug(f"[merge_screen] Chuẩn hóa {len(extracted_elements)} elements đầu vào...")
        for el_count, el in enumerate(extracted_elements):
            if not isinstance(el, dict):
                logger.warning(f"[merge_screen] Bỏ qua element không phải dict ở index {el_count}: {el}")
                continue

            # Lấy element_id và identifier_type (Đã được chuẩn hóa ở bước trước)
            element_id_val = el.get('element_id')
            identifier_type_val = el.get('identifier_type')

            if element_id_val:
                element_entry = {
                    'element_id': element_id_val, # QUAN TRỌNG: Phải có key này
                    'identifier_type': identifier_type_val, # Lưu lại type đã xác định
                    'element_type': el.get('element_type'),
                    'text_content': el.get('text_content'),
                    'coordinate_x': None, # Khởi tạo là None
                    'coordinate_y': None,
                    'bounds': el.get('bounds'), # Giữ nguyên dict bounds nếu có
                    # Thêm các trường bạn muốn lưu vào Neo4j node property
                    'classification': 'unclassified',
                    'attempt_count': 0,
                    'success_count': 0,
                    'is_clickable_observed': False,
                    'is_editable_observed': False,
                    'last_seen_timestamp': current_time_iso # Lưu dạng chuỗi ISO
                }
                # Xử lý coordinates
                coords = el.get('coordinates')
                if isinstance(coords, dict) and 'x' in coords and 'y' in coords:
                    try:
                        element_entry['coordinate_x'] = int(coords['x'])
                        element_entry['coordinate_y'] = int(coords['y'])
                    except (TypeError, ValueError):
                         logger.warning(f"[merge_screen] Tọa độ không hợp lệ cho element {el_count}: {coords}")

                # Loại bỏ key có giá trị None để lưu trữ gọn hơn
                element_entry_clean = {k: v for k, v in element_entry.items() if v is not None}

                # Đảm bảo element_id luôn có mặt (dù giá trị có thể bị lọc nếu là None, nên check lại)
                if 'element_id' not in element_entry_clean and element_id_val:
                    element_entry_clean['element_id'] = element_id_val

                standardized_elements.append(element_entry_clean)
            else:
                logger.warning(f"[merge_screen] Bỏ qua element không có element_id ở index {el_count}: {el}")
    else:
        logger.warning("[merge_screen] extracted_elements không phải list hoặc rỗng.")

    logger.debug(f"[merge_screen] Kết thúc chuẩn hóa. Có {len(standardized_elements)} elements hợp lệ.")

    # --- Bước 2: Chuẩn bị thuộc tính Node và Chuỗi JSON Elements ---
    # Chuyển list element đã chuẩn hóa thành chuỗi JSON
    elements_data_json_str = '[]' # Mặc định là chuỗi mảng rỗng
    if standardized_elements:
        try:
            # Đảm bảo không có kiểu dữ liệu không serialize được
            elements_data_json_str = json.dumps(standardized_elements)
        except TypeError as json_err:
             logger.error(f"[merge_screen] Lỗi TypeError khi tạo JSON cho elements: {json_err}", exc_info=True)
             # Vẫn tiếp tục nhưng elements_data_json sẽ là '[]'
        except Exception as json_err:
             logger.error(f"[merge_screen] Lỗi không xác định khi tạo JSON cho elements: {json_err}", exc_info=True)

    # Chuẩn bị các tham số cho câu lệnh Cypher
    # Sử dụng tên snake_case cho các key trong params để khớp với query
    params = {
        "screen_id": screen_id,
        "app_name": app_name,
        "activity_name": activity_name or 'UnknownActivity',
        "status": 'provisional', # Trạng thái ban đầu khi tạo/cập nhật từ log
        "last_analyzed_log_id": log_id, # Lưu log ID nguồn (có thể None)
        "last_seen": current_time_utc, # Lưu dạng DateTime của Neo4j
        "element_count": len(standardized_elements),
        "screenshot_path": screenshot_path, # Có thể là None
        "elements_data_json": elements_data_json_str # <<< Chuỗi JSON element
    }

    # === LOG 2: Kiểm tra Params trước khi thực thi ===
    logger.debug(f"[merge_screen] Chuẩn bị thực thi Cypher với Params (elements_data_json rút gọn):")
    log_params = params.copy()
    log_params['elements_data_json'] = log_params['elements_data_json'][:100] + '...' if log_params.get('elements_data_json') else '[]'
    logger.debug(json.dumps(log_params, indent=2, default=str)) # Dùng default=str để xử lý datetime
    # =============================================

    # --- Bước 3: Thực thi Cypher MERGE ---
    try:
        db_name = current_app.config.get('NEO4J_DATABASE', 'neo4j') if current_app else 'neo4j'
        with driver.session(database=db_name) as session:
            # Câu lệnh MERGE sử dụng tên thuộc tính snake_case
            # Cập nhật hoặc tạo node :Screen dựa trên screen_id
            # Gán tất cả các thuộc tính mới (dùng $param)
            query = """
            MERGE (s:Screen {screen_id: $screen_id})
            ON CREATE SET
                s.app_name = $app_name,
                s.activity_name = $activity_name,
                s.status = $status,
                s.last_analyzed_log_id = $last_analyzed_log_id,
                s.last_seen = $last_seen,
                s.element_count = $element_count,
                s.screenshot_path = $screenshot_path,
                s.elements_data_json = $elements_data_json, // Lưu chuỗi JSON
                s.created_at = $last_seen                 // Đặt created_at khi tạo
            ON MATCH SET
                s.app_name = $app_name,                   // Luôn cập nhật app_name
                s.activity_name = $activity_name,       // Luôn cập nhật activity
                // s.status = $status,                  // Cân nhắc có ghi đè status không?
                s.last_analyzed_log_id = $last_analyzed_log_id, // Cập nhật log ID nguồn
                s.last_seen = $last_seen,                 // Cập nhật thời gian thấy
                s.element_count = $element_count,         // Cập nhật số lượng element
                s.screenshot_path = $screenshot_path,     // Cập nhật ảnh chụp
                s.elements_data_json = $elements_data_json, // Luôn cập nhật data elements
                s.updated_at = $last_seen                 // Đặt updated_at khi khớp
            """
            # Driver Neo4j sẽ tự xử lý kiểu datetime của Python thành DateTime của Neo4j
            # Chuỗi JSON elements_data_json sẽ được lưu dạng String
            logger.debug(f"[merge_screen] Executing MERGE Screen query for {screen_id}")
            session.run(query, params) # Truyền dict params trực tiếp
            logger.info(f"[merge_screen] Successfully merged Screen node: {screen_id}")
            return True

    # Xử lý các loại lỗi cụ thể
    except CypherTypeError as type_error:
         logger.error(f"[merge_screen] Neo4j TypeError merging screen {screen_id}: {type_error}", exc_info=True)
         logger.error(f"   >>> Failing Params: {json.dumps(log_params, indent=2, default=str)}") # Log params lỗi
         return False
    except ServiceUnavailable as conn_err:
        logger.error(f"[merge_screen] Neo4j Connection Error: {conn_err}")
        return False
    except Exception as e:
        logger.error(f"[merge_screen] Unexpected Neo4j Error merging screen {screen_id}: {e}", exc_info=True)
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
     driver = get_driver()
     if not driver: return None
     details = None
     logger = current_app.logger if current_app else log
     try:
         db_name = current_app.config.get('NEO4J_DATABASE', 'neo4j') if current_app else 'neo4j'
         with driver.session(database=db_name) as session:
             # Lấy properties (bao gồm cả elements_data_json nếu merge_screen đã lưu)
             query = "MATCH (s:Screen {screen_id: $screen_id}) RETURN properties(s) AS props" # Query này lấy properties
             logger.debug(f"Executing Neo4j query: {query} with screen_id={screen_id}")
             result = session.run(query, screen_id=screen_id)
             record = result.single()
             if record and record["props"]:
                 details = dict(record["props"]) # Chuyển thành dict
                 logger.debug(f"Fetched properties for screen {screen_id}")
             else:
                 logger.warning(f"No properties found for screen {screen_id}")
     except ServiceUnavailable as e:
         logger.error(f"Neo4j Connection Error (get_screen_...): {e}")
     except Exception as e:
         logger.error(f"Neo4j Error getting screen details for {screen_id}: {e}", exc_info=True)
     return details


def get_screen_details_with_elements_json(screen_id: str) -> dict | None:
    """Lấy chi tiết node Screen, bao gồm cả chuỗi JSON elements_data_json."""
    driver = get_driver()
    if not driver: return None
    details = None
    logger = current_app.logger if current_app else log # Lấy logger
    try:
        db_name = current_app.config.get('NEO4J_DATABASE', 'neo4j') if current_app else 'neo4j'
        with driver.session(database=db_name) as session:
            # Lấy tất cả properties, bao gồm elements_data_json
            # Đảm bảo dùng tên cột snake_case nếu đã đổi trong DB
            query = "MATCH (s:Screen {screen_id: $screen_id}) RETURN properties(s) AS props"
            logger.debug(f"Executing Neo4j query for screen properties: {query} with screen_id={screen_id}")
            result = session.run(query, screen_id=screen_id)
            record = result.single()
            if record and record["props"]:
                details = dict(record["props"]) # Chuyển properties thành dict
                logger.debug(f"Successfully fetched properties for screen {screen_id}")
            else:
                logger.warning(f"No properties found for screen {screen_id}")
    except ServiceUnavailable as e:
        logger.error(f"Neo4j Connection Error (get_screen_details_...): {e}")
    except Exception as e:
        logger.error(f"Neo4j Error getting screen details for {screen_id}: {e}", exc_info=True)
    return details

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
            SET s.elements = other_elements + updated_elements
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
                                   n.element_count AS element_count,
                                   n.screenshot_path AS screenshot_path  // <<< THÊM DÒNG NÀY
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
                                    "screenshot_path": record["screenshot_path"], # <<< LẤY GIÁ TRỊ Ở ĐÂY
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
                                   r.actionType AS action_type,
                                   r.macro_code AS macro_code,
                                   r.element_id AS element_id,
                                   r.identifier_type AS identifier_type,
                                   r.element_text AS element_text,
                                   r.status AS status,
                                   r.attempt_count AS attempt_count,
                                   r.success_count AS success_count,
                                   r.params_json_str AS params_json,
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


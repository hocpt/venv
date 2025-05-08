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
from neo4j.exceptions import ServiceUnavailable, CypherTypeError 
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

def get_outgoing_transitions(screen_id: str, app_name: str) -> list[dict] | None:

    """
    Lấy danh sách các thuộc tính của các quan hệ TRANSITION đi ra
    từ một Screen node cụ thể.
    """
    log.debug(f"Querying outgoing transitions for screenId: {screen_id}, appName: {app_name}")
    cypher = """
    MATCH (s:Screen {screenId: $screenId, appName: $appName})-[r:TRANSITION]->(t:Screen)
    RETURN properties(r) as props
    """
    # results là list các dict, mỗi dict chứa {'props': {...}}
    results = execute_read(cypher, {"screenId": screen_id, "appName": app_name})
    if results is not None: # Phân biệt lỗi DB (None) và không có cạnh (list rỗng [])
        # Trả về list các dict chứa thuộc tính của mỗi quan hệ
        return [record.get('props', {}) for record in results]
    else:
        log.error(f"Failed to query outgoing transitions for screen {screen_id}, app {app_name}")
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
                 extracted_elements: list, log_id: int | None) -> bool:
    """
    Tạo hoặc cập nhật node Screen với tên thuộc tính chuẩn hóa (snake_case).
    Chuẩn hóa kiểu dữ liệu trong list 'elements' trước khi lưu.
    """
    logger = current_app.logger if current_app else print
    if not screen_id or not app_name:
        logger.error("merge_screen: screen_id and app_name are required.")
        return False

    driver = _get_driver()
    if not driver: return False

    current_time_utc = datetime.now(timezone.utc) # <<< Dùng datetime có timezone
    current_time_iso = current_time_utc.isoformat() # <<< Chuyển thành chuỗi ISO

    # --- Chuẩn bị standardized_elements với kiểu dữ liệu hợp lệ ---
    standardized_elements = []
    if extracted_elements:
        logger.debug(f"Standardizing {len(extracted_elements)} elements for screen {screen_id}")
        for el_count, el in enumerate(extracted_elements):
            if isinstance(el, dict) and el.get('element_id'):
                element_entry = {
                    'element_id': el['element_id'],
                    'identifier_type': el.get('identifier_type'),
                    'element_type': el.get('element_type'),
                    'text_content': el.get('text_content'),
                    # <<< Khởi tạo coordinate_x, coordinate_y là None >>>
                    'coordinate_x': None,
                    'coordinate_y': None,
                    'classification': 'unclassified',
                    'attempt_count': 0,
                    'success_count': 0,
                    'is_clickable_observed': False,
                    'is_editable_observed': False,
                    'last_seen_timestamp': current_time_iso # <<< LƯU DẠNG CHUỖI ISO >>>
                }
                # Xử lý coordinates
                coords = el.get('coordinates')
                if isinstance(coords, dict) and 'x' in coords and 'y' in coords:
                    try:
                        # <<< LƯU X, Y RIÊNG BIỆT >>>
                        element_entry['coordinate_x'] = int(coords['x'])
                        element_entry['coordinate_y'] = int(coords['y'])
                    except (TypeError, ValueError):
                        logger.warning(f"Invalid coordinate values in element {el_count} for screen {screen_id}: x={coords.get('x')}, y={coords.get('y')}")
                        # Giữ giá trị None đã khởi tạo
                else:
                    # Log nếu coordinates không đúng định dạng hoặc thiếu
                    if coords is not None:
                         logger.warning(f"Invalid 'coordinates' format in element {el_count} for screen {screen_id}: {coords}")


                # Chỉ giữ lại key có giá trị không phải None để lưu trữ gọn hơn
                element_entry_clean = {k:v for k,v in element_entry.items() if v is not None}
                standardized_elements.append(element_entry_clean)
            else:
                logger.warning(f"Skipping invalid element data at index {el_count} for screen {screen_id}: {el}")

    logger.debug(f"Finished standardizing elements for screen {screen_id}. Resulting list size: {len(standardized_elements)}")


    # --- Chuẩn bị screen_props ---
    screen_props = {
        "screen_id": screen_id,
        "app_name": app_name,
        "activity_name": activity_name or 'UnknownActivity',
        "status": 'provisional',
        "last_analyzed_log_id": log_id,
        "last_seen": current_time_utc, # <<< Dùng datetime timezone-aware cho thuộc tính node
        "element_count": len(standardized_elements)
    }

    try:
        with driver.session(database=current_app.config.get('NEO4J_DATABASE', 'neo4j')) as session:
            # Dùng tên chuẩn snake_case
            query = """
            MERGE (s:Screen {screen_id: $props.screen_id})
            ON CREATE SET
                s.app_name = $props.app_name,
                s.activity_name = $props.activity_name,
                s.status = $props.status,
                s.elements = $elements_list, // Lưu list đã chuẩn hóa
                s.element_count = $props.element_count,
                s.last_analyzed_log_id = $props.last_analyzed_log_id,
                s.last_seen = $props.last_seen,
                s.created_at = $props.last_seen // Dùng datetime timezone-aware
            ON MATCH SET
                s.app_name = $props.app_name,
                s.activity_name = $props.activity_name,
                s.elements = $elements_list, // Ghi đè bằng list mới nhất
                s.element_count = $props.element_count,
                s.last_analyzed_log_id = $props.last_analyzed_log_id,
                s.last_seen = $props.last_seen,
                s.updated_at = $props.last_seen // Dùng datetime timezone-aware
            """
            # Driver sẽ tự chuyển datetime timezone-aware thành kiểu DateTime của Neo4j cho thuộc tính node
            # Nhưng list elements phải chứa kiểu nguyên thủy
            logger.debug(f"Executing MERGE Screen query for {screen_id} with {len(standardized_elements)} elements.")
            # Log một phần dữ liệu elements để kiểm tra trước khi chạy query
            # logger.debug(f"Sample elements data: {json.dumps(standardized_elements[:2], default=str)}")
            session.run(query, props=screen_props, elements_list=standardized_elements)
            logger.info(f"Successfully merged Screen node: {screen_id}")
            return True
    except CypherTypeError as type_error: # Bắt lỗi cụ thể hơn
         logger.error(f"Neo4j TypeError (merge_screen for {screen_id}): {type_error}", exc_info=True) # Log cả traceback
         # Log chi tiết hơn về dữ liệu gây lỗi
         logger.error(f"Data that caused TypeError in elements_list (first 5 elements):")
         for i, el_data in enumerate(standardized_elements[:5]):
              logger.error(f"  Element {i}: {el_data}")
         return False
    except ServiceUnavailable as e:
        logger.error(f"Neo4j Connection Error (merge_screen): {e}")
        return False
    except Exception as e:
        logger.error(f"Neo4j Error (merge_screen for {screen_id}): {e}", exc_info=True)
        return False

# --- HÀM MERGE CẠNH TRANSITION (Chuẩn hóa) ---
def merge_transition(source_screen_id: str, target_screen_id: str, app_name: str,
                     action_details: dict, result_status: str, log_id: int | None) -> bool:
    """
    Tạo hoặc cập nhật cạnh TRANSITION với tên thuộc tính chuẩn hóa.
    Cập nhật attempt_count, success_count.
    """
    logger = current_app.logger if current_app else print
    if not source_screen_id or not target_screen_id or not app_name or not action_details:
        logger.error("merge_transition: source_id, target_id, app_name, and action_details are required.")
        return False

    driver = get_driver()
    if not driver: return False

    # Chuẩn hóa action_details (đảm bảo là dict, có thể thêm/xóa key nếu cần)
    # Ví dụ: chỉ giữ lại các key quan trọng để MERGE
    merge_key_action = {
        "actionType": action_details.get("actionType"),
        "element_id": action_details.get("element_id") or action_details.get("onElementId"),
        "identifier_type": action_details.get("identifier_type"),
        # Thêm các key khác nếu cần để xác định duy nhất hành động
    }
    # Loại bỏ key có giá trị None khỏi merge_key
    merge_key_action = {k: v for k, v in merge_key_action.items() if v is not None}

    # Nếu không có đủ thông tin để tạo merge key, không thể MERGE đáng tin cậy
    if not merge_key_action.get("actionType") or not merge_key_action.get("element_id"):
         logger.warning(f"Cannot reliably MERGE transition due to missing actionType or element_id in action_details: {action_details}. Falling back to simple CREATE (might create duplicates).")
         # Cân nhắc logic CREATE thay thế ở đây nếu muốn, hoặc trả về False
         # return False # Hoặc chuyển sang logic CREATE

    current_time = datetime.now(timezone.utc)
    is_success = (result_status == 'success')

    try:
        with driver.session(database=current_app.config.get('NEO4J_DATABASE', 'neo4j')) as session:
            # Dùng MERGE dựa trên node nguồn, đích và action_details (merge_key)
            # ON CREATE: Đặt giá trị ban đầu
            # ON MATCH: Cập nhật counts và timestamp
            query = """
            MATCH (a:Screen {screen_id: $source_id, app_name: $app_name}),
                  (b:Screen {screen_id: $target_id, app_name: $app_name})
            MERGE (a)-[r:TRANSITION {action_details_key: $action_key}]->(b) // Dùng key đã chuẩn hóa để MERGE
            ON CREATE SET
                r.action_details = $full_action_details, // Lưu action_details đầy đủ
                r.status = 'provisional',
                r.attempt_count = 1,
                r.success_count = CASE WHEN $success THEN 1 ELSE 0 END,
                r.first_seen = $now,
                r.last_seen = $now,
                r.last_successful_log_id = CASE WHEN $success THEN $log_id ELSE null END
            ON MATCH SET
                r.action_details = $full_action_details, // Cập nhật action_details đầy đủ mới nhất
                r.attempt_count = r.attempt_count + 1,
                r.success_count = r.success_count + CASE WHEN $success THEN 1 ELSE 0 END,
                r.last_seen = $now,
                r.last_successful_log_id = CASE WHEN $success THEN $log_id ELSE r.last_successful_log_id END
                // Status có thể cập nhật ở đây hoặc trong logic xác nhận riêng
            """
            session.run(query,
                        source_id=source_screen_id,
                        target_id=target_screen_id,
                        app_name=app_name,
                        action_key=merge_key_action, # Key dùng để MERGE
                        full_action_details=action_details, # Lưu chi tiết đầy đủ
                        success=is_success,
                        log_id=log_id,
                        now=current_time)
            logger.debug(f"Merged TRANSITION: {source_screen_id} -> {target_screen_id}")
            return True
    except ServiceUnavailable as e:
        logger.error(f"Neo4j Connection Error (merge_transition): {e}")
        return False
    except Exception as e:
        logger.error(f"Neo4j Error (merge_transition {source_screen_id}->{target_screen_id}): {e}", exc_info=True)
        return False

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
    Lấy dữ liệu nodes (Screen) và edges (TRANSITION) chuẩn hóa (snake_case) cho Cytoscape.js.
    """
    logger = current_app.logger if current_app else print
    logger.info(f"Getting graph data for app: '{app_name}'")
    if not app_name: return {"nodes": [], "edges": []}

    driver = get_driver()
    if not driver: return None

    cy_elements = {"nodes": [], "edges": []}

    try:
        with driver.session(database=current_app.config.get('NEO4J_DATABASE', 'neo4j')) as session:
            # 1. Lấy nodes Screen - Dùng tên chuẩn 'screen_id', 'activity_name', 'status', 'elements'
            node_query = """
                MATCH (n:Screen {app_name: $app_name})
                // Đảm bảo node có screen_id mới lấy
                WHERE n.screen_id IS NOT NULL
                RETURN n.screen_id AS id,
                       n.activity_name AS activity,
                       n.status AS status,
                       // Dùng size(n.elements) an toàn hơn vì đã khởi tạo list rỗng
                       size(n.elements) AS element_count
                ORDER BY n.screen_id
            """
            logger.debug(f"Executing Node Query for app '{app_name}':\n{node_query}")
            nodes_result = session.run(node_query, app_name=app_name)

            processed_nodes = 0
            node_ids_found = set() # Để kiểm tra cạnh hợp lệ
            for record in nodes_result:
                node_id = record["id"]
                # Đã có WHERE n.screen_id IS NOT NULL trong query
                # element_count mặc định là 0 nếu list rỗng
                element_count = record["element_count"] if record["element_count"] is not None else 0

                node_data = {
                    "id": node_id,
                    "activity": record["activity"],
                    "status": record["status"],
                    "element_count": element_count,
                    "label": node_id[:8] + '...' if len(node_id) > 8 else node_id
                }
                node_data_clean = {k: v for k, v in node_data.items() if v is not None}
                cy_elements["nodes"].append({"data": node_data_clean})
                processed_nodes += 1
                node_ids_found.add(node_id) # Thêm ID node hợp lệ vào set

            logger.info(f"Processed {processed_nodes} nodes for app '{app_name}'.")

            # 2. Lấy edges TRANSITION - Dùng tên chuẩn 'screen_id', 'action_details', 'status'
            edge_query = """
                MATCH (a:Screen {app_name: $app_name})-[r:TRANSITION]->(b:Screen {app_name: $app_name})
                WHERE a.screen_id IS NOT NULL AND b.screen_id IS NOT NULL // Chỉ lấy cạnh giữa các node hợp lệ
                RETURN a.screen_id AS source,
                       b.screen_id AS target,
                       r.action_details AS action, // Có thể NULL
                       r.status AS status,         // Có thể NULL
                       elementId(r) AS neo4j_edge_id
            """
            logger.debug(f"Executing Edge Query for app '{app_name}':\n{edge_query}")
            edges_result = session.run(edge_query, app_name=app_name)

            processed_edges = 0
            edge_counter = 0
            for record in edges_result:
                edge_counter += 1
                source_id = record["source"]
                target_id = record["target"]

                # Kiểm tra xem source và target có nằm trong danh sách node hợp lệ đã lấy không
                if source_id not in node_ids_found or target_id not in node_ids_found:
                    logger.warning(f"Skipping edge {record['neo4j_edge_id']} because source '{source_id}' or target '{target_id}' node was not found/valid.")
                    continue

                edge_id = f"edge_{record['neo4j_edge_id']}" if record['neo4j_edge_id'] else f"edge_{source_id}_{target_id}_{edge_counter}"
                action_details = record['action'] or {}
                clicked_element_id = None
                if isinstance(action_details, dict):
                    clicked_element_id = action_details.get('element_id') or action_details.get('target', {}).get('element_id') # Ưu tiên key 'element_id'

                edge_data = {
                    "id": edge_id,
                    "source": source_id,
                    "target": target_id,
                    "status": record["status"],
                    "action_type": action_details.get("actionType"),
                    **({"element_id": clicked_element_id} if clicked_element_id else {})
                }
                edge_data_clean = {k: v for k, v in edge_data.items() if v is not None}
                cy_elements["edges"].append({"data": edge_data_clean})
                processed_edges += 1

            logger.info(f"Processed {processed_edges} edges for app '{app_name}'.")

    except neo4j.exceptions.CypherSyntaxError as syn_err:
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


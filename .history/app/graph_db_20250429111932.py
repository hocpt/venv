# hpt3/app/graph_db.py
from neo4j import GraphDatabase, Driver, Session, Transaction, basic_auth
# KHÔNG import current_app trực tiếp ở đây nếu không cần thiết trong các hàm context-safe
from flask import g # Vẫn cần g để lưu driver
# Import logging tiêu chuẩn
import logging
from datetime import datetime, timezone
import json

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

# --- Các hàm cụ thể cho App Map ---
# ... (Các hàm khác như create_or_update_screen_node nên dùng `log` thay vì `current_app.logger`) ...

log.info("DEBUG: app/graph_db.py - Module loaded completely.") # <<< Dùng log chuẩn

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
    Tăng bộ đếm 'count' và cập nhật 'lastTransitionTime'.
    'action_data' chứa thông tin hành động (ví dụ: từ previous_action).
    """
    if not all([source_screen_id, target_screen_id, app_name, action_data]):
         log.error("Missing parameters for graph_db.create_transition_relationship.")
         return False

    # Thuộc tính định danh quan hệ (key để MERGE)
    identity_props = {
        "actionType": action_data.get("actionType"),
        "onElementId": action_data.get("onElementId"),
        "onElementText": action_data.get("onElementText"),
        "onElementClass": action_data.get("onElementClass") # Thêm Class nếu có
        # Thêm các thuộc tính khác bạn cho là định danh cho hành động
    }
    identity_props_clean = {k: v for k, v in identity_props.items() if v is not None}
    if not identity_props_clean: # Cần ít nhất một thuộc tính để MERGE
         log.warning(f"Cannot MERGE transition from {source_screen_id} to {target_screen_id} for app {app_name} due to empty identity properties in action_data: {action_data}")
         # Có thể bạn muốn tạo quan hệ không có thuộc tính định danh?
         # MERGE (source)-[r:TRANSITION]->(target) ... (ít chính xác hơn)
         return False # Tạm thời không tạo nếu không có key định danh

    # Thuộc tính cập nhật/thêm vào quan hệ
    update_props = action_data.copy()
    update_props['lastTransitionTime'] = datetime.now(timezone.utc).isoformat()
    # Bỏ các thuộc tính định danh khỏi update_props để tránh ghi đè không cần thiết
    for key in identity_props_clean:
        update_props.pop(key, None)
    update_props_clean = {k: v for k, v in update_props.items() if v is not None}


    # Cypher để MERGE quan hệ
    # Đảm bảo MATCH node nguồn và đích thuộc đúng appName
    # identityPropsClean dùng để tìm hoặc tạo quan hệ
    # updatePropsClean dùng để cập nhật thuộc tính mỗi lần khớp hoặc tạo mới
    cypher = """
    MATCH (source:Screen {screenId: $sourceId, appName: $appName}), (target:Screen {screenId: $targetId, appName: $appName})
    MERGE (source)-[r:TRANSITION $identityPropsClean]->(target)
    ON CREATE SET r = $updatePropsClean, r.count = 1, r.createdAt = datetime()
    ON MATCH SET r += $updatePropsClean, r.count = coalesce(r.count, 0) + 1, r.updatedAt = datetime()
    RETURN r
    """
    params = {
        "sourceId": source_screen_id,
        "targetId": target_screen_id,
        "appName": app_name,
        "identityPropsClean": identity_props_clean,
        "updatePropsClean": update_props_clean
    }

    success = execute_write(cypher, params)
    if not success:
        log.error(f"Failed create/update TRANSITION from {source_screen_id} to {target_screen_id} for app {app_name} (Action: {identity_props_clean.get('actionType')})")
    # else: # Bỏ log debug
        # log.debug(f"Successfully created/updated TRANSITION from {source_screen_id} to {target_screen_id} for app {app_name}")
    return success
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



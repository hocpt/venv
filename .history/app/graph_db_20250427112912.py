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

def create_or_update_screen_node(screen_id: str, app_name: str, properties: dict): # <<< Thêm app_name
    """
    Tạo Node Screen mới hoặc cập nhật, gắn liền với appName cụ thể.
    'screen_id' là định danh duy nhất trong ngữ cảnh appName đó.
    'properties' chứa các thông tin khác như activityName, structureHash, aiSummary...
    """
    if not screen_id or not app_name:
        log.error("create_or_update_screen_node: screen_id and app_name are required.")
        return False

    # Thêm appName vào properties sẽ lưu và cập nhật lastSeen
    properties['appName'] = app_name
    properties['lastSeen'] = datetime.now(timezone.utc).isoformat()
    # Loại bỏ screenId khỏi properties vì nó dùng để MERGE
    node_props = properties.copy()
    node_props.pop('screenId', None)
    node_props = {k: v for k, v in node_props.items() if v is not None}

    # MERGE node dựa trên cả screenId VÀ appName để đảm bảo tính duy nhất cho từng app
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
    else:
        log.debug(f"Successfully created/updated Screen node: {screen_id} for app: {app_name}")
    return success

def create_or_update_transition_relationship(source_screen_id: str, target_screen_id: str, app_name: str, action_data: dict): # <<< Thêm app_name
    """
    Tạo hoặc cập nhật quan hệ TRANSITION giữa hai Screen node CỦA CÙNG MỘT APP.
    """
    if not all([source_screen_id, target_screen_id, app_name, action_data]):
         log.error("Missing parameters for create_transition_relationship.")
         return False

    # Thuộc tính định danh quan hệ (vẫn giữ nguyên)
    identity_props = {
        "actionType": action_data.get("actionType"),
        "onElementId": action_data.get("onElementId"),
        "onElementText": action_data.get("onElementText")
    }
    identity_props_clean = {k: v for k, v in identity_props.items() if v is not None}

    # Thuộc tính cập nhật (thêm appName vào nếu muốn lưu trên quan hệ)
    update_props = action_data.copy()
    # update_props['appName'] = app_name # Tùy chọn: Lưu appName cả trên quan hệ
    update_props['lastTransitionTime'] = datetime.now(timezone.utc).isoformat()
    update_props_clean = {k: v for k, v in update_props.items() if v is not None}

    # MERGE quan hệ, đảm bảo MATCH node nguồn và đích thuộc đúng appName
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
        "appName": app_name, # <<< Dùng để MATCH node
        "identityPropsClean": identity_props_clean,
        "updatePropsClean": update_props_clean
    }

    success = execute_write(cypher, params)
    if not success:
        log.error(f"Failed create/update TRANSITION from {source_screen_id} to {target_screen_id} for app {app_name}")
    else:
        log.debug(f"Successfully created/updated TRANSITION from {source_screen_id} to {target_screen_id} for app {app_name}")
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

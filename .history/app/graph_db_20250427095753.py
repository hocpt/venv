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

def create_or_update_screen_node(screen_id: str, properties: dict):
    """
    Tạo Node Screen mới nếu chưa tồn tại, hoặc cập nhật thuộc tính nếu đã tồn tại.
    'properties' nên chứa các thông tin như activityName, structureHash, aiSummary, lastSeen...
    """
    # Luôn thêm/cập nhật thời gian nhìn thấy cuối cùng
    properties['lastSeen'] = datetime.now(timezone.utc).isoformat()
    # Xóa screenId khỏi properties vì nó dùng để MERGE
    node_props = properties.copy()
    node_props.pop('screenId', None) # Bỏ screenId khỏi dict props

    cypher = """
    MERGE (s:Screen {screenId: $screenId})
    ON CREATE SET s = $props, s.createdAt = datetime()
    ON MATCH SET s += $props, s.updatedAt = datetime()
    RETURN s.screenId as id
    """
    params = {"screenId": screen_id, "props": node_props}
    # Dùng execute_write vì có thao tác CREATE/SET
    success = execute_write(cypher, params)
    if not success:
        log.error(f"Failed to create/update Screen node: {screen_id}")
    return success

def create_or_update_transition_relationship(source_screen_id: str, target_screen_id: str, action_data: dict):
    """
    Tạo hoặc cập nhật quan hệ TRANSITION giữa hai Screen node.
    'action_data' chứa thông tin hành động (actionType, onElementId, onElementText...).
    """
    if not all([source_screen_id, target_screen_id, action_data]):
         log.error("Missing parameters for create_transition_relationship.")
         return False

    # Tạo key định danh cho mối quan hệ để MERGE chính xác hơn (tùy chọn)
    # Ví dụ đơn giản dựa trên loại và target cơ bản
    rel_identity_props = {
        "actionType": action_data.get("actionType"),
        "onElementId": action_data.get("onElementId"),
        "onElementText": action_data.get("onElementText")
    }
    # Các thuộc tính khác sẽ được cập nhật
    rel_update_props = action_data.copy()
    rel_update_props['lastTransitionTime'] = datetime.now(timezone.utc).isoformat()

    # Cypher để MERGE quan hệ, tăng bộ đếm 'count'
    cypher = """
    MATCH (source:Screen {screenId: $sourceId}), (target:Screen {screenId: $targetId})
    MERGE (source)-[r:TRANSITION {
        actionType: $identity.actionType,
        onElementId: $identity.onElementId,
        onElementText: $identity.onElementText
    }]->(target)
    ON CREATE SET r = $props, r.count = 1, r.createdAt = datetime()
    ON MATCH SET r += $props, r.count = coalesce(r.count, 0) + 1, r.updatedAt = datetime()
    RETURN r
    """
    params = {
        "sourceId": source_screen_id,
        "targetId": target_screen_id,
        "identity": {k: v for k, v in rel_identity_props.items() if v is not None}, # Chỉ dùng key có giá trị để MERGE
        "props": {k: v for k, v in rel_update_props.items() if v is not None} # Thuộc tính để SET
    }
    success = execute_write(cypher, params)
    if not success:
        log.error(f"Failed to create/update TRANSITION from {source_screen_id} to {target_screen_id}")
    return success

# --- Thêm các hàm truy vấn khác bạn cần ---
# def find_screen_by_hash(structure_hash: str) -> dict | None: ...
# def get_screen_details(screen_id: str) -> dict | None: ...
# def get_outgoing_transitions(screen_id: str) -> list[dict] | None: ...
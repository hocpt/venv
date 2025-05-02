# hpt3/app/graph_db.py
from neo4j import GraphDatabase, Driver, Session, Transaction, basic_auth
from flask import current_app, g # Để lấy config và quản lý driver/session
import json
from datetime import datetime, timezone

# --- Quản lý Driver ---
def get_driver() -> Driver | None:
    """Lấy Neo4j Driver từ Flask app context 'g' hoặc tạo mới."""
    if 'neo4j_driver' not in g:
        try:
            uri = current_app.config.get('NEO4J_URI')
            user = current_app.config.get('NEO4J_USER')
            password = current_app.config.get('NEO4J_PASSWORD')
            if not all([uri, user, password]):
                current_app.logger.error("Neo4j config missing (URI, USER, PASSWORD)")
                return None
            # Dùng basic_auth nếu Neo4j của bạn cấu hình như vậy
            g.neo4j_driver = GraphDatabase.driver(uri, auth=basic_auth(user, password))
            # Hoặc chỉ GraphDatabase.driver(uri, auth=(user, password)) tùy phiên bản driver
            current_app.logger.info("Neo4j Driver created and stored in app context 'g'.")
        except Exception as e:
            current_app.logger.error(f"Failed to create Neo4j Driver: {e}", exc_info=True)
            return None
    return g.neo4j_driver

def close_driver(e=None):
    """Đóng Neo4j Driver khi app context bị teardown."""
    driver = g.pop('neo4j_driver', None)
    if driver is not None:
        try:
            driver.close()
            current_app.logger.info("Neo4j Driver closed.")
        except Exception as e:
            current_app.logger.error(f"Error closing Neo4j Driver: {e}", exc_info=True)

def init_app(app):
    """Đăng ký hàm teardown để đóng driver khi app kết thúc."""
    app.teardown_appcontext(close_driver)
    current_app.logger.info("Neo4j Driver teardown registered.")

# --- Các hàm thực thi Query (Ví dụ) ---

def _execute_write_tx(tx: Transaction, cypher: str, params: dict = None):
    """Hàm helper để thực thi một transaction ghi."""
    result = tx.run(cypher, params or {})
    # Có thể log summary hoặc xử lý kết quả nếu cần
    # current_app.logger.debug(f"Neo4j Write TX executed: {result.consume().counters}")
    return result # Trả về đối tượng result để có thể lấy dữ liệu nếu query có RETURN

def _execute_read_tx(tx: Transaction, cypher: str, params: dict = None):
    """Hàm helper để thực thi một transaction đọc."""
    result = tx.run(cypher, params or {})
    # Trả về list các record (mỗi record là dict-like)
    return [record.data() for record in result]

# --- Hàm Cụ thể cho App Map ---

def create_or_update_screen_node(screen_data: dict):
    """
    Tạo mới hoặc cập nhật Node Screen trong Neo4j.
    screen_data cần chứa 'screenId' và các thuộc tính khác như 'activityName', 'structureHash', 'aiSummary'.
    """
    driver = get_driver()
    if not driver: return False
    screen_id = screen_data.get('screenId')
    if not screen_id:
         current_app.logger.error("Missing screenId in screen_data for Neo4j node.")
         return False

    # Chỉ lấy các thuộc tính hợp lệ để lưu vào node
    node_props = {
        "screenId": screen_id,
        "activityName": screen_data.get("activityName"),
        "structureHash": screen_data.get("structureHash"),
        "aiSummary": screen_data.get("aiSummary"),
        "lastSeen": datetime.now(timezone.utc).isoformat() # Luôn cập nhật lastSeen
    }
    # Loại bỏ các key có giá trị None
    node_props = {k: v for k, v in node_props.items() if v is not None}

    cypher = """
    MERGE (s:Screen {screenId: $screenId})
    ON CREATE SET s = $props, s.createdAt = datetime()
    ON MATCH SET s += $props, s.updatedAt = datetime()
    RETURN s.screenId as id
    """
    params = {"screenId": screen_id, "props": node_props}

    try:
        with driver.session() as session:
            result = session.execute_write(_execute_write_tx, cypher, params)
            # result ở đây là đối tượng Result, không phải list
            # Bạn có thể kiểm tra kết quả nếu cần
            # record = result.single()
            # if record and record['id'] == screen_id:
            #     return True
            # else:
            #     return False
            return True # Giả định thành công nếu không có exception
    except Exception as e:
        current_app.logger.error(f"Error creating/updating Screen node {screen_id}: {e}", exc_info=True)
        return False

def create_or_update_transition_relationship(source_screen_id: str, target_screen_id: str, action_data: dict):
    """
    Tạo mới hoặc cập nhật Relationship TRANSITION giữa hai Screen node.
    action_data chứa thông tin về hành động (actionType, onElementId, onElementText...).
    """
    driver = get_driver()
    if not driver: return False
    if not all([source_screen_id, target_screen_id, action_data]):
         current_app.logger.error("Missing parameters for create_transition_relationship.")
         return False

    # Tạo một định danh duy nhất cho action để MERGE quan hệ chính xác hơn
    # (Ví dụ: hash của actionType + target element) - Tạm bỏ qua để đơn giản
    # action_key = f"{action_data.get('actionType', '')}_{action_data.get('onElementId', '')}_{action_data.get('onElementText', '')}"

    # Chỉ lấy các thuộc tính hợp lệ cho relationship
    rel_props = {
        "actionType": action_data.get("actionType"),
        "onElementId": action_data.get("onElementId"),
        "onElementText": action_data.get("onElementText"),
        "onElementClass": action_data.get("onElementClass"),
        # Thêm các thuộc tính khác nếu cần
        "lastTransitionTime": datetime.now(timezone.utc).isoformat()
    }
    rel_props = {k: v for k, v in rel_props.items() if v is not None}

    # MERGE quan hệ dựa trên screen nguồn, đích và có thể là loại hành động/target cơ bản
    # Tăng bộ đếm 'count' mỗi lần merge thành công
    cypher = """
    MATCH (source:Screen {screenId: $sourceId}), (target:Screen {screenId: $targetId})
    MERGE (source)-[r:TRANSITION {
        actionType: $props.actionType,
        onElementId: $props.onElementId,
        onElementText: $props.onElementText
    }]->(target)
    ON CREATE SET r = $props, r.count = 1, r.createdAt = datetime()
    ON MATCH SET r += $props, r.count = coalesce(r.count, 0) + 1, r.updatedAt = datetime()
    RETURN r
    """
    params = {"sourceId": source_screen_id, "targetId": target_screen_id, "props": rel_props}

    try:
        with driver.session() as session:
            session.execute_write(_execute_write_tx, cypher, params)
        return True
    except Exception as e:
        current_app.logger.error(f"Error creating/updating TRANSITION from {source_screen_id} to {target_screen_id}: {e}", exc_info=True)
        return False

def find_screen_by_hash(structure_hash: str) -> dict | None:
    """Tìm node Screen dựa trên structureHash."""
    driver = get_driver()
    if not driver or not structure_hash: return None

    cypher = "MATCH (s:Screen {structureHash: $hash}) RETURN s LIMIT 1"
    params = {"hash": structure_hash}
    try:
        with driver.session() as session:
            records = session.execute_read(_execute_read_tx, cypher, params)
            return records[0].get('s') if records else None # Trả về properties của node
    except Exception as e:
        current_app.logger.error(f"Error finding screen by hash {structure_hash}: {e}", exc_info=True)
        return None

def get_screen_details(screen_id: str) -> dict | None:
     """Lấy chi tiết một Screen node bằng ID."""
     # ... (Tương tự find_screen_by_hash nhưng dùng screenId) ...
     pass

def get_outgoing_transitions(screen_id: str) -> list[dict] | None:
     """Lấy danh sách các transition đi ra từ một Screen."""
     # ... (Dùng MATCH (s:Screen {screenId: $id})-[r:TRANSITION]->(t) RETURN r, t) ...
     pass

# Thêm các hàm truy vấn khác nếu cần (ví dụ: tìm đường đi, ...)
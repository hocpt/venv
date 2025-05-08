# hpt3/app/graph_db.py
import traceback
from neo4j import GraphDatabase, Driver, Session, Transaction, basic_auth
# KHÔNG import current_app trực tiếp ở đây nếu không cần thiết trong các hàm context-safe
from flask import g # Vẫn cần g để lưu driver
# Import logging tiêu chuẩn
import logging
from datetime import datetime, timezone
import json
from neo4j.exceptions import ServiceUnavailable
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

def merge_screen(screen_id, activity_name, extracted_elements, log_id):
    """
    Tạo hoặc cập nhật node Screen và danh sách elements của nó.

    Args:
        screen_id (str): ID của màn hình.
        activity_name (str): Tên activity.
        extracted_elements (list): List các dict element được trích xuất từ UI state của log này.
                                  Mỗi dict chứa ít nhất 'element_id'. Các key khác sẽ được thêm/cập nhật.
        log_id (int): ID của exploration_log đang được xử lý.
    """
    driver = get_driver()
    with driver.session() as session:
        # Bước 1: MERGE node Screen cơ bản và lấy elements hiện có
        result = session.run(
            """
            MERGE (s:Screen {screen_id: $screen_id})
            ON CREATE SET s.activity_name = $activity_name,
                          s.status = 'provisional',
                          s.elements = [], // Khởi tạo list rỗng
                          s.last_analyzed_log_id = $log_id,
                          s.created_at = datetime()
            ON MATCH SET s.last_analyzed_log_id = $log_id,
                         s.activity_name = $activity_name // Cập nhật activity nếu thay đổi
            RETURN s.elements AS existing_elements, id(s) AS node_id
            """,
            screen_id=screen_id,
            activity_name=activity_name,
            log_id=log_id
        )
        record = result.single()
        existing_elements_data = record["existing_elements"] if record else []
        node_id = record["node_id"] if record else None

        if node_id is None:
            # Trường hợp MERGE không thành công (hiếm khi xảy ra nếu query đúng)
            print(f"Error: Could not MERGE or find Screen node with id {screen_id}")
            return

        # Chuyển đổi list Map từ Neo4j (có thể chứa các kiểu dữ liệu Neo4j)
        # sang list dict chuẩn của Python nếu cần (thường thì driver xử lý tốt)
        existing_elements_map = {el['element_id']: el for el in existing_elements_data}


        # Bước 2: Xử lý cập nhật elements trong Python
        current_time = datetime.now()
        updated = False
        for new_el_data in extracted_elements:
            el_id = new_el_data.get('element_id')
            if not el_id:
                continue # Bỏ qua nếu không có element_id

            existing_el = existing_elements_map.get(el_id)

            if existing_el:
                # Element đã tồn tại, cập nhật timestamp
                if existing_el.get('last_seen_timestamp') != current_time:
                     existing_el['last_seen_timestamp'] = current_time
                     updated = True
                # Cập nhật các thuộc tính khác nếu cần (ví dụ: text_content nếu thay đổi)
                if 'text_content' in new_el_data and existing_el.get('text_content') != new_el_data['text_content']:
                    existing_el['text_content'] = new_el_data['text_content']
                    updated = True
                # Các cập nhật khác như is_clickable_observed, counts sẽ được xử lý dựa trên previous_action (ở tác vụ nền)
            else:
                # Element mới, thêm vào map
                new_element_entry = {
                    'element_id': el_id,
                    'element_type': new_el_data.get('element_type'),
                    'text_content': new_el_data.get('text_content'),
                    'is_clickable_observed': new_el_data.get('is_clickable_observed', False), # Sẽ cập nhật sau
                    'is_editable_observed': new_el_data.get('is_editable_observed', False), # Sẽ cập nhật sau
                    'classification': 'unclassified', # Mặc định
                    'attempt_count': 0,
                    'success_count': 0,
                    'last_seen_timestamp': current_time
                }
                existing_elements_map[el_id] = new_element_entry
                updated = True

        # Chỉ ghi lại nếu có thay đổi
        if updated:
             # Bước 3: Ghi lại toàn bộ danh sách elements đã cập nhật
             final_elements_list = list(existing_elements_map.values())
             session.run(
                 """
                 MATCH (s:Screen) WHERE id(s) = $node_id
                 SET s.elements = $elements_list
                 """,
                 node_id=node_id,
                 elements_list=final_elements_list
             )



def merge_transition(source_screen_id, target_screen_id, action_details, result_status, log_id):
    """
    Tạo hoặc cập nhật cạnh TRANSITION giữa hai Screen node.

    Args:
        source_screen_id (str): Screen ID nguồn.
        target_screen_id (str): Screen ID đích.
        action_details (dict): Chi tiết hành động gây ra transition (vd: element_id đã click).
        result_status (str): 'success' hoặc 'error'.
        log_id (int): ID của exploration_log xác nhận transition này.
    """
    driver = get_driver()
    # Chuyển dict thành string để lưu action_details nếu cần, hoặc đảm bảo driver xử lý Map đúng cách
    # action_details_str = json.dumps(action_details)

    with driver.session() as session:
        # Dùng MERGE để đảm bảo không tạo trùng lặp cạnh với cùng action_details
        # Lưu ý: So sánh Map trong Cypher có thể phức tạp, cân nhắc dùng một key đại diện nếu cần
        # Hoặc đơn giản là cho phép nhiều cạnh nếu action_details khác nhau (vd khác tọa độ click)
        # Ở đây giả định action_details đủ để định danh duy nhất transition mong muốn
        query = """
            MATCH (a:Screen {screen_id: $source_id}), (b:Screen {screen_id: $target_id})
            MERGE (a)-[r:TRANSITION {action_details: $action_details}]->(b)
            ON CREATE SET r.attempt_count = 1,
                          r.success_count = CASE WHEN $status = 'success' THEN 1 ELSE 0 END,
                          r.status = 'provisional',
                          r.last_successful_log_id = CASE WHEN $status = 'success' THEN $log_id ELSE null END,
                          r.created_at = datetime()
            ON MATCH SET r.attempt_count = r.attempt_count + 1,
                         r.success_count = CASE WHEN $status = 'success' THEN r.success_count + 1 ELSE r.success_count END,
                         // Cập nhật status dựa trên logic xác nhận (ví dụ: nếu success_count / attempt_count > threshold)
                         // r.status = CASE WHEN ... THEN 'confirmed' ELSE r.status END,
                         r.last_successful_log_id = CASE WHEN $status = 'success' THEN $log_id ELSE r.last_successful_log_id END
        """
        session.run(query,
                    source_id=source_screen_id,
                    target_id=target_screen_id,
                    action_details=action_details, # Truyền dưới dạng Map (dict)
                    status=result_status,
                    log_id=log_id)

def get_screen_with_elements(screen_id):
    """Lấy thông tin chi tiết của Screen node, bao gồm cả list elements."""
    driver = get_driver()
    with driver.session() as session:
        result = session.run(
            "MATCH (s:Screen {screen_id: $screen_id}) RETURN s",
            screen_id=screen_id
        )
        record = result.single()
        if record and record['s']:
            # Chuyển đổi node Neo4j thành dict Python
            node_data = dict(record['s'])
            # Đảm bảo các kiểu dữ liệu đặc biệt (như Datetime) được xử lý đúng nếu cần
            if 'elements' in node_data and isinstance(node_data['elements'], list):
                 # Chuyển đổi các Map trong list elements nếu cần
                 node_data['elements'] = [dict(el) for el in node_data['elements']]
            return node_data
        return None

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
    Lấy dữ liệu nodes (Screen) và edges (TRANSITION) cho một ứng dụng từ Neo4j,
    định dạng cho Cytoscape.js.

    Args:
        app_name: Tên package của ứng dụng (vd: 'com.google.android.gm').

    Returns:
        Dictionary chứa danh sách nodes và edges hoặc None nếu lỗi.
        Format: { "nodes": [ {"data": {"id": "screen_id", ...}}, ... ],
                  "edges": [ {"data": {"id": "edge_id", "source": "src_id", "target": "tgt_id", ...}}, ... ] }
    """
    if not app_name:
        return None
    driver = get_driver()
    nodes_result = []
    edges_result = []
    cy_elements = {"nodes": [], "edges": []} # Cấu trúc trả về cho Cytoscape

    try:
        with driver.session() as session:
            # 1. Lấy tất cả Screen nodes cho app này
            # Lấy các thuộc tính cơ bản cần thiết cho hiển thị
            node_query = """
                MATCH (n:Screen {app_name: $app_name})
                RETURN n.screen_id AS id, n.activity_name AS activity, n.status AS status, size(n.elements) AS element_count
            """
            nodes_result = session.run(node_query, app_name=app_name)
            for record in nodes_result:
                node_data = {
                    "id": record["id"],
                    "activity": record["activity"],
                    "status": record["status"],
                    "element_count": record["element_count"] or 0,
                    "label": record["id"][:8] # Nhãn hiển thị ngắn gọn trên node
                }
                cy_elements["nodes"].append({"data": node_data})

            # 2. Lấy tất cả TRANSITION edges giữa các Screen nodes của app này
            # Tạo ID duy nhất cho cạnh (ví dụ: source_target_type_hash)
            edge_query = """
                MATCH (a:Screen {app_name: $app_name})-[r:TRANSITION]->(b:Screen {app_name: $app_name})
                RETURN a.screen_id AS source, b.screen_id AS target,
                       r.action_details AS action, r.status AS status, elementId(r) AS neo4j_edge_id
            """
            edges_result = session.run(edge_query, app_name=app_name)
            edge_counter = 0
            for record in edges_result:
                edge_counter += 1
                # Tạo ID cạnh duy nhất, ví dụ dùng ID Neo4j hoặc tự tạo hash
                edge_id = f"edge_{record['neo4j_edge_id']}" if record['neo4j_edge_id'] else f"edge_{edge_counter}"

                action_details = record['action'] or {} # Đảm bảo action là dict
                edge_data = {
                    "id": edge_id,
                    "source": record["source"],
                    "target": record["target"],
                    "status": record["status"],
                    # Lấy thông tin action đơn giản để hiển thị nếu cần
                    "action_type": action_details.get("actionType"),
                    "element_id": action_details.get("element_id") or action_details.get("onElementId")
                }
                # Loại bỏ key có giá trị None
                edge_data = {k: v for k, v in edge_data.items() if v is not None}
                cy_elements["edges"].append({"data": edge_data})

        print(f"GraphDB: Found {len(cy_elements['nodes'])} nodes and {len(cy_elements['edges'])} edges for app '{app_name}'.")
        return cy_elements

    except ServiceUnavailable as e:
        print(f"Neo4j Error (get_app_graph_data): Connection error - {e}")
        # Hoặc raise lại lỗi để route xử lý
        return None
    except Exception as e:
        print(f"Neo4j Error (get_app_graph_data): Unexpected error - {e}")
        traceback.print_exc()
        return None

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


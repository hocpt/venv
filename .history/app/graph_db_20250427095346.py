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
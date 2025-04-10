# database.py
import psycopg2
import psycopg2.extras
import config # Import từ file config.py
import traceback
from flask import current_app
from datetime import datetime
import random
# --- Connection Helper ---
def get_db_connection():
    conn = None
    try:
        # !!! SỬA LẠI CÁCH LẤY CONFIG !!!
        db_host = current_app.config.get('DB_HOST', 'localhost')
        db_port = current_app.config.get('DB_PORT', '5432')
        db_name = current_app.config.get('DB_NAME')
        db_user = current_app.config.get('DB_USER')
        db_password = current_app.config.get('DB_PASSWORD')
        # !!! THÊM LOG KIỂM TRA Ở ĐÂY !!!
        print("--- DEBUG DB Connect Params ---")
        print(f"HOST: '{db_host}' (Type: {type(db_host)})")
        print(f"PORT: '{db_port}' (Type: {type(db_port)})")
        print(f"DBNAME: '{db_name}' (Type: {type(db_name)})")
        print(f"USER: '{db_user}' (Type: {type(db_user)})")
        # Chỉ in ra vài ký tự đầu của password để kiểm tra type mà không lộ pass
        pw_print = db_password[:3] + '...' if isinstance(db_password, str) and len(db_password) > 3 else db_password
        print(f"PASSWORD: '{pw_print}' (Type: {type(db_password)})")
        print("-------------------------------")
        if not db_name or not db_user or not db_password: # Giữ lại kiểm tra này
            print("LỖI (database.py): Thiếu cấu hình CSDL trong app.config!")
            return None

        # Lệnh kết nối - Lỗi xảy ra ở đây
        conn = psycopg2.connect(
            host=db_host,
            database=db_name,
            user=db_user,
            password=db_password,
            port=db_port
        )
        dsn = f"dbname='{db_name}' user='{db_user}' host='{db_host}' password='{db_password}' port='{db_port}'"
        print(f"DEBUG: Connecting with DSN: dbname='{db_name}' user='{db_user}' host='{db_host}' port='{db_port}' password='***'") # Che password
        conn = psycopg2.connect(dsn)
        print("DEBUG (database.py): Kết nối CSDL thành công (dùng DSN).")
        return conn
    except psycopg2.Error as db_err: # Bắt lỗi cụ thể của psycopg2
        print(f"LỖI KẾT NỐI CSDL (psycopg2.Error): {db_err}")
        print(traceback.format_exc()) # In traceback đầy đủ
        return None
    except RuntimeError as rt_err: # Lỗi nếu gọi ngoài app context
         print(f"LỖI (database.py): Lỗi runtime khi lấy config: {rt_err}")
         print(traceback.format_exc())
         return None
    except Exception as e: # Bắt các lỗi không ngờ khác
         print(f"LỖI (database.py): Lỗi không xác định khi kết nối CSDL: {e}")
         print(traceback.format_exc())
         return None

def find_transition(current_stage_id: str | None, user_intent: str | None) -> dict | None:
    """
    Tìm luật chuyển tiếp giai đoạn phù hợp nhất từ CSDL.

    Args:
        current_stage_id: ID của giai đoạn hiện tại.
        user_intent: Ý định của người dùng vừa được phát hiện.

    Returns:
        Một dictionary chứa thông tin luật chuyển tiếp (next_stage_id,
        action_to_suggest, response_template_ref), hoặc None nếu không tìm thấy/lỗi.
    """
    if not current_stage_id or not user_intent:
        print("DEBUG (database.py - find_transition): Thiếu current_stage_id hoặc user_intent.")
        return None

    transition_rule = None
    conn = get_db_connection()
    if not conn:
        return None

    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        print(f"DEBUG (database.py): Tìm transition cho stage='{current_stage_id}', intent='{user_intent}'")
        # Câu lệnh SQL tìm luật khớp chính xác intent HOẶC khớp intent 'any'
        # Ưu tiên luật khớp chính xác intent trước (priority cao hơn hoặc intent <> 'any')
        # Sau đó mới đến luật khớp 'any'
        # Sắp xếp theo độ ưu tiên (priority) giảm dần
        sql = """
            SELECT next_stage_id, action_to_suggest, response_template_ref
            FROM stage_transitions
            WHERE current_stage_id = %s AND (user_intent = %s OR user_intent = 'any')
            ORDER BY
                CASE user_intent WHEN 'any' THEN 0 ELSE 1 END DESC, -- Ưu tiên luật không phải 'any'
                priority DESC -- Ưu tiên luật có priority cao hơn
            LIMIT 1; -- Chỉ lấy luật phù hợp nhất
        """
        cur.execute(sql, (current_stage_id, user_intent))
        row = cur.fetchone()

        if row:
            transition_rule = dict(row) # Chuyển kết quả thành dictionary
            print(f"DEBUG (database.py): Transition tìm thấy: {transition_rule}")
        else:
            print(f"DEBUG (database.py): Không tìm thấy transition phù hợp cho stage='{current_stage_id}', intent='{user_intent}'.")

    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - find_transition): Truy vấn thất bại: {db_err}")
        print(traceback.format_exc())
    except Exception as e:
        print(f"LỖI (database.py - find_transition): Lỗi không xác định: {e}")
        print(traceback.format_exc())
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return transition_rule
# --- Account Functions ---

def get_rules_by_category(category=None): # Ví dụ sửa hàm lấy rules
    rules = []
    conn = get_db_connection()
    if not conn:
        return None # Trả về None nếu không kết nối được DB

    cur = None # Khởi tạo cur là None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        print(f"DEBUG (database.py): Đang truy vấn thông tin tài khoản: {account_id}")
        cur.execute("""
            SELECT account_id, platform, username, status, notes, goal, default_strategy_id
            FROM accounts
            WHERE account_id = %s
            """, (account_id,))
        row = cur.fetchone()
        if row:
            account_info = dict(row)
            print(f"DEBUG (database.py): Tìm thấy thông tin cho {account_id}")
        else:
            print(f"WARNING (database.py): Không tìm thấy tài khoản {account_id} trong CSDL")

    except psycopg2.Error as db_err: # Bắt lỗi truy vấn CSDL
        print(f"LỖI (database.py - get_account_details): Truy vấn thất bại: {db_err}")
        print(traceback.format_exc())
        account_info = None # Đảm bảo trả về None khi lỗi
    except Exception as e: # Bắt lỗi chung khác
        print(f"LỖI (database.py - get_account_details): Lỗi không xác định: {e}")
        print(traceback.format_exc())
        account_info = None
    finally:
        # Luôn đóng cursor và connection trong finally để tránh rò rỉ
        if cur:
            cur.close()
        if conn:
            conn.close()
            print("DEBUG (database.py - get_account_details): Đã đóng kết nối CSDL.")

    return account_info

def get_account_goal(account_id: str) -> str | None:
    """
    Lấy default_strategy_id được gán cho một tài khoản từ CSDL.

    Args:
        account_id: ID của tài khoản cần kiểm tra.

    Returns:
        Chuỗi default_strategy_id, hoặc None nếu không tìm thấy/lỗi.
    """
    if not account_id:
        return None

    default_strategy = None
    conn = get_db_connection() # Dùng hàm kết nối đã có
    if not conn:
        return None

    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        print(f"DEBUG (database.py): Truy vấn default_strategy_id cho account_id: {account_id}")
        # Lấy giá trị từ cột default_strategy_id trong bảng accounts
        cur.execute("""
            SELECT default_strategy_id
            FROM accounts
            WHERE account_id = %s;
            """, (account_id,))
        row = cur.fetchone()
        if row and row['default_strategy_id']:
            default_strategy = row['default_strategy_id']
            print(f"DEBUG (database.py): Default strategy tìm thấy: {default_strategy}")
        else:
            print(f"WARNING (database.py): Không tìm thấy default_strategy_id cho account_id {account_id} trong bảng accounts")

    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - get_account_goal): Truy vấn thất bại: {db_err}")
        print(traceback.format_exc())
    except Exception as e:
        print(f"LỖI (database.py - get_account_goal): Lỗi không xác định: {e}")
        print(traceback.format_exc())
    finally:
        if cur: cur.close()
        if conn: conn.close()
        # print("DEBUG (database.py - get_account_goal): Đã đóng kết nối CSDL.")

    return default_strategy

def get_account_details(account_id: str) -> dict | None:
    """Lấy thông tin chi tiết của tài khoản từ CSDL."""
    account_info = None
    conn = get_db_connection() # Dùng hàm kết nối đã sửa ở trên
    if not conn:
        return None # Trả về None nếu không kết nối được DB

    cur = None # Khởi tạo cur là None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        print(f"DEBUG (database.py): Đang truy vấn thông tin tài khoản: {account_id}")
        cur.execute("""
            SELECT account_id, platform, username, status, notes, goal, default_strategy_id
            FROM accounts
            WHERE account_id = %s
            """, (account_id,))
        row = cur.fetchone()
        if row:
            account_info = dict(row)
            print(f"DEBUG (database.py): Tìm thấy thông tin cho {account_id}")
        else:
            print(f"WARNING (database.py): Không tìm thấy tài khoản {account_id} trong CSDL")

    except psycopg2.Error as db_err: # Bắt lỗi truy vấn CSDL
        print(f"LỖI (database.py - get_account_details): Truy vấn thất bại: {db_err}")
        print(traceback.format_exc())
        account_info = None # Đảm bảo trả về None khi lỗi
    except Exception as e: # Bắt lỗi chung khác
        print(f"LỖI (database.py - get_account_details): Lỗi không xác định: {e}")
        print(traceback.format_exc())
        account_info = None
    finally:
        # Luôn đóng cursor và connection trong finally để tránh rò rỉ
        if cur:
            cur.close()
        if conn:
            conn.close()
            print("DEBUG (database.py - get_account_details): Đã đóng kết nối CSDL.")

    return account_info
    
# --- Rule & Template Functions ---

def get_formatted_history(thread_id: str | None, limit: int = 5) -> str:
    """
    Truy vấn CSDL lấy N tin nhắn/bình luận cuối cùng của một thread_id
    và định dạng thành chuỗi lịch sử hội thoại.

    Args:
        thread_id: ID của luồng hội thoại. Nếu None hoặc rỗng, trả về chuỗi rỗng.
        limit: Số lượng bản ghi lịch sử gần nhất cần lấy.

    Returns:
        Một chuỗi string chứa lịch sử đã định dạng, hoặc chuỗi rỗng nếu không có lịch sử/lỗi.
    """
    if not thread_id:
        return "" # Trả về rỗng nếu không có thread_id

    history_lines = []
    conn = get_db_connection() # Dùng hàm kết nối đã có
    if not conn:
        return "" # Trả về rỗng nếu không kết nối được DB

    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        # Lấy các bản ghi gần nhất, sắp xếp từ cũ đến mới để dễ format
        cur.execute("""
            SELECT received_text, sent_text
            FROM interaction_history
            WHERE thread_id = %s
            ORDER BY timestamp DESC
            LIMIT %s;
            """, (thread_id, limit)) # Truyền thread_id và limit

        rows = cur.fetchall()
        cur.close()

        # Format lại theo thứ tự thời gian (đảo ngược list)
        for row in reversed(rows):
            if row['received_text']:
                 history_lines.append(f"Người dùng: {row['received_text']}")
            # Chỉ thêm sent_text nếu nó không rỗng (tránh thêm dòng "Bạn: " khi chưa trả lời)
            if row['sent_text']:
                 history_lines.append(f"Bạn: {row['sent_text']}")

        print(f"DEBUG (database.py - get_formatted_history): Lấy được {len(rows)} bản ghi cho thread_id '{thread_id}'")

    except psycopg2.Error as e:
        print(f"LỖI (database.py - get_formatted_history): Truy vấn lịch sử thất bại: {e}")
    except Exception as e:
        print(f"LỖI (database.py - get_formatted_history): Lỗi không xác định: {e}")
    finally:
        if conn:
            conn.close()

    # Nối các dòng lại bằng ký tự xuống dòng
    return "\n".join(history_lines)

def get_template_variations(template_ref: str | None) -> list[dict] | None:
    """
    Lấy tất cả các biến thể text cho một template_ref từ CSDL.

    Args:
        template_ref: Mã tham chiếu của template cần lấy biến thể.

    Returns:
        List các dictionary (ví dụ: [{'variation_text': 'text1'}, ...]),
        hoặc list rỗng [] nếu không có biến thể,
        hoặc None nếu có lỗi CSDL.
    """
    if not template_ref:
        return [] # Trả về list rỗng nếu không có ref

    variations_list = None # Khởi tạo là None để phân biệt lỗi và không có dữ liệu
    conn = get_db_connection()
    if not conn:
        return None # Lỗi kết nối -> trả về None

    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        print(f"DEBUG (database.py): Truy vấn các biến thể cho template_ref: {template_ref}")
        cur.execute("""
            SELECT variation_text
            FROM template_variations
            WHERE template_ref = %s;
            """, (template_ref,))
        rows = cur.fetchall() # Lấy tất cả các dòng khớp

        if rows:
            variations_list = [dict(row) for row in rows] # Trả về list các dict
            print(f"DEBUG (database.py): Tìm thấy {len(variations_list)} biến thể cho {template_ref}")
        else:
            print(f"WARNING (database.py): Không tìm thấy biến thể nào cho template_ref {template_ref}")
            variations_list = [] # Trả về list rỗng nếu ref đúng nhưng chưa có biến thể

    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - get_template_variations): Truy vấn thất bại: {db_err}")
        print(traceback.format_exc())
        # variations_list vẫn là None
    except Exception as e:
        print(f"LỖI (database.py - get_template_variations): Lỗi không xác định: {e}")
        print(traceback.format_exc())
        # variations_list vẫn là None
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return variations_list # Trả về list (có thể rỗng) hoặc None nếu lỗi
    
def get_last_stage(thread_id: str | None) -> str | None:
    """
    Lấy stage_id gần nhất của một luồng hội thoại từ lịch sử.

    Args:
        thread_id: ID của luồng hội thoại.

    Returns:
        Chuỗi stage_id gần nhất, hoặc None nếu không có lịch sử hoặc lỗi.
    """
    if not thread_id:
        return None # Không có thread_id thì không có stage cuối

    last_stage = None
    conn = get_db_connection()
    if not conn:
        return None

    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        print(f"DEBUG (database.py): Truy vấn stage cuối cùng cho thread_id: {thread_id}")
        # Lấy stage_id từ bản ghi interaction_history gần nhất của thread này
        # Giả sử bạn lưu stage *trước khi* tương tác vào cột stage_id
        # Hoặc nếu bạn lưu stage *tiếp theo* vào cột next_stage_id thì SELECT cột đó
        cur.execute("""
            SELECT stage_id
            FROM interaction_history
            WHERE thread_id = %s
            ORDER BY timestamp DESC
            LIMIT 1;
            """, (thread_id,))
        row = cur.fetchone()
        if row:
            last_stage = row['stage_id']
            print(f"DEBUG (database.py): Stage cuối cùng tìm thấy: {last_stage}")
        else:
            print(f"DEBUG (database.py): Không tìm thấy lịch sử cho thread_id {thread_id}")

    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - get_last_stage): Truy vấn thất bại: {db_err}")
        print(traceback.format_exc())
    except Exception as e:
        print(f"LỖI (database.py - get_last_stage): Lỗi không xác định: {e}")
        print(traceback.format_exc())
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
            # print("DEBUG (database.py - get_last_stage): Đã đóng kết nối CSDL.") # Có thể bỏ log này

    return last_stage    
    
def get_initial_stage(strategy_id: str) -> str | None:
    """
    Lấy initial_stage_id (giai đoạn bắt đầu) của một chiến lược từ CSDL.

    Args:
        strategy_id: ID của chiến lược cần lấy giai đoạn bắt đầu.

    Returns:
        Chuỗi initial_stage_id, hoặc None nếu không tìm thấy hoặc lỗi.
    """
    if not strategy_id:
        return None

    initial_stage = None
    conn = get_db_connection() # Dùng hàm kết nối đã có
    if not conn:
        return None

    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        print(f"DEBUG (database.py): Truy vấn initial_stage cho strategy_id: {strategy_id}")
        cur.execute("""
            SELECT initial_stage_id
            FROM strategies
            WHERE strategy_id = %s;
            """, (strategy_id,))
        row = cur.fetchone()
        if row and row['initial_stage_id']:
            initial_stage = row['initial_stage_id']
            print(f"DEBUG (database.py): Initial stage tìm thấy: {initial_stage}")
        else:
            print(f"WARNING (database.py): Không tìm thấy initial_stage cho strategy_id {strategy_id} trong bảng strategies")

    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - get_initial_stage): Truy vấn thất bại: {db_err}")
        print(traceback.format_exc())
    except Exception as e:
        print(f"LỖI (database.py - get_initial_stage): Lỗi không xác định: {e}")
        print(traceback.format_exc())
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
            # print("DEBUG (database.py - get_initial_stage): Đã đóng kết nối CSDL.")

    return initial_stage    

def log_interaction_received(account_id: str | None, app_name: str | None, thread_id: str | None, received_text: str, strategy_id: str | None, current_stage_id: str | None, user_intent: str | None) -> int | None:
    """
    Ghi log ban đầu khi nhận được tương tác, bao gồm context chiến lược.
    Đã cập nhật để nhận đủ 7 tham số.
    Trả về history_id nếu thành công, None nếu lỗi.
    """
    history_id = None
    conn = get_db_connection()
    if not conn:
        return None

    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        print(f"DEBUG (database.py): Ghi log nhận: acc='{account_id}', app='{app_name}', thread='{thread_id}', strategy='{strategy_id}', stage='{current_stage_id}', intent='{user_intent}'")

        # !!! Cập nhật câu lệnh INSERT để bao gồm các cột mới và tham số mới !!!
        sql = """
            INSERT INTO interaction_history
            (account_id, app, thread_id, received_text, strategy_id, stage_id, detected_user_intent, status, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING history_id;
        """
        # Đảm bảo thứ tự và số lượng giá trị trong tuple khớp với số lượng %s và định nghĩa hàm
        params = (account_id, app_name, thread_id, received_text, strategy_id, current_stage_id, user_intent, 'received', datetime.now()) # Thêm các giá trị mới và timestamp
        cur.execute(sql, params)
        result = cur.fetchone()
        if result:
            history_id = result['history_id']
        conn.commit() # Commit sau khi execute thành công
        print(f"DEBUG (database.py): Ghi log nhận thành công, history_id = {history_id}")

    except psycopg2.Error as db_err: # Bắt lỗi CSDL cụ thể
        print(f"LỖI (database.py - log_interaction_received): INSERT thất bại: {db_err}")
        print(traceback.format_exc())
        if conn: conn.rollback() # Rollback nếu có lỗi CSDL
        history_id = None
    except Exception as e: # Bắt các lỗi khác
        print(f"LỖI (database.py - log_interaction_received): Lỗi không xác định: {e}")
        print(traceback.format_exc())
        if conn: conn.rollback() # Cũng nên rollback
        history_id = None
    finally:
        # Luôn đóng cursor và connection
        if cur:
            cur.close()
        if conn:
            conn.close()
            # print("DEBUG (database.py - log_interaction_received): Đã đóng kết nối.")

    return history_id

# --- History Functions ---


def update_interaction_log(history_id: int | None, sent_text: str | None, status: str, next_stage_id: str | None):
    """Cập nhật bản ghi lịch sử với text đã gửi và status cuối cùng."""
    if not history_id:
        print("WARNING (database.py - update_log): Không có history_id để cập nhật.")
        return False # Hoặc True tùy bạn muốn xử lý thế nào

    conn = get_db_connection()
    if not conn:
        return False

    cur = None
    success = False
    try:
        cur = conn.cursor()
        print(f"DEBUG (database.py): Cập nhật log history_id={history_id}, status={status}, next_stage={next_stage_id}")
        # Cập nhật các cột cần thiết
        # Lưu ý: Cột stage_id lưu stage *trước khi* xử lý, next_stage_id có thể lưu vào cột riêng hoặc dùng để tính toán ở lần sau
        sql = """
            UPDATE interaction_history
            SET sent_text = %s,
                status = %s,
                stage_id = %s -- Lưu lại stage trước đó (hoặc bạn có thể tạo cột next_stage để lưu next_stage_id_for_log)
            WHERE history_id = %s;
        """
        params = (sent_text, status, next_stage_id, history_id) # Giả sử next_stage_id_for_log được lưu vào stage_id cho lần sau
        cur.execute(sql, params)
        conn.commit()
        success = True
        print(f"DEBUG (database.py): Cập nhật log thành công cho history_id {history_id}")

    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - update_interaction_log): UPDATE thất bại: {db_err}")
        print(traceback.format_exc())
        if conn: conn.rollback()
    except Exception as e:
        print(f"LỖI (database.py - update_interaction_log): Lỗi không xác định: {e}")
        print(traceback.format_exc())
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return success

# --- Strategy Functions ---

def find_transition(current_stage_id: str | None, user_intent: str | None) -> dict | None:
    """Tìm luật chuyển tiếp phù hợp nhất dựa trên stage hiện tại và intent."""
    if not current_stage_id or not user_intent:
        return None

    transition_rule = None
    conn = get_db_connection()
    if not conn:
        return None

    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        print(f"DEBUG (database.py): Tìm transition cho stage='{current_stage_id}', intent='{user_intent}'")
        # Tìm luật khớp chính xác intent hoặc khớp 'any', ưu tiên luật không phải 'any' và có priority cao nhất
        cur.execute("""
            SELECT next_stage_id, action_to_suggest, response_template_ref
            FROM stage_transitions
            WHERE current_stage_id = %s AND (user_intent = %s OR user_intent = 'any')
            ORDER BY CASE user_intent WHEN 'any' THEN 0 ELSE 1 END DESC, -- Ưu tiên không phải 'any'
                     priority DESC -- Ưu tiên priority cao hơn
            LIMIT 1;
            """, (current_stage_id, user_intent))
        row = cur.fetchone()
        if row:
            transition_rule = dict(row)
            print(f"DEBUG (database.py): Transition tìm thấy: {transition_rule}")
        else:
            print(f"DEBUG (database.py): Không tìm thấy transition phù hợp.")

    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - find_transition): Truy vấn thất bại: {db_err}")
        print(traceback.format_exc())
    except Exception as e:
        print(f"LỖI (database.py - find_transition): Lỗi không xác định: {e}")
        print(traceback.format_exc())
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return transition_rule


#---------------------------web-------------------------------------------------------
def get_pending_suggestions() -> list[dict] | None:
    """Lấy tất cả các đề xuất luật/template đang chờ xử lý (status='pending')."""
    suggestions = None
    conn = get_db_connection()
    if not conn:
        return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        print(f"DEBUG (database.py): Truy vấn các đề xuất đang chờ...")
        cur.execute("""
            SELECT suggestion_id, suggested_keywords, suggested_template_text, source_examples, created_at
            FROM suggested_rules
            WHERE status = 'pending'
            ORDER BY created_at DESC;
            """)
        rows = cur.fetchall()
        if rows:
            suggestions = [dict(row) for row in rows] # Chuyển thành list các dict
            print(f"DEBUG (database.py): Tìm thấy {len(suggestions)} đề xuất đang chờ.")
        else:
            print(f"DEBUG (database.py): Không có đề xuất nào đang chờ.")
            suggestions = [] # Trả về list rỗng nếu không có

    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - get_pending_suggestions): Truy vấn thất bại: {db_err}")
        print(traceback.format_exc())
        suggestions = None # Trả về None khi lỗi DB
    except Exception as e:
        print(f"LỖI (database.py - get_pending_suggestions): Lỗi không xác định: {e}")
        print(traceback.format_exc())
        suggestions = None
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return suggestions

def get_suggestion_by_id(suggestion_id: int) -> dict | None:
    """Lấy chi tiết một đề xuất cụ thể bằng ID."""
    if not suggestion_id:
        return None
    suggestion = None
    conn = get_db_connection()
    if not conn:
        return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        print(f"DEBUG (database.py): Truy vấn đề xuất ID: {suggestion_id}")
        cur.execute("""
            SELECT suggestion_id, suggested_keywords, suggested_template_text, source_examples, status
            FROM suggested_rules
            WHERE suggestion_id = %s;
            """, (suggestion_id,))
        row = cur.fetchone()
        if row:
            suggestion = dict(row)
        else:
            print(f"WARNING (database.py): Không tìm thấy đề xuất ID: {suggestion_id}")

    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - get_suggestion_by_id): Truy vấn thất bại: {db_err}")
        print(traceback.format_exc())
    except Exception as e:
        print(f"LỖI (database.py - get_suggestion_by_id): Lỗi không xác định: {e}")
        print(traceback.format_exc())
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return suggestion

def update_suggestion_status(suggestion_id: int, new_status: str) -> bool:
    """Cập nhật trạng thái (status) cho một đề xuất."""
    if not suggestion_id or not new_status:
        return False
    conn = get_db_connection()
    if not conn:
        return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        print(f"DEBUG (database.py): Cập nhật status='{new_status}' cho suggestion_id={suggestion_id}")
        cur.execute("""
            UPDATE suggested_rules
            SET status = %s
            WHERE suggestion_id = %s;
            """, (new_status, suggestion_id))
        conn.commit()
        success = cur.rowcount > 0 # Kiểm tra xem có dòng nào được cập nhật không
        if success:
             print(f"DEBUG (database.py): Cập nhật status đề xuất thành công.")
        else:
             print(f"WARNING (database.py): Không tìm thấy suggestion_id {suggestion_id} để cập nhật status.")

    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - update_suggestion_status): UPDATE thất bại: {db_err}")
        print(traceback.format_exc())
        if conn: conn.rollback()
    except Exception as e:
        print(f"LỖI (database.py - update_suggestion_status): Lỗi không xác định: {e}")
        print(traceback.format_exc())
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success

def add_new_template(template_ref: str, first_variation_text: str, description: str | None = None, category: str | None = None) -> str | None:
    """
    Thêm template_ref vào response_templates (nếu chưa có)
    VÀ thêm biến thể đầu tiên vào template_variations.
    Trả về template_ref nếu thành công, None nếu lỗi.
    """
    if not template_ref or not first_variation_text:
        return None

    conn = get_db_connection()
    if not conn:
        return None
    cur = None
    success_ref = False
    success_var = False
    try:
        cur = conn.cursor()
        # Bước 1: Thêm vào response_templates, bỏ qua nếu đã tồn tại
        print(f"DEBUG (database.py): Thêm/Đảm bảo template_ref '{template_ref}' tồn tại...")
        sql_ref = """
            INSERT INTO response_templates (template_ref, description, category)
            VALUES (%s, %s, %s)
            ON CONFLICT (template_ref) DO NOTHING;
        """
        cur.execute(sql_ref, (template_ref, description, category))
        # Không cần commit ngay, làm trong 1 transaction

        # Bước 2: Thêm biến thể vào template_variations
        print(f"DEBUG (database.py): Thêm variation cho '{template_ref}'...")
        sql_var = """
            INSERT INTO template_variations (template_ref, variation_text)
            VALUES (%s, %s);
        """
        # Cân nhắc thêm ON CONFLICT cho variations nếu cần (ví dụ UNIQUE(template_ref, variation_text))
        cur.execute(sql_var, (template_ref, first_variation_text))

        conn.commit() # Commit cả hai lệnh insert
        print(f"DEBUG (database.py): Thêm template và variation thành công cho '{template_ref}'.")
        return template_ref # Trả về ref nếu thành công

    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - add_new_template): INSERT thất bại: {db_err}")
        print(traceback.format_exc())
        if conn: conn.rollback()
    except Exception as e:
        print(f"LỖI (database.py - add_new_template): Lỗi không xác định: {e}")
        print(traceback.format_exc())
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return None # Trả về None nếu có lỗi

def get_all_rules() -> list[dict] | None:
    """Lấy tất cả các luật từ bảng simple_rules."""
    rules_list = None
    conn = get_db_connection()
    if not conn:
        return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        print(f"DEBUG (database.py): Truy vấn tất cả rules...")
        cur.execute("""
            SELECT rule_id, trigger_keywords, category, response_template_ref, priority, notes
            FROM simple_rules
            ORDER BY rule_id;
            """)
        rows = cur.fetchall()
        if rows:
            rules_list = [dict(row) for row in rows]
            print(f"DEBUG (database.py): Tìm thấy {len(rules_list)} luật.")
        else:
            print(f"DEBUG (database.py): Không có luật nào trong CSDL.")
            rules_list = [] # Trả về list rỗng nếu không có luật

    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - get_all_rules): Truy vấn thất bại: {db_err}")
        print(traceback.format_exc())
    except Exception as e:
        print(f"LỖI (database.py - get_all_rules): Lỗi không xác định: {e}")
        print(traceback.format_exc())
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return rules_list # Trả về list (có thể rỗng) hoặc None nếu lỗi DB


def add_new_rule(keywords: str, category: str | None, template_ref: str, priority: int = 0, notes: str | None = None) -> bool:
    """Thêm một luật mới vào bảng simple_rules."""
    if not keywords or not template_ref:
        return False

    conn = get_db_connection()
    if not conn:
        return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        print(f"DEBUG (database.py): Thêm rule mới: keywords='{keywords[:50]}...', category='{category}', ref='{template_ref}'")
        sql = """
            INSERT INTO simple_rules
            (trigger_keywords, category, response_template_ref, priority, notes)
            VALUES (%s, %s, %s, %s, %s);
        """
        params = (keywords, category, template_ref, priority, notes)
        cur.execute(sql, params)
        conn.commit()
        success = True
        print(f"DEBUG (database.py): Thêm rule mới thành công.")

    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - add_new_rule): INSERT thất bại: {db_err}")
        print(traceback.format_exc())
        if conn: conn.rollback()
    except Exception as e:
        print(f"LỖI (database.py - add_new_rule): Lỗi không xác định: {e}")
        print(traceback.format_exc())
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return success
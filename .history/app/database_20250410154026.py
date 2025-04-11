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



def add_new_account(account_id: str, platform: str, username: str, status: str = 'active', notes: str | None = None, goal: str | None = None, default_strategy_id: str | None = None) -> bool:
    """Thêm một tài khoản mới vào bảng accounts.
       Đã thêm account_id vào INSERT và tham số hàm.
    """
    # <<< Thêm kiểm tra account_id >>>
    if not account_id or not platform or not username:
        print("WARNING (database.py - add_new_account): Account ID, Platform và Username là bắt buộc.")
        return False

    conn = get_db_connection()
    if not conn:
        return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        print(f"DEBUG (database.py): Thêm account mới: account_id='{account_id}', platform='{platform}', username='{username}'")

        # <<< Thêm account_id vào danh sách cột và VALUES >>>
        sql = """
            INSERT INTO accounts
            (account_id, platform, username, status, notes, goal, default_strategy_id, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """
        # <<< Thêm account_id vào tuple params >>>
        params = (account_id, platform, username, status, notes, goal, default_strategy_id, None) # Giữ updated_at là None khi tạo mới
        cur.execute(sql, params)
        conn.commit()
        success = True
        print(f"DEBUG (database.py): Thêm account mới thành công.")

    except psycopg2.IntegrityError as int_err: # Bắt lỗi nếu account_id đã tồn tại (PRIMARY KEY)
         print(f"LỖI (database.py - add_new_account): Lỗi ràng buộc CSDL (Account ID đã tồn tại?): {int_err}")
         if conn: conn.rollback()
    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - add_new_account): INSERT thất bại: {db_err}")
        if conn: conn.rollback()
    except Exception as e:
        print(f"LỖI (database.py - add_new_account): Lỗi không xác định: {e}")
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return success

def update_account(account_id: str, platform: str, username: str, status: str, notes: str | None, goal: str | None, default_strategy_id: str | None) -> bool:
    """Cập nhật thông tin một tài khoản.
       Đã thêm updated_at vào UPDATE.
    """
    if not account_id or not platform or not username:
        return False

    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        sql = """
            UPDATE accounts
            SET platform = %s, username = %s, status = %s, notes = %s, goal = %s, default_strategy_id = %s, updated_at = %s
            WHERE account_id = %s;
        """
        # Truyền datetime.now() cho updated_at
        params = (platform, username, status, notes, goal, default_strategy_id, datetime.now(), account_id)
        cur.execute(sql, params)
        conn.commit()
        success = cur.rowcount > 0
        if not success:
             print(f"WARNING (database.py - update_account): Không tìm thấy account_id {account_id} để cập nhật.")

    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - update_account): UPDATE thất bại: {db_err}")
        if conn: conn.rollback()
    except Exception as e:
        print(f"LỖI (database.py - update_account): Lỗi không xác định: {e}")
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success


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
            SELECT variation_id, variation_text
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

def delete_template_ref(template_ref: str) -> bool:
    """Xóa một template_ref khỏi response_templates.
       Do có ràng buộc ON DELETE CASCADE trong DB, các variations liên quan
       trong template_variations cũng sẽ tự động bị xóa.
       Hàm sẽ thất bại (ném ForeignKeyViolation) nếu template_ref đang được
       tham chiếu bởi simple_rules hoặc stage_transitions (do không có ON DELETE).
    """
    if not template_ref: return False
    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        print(f"DEBUG (database.py): Xóa template_ref='{template_ref}'...")
        # Chỉ cần xóa từ response_templates, variations sẽ tự xóa theo CASCADE
        sql = "DELETE FROM response_templates WHERE template_ref = %s;"
        cur.execute(sql, (template_ref,))
        conn.commit()
        # Kiểm tra xem có dòng nào thực sự bị xóa không
        success = cur.rowcount > 0
        if not success:
            print(f"WARNING (database.py - delete_template_ref): Không tìm thấy template_ref '{template_ref}' để xóa.")

    except psycopg2.Error as db_err:
         # Không bắt lỗi ForeignKeyViolation ở đây, để route xử lý
         print(f"LỖI (database.py - delete_template_ref): DELETE thất bại: {db_err}")
         if conn: conn.rollback()
         # Ném lại lỗi để route có thể bắt cụ thể lỗi FK
         raise db_err
    except Exception as e:
        print(f"LỖI (database.py - delete_template_ref): Lỗi không xác định: {e}")
        if conn: conn.rollback()
        raise e # Ném lại lỗi để route bắt
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success # Chỉ trả về True nếu không có Exception và rowcount > 0

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

def get_all_strategies() -> list[dict] | None:
    """Lấy danh sách tất cả các chiến lược.
       Đã thêm cột 'name'.
    """
    strategies_list = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        print("DEBUG (database.py): Truy vấn tất cả strategies...")
        # Thêm cột 'name' vào SELECT
        cur.execute("""
            SELECT strategy_id, name, description, initial_stage_id
            FROM strategies
            ORDER BY strategy_id;
            """)
        rows = cur.fetchall()
        if rows:
            strategies_list = [dict(row) for row in rows]
        else:
            strategies_list = []
    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - get_all_strategies): Truy vấn thất bại: {db_err}")
    except Exception as e:
        print(f"LỖI (database.py - get_all_strategies): Lỗi không xác định: {e}")
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return strategies_list

def add_new_strategy(strategy_id: str, name: str, description: str | None, initial_stage_id: str) -> bool:
    """Thêm một chiến lược mới.
       Đã thêm cột 'name' vào INSERT và tham số hàm.
    """
    if not strategy_id or not name or not initial_stage_id: # Thêm kiểm tra name
        print("WARNING (add_new_strategy): strategy_id, name, initial_stage_id là bắt buộc.")
        return False

    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        print(f"DEBUG (database.py): Thêm strategy mới: id='{strategy_id}', name='{name}'")
        # Thêm cột 'name' vào INSERT
        sql = """
            INSERT INTO strategies (strategy_id, name, description, initial_stage_id)
            VALUES (%s, %s, %s, %s);
        """
        params = (strategy_id, name, description, initial_stage_id)
        cur.execute(sql, params)
        conn.commit()
        success = True
    except psycopg2.IntegrityError as int_err:
         print(f"LỖI (database.py - add_new_strategy): Lỗi ràng buộc CSDL (ID hoặc Name đã tồn tại?): {int_err}")
         if conn: conn.rollback()
    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - add_new_strategy): INSERT thất bại: {db_err}")
        if conn: conn.rollback()
    except Exception as e:
        print(f"LỖI (database.py - add_new_strategy): Lỗi không xác định: {e}")
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success

def get_strategy_details(strategy_id: str) -> dict | None:
    """Lấy chi tiết một chiến lược.
       Đã thêm cột 'name'.
    """
    if not strategy_id: return None
    details = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        # Thêm cột 'name'
        cur.execute("""
            SELECT strategy_id, name, description, initial_stage_id
            FROM strategies WHERE strategy_id = %s;
            """, (strategy_id,))
        row = cur.fetchone()
        if row: details = dict(row)
    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - get_strategy_details): Truy vấn thất bại: {db_err}")
    except Exception as e:
        print(f"LỖI (database.py - get_strategy_details): Lỗi không xác định: {e}")
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return details

def update_strategy(strategy_id: str, name: str, description: str | None, initial_stage_id: str) -> bool:
    """Cập nhật một chiến lược.
       Đã thêm cột 'name' vào UPDATE và tham số hàm.
    """
    if not strategy_id or not name or not initial_stage_id: # Thêm kiểm tra name
         print("WARNING (update_strategy): strategy_id, name, initial_stage_id là bắt buộc.")
         return False
    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        # Thêm cột 'name' vào SET
        sql = """
            UPDATE strategies SET name = %s, description = %s, initial_stage_id = %s
            WHERE strategy_id = %s;
        """
        params = (name, description, initial_stage_id, strategy_id)
        cur.execute(sql, params)
        conn.commit()
        success = cur.rowcount > 0
        if not success:
             print(f"WARNING (database.py - update_strategy): Không tìm thấy strategy_id {strategy_id} để cập nhật.")
    except psycopg2.IntegrityError as int_err: # Bắt lỗi nếu name vi phạm UNIQUE
         print(f"LỖI (database.py - update_strategy): Lỗi ràng buộc CSDL (Name đã tồn tại?): {int_err}")
         if conn: conn.rollback()
    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - update_strategy): UPDATE thất bại: {db_err}")
        if conn: conn.rollback()
    except Exception as e:
        print(f"LỖI (database.py - update_strategy): Lỗi không xác định: {e}")
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success

def get_all_stages() -> list[dict] | None:
    """Lấy danh sách tất cả các stage ID và description từ bảng strategy_stages."""
    stages_list = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        print("DEBUG (database.py): Truy vấn tất cả stages từ strategy_stages...")
        # Truy vấn trực tiếp bảng strategy_stages
        cur.execute("""
            SELECT stage_id, description, strategy_id, stage_order
            FROM strategy_stages
            ORDER BY strategy_id, stage_order, stage_id;
            """)
        rows = cur.fetchall()
        if rows:
            stages_list = [dict(row) for row in rows]
        else:
            stages_list = []
    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - get_all_stages): Truy vấn thất bại: {db_err}")
    except Exception as e:
        print(f"LỖI (database.py - get_all_stages): Lỗi không xác định: {e}")
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return stages_list


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

def get_all_accounts() -> list[dict] | None:
    """Lấy danh sách tất cả các tài khoản từ CSDL."""
    accounts_list = None
    conn = get_db_connection()
    if not conn:
        print("LỖI (database.py - get_all_accounts): Không thể kết nối CSDL.")
        return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        print(f"DEBUG (database.py): Truy vấn tất cả accounts...")
        # !!! Thay đổi tên cột cho đúng với bảng 'accounts' của bạn !!!
        cur.execute("""
            SELECT account_id, platform, username, status, notes, goal, default_strategy_id
            FROM accounts
            ORDER BY account_id;
            """)
        rows = cur.fetchall()
        if rows:
            accounts_list = [dict(row) for row in rows]
            print(f"DEBUG (database.py): Tìm thấy {len(accounts_list)} tài khoản.")
        else:
            print(f"DEBUG (database.py): Không có tài khoản nào trong CSDL.")
            accounts_list = [] # Trả về list rỗng nếu không có

    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - get_all_accounts): Truy vấn thất bại: {db_err}")
        print(traceback.format_exc())
        # accounts_list vẫn là None
    except Exception as e:
        print(f"LỖI (database.py - get_all_accounts): Lỗi không xác định: {e}")
        print(traceback.format_exc())
        # accounts_list vẫn là None
    finally:
        if cur: cur.close()
        if conn: conn.close()
        # print("DEBUG (database.py - get_all_accounts): Đã đóng kết nối.")

    return accounts_list # Trả về list (có thể rỗng) hoặc None nếu lỗi DB

def get_all_accounts() -> list[dict] | None:
    """Lấy danh sách tất cả các tài khoản từ CSDL."""
    accounts_list = None
    conn = get_db_connection()
    if not conn:
        print("LỖI (database.py - get_all_accounts): Không thể kết nối CSDL.")
        return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        print(f"DEBUG (database.py): Truy vấn tất cả accounts...")
        # !!! Đảm bảo tên cột khớp với bảng 'accounts' của bạn !!!
        cur.execute("""
            SELECT account_id, platform, username, status, notes, goal, default_strategy_id
            FROM accounts
            ORDER BY account_id;
            """)
        rows = cur.fetchall()
        if rows:
            accounts_list = [dict(row) for row in rows]
            print(f"DEBUG (database.py): Tìm thấy {len(accounts_list)} tài khoản.")
        else:
            print(f"DEBUG (database.py): Không có tài khoản nào trong CSDL.")
            accounts_list = [] # Trả về list rỗng nếu không có

    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - get_all_accounts): Truy vấn thất bại: {db_err}")
        print(traceback.format_exc())
        # accounts_list vẫn là None
    except Exception as e:
        print(f"LỖI (database.py - get_all_accounts): Lỗi không xác định: {e}")
        print(traceback.format_exc())
        # accounts_list vẫn là None
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return accounts_list



def update_account(account_id: str, platform: str, username: str, status: str, notes: str | None, goal: str | None, default_strategy_id: str | None) -> bool:
    """Cập nhật thông tin một tài khoản."""
    # Thêm validation nếu cần
    if not account_id or not platform or not username:
        return False

    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        sql = """
            UPDATE accounts
            SET platform = %s, username = %s, status = %s, notes = %s, goal = %s, default_strategy_id = %s, updated_at = %s
            WHERE account_id = %s;
        """
        params = (platform, username, status, notes, goal, default_strategy_id, datetime.now(), account_id)
        cur.execute(sql, params)
        conn.commit()
        success = cur.rowcount > 0 # Kiểm tra xem có dòng nào được cập nhật không
        if not success:
             print(f"WARNING (database.py - update_account): Không tìm thấy account_id {account_id} để cập nhật.")

    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - update_account): UPDATE thất bại: {db_err}")
        if conn: conn.rollback()
    except Exception as e:
        print(f"LỖI (database.py - update_account): Lỗi không xác định: {e}")
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success

def delete_account(account_id: str) -> bool:
    """Xóa một tài khoản."""
    if not account_id: return False
    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        sql = "DELETE FROM accounts WHERE account_id = %s;"
        cur.execute(sql, (account_id,))
        conn.commit()
        success = cur.rowcount > 0
        if not success:
             print(f"WARNING (database.py - delete_account): Không tìm thấy account_id {account_id} để xóa.")
    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - delete_account): DELETE thất bại: {db_err}")
        if conn: conn.rollback()
    except Exception as e:
        print(f"LỖI (database.py - delete_account): Lỗi không xác định: {e}")
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success

# --- Template/Variation Functions ---

def get_all_template_refs() -> list[dict] | None:
    """Lấy danh sách tất cả các template_ref."""
    refs_list = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        print("DEBUG (database.py): Truy vấn tất cả template refs...")
        # !!! Đảm bảo tên bảng và cột khớp !!!
        cur.execute("SELECT template_ref FROM response_templates ORDER BY template_ref;")
        rows = cur.fetchall()
        if rows:
            refs_list = [dict(row) for row in rows]
        else:
            refs_list = []
    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - get_all_template_refs): Truy vấn thất bại: {db_err}")
    except Exception as e:
        print(f"LỖI (database.py - get_all_template_refs): Lỗi không xác định: {e}")
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return refs_list

def get_all_template_refs_with_details() -> list[dict] | None:
    """Lấy danh sách template refs cùng mô tả, category và số lượng variations."""
    templates_data = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        print("DEBUG (database.py): Truy vấn templates với details và variation count...")
        # !!! Đảm bảo tên bảng và cột khớp !!!
        # Sử dụng LEFT JOIN và COUNT để đếm variations
        sql = """
            SELECT
                rt.template_ref,
                rt.description,
                rt.category,
                COUNT(tv.variation_id) AS variation_count
            FROM response_templates rt
            LEFT JOIN template_variations tv ON rt.template_ref = tv.template_ref
            GROUP BY rt.template_ref, rt.description, rt.category
            ORDER BY rt.template_ref;
        """
        cur.execute(sql)
        rows = cur.fetchall()
        if rows:
            templates_data = [dict(row) for row in rows]
        else:
            templates_data = []
    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - get_all_template_refs_with_details): Truy vấn thất bại: {db_err}")
    except Exception as e:
        print(f"LỖI (database.py - get_all_template_refs_with_details): Lỗi không xác định: {e}")
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return templates_data

def get_template_ref_details(template_ref: str) -> dict | None:
    """Lấy thông tin chi tiết (description, category) của một template_ref."""
    if not template_ref: return None
    details = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        print(f"DEBUG (database.py): Truy vấn details cho template_ref '{template_ref}'...")
        # !!! Đảm bảo tên bảng và cột khớp !!!
        cur.execute("""
            SELECT template_ref, description, category
            FROM response_templates
            WHERE template_ref = %s;
            """, (template_ref,))
        row = cur.fetchone()
        if row:
            details = dict(row)
        else:
            print(f"WARNING (database.py): Không tìm thấy template_ref '{template_ref}'.")
    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - get_template_ref_details): Truy vấn thất bại: {db_err}")
    except Exception as e:
        print(f"LỖI (database.py - get_template_ref_details): Lỗi không xác định: {e}")
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return details

def add_single_variation(template_ref: str, variation_text: str) -> bool:
    """Thêm một variation mới cho một template_ref đã tồn tại."""
    if not template_ref or not variation_text:
        return False

    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        print(f"DEBUG (database.py): Thêm variation cho '{template_ref}'...")
        # !!! Đảm bảo tên bảng và cột khớp !!!
        # Cân nhắc thêm ràng buộc UNIQUE(template_ref, variation_text) trong DB
        sql = """
            INSERT INTO template_variations (template_ref, variation_text)
            VALUES (%s, %s);
        """
        params = (template_ref, variation_text)
        cur.execute(sql, params)
        conn.commit()
        success = True
        print(f"DEBUG (database.py): Thêm variation thành công.")

    except psycopg2.IntegrityError as int_err: # Bắt lỗi nếu vi phạm ràng buộc (vd: UNIQUE)
         print(f"LỖI (database.py - add_single_variation): Lỗi ràng buộc CSDL (có thể text đã tồn tại?): {int_err}")
         if conn: conn.rollback()
    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - add_single_variation): INSERT thất bại: {db_err}")
        if conn: conn.rollback()
    except Exception as e:
        print(f"LỖI (database.py - add_single_variation): Lỗi không xác định: {e}")
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return success

# --- Strategy/Stage Functions ---

def get_all_strategies() -> list[dict] | None:
    """Lấy danh sách tất cả các chiến lược."""
    strategies_list = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        print("DEBUG (database.py): Truy vấn tất cả strategies...")
        # !!! Đảm bảo tên bảng và cột khớp !!!
        cur.execute("""
            SELECT strategy_id, name, description, initial_stage_id
            FROM strategies
            ORDER BY strategy_id;
            """)
        rows = cur.fetchall()
        if rows:
            strategies_list = [dict(row) for row in rows]
        else:
            strategies_list = []
    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - get_all_strategies): Truy vấn thất bại: {db_err}")
    except Exception as e:
        print(f"LỖI (database.py - get_all_strategies): Lỗi không xác định: {e}")
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return strategies_list

def add_new_strategy(strategy_id: str, name: str, description: str | None, initial_stage_id: str) -> bool:
    """Thêm một chiến lược mới."""
    if not strategy_id or not name or not initial_stage_id:
        return False

    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        print(f"DEBUG (database.py): Thêm strategy mới: id='{strategy_id}', name='{name}'")
        # !!! Đảm bảo tên bảng và cột khớp !!!
        sql = """
            INSERT INTO strategies (strategy_id, name, description, initial_stage_id)
            VALUES (%s, %s, %s, %s);
        """
        params = (strategy_id, name, description, initial_stage_id)
        cur.execute(sql, params)
        conn.commit()
        success = True
    except psycopg2.IntegrityError as int_err: # Bắt lỗi nếu strategy_id đã tồn tại (nếu là PRIMARY KEY)
         print(f"LỖI (database.py - add_new_strategy): Lỗi ràng buộc CSDL (ID đã tồn tại?): {int_err}")
         if conn: conn.rollback()
    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - add_new_strategy): INSERT thất bại: {db_err}")
        if conn: conn.rollback()
    except Exception as e:
        print(f"LỖI (database.py - add_new_strategy): Lỗi không xác định: {e}")
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success

def get_strategy_details(strategy_id: str) -> dict | None:
    """Lấy chi tiết một chiến lược."""
    if not strategy_id: return None
    details = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        # !!! Đảm bảo tên bảng và cột khớp !!!
        cur.execute("""
            SELECT strategy_id, name, description, initial_stage_id
            FROM strategies WHERE strategy_id = %s;
            """, (strategy_id,))
        row = cur.fetchone()
        if row: details = dict(row)
    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - get_strategy_details): Truy vấn thất bại: {db_err}")
    except Exception as e:
        print(f"LỖI (database.py - get_strategy_details): Lỗi không xác định: {e}")
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return details

def update_strategy(strategy_id: str, name: str, description: str | None, initial_stage_id: str) -> bool:
    """Cập nhật một chiến lược."""
    if not strategy_id or not name or not initial_stage_id: return False
    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        # !!! Đảm bảo tên bảng và cột khớp !!!
        sql = """
            UPDATE strategies SET name = %s, description = %s, initial_stage_id = %s
            WHERE strategy_id = %s;
        """
        params = (name, description, initial_stage_id, strategy_id)
        cur.execute(sql, params)
        conn.commit()
        success = cur.rowcount > 0
    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - update_strategy): UPDATE thất bại: {db_err}")
        if conn: conn.rollback()
    except Exception as e:
        print(f"LỖI (database.py - update_strategy): Lỗi không xác định: {e}")
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success

def get_all_stages() -> list[dict] | None:
    """Lấy danh sách tất cả các stage ID và tên (nếu có)."""
    stages_list = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        print("DEBUG (database.py): Truy vấn tất cả stages...")
        # !!! Giả sử bạn có bảng 'stages' hoặc lấy DISTINCT từ 'stage_transitions' ???
        # Cách 1: Nếu có bảng 'stages' riêng
        # cur.execute("SELECT stage_id, name, description FROM stages ORDER BY stage_id;")
        # Cách 2: Lấy các stage_id duy nhất từ bảng transitions (có thể thiếu stage cuối)
        cur.execute("""
             SELECT DISTINCT current_stage_id AS stage_id FROM stage_transitions
             UNION
             SELECT DISTINCT next_stage_id AS stage_id FROM stage_transitions WHERE next_stage_id IS NOT NULL
             ORDER BY stage_id;
             """)
        rows = cur.fetchall()
        if rows:
            # Nếu không có cột name, bạn có thể chỉ trả về [{'stage_id': 'id1'}, ...]
            stages_list = [dict(row) for row in rows]
        else:
            stages_list = []
    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - get_all_stages): Truy vấn thất bại: {db_err}")
    except Exception as e:
        print(f"LỖI (database.py - get_all_stages): Lỗi không xác định: {e}")
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return stages_list

def get_stages_for_strategy(strategy_id: str) -> list[dict] | None:
     """Lấy các stages liên quan đến một chiến lược (cần định nghĩa rõ hơn logic này)."""
     # Logic này phức tạp: có thể là tất cả các current_stage và next_stage trong transitions
     # thuộc về các stages bắt đầu từ initial_stage của strategy đó.
     # Hoặc đơn giản là lấy tất cả stages được định nghĩa trong 1 bảng riêng liên kết với strategy.
     # Tạm thời trả về None hoặc list rỗng.
     print(f"WARNING (database.py - get_stages_for_strategy): Hàm chưa được triển khai đầy đủ logic.")
     # return get_all_stages() # Tạm thời trả về tất cả stages
     return []

def delete_strategy(strategy_id: str) -> bool:
    """Xóa một chiến lược khỏi bảng strategies.
       Lưu ý: Các bảng khác tham chiếu đến strategy_id này
       sẽ bị ảnh hưởng dựa trên ràng buộc khóa ngoại (ON DELETE CASCADE/SET NULL)."""
    if not strategy_id: return False
    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        print(f"DEBUG (database.py): Xóa strategy ID={strategy_id}")
        # Xóa từ bảng strategies, các bảng khác sẽ tự xử lý qua FK constraints
        sql = "DELETE FROM strategies WHERE strategy_id = %s;"
        cur.execute(sql, (strategy_id,))
        conn.commit()
        success = cur.rowcount > 0 # Kiểm tra xem có dòng nào bị xóa không
        if not success:
             print(f"WARNING (database.py - delete_strategy): Không tìm thấy strategy_id {strategy_id} để xóa.")

    except psycopg2.Error as db_err:
        # Có thể bắt lỗi khóa ngoại cụ thể nếu cần (vd: psycopg2.errors.ForeignKeyViolation)
        print(f"LỖI (database.py - delete_strategy): DELETE thất bại: {db_err}")
        if conn: conn.rollback()
    except Exception as e:
        print(f"LỖI (database.py - delete_strategy): Lỗi không xác định: {e}")
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success

def get_stages_for_strategy(strategy_id: str) -> list[dict] | None:
     """Lấy danh sách các stages thuộc về một strategy_id cụ thể từ bảng strategy_stages."""
     if not strategy_id: return None
     stages_list = None
     conn = get_db_connection()
     if not conn: return None
     cur = None
     try:
         cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
         print(f"DEBUG (database.py): Truy vấn stages cho strategy_id='{strategy_id}'...")
         # Truy vấn bảng strategy_stages
         cur.execute("""
             SELECT stage_id, description, strategy_id, stage_order
             FROM strategy_stages
             WHERE strategy_id = %s
             ORDER BY stage_order, stage_id;
             """, (strategy_id,))
         rows = cur.fetchall()
         if rows:
             stages_list = [dict(row) for row in rows]
         else:
             print(f"DEBUG (database.py): Không tìm thấy stage nào cho strategy_id='{strategy_id}'.")
             stages_list = []
     except psycopg2.Error as db_err:
         print(f"LỖI (database.py - get_stages_for_strategy): Truy vấn thất bại: {db_err}")
     except Exception as e:
         print(f"LỖI (database.py - get_stages_for_strategy): Lỗi không xác định: {e}")
     finally:
         if cur: cur.close()
         if conn: conn.close()
     return stages_list

def get_transitions_for_strategy(strategy_id: str) -> list[dict] | None:
     """Lấy danh sách các transitions có current_stage_id thuộc về một strategy_id."""
     if not strategy_id: return None
     transitions_list = None
     conn = get_db_connection()
     if not conn: return None
     cur = None
     try:
         cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
         print(f"DEBUG (database.py): Truy vấn transitions cho strategy_id='{strategy_id}'...")
         # Lấy transitions mà current_stage_id nằm trong danh sách các stage của strategy đó
         sql = """
             SELECT
                 t.transition_id, t.current_stage_id, t.user_intent, t.condition_logic,
                 t.next_stage_id, t.action_to_suggest, t.response_template_ref, t.priority
             FROM stage_transitions t
             JOIN strategy_stages ss ON t.current_stage_id = ss.stage_id
             WHERE ss.strategy_id = %s
             ORDER BY t.current_stage_id, t.priority DESC, t.user_intent;
         """
         cur.execute(sql, (strategy_id,))
         rows = cur.fetchall()
         if rows:
             transitions_list = [dict(row) for row in rows]
         else:
             print(f"DEBUG (database.py): Không tìm thấy transition nào cho strategy_id='{strategy_id}'.")
             transitions_list = []
     except psycopg2.Error as db_err:
         print(f"LỖI (database.py - get_transitions_for_strategy): Truy vấn thất bại: {db_err}")
     except Exception as e:
         print(f"LỖI (database.py - get_transitions_for_strategy): Lỗi không xác định: {e}")
     finally:
         if cur: cur.close()
         if conn: conn.close()
     return transitions_list

def delete_single_variation(variation_id: int) -> bool:
    """Xóa một variation cụ thể bằng variation_id."""
    if not variation_id: return False
    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        print(f"DEBUG (database.py): Xóa variation ID={variation_id}...")
        sql = "DELETE FROM template_variations WHERE variation_id = %s;"
        cur.execute(sql, (variation_id,))
        conn.commit()
        success = cur.rowcount > 0 # Kiểm tra xem có dòng nào bị xóa không
        if not success:
            print(f"WARNING (database.py - delete_single_variation): Không tìm thấy variation_id {variation_id} để xóa.")

    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - delete_single_variation): DELETE thất bại: {db_err}")
        if conn: conn.rollback()
        # Ném lỗi lên để route xử lý nếu cần
        raise db_err
    except Exception as e:
        print(f"LỖI (database.py - delete_single_variation): Lỗi không xác định: {e}")
        if conn: conn.rollback()
        raise e
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success

# --- Stage Management Functions ---

def add_new_stage(stage_id: str, strategy_id: str, description: str | None, order: int = 0) -> bool:
    """Thêm một stage mới vào bảng strategy_stages."""
    if not stage_id or not strategy_id:
        print("WARNING (database.py - add_new_stage): stage_id và strategy_id là bắt buộc.")
        return False
    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        print(f"DEBUG: Thêm stage mới: stage_id='{stage_id}', strategy_id='{strategy_id}'")
        sql = """
            INSERT INTO strategy_stages (stage_id, strategy_id, description, stage_order)
            VALUES (%s, %s, %s, %s);
        """
        params = (stage_id, strategy_id, description, order)
        cur.execute(sql, params)
        conn.commit()
        success = True
    except psycopg2.IntegrityError as e: # Bắt lỗi nếu stage_id đã tồn tại (PK)
        print(f"LỖI (database.py - add_new_stage): Lỗi ràng buộc CSDL (Stage ID đã tồn tại?): {e}")
        if conn: conn.rollback()
    except psycopg2.Error as e:
        print(f"LỖI (database.py - add_new_stage): INSERT thất bại: {e}")
        if conn: conn.rollback()
    except Exception as e:
        print(f"LỖI (database.py - add_new_stage): Lỗi không xác định: {e}")
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success

def get_stage_details(stage_id: str) -> dict | None:
    """Lấy chi tiết một stage từ strategy_stages."""
    if not stage_id: return None
    details = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("""
            SELECT stage_id, strategy_id, description, stage_order
            FROM strategy_stages WHERE stage_id = %s;
            """, (stage_id,))
        row = cur.fetchone()
        if row: details = dict(row)
    except psycopg2.Error as e:
        print(f"LỖI (database.py - get_stage_details): Truy vấn thất bại: {e}")
    except Exception as e:
        print(f"LỖI (database.py - get_stage_details): Lỗi không xác định: {e}")
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return details

def update_stage(stage_id: str, description: str | None, order: int) -> bool:
    """Cập nhật description và order cho một stage."""
    if not stage_id: return False
    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        sql = """
            UPDATE strategy_stages SET description = %s, stage_order = %s
            WHERE stage_id = %s;
        """
        params = (description, order, stage_id)
        cur.execute(sql, params)
        conn.commit()
        success = cur.rowcount > 0
    except psycopg2.Error as e:
        print(f"LỖI (database.py - update_stage): UPDATE thất bại: {e}")
        if conn: conn.rollback()
    except Exception as e:
        print(f"LỖI (database.py - update_stage): Lỗi không xác định: {e}")
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success

def delete_stage(stage_id: str) -> bool:
    """Xóa một stage khỏi strategy_stages.
       LƯU Ý: Transitions có current_stage_id=stage_id sẽ bị CASCADE DELETE.
             Transitions có next_stage_id=stage_id sẽ bị SET NULL.
             Strategy có initial_stage_id=stage_id sẽ bị SET NULL.
    """
    if not stage_id: return False
    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        print(f"DEBUG: Xóa stage ID={stage_id}...")
        sql = "DELETE FROM strategy_stages WHERE stage_id = %s;"
        cur.execute(sql, (stage_id,))
        conn.commit()
        success = cur.rowcount > 0
        if not success:
             print(f"WARNING (database.py - delete_stage): Không tìm thấy stage_id {stage_id} để xóa.")
    except psycopg2.Error as e:
        print(f"LỖI (database.py - delete_stage): DELETE thất bại: {e}")
        if conn: conn.rollback()
        raise e # Ném lỗi lên để route xử lý
    except Exception as e:
        print(f"LỖI (database.py - delete_stage): Lỗi không xác định: {e}")
        if conn: conn.rollback()
        raise e
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success

# --- Transition Management Functions ---

def add_new_transition(current_stage_id: str, user_intent: str, condition_logic: str | None,
                       next_stage_id: str | None, action_to_suggest: str | None,
                       response_template_ref: str | None, priority: int = 0) -> bool:
    """Thêm một transition mới vào stage_transitions."""
    if not current_stage_id or not user_intent:
        print("WARNING (database.py - add_new_transition): current_stage_id và user_intent là bắt buộc.")
        return False
    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        print(f"DEBUG: Thêm transition: current='{current_stage_id}', intent='{user_intent}'")
        sql = """
            INSERT INTO stage_transitions (current_stage_id, user_intent, condition_logic,
                                           next_stage_id, action_to_suggest, response_template_ref, priority)
            VALUES (%s, %s, %s, %s, %s, %s, %s);
        """
        params = (current_stage_id, user_intent, condition_logic,
                  next_stage_id if next_stage_id else None, # Đảm bảo NULL nếu trống
                  action_to_suggest if action_to_suggest else None,
                  response_template_ref if response_template_ref else None,
                  priority)
        cur.execute(sql, params)
        conn.commit()
        success = True
    except psycopg2.Error as e:
        print(f"LỖI (database.py - add_new_transition): INSERT thất bại: {e}")
        if conn: conn.rollback()
    except Exception as e:
        print(f"LỖI (database.py - add_new_transition): Lỗi không xác định: {e}")
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success

def get_transition_details(transition_id: int) -> dict | None:
    """Lấy chi tiết một transition bằng transition_id."""
    if not transition_id: return None
    details = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        # Lấy cả strategy_id để tiện redirect
        sql = """
            SELECT t.*, ss.strategy_id
            FROM stage_transitions t
            JOIN strategy_stages ss ON t.current_stage_id = ss.stage_id
            WHERE t.transition_id = %s;
        """
        cur.execute(sql, (transition_id,))
        row = cur.fetchone()
        if row: details = dict(row)
    except psycopg2.Error as e:
        print(f"LỖI (database.py - get_transition_details): Truy vấn thất bại: {e}")
    except Exception as e:
        print(f"LỖI (database.py - get_transition_details): Lỗi không xác định: {e}")
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return details

def update_transition(transition_id: int, current_stage_id: str, user_intent: str, condition_logic: str | None,
                      next_stage_id: str | None, action_to_suggest: str | None,
                      response_template_ref: str | None, priority: int) -> bool:
    """Cập nhật một transition."""
    if not transition_id or not current_stage_id or not user_intent:
        return False
    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        sql = """
            UPDATE stage_transitions
            SET current_stage_id = %s, user_intent = %s, condition_logic = %s, next_stage_id = %s,
                action_to_suggest = %s, response_template_ref = %s, priority = %s
            WHERE transition_id = %s;
        """
        params = (current_stage_id, user_intent, condition_logic,
                  next_stage_id if next_stage_id else None,
                  action_to_suggest if action_to_suggest else None,
                  response_template_ref if response_template_ref else None,
                  priority, transition_id)
        cur.execute(sql, params)
        conn.commit()
        success = cur.rowcount > 0
    except psycopg2.Error as e:
        print(f"LỖI (database.py - update_transition): UPDATE thất bại: {e}")
        if conn: conn.rollback()
    except Exception as e:
        print(f"LỖI (database.py - update_transition): Lỗi không xác định: {e}")
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success

def delete_transition(transition_id: int) -> bool:
    """Xóa một transition khỏi stage_transitions."""
    if not transition_id: return False
    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        print(f"DEBUG: Xóa transition ID={transition_id}...")
        sql = "DELETE FROM stage_transitions WHERE transition_id = %s;"
        cur.execute(sql, (transition_id,))
        conn.commit()
        success = cur.rowcount > 0
        if not success:
             print(f"WARNING (database.py - delete_transition): Không tìm thấy transition_id {transition_id} để xóa.")
    except psycopg2.Error as e:
        print(f"LỖI (database.py - delete_transition): DELETE thất bại: {e}")
        if conn: conn.rollback()
        raise e
    except Exception as e:
        print(f"LỖI (database.py - delete_transition): Lỗi không xác định: {e}")
        if conn: conn.rollback()
        raise e
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success


# --- History Functions ---

def get_all_interaction_history() -> list[dict] | None:
    """Lấy TOÀN BỘ lịch sử tương tác (KHÔNG PHÂN TRANG - Cẩn thận với dữ liệu lớn)."""
    history_list = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        print("DEBUG (database.py): Truy vấn TẤT CẢ interaction history (no pagination)...")
        # !!! Đảm bảo tên cột khớp với bảng 'interaction_history' !!!
        cur.execute("""
            SELECT history_id, account_id, app, thread_id, received_text, sent_text,
                   status, strategy_id, stage_id, detected_user_intent, timestamp
            FROM interaction_history
            ORDER BY timestamp DESC;
            """)
        rows = cur.fetchall()
        if rows:
            history_list = [dict(row) for row in rows]
        else:
            history_list = []
    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - get_all_interaction_history): Truy vấn thất bại: {db_err}")
    except Exception as e:
        print(f"LỖI (database.py - get_all_interaction_history): Lỗi không xác định: {e}")
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return history_list

# --- Rule Functions (simple_rules) ---

def get_rule_by_id(rule_id: int) -> dict | None:
    """Lấy chi tiết một luật trong simple_rules bằng ID."""
    if not rule_id: return None
    rule = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        print(f"DEBUG (database.py): Truy vấn rule ID: {rule_id}")
        # !!! Đảm bảo tên bảng và cột khớp !!!
        cur.execute("""
            SELECT rule_id, trigger_keywords, category, response_template_ref, priority, notes
            FROM simple_rules
            WHERE rule_id = %s;
            """, (rule_id,))
        row = cur.fetchone()
        if row:
            rule = dict(row)
        else:
            print(f"WARNING (database.py): Không tìm thấy rule ID: {rule_id}")

    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - get_rule_by_id): Truy vấn thất bại: {db_err}")
    except Exception as e:
        print(f"LỖI (database.py - get_rule_by_id): Lỗi không xác định: {e}")
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return rule


def update_rule(rule_id: int, keywords: str, category: str | None, template_ref: str | None, priority: int, notes: str | None) -> bool:
    """Cập nhật một luật trong simple_rules."""
    if not rule_id or not keywords: # Keywords là bắt buộc
        return False

    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        print(f"DEBUG (database.py): Cập nhật rule ID={rule_id}")
        # !!! Đảm bảo tên bảng và cột khớp !!!
        sql = """
            UPDATE simple_rules
            SET trigger_keywords = %s, category = %s, response_template_ref = %s, priority = %s, notes = %s
            WHERE rule_id = %s;
        """
        params = (keywords, category, template_ref, priority, notes, rule_id)
        cur.execute(sql, params)
        conn.commit()
        success = cur.rowcount > 0 # Kiểm tra xem có dòng nào được cập nhật không
        if not success:
            print(f"WARNING (database.py - update_rule): Không tìm thấy rule_id {rule_id} để cập nhật.")

    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - update_rule): UPDATE thất bại: {db_err}")
        if conn: conn.rollback()
    except Exception as e:
        print(f"LỖI (database.py - update_rule): Lỗi không xác định: {e}")
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return success

def delete_rule(rule_id: int) -> bool:
    """Xóa một luật khỏi simple_rules."""
    if not rule_id: return False
    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        print(f"DEBUG (database.py): Xóa rule ID={rule_id}")
        # !!! Đảm bảo tên bảng khớp !!!
        sql = "DELETE FROM simple_rules WHERE rule_id = %s;"
        cur.execute(sql, (rule_id,))
        conn.commit()
        success = cur.rowcount > 0 # Kiểm tra xem có dòng nào bị xóa không
        if not success:
             print(f"WARNING (database.py - delete_rule): Không tìm thấy rule_id {rule_id} để xóa.")

    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - delete_rule): DELETE thất bại: {db_err}")
        if conn: conn.rollback()
    except Exception as e:
        print(f"LỖI (database.py - delete_rule): Lỗi không xác định: {e}")
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return success

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
# database.py
import psycopg2
import psycopg2.extras 
from psycopg2.extras import DictCursor
import config # Import từ file config.py
import traceback
from flask import current_app
from datetime import datetime, timedelta, timezone 
import random
import json
import os
import logging
from cryptography.fernet import Fernet, InvalidToken
# app/database.py
from psycopg2.extras import DictCursor, Json
# Giả sử bạn đã có hàm get_db_connection() ở đâu đó trong file này
try:
    # Giả sử hàm giải mã nằm trong app/encryption.py
    from .encryption import decrypt_data, encrypt_data
    # Hoặc nếu nó nằm ở thư mục gốc (không khuyến khích):
    # from encryption import decrypt_data
except ImportError:
    print("LỖI NGHIÊM TRỌNG: Không thể import hàm decrypt_data! Việc giải mã API key sẽ thất bại.")
    # Định nghĩa hàm giả để code không bị lỗi NameError ngay lập tức,
    # nhưng bạn PHẢI sửa import hoặc định nghĩa hàm decrypt_data thật.
    def decrypt_data(data):
        print("CẢNH BÁO: Đang dùng hàm decrypt_data giả lập. Hãy implment hoặc sửa import.")
        raise NotImplementedError("Hàm decrypt_data chưa được import hoặc định nghĩa đúng.")

# --- Connection Helper ---
# --- Encryption Helper ---
__fernet_instance = None
def get_valid_api_keys(provider: str) -> list[dict] | None:
    """
    Lấy danh sách các API key hợp lệ (status='active') cho một provider cụ thể.
    Hàm này trả về key đã được giải mã.

    Args:
        provider: Tên nhà cung cấp (ví dụ: 'google_gemini').

    Returns:
        List các dictionary chứa thông tin key (key_id, api_key, provider, ...)
        hoặc None nếu có lỗi CSDL. Trả về list rỗng [] nếu không tìm thấy key hợp lệ.
    """
    # Ghi log khi hàm được gọi (nếu có logger)
    logger = current_app.logger if current_app else print
    logger.debug(f"Attempting to get valid API keys for provider: {provider}")

    if not provider:
        logger.warning("get_valid_api_keys called with empty provider.")
        return [] # Trả về rỗng nếu không có provider

    keys_info_decrypted = [] # List chứa thông tin key đã giải mã
    conn = None
    cur = None
    # Câu SQL lấy các key đang active cho provider được chỉ định
    # Lấy các cột cần thiết, bao gồm cả key đã mã hóa
    sql = """
        SELECT key_id, provider, key_name, api_key_value, status, notes, created_at, updated_at
        FROM public.api_keys
        WHERE provider = %s AND status = 'active'
        ORDER BY key_id ASC; -- Sắp xếp để đảm bảo thứ tự ổn định (tùy chọn)
    """

    try:
        conn = get_db_connection()
        if not conn:
            logger.error("get_valid_api_keys: Failed to get DB connection.")
            return None # Lỗi kết nối

        cur = conn.cursor(cursor_factory=DictCursor) # Dùng DictCursor để truy cập cột theo tên
        cur.execute(sql, (provider,))
        rows = cur.fetchall()
        logger.debug(f"Found {len(rows)} active keys for provider '{provider}' in DB.")

        if rows:
            for row in rows:
                key_data = dict(row) # Chuyển row thành dictionary
                encrypted_key = key_data.get('api_key_value')
                key_id = key_data.get('key_id') # Lấy key_id để log lỗi nếu cần
                decrypted_key = None

                if encrypted_key:
                    try:
                        # >>> GỌI HÀM GIẢI MÃ CỦA BẠN Ở ĐÂY <<<
                        decrypted_key = decrypt_data(encrypted_key)
                        if not decrypted_key:
                             # Nếu giải mã trả về None hoặc rỗng, ghi log và bỏ qua key này
                             logger.warning(f"Decryption returned empty value for API key ID {key_id}. Skipping.")
                             continue
                    except Exception as decrypt_err:
                        # Ghi log lỗi giải mã chi tiết nhưng không dừng toàn bộ quá trình
                        logger.error(f"Lỗi giải mã API key ID {key_id} cho provider '{provider}': {decrypt_err}", exc_info=True)
                        # Bỏ qua key này nếu không giải mã được
                        continue
                else:
                    # Nếu không có key mã hóa trong DB, ghi log và bỏ qua
                    logger.warning(f"API key ID {key_id} for provider '{provider}' has no api_key_value value in DB. Skipping.")
                    continue

                # Thêm key đã giải mã vào dict trả về cho ai_service sử dụng
                # Quan trọng: Key trả về phải có tên là 'api_key'
                key_data['api_key'] = decrypted_key
                # Xóa key đã mã hóa khỏi dict trả về để tránh lộ hoặc nhầm lẫn
                key_data.pop('api_key_value', None)

                # Thêm dict chứa thông tin key đã giải mã vào list kết quả
                keys_info_decrypted.append(key_data)

            logger.info(f"Successfully fetched and decrypted {len(keys_info_decrypted)} keys for provider '{provider}'.")
            return keys_info_decrypted # Trả về list các key đã giải mã thành công
        else:
            logger.warning(f"No active API keys found for provider '{provider}' in the database.")
            return [] # Không tìm thấy key nào hợp lệ

    except psycopg2.Error as db_err:
        logger.error(f"DB Error getting valid API keys for '{provider}': {db_err}", exc_info=True)
        return None # Lỗi CSDL
    except Exception as e:
        logger.error(f"Unexpected Error getting valid API keys for '{provider}': {e}", exc_info=True)
        return None # Lỗi không xác định
    finally:
        if cur: cur.close()
        if conn: conn.close()


# --- API Key Management Functions ---
def add_api_key(key_name: str, provider: str, api_key_value: str, status: str, notes: str | None) -> bool:
    """Thêm API Key mới, mã hóa giá trị key trước khi lưu."""
    logger = current_app.logger if current_app else print
    if not key_name or not provider or not api_key_value:
        logger.error("add_api_key: key_name, provider, và api_key_value là bắt buộc.")
        return False

    # --- BƯỚC 1: MÃ HÓA KEY ---
    encrypted_key_to_save = None
    try:
        encrypted_key_bytes = encrypt_data(api_key_value)
        if encrypted_key_bytes is None:
            logger.error(f"Lỗi mã hóa API key cho key_name: {key_name}")
            return False
        # QUAN TRỌNG: Giả sử cột trong DB là BYTEA. Nếu là TEXT, hãy chuyển sang Base64:
        # import base64
        # encrypted_key_to_save = base64.urlsafe_b64encode(encrypted_key_bytes).decode('utf-8')
        encrypted_key_to_save = encrypted_key_bytes # Dùng trực tiếp bytes nếu cột là BYTEA
    except Exception as enc_err:
        logger.error(f"Lỗi nghiêm trọng khi mã hóa key '{key_name}': {enc_err}", exc_info=True)
        return False


    # --- BƯỚC 2: LƯU VÀO DB ---
    conn = None
    cur = None
    success = False

    # !!!!!!!!!! THAY THẾ TÊN CỘT Ở ĐÂY !!!!!!!!!!
    # Thay 'YOUR_ACTUAL_COLUMN_NAME_FOR_ENCRYPTED_KEY' bằng tên cột đúng trong bảng api_keys
    # Ví dụ: Nếu tên cột là 'key_value', thì sửa thành 'key_value'
    actual_encrypted_column_name = 'api_key_value'
    # !!!!!!!!!! ----------------------------- !!!!!!!!!!

    # Kiểm tra xem placeholder đã được thay thế chưa
    if actual_encrypted_column_name == 'api_key_value':
        logger.error("LỖI CODE: Bạn chưa thay thế 'api_key_value' trong hàm add_api_key!")
        return False # Ngăn chặn lỗi DB

    # Dùng tên cột đúng trong câu SQL INSERT
    sql = f"""
        INSERT INTO public.api_keys (key_name, provider, "{actual_encrypted_column_name}", status, notes)
        VALUES (%s, %s, %s, %s, %s);
    """

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(sql, (key_name, provider, encrypted_key_to_save, status, notes))
        conn.commit()
        success = True
        logger.info(f"Đã thêm API Key '{key_name}' vào DB.")
    except psycopg2.IntegrityError:
        logger.warning(f"Lỗi: API Key name '{key_name}' có thể đã tồn tại.")
        if conn: conn.rollback()
    except psycopg2.Error as db_err:
        logger.error(f"Lỗi CSDL khi thêm API Key '{key_name}': {db_err}", exc_info=True)
        if conn: conn.rollback()
    except Exception as e:
        logger.error(f"Lỗi không xác định khi thêm API Key '{key_name}': {e}", exc_info=True)
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success


def get_all_api_keys() -> list[dict] | None:
    """Lấy danh sách tất cả API keys (không bao gồm giá trị key)."""
    keys_list = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        # Không lấy cột api_key_value trong danh sách chung
        sql = """
            SELECT key_id, key_name, provider, status, notes, created_at, updated_at, last_used_at, rate_limited_until
            FROM public.api_keys ORDER BY provider, key_name;
        """
        cur.execute(sql)
        rows = cur.fetchall()
        keys_list = [dict(row) for row in rows] if rows else []
    except psycopg2.Error as e: print(f"ERROR (db - get_all_api_keys): {e}"); keys_list = None
    except Exception as e: print(f"ERROR (db - get_all_api_keys): {e}"); keys_list = None
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return keys_list

def get_api_key_details(key_id: int) -> dict | None:
    """Lấy chi tiết một API key bằng ID (không bao gồm giá trị key)."""
    if not key_id: return None
    details = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        sql = """
            SELECT key_id, key_name, provider, status, notes, created_at, updated_at, last_used_at, rate_limited_until
            FROM public.api_keys WHERE key_id = %s;
        """
        cur.execute(sql, (key_id,))
        row = cur.fetchone()
        if row: details = dict(row)
    except psycopg2.Error as e: print(f"ERROR (db - get_api_key_details) ID {key_id}: {e}")
    except Exception as e: print(f"ERROR (db - get_api_key_details) ID {key_id}: {e}")
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return details

def get_decrypted_api_key_value(key_id: int) -> str | None:
    """Lấy giá trị API key đã giải mã dựa trên key_id."""
    logger = current_app.logger if current_app else print
    if key_id is None: return None

    decrypted_key = None
    conn = None
    cur = None

    # !!!!!!!!!! THAY THẾ TÊN CỘT Ở ĐÂY !!!!!!!!!!
    actual_encrypted_column_name = 'api_key_value'
    # !!!!!!!!!! ----------------------------- !!!!!!!!!!
    if actual_encrypted_column_name == 'api_key_value':
         logger.error("LỖI CODE: Bạn chưa thay thế placeholder tên cột trong hàm get_decrypted_api_key_value!")
         return None

    sql = f'SELECT "{actual_encrypted_column_name}" FROM public.api_keys WHERE key_id = %s;'

    try:
        conn = get_db_connection()
        if not conn: return None
        cur = conn.cursor()
        cur.execute(sql, (key_id,))
        result = cur.fetchone()
        if result and result[0]:
            encrypted_value = result[0]
            try:
                decrypted_key = decrypt_data(encrypted_value)
                if not decrypted_key: logger.warning(f"Decryption returned empty for key ID {key_id}.")
            except Exception as decrypt_err:
                logger.error(f"Error decrypting API key ID {key_id}: {decrypt_err}", exc_info=False)
        else:
             logger.warning(f"No encrypted value found for key ID {key_id}.")

    except psycopg2.errors.UndefinedColumn as col_err:
        logger.error(f"DB Error getting key value for ID {key_id}: Column not found - {col_err}. Check column name '{actual_encrypted_column_name}' in SQL.", exc_info=False)
    except psycopg2.Error as db_err:
        logger.error(f"DB Error getting key value for ID {key_id}: {db_err}", exc_info=True)
    except Exception as e:
        logger.error(f"Unexpected Error getting key value for ID {key_id}: {e}", exc_info=True)
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return decrypted_key

def get_active_api_keys_by_provider(provider: str) -> list[dict] | None:
    """
    Lấy danh sách các API key đang hoạt động (status='active') cho một provider.
    Hàm này trả về key đã được giải mã.
    """
    logger = current_app.logger if current_app else print
    logger.debug(f"Getting active API keys for provider: {provider}")

    if not provider:
        logger.warning("get_active_api_keys_by_provider called with empty provider.")
        return []

    keys_info_decrypted = []
    conn = None
    cur = None

    # !!!!!!!!!! THAY THẾ TÊN CỘT Ở ĐÂY !!!!!!!!!!
    # Thay 'YOUR_ACTUAL_COLUMN_NAME_FOR_ENCRYPTED_KEY' bằng tên cột đúng trong bảng api_keys
    actual_encrypted_column_name = 'api_key_value'
    # !!!!!!!!!! ----------------------------- !!!!!!!!!!

    # Kiểm tra xem placeholder đã được thay thế chưa
    if actual_encrypted_column_name == 'api_key_value':
        logger.error("LỖI CODE: Bạn chưa thay thế 'api_key_value' trong hàm get_active_api_keys_by_provider!")
        return None # Trả về None để báo lỗi nghiêm trọng

    # Dùng tên cột đúng trong câu SQL SELECT
    sql = f"""
        SELECT key_id, provider, key_name, api_key_value, status, notes, created_at, updated_at
        FROM public.api_keys
        WHERE LOWER(provider) = LOWER(%s) AND status = 'active'
        ORDER BY key_id ASC;
    """

    try:
        conn = get_db_connection()
        if not conn: return None

        cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute(sql, (provider,))
        rows = cur.fetchall()
        logger.debug(f"Found {len(rows)} active DB keys for provider '{provider}'.")

        if rows:
            for row in rows:
                key_data = dict(row)
                encrypted_key = key_data.get(actual_encrypted_column_name) # <<< Dùng tên cột đúng
                key_id = key_data.get('key_id')
                decrypted_key = None

                if encrypted_key:
                    try:
                        decrypted_key = decrypt_data(encrypted_key)
                        if not decrypted_key:
                             logger.warning(f"Decryption returned empty for key ID {key_id}. Skipping.")
                             continue
                    except Exception as decrypt_err:
                        logger.error(f"Error decrypting API key ID {key_id}: {decrypt_err}", exc_info=False)
                        continue
                else:
                    logger.warning(f"Key ID {key_id} has no value in DB column '{actual_encrypted_column_name}'. Skipping.")
                    continue

                # Key trả về cho ai_service vẫn là 'api_key'
                key_data['api_key'] = decrypted_key
                # Xóa cột mã hóa gốc khỏi dict trả về
                key_data.pop(actual_encrypted_column_name, None)

                keys_info_decrypted.append(key_data)

            logger.info(f"Successfully fetched and decrypted {len(keys_info_decrypted)} keys for provider '{provider}'.")
            return keys_info_decrypted
        else:
            logger.warning(f"No active API keys found for provider '{provider}'.")
            return []

    except psycopg2.errors.UndefinedColumn as col_err:
         logger.error(f"DB Error getting keys for '{provider}': Column not found - {col_err}. Check column name '{actual_encrypted_column_name}' in SQL.", exc_info=False)
         # Log câu SQL bị lỗi để dễ debug
         logger.error(f"Failed SQL: {cur.query.decode() if cur and cur.query else 'Could not get query'}")
         return None
    except psycopg2.Error as db_err:
        logger.error(f"DB Error getting keys for '{provider}': {db_err}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected Error getting keys for '{provider}': {e}", exc_info=True)
        return None
    finally:
        if cur: cur.close()
        if conn: conn.close()

def update_api_key(key_id: int, key_name: str, status: str, notes: str | None) -> bool:
    """Cập nhật thông tin (không phải giá trị key) của một API key."""
    if not key_id or not key_name or not status: return False
    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        sql = """
            UPDATE public.api_keys
            SET key_name = %s, status = %s, notes = %s, updated_at = NOW()
            WHERE key_id = %s;
        """
        params = (key_name, status, notes, key_id)
        cur.execute(sql, params)
        conn.commit()
        success = cur.rowcount > 0
    except psycopg2.IntegrityError as e: # Lỗi unique key_name
        print(f"ERROR (db - update_api_key): Integrity Error ID {key_id}: {e}"); conn.rollback()
    except psycopg2.Error as e: print(f"ERROR (db - update_api_key): DB Error ID {key_id}: {e}"); conn.rollback()
    except Exception as e: print(f"ERROR (db - update_api_key): Unexpected error ID {key_id}: {e}"); conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success

def delete_api_key(key_id: int) -> bool:
    """Xóa một API key."""
    if not key_id: return False
    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        sql = "DELETE FROM public.api_keys WHERE key_id = %s;"
        cur.execute(sql, (key_id,))
        conn.commit()
        success = cur.rowcount > 0
    except psycopg2.Error as e: print(f"ERROR (db - delete_api_key) ID {key_id}: {e}"); conn.rollback()
    except Exception as e: print(f"ERROR (db - delete_api_key) ID {key_id}: {e}"); conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success

def update_key_last_used(key_id: int) -> bool:
    """Cập nhật thời gian sử dụng cuối cùng cho một key."""
    if not key_id: return False
    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        sql = "UPDATE public.api_keys SET last_used_at = NOW() WHERE key_id = %s;"
        cur.execute(sql, (key_id,))
        conn.commit()
        success = cur.rowcount > 0
    except Exception as e: print(f"ERROR updating last_used for key {key_id}: {e}"); conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success

def set_key_rate_limit_expiry(key_id: int, expiry_timestamp: datetime) -> bool:
    """Đặt trạng thái rate_limited và thời gian hết hạn cho key."""
    if not key_id or not expiry_timestamp: return False
    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        # Cập nhật cả status và thời gian hết hạn
        sql = "UPDATE public.api_keys SET status = 'rate_limited', rate_limited_until = %s, updated_at = NOW() WHERE key_id = %s;"
        cur.execute(sql, (expiry_timestamp, key_id))
        conn.commit()
        success = cur.rowcount > 0
    except Exception as e: print(f"ERROR setting rate limit expiry for key {key_id}: {e}"); conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success


def get_db_connection():
    conn = None
    try:
        # !!! THAY ĐỔI CÁCH LẤY CONFIG: DÙNG os.environ.get !!!
        # Sử dụng cùng tên biến môi trường và giá trị mặc định như trong config.py
        db_host = os.environ.get('DB_HOST', 'localhost')
        db_port = os.environ.get('DB_PORT', '5432')
        db_name = os.environ.get('DB_NAME')
        db_user = os.environ.get('DB_USER')
        db_password = os.environ.get('DB_PASSWORD')

        # --- Bỏ khối kiểm tra và log dùng current_app ---
        # print("--- DEBUG DB Connect Params (from current_app) ---")
        # ... (bỏ các dòng print dùng current_app.config) ...

        # Kiểm tra xem các biến môi trường cần thiết có được đặt không
        if not db_name or not db_user or not db_password:
            print("LỖI (database.py): Thiếu cấu hình CSDL (DB_NAME, DB_USER, DB_PASSWORD) trong biến môi trường!")
            return None

        # Tạo chuỗi DSN (Data Source Name) để kết nối
        # Dùng f-string hoặc cách khác đều được
        dsn = f"dbname='{db_name}' user='{db_user}' host='{db_host}' password='{db_password}' port='{db_port}'"
        #print(f"DEBUG (database.py): Connecting with DSN: dbname='{db_name}' user='{db_user}' host='{db_host}' port='{db_port}' password='***'") # Che password

        # Lệnh kết nối sử dụng DSN
        conn = psycopg2.connect(dsn)
        #print("DEBUG (database.py): Kết nối CSDL thành công (dùng DSN).")
        return conn

    # --- Bỏ khối except RuntimeError vì không còn dùng current_app ---
    # except RuntimeError as rt_err: ...

    except psycopg2.Error as db_err: # Giữ lại bắt lỗi psycopg2
        print(f"LỖI KẾT NỐI CSDL (psycopg2.Error): {db_err}")
        print(traceback.format_exc())
        return None
    except Exception as e: # Giữ lại bắt lỗi chung
         print(f"LỖI (database.py): Lỗi không xác định khi kết nối CSDL: {e}")
         print(traceback.format_exc())
         return None

def find_transition(current_stage_id: str | None, user_intent: str | None) -> dict | None:
    """
    Tìm luật chuyển tiếp giai đoạn phù hợp nhất từ CSDL.
    Đã sửa để lấy đúng cột action và trả về dict đầy đủ hơn.

    Args:
        current_stage_id: ID của giai đoạn hiện tại.
        user_intent: Ý định của người dùng vừa được phát hiện.

    Returns:
        Một dictionary chứa thông tin luật chuyển tiếp bao gồm:
        next_stage_id, response_template_ref, action_macro_code, action_params_str
        hoặc None nếu không tìm thấy/lỗi.
    """
    # Lấy logger hoặc dùng print
    logger = current_app.logger if current_app else print

    if not current_stage_id or not user_intent:
        logger.debug(f"DEBUG (database.py - find_transition): Thiếu current_stage_id ('{current_stage_id}') hoặc user_intent ('{user_intent}').")
        return None

    transition_rule = None
    conn = get_db_connection()
    if not conn:
        return None

    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        logger.debug(f"DEBUG (database.py): Tìm transition cho stage='{current_stage_id}', intent='{user_intent}'")

        # === SỬA LẠI CÂU SQL SELECT ===
        sql = """
            SELECT
                next_stage_id,
                response_template_ref,
                action_macro_code,
                action_params_str          -- Lấy cột TEXT chứa JSON params
            FROM stage_transitions
            WHERE current_stage_id = %s AND (user_intent = %s OR user_intent = 'any')
            ORDER BY
                CASE user_intent WHEN 'any' THEN 0 ELSE 1 END DESC, -- Ưu tiên luật không phải 'any'
                priority DESC -- Ưu tiên luật có priority cao hơn
            LIMIT 1; -- Chỉ lấy luật phù hợp nhất
        """
        # =============================
        cur.execute(sql, (current_stage_id, user_intent))
        row = cur.fetchone()

        if row:
            transition_rule = dict(row) # Chuyển kết quả thành dictionary
            # Chuyển đổi action_params_str thành dict nếu có thể
            params_str = transition_rule.get('action_params_str')
            parsed_params = {}
            if params_str:
                try:
                    loaded_json = json.loads(params_str)
                    if isinstance(loaded_json, dict):
                        parsed_params = loaded_json
                    else:
                         logger.warning(f"WARN (find_transition): action_params_str is not a JSON object: {params_str}")
                except json.JSONDecodeError:
                     logger.warning(f"WARN (find_transition): Could not parse action_params_str: {params_str}")
            # Thêm key 'action_params' chứa dict đã parse (hoặc rỗng) vào kết quả trả về
            transition_rule['action_params'] = parsed_params
            logger.debug(f"DEBUG (database.py): Transition tìm thấy: {transition_rule}")
        else:
            logger.debug(f"DEBUG (database.py): Không tìm thấy transition phù hợp cho stage='{current_stage_id}', intent='{user_intent}'.")

    except psycopg2.Error as db_err:
        # === SỬA LẠI LOGGING ===
        logger.error(f"LỖI (database.py - find_transition): Truy vấn thất bại: {db_err}", exc_info=True) # Thêm traceback
        transition_rule = None # Đảm bảo trả về None khi lỗi
    except Exception as e:
        logger.error(f"LỖI (database.py - find_transition): Lỗi không xác định: {e}", exc_info=True) # Thêm traceback
        transition_rule = None
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


def get_rules_by_category(account_id: str,category=None): # Ví dụ sửa hàm lấy rules
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

def add_new_strategy(strategy_id: str, name: str, description: str | None,
                     initial_stage_id: str, strategy_type: str) -> tuple[bool, str | None]: # <<< XÓA target_platform, execution_config khỏi tham số
    """
    Thêm một chiến lược mới vào bảng strategies.
    Hỗ trợ các loại: 'language', 'control', 'mainloop'.
    """
    logger = current_app.logger if current_app else print
    logger.info(f"DEBUG (db.add_new_strategy): Adding strategy '{strategy_id}', type '{strategy_type}'")

    # --- Kiểm tra đầu vào ---
    if not strategy_id or not name  or not strategy_type:
        return False, "Strategy ID, Name, Initial Stage ID, và Strategy Type là bắt buộc."

    valid_types = ['language', 'control', 'mainloop'] # Đảm bảo 'mainloop' có ở đây
    if strategy_type not in valid_types:
        return False, f"Strategy Type không hợp lệ (phải là một trong: {', '.join(valid_types)})."

    # --- Không cần validate JSON execution_config nữa ---

    # --- Thực hiện thao tác CSDL ---
    conn = get_db_connection()
    if not conn: return False, "Không thể kết nối CSDL."
    cur = None
    success = False
    error_msg = None
    try:
        cur = conn.cursor()
        # <<< XÓA target_platform và execution_config khỏi câu lệnh INSERT >>>
        sql = """
            INSERT INTO public.strategies (
                strategy_id, name, description, initial_stage_id, strategy_type,
                updated_at
            ) VALUES (%s, %s, %s, %s, %s, NOW());
        """
        params = (
            strategy_id, name, description, initial_stage_id, strategy_type
        ) # <<< XÓA 2 tham số cuối khỏi tuple params >>>

        # logger.debug(f"DEBUG SQL (add_new_strategy): {cur.mogrify(sql, params).decode('utf-8','ignore')}")
        cur.execute(sql, params)
        conn.commit()
        success = True
        logger.info(f"INFO (db.add_new_strategy): Thêm strategy '{strategy_id}' type '{strategy_type}' thành công.")

    # ... (Phần except và finally giữ nguyên) ...
    except psycopg2.IntegrityError as int_err:
        error_msg = f"Lỗi ràng buộc CSDL (ID hoặc Name '{strategy_id}'/'{name}' đã tồn tại?): {int_err}"
        logger.error(f"ERROR (db.add_new_strategy): {error_msg}")
        if conn: conn.rollback()
    except psycopg2.Error as db_err:
        error_msg = f"Lỗi CSDL khi thêm strategy: {db_err}" # <<< Lỗi của bạn xuất hiện ở đây >>>
        logger.error(f"ERROR (db.add_new_strategy): {error_msg}\n{traceback.format_exc()}")
        if conn: conn.rollback()
    except Exception as e:
        error_msg = f"Lỗi không xác định khi thêm strategy: {e}"
        logger.error(f"ERROR (db.add_new_strategy): {error_msg}\n{traceback.format_exc()}")
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success, error_msg


def update_strategy(strategy_id: str, name: str, description: str | None, initial_stage_id: str | None) -> tuple[bool, str | None]:
    """Cập nhật thông tin cơ bản của một strategy (Name, Desc, Initial Stage).
       Không cập nhật strategy_type.
       Trả về True nếu không có lỗi DB, False nếu có lỗi.
    """
    logger = current_app.logger if current_app else print
    logger.debug(f"DEBUG (db.update_strategy): Attempting to update strategy '{strategy_id}' (excluding type)") # Log giữ nguyên

    if not strategy_id or not name: # Name vẫn là bắt buộc
        return False, "Strategy ID và Name là bắt buộc."

    conn = get_db_connection()
    if not conn: return False, "Không thể kết nối CSDL."
    cur = None
    success = False # Mặc định là False
    error_msg = None
    try:
        cur = conn.cursor()
        sql = """
            UPDATE public.strategies
            SET name = %s, description = %s, initial_stage_id = %s, updated_at = NOW()
            WHERE strategy_id = %s;
        """
        # Giá trị initial_stage_id có thể là None (từ route đã xử lý '' thành None)
        params = (name, description, initial_stage_id, strategy_id)
        cur.execute(sql, params)
        conn.commit()

        # === THAY ĐỔI LOGIC KIỂM TRA SUCCESS ===
        # Chỉ coi là thất bại nếu có lỗi DB xảy ra (bắt trong except)
        # Nếu không có lỗi, coi như thành công, dù rowcount có thể là 0 (nếu không có gì thay đổi)
        success = True
        # logger.info(f"Update executed for strategy '{strategy_id}'. Rowcount: {cur.rowcount}") # Log rowcount nếu muốn

    except psycopg2.IntegrityError as e_int:
         # Bắt lỗi ràng buộc (ví dụ: initial_stage_id không tồn tại trong stages VÀ constraint là RESTRICT)
         error_msg = f"Lỗi ràng buộc CSDL (Tên '{name}' đã tồn tại? Hoặc Initial Stage không hợp lệ?): {e_int}"
         logger.error(f"ERROR (db.update_strategy): {error_msg}")
         if conn: conn.rollback()
         success = False # Đặt lại thành False khi có lỗi
    except psycopg2.Error as e_db:
        error_msg = f"Lỗi CSDL khi cập nhật strategy: {e_db}"
        logger.error(f"ERROR (db.update_strategy): {error_msg}", exc_info=True)
        if conn: conn.rollback()
        success = False # Đặt lại thành False khi có lỗi
    except Exception as e:
        error_msg = f"Lỗi không xác định khi cập nhật strategy: {e}"
        logger.error(f"ERROR (db.update_strategy): {error_msg}", exc_info=True)
        if conn: conn.rollback()
        success = False # Đặt lại thành False khi có lỗi
    finally:
        if cur: cur.close()
        if conn: conn.close()

    # Trả về success (True nếu không có Exception) và error_msg (nếu có)
    return success, error_msg

def get_all_strategies(strategy_type_filter: str | None = None) -> list[dict] | None:
    """
    Lấy danh sách các chiến lược, có thể lọc theo strategy_type.
    Đã sửa lỗi lọc cho 'mainloop'.
    """
    logger = current_app.logger if current_app else print # Dùng logger nếu có
    strategies_list = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        sql = """
            SELECT strategy_id, name, description, initial_stage_id, strategy_type, updated_at
            FROM public.strategies
        """
        params = []
        # === SỬA LẠI LOGIC LỌC ===
        # Chỉ cần kiểm tra xem strategy_type_filter có giá trị hợp lệ không
        if strategy_type_filter and strategy_type_filter in ['language', 'control', 'mainloop']:
            sql += " WHERE strategy_type = %s" # Thêm điều kiện WHERE
            params.append(strategy_type_filter) # Thêm giá trị filter vào params
            logger.debug(f"Applying strategy_type filter: {strategy_type_filter}")
        else:
             logger.debug("No valid strategy_type filter applied, fetching all types.")
        # === KẾT THÚC SỬA LOGIC ===

        sql += " ORDER BY strategy_type, name;" # Sắp xếp

        # Log câu lệnh SQL cuối cùng trước khi chạy
        # logger.debug(f"DEBUG SQL (get_all_strategies): {cur.mogrify(sql, tuple(params)).decode('utf-8','ignore')}")
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
        strategies_list = [dict(row) for row in rows] if rows else []
        # Log debug này bây giờ sẽ phản ánh đúng hơn kết quả của việc lọc
        logger.debug(f"DEBUG DB (get_all_strategies): Fetched {len(strategies_list)} strategies matching filter '{strategy_type_filter}'.")

    except psycopg2.Error as db_err:
        logger.error(f"LỖI (database.py - get_all_strategies): Truy vấn thất bại: {db_err}", exc_info=True)
        strategies_list = None # Trả về None khi lỗi
    except Exception as e:
        logger.error(f"LỖI (database.py - get_all_strategies): Lỗi không xác định: {e}", exc_info=True)
        strategies_list = None
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return strategies_list


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
    """Lấy tất cả các đề xuất đang chờ (đã thêm category, ref)."""
    suggestions = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        print(f"DEBUG (database.py): Truy vấn các đề xuất đang chờ...")
        # <<< THÊM CỘT MỚI VÀO SELECT >>>
        cur.execute("""
            SELECT suggestion_id, suggested_keywords, suggested_template_text,
                   suggested_category, suggested_template_ref,
                   source_examples, created_at
            FROM suggested_rules
            WHERE status = 'pending'
            ORDER BY created_at DESC;
            """)
        rows = cur.fetchall()
        if rows:
            suggestions = [dict(row) for row in rows]
            print(f"DEBUG (database.py): Tìm thấy {len(suggestions)} đề xuất đang chờ.")
        else:
            print(f"DEBUG (database.py): Không có đề xuất nào đang chờ.")
            suggestions = []
    # ... (Except và Finally như cũ) ...
    except psycopg2.Error as db_err: # Giữ lại để handle lỗi cụ thể nếu cần
        print(f"LỖI DB trong get_pending_suggestions: {db_err}")
        suggestions = None
    except Exception as e:
        print(f"LỖI không xác định trong get_pending_suggestions: {e}")
        suggestions = None
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return suggestions

def get_suggestion_by_id(suggestion_id: int) -> dict | None:
    """Lấy chi tiết một đề xuất bằng ID (đã thêm category, ref)."""
    if not suggestion_id: return None
    suggestion = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        print(f"DEBUG (database.py): Truy vấn đề xuất ID: {suggestion_id}")
        # <<< THÊM CỘT MỚI VÀO SELECT >>>
        cur.execute("""
            SELECT suggestion_id, suggested_keywords, suggested_template_text,
                   suggested_category, suggested_template_ref,
                   source_examples, status
            FROM suggested_rules
            WHERE suggestion_id = %s;
            """, (suggestion_id,))
        row = cur.fetchone()
        if row: suggestion = dict(row)
        else: print(f"WARNING (database.py): Không tìm thấy đề xuất ID: {suggestion_id}")
    # ... (Except và Finally như cũ) ...
    except psycopg2.Error as db_err: # Giữ lại để handle lỗi cụ thể nếu cần
        print(f"LỖI DB trong get_suggestion_by_id: {db_err}")
        suggestion = None
    except Exception as e:
        print(f"LỖI không xác định trong get_suggestion_by_id: {e}")
        suggestion = None
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

def add_new_template(_template_ref, description, category, first_variation_text):
    """
    Thêm một template_ref mới vào bảng 'templates' và variation đầu tiên
    vào bảng 'template_variations'. Sử dụng current_app.logger.
    """
    # === Lấy logger từ Flask app context ===
    logger = current_app.logger if current_app else print # Dùng print nếu không có context

    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            raise Exception("Không thể kết nối tới CSDL.")

        with conn.cursor() as cur:
            # === Bước 1: INSERT hoặc UPDATE vào bảng 'templates' ===
            sql_upsert_template = """
                INSERT INTO public.templates (template_ref, description, category, created_at, updated_at)
                VALUES (%s, %s, %s, NOW(), NOW())
                ON CONFLICT (template_ref) DO UPDATE SET
                    description = EXCLUDED.description,
                    category = EXCLUDED.category,
                    updated_at = NOW();
            """
            category_to_insert = category if category else None
            cur.execute(sql_upsert_template, (_template_ref, description, category_to_insert))
            # === SỬA LẠI: Dùng logger ===
            logger.debug(f"Executed UPSERT for templates table: {_template_ref}")

            # === Bước 2: INSERT variation đầu tiên vào 'template_variations' ===
            sql_insert_variation = """
                INSERT INTO public.template_variations (template_ref, variation_text, created_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (template_ref, variation_text) DO NOTHING;
            """
            cur.execute(sql_insert_variation, (_template_ref, first_variation_text))
            # === SỬA LẠI: Dùng logger ===
            logger.debug(f"Executed INSERT for template_variations table: {_template_ref}")

            conn.commit()
            # === SỬA LẠI: Dùng logger ===
            logger.info(f"Template '{_template_ref}' và variation đầu tiên đã được thêm/cập nhật thành công.")
            # Trả về True và template_ref
            return True, _template_ref

    except psycopg2.Error as e:
        # === SỬA LẠI: Dùng logger (ghi lỗi kèm traceback) ===
        logger.error(f"LỖI (database.py - add_new_template): INSERT/UPSERT thất bại: {e}", exc_info=True)
        if conn: conn.rollback()
        error_detail = f"Database error: {e}"
        if hasattr(e, 'pgcode') and e.pgcode == psycopg2.errors.UNIQUE_VIOLATION:
             error_detail = f"Template Ref '{_template_ref}' đã tồn tại hoặc Variation Text bị trùng."
        elif hasattr(e, 'pgcode') and e.pgcode == psycopg2.errors.FOREIGN_KEY_VIOLATION:
             error_detail = f"Lỗi Khóa ngoại. Kiểm tra template_ref '{_template_ref}' có tồn tại trong bảng templates không?"
        return False, error_detail

    except Exception as ex:
        # === SỬA LẠI: Dùng logger ===
        logger.critical(f"LỖI KHÔNG XÁC ĐỊNH (database.py - add_new_template): {ex}", exc_info=True)
        if conn: conn.rollback()
        return False, f"An unexpected error occurred: {ex}"
    finally:
        if conn: conn.close()

def get_all_rules() -> list[dict] | None:
    """Lấy tất cả luật (gọi hàm lọc không có filter)."""
    print("DEBUG (database.py - get_all_rules): Calling get_filtered_rules with no filters.")
    return get_filtered_rules(filters=None)


def get_all_accounts(page: int = 1, per_page: int = 30) -> tuple[list[dict] | None, int | None]:
    """
    Lấy danh sách tất cả các tài khoản từ CSDL với phân trang.

    Args:
        page: Số trang hiện tại.
        per_page: Số lượng mục mỗi trang.

    Returns:
        Tuple: (list các account của trang hiện tại hoặc None nếu lỗi,
                tổng số account hoặc None nếu lỗi)
    """
    accounts_list = None
    total_items = None
    conn = get_db_connection()
    if not conn: return None, None
    cur = None
    try:
        # Query đếm tổng số tài khoản
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM public.accounts;")
        total_items = cur.fetchone()[0]
        cur.close()

        # Query lấy dữ liệu cho trang hiện tại
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        offset = (page - 1) * per_page
        sql = """
            SELECT account_id, platform, username, status, notes, goal, default_strategy_id
            FROM accounts
            ORDER BY account_id -- Hoặc sắp xếp theo tiêu chí khác
            LIMIT %s OFFSET %s;
        """
        cur.execute(sql, (per_page, offset))
        rows = cur.fetchall()
        accounts_list = [dict(row) for row in rows] if rows else []
        print(f"DEBUG (database.py - get_all_accounts): Fetched {len(accounts_list)} accounts for page {page}.")

    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - get_all_accounts): Truy vấn thất bại: {db_err}")
        accounts_list = None; total_items = None
    except Exception as e:
        print(f"LỖI (database.py - get_all_accounts): Lỗi không xác định: {e}")
        accounts_list = None; total_items = None
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return accounts_list, total_items
# === Thêm hàm này vào backup/app/database.py ===

def get_all_accounts_paginated(page: int = 1, per_page: int = 10, search_query: str | None = None) -> tuple[list[dict] | None, int | None]:
    """
    Lấy danh sách accounts với phân trang và tìm kiếm.
    Trả về tuple: (list các account của trang hiện tại hoặc None nếu lỗi,
                   tổng số account khớp tìm kiếm hoặc None nếu lỗi)
    """
    accounts_list = None
    total_items = None
    conn = get_db_connection() # Sử dụng hàm kết nối CSDL của bạn
    if not conn: return None, None
    cur = None

    # --- Xây dựng mệnh đề WHERE và params cho tìm kiếm ---
    where_clauses = []
    params = []
    if search_query:
        search_term = f"%{search_query}%"
        # Tìm kiếm trên nhiều trường (không phân biệt hoa thường với ILIKE)
        where_clauses.append("""
            (account_id ILIKE %s OR
             platform ILIKE %s OR
             username ILIKE %s OR
             status ILIKE %s)
        """)
        # Lặp lại search_term 4 lần cho mỗi cột tìm kiếm
        params.extend([search_term] * 4)

    where_sql = ""
    if where_clauses:
        # Nối các điều kiện (nếu có nhiều hơn 1) bằng AND
        where_sql = "WHERE " + " AND ".join(where_clauses)

    try:
        # --- Query 1: Đếm tổng số mục khớp bộ lọc ---
        cur = conn.cursor()
        count_sql = f"SELECT COUNT(*) FROM public.accounts {where_sql};"
        # Log câu lệnh SQL nếu cần debug
        # print(f"DEBUG Count SQL: {cur.mogrify(count_sql, tuple(params)).decode('utf-8', 'ignore')}")
        cur.execute(count_sql, tuple(params))
        total_items = cur.fetchone()[0]
        cur.close() # Đóng cursor đếm

        # --- Query 2: Lấy dữ liệu cho trang hiện tại ---
        accounts_list = [] # Khởi tạo list rỗng phòng trường hợp không có kết quả
        if total_items is not None and total_items > 0 and page > 0: # Chỉ query nếu có dữ liệu và page hợp lệ
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor) # Dùng DictCursor
            offset = (page - 1) * per_page
            data_sql = f"""
                SELECT account_id, platform, username, status, notes, goal, default_strategy_id
                FROM accounts
                {where_sql}
                ORDER BY account_id -- Hoặc sắp xếp theo tiêu chí khác
                LIMIT %s OFFSET %s;
            """
            # Thêm limit và offset vào params cho query lấy dữ liệu
            data_params = params + [per_page, offset]
            # print(f"DEBUG Data SQL: {cur.mogrify(data_sql, tuple(data_params)).decode('utf-8', 'ignore')}")
            cur.execute(data_sql, tuple(data_params))
            rows = cur.fetchall()
            accounts_list = [dict(row) for row in rows] if rows else []
            print(f"DEBUG (database.py - get_all_accounts_paginated): Lấy được {len(accounts_list)} tài khoản cho trang {page}.")
        elif total_items == 0:
             print(f"DEBUG (database.py - get_all_accounts_paginated): Không tìm thấy tài khoản nào khớp tìm kiếm.")
        # else: Lỗi khi đếm total_items

    except psycopg2.Error as db_err:
        # Sử dụng logger nếu có, nếu không thì print
        log_func = current_app.logger.error if current_app else print
        log_func(f"LỖI (database.py - get_all_accounts_paginated): Truy vấn thất bại: {db_err}")
        if current_app: print(traceback.format_exc()) # In traceback nếu có context app
        accounts_list = None; total_items = None
    except Exception as e:
        log_func = current_app.logger.error if current_app else print
        log_func(f"LỖI (database.py - get_all_accounts_paginated): Lỗi không xác định: {e}")
        if current_app: print(traceback.format_exc())
        accounts_list = None; total_items = None
    finally:
        if cur: cur.close()
        if conn: conn.close()

    # Trả về tuple (list, total)
    return accounts_list, total_items

def get_pending_suggestion_interaction_count(min_history_id: int, status_filter: list = None) -> int | None:
    """
    Đếm số lượng bản ghi interaction_history thỏa mãn điều kiện để tạo đề xuất.

    Args:
        min_history_id: ID tối thiểu (chỉ đếm các bản ghi có ID lớn hơn giá trị này).
        status_filter: List các status cần đếm (ví dụ: ['success_ai']).

    Returns:
        Số lượng bản ghi (integer) hoặc None nếu có lỗi.
    """
    count = None
    conn = get_db_connection()
    if not conn: return None
    cur = None

    # --- Xây dựng mệnh đề WHERE động ---
    params = [min_history_id]
    where_clauses = ["history_id > %s", "sent_text IS NOT NULL", "received_text IS NOT NULL"]

    if status_filter:
        where_clauses.append("status = ANY(%s::varchar[])")
        params.append(status_filter)

    where_sql = " AND ".join(where_clauses)
    sql = f"SELECT COUNT(*) FROM interaction_history WHERE {where_sql};"

    try:
        cur = conn.cursor()
        print(f"DEBUG SQL (count_pending_interactions): {cur.mogrify(sql, tuple(params)).decode('utf-8')}")
        cur.execute(sql, tuple(params))
        count = cur.fetchone()[0]
        print(f"DEBUG: Found {count} pending interactions after ID {min_history_id} with status {status_filter}.")
    except psycopg2.Error as db_err:
        print(f"LỖI DB trong get_pending_suggestion_interaction_count: {db_err}")
        count = None # Lỗi thì trả về None
    except Exception as e:
        print(f"LỖI không xác định trong get_pending_suggestion_interaction_count: {e}")
        count = None
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return count

# ... (Các hàm khác) ...

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
            VALUES (%s, %s)
            ON CONFLICT (template_ref, variation_text) DO NOTHING; -- <<< THÊM DÒNG NÀY
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


def get_variation_details(variation_id: int) -> dict | None:
    """Lấy chi tiết một variation (bao gồm cả template_ref)."""
    if not variation_id: return None
    details = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        # Lấy cả template_ref để tiện redirect hoặc hiển thị
        sql = """
            SELECT variation_id, template_ref, variation_text
            FROM template_variations
            WHERE variation_id = %s;
        """
        cur.execute(sql, (variation_id,))
        row = cur.fetchone()
        if row: details = dict(row)
    except psycopg2.Error as e:
        print(f"LỖI (database.py - get_variation_details): Truy vấn thất bại: {e}")
    except Exception as e:
        print(f"LỖI (database.py - get_variation_details): Lỗi không xác định: {e}")
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return details

def update_variation(variation_id: int, variation_text: str) -> bool:
    """Cập nhật nội dung text của một variation."""
    if not variation_id or variation_text is None: # Variation text không nên null
         return False
    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        sql = """
            UPDATE template_variations SET variation_text = %s
            WHERE variation_id = %s;
        """
        params = (variation_text, variation_id)
        cur.execute(sql, params)
        conn.commit()
        success = cur.rowcount > 0
        if not success:
             print(f"WARNING (database.py - update_variation): Không tìm thấy variation_id {variation_id} để cập nhật.")
    except psycopg2.Error as e:
        print(f"LỖI (database.py - update_variation): UPDATE thất bại: {e}")
        if conn: conn.rollback()
        raise e # Ném lỗi lên
    except Exception as e:
        print(f"LỖI (database.py - update_variation): Lỗi không xác định: {e}")
        if conn: conn.rollback()
        raise e
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success


def get_strategy_details(strategy_id: str) -> dict | None:
    """Lấy chi tiết một chiến lược, bao gồm cả strategy_type và updated_at."""
    if not strategy_id: return None
    details = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        # <<< SỬA LẠI CÂU SELECT ĐỂ LẤY ĐỦ CÁC CỘT >>>
        sql = """
            SELECT strategy_id, name, description, initial_stage_id, strategy_type, updated_at
            FROM strategies WHERE strategy_id = %s;
            """
        # <<< Kết thúc sửa SELECT >>>
        print(f"DEBUG SQL (get_strategy_details): {cur.mogrify(sql, (strategy_id,)).decode('utf-8','ignore')}") # Debug SQL
        cur.execute(sql, (strategy_id,))
        row = cur.fetchone()
        if row:
            details = dict(row)
            print(f"DEBUG DB (get_strategy_details): Fetched details: {details}") # Debug kết quả
        else:
             print(f"WARN (db.get_strategy_details): Không tìm thấy strategy_id '{strategy_id}'.")

    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - get_strategy_details): Truy vấn thất bại: {db_err}")
        print(traceback.format_exc())
        details = None
    except Exception as e:
        print(f"LỖI (database.py - get_strategy_details): Lỗi không xác định: {e}")
        print(traceback.format_exc())
        details = None
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return details



def delete_strategy(strategy_id: str) -> tuple[bool, str | None]: # <<< Sửa kiểu trả về thành tuple
    """Xóa một chiến lược khỏi bảng strategies.
       Trả về tuple (success: bool, error_message: str | None).
    """
    if not strategy_id:
        return False, "Strategy ID là bắt buộc." # <<< Trả về tuple

    conn = get_db_connection()
    if not conn:
        return False, "Không thể kết nối CSDL." # <<< Trả về tuple

    cur = None
    success = False
    error_msg = None # <<< Khởi tạo error_msg
    try:
        cur = conn.cursor()
        print(f"DEBUG (database.py): Xóa strategy ID={strategy_id}")
        sql = "DELETE FROM strategies WHERE strategy_id = %s;"
        cur.execute(sql, (strategy_id,))
        conn.commit()
        success = cur.rowcount > 0 # True nếu có dòng bị xóa
        if not success:
             error_msg = f"Không tìm thấy strategy_id {strategy_id} để xóa." # <<< Gán lỗi nếu không tìm thấy
             print(f"WARNING (database.py - delete_strategy): {error_msg}")

    except psycopg2.Error as db_err:
        error_msg = f"Lỗi CSDL khi xóa strategy: {db_err}" # <<< Gán lỗi DB
        print(f"LỖI (database.py - delete_strategy): {error_msg}\n{traceback.format_exc()}")
        if conn: conn.rollback()
        success = False # Đảm bảo success là False khi có lỗi
    except Exception as e:
        error_msg = f"Lỗi không xác định khi xóa strategy: {e}" # <<< Gán lỗi chung
        print(f"LỖI (database.py - delete_strategy): {error_msg}\n{traceback.format_exc()}")
        if conn: conn.rollback()
        success = False # Đảm bảo success là False khi có lỗi
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return success, error_msg

def get_stages_for_strategy(strategy_id: str) -> list[dict] | None:
    """
    Lấy danh sách tất cả các stage thuộc về một strategy cụ thể.
    Bao gồm cả cột identifying_elements.

    Args:
        strategy_id: ID của chiến lược cần lấy stages.

    Returns:
        Một list các dictionary, mỗi dictionary chứa thông tin một stage,
        hoặc None nếu có lỗi, hoặc list rỗng nếu không có stage nào.
    """
    if not strategy_id:
        print("WARN (db.get_stages_for_strategy): strategy_id rỗng được cung cấp.")
        return [] # Trả về list rỗng nếu không có strategy_id

    stages_list = None
    conn = get_db_connection()
    if not conn:
        print("ERROR (db.get_stages_for_strategy): Không thể kết nối CSDL.")
        return None # Trả về None nếu lỗi kết nối

    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor) # Dùng DictCursor
        print(f"DEBUG (database.py): Truy vấn stages cho strategy_id='{strategy_id}'...")

        # <<< Câu lệnh SELECT lấy đủ các cột cần thiết >>>
        sql = """
            SELECT stage_id, strategy_id, description, stage_order, identifying_elements
            FROM public.strategy_stages
            WHERE strategy_id = %s
            ORDER BY stage_order, stage_id; -- Sắp xếp theo thứ tự và ID
        """
        cur.execute(sql, (strategy_id,))
        rows = cur.fetchall()

        # Chuyển kết quả thành list các dictionary
        stages_list = [dict(row) for row in rows] if rows else []
        print(f"DEBUG DB (get_stages_for_strategy): Found {len(stages_list)} stages for strategy {strategy_id}.")

    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - get_stages_for_strategy): Truy vấn thất bại cho strategy '{strategy_id}': {db_err}")
        print(traceback.format_exc())
        stages_list = None # Trả về None khi có lỗi CSDL
    except Exception as e:
        print(f"LỖI (database.py - get_stages_for_strategy): Lỗi không xác định cho strategy '{strategy_id}': {e}")
        print(traceback.format_exc())
        stages_list = None # Trả về None khi có lỗi khác
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
            # print(f"DEBUG (db.get_stages_for_strategy): Đã đóng kết nối DB cho strategy '{strategy_id}'.")

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
def add_new_stage(stage_id: str, strategy_id: str, description: str | None, stage_order: int = 0, identifying_elements_str: str | None = None) -> tuple[bool, str | None]:
    """Thêm một stage mới vào bảng strategy_stages.
       Trả về tuple (success: bool, error_message: str | None).
    """
    print(f"DEBUG (db.add_new_stage): Adding stage '{stage_id}' to strategy '{strategy_id}'")
    if not stage_id or not strategy_id:
        return False, "Stage ID và Strategy ID là bắt buộc."

    identifying_elements_json = None
    if identifying_elements_str and identifying_elements_str.strip():
        try:
            # Validate JSON và chuẩn hóa thành chuỗi JSON trước khi lưu
            identifying_elements_json = json.dumps(json.loads(identifying_elements_str))
        except json.JSONDecodeError:
            return False, "Identifying Elements không phải là JSON hợp lệ."

    conn = get_db_connection()
    if not conn:
        return False, "Không thể kết nối CSDL."
    cur = None
    success = False
    error_msg = None
    try:
        cur = conn.cursor()
        # Đảm bảo bảng strategy_stages có các cột này
        sql = """
            INSERT INTO public.strategy_stages
                (stage_id, strategy_id, description, stage_order, identifying_elements)
            VALUES (%s, %s, %s, %s, %s::jsonb);
        """
        params = (
            stage_id,
            strategy_id,
            description,
            stage_order,
            identifying_elements_json # Truyền chuỗi JSON hoặc None
        )
        cur.execute(sql, params)
        conn.commit()
        success = True
        print(f"INFO (db.add_new_stage): Thêm stage '{stage_id}' thành công.")

    except psycopg2.IntegrityError as int_err:
        error_msg = f"Lỗi ràng buộc CSDL (Stage ID '{stage_id}' đã tồn tại trong strategy này?): {int_err}"
        print(f"ERROR (db.add_new_stage): {error_msg}\n{traceback.format_exc()}")
        if conn: conn.rollback()
    except psycopg2.Error as db_err:
        error_msg = f"Lỗi CSDL khi thêm stage: {db_err}"
        print(f"ERROR (db.add_new_stage): {error_msg}\n{traceback.format_exc()}")
        if conn: conn.rollback()
    except Exception as e:
        error_msg = f"Lỗi không xác định khi thêm stage: {e}"
        print(f"ERROR (db.add_new_stage): {error_msg}\n{traceback.format_exc()}")
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()

    # <<< Trả về tuple (bool, str|None) >>>
    return success, error_msg

def get_stage_details(stage_id: str) -> dict | None:
    """
    Lấy chi tiết một stage từ bảng strategy_stages,
    bao gồm cả identifying_elements và strategy_id gốc.
    Tạo thêm key 'identifying_elements_str' để tiện hiển thị trên form.

    Args:
        stage_id: ID của stage cần lấy thông tin.

    Returns:
        Một dictionary chứa chi tiết stage nếu tìm thấy, hoặc None nếu không tìm thấy/lỗi.
    """
    if not stage_id:
        print("WARN (db.get_stage_details): Stage ID rỗng được cung cấp.")
        return None

    details = None
    conn = get_db_connection()
    if not conn:
        print("ERROR (db.get_stage_details): Không thể kết nối CSDL.")
        return None

    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor) # Dùng DictCursor để trả về dict

        # Lấy tất cả các cột cần thiết từ bảng strategy_stages
        sql = """
            SELECT stage_id, strategy_id, description, stage_order, identifying_elements
            FROM public.strategy_stages
            WHERE stage_id = %s;
        """
        print(f"DEBUG SQL (get_stage_details): {cur.mogrify(sql, (stage_id,)).decode('utf-8','ignore')}") # Debug SQL
        cur.execute(sql, (stage_id,))
        row = cur.fetchone()

        if row:
            details = dict(row) # Chuyển kết quả thành dict
            print(f"DEBUG DB (get_stage_details): Tìm thấy stage '{stage_id}': {details}")

            # Xử lý cột identifying_elements (kiểu JSONB trong DB)
            # để tạo chuỗi JSON format đẹp cho textarea trong form edit
            if details.get('identifying_elements') is not None:
                try:
                    # Format JSON với thụt lề, không dùng escape ký tự Unicode
                    details['identifying_elements_str'] = json.dumps(details['identifying_elements'], indent=2, ensure_ascii=False)
                except (TypeError, ValueError) as json_err:
                    # Fallback nếu dữ liệu JSONB trong DB bị lỗi hoặc không hợp lệ
                    print(f"WARN (db.get_stage_details): Lỗi format JSON cho identifying_elements của stage '{stage_id}': {json_err}")
                    details['identifying_elements_str'] = str(details['identifying_elements']) # Hiển thị dạng chuỗi thô
            else:
                 # Nếu identifying_elements là NULL trong DB, hiển thị chuỗi JSON rỗng '{}' trong form
                 details['identifying_elements_str'] = '{}'
        else:
            print(f"WARN (db.get_stage_details): Không tìm thấy stage_id '{stage_id}' trong CSDL.")
            # Trả về None nếu không tìm thấy

    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - get_stage_details): Truy vấn CSDL thất bại cho stage '{stage_id}': {db_err}")
        print(traceback.format_exc())
        details = None # Trả về None khi có lỗi CSDL
    except Exception as e:
        print(f"LỖI (database.py - get_stage_details): Lỗi không xác định cho stage '{stage_id}': {e}")
        print(traceback.format_exc())
        details = None # Trả về None khi có lỗi khác
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
            # print(f"DEBUG (db.get_stage_details): Đã đóng kết nối DB cho stage '{stage_id}'.")

    return details

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

def update_stage(stage_id: str, description: str | None, stage_order: int, identifying_elements_str: str | None = None) -> tuple[bool, str | None]:
    """
    Cập nhật description, order, và identifying_elements của stage.
    Trả về tuple (success: bool, error_message: str | None).
    """
    print(f"DEBUG (db.update_stage): Attempting to update stage '{stage_id}'")
    if not stage_id:
        return False, "Stage ID là bắt buộc."

    identifying_elements_json = None # Sẽ là None hoặc chuỗi JSON hợp lệ
    # Chỉ parse và chuẩn bị JSON nếu string được cung cấp và không rỗng/chỉ chứa '{}'
    if identifying_elements_str and identifying_elements_str.strip() and identifying_elements_str != '{}':
        try:
            # Validate và đảm bảo là chuỗi JSON để lưu vào DB
            identifying_elements_json = json.dumps(json.loads(identifying_elements_str))
        except json.JSONDecodeError:
            return False, "Identifying Elements không phải là JSON hợp lệ."
    # Nếu chuỗi rỗng, trống, hoặc '{}', sẽ lưu NULL vào DB
    elif identifying_elements_str is not None and (not identifying_elements_str.strip() or identifying_elements_str == '{}'):
         identifying_elements_json = None # Lưu NULL nếu người dùng xóa trắng hoặc nhập {}

    conn = get_db_connection()
    if not conn:
        return False, "Không thể kết nối CSDL."

    cur = None
    success = False
    error_msg = None
    try:
        cur = conn.cursor()
        # <<< Đảm bảo câu UPDATE đúng tên cột và có updated_at (nếu bảng có) >>>
        # Giả sử bảng strategy_stages không có updated_at riêng
        sql = """
            UPDATE public.strategy_stages
            SET description = %s, stage_order = %s, identifying_elements = %s::jsonb
            WHERE stage_id = %s;
        """
        params = (
            description,
            stage_order,
            identifying_elements_json, # Truyền chuỗi JSON hoặc None
            stage_id
        )
        print(f"DEBUG SQL (update_stage): {cur.mogrify(sql, params).decode('utf-8','ignore')}")
        cur.execute(sql, params)
        conn.commit()
        success = cur.rowcount > 0 # True nếu có ít nhất 1 dòng được cập nhật
        if not success:
             error_msg = f"Không tìm thấy stage_id '{stage_id}' để cập nhật hoặc không có gì thay đổi."
             print(f"WARNING (db.update_stage): {error_msg}")

    except psycopg2.Error as db_err:
        error_msg = f"Lỗi CSDL khi cập nhật stage: {db_err}"
        print(f"ERROR (db.update_stage): {error_msg}\n{traceback.format_exc()}")
        if conn: conn.rollback()
        success = False # Đảm bảo success là False khi lỗi
    except Exception as e:
        error_msg = f"Lỗi không xác định khi cập nhật stage: {e}"
        print(f"ERROR (db.update_stage): {error_msg}\n{traceback.format_exc()}")
        if conn: conn.rollback()
        success = False # Đảm bảo success là False khi lỗi
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

    return success, error_msg # <<< Trả về tuple >>>
# --- Transition Management Functions ---

# --- HÀM delete_transition ĐÚNG (TRẢ VỀ TUPLE) ---
def delete_transition(transition_id: int) -> tuple[bool, str | None]: # <<< KIỂM TRA KIỂU TRẢ VỀ
    """Xóa một transition khỏi stage_transitions.
       Trả về tuple (success: bool, error_message: str | None).
    """
    print(f"DEBUG (db.delete_transition): Attempting to delete transition ID={transition_id}")
    if not transition_id:
        return False, "Transition ID là bắt buộc." # <<< Trả về tuple

    conn = get_db_connection()
    if not conn:
        return False, "Không thể kết nối CSDL." # <<< Trả về tuple

    cur = None
    success = False
    error_msg = None # <<< Khởi tạo error_msg
    try:
        cur = conn.cursor()
        sql = "DELETE FROM public.stage_transitions WHERE transition_id = %s;"
        cur.execute(sql, (transition_id,))
        conn.commit()
        affected_rows = cur.rowcount
        success = affected_rows > 0
        if not success:
             error_msg = f"Không tìm thấy transition_id {transition_id} để xóa."
             print(f"WARNING (database.py - delete_transition): {error_msg}")
        else:
            print(f"INFO (db.delete_transition): Successfully deleted {affected_rows} row(s) for transition ID={transition_id}.")

    except psycopg2.Error as db_err:
        error_msg = f"Lỗi CSDL khi xóa transition: {db_err}"
        print(f"LỖI (database.py - delete_transition): {error_msg}\n{traceback.format_exc()}")
        if conn: conn.rollback()
        success = False
    except Exception as e:
        error_msg = f"Lỗi không xác định khi xóa transition: {e}"
        print(f"LỖI (database.py - delete_transition): {error_msg}\n{traceback.format_exc()}")
        if conn: conn.rollback()
        success = False
    finally:
        if cur: cur.close()
        if conn: conn.close()

    # <<< Trả về tuple (bool, str|None) >>>
    return success, error_msg



def get_interaction_history(page: int = 1, per_page: int = 30, filters: dict = None) -> tuple[list[dict] | None, dict | None]:
    """Lấy lịch sử tương tác với phân trang và bộ lọc (chưa dùng filters)."""
    logger = current_app.logger if current_app else print
    entries = None
    pagination_data = None
    total_items = 0
    conn = get_db_connection()
    if not conn: return None, None
    cur = None

    try:
        # Đếm tổng số dòng
        cur = conn.cursor()
        count_sql = "SELECT COUNT(*) FROM public.interaction_history;"
        cur.execute(count_sql)
        total_items = cur.fetchone()[0]
        cur.close()

        if total_items == 0:
            logger.debug("DEBUG (get_interaction_history): No entries found.")
            return [], {'page': page, 'per_page': per_page, 'total_items': 0, 'total_pages': 0}

        total_pages = (total_items + per_page - 1) // per_page
        offset = (page - 1) * per_page

        # Lấy dữ liệu cho trang hiện tại
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        # === SỬA CÂU SQL: Bỏ next_stage_id ===
        data_sql = """
            SELECT history_id, timestamp, account_id, strategy_id, stage_id, received_text,
                   sent_text, detected_user_intent, status
            FROM public.interaction_history
            ORDER BY timestamp DESC
            LIMIT %s OFFSET %s;
        """
        # ====================================
        logger.debug(f"DEBUG (get_interaction_history): Executing query for page {page}, limit {per_page}, offset {offset}")
        logger.debug(f"DEBUG (get_interaction_history): SQL: {cur.mogrify(data_sql, (per_page, offset)).decode('utf-8', 'ignore')}")
        cur.execute(data_sql, (per_page, offset))
        rows = cur.fetchall()
        logger.debug(f"DEBUG (get_interaction_history): Fetched {len(rows)} rows.")
        entries = [dict(row) for row in rows] if rows else []

        # Tạo thông tin phân trang
        pagination_data = {
            'page': page, 'per_page': per_page, 'total_items': total_items, 'total_pages': total_pages,
            'has_prev': page > 1, 'has_next': page < total_pages,
            'prev_num': page - 1 if page > 1 else None,
            'next_num': page + 1 if page < total_pages else None
        }
        logger.debug(f"DEBUG (get_interaction_history): Returning {len(entries)} entries.")
        logger.debug(f"DEBUG (get_interaction_history): Returning pagination: {pagination_data}")

    # ... (Phần except và finally giữ nguyên) ...
    except psycopg2.Error as db_err:
        logger.error(f"LỖI (get_interaction_history): Truy vấn thất bại: {db_err}", exc_info=True)
        entries, pagination_data = None, None
    except Exception as e:
        logger.error(f"LỖI (get_interaction_history): Lỗi không xác định: {e}", exc_info=True)
        entries, pagination_data = None, None
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return entries, pagination_data
# --- Rule Functions (simple_rules) ---



# === Cập nhật hàm này trong backup/app/database.py ===

def get_interactions_for_suggestion(min_timestamp, status_filter: list = None, limit: int = 100) -> list[dict] | None:
    """
    Lấy các bản ghi interaction_history phù hợp để tạo đề xuất,
    dựa trên thời gian tối thiểu và bộ lọc trạng thái.

    Args:
        min_timestamp: Thời gian sớm nhất để lấy (chỉ lấy các bản ghi mới hơn hoặc bằng thời gian này).
        status_filter: List các status cần lấy (ví dụ: ['success_ai']). Nếu None hoặc rỗng, không lọc theo status.
        limit: Số lượng bản ghi tối đa cần lấy.

    Returns:
        List các dictionary chứa thông tin interaction, hoặc None nếu lỗi.
    """
    interactions = None
    conn = get_db_connection()
    if not conn: return None
    cur = None

    # --- Xây dựng câu lệnh SQL động ---
    params = []
    where_clauses = ["timestamp >= %s", "sent_text IS NOT NULL", "received_text IS NOT NULL"] # Điều kiện cơ bản
    params.append(min_timestamp)

    if status_filter:
        # Sử dụng toán tử ANY của PostgreSQL để kiểm tra với list status
        where_clauses.append("status = ANY(%s::varchar[])") # Ép kiểu thành mảng varchar
        params.append(status_filter)
        # Lưu ý: Nếu dùng cách placeholder %s cho từng status thì cần tạo placeholder động

    # TODO: Thêm cơ chế đánh dấu hoặc lọc các interaction đã được xử lý để tránh lặp lại.
    # Ví dụ: Thêm một cột 'suggestion_processed BOOLEAN DEFAULT FALSE' vào interaction_history
    # và thêm "AND suggestion_processed = FALSE" vào where_clauses.
    # Hoặc lưu lại timestamp của lần xử lý cuối cùng và dùng "timestamp > last_processed_time".
    # Hiện tại, hàm này sẽ lấy lại các bản ghi cũ nếu min_timestamp không thay đổi.

    where_sql = " AND ".join(where_clauses)
    sql = f"""
        SELECT history_id, received_text, sent_text, detected_user_intent, stage_id, strategy_id
        FROM interaction_history
        WHERE {where_sql}
        ORDER BY timestamp ASC -- Xử lý các tương tác cũ trước
        LIMIT %s;
    """
    params.append(limit) # Thêm limit vào cuối params

    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        print(f"DEBUG SQL (get_interactions_for_suggestion): {cur.mogrify(sql, tuple(params)).decode('utf-8')}") # Log câu lệnh SQL đầy đủ với params
        # print(f"DEBUG PARAMS (get_interactions_for_suggestion): {params}") # Log params riêng nếu cần
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
        interactions = [dict(row) for row in rows] if rows else []
        print(f"DEBUG: Tìm thấy {len(interactions)} interactions để phân tích.")

    except psycopg2.Error as db_err:
        print(f"LỖI DB trong get_interactions_for_suggestion: {db_err}")
        print(traceback.format_exc())
        interactions = None # Trả về None khi lỗi
    except Exception as e:
        print(f"LỖI không xác định trong get_interactions_for_suggestion: {e}")
        print(traceback.format_exc())
        interactions = None
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return interactions

def add_suggestion(keywords: str | None, category: str | None, template_ref: str | None, template_text: str | None, source_examples: dict) -> bool:
    """Lưu một đề xuất mới vào bảng suggested_rules (đã thêm category, ref)."""
    # Chỉ cần ít nhất keywords hoặc template_text
    if not keywords and not template_text:
         print("WARNING (add_suggestion): Cần có ít nhất Keywords hoặc Template Text.")
         return False
    if source_examples is None: source_examples = {}

    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        import json # Đảm bảo json được import
        source_examples_json = json.dumps(source_examples)

        print(f"DEBUG (add_suggestion): Lưu đề xuất: keywords='{str(keywords)[:50]}...', category='{category}', ref='{template_ref}', template='{str(template_text)[:50]}...'")
        # <<< THÊM CỘT MỚI VÀO INSERT >>>
        sql = """
            INSERT INTO suggested_rules
            (suggested_keywords, suggested_template_text, source_examples, status, suggested_category, suggested_template_ref)
            VALUES (%s, %s, %s, %s, %s, %s);
        """
        params = (keywords, template_text, source_examples_json, 'pending', category, template_ref)
        cur.execute(sql, params)
        conn.commit()
        success = True
        print("DEBUG (add_suggestion): Lưu đề xuất thành công.")

    # ... (Except và Finally như cũ) ...
    except psycopg2.Error as db_err:
        print(f"LỖI DB trong add_suggestion: {db_err}")
        if conn: conn.rollback()
    except Exception as e:
        print(f"LỖI không xác định trong add_suggestion: {e}")
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success
# --- ReportReport (simple_rules) ---

def get_dashboard_stats() -> dict | None:

    """Lấy các số liệu thống kê tổng quan cho Dashboard."""
    stats = {}
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor() # Không cần DictCursor cho COUNT

        # Hàm helper để chạy COUNT và gán vào dict stats
        def _get_count(key_name, sql, params=None):
            try:
                cur.execute(sql, params or ())
                count = cur.fetchone()[0]
                stats[key_name] = count
            except Exception as e:
                print(f"Lỗi khi đếm '{key_name}': {e}")
                stats[key_name] = 'Lỗi' # Hoặc None, hoặc 0 tùy cách muốn hiển thị

        # Thực hiện các truy vấn COUNT
        _get_count('total_accounts', "SELECT COUNT(*) FROM accounts;")
        _get_count('active_accounts', "SELECT COUNT(*) FROM accounts WHERE status = 'active';")
        _get_count('total_strategies', "SELECT COUNT(*) FROM strategies;")
        _get_count('total_stages', "SELECT COUNT(*) FROM strategy_stages;")
        _get_count('total_transitions', "SELECT COUNT(*) FROM stage_transitions;")
        _get_count('total_rules', "SELECT COUNT(*) FROM simple_rules;")
        _get_count('total_templates', "SELECT COUNT(*) FROM response_templates;")
        _get_count('total_variations', "SELECT COUNT(*) FROM template_variations;")
        _get_count('pending_suggestions', "SELECT COUNT(*) FROM suggested_rules WHERE status = 'pending';")

        # Đếm tương tác trong 24 giờ qua
        time_24h_ago = datetime.now() - timedelta(hours=24)
        _get_count('interactions_24h',
                   "SELECT COUNT(*) FROM interaction_history WHERE timestamp >= %s;",
                   (time_24h_ago,))

        # Đếm lỗi trong 24 giờ qua (ví dụ status bắt đầu bằng 'error_')
        _get_count('errors_24h',
                   "SELECT COUNT(*) FROM interaction_history WHERE status LIKE 'error%%' AND timestamp >= %s;",
                   (time_24h_ago,))

    except psycopg2.Error as db_err:
        print(f"LỖI DB trong get_dashboard_stats: {db_err}")
        return None # Trả về None nếu có lỗi kết nối hoặc lỗi DB nghiêm trọng ban đầu
    except Exception as e:
        print(f"LỖI không xác định trong get_dashboard_stats: {e}")
        return None
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return stats

# --- AI promptprompt ---

def get_prompt_template_by_task(task_type: str) -> str | None:
    
    """Lấy nội dung template_content từ prompt_templates dựa trên task_type.
       Ưu tiên lấy bản ghi mới nhất nếu có nhiều bản ghi cùng task_type (mặc dù name là unique).
    """
    if not task_type: return None
    template_content = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor() # Chỉ cần lấy 1 cột
        # Lấy template_content của bản ghi phù hợp (có thể thêm ORDER BY created_at DESC nếu cần chọn mới nhất)
        sql = """
            SELECT template_content
            FROM prompt_templates
            WHERE task_type = %s
            ORDER BY prompt_template_id DESC -- Ưu tiên ID lớn nhất (mới nhất) nếu có trùng task_type
            LIMIT 1;
        """
        cur.execute(sql, (task_type,))
        row = cur.fetchone()
        if row:
            template_content = row[0]
        else:
             print(f"WARNING (get_prompt_template_by_task): Không tìm thấy prompt template cho task_type='{task_type}'.")

    except psycopg2.Error as db_err:
        print(f"LỖI DB trong get_prompt_template_by_task: {db_err}")
    except Exception as e:
        print(f"LỖI không xác định trong get_prompt_template_by_task: {e}")
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return template_content

# === Thêm các hàm này vào backup/app/database.py ===

def get_task_state(task_name: str) -> int | None:
    """Lấy ID bản ghi cuối cùng đã xử lý cho một tác vụ."""
    last_id = None # Trả về None nếu lỗi hoặc không tìm thấy
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor()
        sql = "SELECT last_processed_id FROM task_state WHERE task_name = %s;"
        cur.execute(sql, (task_name,))
        row = cur.fetchone()
        if row:
            last_id = row[0]
        else:
            # Nếu chưa có trạng thái cho task này, trả về 0 để bắt đầu từ đầu
            last_id = 0
            print(f"INFO (get_task_state): Không tìm thấy trạng thái cho task '{task_name}', bắt đầu từ ID 0.")
    except psycopg2.Error as db_err:
        print(f"LỖI DB trong get_task_state cho '{task_name}': {db_err}")
    except Exception as e:
        print(f"LỖI không xác định trong get_task_state cho '{task_name}': {e}")
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return last_id if last_id is not None else 0 # Đảm bảo trả về số nguyên >= 0

def update_task_state(task_name: str, last_processed_id: int) -> bool:
    """Cập nhật ID bản ghi cuối cùng đã xử lý cho một tác vụ (UPSERT)."""
    if not task_name or last_processed_id is None: return False
    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        now = datetime.now()
        # Sử dụng INSERT ... ON CONFLICT (UPSERT) để chèn nếu chưa có, cập nhật nếu đã có
        sql = """
            INSERT INTO task_state (task_name, last_processed_id, last_run_timestamp)
            VALUES (%s, %s, %s)
            ON CONFLICT (task_name) DO UPDATE SET
                last_processed_id = EXCLUDED.last_processed_id,
                last_run_timestamp = EXCLUDED.last_run_timestamp;
        """
        params = (task_name, last_processed_id, now)
        cur.execute(sql, params)
        conn.commit()
        success = True
    except psycopg2.Error as db_err:
        print(f"LỖI DB trong update_task_state cho '{task_name}': {db_err}")
        if conn: conn.rollback()
    except Exception as e:
        print(f"LỖI không xác định trong update_task_state cho '{task_name}': {e}")
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success

# --- Sửa lại hàm get_interactions_for_suggestion ---

def get_interactions_for_suggestion(min_history_id: int, status_filter: list = None, limit: int = 100) -> list[dict] | None:
    """
    Lấy các bản ghi interaction_history phù hợp để tạo đề xuất,
    dựa trên history_id tối thiểu và bộ lọc trạng thái.

    Args:
        min_history_id: ID tối thiểu (chỉ lấy các bản ghi có ID lớn hơn giá trị này).
        status_filter: List các status cần lấy (ví dụ: ['success_ai']).
        limit: Số lượng bản ghi tối đa cần lấy.

    Returns:
        List các dictionary chứa thông tin interaction, hoặc None nếu lỗi.
    """
    interactions = None
    conn = get_db_connection()
    if not conn: return None
    cur = None

    # --- Xây dựng câu lệnh SQL động ---
    params = [min_history_id] # Tham số đầu tiên cho history_id
    where_clauses = ["history_id > %s", "sent_text IS NOT NULL", "received_text IS NOT NULL"] # Điều kiện cơ bản

    if status_filter:
        where_clauses.append("status = ANY(%s::varchar[])")
        params.append(status_filter) # Thêm status_filter vào params

    # TODO: Vẫn có thể thêm cột 'suggestion_processed' để tăng độ tin cậy
    # if use_processed_flag: where_clauses.append("suggestion_processed = FALSE")

    where_sql = " AND ".join(where_clauses)
    sql = f"""
        SELECT history_id, received_text, sent_text, detected_user_intent, stage_id, strategy_id
        FROM interaction_history
        WHERE {where_sql}
        ORDER BY history_id ASC -- Xử lý theo thứ tự ID tăng dần
        LIMIT %s;
    """
    params.append(limit) # Thêm limit vào cuối params

    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        # cur.mogrify có thể không hoạt động tốt với ANY(%s::varchar[]) nên log riêng
        print(f"DEBUG SQL (get_interactions_for_suggestion): {sql}")
        print(f"DEBUG PARAMS (get_interactions_for_suggestion): {params}")
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
        interactions = [dict(row) for row in rows] if rows else []
        print(f"DEBUG: Tìm thấy {len(interactions)} interactions mới để phân tích (sau ID {min_history_id}).")

    except psycopg2.Error as db_err:
        print(f"LỖI DB trong get_interactions_for_suggestion: {db_err}")
        print(traceback.format_exc())
        interactions = None
    except Exception as e:
        print(f"LỖI không xác định trong get_interactions_for_suggestion: {e}")
        print(traceback.format_exc())
        interactions = None
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return interactions

# --- AI Persona CRUD Functions ---
def get_all_personas(page: int = 1, per_page: int = 30) -> tuple[list[dict] | None, int | None]:
    """
    Lấy danh sách tất cả các AI personas với phân trang.

    Args:
        page: Số trang hiện tại.
        per_page: Số lượng mục mỗi trang.

    Returns:
        Tuple: (list các persona của trang hiện tại hoặc None nếu lỗi,
                tổng số persona hoặc None nếu lỗi)
    """
    personas = None
    total_items = None
    conn = get_db_connection()
    if not conn: return None, None
    cur = None
    try:
        # Query đếm tổng số personas
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM public.ai_personas;")
        total_items = cur.fetchone()[0]
        cur.close()

        # Query lấy dữ liệu cho trang hiện tại
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        offset = (page - 1) * per_page
        # Lấy các cột cần thiết cho bảng danh sách
        sql = """
            SELECT persona_id, name, description, model_name
            FROM ai_personas
            ORDER BY name ASC -- Sắp xếp theo tên
            LIMIT %s OFFSET %s;
        """
        cur.execute(sql, (per_page, offset))
        rows = cur.fetchall()
        personas = [dict(row) for row in rows] if rows else []
        print(f"DEBUG (database.py - get_all_personas): Fetched {len(personas)} personas for page {page}.")

    except psycopg2.Error as e:
        print(f"LỖI khi lấy danh sách personas: {e}")
        personas = None; total_items = None
    except Exception as e:
        print(f"LỖI không xác định khi lấy personas: {e}")
        personas = None; total_items = None
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return personas, total_items

def get_persona_details(persona_id: str) -> dict | None:
    """Lấy chi tiết một AI persona bằng ID."""
    if not persona_id: return None
    details = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("""
            SELECT persona_id, name, description, base_prompt, model_name, generation_config
            FROM ai_personas WHERE persona_id = %s;
            """, (persona_id,))
        row = cur.fetchone()
        if row:
            details = dict(row)
            # Chuyển đổi generation_config từ dict/None sang chuỗi JSON để hiển thị trong textarea nếu cần
            if details.get('generation_config') is not None:
                 try:
                      details['generation_config_str'] = json.dumps(details['generation_config'], indent=2)
                 except TypeError:
                      details['generation_config_str'] = str(details['generation_config']) # Fallback nếu không phải JSON hợp lệ
            else:
                 details['generation_config_str'] = ''
    except Exception as e:
        print(f"LỖI khi lấy chi tiết persona {persona_id}: {e}")
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return details

def add_new_persona(persona_id: str, name: str, description: str | None, base_prompt: str,
                    model_name: str | None, generation_config_str: str | None) -> bool:
    """Thêm một AI persona mới."""
    if not persona_id or not name or not base_prompt:
        print("WARNING (add_new_persona): persona_id, name, base_prompt là bắt buộc.")
        return False

    # Xử lý generation_config từ chuỗi JSON
    gen_config = None
    if generation_config_str:
        try:
            gen_config = json.loads(generation_config_str) # Chuyển chuỗi JSON thành dict Python
        except json.JSONDecodeError:
            print("WARNING (add_new_persona): generation_config không phải là JSON hợp lệ. Sẽ lưu là NULL.")
            # Hoặc có thể báo lỗi và không cho lưu tùy yêu cầu

    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        sql = """
            INSERT INTO ai_personas (persona_id, name, description, base_prompt, model_name, generation_config, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s);
        """
        # generation_config có thể là None nếu json.loads thất bại hoặc chuỗi rỗng
        params = (persona_id, name, description, base_prompt, model_name if model_name else None,
                  json.dumps(gen_config) if gen_config else None, # Lưu lại dạng JSON string hoặc NULL
                  datetime.now())
        cur.execute(sql, params)
        conn.commit()
        success = True
    except psycopg2.IntegrityError as e:
        print(f"LỖI (add_new_persona): Lỗi ràng buộc CSDL (ID hoặc Name đã tồn tại?): {e}")
        if conn: conn.rollback()
    except psycopg2.Error as e:
        print(f"LỖI (add_new_persona): INSERT thất bại: {e}")
        if conn: conn.rollback()
    except Exception as e:
        print(f"LỖI (add_new_persona): Lỗi không xác định: {e}")
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success

def update_persona(persona_id: str, name: str, description: str | None, base_prompt: str,
                   model_name: str | None, generation_config_str: str | None) -> bool:
    """Cập nhật một AI persona."""
    if not persona_id or not name or not base_prompt:
        print("WARNING (update_persona): persona_id, name, base_prompt là bắt buộc.")
        return False

    # Xử lý generation_config từ chuỗi JSON
    gen_config = None
    if generation_config_str:
        try:
            gen_config = json.loads(generation_config_str)
        except json.JSONDecodeError:
            print("WARNING (update_persona): generation_config không phải là JSON hợp lệ. Sẽ lưu là NULL.")

    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        sql = """
            UPDATE ai_personas
            SET name = %s, description = %s, base_prompt = %s, model_name = %s, generation_config = %s, updated_at = %s
            WHERE persona_id = %s;
        """
        params = (name, description, base_prompt, model_name if model_name else None,
                  json.dumps(gen_config) if gen_config else None, # Lưu lại dạng JSON string hoặc NULL
                  datetime.now(), persona_id)
        cur.execute(sql, params)
        conn.commit()
        success = cur.rowcount > 0 # True nếu có ít nhất 1 dòng được cập nhật
    except psycopg2.IntegrityError as e:
        print(f"LỖI (update_persona): Lỗi ràng buộc CSDL (Name đã tồn tại?): {e}")
        if conn: conn.rollback()
    except psycopg2.Error as e:
        print(f"LỖI (update_persona): UPDATE thất bại: {e}")
        if conn: conn.rollback()
    except Exception as e:
        print(f"LỖI (update_persona): Lỗi không xác định: {e}")
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success

def delete_persona(persona_id: str) -> bool:
    """Xóa một AI persona.
       Lưu ý: Cột default_persona_id trong accounts sẽ tự động thành NULL do FK constraint.
    """
    if not persona_id: return False
    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        sql = "DELETE FROM ai_personas WHERE persona_id = %s;"
        cur.execute(sql, (persona_id,))
        conn.commit()
        success = cur.rowcount > 0
    except psycopg2.Error as e: # Bắt lỗi DB chung
        print(f"LỖI DB khi xóa persona {persona_id}: {e}")
        if conn: conn.rollback()
        # Không cần raise lại nếu muốn route chỉ báo lỗi chung
    except Exception as e:
        print(f"LỖI không xác định khi xóa persona {persona_id}: {e}")
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success

# --- Prompt Template CRUD Functions ---

def get_all_prompt_templates(page: int = 1, per_page: int = 30) -> tuple[list[dict] | None, int | None]:
    """
    Lấy danh sách tất cả các prompt templates với phân trang.

    Args:
        page: Số trang hiện tại.
        per_page: Số lượng mục mỗi trang.

    Returns:
        Tuple: (list các template của trang hiện tại hoặc None nếu lỗi,
                tổng số template hoặc None nếu lỗi)
    """
    templates = None
    total_items = None
    conn = get_db_connection()
    if not conn: return None, None
    cur = None
    try:
        # Query đếm tổng số prompt templates
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM public.prompt_templates;")
        total_items = cur.fetchone()[0]
        cur.close()

        # Query lấy dữ liệu cho trang hiện tại
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        offset = (page - 1) * per_page
        # Lấy các cột cần thiết cho bảng danh sách
        sql = """
            SELECT prompt_template_id, name, task_type, updated_at
            FROM prompt_templates
            ORDER BY name ASC -- Sắp xếp theo tên
            LIMIT %s OFFSET %s;
        """
        cur.execute(sql, (per_page, offset))
        rows = cur.fetchall()
        templates = [dict(row) for row in rows] if rows else []
        print(f"DEBUG (database.py - get_all_prompt_templates): Fetched {len(templates)} prompt templates for page {page}.")

    except psycopg2.Error as e:
        print(f"LỖI khi lấy danh sách prompt templates: {e}")
        templates = None; total_items = None
    except Exception as e:
        print(f"LỖI không xác định khi lấy prompt templates: {e}")
        templates = None; total_items = None
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return templates, total_items

def get_prompt_template_details(prompt_template_id: int) -> dict | None:
    """Lấy chi tiết một prompt template bằng ID."""
    if not prompt_template_id: return None
    details = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("""
            SELECT prompt_template_id, name, task_type, template_content
            FROM prompt_templates WHERE prompt_template_id = %s;
            """, (prompt_template_id,))
        row = cur.fetchone()
        if row: details = dict(row)
    except Exception as e:
        print(f"LỖI khi lấy chi tiết prompt template {prompt_template_id}: {e}")
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return details

def add_new_prompt_template(name: str, task_type: str, template_content: str) -> bool:
    """Thêm một prompt template mới."""
    if not name or not task_type or not template_content:
        print("WARNING (add_new_prompt_template): name, task_type, template_content là bắt buộc.")
        return False
    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        sql = """
            INSERT INTO prompt_templates (name, task_type, template_content, updated_at)
            VALUES (%s, %s, %s, %s);
        """
        params = (name, task_type, template_content, datetime.now())
        cur.execute(sql, params)
        conn.commit()
        success = True
    except psycopg2.IntegrityError as e:
        print(f"LỖI (add_new_prompt_template): Lỗi ràng buộc CSDL (Name đã tồn tại?): {e}")
        if conn: conn.rollback()
    except psycopg2.Error as e:
        print(f"LỖI (add_new_prompt_template): INSERT thất bại: {e}")
        if conn: conn.rollback()
    except Exception as e:
        print(f"LỖI (add_new_prompt_template): Lỗi không xác định: {e}")
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success

def update_prompt_template(prompt_template_id: int, name: str, task_type: str, template_content: str) -> bool:
    """Cập nhật một prompt template."""
    if not prompt_template_id or not name or not task_type or not template_content:
        print("WARNING (update_prompt_template): id, name, task_type, template_content là bắt buộc.")
        return False
    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        sql = """
            UPDATE prompt_templates
            SET name = %s, task_type = %s, template_content = %s, updated_at = %s
            WHERE prompt_template_id = %s;
        """
        params = (name, task_type, template_content, datetime.now(), prompt_template_id)
        cur.execute(sql, params)
        conn.commit()
        success = cur.rowcount > 0
    except psycopg2.IntegrityError as e:
        print(f"LỖI (update_prompt_template): Lỗi ràng buộc CSDL (Name đã tồn tại?): {e}")
        if conn: conn.rollback()
    except psycopg2.Error as e:
        print(f"LỖI (update_prompt_template): UPDATE thất bại: {e}")
        if conn: conn.rollback()
    except Exception as e:
        print(f"LỖI (update_prompt_template): Lỗi không xác định: {e}")
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success

def delete_prompt_template(prompt_template_id: int) -> bool:

    """Xóa một prompt template."""
    if not prompt_template_id: return False
    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        sql = "DELETE FROM prompt_templates WHERE prompt_template_id = %s;"
        cur.execute(sql, (prompt_template_id,))
        conn.commit()
        success = cur.rowcount > 0
    except psycopg2.Error as e: # Hiện tại không có FK rõ ràng trỏ đến bảng này
        print(f"LỖI DB khi xóa prompt template {prompt_template_id}: {e}")
        if conn: conn.rollback()
    except Exception as e:
        print(f"LỖI không xác định khi xóa prompt template {prompt_template_id}: {e}")
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success

# --- Scheduled Job CRUD Functions ---

def get_all_job_configs() -> list[dict] | None:
    """Lấy cấu hình của tất cả các scheduled jobs từ DB."""
    logger = current_app.logger if current_app else print # Lấy logger
    jobs = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        # Lấy các cột cần thiết để hiển thị và quản lý
        # Đảm bảo tên bảng và cột là chính xác theo schema của bạn
        sql = """
            SELECT job_id, job_function_path, trigger_type, trigger_args, is_enabled, description, updated_at
            FROM public.scheduled_jobs ORDER BY job_id;
        """
        cur.execute(sql)
        rows = cur.fetchall()
        jobs = [dict(row) for row in rows] if rows else []
        logger.debug(f"DEBUG (db.get_all_job_configs): Fetched {len(jobs)} job configs from DB.") # Thêm log debug

    except psycopg2.Error as e_db: # Bắt lỗi DB cụ thể
        logger.error(f"LỖI DB khi lấy danh sách job configs: {e_db}", exc_info=True)
        jobs = None # Trả về None nếu lỗi DB
    except Exception as e:
        logger.error(f"LỖI không xác định khi lấy job configs: {e}", exc_info=True)
        jobs = None # Trả về None nếu lỗi khác
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return jobs

def get_job_config_details(job_id: str) -> dict | None:
    """Lấy chi tiết cấu hình một job bằng job_id, bao gồm job_args."""
    if not job_id: return None
    details = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        # === SỬA SQL: Thêm cột job_args ===
        cur.execute("""
            SELECT job_id, job_function_path, trigger_type, trigger_args, job_args, is_enabled, description
            FROM public.scheduled_jobs WHERE job_id = %s;
            """, (job_id,))
        # ================================
        row = cur.fetchone()
        if row:
            details = dict(row)
            # Chuyển đổi trigger_args JSON -> chuỗi (giữ nguyên)
            if details.get('trigger_args') is not None:
                 try: details['trigger_args_str'] = json.dumps(details['trigger_args'], indent=2)
                 except: details['trigger_args_str'] = str(details['trigger_args'])
            else: details['trigger_args_str'] = '{}'

            # === THÊM: Chuyển đổi job_args JSON -> chuỗi ===
            if details.get('job_args') is not None:
                try: details['job_args_str'] = json.dumps(details['job_args'], indent=2)
                except: details['job_args_str'] = str(details['job_args'])
            else: details['job_args_str'] = '{}' # Mặc định object rỗng nếu là NULL
            # =============================================
    # ... (Phần except và finally giữ nguyên) ...
    except Exception as e:
        print(f"LỖI khi lấy chi tiết job config {job_id}: {e}")
        details = None # <<< Thêm trả về None khi lỗi
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return details

def add_job_config(job_id: str, function_path: str, trigger_type: str, trigger_args_str: str,
                   is_enabled: bool, description: str | None,
                   job_args_str: str | None = None) -> tuple[bool, str | None]: # <<< Thêm job_args_str
    """Thêm cấu hình job mới vào DB, bao gồm cả job_args. Trả về (success, error_message)."""
    logger = current_app.logger if current_app else print
    if not job_id or not function_path or not trigger_type or not trigger_args_str:
        return False, "Job ID, Function Path, Trigger Type, và Trigger Args là bắt buộc."

    # Validate trigger_args (giữ nguyên)
    trigger_args_json = None
    try:
        # ... (code validate trigger_args_str như cũ) ...
        trigger_args_dict = json.loads(trigger_args_str)
        if not isinstance(trigger_args_dict, dict): raise ValueError("Trigger Args phải là JSON object.")
        trigger_args_json = json.dumps(trigger_args_dict)
    except (json.JSONDecodeError, ValueError) as ve:
         return False, f"Trigger Args không hợp lệ: {ve}"


    # === THÊM: Validate job_args ===
    job_args_json = None
    if job_args_str and job_args_str.strip() and job_args_str.strip() != '{}':
        try:
            job_args_dict = json.loads(job_args_str)
            if not isinstance(job_args_dict, dict):
                raise ValueError("Job Args phải là một JSON object.")
            job_args_json = json.dumps(job_args_dict) # Lưu dạng JSON chuẩn
        except (json.JSONDecodeError, ValueError) as ve:
             return False, f"Job Args không hợp lệ: {ve}"
    # ==============================

    conn = get_db_connection()
    if not conn: return False, "Không thể kết nối CSDL."
    cur = None
    success = False
    error_msg = None
    try:
        cur = conn.cursor()
        # === SỬA SQL: Thêm cột job_args ===
        sql = """
            INSERT INTO public.scheduled_jobs
                (job_id, job_function_path, trigger_type, trigger_args, job_args, is_enabled, description, updated_at)
            VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s); -- <<< Thêm job_args và ép kiểu
        """
        params = (job_id, function_path, trigger_type, trigger_args_json,
                  job_args_json, # <<< Thêm giá trị job_args (có thể là None)
                  is_enabled, description, datetime.now(timezone.utc)) # <<< Đảm bảo timezone UTC
        # =================================
        cur.execute(sql, params)
        conn.commit()
        success = True
    except psycopg2.IntegrityError:
        error_msg = f"Job ID '{job_id}' đã tồn tại."
        if conn: conn.rollback()
    except psycopg2.Error as e:
        error_msg = f"Lỗi CSDL khi thêm job: {e}"
        logger.error(f"ERROR adding job {job_id}: {error_msg}", exc_info=True)
        if conn: conn.rollback()
    except Exception as e:
        error_msg = f"Lỗi không xác định khi thêm job: {e}"
        logger.error(f"ERROR adding job {job_id}: {error_msg}", exc_info=True)
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success, error_msg

def update_job_config(job_id: str, trigger_type: str, trigger_args_str: str,
                      is_enabled: bool, description: str | None,
                      job_args_str: str | None = None) -> tuple[bool, str | None]: # <<< Thêm job_args_str
    """Cập nhật cấu hình một job trong DB, bao gồm job_args. Trả về (success, error_message)."""
    logger = current_app.logger if current_app else print
    if not job_id or not trigger_type or not trigger_args_str:
         return False, "Job ID, Trigger Type, và Trigger Args là bắt buộc."

    # Validate trigger_args (giữ nguyên)
    trigger_args_json = None
    try:
         # ... (code validate trigger_args_str như cũ) ...
        trigger_args_dict = json.loads(trigger_args_str)
        if not isinstance(trigger_args_dict, dict): raise ValueError("Trigger Args phải là JSON object.")
        trigger_args_json = json.dumps(trigger_args_dict)
    except (json.JSONDecodeError, ValueError) as ve:
         return False, f"Trigger Args không hợp lệ: {ve}"

    # === THÊM: Validate job_args ===
    job_args_json = None
    if job_args_str and job_args_str.strip() and job_args_str.strip() != '{}':
        try:
            job_args_dict = json.loads(job_args_str)
            if not isinstance(job_args_dict, dict):
                raise ValueError("Job Args phải là một JSON object.")
            job_args_json = json.dumps(job_args_dict)
        except (json.JSONDecodeError, ValueError) as ve:
             return False, f"Job Args không hợp lệ: {ve}"
    # ==============================

    conn = get_db_connection()
    if not conn: return False, "Không thể kết nối CSDL."
    cur = None
    success = False
    error_msg = None
    try:
        cur = conn.cursor()
        # === SỬA SQL: Thêm cột job_args vào SET ===
        sql = """
            UPDATE public.scheduled_jobs
            SET trigger_type = %s, trigger_args = %s::jsonb, job_args = %s::jsonb, is_enabled = %s, description = %s, updated_at = %s
            WHERE job_id = %s;
        """
        params = (trigger_type, trigger_args_json,
                  job_args_json, # <<< Thêm job_args
                  is_enabled, description, datetime.now(timezone.utc), job_id)
        # ========================================
        cur.execute(sql, params)
        conn.commit()
        success = cur.rowcount > 0
        if not success:
             error_msg = f"Không tìm thấy Job ID '{job_id}' để cập nhật."
    except psycopg2.Error as e:
        error_msg = f"Lỗi CSDL khi cập nhật job: {e}"
        logger.error(f"ERROR updating job {job_id}: {error_msg}", exc_info=True)
        if conn: conn.rollback()
    except Exception as e:
        error_msg = f"Lỗi không xác định khi cập nhật job: {e}"
        logger.error(f"ERROR updating job {job_id}: {error_msg}", exc_info=True)
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success, error_msg

def delete_job_config(job_id: str) -> tuple[bool, str | None]:
    """Xóa cấu hình một job khỏi DB. Trả về (success, error_message)."""
    if not job_id: return False, "Job ID là bắt buộc."
    conn = get_db_connection()
    if not conn: return False, "Không thể kết nối CSDL."
    cur = None
    success = False
    error_msg = None
    try:
        cur = conn.cursor()
        sql = "DELETE FROM scheduled_jobs WHERE job_id = %s;"
        cur.execute(sql, (job_id,))
        conn.commit()
        success = cur.rowcount > 0
        if not success:
             error_msg = f"Không tìm thấy Job ID '{job_id}' để xóa."
    except psycopg2.Error as e:
        error_msg = f"Lỗi CSDL khi xóa job: {e}"
        if conn: conn.rollback()
    except Exception as e:
        error_msg = f"Lỗi không xác định khi xóa job: {e}"
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success, error_msg

# --- Hàm cập nhật trạng thái bật/tắt nhanh ---
def update_job_enabled_status(job_id: str, is_enabled: bool) -> tuple[bool, str | None]:

    """Cập nhật trạng thái is_enabled cho một job trong DB."""
    if not job_id: return False, "Job ID là bắt buộc."
    conn = get_db_connection()
    if not conn: return False, "Không thể kết nối CSDL."
    cur = None
    success = False
    error_msg = None
    try:
        cur = conn.cursor()
        sql = "UPDATE scheduled_jobs SET is_enabled = %s, updated_at = %s WHERE job_id = %s;"
        params = (is_enabled, datetime.now(), job_id)
        cur.execute(sql, params)
        conn.commit()
        success = cur.rowcount > 0
        if not success:
            error_msg = f"Không tìm thấy Job ID '{job_id}' để cập nhật trạng thái."
    except psycopg2.Error as e:
        error_msg = f"Lỗi CSDL khi cập nhật trạng thái job: {e}"
        if conn: conn.rollback()
    except Exception as e:
        error_msg = f"Lỗi không xác định khi cập nhật trạng thái job: {e}"
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success, error_msg

# app/database.py
# ... (các import hiện có: psycopg2, extras, datetime, os, traceback, json, ...) ...

# --- AI Simulation Config Functions ---

def add_simulation_config(config_name: str, description: str | None,
                          persona_a_id: str, persona_b_id: str,
                          log_account_id_a: str, log_account_id_b: str,
                          strategy_id: str, max_turns: int,
                          starting_prompt: str | None, simulation_goal: str | None,
                          is_enabled: bool = True) -> tuple[bool, str | None]: # <<< Trả về Tuple
    """Thêm một cấu hình mô phỏng mới vào CSDL."""
    # === Lấy logger ===
    logger = current_app.logger if current_app else print

    if not all([config_name, persona_a_id, persona_b_id, log_account_id_a, log_account_id_b, strategy_id]):
        logger.error("ERROR (db - add_simulation_config): Missing required parameters.")
        return False, "Thiếu tham số bắt buộc." # <<< Trả về lỗi

    conn = get_db_connection()
    if not conn: return False, "Không thể kết nối CSDL." # <<< Trả về lỗi
    cur = None
    success = False
    error_msg = None # <<< Khởi tạo error_msg

    try:
        cur = conn.cursor()
        sql = """
            INSERT INTO public.ai_simulation_configs (
                config_name, description, persona_a_id, persona_b_id,
                log_account_id_a, log_account_id_b, strategy_id, max_turns,
                starting_prompt, simulation_goal, is_enabled, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW());
        """
        params = (
            config_name, description, persona_a_id, persona_b_id,
            log_account_id_a, log_account_id_b, strategy_id, max_turns,
            starting_prompt, simulation_goal, is_enabled
        )
        cur.execute(sql, params)
        conn.commit()
        success = True
        logger.info(f"DEBUG (db): Added simulation config '{config_name}'.") # Dùng logger.info hoặc debug
    except psycopg2.IntegrityError as e:
        # === SỬA LẠI: Dùng logger ===
        error_msg = f"Integrity Error (name exists or FK violation?): {e}"
        logger.error(f"ERROR (db - add_simulation_config): {error_msg}", exc_info=True) # Thêm exc_info
        if conn: conn.rollback()
    except psycopg2.Error as e:
        # === SỬA LẠI: Dùng logger ===
        error_msg = f"DB Error: {e}"
        logger.error(f"ERROR (db - add_simulation_config): {error_msg}", exc_info=True) # Thêm exc_info
        if conn: conn.rollback()
    except Exception as e:
        # === SỬA LẠI: Dùng logger ===
        error_msg = f"Unexpected error: {e}"
        logger.error(f"ERROR (db - add_simulation_config): {error_msg}", exc_info=True) # Thêm exc_info
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    # <<< Trả về tuple (success, error_msg) >>>
    return success, error_msg

def get_all_simulation_configs(page: int = 1, per_page: int = 20) -> tuple[list[dict] | None, int | None]:
    """
    Lấy danh sách tất cả các cấu hình mô phỏng đã lưu với phân trang.

    Args:
        page: Số trang hiện tại.
        per_page: Số lượng mục mỗi trang.

    Returns:
        Tuple: (list các config của trang hiện tại hoặc None nếu lỗi,
                tổng số config hoặc None nếu lỗi)
    """
    configs = None
    total_items = None
    conn = get_db_connection()
    if not conn: return None, None
    cur = None
    try:
        # Query đếm tổng số cấu hình
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM public.ai_simulation_configs;")
        total_items = cur.fetchone()[0]
        cur.close()

        # Query lấy dữ liệu cho trang hiện tại
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        offset = (page - 1) * per_page
        # Lấy các cột cần thiết cho bảng danh sách
        sql = """
            SELECT config_id, config_name, description, persona_a_id, persona_b_id,
                   strategy_id, max_turns, simulation_goal, is_enabled
            FROM public.ai_simulation_configs
            ORDER BY config_name ASC -- Sắp xếp theo tên cấu hình
            LIMIT %s OFFSET %s;
        """
        cur.execute(sql, (per_page, offset))
        rows = cur.fetchall()
        configs = [dict(row) for row in rows] if rows else []
        print(f"DEBUG (db - get_all_simulation_configs): Fetched {len(configs)} configs for page {page}.")

    except psycopg2.Error as e:
        print(f"LỖI khi lấy danh sách sim configs: {e}")
        configs = None; total_items = None
    except Exception as e:
        print(f"LỖI không xác định khi lấy sim configs: {e}")
        configs = None; total_items = None
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return configs, total_items


def get_simulation_config(config_id: int) -> dict | None:
    """Lấy chi tiết một cấu hình mô phỏng bằng config_id."""
    if not config_id: return None
    config_details = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        # Lấy tất cả các cột để điền form sửa
        sql = "SELECT * FROM public.ai_simulation_configs WHERE config_id = %s;"
        cur.execute(sql, (config_id,))
        row = cur.fetchone()
        if row:
            config_details = dict(row)
    except psycopg2.Error as e:
        print(f"ERROR (db - get_simulation_config): DB Error for ID {config_id}: {e}")
    except Exception as e:
        print(f"ERROR (db - get_simulation_config): Unexpected error for ID {config_id}: {e}")
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return config_details

def update_simulation_config(config_id: int, config_name: str, description: str | None,
                             persona_a_id: str, persona_b_id: str,
                             log_account_id_a: str, log_account_id_b: str,
                             strategy_id: str, max_turns: int,
                             starting_prompt: str | None, simulation_goal: str | None,
                             is_enabled: bool) -> tuple[bool, str | None]: # <<< SỬA: Đổi kiểu trả về thành tuple
    """Cập nhật một cấu hình mô phỏng đã có."""
    # === Lấy logger ===
    logger = current_app.logger if current_app else print

    if not all([config_id, config_name, persona_a_id, persona_b_id, log_account_id_a, log_account_id_b, strategy_id]):
        logger.error("ERROR (db - update_simulation_config): Missing required parameters.")
        return False, "Thiếu tham số bắt buộc." # <<< Trả về tuple

    conn = get_db_connection()
    if not conn: return False, "Không thể kết nối CSDL." # <<< Trả về tuple
    cur = None
    success = False
    error_msg = None # <<< Khởi tạo error_msg

    try:
        cur = conn.cursor()
        sql = """
            UPDATE public.ai_simulation_configs SET
                config_name = %s, description = %s, persona_a_id = %s, persona_b_id = %s,
                log_account_id_a = %s, log_account_id_b = %s, strategy_id = %s, max_turns = %s,
                starting_prompt = %s, simulation_goal = %s, is_enabled = %s, updated_at = NOW()
            WHERE config_id = %s;
        """
        params = (
            config_name, description, persona_a_id, persona_b_id,
            log_account_id_a, log_account_id_b, strategy_id, max_turns,
            starting_prompt, simulation_goal, is_enabled,
            config_id
        )
        cur.execute(sql, params)
        conn.commit()
        success = cur.rowcount > 0
        if success:
             logger.info(f"DEBUG (db): Updated simulation config ID {config_id}.") # <<< Sửa thành logger.info/debug
        else:
             error_msg = f"Config ID {config_id} not found or no changes made." # <<< Gán lỗi nếu không update được
             logger.warning(f"WARN (db - update_simulation_config): {error_msg}")

    except psycopg2.IntegrityError as e:
        # === SỬA LẠI: Dùng logger và gán error_msg ===
        error_msg = f"Integrity Error for ID {config_id}: {e}"
        logger.error(f"ERROR (db - update_simulation_config): {error_msg}", exc_info=True)
        if conn: conn.rollback()
        success = False # <<< Đảm bảo success là False
    except psycopg2.Error as e:
        # === SỬA LẠI: Dùng logger và gán error_msg ===
        error_msg = f"DB Error for ID {config_id}: {e}"
        logger.error(f"ERROR (db - update_simulation_config): {error_msg}", exc_info=True)
        if conn: conn.rollback()
        success = False # <<< Đảm bảo success là False
    except Exception as e:
        # === SỬA LẠI: Dùng logger và gán error_msg ===
        error_msg = f"Unexpected error for ID {config_id}: {e}"
        logger.error(f"ERROR (db - update_simulation_config): {error_msg}", exc_info=True)
        if conn: conn.rollback()
        success = False # <<< Đảm bảo success là False
    finally:
        if cur: cur.close()
        if conn: conn.close()

    # === SỬA LẠI: Trả về tuple (success, error_msg) ===
    return success, error_msg

def update_simulation_config_enabled(config_id: int, new_enabled_state: bool) -> tuple[bool, str | None]:
    """Chỉ cập nhật trạng thái is_enabled của một simulation config."""
    logger = current_app.logger if current_app else print
    if config_id is None: # ID là số nguyên
        return False, "Config ID là bắt buộc."

    conn = get_db_connection()
    if not conn: return False, "Không thể kết nối CSDL."
    cur = None
    success = False
    error_msg = None
    try:
        cur = conn.cursor()
        sql = """
            UPDATE public.ai_simulation_configs
            SET is_enabled = %s, updated_at = NOW()
            WHERE config_id = %s;
        """
        params = (new_enabled_state, config_id)
        cur.execute(sql, params)
        conn.commit()
        success = cur.rowcount > 0 # True nếu có dòng được cập nhật
        if not success:
            error_msg = f"Không tìm thấy Config ID {config_id} để cập nhật trạng thái."
            logger.warning(f"WARN (db - update_simulation_config_enabled): {error_msg}")
        else:
            logger.info(f"INFO (db): Toggled is_enabled to {new_enabled_state} for config ID {config_id}.")

    except psycopg2.Error as e:
        error_msg = f"Lỗi CSDL: {e}"
        logger.error(f"ERROR (db - update_simulation_config_enabled): {error_msg}", exc_info=True)
        if conn: conn.rollback()
    except Exception as e:
        error_msg = f"Lỗi không xác định: {e}"
        logger.error(f"ERROR (db - update_simulation_config_enabled): {error_msg}", exc_info=True)
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return success, error_msg

def delete_simulation_config(config_id: int) -> bool:
    """Xóa một cấu hình mô phỏng khỏi CSDL."""
    if not config_id: return False
    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        sql = "DELETE FROM public.ai_simulation_configs WHERE config_id = %s;"
        cur.execute(sql, (config_id,))
        conn.commit()
        success = cur.rowcount > 0 # True nếu có dòng bị xóa
        if success:
            print(f"DEBUG (db): Deleted simulation config ID {config_id}.")
        else:
            print(f"WARN (db - delete_simulation_config): Config ID {config_id} not found for deletion.")
    except psycopg2.Error as e: # Bắt lỗi DB chung (FK ít khả năng vì chưa có bảng nào trỏ tới nó)
        print(f"ERROR (db - delete_simulation_config): DB Error for ID {config_id}: {e}")
        if conn: conn.rollback()
    except Exception as e:
        print(f"ERROR (db - delete_simulation_config): Unexpected error for ID {config_id}: {e}")
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success

# ... (Các hàm database khác) ...

# --- Scheduler Command Functions ---

def add_scheduler_command(command_type: str, payload: dict) -> int | None:
    """Thêm một lệnh mới vào hàng đợi của scheduler."""
    command_id = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor()
        # Chuyển dict payload thành chuỗi JSON để lưu vào cột JSONB
        payload_json = json.dumps(payload)
        sql = """
            INSERT INTO public.scheduler_commands (command_type, payload, status)
            VALUES (%s, %s, 'pending')
            RETURNING command_id;
        """
        cur.execute(sql, (command_type, payload_json))
        result = cur.fetchone()
        if result:
            command_id = result[0]
        conn.commit()
        print(f"DEBUG (db): Added scheduler command type '{command_type}' with ID {command_id}")
    except psycopg2.Error as db_err:
        print(f"ERROR (db - add_scheduler_command): INSERT failed: {db_err}")
        if conn: conn.rollback()
    except Exception as e:
        print(f"ERROR (db - add_scheduler_command): Unexpected error: {e}")
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return command_id

def get_pending_commands(command_type: str, limit: int = 10) -> list[dict] | None:
    """Lấy danh sách các lệnh đang chờ xử lý (pending)."""
    commands = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor) # Dùng DictCursor
        sql = """
            SELECT command_id, command_type, payload, created_at
            FROM public.scheduler_commands
            WHERE status = 'pending' AND command_type = %s
            ORDER BY created_at ASC -- Xử lý lệnh cũ trước
            LIMIT %s
            FOR UPDATE SKIP LOCKED; -- Để tránh nhiều worker lấy cùng lệnh (nếu chạy nhiều instance scheduler)
        """
        cur.execute(sql, (command_type, limit))
        rows = cur.fetchall()
        commands = [dict(row) for row in rows] if rows else []
        # Không commit ở đây vì có FOR UPDATE
    except psycopg2.Error as db_err:
        print(f"ERROR (db - get_pending_commands): SELECT failed: {db_err}")
        # Không rollback vì chỉ là SELECT
    except Exception as e:
        print(f"ERROR (db - get_pending_commands): Unexpected error: {e}")
    finally:
        # QUAN TRỌNG: Connection sẽ được đóng bởi hàm gọi (trong _process_pending_commands) sau khi cập nhật status
        if cur: cur.close()
        # if conn: conn.close() # <<< KHÔNG ĐÓNG CONNECTION Ở ĐÂY
    return commands

def update_command_status(conn, command_id: int, status: str, error_message: str | None = None) -> bool:
    """Cập nhật trạng thái của một lệnh (Dùng lại connection đã có)."""
    # Lưu ý: Hàm này nhận connection làm tham số để chạy trong cùng transaction với get_pending_commands
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        sql = """
            UPDATE public.scheduler_commands
            SET status = %s, processed_at = CURRENT_TIMESTAMP, error_message = %s
            WHERE command_id = %s;
        """
        cur.execute(sql, (status, error_message, command_id))
        # Commit sẽ được thực hiện bởi hàm gọi (_process_pending_commands)
        success = cur.rowcount > 0
    except psycopg2.Error as db_err:
        print(f"ERROR (db - update_command_status): UPDATE failed for command {command_id}: {db_err}")
        # Rollback sẽ do hàm gọi xử lý
    except Exception as e:
        print(f"ERROR (db - update_command_status): Unexpected error for command {command_id}: {e}")
    finally:
        if cur: cur.close()
        # Không đóng connection ở đây
    return success

def get_recent_simulation_commands(
        status_list: list[str] = None, # Giữ nguyên để có thể lọc nếu cần sau
        command_type: str = 'run_simulation', # Thêm command_type
        limit: int = 25 # Tăng limit lên một chút
    ) -> list[dict] | None:
    """Lấy các lệnh chạy mô phỏng gần đây theo trạng thái và loại."""
    # Mặc định lấy các trạng thái này nếu không có status_list được truyền vào
    if status_list is None:
        status_list = ['pending', 'processing', 'error', 'done']

    commands = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        sql = """
            SELECT command_id, command_type, payload, status, created_at, processed_at, error_message
            FROM public.scheduler_commands
            WHERE command_type = %s AND status = ANY(%s::varchar[]) -- Lọc theo cả type và status
            ORDER BY created_at DESC -- Luôn lấy mới nhất trước
            LIMIT %s;
        """
        # FOR UPDATE SKIP LOCKED không cần thiết nếu chỉ lấy các trạng thái cuối cùng
        cur.execute(sql, (command_type, status_list, limit))
        rows = cur.fetchall()
        commands = [dict(row) for row in rows] if rows else []
        for cmd in commands: # Parse payload
            try:
                if isinstance(cmd.get('payload'), str):
                    cmd['payload'] = json.loads(cmd['payload'])
            except: cmd['payload'] = {} # Gán rỗng nếu lỗi

    except Exception as e: print(f"ERROR (db - get_recent_commands): {e}"); commands = None
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return commands

def delete_scheduler_command(command_id: int) -> bool:
    """Xóa một lệnh cụ thể khỏi bảng scheduler_commands."""
    if not command_id: return False
    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        sql = "DELETE FROM public.scheduler_commands WHERE command_id = %s;"
        cur.execute(sql, (command_id,))
        conn.commit()
        success = cur.rowcount > 0 # True nếu có dòng bị xóa
        if success:
            print(f"DEBUG (db): Deleted scheduler command ID {command_id}.")
        else:
            print(f"WARN (db - delete_scheduler_command): Command ID {command_id} not found for deletion.")
    except psycopg2.Error as e:
        print(f"ERROR (db - delete_scheduler_command): DB Error for ID {command_id}: {e}")
        if conn: conn.rollback()
    except Exception as e:
        print(f"ERROR (db - delete_scheduler_command): Unexpected error for ID {command_id}: {e}")
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success

def delete_completed_or_errored_commands(command_type: str) -> tuple[bool, int | None, str | None]:
    """Xóa tất cả các lệnh có trạng thái 'done' hoặc 'error' cho một loại lệnh cụ thể.

    Returns:
        Tuple: (success: bool, deleted_count: int | None, error_message: str | None)
    """
    if not command_type:
        return False, None, "Command type cannot be empty."

    conn = get_db_connection()
    if not conn:
        return False, None, "Cannot connect to database."

    cur = None
    success = False
    deleted_count = 0
    error_msg = None
    try:
        cur = conn.cursor()
        sql = """
            DELETE FROM public.scheduler_commands
            WHERE command_type = %s AND status IN ('done', 'error');
        """
        cur.execute(sql, (command_type,))
        deleted_count = cur.rowcount # Số dòng đã bị xóa
        conn.commit()
        success = True
        print(f"DEBUG (db): Deleted {deleted_count} completed/errored '{command_type}' commands.")
    except psycopg2.Error as e:
        error_msg = f"DB Error: {e}"
        print(f"ERROR (db - delete_completed_or_errored_commands): {error_msg}")
        if conn: conn.rollback()
    except Exception as e:
        error_msg = f"Unexpected error: {e}"
        print(f"ERROR (db - delete_completed_or_errored_commands): {error_msg}")
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success, deleted_count, error_msg

def get_filtered_templates_with_details(
        filter_ref: str | None = None,
        filter_category: str | None = None,
        page: int = 1,
        per_page: int = 30
    ) -> tuple[list[dict] | None, int | None]:
    """Lấy danh sách template refs đã lọc với details, variation count, và hỗ trợ phân trang."""
    templates_data = None
    total_items = None
    conn = get_db_connection()
    if not conn: return None, None
    cur = None

    # --- Xây dựng WHERE và params (giữ nguyên) ---
    where_clauses = []
    params = []
    if filter_ref:
        where_clauses.append("t.template_ref ILIKE %s") # <<< SỬA alias thành t
        params.append(f"%{filter_ref}%")
    if filter_category:
        where_clauses.append("t.category = %s") # <<< SỬA alias thành t
        params.append(filter_category)
    where_sql = ""
    if where_clauses:
        where_sql = " WHERE " + " AND ".join(where_clauses)

    try:
        # --- Query 1: Đếm tổng số mục khớp bộ lọc ---
        cur = conn.cursor()
        # === SỬA TÊN BẢNG Ở ĐÂY ===
        count_sql = f"""
            SELECT COUNT(*) FROM public.templates t {where_sql};
        """
        # =========================
        print(f"DEBUG SQL (count_templates): {cur.mogrify(count_sql, tuple(params)).decode('utf-8', 'ignore')}")
        cur.execute(count_sql, tuple(params))
        total_items = cur.fetchone()[0]
        cur.close()

        # --- Query 2: Lấy dữ liệu cho trang hiện tại ---
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        offset = (page - 1) * per_page
        # === SỬA TÊN BẢNG Ở ĐÂY ===
        data_sql = f"""
            SELECT
                t.template_ref, t.description, t.category,
                COUNT(tv.variation_id) AS variation_count
            FROM public.templates t          -- <<< SỬA Ở ĐÂY
            LEFT JOIN public.template_variations tv ON t.template_ref = tv.template_ref
            {where_sql}
            GROUP BY t.template_ref, t.description, t.category
            ORDER BY t.template_ref
            LIMIT %s OFFSET %s;
        """
        # =========================
        data_params = params + [per_page, offset]
        print(f"DEBUG SQL (get_templates_page): {cur.mogrify(data_sql, tuple(data_params)).decode('utf-8', 'ignore')}")
        cur.execute(data_sql, tuple(data_params))
        rows = cur.fetchall()
        templates_data = [dict(row) for row in rows] if rows else []
        print(f"DEBUG (get_filtered_templates): Fetched {len(templates_data)} templates for page {page}.")

    # ... (Phần except và finally giữ nguyên) ...
    except psycopg2.Error as db_err:
        print(f"LỖI (db - get_filtered_templates): Truy vấn thất bại: {db_err}")
        templates_data = None; total_items = None
    except Exception as e:
        print(f"LỖI (db - get_filtered_templates): Lỗi không xác định: {e}")
        templates_data = None; total_items = None
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return templates_data, total_items
# Có thể bạn cần sửa cả hàm get_all_template_refs_with_details nếu còn dùng
# Hoặc bỏ nó đi và chỉ dùng hàm filter mới
def get_all_template_refs_with_details() -> list[dict] | None:
    """Lấy danh sách template refs cùng mô tả, category và số lượng variations."""
    templates_data = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        print("DEBUG (database.py): Truy vấn templates với details và variation count...")
        # === SỬA TÊN BẢNG Ở ĐÂY ===
        sql = """
            SELECT
                t.template_ref,         -- <<< Dùng alias t
                t.description,
                t.category,
                COUNT(tv.variation_id) AS variation_count
            FROM public.templates t     -- <<< SỬA Ở ĐÂY
            LEFT JOIN public.template_variations tv ON t.template_ref = tv.template_ref
            GROUP BY t.template_ref, t.description, t.category
            ORDER BY t.template_ref;
        """
        # =========================
        cur.execute(sql)
        rows = cur.fetchall()
        if rows:
            templates_data = [dict(row) for row in rows]
        else:
            templates_data = []
    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - get_all_template_refs_with_details): Truy vấn thất bại: {db_err}")
        templates_data = None # <<< Thêm trả về None khi lỗi
    except Exception as e:
        print(f"LỖI (database.py - get_all_template_refs_with_details): Lỗi không xác định: {e}")
        templates_data = None # <<< Thêm trả về None khi lỗi
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
        # === SỬA TÊN BẢNG Ở ĐÂY ===
        cur.execute("""
            SELECT template_ref, description, category
            FROM public.templates         -- <<< SỬA Ở ĐÂY
            WHERE template_ref = %s;
            """, (template_ref,))
        # =========================
        row = cur.fetchone()
        if row:
            details = dict(row)
        else:
            print(f"WARNING (database.py): Không tìm thấy template_ref '{template_ref}'.")
    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - get_template_ref_details): Truy vấn thất bại: {db_err}")
        details = None # <<< Thêm trả về None khi lỗi
    except Exception as e:
        print(f"LỖI (database.py - get_template_ref_details): Lỗi không xác định: {e}")
        details = None # <<< Thêm trả về None khi lỗi
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return details

def update_template_details(template_ref: str, description: str | None, category: str | None) -> bool:
    """Cập nhật description và category cho một template_ref."""
    if not template_ref: return False
    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        # === SỬA TÊN BẢNG Ở ĐÂY ===
        sql = """
            UPDATE public.templates SET description = %s, category = %s -- <<< SỬA Ở ĐÂY
            WHERE template_ref = %s;
        """
        # =========================
        params = (description, category, template_ref)
        cur.execute(sql, params)
        conn.commit()
        success = cur.rowcount > 0
    # ... (Phần except và finally giữ nguyên) ...
    except psycopg2.Error as e:
        print(f"LỖI (database.py - update_template_details): UPDATE thất bại: {e}")
        if conn: conn.rollback()
    except Exception as e:
        print(f"LỖI (database.py - update_template_details): Lỗi không xác định: {e}")
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success

def get_distinct_template_categories() -> list[str] | None:
    """Lấy danh sách các category duy nhất đã tồn tại trong bảng templates."""
    categories_list = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor()
        print("DEBUG (database.py): Truy vấn các template categories duy nhất...")
        # === SỬA TÊN BẢNG Ở ĐÂY ===
        cur.execute("""
            SELECT DISTINCT category
            FROM public.templates             -- <<< SỬA Ở ĐÂY
            WHERE category IS NOT NULL AND category <> ''
            ORDER BY category;
            """)
        # =========================
        rows = cur.fetchall()
        if rows:
            categories_list = [row[0] for row in rows]
        else:
            categories_list = []
    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - get_distinct_template_categories): Truy vấn thất bại: {db_err}")
        categories_list = None # <<< Thêm trả về None khi lỗi
    except Exception as e:
        print(f"LỖI (database.py - get_distinct_template_categories): Lỗi không xác định: {e}")
        categories_list = None # <<< Thêm trả về None khi lỗi
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return categories_list

# Hàm get_filtered_templates_with_details đã được sửa ở phản hồi trước, đảm bảo bạn dùng bản đó.

# Hàm get_all_template_refs (Nếu còn dùng)
def get_all_template_refs() -> list[dict] | None:
    """Lấy danh sách tất cả các template_ref."""
    refs_list = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        print("DEBUG (database.py): Truy vấn tất cả template refs...")
        # === SỬA TÊN BẢNG Ở ĐÂY ===
        cur.execute("SELECT template_ref FROM public.templates ORDER BY template_ref;") 
        # =========================
        rows = cur.fetchall()
        if rows:
            refs_list = [dict(row) for row in rows]
        else:
            refs_list = []
    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - get_all_template_refs): Truy vấn thất bại: {db_err}")
        refs_list = None
    except Exception as e:
        print(f"LỖI (database.py - get_all_template_refs): Lỗi không xác định: {e}")
        refs_list = None
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return refs_list

# Hàm delete_template_ref (Nếu còn dùng, cần đảm bảo đúng tên bảng)
def delete_template_ref(template_ref: str) -> bool:
    """Xóa một template_ref khỏi templates."""
    if not template_ref: return False
    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        print(f"DEBUG (database.py): Xóa template_ref='{template_ref}'...")
        # === SỬA TÊN BẢNG Ở ĐÂY ===
        sql = "DELETE FROM public.templates WHERE template_ref = %s;" # <<< SỬA Ở ĐÂY
        # =========================
        cur.execute(sql, (template_ref,))
        conn.commit()
        success = cur.rowcount > 0
        if not success:
            print(f"WARNING (database.py - delete_template_ref): Không tìm thấy template_ref '{template_ref}' để xóa.")
    # ... (Phần except và finally giữ nguyên) ...
    except psycopg2.Error as db_err:
         print(f"LỖI (database.py - delete_template_ref): DELETE thất bại: {db_err}")
         if conn: conn.rollback()
         raise db_err
    except Exception as e:
        print(f"LỖI (database.py - delete_template_ref): Lỗi không xác định: {e}")
        if conn: conn.rollback()
        raise e
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success




def get_command_details(command_id: int) -> dict | None:
    """Lấy chi tiết một command bằng ID."""
    if not command_id: return None
    details = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        sql = """
            SELECT command_id, command_type, payload, status, created_at, processed_at, error_message
            FROM public.scheduler_commands WHERE command_id = %s;
        """
        cur.execute(sql, (command_id,))
        row = cur.fetchone()
        if row:
            details = dict(row)
            # Parse payload luôn nếu nó là string
            if isinstance(details.get('payload'), str):
                try: details['payload'] = json.loads(details['payload'])
                except: details['payload'] = {}
            elif not isinstance(details.get('payload'), dict):
                 details['payload'] = {} # Đảm bảo payload là dict hoặc rỗng

    except psycopg2.Error as e:
        print(f"ERROR (db - get_command_details): DB Error for ID {command_id}: {e}")
    except Exception as e:
        print(f"ERROR (db - get_command_details): Unexpected error for ID {command_id}: {e}")
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return details

def get_simulation_conversation(thread_id_pattern: str) -> list[dict] | None:
    """Lấy các lượt hội thoại từ interaction_history dựa vào thread_id pattern."""
    if not thread_id_pattern: return None
    conversation = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        # Lấy các cột cần thiết để hiển thị log chat
        sql = """
            SELECT history_id, timestamp, account_id, received_text, sent_text, status, stage_id
            FROM public.interaction_history
            WHERE thread_id LIKE %s -- Dùng LIKE để khớp pattern
            ORDER BY timestamp ASC; -- Sắp xếp theo thời gian tăng dần
        """
        # Pattern thường là 'sim_thread_base_%'
        params = (thread_id_pattern,)
        cur.execute(sql, params)
        rows = cur.fetchall()
        conversation = [dict(row) for row in rows] if rows else []
    except psycopg2.Error as e:
        print(f"ERROR (db - get_simulation_conversation): DB Error for pattern {thread_id_pattern}: {e}")
        conversation = None
    except Exception as e:
        print(f"ERROR (db - get_simulation_conversation): Unexpected error for pattern {thread_id_pattern}: {e}")
        conversation = None
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return conversation

# Sửa lại hàm get_all_rules để gọi hàm lọc mới (hoặc bỏ hẳn get_all_rules)
# --- Macro Definition Functions ---

def add_macro_definition(macro_code: str, description: str | None, app_target: str | None, params_schema_str: str | None, notes: str | None) -> tuple[bool, str | None]:
    """Thêm định nghĩa macro mới vào DB. Trả về (success, error_message)."""
    if not macro_code: return False, "Macro Code là bắt buộc."
    params_schema_json = None
    if params_schema_str and params_schema_str.strip():
        try:
            # Validate JSON trước khi lưu
            params_schema_json = json.dumps(json.loads(params_schema_str))
        except json.JSONDecodeError:
            return False, "Params Schema không phải là JSON hợp lệ."

    conn = get_db_connection()
    if not conn: return False, "Không thể kết nối CSDL."
    cur = None
    success = False
    error_msg = None
    try:
        cur = conn.cursor()
        sql = """
            INSERT INTO public.macro_definitions
                (macro_code, description, app_target, params_schema, notes, created_at, updated_at)
            VALUES (%s, %s, %s, %s::jsonb, %s, NOW(), NOW());
        """
        # Chuyển app_target rỗng thành 'system' hoặc None tùy logic
        app_target_db = app_target if app_target and app_target.strip() else 'system'
        params = (macro_code, description, app_target_db, params_schema_json, notes)
        cur.execute(sql, params)
        conn.commit()
        success = True
    except psycopg2.IntegrityError:
        error_msg = f"Macro Code '{macro_code}' đã tồn tại."
        if conn: conn.rollback()
    except psycopg2.Error as e:
        error_msg = f"Lỗi CSDL: {e}"
        if conn: conn.rollback()
    except Exception as e:
        error_msg = f"Lỗi không xác định: {e}"
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success, error_msg

def get_macro_definition(macro_code: str) -> dict | None:
    """Lấy chi tiết một định nghĩa macro."""
    if not macro_code: return None
    details = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        sql = """
            SELECT macro_code, description, app_target, params_schema, notes, created_at, updated_at
            FROM public.macro_definitions WHERE macro_code = %s;
        """
        cur.execute(sql, (macro_code,))
        row = cur.fetchone()
        if row:
            details = dict(row)
            # Chuyển schema dict thành chuỗi JSON format đẹp để hiển thị trong form
            if details.get('params_schema') is not None:
                try: details['params_schema_str'] = json.dumps(details['params_schema'], indent=2, ensure_ascii=False)
                except: details['params_schema_str'] = str(details['params_schema'])
            else: details['params_schema_str'] = '' # Hoặc '{}' nếu muốn default là object rỗng
    except Exception as e: print(f"ERROR (db - get_macro_definition) Code {macro_code}: {e}")
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return details

def get_all_macro_definitions( # Tham số filters và phân trang đã thêm ở bước trước
    filters: dict = None,
    page: int = 1,
    per_page: int = 30 # PER_PAGE_MACROS đã định nghĩa ở admin_routes
    ) -> tuple[list[dict] | None, int | None]:
    """
    Lấy danh sách định nghĩa macro đã lọc và phân trang.
    Trả về: (list các macro của trang, tổng số macro khớp filter)
    """
    macros_list = None
    total_items = None
    conn = get_db_connection()
    if not conn: return None, None
    cur = None

    # --- Xây dựng mệnh đề WHERE và params cho filter ---
    where_clauses = []
    params = []
    if filters:
        if filters.get('macro_code'):
            where_clauses.append("macro_code ILIKE %s")
            params.append(f"%{filters['macro_code']}%")
        if filters.get('description'):
            where_clauses.append("description ILIKE %s")
            params.append(f"%{filters['description']}%")
        if filters.get('app_target'):
            app_filter = filters['app_target']
            if app_filter != '__all__': # '__all__' nghĩa là không lọc theo target
                 targets_to_filter = [app_filter]
                 # Bao gồm cả system/generic khi lọc theo app cụ thể
                 if app_filter not in ['system', 'generic', '', None]:
                     targets_to_filter.extend(['system', 'generic'])

                 target_conditions = []
                 valid_targets_in_params = []
                 for target in targets_to_filter:
                     if target is None: target_conditions.append("app_target IS NULL")
                     elif target == '': target_conditions.append("app_target = ''")
                     else:
                          target_conditions.append("app_target = %s")
                          valid_targets_in_params.append(target)
                 if target_conditions:
                     where_clauses.append(f"({ ' OR '.join(target_conditions) })")
                     params.extend(valid_targets_in_params)

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    try:
        # --- Query 1: Đếm tổng số ---
        cur = conn.cursor()
        count_sql = f"SELECT COUNT(*) FROM public.macro_definitions {where_sql};"
        # print(f"DEBUG Count SQL (macros): {cur.mogrify(count_sql, tuple(params)).decode('utf-8', 'ignore')}")
        cur.execute(count_sql, tuple(params))
        total_items = cur.fetchone()[0]
        cur.close()

        # --- Query 2: Lấy dữ liệu trang ---
        macros_list = []
        if total_items > 0:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            offset = (page - 1) * per_page
            # <<< Đảm bảo SELECT có cột app_target >>>
            data_sql = f"""
                SELECT macro_code, description, app_target, notes
                FROM public.macro_definitions
                {where_sql}
                ORDER BY app_target, macro_code
                LIMIT %s OFFSET %s;
            """
            data_params = params + [per_page, offset]
            # print(f"DEBUG Data SQL (macros): {cur.mogrify(data_sql, tuple(data_params)).decode('utf-8', 'ignore')}")
            cur.execute(data_sql, tuple(data_params))
            rows = cur.fetchall()
            macros_list = [dict(row) for row in rows] if rows else []
            # print(f"DEBUG (get_all_macros): Fetched {len(macros_list)} macros for page {page}.")

    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - get_all_macro_definitions): Truy vấn thất bại: {db_err}")
        traceback.print_exc()
        macros_list = None; total_items = None
    except Exception as e:
        print(f"LỖI (database.py - get_all_macro_definitions): Lỗi không xác định: {e}")
        traceback.print_exc()
        macros_list = None; total_items = None
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return macros_list, total_items

def update_macro_definition(macro_code: str, description: str | None, app_target: str | None, params_schema_str: str | None, notes: str | None) -> tuple[bool, str | None]:
    """Cập nhật định nghĩa macro. Trả về (success, error_message)."""
    if not macro_code: return False, "Macro Code là bắt buộc."
    params_schema_json = None
    # Chỉ parse và lưu nếu params_schema_str được cung cấp và không rỗng
    if params_schema_str and params_schema_str.strip():
        try:
            params_schema_json = json.dumps(json.loads(params_schema_str))
        except json.JSONDecodeError:
            return False, "Params Schema không phải là JSON hợp lệ."
    # Nếu params_schema_str rỗng hoặc chỉ chứa khoảng trắng, ta muốn lưu NULL vào DB
    elif params_schema_str is not None and not params_schema_str.strip():
         params_schema_json = None # Lưu NULL nếu người dùng xóa trắng textarea

    conn = get_db_connection()
    if not conn: return False, "Không thể kết nối CSDL."
    cur = None
    success = False
    error_msg = None
    try:
        cur = conn.cursor()
        sql = """
            UPDATE public.macro_definitions SET
                description = %s, app_target = %s, params_schema = %s::jsonb, notes = %s, updated_at = NOW()
            WHERE macro_code = %s;
        """
        app_target_db = app_target if app_target and app_target.strip() else 'system'
        params = (description, app_target_db, params_schema_json, notes, macro_code)
        cur.execute(sql, params)
        conn.commit()
        success = cur.rowcount > 0
        if not success:
            error_msg = f"Không tìm thấy Macro Code '{macro_code}' để cập nhật."
    except psycopg2.Error as e:
        error_msg = f"Lỗi CSDL: {e}"
        if conn: conn.rollback()
    except Exception as e:
        error_msg = f"Lỗi không xác định: {e}"
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success, error_msg

def delete_macro_definition(macro_code: str) -> tuple[bool, str | None]:
    """Xóa định nghĩa macro. Trả về (success, error_message)."""
    if not macro_code: return False, "Macro Code là bắt buộc."
    conn = get_db_connection()
    if not conn: return False, "Không thể kết nối CSDL."
    cur = None
    success = False
    error_msg = None
    try:
        cur = conn.cursor()
        # KIỂM TRA RÀNG BUỘC (QUAN TRỌNG)
        check_sql = """
            SELECT 1 FROM stage_transitions
            WHERE (action_to_suggest ->> 'macro_code') = %s LIMIT 1;
        """
        cur.execute(check_sql, (macro_code,))
        if cur.fetchone():
            return False, f"Không thể xóa Macro Code '{macro_code}' vì đang được sử dụng trong ít nhất một Transition."

        # Nếu không có ràng buộc, tiến hành xóa
        delete_sql = "DELETE FROM public.macro_definitions WHERE macro_code = %s;"
        cur.execute(delete_sql, (macro_code,))
        conn.commit()
        success = cur.rowcount > 0
        if not success:
            error_msg = f"Không tìm thấy Macro Code '{macro_code}' để xóa."
    except psycopg2.Error as e:
        error_msg = f"Lỗi CSDL: {e}"
        if conn: conn.rollback()
    except Exception as e:
        error_msg = f"Lỗi không xác định: {e}"
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success, error_msg

# --- SỬA LẠI các hàm add/update/get transition ---
def add_new_transition(strategy_id: str, # <<< THÊM strategy_id làm tham số bắt buộc
                       current_stage_id: str,
                       user_intent: str,
                       priority: int = 0,
                       condition_type: str | None = None,
                       condition_value: str | None = None,
                       next_stage_id: str | None = None,
                       # -- Các trường liên quan đến Action (Control) --
                       action_macro_code: str | None = None, # Tên macro (vd: UI_CLICK)
                       action_params_str: str | None = None, # Tham số cho macro (dạng chuỗi JSON)
                       # -- Trường liên quan đến Response (Language) --
                       response_template_ref: str | None = None,
                       # -- Các trường liên quan đến Loop (Control) --
                       loop_type: str | None = None,
                       loop_count: int | None = None, # Nên là int hoặc None
                       loop_condition_type: str | None = None,
                       loop_condition_value: str | None = None,
                       loop_target_selector_str: str | None = None, # Selector mục tiêu lặp (dạng chuỗi JSON)
                       loop_variable_name: str | None = None, # Tên biến lưu phần tử lặp (cho for_each)
                       notes: str | None = None # Thêm trường ghi chú
                       ) -> tuple[bool, str | None]:
    """
    Thêm một transition mới vào bảng stage_transitions.
    Hàm này bao gồm strategy_id và tất cả các trường cần thiết khác,
    đồng thời validate JSON đầu vào và xử lý giá trị None/rỗng.

    Trả về tuple (success: bool, error_message: str | None).
    """
    # Lấy logger hoặc dùng print
    logger = current_app.logger if current_app else print
    logger.info(f"DEBUG (db.add_new_transition): Adding transition for strategy '{strategy_id}', current='{current_stage_id}', intent='{user_intent}', loop='{loop_type}'")

    # --- Bước 1: Kiểm tra các tham số bắt buộc ---
    if not strategy_id:
         return False, "Lỗi nội bộ: Strategy ID không được cung cấp cho hàm add_new_transition." # Lỗi logic nếu hàm này được gọi mà thiếu strategy_id
    if not current_stage_id:
        return False, "Current Stage ID là bắt buộc."
    if not user_intent:
        # Cho phép intent rỗng hoặc None nếu logic của bạn cho phép? Nếu không thì báo lỗi:
        # return False, "User Intent là bắt buộc."
        user_intent = user_intent if user_intent else '' # Hoặc gán giá trị mặc định nếu được phép

    # --- Bước 2: Xử lý và Validate các chuỗi JSON đầu vào ---
    action_params_json_to_save = None # Giá trị sẽ lưu vào DB (TEXT)
    if action_params_str and action_params_str.strip() and action_params_str.strip() != '{}':
        try:
            # Validate xem có phải JSON không và chuẩn hóa lại chuỗi
            loaded_params = json.loads(action_params_str)
            if not isinstance(loaded_params, dict): raise ValueError("Action Params phải là một JSON object.")
            action_params_json_to_save = json.dumps(loaded_params) # Lưu dạng chuỗi JSON chuẩn
        except (json.JSONDecodeError, ValueError) as json_err:
            return False, f"Trường 'Action Params' chứa JSON không hợp lệ: {json_err}"

    loop_selector_json_to_save = None # Giá trị sẽ lưu vào DB (JSONB)
    if loop_target_selector_str and loop_target_selector_str.strip() and loop_target_selector_str.strip() != '{}':
        try:
             # Validate JSON
             loaded_selector = json.loads(loop_target_selector_str)
             # Có thể thêm kiểm tra cấu trúc của selector ở đây nếu cần
             loop_selector_json_to_save = json.dumps(loaded_selector) # Lưu dạng chuỗi để truyền vào SQL (sẽ ép kiểu jsonb)
        except json.JSONDecodeError as json_err:
             return False, f"Trường 'Loop Target Selector' chứa JSON không hợp lệ: {json_err}"

    # --- Bước 3: Xử lý các giá trị Optional (chuyển chuỗi rỗng thành None) ---
    # Điều này đảm bảo CSDL lưu NULL thay vì chuỗi rỗng cho các trường có thể NULL
    condition_type_db = condition_type.strip() if condition_type and condition_type.strip() else None
    condition_value_db = condition_value.strip() if condition_value and condition_value.strip() else None
    next_stage_id_db = next_stage_id.strip() if next_stage_id and next_stage_id.strip() else None
    action_macro_code_db = action_macro_code.strip() if action_macro_code and action_macro_code.strip() else None
    response_template_ref_db = response_template_ref.strip() if response_template_ref and response_template_ref.strip() else None
    loop_type_db = loop_type if loop_type and loop_type.strip() else None
    # Kiểm tra loop_type hợp lệ nếu cần
    # valid_loop_types = ['repeat_n', 'while_condition_met', 'for_each']
    # if loop_type_db and loop_type_db not in valid_loop_types:
    #    return False, f"Loop Type '{loop_type_db}' không hợp lệ."
    loop_condition_type_db = loop_condition_type.strip() if loop_condition_type and loop_condition_type.strip() else None
    loop_condition_value_db = loop_condition_value.strip() if loop_condition_value and loop_condition_value.strip() else None
    loop_variable_name_db = loop_variable_name.strip() if loop_variable_name and loop_variable_name.strip() else None
    notes_db = notes.strip() if notes and notes.strip() else None

    # Xử lý loop_count (phải là số nguyên hoặc None)
    loop_count_db = None
    if loop_count is not None:
        try:
            loop_count_db = int(loop_count)
        except (ValueError, TypeError):
             return False, "Loop Count phải là một số nguyên hợp lệ."

    # --- Bước 4: Thực hiện INSERT vào CSDL ---
    conn = get_db_connection()
    if not conn: return False, "Không thể kết nối CSDL."
    cur = None
    success = False
    error_msg = None
    try:
        cur = conn.cursor()
        # Câu lệnh SQL bao gồm tất cả các cột liên quan
        sql = """
            INSERT INTO public.stage_transitions (
                strategy_id, current_stage_id, user_intent, priority,
                condition_type, condition_value, next_stage_id,
                action_macro_code, action_params_str, -- Các cột đã sửa tên
                response_template_ref,
                loop_type, loop_count, loop_condition_type, loop_condition_value,
                loop_target_selector, loop_variable_name, notes,
                created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s,  -- strategy_id, current_stage_id, user_intent, priority
                %s, %s, %s,      -- condition_type, condition_value, next_stage_id
                %s, %s,          -- action_macro_code, action_params_str
                %s,              -- response_template_ref
                %s, %s, %s, %s,  -- loop_type, loop_count, loop_condition_type, loop_condition_value
                %s::jsonb, %s, %s, -- loop_target_selector (ép kiểu jsonb), loop_variable_name, notes
                NOW(), NOW()     -- created_at, updated_at
             );
        """
        params = (
            strategy_id, # <<< Đã thêm
            current_stage_id,
            user_intent,
            priority,
            condition_type_db,
            condition_value_db,
            next_stage_id_db,
            action_macro_code_db, # Cột đã sửa
            action_params_json_to_save, # Cột đã sửa, lưu chuỗi JSON hoặc None
            response_template_ref_db,
            loop_type_db,
            loop_count_db, # Integer hoặc None
            loop_condition_type_db,
            loop_condition_value_db,
            loop_selector_json_to_save, # Chuỗi JSON hoặc None (sẽ được ép kiểu jsonb trong SQL)
            loop_variable_name_db,
            notes_db
        )
        # logger.debug(f"DEBUG SQL (add_new_transition): {cur.mogrify(sql, params).decode('utf-8','ignore')}") # Bỏ comment để debug
        cur.execute(sql, params)
        conn.commit()
        success = True
        logger.info(f"INFO (db.add_new_transition): Thêm transition thành công cho strategy '{strategy_id}'.")

    except psycopg2.IntegrityError as int_err:
        # Lỗi ràng buộc khóa ngoại (vd: current_stage_id không tồn tại trong strategy_stages cho strategy_id này)
        # Hoặc lỗi ràng buộc UNIQUE (vd: UNIQUE(strategy_id, current_stage_id, user_intent) nếu có)
        error_msg = f"Lỗi ràng buộc CSDL khi thêm transition: {int_err}"
        logger.error(f"ERROR (db.add_new_transition): {error_msg}\n{traceback.format_exc()}")
        if conn: conn.rollback()
    except psycopg2.Error as db_err:
        # Các lỗi CSDL khác
        error_msg = f"Lỗi CSDL khi thêm transition: {db_err}"
        logger.error(f"ERROR (db.add_new_transition): {error_msg}\n{traceback.format_exc()}")
        if conn: conn.rollback()
    except Exception as e:
        # Các lỗi không mong muốn khác
        error_msg = f"Lỗi không xác định khi thêm transition: {e}"
        logger.error(f"ERROR (db.add_new_transition): {error_msg}\n{traceback.format_exc()}")
        if conn: conn.rollback()
    finally:
        # Luôn đóng kết nối và con trỏ
        if cur: cur.close()
        if conn: conn.close()

    # Trả về tuple (bool, str|None)
    return success, error_msg

# --- Hàm Cập nhật Transition ---
def update_transition(transition_id: int, current_stage_id: str, user_intent: str,
                      next_stage_id: str | None, priority: int,
                      # Tham số dùng cho Language (có thể None cho Control/Mainloop)
                      response_template_ref: str | None,
                      # Tham số dùng cho Control/Mainloop (có thể None cho Language)
                      action_macro_code: str | None,
                      action_params_str: str | None, # Chuỗi JSON từ form
                      condition_type: str | None,
                      condition_value: str | None,
                      # Tham số LOOP
                      loop_type: str | None = None,
                      loop_count: int | None = None,
                      loop_condition_type: str | None = None,
                      loop_condition_value: str | None = None,
                      loop_target_selector_str: str | None = None,
                      loop_variable_name: str | None = None,
                      # Thêm tham số notes nếu cần (giả sử bảng có cột notes)
                      notes: str | None = None
                     ) -> tuple[bool, str | None]:
    """Cập nhật một transition, bao gồm cả các trường loop. Đã sửa lỗi cột action."""
    logger = current_app.logger if current_app else print
    logger.info(f"DEBUG (db.update_transition): Updating transition ID={transition_id}, loop='{loop_type}'")

    if not transition_id or not current_stage_id or not user_intent:
        return False, "ID, Current Stage và User Intent là bắt buộc."

    # --- Xử lý các chuỗi JSON đầu vào và giá trị Optional ---
    action_params_json_to_save = None # Giá trị TEXT sẽ lưu vào DB
    if action_params_str and action_params_str.strip() and action_params_str.strip() != '{}':
        try:
            # Validate xem có phải JSON object không
            loaded_params = json.loads(action_params_str)
            if not isinstance(loaded_params, dict): raise ValueError("Action Params phải là JSON object.")
            action_params_json_to_save = json.dumps(loaded_params) # Chuẩn hóa lại thành chuỗi JSON
        except (json.JSONDecodeError, ValueError) as json_err:
            return False, f"Action Params không hợp lệ: {json_err}"

    loop_selector_json_to_save = None # Giá trị TEXT sẽ lưu vào DB (cho cột JSONB)
    if loop_target_selector_str and loop_target_selector_str.strip() and loop_target_selector_str.strip() != '{}':
        try:
             loaded_selector = json.loads(loop_target_selector_str)
             # Có thể thêm validate cấu trúc selector ở đây
             loop_selector_json_to_save = json.dumps(loaded_selector)
        except json.JSONDecodeError as json_err:
             return False, f"Loop Target Selector JSON không hợp lệ: {json_err}"

    # Chuyển chuỗi rỗng thành None cho các trường tùy chọn
    condition_type_db = condition_type if condition_type else None
    condition_value_db = condition_value if condition_value else None
    next_stage_id_db = next_stage_id if next_stage_id else None
    action_macro_code_db = action_macro_code if action_macro_code else None
    response_template_ref_db = response_template_ref if response_template_ref else None
    loop_type_db = loop_type if loop_type else None
    loop_condition_type_db = loop_condition_type if loop_condition_type else None
    loop_condition_value_db = loop_condition_value if loop_condition_value else None
    loop_variable_name_db = loop_variable_name if loop_variable_name else None
    notes_db = notes if notes else None

    # Xử lý loop_count (đảm bảo là int hoặc None)
    loop_count_db = None
    if loop_count is not None:
        try: loop_count_db = int(loop_count)
        except: return False, "Loop Count không hợp lệ."


    # --- Thực hiện UPDATE ---
    conn = get_db_connection()
    if not conn: return False, "Không thể kết nối CSDL."
    cur = None
    success = False
    error_msg = None
    try:
        cur = conn.cursor()
        # <<< SỬA LẠI CÂU LỆNH UPDATE: Dùng action_macro_code và action_params_str >>>
        sql = """
            UPDATE public.stage_transitions SET
                current_stage_id = %s, user_intent = %s, condition_type = %s, condition_value = %s,
                next_stage_id = %s, priority = %s,
                action_macro_code = %s,   -- <<< SỬA Ở ĐÂY
                action_params_str = %s,   -- <<< SỬA Ở ĐÂY
                response_template_ref = %s,
                loop_type = %s, loop_count = %s, loop_condition_type = %s, loop_condition_value = %s,
                loop_target_selector = %s::jsonb, loop_variable_name = %s, notes = %s, -- Thêm notes
                updated_at = NOW() -- Luôn cập nhật updated_at
            WHERE transition_id = %s;
        """
        params = (
            current_stage_id, user_intent,
            condition_type_db, condition_value_db,
            next_stage_id_db, priority,
            action_macro_code_db, # <<< Giá trị macro code (TEXT)
            action_params_json_to_save, # <<< Chuỗi JSON params hoặc None (TEXT)
            response_template_ref_db,
            loop_type_db, loop_count_db, loop_condition_type_db, loop_condition_value_db,
            loop_selector_json_to_save, # Chuỗi JSON hoặc None (sẽ ép kiểu jsonb)
            loop_variable_name_db,
            notes_db, # Thêm notes
            # --- Where condition ---
            transition_id
        )
        # logger.debug(f"DEBUG SQL (update_transition): {cur.mogrify(sql, params).decode('utf-8','ignore')}")
        cur.execute(sql, params)
        conn.commit()
        success = cur.rowcount > 0 # True nếu có dòng được cập nhật
        if not success:
             error_msg = f"Không tìm thấy transition_id {transition_id} để cập nhật."
             logger.warning(f"WARN (db.update_transition): {error_msg}")
        else:
             logger.info(f"INFO (db.update_transition): Updated transition {transition_id} successfully.")

    except psycopg2.Error as e:
        error_msg = f"Lỗi CSDL khi cập nhật transition: {e}"
        logger.error(f"ERROR (db - update_transition): {error_msg}\n{traceback.format_exc()}")
        if conn: conn.rollback()
    except Exception as e:
        error_msg = f"Lỗi không xác định khi cập nhật transition: {e}"
        logger.error(f"ERROR (db - update_transition): {error_msg}\n{traceback.format_exc()}")
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return success, error_msg

# --- Hàm Lấy Chi tiết Transition ---

def get_transition_details(transition_id: int) -> dict | None:
    """
    Lấy chi tiết một transition bằng ID, bao gồm cả strategy_id và các trường loop.
    Đã sửa lỗi truy vấn cột action và xử lý action_params_str.
    """
    # Lấy logger hoặc dùng print
    logger = current_app.logger if current_app else print

    if not transition_id:
        logger.warning("WARN (db.get_transition_details): transition_id rỗng được cung cấp.")
        return None

    details = None
    conn = get_db_connection()
    if not conn:
        logger.error("ERROR (db.get_transition_details): Không thể kết nối CSDL.")
        return None

    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # <<< SỬA LẠI CÂU SELECT: Dùng action_macro_code và action_params_str >>>
        sql = """
            SELECT
                t.transition_id, t.current_stage_id, t.user_intent,
                t.condition_type, t.condition_value,
                t.next_stage_id,
                t.action_macro_code,    -- <<< SỬA Ở ĐÂY
                t.action_params_str,    -- <<< SỬA Ở ĐÂY
                t.response_template_ref,
                t.priority,
                t.loop_type, t.loop_count, t.loop_condition_type, t.loop_condition_value,
                t.loop_target_selector, t.loop_variable_name,
                t.notes, -- Lấy cả notes
                ss.strategy_id -- Lấy strategy_id từ bảng stages
            FROM
                public.stage_transitions t
            LEFT JOIN
                public.strategy_stages ss ON t.current_stage_id = ss.stage_id AND t.strategy_id = ss.strategy_id -- Join cả strategy_id
            WHERE
                t.transition_id = %s;
        """
        # logger.debug(f"DEBUG SQL (get_transition_details): {cur.mogrify(sql, (transition_id,)).decode('utf-8','ignore')}")
        cur.execute(sql, (transition_id,))
        row = cur.fetchone()

        if row:
            details = dict(row) # Chuyển kết quả thành dict

            # <<< SỬA LẠI LOGIC XỬ LÝ SAU KHI FETCH >>>
            # Không cần parse `action_to_suggest` nữa
            # Thay vào đó, parse `action_params_str` để tạo chuỗi đẹp cho form edit

            # action_macro_code đã được lấy trực tiếp
            details['action_macro_code'] = details.get('action_macro_code') # Có thể là None

            # Xử lý action_params_str (TEXT trong DB) -> tạo action_params_str (chuỗi JSON đẹp) cho form
            params_str_from_db = details.get('action_params_str')
            params_str_for_form = '{}' # Default là object rỗng
            if params_str_from_db:
                try:
                    # Parse chuỗi JSON từ DB thành dict Python
                    params_dict = json.loads(params_str_from_db)
                    # Chuyển dict Python thành chuỗi JSON format đẹp
                    params_str_for_form = json.dumps(params_dict, indent=2, ensure_ascii=False)
                except (json.JSONDecodeError, TypeError):
                    logger.warning(f"WARN: action_params_str trong DB không phải JSON hợp lệ cho transition {transition_id}: {params_str_from_db}. Hiển thị chuỗi gốc.")
                    params_str_for_form = params_str_from_db # Hiển thị chuỗi gốc nếu lỗi parse
            details['action_params_str'] = params_str_for_form # Gán vào key mới hoặc key cũ tùy template

            # Xử lý loop_target_selector (JSONB trong DB) -> tạo chuỗi JSON đẹp
            selector_from_db = details.get('loop_target_selector')
            selector_str_for_form = '' # Default là chuỗi rỗng
            if selector_from_db is not None:
                 try:
                     selector_str_for_form = json.dumps(selector_from_db, indent=2, ensure_ascii=False)
                 except TypeError:
                     logger.warning(f"WARN: loop_target_selector trong DB không thể serialize cho transition {transition_id}. Hiển thị dạng thô.")
                     selector_str_for_form = str(selector_from_db)
            details['loop_target_selector_str'] = selector_str_for_form # Gán vào key mới

            logger.info(f"DEBUG DB (get_transition_details): Found details for {transition_id}: {details}")

        else:
            logger.warning(f"WARN (db.get_transition_details): Không tìm thấy transition ID {transition_id}.")
            # Trả về None nếu không tìm thấy

    except psycopg2.Error as db_err:
        logger.error(f"LỖI (database.py - get_transition_details): Truy vấn CSDL thất bại cho ID {transition_id}: {db_err}")
        logger.error(traceback.format_exc())
        details = None # Trả về None khi có lỗi CSDL
    except Exception as e:
        logger.error(f"LỖI (database.py - get_transition_details): Lỗi không xác định cho ID {transition_id}: {e}")
        logger.error(traceback.format_exc())
        details = None # Trả về None khi có lỗi khác
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return details

def get_strategy_version(strategy_id: str) -> str | None:
    """Lấy phiên bản hiện tại của chiến lược."""
    # ... (Giữ nguyên code đã cung cấp ở lần trước) ...
    conn = get_db_connection()
    if not conn: return None
    cur = None
    version = None
    try:
        cur = conn.cursor()
        # Lấy max updated_at từ strategy, stages, transitions liên quan
        sql = """
            SELECT MAX(last_update)
            FROM (
                SELECT updated_at AS last_update FROM strategies WHERE strategy_id = %s
                UNION ALL
                SELECT updated_at FROM strategy_stages WHERE strategy_id = %s AND updated_at IS NOT NULL
                UNION ALL
                SELECT t.updated_at FROM stage_transitions t JOIN strategy_stages s ON t.current_stage_id = s.stage_id WHERE s.strategy_id = %s AND t.updated_at IS NOT NULL
            ) AS all_updates;
            -- Cần đảm bảo các bảng có cột updated_at và được cập nhật đúng
        """
        # Note: Cần đảm bảo bảng transitions cũng có cột updated_at được cập nhật khi sửa
        # Nếu không có cột updated_at ở transitions, query cần sửa lại
        cur.execute(sql, (strategy_id, strategy_id, strategy_id))
        row = cur.fetchone()
        if row and row[0]:
            version = row[0].isoformat()
        else: # Fallback nếu không có updated_at
            version = datetime.now(timezone.utc).isoformat()
    except Exception as e: print(f"Error getting strategy version: {e}")
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return version or datetime.now(timezone.utc).isoformat()


def log_phone_action(session_id, timestamp, macro_code, params_json, execution_status, execution_error=None, current_stage=None, received_state_json=None):
     """Ghi log một hành động được thực thi bởi điện thoại."""
     conn = get_db_connection()
     if not conn: return False
     cur = None
     success = False
     try:
          cur = conn.cursor()
          # Cần tạo bảng phone_action_log với các cột phù hợp
          # Giả sử bảng có cột: session_id, timestamp, macro_code, params_json, status, error_msg, current_stage, ui_state_json
          sql = """
               INSERT INTO public.phone_action_log
               (session_id, "timestamp", macro_code, params_json, execution_status, execution_error, current_stage, received_state_json)
               VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s::jsonb);
          """
          ts_obj = timestamp
          if isinstance(timestamp, str): # Chuyển đổi nếu timestamp là string ISO
              try: ts_obj = datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00')) # Xử lý Z timezone
              except: ts_obj = datetime.datetime.now(datetime.timezone.utc)
          elif timestamp is None:
              ts_obj = datetime.datetime.now(datetime.timezone.utc)

          params_json_str = json.dumps(params_json) if params_json else None
          state_json_str = json.dumps(received_state_json) if received_state_json else None

          params = (
               session_id, ts_obj, macro_code, params_json_str, execution_status,
               execution_error, current_stage, state_json_str
          )
          cur.execute(sql, params)
          conn.commit()
          success = True
     except psycopg2.Error as e: print(f"ERROR logging phone action: {e}"); conn.rollback()
     except Exception as e: print(f"ERROR logging phone action: {e}"); conn.rollback()
     finally:
          if cur: cur.close()
          if conn: conn.close()
     return success

# --- HÀM GET ACTION SEQUENCE - ĐÃ CẬP NHẬT VỚI LOOP FIELDS ---
def get_strategy_action_sequence(strategy_id: str) -> list[dict] | None:
    """
    Lấy danh sách các transition thô (đã sắp xếp) cho một chiến lược,
    bao gồm các trường action và loop riêng biệt. Truy vấn trực tiếp bảng transitions.
    Hàm này được dùng bởi compile_strategy_package để tạo action_sequence JSON.

    Args:
        strategy_id: ID của chiến lược cần lấy transitions.

    Returns:
        List các dictionary chứa thông tin transition, hoặc None nếu lỗi.
        Mỗi dictionary sẽ có thêm key 'action_params' (là dict) được parse từ 'action_params_str'.
    """
    # Lấy logger hoặc dùng print
    logger = current_app.logger if current_app else print

    if not strategy_id:
        logger.warning("WARN (db.get_strategy_action_sequence): strategy_id rỗng được cung cấp.")
        return None # Trả về None nếu không có strategy_id

    transitions_list = None
    conn = get_db_connection()
    if not conn:
        logger.error("ERROR (db.get_strategy_action_sequence): Không thể kết nối CSDL.")
        return None # Trả về None nếu lỗi kết nối

    cur = None
    try:
        # Sử dụng DictCursor để dễ dàng truy cập cột bằng tên
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        logger.info(f"DEBUG (database.py): Truy vấn action sequence cho strategy_id='{strategy_id}'...")

        # Câu lệnh SQL chọn tất cả các cột cần thiết từ stage_transitions
        # Lọc trực tiếp theo strategy_id trên bảng này
        sql = """
            SELECT
                transition_id, strategy_id, current_stage_id, user_intent,
                priority, condition_type, condition_value, next_stage_id,
                action_macro_code, action_params_str, -- Cột action riêng biệt
                response_template_ref,               -- Cột template (cho language)
                loop_type, loop_count, loop_condition_type, loop_condition_value,
                loop_target_selector, loop_variable_name, notes, -- Các cột loop và notes
                created_at, updated_at -- Thêm timestamps nếu cần
            FROM
                public.stage_transitions
            WHERE
                strategy_id = %s -- <<< Lọc trực tiếp trên bảng transitions
            ORDER BY
                current_stage_id, priority DESC, user_intent; -- Giữ nguyên thứ tự sắp xếp quan trọng này
        """
        cur.execute(sql, (strategy_id,))
        rows = cur.fetchall()

        # Chuyển đổi kết quả thành list các dictionary
        transitions_list = [dict(row) for row in rows] if rows else []

        # Xử lý bổ sung: Parse các chuỗi JSON thành dictionary Python để dễ dùng hơn ở tầng controller
        for transition in transitions_list:
            # Xử lý action_params_str (là TEXT trong DB) -> action_params (là dict)
            params_str = transition.get('action_params_str')
            parsed_params = {} # Mặc định là dict rỗng
            if params_str and isinstance(params_str, str):
                try:
                    loaded_json = json.loads(params_str)
                    if isinstance(loaded_json, dict): # Đảm bảo kết quả là dict
                        parsed_params = loaded_json
                    else:
                        logger.warning(f"WARN: action_params_str không phải JSON object cho transition {transition.get('transition_id')}: {params_str}")
                except json.JSONDecodeError:
                    logger.warning(f"WARN: Không thể parse action_params_str cho transition {transition.get('transition_id')}: {params_str}")
            transition['action_params'] = parsed_params # Thêm key mới vào dict transition

            # Xử lý loop_target_selector (là JSONB trong DB, DictCursor thường trả về dict)
            # Chỉ cần đảm bảo nó là dict nếu không null
            if transition.get('loop_target_selector') is None:
                transition['loop_target_selector'] = {} # Đảm bảo là dict rỗng nếu giá trị là NULL

        logger.info(f"DEBUG: Found {len(transitions_list)} raw transitions for strategy {strategy_id}")

    except psycopg2.Error as db_err:
        logger.error(f"LỖI (db - get_strategy_action_sequence): Truy vấn thất bại cho strategy '{strategy_id}': {db_err}")
        logger.error(traceback.format_exc())
        transitions_list = None # Trả về None khi có lỗi CSDL
    except Exception as e:
        logger.error(f"LỖI (db - get_strategy_action_sequence): Lỗi không xác định cho strategy '{strategy_id}': {e}")
        logger.error(traceback.format_exc())
        transitions_list = None # Trả về None khi có lỗi khác
    finally:
        if cur: cur.close()
        if conn: conn.close()
        # logger.debug(f"DEBUG (db.get_strategy_action_sequence): Đã đóng kết nối DB.")

    return transitions_list

# =============================================
# === HÀM MỚI CHO QUẢN LÝ THIẾT BỊ & GIAO VIỆC ===
# =============================================

def register_or_update_device(device_id: str, device_info: dict, client_version: str, managed_accounts: list) -> bool:
    """
    Đăng ký thiết bị mới hoặc cập nhật thông tin thiết bị đã có.
    Đồng thời cập nhật/thêm thông tin liên kết device-account.

    Args:
        device_id: ID duy nhất của thiết bị.
        device_info: Dict chứa thông tin OS, model.
        client_version: Version của MacroDroid client.
        managed_accounts: List các dict, mỗi dict chứa:
                          {'account_id', 'platform', 'clone_context', 'status'}

    Returns:
        True nếu thành công, False nếu lỗi.
    """
    if not device_id or not managed_accounts:
        current_app.logger.error("register_or_update_device: Missing device_id or managed_accounts.")
        return False

    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        now = datetime.now(timezone.utc)
        os_info_str = f"{device_info.get('os', '?')}, {device_info.get('model', '?')}"

        # 1. UPSERT vào bảng devices
        sql_upsert_device = """
            INSERT INTO public.devices (device_id, os_info, macrodroid_version, status, last_seen_at, registered_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (device_id) DO UPDATE SET
                os_info = EXCLUDED.os_info,
                macrodroid_version = EXCLUDED.macrodroid_version,
                status = EXCLUDED.status,
                last_seen_at = EXCLUDED.last_seen_at;
        """
        cur.execute(sql_upsert_device, (device_id, os_info_str, client_version, 'online', now, now))
        current_app.logger.debug(f"Upserted device: {device_id}")

        # 2. Xử lý từng managed_account
        for acc_info in managed_accounts:
            account_id = acc_info.get('account_id')
            platform = acc_info.get('platform')
            clone_context = acc_info.get('clone_context')
            acc_status_on_device = acc_info.get('status', 'unknown') # Status account trên device

            if not account_id or not platform:
                current_app.logger.warning(f"Skipping invalid managed account data for device {device_id}: {acc_info}")
                continue

            # 2a. Đảm bảo account tồn tại trong bảng accounts (Thêm nếu chưa có)
            # Bạn có thể bỏ qua bước này nếu client chỉ báo cáo account đã có
            sql_ensure_account = """
                INSERT INTO public.accounts (account_id, platform, username, status, created_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (account_id) DO NOTHING;
            """
            # Username có thể không có, status mặc định là 'active' nếu tạo mới
            cur.execute(sql_ensure_account, (account_id, platform, acc_info.get('username'), 'active', now))

            # 2b. UPSERT vào bảng device_accounts
            sql_upsert_device_account = """
                INSERT INTO public.device_accounts (device_id, account_id, clone_context, status, last_check_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (device_id, account_id) DO UPDATE SET
                    clone_context = EXCLUDED.clone_context,
                    status = EXCLUDED.status,
                    last_check_at = EXCLUDED.last_check_at;
            """
            cur.execute(sql_upsert_device_account, (device_id, account_id, clone_context, acc_status_on_device, now))
            current_app.logger.debug(f"Upserted device_account link: device={device_id}, account={account_id}")

        conn.commit()
        success = True

    except psycopg2.Error as db_err:
        current_app.logger.error(f"DB Error in register_or_update_device for {device_id}: {db_err}", exc_info=True)
        if conn: conn.rollback()
    except Exception as e:
        current_app.logger.error(f"Unexpected Error in register_or_update_device for {device_id}: {e}", exc_info=True)
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success

def get_device_account_id(device_id: str, account_id: str) -> int | None:
    """Lấy device_account_id từ device_id và account_id."""
    if not device_id or not account_id: return None
    dev_acc_id = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor()
        sql = "SELECT device_account_id FROM public.device_accounts WHERE device_id = %s AND account_id = %s;"
        cur.execute(sql, (device_id, account_id))
        row = cur.fetchone()
        if row:
            dev_acc_id = row[0]
        else:
            current_app.logger.warning(f"No device_account link found for device='{device_id}', account='{account_id}'")
    except Exception as e:
        current_app.logger.error(f"Error getting device_account_id for device='{device_id}', account='{account_id}': {e}", exc_info=True)
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return dev_acc_id

def get_pending_assignment(device_account_id: int) -> dict | None:
    """
    Tìm một task assignment phù hợp ('pending' hoặc 'assigned') cho một device_account cụ thể.
    Ưu tiên theo priority và thời gian tạo.
    """
    if not device_account_id: return None
    assignment_details = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor) # Dùng DictCursor
        now = datetime.now(timezone.utc)
        # Tìm assignment 'pending' hoặc 'assigned' (có thể client cũ bị dừng đột ngột)
        # Phải khớp device_account_id
        # Phải nằm trong khoảng thời gian schedule (nếu có)
        # Ưu tiên priority cao nhất, sau đó đến thời gian tạo cũ nhất
        sql = """
            SELECT assignment_id, strategy_id, target_data
            FROM public.task_assignments
            WHERE device_account_id = %s
              AND status IN ('pending', 'assigned')
              AND (schedule_start_time IS NULL OR schedule_start_time <= %s)
              AND (schedule_end_time IS NULL OR schedule_end_time > %s)
            ORDER BY priority DESC, created_at ASC
            LIMIT 1;
        """
        cur.execute(sql, (device_account_id, now, now))
        row = cur.fetchone()
        if row:
            assignment_details = dict(row)
            current_app.logger.info(f"Found pending assignment {assignment_details['assignment_id']} for device_account {device_account_id}")
        # else:
            # current_app.logger.debug(f"No pending assignment found for device_account {device_account_id}")

    except Exception as e:
        current_app.logger.error(f"Error getting pending assignment for device_account {device_account_id}: {e}", exc_info=True)
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return assignment_details

def update_assignment_status(assignment_id: int, new_status: str, **kwargs) -> bool:
    """
    Cập nhật status và các trường tùy chọn khác cho một assignment.

    Args:
        assignment_id: ID của assignment.
        new_status: Trạng thái mới ('assigned', 'running', 'completed', 'error', 'cancelled').
        **kwargs: Các trường tùy chọn khác cần cập nhật (vd: assigned_at, started_at,
                  completed_at, result_data).
    """
    if not assignment_id or not new_status: return False

    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        # Xây dựng câu lệnh UPDATE động
        set_clauses = ["status = %s"]
        params = [new_status]

        allowed_updates = {
            "assigned_at": "assigned_at = %s",
            "started_at": "started_at = %s",
            "completed_at": "completed_at = %s",
            "result_data": "result_data = %s::jsonb" # Ép kiểu JSONB
        }

        for key, value in kwargs.items():
            if key in allowed_updates:
                set_clauses.append(allowed_updates[key])
                # Xử lý JSON cho result_data
                if key == 'result_data':
                    params.append(json.dumps(value) if value is not None else None)
                else:
                    params.append(value) # Thường là datetime hoặc None

        set_sql = ", ".join(set_clauses)
        sql = f"UPDATE public.task_assignments SET {set_sql} WHERE assignment_id = %s;"
        params.append(assignment_id) # Thêm assignment_id vào cuối cho WHERE

        cur.execute(sql, tuple(params))
        conn.commit()
        success = cur.rowcount > 0
        if not success:
            current_app.logger.warning(f"Assignment ID {assignment_id} not found for status update.")

    except Exception as e:
        current_app.logger.error(f"Error updating assignment status for {assignment_id}: {e}", exc_info=True)
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success

def update_assignment_progress(assignment_id: int, progress_data: dict) -> bool:
    """
    Cập nhật trường target_data (JSONB) với thông tin tiến độ mới.
    Sử dụng jsonb_set hoặc jsonb_insert của PostgreSQL để cập nhật an toàn.
    """
    if not assignment_id or not progress_data or not isinstance(progress_data, dict):
        return False

    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        # Ví dụ: Cập nhật 'current_count' nếu client gửi 'followers_gained'
        # Cách tiếp cận an toàn là lấy target_data hiện tại, cập nhật trong Python, rồi ghi lại
        # Hoặc dùng toán tử của PostgreSQL

        # Cách 1: Lấy -> Cập nhật -> Ghi lại (An toàn hơn, dễ xử lý logic phức tạp)
        sql_get = "SELECT target_data FROM public.task_assignments WHERE assignment_id = %s;"
        cur.execute(sql_get, (assignment_id,))
        row = cur.fetchone()
        if not row:
             current_app.logger.warning(f"Assignment {assignment_id} not found for progress update.")
             return False

        current_target_data = row[0] or {} # Lấy dict hiện tại hoặc dict rỗng
        updated_target_data = current_target_data.copy() # Tạo bản sao để sửa

        # --- Logic cập nhật ví dụ ---
        if 'followers_gained' in progress_data:
             try:
                 current = int(updated_target_data.get('current_count', 0))
                 gained = int(progress_data['followers_gained'])
                 updated_target_data['current_count'] = current + gained
             except (ValueError, TypeError):
                 current_app.logger.warning(f"Invalid progress data type for followers_gained (assignment {assignment_id})")
        # Thêm các cập nhật khác cho 'videos_watched', 'comments_posted' v.v...
        # if 'videos_watched' in progress_data: ...

        # Ghi lại target_data đã cập nhật
        sql_update = "UPDATE public.task_assignments SET target_data = %s::jsonb WHERE assignment_id = %s;"
        cur.execute(sql_update, (json.dumps(updated_target_data), assignment_id))

        # Cách 2: Dùng toán tử PostgreSQL (Phức tạp hơn nếu có nhiều key cần cập nhật)
        # Ví dụ: Tăng current_count bằng giá trị followers_gained
        # followers_gained_value = progress_data.get('followers_gained', 0)
        # try: followers_gained_int = int(followers_gained_value)
        # except: followers_gained_int = 0
        # sql_update = """
        #     UPDATE public.task_assignments
        #     SET target_data = jsonb_set(
        #         target_data,
        #         '{current_count}',
        #         to_jsonb(COALESCE((target_data->>'current_count')::int, 0) + %s)
        #     )
        #     WHERE assignment_id = %s;
        # """
        # cur.execute(sql_update, (followers_gained_int, assignment_id))

        conn.commit()
        success = cur.rowcount > 0

    except Exception as e:
        current_app.logger.error(f"Error updating assignment progress for {assignment_id}: {e}", exc_info=True)
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success

def update_assignment_last_report(assignment_id: int) -> bool:
    """Cập nhật chỉ trường last_report_at."""
    if not assignment_id: return False
    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        sql = "UPDATE public.task_assignments SET last_report_at = %s WHERE assignment_id = %s;"
        cur.execute(sql, (datetime.now(timezone.utc), assignment_id))
        conn.commit()
        success = cur.rowcount > 0
    except Exception as e:
        current_app.logger.error(f"Error updating assignment last_report_at for {assignment_id}: {e}", exc_info=True)
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success

def add_phone_action_logs(assignment_id: int | None, # Cho phép assignment_id là None
                            device_id: str, account_id: str,
                            logs: list[dict], # logs có thể là []
                            structured_ui_state_json: str | None = None
                            ) -> bool:
    logger = current_app.logger if current_app else print

    # Kiểm tra input cơ bản
    if not device_id or not account_id: # assignment_id có thể None
        logger.warning(f"Input không hợp lệ cho add_phone_action_logs: Thiếu device_id hoặc account_id")
        return False

    # Nếu không có log từ client VÀ không có UI state thì không cần làm gì
    if not logs and not structured_ui_state_json:
         logger.info(f"No client logs or UI state to record for device={device_id}, account={account_id}, assignment={assignment_id}.")
         return True

    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        sql_template = """
                    INSERT INTO public.phone_action_log
                    (assignment_id, device_id, account_id, "timestamp", action_macro_code, 
                     params_json, execution_status, execution_error, current_stage,
                     received_state_json)
                    VALUES %s;
                """
        data_tuples = []

        # Xử lý các log entry từ client (nếu có)
        if logs and isinstance(logs, list):
            for log_entry in logs:
                # ... (code xử lý timestamp, params như cũ) ...
                ts_str = log_entry.get('timestamp'); ts_obj = datetime.now(timezone.utc)
                if isinstance(ts_str, str):
                    try: ts_obj = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                    except ValueError: pass
                params_data = log_entry.get('params'); params_json_str_to_save = None
                if params_data is not None:
                    try: params_json_str_to_save = json.dumps(params_data, ensure_ascii=False)
                    except TypeError: params_json_str_to_save = json.dumps({"raw_param_data": str(params_data)})

                data_tuples.append((
                    assignment_id, device_id, account_id, ts_obj,
                    log_entry.get('macro'),
                    params_json_str_to_save,
                    log_entry.get('status', 'unknown'),
                    log_entry.get('error'),
                    log_entry.get('stage'),
                    structured_ui_state_json # <<< Vẫn gắn state UI vào log hành động
                ))

        # <<< THÊM XỬ LÝ: Nếu KHÔNG có log client NHƯNG CÓ UI state >>>
        # Tạo một bản ghi log "placeholder" để lưu state này
        if not logs and structured_ui_state_json:
            logger.debug(f"Creating placeholder log entry to store UI state for assignment {assignment_id}.")
            data_tuples.append((
                assignment_id, device_id, account_id,
                datetime.now(timezone.utc), # Dùng thời gian server
                'STATE_REPORT', # Macro code đặc biệt cho biết đây là log chỉ chứa state
                None, # Không có params
                'info', # Status là info
                None, # Không có lỗi
                None, # Không có stage cụ thể từ client
                structured_ui_state_json # <<< Dữ liệu UI state
            ))

        # Thực thi INSERT nếu có dữ liệu để ghi
        if data_tuples:
            logger.debug(f"Preparing to INSERT {len(data_tuples)} log entries (including possible state placeholder) for assignment {assignment_id}.")
            psycopg2.extras.execute_values(cur, sql_template, data_tuples, page_size=100)
            conn.commit()
            success = True
            logger.info(f"Successfully added {len(data_tuples)} phone log entries for assignment {assignment_id}.")
        else:
            # Trường hợp này không nên xảy ra do đã kiểm tra ở đầu hàm
            logger.warning(f"No data tuples generated for logging for assignment {assignment_id}.")
            success = True # Coi như thành công vì không có lỗi DB

    except psycopg2.Error as db_err:
        logger.error(f"Lỗi DB khi thêm phone action logs cho assignment {assignment_id}: {db_err}", exc_info=True)
        if conn: conn.rollback()
    except Exception as e:
        logger.error(f"Lỗi không xác định khi thêm phone action logs cho assignment {assignment_id}: {e}", exc_info=True)
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success

# --- Cần các hàm lấy chi tiết/status của Assignment (nếu chưa có) ---
def get_task_assignment_details(assignment_id: int) -> dict | None:
    """Lấy chi tiết một task assignment bằng ID."""
    if not assignment_id: return None
    details = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        # Lấy đủ các cột cần thiết
        sql = """
            SELECT ta.*, da.device_id, da.account_id -- Lấy thêm device_id, account_id từ join
            FROM public.task_assignments ta
            JOIN public.device_accounts da ON ta.device_account_id = da.device_account_id
            WHERE ta.assignment_id = %s;
            """
        cur.execute(sql, (assignment_id,))
        row = cur.fetchone()
        if row:
            details = dict(row)
            # Parse JSON nếu cần (thường DictCursor làm rồi)
            if isinstance(details.get('target_data'), str):
                 try: details['target_data'] = json.loads(details['target_data'])
                 except: details['target_data'] = {}
            if isinstance(details.get('result_data'), str):
                 try: details['result_data'] = json.loads(details['result_data'])
                 except: details['result_data'] = {}
    except Exception as e:
        current_app.logger.error(f"Error getting task assignment details for {assignment_id}: {e}", exc_info=True)
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return details

def get_task_assignment_status(assignment_id: int) -> str | None:
    """Lấy chỉ status của một task assignment."""
    if not assignment_id: return None
    status = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor()
        sql = "SELECT status FROM public.task_assignments WHERE assignment_id = %s;"
        cur.execute(sql, (assignment_id,))
        row = cur.fetchone()
        if row:
            status = row[0]
    except Exception as e:
        current_app.logger.error(f"Error getting task assignment status for {assignment_id}: {e}", exc_info=True)
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return status

# =============================================
# === HÀM MỚI CHO QUẢN LÝ TASK ASSIGNMENT ===
# =============================================

def get_all_task_assignments(filters: dict = None, page: int = 1, per_page: int = 30) -> tuple[list[dict] | None, int | None]:
    """
    Lấy danh sách các task assignments đã lọc và phân trang.

    Args:
        filters: Dict chứa các bộ lọc (vd: {'status': 'running', 'device_id': '...', 'account_id': '...'}).
        page: Số trang hiện tại.
        per_page: Số mục mỗi trang.

    Returns:
        Tuple: (list các assignment của trang hoặc None nếu lỗi, tổng số assignment khớp filter hoặc None nếu lỗi)
    """
    assignments = None
    total_items = None
    conn = get_db_connection()
    if not conn: return None, None
    cur = None

    # --- Xây dựng câu lệnh SELECT và JOIN ---
    select_sql = """
            SELECT
                ta.assignment_id,
                ta.status,
                ta.priority,
                ta.strategy_id,
                s.name as strategy_name,
                da.device_id,
                d.device_name,
                da.account_id,
                acc.username as account_username,
                acc.platform as account_platform,
                ta.target_data, -- <<< Lấy cả target_data (JSONB)
                ta.result_data, -- <<< THAY THẾ: Lấy result_data (JSONB)
                ta.created_at,
                ta.assigned_at,
                ta.last_report_at,
                ta.completed_at
                -- Bỏ cột ta.error_message không tồn tại
            FROM public.task_assignments ta
            JOIN public.device_accounts da ON ta.device_account_id = da.device_account_id
            JOIN public.devices d ON da.device_id = d.device_id
            JOIN public.accounts acc ON da.account_id = acc.account_id
            LEFT JOIN public.strategies s ON ta.strategy_id = s.strategy_id
        """

    # --- Xây dựng mệnh đề WHERE động ---
    where_clauses = []
    params = []
    if filters:
        # ... (Xử lý filters như cũ) ...
        if filters.get('status'): where_clauses.append("ta.status = %s"); params.append(filters['status'])
        if filters.get('strategy_id'): where_clauses.append("ta.strategy_id = %s"); params.append(filters['strategy_id'])
        if filters.get('device_id'): where_clauses.append("da.device_id = %s"); params.append(filters['device_id'])
        if filters.get('account_id'): where_clauses.append("da.account_id = %s"); params.append(filters['account_id'])

    where_sql = ""
    if where_clauses: where_sql = "WHERE " + " AND ".join(where_clauses)

    try:
        cur = conn.cursor()
        count_sql = f"SELECT COUNT(ta.assignment_id) FROM public.task_assignments ta JOIN public.device_accounts da ON ta.device_account_id = da.device_account_id {where_sql};"
        cur.execute(count_sql, tuple(params))
        total_items = cur.fetchone()[0]
        cur.close()

        assignments = []
        if total_items > 0:
                    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    offset = (page - 1) * per_page
                    data_sql = f"{select_sql} {where_sql} ORDER BY ta.created_at DESC LIMIT %s OFFSET %s;"
                    data_params = params + [per_page, offset]
                    cur.execute(data_sql, tuple(data_params))
                    rows = cur.fetchall()
                    assignments = [dict(row) for row in rows] if rows else []
                    # Chuyển đổi JSONB thành dict nếu cần (psycopg2 DictCursor thường tự làm)
                    for task in assignments:
                         if task.get('target_data') and isinstance(task['target_data'], str):
                              try: task['target_data'] = json.loads(task['target_data'])
                              except: task['target_data'] = {}
                         elif not isinstance(task.get('target_data'), dict): # Đảm bảo là dict hoặc None/rỗng
                             task['target_data'] = {}
        
                         if task.get('result_data') and isinstance(task['result_data'], str):
                              try: task['result_data'] = json.loads(task['result_data'])
                              except: task['result_data'] = {}
                         elif not isinstance(task.get('result_data'), dict): # Đảm bảo là dict hoặc None/rỗng
                             task['result_data'] = {}

    except psycopg2.Error as db_err:
        current_app.logger.error(f"DB Error fetching task assignments: {db_err}", exc_info=True)
        assignments = None; total_items = None
    except Exception as e:
        current_app.logger.error(f"Unexpected Error fetching task assignments: {e}", exc_info=True)
        assignments = None; total_items = None
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return assignments, total_items


def add_task_assignment(device_account_id: int, strategy_id: str, priority: int,
                        target_data_str: str | None, notes: str | None,
                        schedule_start_time: datetime | None = None,
                        schedule_end_time: datetime | None = None) -> tuple[bool, str | None]:
    """
    Thêm một task assignment mới vào CSDL.

    Args:
        device_account_id: ID của liên kết device-account.
        strategy_id: ID của control strategy.
        priority: Độ ưu tiên.
        target_data_str: Chuỗi JSON chứa mục tiêu (vd: '{"goal_type":"followers", "target_count":1000}').
        notes: Ghi chú.
        schedule_start_time: Thời gian bắt đầu dự kiến (optional).
        schedule_end_time: Thời gian kết thúc dự kiến (optional).

    Returns:
        Tuple (bool, str | None): (True nếu thành công, None) hoặc (False, thông báo lỗi).
    """
    if not device_account_id or not strategy_id:
        return False, "Device/Account và Strategy là bắt buộc."

    # Validate và parse JSON target_data
    target_data_json = None
    if target_data_str and target_data_str.strip() and target_data_str != '{}':
        try:
            target_data_dict = json.loads(target_data_str)
            if not isinstance(target_data_dict, dict):
                raise ValueError("Target Data phải là một JSON object.")
            # Thêm các trường mặc định nếu cần (ví dụ: current_count)
            if target_data_dict.get('target_count') is not None and 'current_count' not in target_data_dict:
                 target_data_dict['current_count'] = 0
            target_data_json = json.dumps(target_data_dict) # Lưu lại dạng JSON chuẩn
        except (json.JSONDecodeError, ValueError) as json_err:
            return False, f"Target Data không hợp lệ: {json_err}"

    conn = get_db_connection()
    if not conn: return False, "Không thể kết nối CSDL."
    cur = None
    success = False
    error_msg = None
    try:
        cur = conn.cursor()
        sql = """
            INSERT INTO public.task_assignments (
                device_account_id, strategy_id, status, priority,
                schedule_start_time, schedule_end_time, target_data, notes, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, NOW());
        """
        params = (
            device_account_id,
            strategy_id,
            'pending', # Trạng thái ban đầu
            priority,
            schedule_start_time, # Có thể là None
            schedule_end_time,   # Có thể là None
            target_data_json,    # Chuỗi JSON hoặc None
            notes
        )
        cur.execute(sql, params)
        conn.commit()
        success = True
        current_app.logger.info(f"Added new task assignment for device_account_id {device_account_id}, strategy {strategy_id}")

    except psycopg2.Error as e:
        error_msg = f"Lỗi CSDL khi thêm task assignment: {e}"
        current_app.logger.error(error_msg, exc_info=True)
        if conn: conn.rollback()
    except Exception as e:
        error_msg = f"Lỗi không xác định khi thêm task assignment: {e}"
        current_app.logger.error(error_msg, exc_info=True)
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success, error_msg



# =============================================
# === HÀM CHO QUẢN LÝ DEVICES (ADMIN) ===
# =============================================
def add_device(device_id: str, device_name: str | None, notes: str | None,
               os_info: str | None, macrodroid_version: str | None) -> tuple[bool, str | None]:
    """Thêm một thiết bị mới thủ công từ Admin."""
    if not device_id:
        return False, "Device ID là bắt buộc."
    # Thêm kiểm tra độ dài tối đa nếu cần
    # if len(device_id) > 100: return False, "Device ID quá dài (tối đa 100 ký tự)."

    conn = get_db_connection() # Đảm bảo hàm get_db_connection tồn tại
    if not conn: return False, "Không thể kết nối CSDL."
    cur = None
    success = False
    error_msg = None
    try:
        cur = conn.cursor()
        # Thêm os_info và macrodroid_version vào INSERT
        sql = """
            INSERT INTO public.devices
                (device_id, device_name, notes, status, registered_at, os_info, macrodroid_version)
            VALUES (%s, %s, %s, %s, NOW(), %s, %s);
        """
        params = (
            device_id.strip(),
            device_name.strip() if device_name else None,
            notes.strip() if notes else None,
            'offline', # Trạng thái mặc định khi thêm thủ công
            os_info.strip() if os_info else None,
            macrodroid_version.strip() if macrodroid_version else None
        )
        cur.execute(sql, params)
        conn.commit()
        success = True
        # Sử dụng logger nếu có, nếu không thì print
        log_func = current_app.logger.info if current_app else print
        log_func(f"Admin added device: {device_id} with OS='{os_info}', Ver='{macrodroid_version}'")
    except psycopg2.IntegrityError:
        error_msg = f"Device ID '{device_id}' đã tồn tại."
        if conn: conn.rollback()
    except psycopg2.Error as e:
        error_msg = f"Lỗi CSDL khi thêm device: {e}"
        log_func = current_app.logger.error if current_app else print
        log_func(error_msg, exc_info=True)
        if conn: conn.rollback()
    except Exception as e:
        error_msg = f"Lỗi không xác định khi thêm device: {e}"
        log_func = current_app.logger.error if current_app else print
        log_func(error_msg, exc_info=True)
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success, error_msg

def get_all_devices(page: int = 1, per_page: int = 30) -> tuple[list[dict] | None, int | None]:
    """Lấy danh sách tất cả các thiết bị với phân trang."""
    # ... (Code của hàm này đã được cung cấp và sửa ở bước trước) ...
    devices = None
    total_items = None
    conn = get_db_connection()
    if not conn: return None, None
    cur = None
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM public.devices;")
        total_items = cur.fetchone()[0]
        cur.close()
        devices = []
        if total_items > 0:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            offset = (page - 1) * per_page
            sql = """
                SELECT device_id, device_name, os_info, macrodroid_version, status, last_seen_at, registered_at, notes
                FROM public.devices ORDER BY registered_at DESC, device_id LIMIT %s OFFSET %s;
            """
            cur.execute(sql, (per_page, offset))
            rows = cur.fetchall()
            devices = [dict(row) for row in rows] if rows else []
    except psycopg2.Error as db_err:
        log_func = current_app.logger.error if current_app else print
        log_func(f"DB Error fetching all devices: {db_err}", exc_info=True)
        devices, total_items = None, None
    except Exception as e:
        log_func = current_app.logger.error if current_app else print
        log_func(f"Unexpected Error fetching all devices: {e}", exc_info=True)
        devices, total_items = None, None
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return devices, total_items


def get_device_details(device_id: str) -> dict | None:
    """Lấy chi tiết một thiết bị bằng device_id."""
    # ... (Code của hàm này đã được cung cấp trước đó) ...
    if not device_id: return None
    details = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        sql = "SELECT * FROM public.devices WHERE device_id = %s;" # Lấy tất cả cột
        cur.execute(sql, (device_id,))
        row = cur.fetchone()
        if row: details = dict(row)
    except Exception as e:
        log_func = current_app.logger.error if current_app else print
        log_func(f"Error getting device details for {device_id}: {e}", exc_info=True)
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return details


def update_device_admin(device_id: str, device_name: str | None, notes: str | None, status: str | None,
                        os_info: str | None, macrodroid_version: str | None) -> tuple[bool, str | None]: # <<< Thêm tham số mới
    """Cập nhật thông tin device từ Admin."""
    if not device_id: return False, "Device ID là bắt buộc."

    conn = get_db_connection()
    if not conn: return False, "Không thể kết nối CSDL."
    cur = None
    success = False
    error_msg = None
    try:
        cur = conn.cursor()
        # Thêm os_info, macrodroid_version vào SET clause
        # Dùng COALESCE để chỉ cập nhật nếu giá trị mới được cung cấp (không phải None/rỗng),
        # nếu không giữ lại giá trị cũ. Tuy nhiên, nếu muốn admin có thể xóa trắng thông tin thì
        # cần logic khác hoặc truyền chuỗi rỗng thay vì None.
        # Cách đơn giản hơn là luôn cập nhật giá trị mới (kể cả None/rỗng).
        sql = """
            UPDATE public.devices
            SET device_name = %s,
                notes = %s,
                status = COALESCE(%s, status), -- Chỉ cập nhật status nếu được cung cấp
                os_info = %s,                -- Luôn cập nhật os_info
                macrodroid_version = %s      -- Luôn cập nhật macrodroid_version
            WHERE device_id = %s;
        """
        params = (
            device_name.strip() if device_name else None,
            notes.strip() if notes else None,
            status.strip() if status else None, # Chỉ cập nhật status nếu admin chọn
            os_info.strip() if os_info else None,             # <<< Thêm giá trị mới
            macrodroid_version.strip() if macrodroid_version else None, # <<< Thêm giá trị mới
            device_id
        )
        cur.execute(sql, params)
        conn.commit()
        success = cur.rowcount > 0
        if not success:
            error_msg = f"Không tìm thấy Device ID '{device_id}' để cập nhật hoặc không có gì thay đổi."
    # ... (phần except và finally giữ nguyên) ...
    except psycopg2.Error as e:
        error_msg = f"Lỗi CSDL khi cập nhật device: {e}"; log_func = current_app.logger.error if current_app else print; log_func(error_msg, exc_info=True); conn.rollback()
    except Exception as e:
        error_msg = f"Lỗi không xác định khi cập nhật device: {e}"; log_func = current_app.logger.error if current_app else print; log_func(error_msg, exc_info=True); conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success, error_msg

def delete_device(device_id: str) -> tuple[bool, str | None]:
    """Xóa một thiết bị (và các liên kết device_accounts, task_assignments liên quan do CASCADE)."""
    # ... (Code của hàm này đã được cung cấp trước đó) ...
    if not device_id: return False, "Device ID là bắt buộc."
    conn = get_db_connection()
    if not conn: return False, "Không thể kết nối CSDL."
    cur = None
    success = False; error_msg = None
    try:
        cur = conn.cursor()
        sql = "DELETE FROM public.devices WHERE device_id = %s;"
        cur.execute(sql, (device_id,))
        conn.commit()
        success = cur.rowcount > 0
        if not success: error_msg = f"Không tìm thấy Device ID '{device_id}' để xóa."
        else: current_app.logger.info(f"Deleted device {device_id} and associated data via CASCADE.")
    except psycopg2.Error as e:
        error_msg = f"Lỗi CSDL khi xóa device: {e}"; log_func = current_app.logger.error if current_app else print; log_func(error_msg, exc_info=True); conn.rollback()
    except Exception as e:
        error_msg = f"Lỗi không xác định khi xóa device: {e}"; log_func = current_app.logger.error if current_app else print; log_func(error_msg, exc_info=True); conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success, error_msg

# --- Thêm hàm lấy tất cả tài khoản cho dropdown ---
def get_all_accounts_for_select() -> list[dict] | None:
    """Lấy danh sách account (ID, Username, Platform) cho dropdown."""
    accounts = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        # Lấy các cột cần thiết, sắp xếp
        cur.execute("""
            SELECT account_id, username, platform
            FROM public.accounts
            ORDER BY platform, username, account_id;
        """)
        rows = cur.fetchall()
        accounts = [dict(row) for row in rows] if rows else []
    except Exception as e:
        current_app.logger.error(f"Error getting all accounts for select: {e}", exc_info=True)
        accounts = None
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return accounts

# ============================================================
# === HÀM LẤY DỮ LIỆU CHO DROPDOWNS (Form Add Task Assignment) ===
# ============================================================

def get_all_devices_for_select() -> list[dict] | None:
    """Lấy danh sách device (ID và Name) cho dropdown."""
    devices = None
    conn = get_db_connection() # Đảm bảo hàm get_db_connection tồn tại
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        # Lấy ID và Name, sắp xếp theo tên hoặc ID
        cur.execute("""
            SELECT device_id, device_name
            FROM public.devices
            ORDER BY device_name NULLS LAST, device_id;
        """)
        rows = cur.fetchall()
        # Trả về list các dict, mỗi dict có key 'device_id' và 'device_name'
        devices = [dict(row) for row in rows] if rows else []
    except Exception as e:
        log_func = current_app.logger.error if current_app else print
        log_func(f"Error getting all devices for select: {e}", exc_info=True)
        devices = None # Trả về None nếu có lỗi
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return devices

# --- Đảm bảo hàm này cũng tồn tại (đã cung cấp trước đó) ---
def get_accounts_for_device_select(device_id: str) -> list[dict] | None:
    """Lấy danh sách tài khoản liên kết với một device (ID, Username, Platform, device_account_id) cho dropdown động."""
    if not device_id: return None
    accounts = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        sql = """
            SELECT da.device_account_id, da.account_id, acc.username, acc.platform
            FROM public.device_accounts da
            JOIN public.accounts acc ON da.account_id = acc.account_id
            WHERE da.device_id = %s
            ORDER BY acc.platform, acc.username, da.account_id;
        """
        cur.execute(sql, (device_id,))
        rows = cur.fetchall()
        # Trả về list các dict, mỗi dict có các key cần thiết cho JS và hiển thị
        accounts = [dict(row) for row in rows] if rows else []
    except Exception as e:
        log_func = current_app.logger.error if current_app else print
        log_func(f"Error getting accounts for device {device_id}: {e}", exc_info=True)
        accounts = None
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return accounts

# ======================================================
# === HÀM MỚI CHO QUẢN LÝ LIÊN KẾT DEVICE-ACCOUNT ===
# ======================================================

def get_accounts_linked_to_device(device_id: str) -> list[dict] | None:
    """
    Lấy danh sách các tài khoản (kèm thông tin chi tiết) đã được liên kết
    với một thiết bị cụ thể.
    """
    if not device_id: return None
    linked_accounts = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        # Join 3 bảng: device_accounts, accounts, devices (devices để chắc chắn device_id tồn tại)
        sql = """
            SELECT
                da.device_account_id,
                da.account_id,
                acc.username,
                acc.platform,
                acc.status as account_status, -- Trạng thái chung của account
                da.clone_context,
                da.app_package_name,
                da.status as link_status, -- Trạng thái của liên kết trên device này
                da.last_check_at,
                da.notes as link_notes
            FROM public.device_accounts da
            JOIN public.accounts acc ON da.account_id = acc.account_id
            WHERE da.device_id = %s
            ORDER BY acc.platform, acc.username, da.account_id;
        """
        cur.execute(sql, (device_id,))
        rows = cur.fetchall()
        linked_accounts = [dict(row) for row in rows] if rows else []
    except Exception as e:
        log_func = current_app.logger.error if current_app else print
        log_func(f"Error getting linked accounts for device {device_id}: {e}", exc_info=True)
        linked_accounts = None # Trả về None nếu lỗi DB
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return linked_accounts

def link_device_account(device_id: str, account_id: str, clone_context: str | None,
                        app_package_name: str | None, status: str) -> tuple[bool, str | None]:
    """Tạo liên kết mới giữa device và account trong device_accounts."""
    if not device_id or not account_id or not status:
        return False, "Device ID, Account ID, và Status là bắt buộc."

    conn = get_db_connection()
    if not conn: return False, "Không thể kết nối CSDL."
    cur = None
    success = False
    error_msg = None
    try:
        cur = conn.cursor()
        sql = """
            INSERT INTO public.device_accounts
                (device_id, account_id, clone_context, app_package_name, status, last_check_at)
            VALUES (%s, %s, %s, %s, %s, NOW());
        """
        params = (
            device_id, account_id,
            clone_context.strip() if clone_context else None,
            app_package_name.strip() if app_package_name else None,
            status
        )
        cur.execute(sql, params)
        conn.commit()
        success = True
        current_app.logger.info(f"Linked account {account_id} to device {device_id}")
    except psycopg2.IntegrityError as e:
        # Lỗi UNIQUE (device_id, account_id) hoặc FK không tồn tại
        error_msg = f"Lỗi ràng buộc CSDL: Liên kết này đã tồn tại hoặc Device/Account ID không hợp lệ. ({e})"
        if conn: conn.rollback()
    except psycopg2.Error as e:
        error_msg = f"Lỗi CSDL khi liên kết device-account: {e}"
        current_app.logger.error(error_msg, exc_info=True)
        if conn: conn.rollback()
    except Exception as e:
        error_msg = f"Lỗi không xác định khi liên kết device-account: {e}"
        current_app.logger.error(error_msg, exc_info=True)
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success, error_msg

# ======================================================
# === HÀM CRUD CHO LIÊN KẾT DEVICE-ACCOUNT (ADMIN) ===
# ======================================================

def get_device_account_link_details(device_account_id: int) -> dict | None:
    """Lấy chi tiết một bản ghi liên kết device_account bằng ID của nó."""
    if not device_account_id: return None
    details = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        # Lấy tất cả các cột từ device_accounts và join để lấy thêm thông tin nếu cần
        sql = """
            SELECT da.*, d.device_name, acc.username, acc.platform
            FROM public.device_accounts da
            JOIN public.devices d ON da.device_id = d.device_id
            JOIN public.accounts acc ON da.account_id = acc.account_id
            WHERE da.device_account_id = %s;
            """
        cur.execute(sql, (device_account_id,))
        row = cur.fetchone()
        if row:
            details = dict(row)
    except Exception as e:
        log_func = current_app.logger.error if current_app else print
        log_func(f"Error getting device_account link details for ID {device_account_id}: {e}", exc_info=True)
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return details


def update_device_account_link(device_account_id: int, clone_context: str | None,
                               app_package_name: str | None, status: str, notes: str | None) -> tuple[bool, str | None]:
    """Cập nhật thông tin cho một liên kết device_account."""
    if not device_account_id or not status:
        return False, "Link ID và Status là bắt buộc."

    # Các status hợp lệ có thể lấy từ config hoặc định nghĩa ở đây
    valid_link_statuses = ['active_logged_in', 'login_required', 'unknown', 'error', 'inactive']
    if status not in valid_link_statuses:
        return False, f"Trạng thái liên kết '{status}' không hợp lệ."

    conn = get_db_connection()
    if not conn: return False, "Không thể kết nối CSDL."
    cur = None
    success = False
    error_msg = None
    try:
        cur = conn.cursor()
        sql = """
            UPDATE public.device_accounts
            SET clone_context = %s,
                app_package_name = %s,
                status = %s,
                notes = %s,
                last_check_at = NOW() -- Cập nhật thời gian kiểm tra/sửa đổi
            WHERE device_account_id = %s;
        """
        params = (
            clone_context.strip() if clone_context else None,
            app_package_name.strip() if app_package_name else None,
            status,
            notes.strip() if notes else None,
            device_account_id
        )
        cur.execute(sql, params)
        conn.commit()
        success = cur.rowcount > 0
        if not success:
            error_msg = f"Không tìm thấy liên kết ID {device_account_id} để cập nhật."
        else:
            current_app.logger.info(f"Updated device_account link ID: {device_account_id}")

    except psycopg2.Error as e:
        error_msg = f"Lỗi CSDL khi cập nhật liên kết device-account: {e}"
        log_func = current_app.logger.error if current_app else print; log_func(error_msg, exc_info=True); conn.rollback()
    except Exception as e:
        error_msg = f"Lỗi không xác định khi cập nhật liên kết device-account: {e}"
        log_func = current_app.logger.error if current_app else print; log_func(error_msg, exc_info=True); conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success, error_msg


def unlink_device_account(device_account_id: int) -> tuple[bool, str | None]:
    """Xóa một liên kết device-account bằng ID của nó."""
    if not device_account_id: return False, "Link ID là bắt buộc."

    conn = get_db_connection()
    if not conn: return False, "Không thể kết nối CSDL."
    cur = None
    success = False
    error_msg = None
    try:
        cur = conn.cursor()
        sql = "DELETE FROM public.device_accounts WHERE device_account_id = %s;"
        cur.execute(sql, (device_account_id,))
        conn.commit()
        success = cur.rowcount > 0
        if not success:
            error_msg = f"Không tìm thấy liên kết ID {device_account_id} để xóa."
        else:
            current_app.logger.info(f"Unlinked device_account ID: {device_account_id}")
    except psycopg2.Error as e:
        # Xóa liên kết ít khi bị lỗi FK, trừ khi task_assignments không đặt ON DELETE CASCADE/SET NULL đúng
        error_msg = f"Lỗi CSDL khi hủy liên kết: {e}"
        log_func = current_app.logger.error if current_app else print; log_func(error_msg, exc_info=True); conn.rollback()
    except Exception as e:
        error_msg = f"Lỗi không xác định khi hủy liên kết: {e}"
        log_func = current_app.logger.error if current_app else print; log_func(error_msg, exc_info=True); conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success, error_msg

# ======================================================
# === HÀM CRUD CHO TASK ASSIGNMENT (ADMIN) ===
# ======================================================

# ... (Các hàm get_all_task_assignments, add_task_assignment đã có) ...

def delete_task_assignment(assignment_id: int) -> tuple[bool, str | None]:
    """Xóa một task assignment bằng ID.
       Lưu ý: Log liên quan trong phone_action_log sẽ không bị xóa
       nhưng cột assignment_id của chúng sẽ thành NULL do FK constraint.
    """
    if not assignment_id: return False, "Assignment ID là bắt buộc."

    conn = get_db_connection()
    if not conn: return False, "Không thể kết nối CSDL."
    cur = None
    success = False
    error_msg = None
    try:
        cur = conn.cursor()
        sql = "DELETE FROM public.task_assignments WHERE assignment_id = %s;"
        cur.execute(sql, (assignment_id,))
        conn.commit()
        affected_rows = cur.rowcount
        success = affected_rows > 0
        if not success:
            error_msg = f"Không tìm thấy Task Assignment ID {assignment_id} để xóa."
        else:
            current_app.logger.info(f"Deleted task assignment ID: {assignment_id}")

    except psycopg2.Error as e:
        error_msg = f"Lỗi CSDL khi xóa task assignment: {e}"
        log_func = current_app.logger.error if current_app else print; log_func(error_msg, exc_info=True); conn.rollback()
    except Exception as e:
        error_msg = f"Lỗi không xác định khi xóa task assignment: {e}"
        log_func = current_app.logger.error if current_app else print; log_func(error_msg, exc_info=True); conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success, error_msg

def get_assignment_logs(assignment_id: int, page: int = 1, per_page: int = 50) -> tuple[list[dict] | None, int | None]:
    """
    Lấy danh sách các bản ghi log thuộc về một assignment, có phân trang.
    Bao gồm cả cột received_state_json.

    Args:
        assignment_id: ID của task assignment.
        page: Số trang hiện tại.
        per_page: Số log mỗi trang.

    Returns:
        Tuple: (list các log của trang hoặc None nếu lỗi, tổng số log hoặc None nếu lỗi)
    """
    logger = current_app.logger if current_app else print
    if not assignment_id:
        logger.warning("get_assignment_logs: Thiếu assignment_id.")
        return None, None

    logs = None
    total_items = None
    conn = get_db_connection()
    if not conn: return None, None
    cur = None

    try:
        # Query đếm tổng số log cho assignment này
        cur = conn.cursor()
        count_sql = "SELECT COUNT(*) FROM public.phone_action_log WHERE assignment_id = %s;"
        cur.execute(count_sql, (assignment_id,))
        total_items = cur.fetchone()[0]
        cur.close() # Đóng cursor đếm

        # Query lấy dữ liệu log của trang hiện tại
        logs = [] # Khởi tạo list rỗng
        if total_items is not None and total_items > 0:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor) # Dùng DictCursor
            offset = (page - 1) * per_page
            # <<< SELECT cột received_state_json >>>
            data_sql = """
                SELECT log_id, "timestamp", current_stage, action_macro_code,
                       params_json, execution_status, execution_error, received_state_json
                FROM public.phone_action_log
                WHERE assignment_id = %s
                ORDER BY "timestamp" DESC, log_id DESC -- Sắp xếp mới nhất lên đầu
                LIMIT %s OFFSET %s;
            """
            cur.execute(data_sql, (assignment_id, per_page, offset))
            rows = cur.fetchall()
            logs = [dict(row) for row in rows] if rows else []

            # Xử lý hậu kỳ nếu cần (DictCursor thường xử lý JSONB tốt)
            for log_entry in logs:
                # Đảm bảo params_json là dict hoặc None/{}
                if log_entry.get('params_json') and isinstance(log_entry['params_json'], str):
                    try: log_entry['params_json'] = json.loads(log_entry['params_json'])
                    except: log_entry['params_json'] = {"error": "invalid JSON string in DB"}
                elif not isinstance(log_entry.get('params_json'), dict):
                    log_entry['params_json'] = {}

                # Đảm bảo received_state_json là dict hoặc None/{}
                if log_entry.get('received_state_json') and isinstance(log_entry['received_state_json'], str):
                    try: log_entry['received_state_json'] = json.loads(log_entry['received_state_json'])
                    except: log_entry['received_state_json'] = {"error": "invalid JSON string in DB"}
                elif not isinstance(log_entry.get('received_state_json'), dict):
                     log_entry['received_state_json'] = None # Để None nếu không phải dict

    except psycopg2.Error as db_err:
        logger.error(f"Lỗi DB khi lấy logs cho assignment {assignment_id}: {db_err}", exc_info=True)
        logs, total_items = None, None
    except Exception as e:
        logger.error(f"Lỗi không xác định khi lấy logs cho assignment {assignment_id}: {e}", exc_info=True)
        logs, total_items = None, None
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return logs, total_items

def update_task_assignment(assignment_id: int, update_data: dict) -> tuple[bool, str | None]:
    """
    Cập nhật các trường cho phép sửa đổi của một task assignment.

    Args:
        assignment_id: ID của assignment cần cập nhật.
        update_data: Dict chứa các cặp key-value cần cập nhật.
                     Các key hợp lệ ví dụ: 'priority', 'schedule_start_time',
                     'schedule_end_time', 'target_data', 'notes', 'status'.

    Returns:
        Tuple (bool, str | None): (True nếu thành công, None) hoặc (False, thông báo lỗi).
    """
    if not assignment_id or not update_data:
        return False, "Cần Assignment ID và dữ liệu cập nhật."

    conn = get_db_connection()
    if not conn: return False, "Không thể kết nối CSDL."
    cur = None
    success = False
    error_msg = None

    # --- Xây dựng câu lệnh UPDATE động ---
    set_parts = []
    params = []
    # Các cột được phép cập nhật từ form Sửa
    allowed_columns = {
        'priority': 'priority = %s',
        'schedule_start_time': 'schedule_start_time = %s',
        'schedule_end_time': 'schedule_end_time = %s',
        'target_data': 'target_data = %s::jsonb', # Ép kiểu JSONB
        'notes': 'notes = %s',
        'status': 'status = %s' # Cho phép sửa status nếu muốn (vd: Pause/Resume)
    }
    # Các status hợp lệ nếu cho sửa
    valid_statuses_if_edit = ['pending', 'paused', 'cancelled'] # Ví dụ

    for key, value in update_data.items():
        if key in allowed_columns:
            # Validate dữ liệu trước khi thêm vào câu lệnh
            param_value = None
            valid = True
            if key == 'priority':
                try: param_value = int(value)
                except (ValueError, TypeError): valid = False; error_msg = "Độ ưu tiên phải là số."
            elif key in ['schedule_start_time', 'schedule_end_time']:
                if isinstance(value, datetime): param_value = value # Nếu đã là datetime
                elif isinstance(value, str) and value:
                    try: param_value = datetime.fromisoformat(value)
                    except ValueError: valid = False; error_msg = f"Định dạng thời gian {key} không hợp lệ."
                else: param_value = None # Cho phép xóa thời gian
            elif key == 'target_data':
                 if isinstance(value, dict): param_value = json.dumps(value) # Nếu là dict, chuyển sang JSON string
                 elif isinstance(value, str) and value.strip() and value.strip() != '{}':
                     try:
                         parsed_json = json.loads(value) # Validate JSON string
                         if not isinstance(parsed_json, dict): raise ValueError()
                         param_value = value # Lưu dạng string nếu hợp lệ
                     except: valid = False; error_msg = "Target Data phải là JSON object hợp lệ."
                 else: param_value = None # Cho phép xóa trắng target_data
            elif key == 'status':
                param_value = value.strip() if isinstance(value, str) else None
                if not param_value or param_value not in valid_statuses_if_edit: # Kiểm tra status hợp lệ
                    valid = False; error_msg = f"Trạng thái '{param_value}' không hợp lệ hoặc không được phép sửa."
            else: # notes
                 param_value = value.strip() if isinstance(value, str) and value.strip() else None

            if valid:
                set_parts.append(allowed_columns[key])
                params.append(param_value)
            else:
                # Nếu có một trường không hợp lệ, dừng lại và báo lỗi
                 current_app.logger.warning(f"Invalid update data for assignment {assignment_id}: Key='{key}', Value='{value}', Reason: {error_msg}")
                 return False, error_msg # Trả về lỗi validation

    if not set_parts:
        return False, "Không có trường hợp lệ nào được cung cấp để cập nhật."

    # --- Thực thi UPDATE ---
    try:
        cur = conn.cursor()
        set_sql = ", ".join(set_parts)
        sql = f"UPDATE public.task_assignments SET {set_sql} WHERE assignment_id = %s;"
        params.append(assignment_id) # Thêm ID vào cuối cho WHERE

        cur.execute(sql, tuple(params))
        conn.commit()
        success = cur.rowcount > 0 # Thành công nếu có ít nhất 1 dòng bị ảnh hưởng
        if not success:
            error_msg = f"Không tìm thấy Task Assignment ID {assignment_id} hoặc không có gì thay đổi."
        else:
            current_app.logger.info(f"Updated task assignment ID: {assignment_id} with data: {update_data}")

    except psycopg2.Error as e:
        error_msg = f"Lỗi CSDL khi cập nhật task assignment: {e}"
        log_func = current_app.logger.error if current_app else print; log_func(error_msg, exc_info=True); conn.rollback()
    except Exception as e:
        error_msg = f"Lỗi không xác định khi cập nhật task assignment: {e}"
        log_func = current_app.logger.error if current_app else print; log_func(error_msg, exc_info=True); conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return success, error_msg

def get_all_api_docs_paginated(page: int = 1, per_page: int = 15) -> tuple[list[dict] | None, int | None]:
    """
    Lấy danh sách TẤT CẢ CHI TIẾT của các tài liệu API đã được kích hoạt,
    có phân trang. Dùng để hiển thị bảng list và cung cấp data cho modal.

    Args:
        page: Số trang hiện tại.
        per_page: Số lượng mục mỗi trang.

    Returns:
        Tuple: (list các dict chứa đầy đủ chi tiết API của trang hiện tại hoặc None nếu lỗi,
                tổng số API docs hoặc None nếu lỗi)
    """
    logger = current_app.logger if current_app else print
    docs = None
    total_items = None
    conn = get_db_connection()
    if not conn: return None, None
    cur = None

    try:
        # Query đếm tổng số mục đang active
        cur = conn.cursor()
        count_sql = "SELECT COUNT(*) FROM public.api_documentation WHERE is_active = true;"
        cur.execute(count_sql)
        total_items = cur.fetchone()[0]
        cur.close()

        # Query lấy dữ liệu chi tiết cho trang hiện tại
        docs = [] # Khởi tạo list rỗng
        if total_items is not None and total_items > 0:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor) # Dùng DictCursor
            offset = (page - 1) * per_page
            # Lấy tất cả các cột cần thiết cho cả list và details
            sql = """
                SELECT doc_id, endpoint_path, http_method, summary, description,
                       request_notes, request_example, response_notes,
                       success_response_example, error_response_example, notes, updated_at
                FROM public.api_documentation
                WHERE is_active = true
                ORDER BY endpoint_path, http_method -- Sắp xếp theo endpoint và method
                LIMIT %s OFFSET %s;
            """
            cur.execute(sql, (per_page, offset))
            rows = cur.fetchall()
            docs = [dict(row) for row in rows] if rows else []
            logger.debug(f"Fetched {len(docs)} API docs for page {page}.")

    except psycopg2.Error as db_err:
        logger.error(f"DB Error fetching API docs: {db_err}", exc_info=True)
        docs, total_items = None, None
    except Exception as e:
        logger.error(f"Unexpected Error fetching API docs: {e}", exc_info=True)
        docs, total_items = None, None
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return docs, total_items

# --- API Documentation CRUD Functions ---

def add_api_doc(endpoint_path: str, http_method: str, summary: str,
                description: str | None, request_notes: str | None, request_example: str | None,
                response_notes: str | None, success_response_example: str | None,
                error_response_example: str | None, notes: str | None, is_active: bool = True) -> tuple[bool, str | None]:
    """Thêm một tài liệu API mới vào CSDL."""
    logger = current_app.logger if current_app else print
    if not endpoint_path or not http_method or not summary:
        return False, "Endpoint Path, HTTP Method, và Summary là bắt buộc."
    # Có thể thêm validation cho http_method

    conn = get_db_connection()
    if not conn: return False, "Không thể kết nối CSDL."
    cur = None
    success = False
    error_msg = None
    try:
        cur = conn.cursor()
        sql = """
            INSERT INTO public.api_documentation (
                endpoint_path, http_method, summary, description,
                request_notes, request_example, response_notes,
                success_response_example, error_response_example, notes, is_active,
                created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW());
        """
        params = (
            endpoint_path, http_method.upper(), summary, description,
            request_notes, request_example, response_notes,
            success_response_example, error_response_example, notes, is_active
        )
        cur.execute(sql, params)
        conn.commit()
        success = True
        logger.info(f"Added API documentation for endpoint: {http_method} {endpoint_path}")
    except psycopg2.IntegrityError:
        error_msg = f"Endpoint Path '{endpoint_path}' đã tồn tại."
        if conn: conn.rollback()
    except psycopg2.Error as e:
        error_msg = f"Lỗi CSDL khi thêm API doc: {e}"
        logger.error(error_msg, exc_info=True)
        if conn: conn.rollback()
    except Exception as e:
        error_msg = f"Lỗi không xác định khi thêm API doc: {e}"
        logger.error(error_msg, exc_info=True)
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success, error_msg

def get_api_doc_by_id(doc_id: int) -> dict | None:
    """Lấy chi tiết một tài liệu API bằng ID."""
    logger = current_app.logger if current_app else print
    if not doc_id: return None
    details = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        sql = "SELECT * FROM public.api_documentation WHERE doc_id = %s;"
        cur.execute(sql, (doc_id,))
        row = cur.fetchone()
        if row:
            details = dict(row)
        else:
            logger.warning(f"Không tìm thấy API Doc ID: {doc_id}")
    except Exception as e:
        logger.error(f"Lỗi khi lấy chi tiết API Doc ID {doc_id}: {e}", exc_info=True)
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return details

def update_api_doc(doc_id: int, endpoint_path: str, http_method: str, summary: str,
                   description: str | None, request_notes: str | None, request_example: str | None,
                   response_notes: str | None, success_response_example: str | None,
                   error_response_example: str | None, notes: str | None, is_active: bool) -> tuple[bool, str | None]:
    """Cập nhật một tài liệu API."""
    logger = current_app.logger if current_app else print
    if not doc_id or not endpoint_path or not http_method or not summary:
        return False, "Doc ID, Endpoint Path, HTTP Method, và Summary là bắt buộc."

    conn = get_db_connection()
    if not conn: return False, "Không thể kết nối CSDL."
    cur = None
    success = False
    error_msg = None
    try:
        cur = conn.cursor()
        sql = """
            UPDATE public.api_documentation SET
                endpoint_path = %s, http_method = %s, summary = %s, description = %s,
                request_notes = %s, request_example = %s, response_notes = %s,
                success_response_example = %s, error_response_example = %s, notes = %s,
                is_active = %s, updated_at = NOW()
            WHERE doc_id = %s;
        """
        params = (
            endpoint_path, http_method.upper(), summary, description,
            request_notes, request_example, response_notes,
            success_response_example, error_response_example, notes, is_active,
            doc_id
        )
        cur.execute(sql, params)
        conn.commit()
        success = cur.rowcount > 0
        if not success:
            error_msg = f"Không tìm thấy API Doc ID {doc_id} để cập nhật hoặc không có gì thay đổi."
        else:
            logger.info(f"Updated API documentation for endpoint: {http_method} {endpoint_path} (ID: {doc_id})")
    except psycopg2.IntegrityError:
        error_msg = f"Endpoint Path '{endpoint_path}' có thể đã bị trùng."
        if conn: conn.rollback()
    except psycopg2.Error as e:
        error_msg = f"Lỗi CSDL khi cập nhật API doc: {e}"
        logger.error(error_msg, exc_info=True)
        if conn: conn.rollback()
    except Exception as e:
        error_msg = f"Lỗi không xác định khi cập nhật API doc: {e}"
        logger.error(error_msg, exc_info=True)
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success, error_msg

def delete_api_doc(doc_id: int) -> tuple[bool, str | None]:
    """Xóa một tài liệu API."""
    logger = current_app.logger if current_app else print
    if not doc_id: return False, "Doc ID là bắt buộc."
    conn = get_db_connection()
    if not conn: return False, "Không thể kết nối CSDL."
    cur = None
    success = False
    error_msg = None
    try:
        cur = conn.cursor()
        sql = "DELETE FROM public.api_documentation WHERE doc_id = %s;"
        cur.execute(sql, (doc_id,))
        conn.commit()
        success = cur.rowcount > 0
        if not success:
            error_msg = f"Không tìm thấy API Doc ID {doc_id} để xóa."
        else:
            logger.info(f"Deleted API documentation ID: {doc_id}")
    except psycopg2.Error as e:
        error_msg = f"Lỗi CSDL khi xóa API doc: {e}"
        logger.error(error_msg, exc_info=True)
        if conn: conn.rollback()
    except Exception as e:
        error_msg = f"Lỗi không xác định khi xóa API doc: {e}"
        logger.error(error_msg, exc_info=True)
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success, error_msg

def update_device_mainloop_strategy(device_id: str, mainloop_strategy_id: str | None) -> tuple[bool, str | None]:
    """
    Cập nhật hoặc xóa chiến lược Main Loop được gán cho một thiết bị.

    Args:
        device_id: ID của thiết bị cần cập nhật.
        mainloop_strategy_id: ID (Text) của chiến lược Main Loop mới,
                              hoặc None/chuỗi rỗng để xóa gán (đặt thành NULL).

    Returns:
        Tuple (bool, str | None): (True, None) nếu thành công, (False, error_message) nếu thất bại.
    """
    logger = current_app.logger if current_app else print
    if not device_id:
        return False, "Device ID là bắt buộc."

    # Xử lý giá trị strategy ID: chuỗi rỗng hoặc None đều coi là muốn xóa gán (NULL)
    strategy_id_to_set = mainloop_strategy_id.strip() if isinstance(mainloop_strategy_id, str) and mainloop_strategy_id.strip() else None

    logger.info(f"Attempting to set mainloop_strategy for device '{device_id}' to '{strategy_id_to_set}'")

    conn = get_db_connection()
    if not conn: return False, "Không thể kết nối CSDL."
    cur = None
    success = False
    error_msg = None
    try:
        cur = conn.cursor()
        sql = """
            UPDATE public.devices
            SET mainloop_strategy_id = %s
            WHERE device_id = %s;
        """
        params = (strategy_id_to_set, device_id)
        cur.execute(sql, params)
        conn.commit()
        success = cur.rowcount > 0 # True nếu có dòng được cập nhật
        if not success:
            error_msg = f"Không tìm thấy Device ID '{device_id}' để cập nhật Main Loop Strategy."
            logger.warning(error_msg)
        else:
             logger.info(f"Successfully updated mainloop strategy for device '{device_id}'.")

    except psycopg2.IntegrityError as e:
        # Lỗi này có thể xảy ra nếu mainloop_strategy_id không tồn tại trong bảng strategies
        error_msg = f"Lỗi ràng buộc FK: Main Loop Strategy ID '{strategy_id_to_set}' không tồn tại?"
        logger.error(f"ERROR updating mainloop strategy for device '{device_id}': {error_msg} - {e}")
        if conn: conn.rollback()
    except psycopg2.Error as e:
        error_msg = f"Lỗi CSDL khi cập nhật Main Loop Strategy: {e}"
        logger.error(f"ERROR updating mainloop strategy for device '{device_id}': {error_msg}", exc_info=True)
        if conn: conn.rollback()
    except Exception as e:
        error_msg = f"Lỗi không xác định khi cập nhật Main Loop Strategy: {e}"
        logger.error(f"ERROR updating mainloop strategy for device '{device_id}': {error_msg}", exc_info=True)
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return success, error_msg

def get_stages_by_type(strategy_type: str) -> list[dict] | None:
    """
    Lấy danh sách các stage thuộc về các strategies có strategy_type cụ thể.
    Đã sửa ORDER BY để sắp xếp theo stage_id.
    """
    logger = current_app.logger if current_app else print
    if not strategy_type or strategy_type not in ['language', 'control', 'mainloop']:
        logger.warning(f"Invalid strategy_type '{strategy_type}' passed to get_stages_by_type.")
        return None

    stages_list = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        logger.debug(f"Fetching stages for strategy_type='{strategy_type}'...")
        # Join strategy_stages và strategies, lọc theo strategy_type
        sql = """
            SELECT ss.stage_id, ss.description, ss.strategy_id
            FROM public.strategy_stages ss
            JOIN public.strategies s ON ss.strategy_id = s.strategy_id
            WHERE s.strategy_type = %s
            ORDER BY ss.stage_id; -- <<< SỬA Ở ĐÂY: Chỉ sort theo stage_id
        """
        cur.execute(sql, (strategy_type,))
        rows = cur.fetchall()
        stages_list = [dict(row) for row in rows] if rows else []
        logger.debug(f"Found {len(stages_list)} stages for type '{strategy_type}'.")

    except psycopg2.Error as db_err:
        logger.error(f"DB Error fetching stages by type '{strategy_type}': {db_err}", exc_info=True)
        stages_list = None
    except Exception as e:
        logger.error(f"Unexpected error fetching stages by type '{strategy_type}': {e}", exc_info=True)
        stages_list = None
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return stages_list





def add_new_rule(strategy_id: str, keywords: str, category: str | None, template_ref: str | None, priority: int = 0, notes: str | None = None) -> bool:
    """Thêm một luật mới vào bảng 'rules'."""
    if not strategy_id or not keywords: # Cần cả strategy_id và keywords
        print("ERROR (add_new_rule): strategy_id and keywords are required.")
        return False
    # Có thể cho phép template_ref là None nếu luật đó chỉ dùng để chuyển stage chẳng hạn
    # if not template_ref:
    #     print("ERROR (add_new_rule): template_ref is required.")
    #     return False

    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        print(f"DEBUG (database.py): Thêm rule mới cho strategy '{strategy_id}': keywords='{keywords[:50]}...', category='{category}', ref='{template_ref}'")
        # === SỬA TÊN BẢNG VÀ THÊM CỘT strategy_id ===
        # Bỏ ON CONFLICT vì chưa rõ constraint UNIQUE mới là gì
        sql = """
            INSERT INTO public.rules
            (strategy_id, trigger_keywords, category, response_template_ref, priority, notes, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW());
        """
        params = (strategy_id, keywords, category, template_ref, priority, notes)
        # =============================================
        cur.execute(sql, params)
        conn.commit()
        success = True
        print(f"DEBUG (database.py): Added new rule successfully.")
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


def get_filtered_rules(filters: dict = None, page: int = 1, per_page: int = 30) -> tuple[list[dict] | None, int | None]:
    """Lấy danh sách luật đã lọc từ bảng 'rules' với phân trang."""
    # ... (Code bên trong hàm này đã được sửa ở phản hồi trước - đảm bảo dùng bảng 'rules') ...
    rules_list = None
    total_items = None
    conn = get_db_connection()
    if not conn: return None, None
    cur = None
    where_clauses = []
    params = []
    if filters:
        if filters.get('keywords'):
            where_clauses.append("trigger_keywords ILIKE %s")
            params.append(f"%{filters['keywords']}%")
        if filters.get('category'):
            where_clauses.append("category = %s")
            params.append(filters['category'])
        if filters.get('template_ref'):
            where_clauses.append("response_template_ref = %s")
            params.append(filters['template_ref'])
    where_sql = ""
    if where_clauses: where_sql = "WHERE " + " AND ".join(where_clauses)
    try:
        cur = conn.cursor()
        count_sql = f"SELECT COUNT(*) FROM public.rules {where_sql};" # SỬA: Dùng bảng rules
        cur.execute(count_sql, tuple(params))
        total_items = cur.fetchone()[0]
        cur.close()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        offset = (page - 1) * per_page
        data_sql = f"""
            SELECT rule_id, trigger_keywords, category, response_template_ref, priority, notes
            FROM public.rules           -- <<< SỬA: Dùng bảng rules
            {where_sql}
            ORDER BY rule_id ASC
            LIMIT %s OFFSET %s;
        """
        data_params = params + [per_page, offset]
        cur.execute(data_sql, tuple(data_params))
        rows = cur.fetchall()
        rules_list = [dict(row) for row in rows] if rows else []
    except psycopg2.Error as db_err:
        print(f"LỖI (db - get_filtered_rules): {db_err}")
        rules_list, total_items = None, None
    except Exception as e:
        print(f"LỖI (db - get_filtered_rules): {e}")
        rules_list, total_items = None, None
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return rules_list, total_items


def get_rule_by_id(rule_id: int) -> dict | None:
    """Lấy chi tiết một luật trong bảng 'rules' bằng ID."""
    # ... (Code bên trong hàm này đã được sửa ở phản hồi trước - đảm bảo dùng bảng 'rules') ...
    if not rule_id: return None
    rule = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("""
            SELECT rule_id, trigger_keywords, category, response_template_ref, priority, notes
            FROM public.rules      -- <<< SỬA: Dùng bảng rules
            WHERE rule_id = %s;
            """, (rule_id,))
        row = cur.fetchone()
        if row: rule = dict(row)
    except psycopg2.Error as db_err: print(f"LỖI (db - get_rule_by_id): {db_err}"); rule = None
    except Exception as e: print(f"LỖI (db - get_rule_by_id): {e}"); rule = None
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return rule

# === SỬA LẠI SIGNATURE VÀ SQL (Bỏ strategy_id) ===
def update_rule(rule_id: int, keywords: str, category: str | None, template_ref: str | None, priority: int, notes: str | None) -> bool:
    """Cập nhật một luật trong bảng 'rules'."""
    if not rule_id or not keywords:
        return False
    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        sql = """
            UPDATE public.rules           -- <<< SỬA: Dùng bảng rules
            SET trigger_keywords = %s, category = %s, response_template_ref = %s, priority = %s, notes = %s, updated_at = NOW()
            WHERE rule_id = %s;
        """
        params = (keywords, category, template_ref, priority, notes, rule_id) # <<< Bỏ strategy_id
        cur.execute(sql, params)
        conn.commit()
        success = cur.rowcount > 0
    # ... (Phần except và finally giữ nguyên) ...
    except psycopg2.Error as db_err: print(f"LỖI (db - update_rule): {db_err}"); conn.rollback()
    except Exception as e: print(f"LỖI (db - update_rule): {e}"); conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success

def delete_rule(rule_id: int) -> bool:
    """Xóa một luật khỏi bảng 'rules'."""
    # ... (Code bên trong hàm này đã được sửa ở phản hồi trước - đảm bảo dùng bảng 'rules') ...
    if not rule_id: return False
    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        sql = "DELETE FROM public.rules WHERE rule_id = %s;" # <<< SỬA: Dùng bảng rules
        cur.execute(sql, (rule_id,))
        conn.commit()
        success = cur.rowcount > 0
    except psycopg2.Error as db_err: print(f"LỖI (db - delete_rule): {db_err}"); conn.rollback()
    except Exception as e: print(f"LỖI (db - delete_rule): {e}"); conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success

# === SỬA LẠI SIGNATURE VÀ SQL (Bỏ strategy_id) ===
def add_new_rule(keywords: str, category: str | None, template_ref: str | None, priority: int = 0, notes: str | None = None) -> bool:
    """Thêm một luật mới vào bảng 'rules'."""
    if not keywords:
        print("ERROR (add_new_rule): keywords are required.")
        return False
    # Bỏ kiểm tra template_ref bắt buộc vì có thể không cần
    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        # Bỏ constraint ON CONFLICT vì chưa chắc đã đúng
        sql = """
            INSERT INTO public.rules
            (trigger_keywords, category, response_template_ref, priority, notes, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, NOW(), NOW());
        """
        params = (keywords, category, template_ref, priority, notes) # <<< Bỏ strategy_id
        cur.execute(sql, params)
        conn.commit()
        success = True
    # ... (Phần except và finally giữ nguyên) ...
    except psycopg2.Error as db_err: print(f"LỖI (db - add_new_rule): {db_err}"); conn.rollback()
    except Exception as e: print(f"LỖI (db - add_new_rule): {e}"); conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success

def get_distinct_rule_categories() -> list[str] | None:
    """Lấy danh sách category duy nhất từ bảng 'rules'."""
    # ... (Code bên trong hàm này đã được sửa ở phản hồi trước - đảm bảo dùng bảng 'rules') ...
    categories = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor()
        sql = "SELECT DISTINCT category FROM public.rules WHERE category IS NOT NULL AND category <> '' ORDER BY category;" # <<< SỬA: Dùng bảng rules
        cur.execute(sql)
        rows = cur.fetchall()
        categories = [row[0] for row in rows] if rows else []
    except Exception as e: print(f"Lỗi lấy distinct rule categories: {e}"); categories = None
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return categories

def get_distinct_rule_template_refs() -> list[str] | None:
    """Lấy danh sách template_ref duy nhất từ bảng 'rules'."""
    # ... (Code bên trong hàm này đã được sửa ở phản hồi trước - đảm bảo dùng bảng 'rules') ...
    refs = None
    conn = get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor()
        sql = "SELECT DISTINCT response_template_ref FROM public.rules WHERE response_template_ref IS NOT NULL ORDER BY response_template_ref;" # <<< SỬA: Dùng bảng rules
        cur.execute(sql)
        rows = cur.fetchall()
        refs = [row[0] for row in rows] if rows else []
    except Exception as e: print(f"Lỗi lấy distinct rule template refs: {e}"); refs = None
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return refs

def delete_all_interaction_history() -> tuple[bool, str | None]:
    """Xóa TOÀN BỘ dữ liệu khỏi bảng interaction_history. Rất nguy hiểm!"""
    logger = current_app.logger if current_app else print
    logger.warning("Executing delete_all_interaction_history! This will clear the table.")

    conn = get_db_connection()
    if not conn:
        return False, "Không thể kết nối CSDL."

    cur = None
    success = False
    error_msg = None

    try:
        cur = conn.cursor()
        # Dùng TRUNCATE thường nhanh hơn DELETE FROM cho bảng lớn và reset sequence (nếu có)
        # cur.execute("DELETE FROM public.interaction_history;")
        cur.execute("TRUNCATE TABLE public.interaction_history RESTART IDENTITY;") # RESTART IDENTITY để reset ID về 1 (tùy chọn)
        conn.commit()
        success = True
        logger.info("TRUNCATED interaction_history table successfully.")
    except psycopg2.Error as db_err:
        error_msg = f"Lỗi CSDL khi xóa interaction_history: {db_err}"
        logger.error(error_msg, exc_info=True)
        if conn: conn.rollback()
    except Exception as e:
        error_msg = f"Lỗi không xác định khi xóa interaction_history: {e}"
        logger.error(error_msg, exc_info=True)
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return success, error_msg
def get_last_reported_ui_state(device_id: str, account_id: str) -> dict | None:
    """
    Lấy dữ liệu UI state (dạng dict) gần nhất được báo cáo từ client
    cho một device_id và account_id cụ thể từ bảng phone_action_log.

    Args:
        device_id: ID của thiết bị.
        account_id: ID của tài khoản.

    Returns:
        Dictionary chứa dữ liệu UI state đã parse từ JSON,
        hoặc None nếu không tìm thấy log hợp lệ hoặc có lỗi.
    """
    logger = current_app.logger if current_app else print
    if not device_id or not account_id:
        logger.warning("get_last_reported_ui_state: Thiếu device_id hoặc account_id.")
        return None

    last_state_dict = None
    conn = get_db_connection() # Dùng hàm kết nối hiện có của bạn
    if not conn:
        logger.error("get_last_reported_ui_state: Không thể kết nối CSDL.")
        return None

    cur = None
    try:
        # Dùng DictCursor để dễ lấy cột bằng tên, nhưng không bắt buộc vì chỉ lấy 1 cột
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        # Truy vấn lấy cột received_state_json từ log gần nhất có giá trị này
        sql = """
            SELECT received_state_json
            FROM public.phone_action_log
            WHERE device_id = %s
              AND account_id = %s
              AND received_state_json IS NOT NULL -- Chỉ lấy những log có state
            ORDER BY "timestamp" DESC, log_id DESC -- Lấy log mới nhất
            LIMIT 1;
        """
        logger.debug(f"Executing query to get last UI state for device={device_id}, account={account_id}")
        cur.execute(sql, (device_id, account_id))
        row = cur.fetchone()

        if row and row['received_state_json']:
            # psycopg2 với JSONB thường tự trả về dict
            if isinstance(row['received_state_json'], dict):
                last_state_dict = row['received_state_json']
                logger.debug(f"Found last UI state (already dict): {str(last_state_dict)[:200]}...") # Log một phần
            elif isinstance(row['received_state_json'], str):
                # Nếu DB trả về string (ít khả năng với JSONB), thử parse
                try:
                    last_state_dict = json.loads(row['received_state_json'])
                    logger.debug(f"Found and parsed last UI state from string: {str(last_state_dict)[:200]}...")
                except json.JSONDecodeError as json_err:
                    logger.error(f"Failed to parse received_state_json string from DB: {json_err}. Value: {row['received_state_json']}")
            else:
                 logger.warning(f"Unexpected data type for received_state_json: {type(row['received_state_json'])}")

        else:
            logger.info(f"No recent log with UI state found for device={device_id}, account={account_id}.")

    except psycopg2.Error as db_err:
        logger.error(f"DB Error in get_last_reported_ui_state: {db_err}", exc_info=True)
    except Exception as e:
        logger.error(f"Unexpected Error in get_last_reported_ui_state: {e}", exc_info=True)
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return last_state_dict

def add_exploration_log(log_data):
    """Thêm một bản ghi log khám phá mới vào CSDL."""
    sql = """
        INSERT INTO exploration_logs (
            device_id, account_id, app_name, mapping_goal,
            previous_action, reported_ui_state, screen_id_generated,
            result_status, error_message, next_action_suggested, processed
        ) VALUES (
            %(device_id)s, %(account_id)s, %(app_name)s, %(mapping_goal)s,
            %(previous_action)s, %(reported_ui_state)s, %(screen_id_generated)s,
            %(result_status)s, %(error_message)s, %(next_action_suggested)s, FALSE
        ) RETURNING log_id;
    """
    conn = None
    log_id = None
    try:
        conn = get_db_connection() # Sử dụng hàm kết nối CSDL của bạn
        cur = conn.cursor()
        # Sử dụng Json adapter để xử lý dict thành JSONB
        cur.execute(sql, {
            'device_id': log_data.get('device_id'),
            'account_id': log_data.get('account_id'),
            'app_name': log_data.get('app_name'),
            'mapping_goal': log_data.get('mapping_goal'),
            'previous_action': Json(log_data.get('previous_action')),
            'reported_ui_state': Json(log_data.get('reported_ui_state')),
            'screen_id_generated': log_data.get('screen_id_generated'),
            'result_status': log_data.get('result_status'),
            'error_message': log_data.get('error_message'),
            'next_action_suggested': Json(log_data.get('next_action_suggested'))
        })
        log_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        print(f"Successfully added exploration log with ID: {log_id}") # Thêm log debug
    except (Exception, psycopg2.DatabaseError) as error:
        print(f"Error adding exploration log: {error}") # Log lỗi chi tiết
        # Cân nhắc rollback nếu có lỗi
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
    return log_id

def get_unprocessed_exploration_logs(limit=100):
    """Lấy các bản ghi log chưa được xử lý."""
    sql = "SELECT * FROM exploration_logs WHERE processed = FALSE ORDER BY timestamp ASC LIMIT %s;"
    conn = None
    logs = []
    try:
        conn = get_db_connection()
        # Dùng DictCursor để dễ dàng truy cập cột theo tên
        cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute(sql, (limit,))
        logs = cur.fetchall()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        print(f"Error fetching unprocessed exploration logs: {error}")
    finally:
        if conn:
            conn.close()
    return logs

def mark_exploration_logs_processed(log_ids):
    """Đánh dấu một danh sách các log là đã xử lý."""
    if not log_ids:
        return 0

    sql = "UPDATE exploration_logs SET processed = TRUE WHERE log_id = ANY(%s::int[]);"
    conn = None
    rows_updated = 0
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(sql, (log_ids,))
        rows_updated = cur.rowcount
        conn.commit()
        cur.close()
        print(f"Marked {rows_updated} exploration logs as processed.") # Thêm log debug
    except (Exception, psycopg2.DatabaseError) as error:
        print(f"Error marking exploration logs processed: {error}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
    return rows_updated

# Hàm này có thể cần điều chỉnh tùy theo logic xác nhận cụ thể
def query_transition_history(source_screen_id, action_details_str, target_screen_id, limit=20):
    """
    Query lịch sử của một transition cụ thể để hỗ trợ logic xác nhận.
    Lưu ý: So sánh JSONB có thể cần toán tử đặc biệt.
    """
    sql = """
        SELECT log_id, result_status, timestamp
        FROM exploration_logs
        WHERE screen_id_generated = %s
        AND previous_action ->> 'action_details' = %s -- Ví dụ: So sánh một phần của JSON
        -- AND <điều kiện kiểm tra screen_id đích dựa trên log tiếp theo hoặc phân tích state>
        ORDER BY timestamp DESC
        LIMIT %s;
    """
    conn = None
    history = []
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        # Cần logic phức tạp hơn để xác định target_screen_id từ log tiếp theo
        # Tạm thời query dựa trên source và action
        cur.execute(sql, (source_screen_id, action_details_str, limit))
        history = cur.fetchall()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        print(f"Error querying transition history: {error}")
    finally:
        if conn:
            conn.close()
    return history

def update_task_mapping_status(assignment_id: int, new_status: str) -> tuple[bool, str | None]:
    """Cập nhật trạng thái mapping ('active' hoặc 'paused') cho Task Assignment."""
    if new_status not in ['active', 'paused']:
        return False, f"Trạng thái '{new_status}' không hợp lệ."
    if assignment_id is None:
        return False, "Cần assignment_id."

    conn = None
    cur = None
    success = False
    error_msg = None
    # <<< SỬA CÂU SQL: Bỏ phần updated_at = NOW() >>>
    sql = "UPDATE task_assignments SET mapping_status = %s WHERE assignment_id = %s;"

    try:
        conn = get_db_connection()
        if not conn: return False, "Không thể kết nối CSDL."
        cur = conn.cursor()
        # <<< SỬA THAM SỐ: Chỉ còn new_status và assignment_id >>>
        cur.execute(sql, (new_status, assignment_id))

        if cur.rowcount > 0:
            conn.commit()
            success = True
            if current_app: current_app.logger.info(f"Updated mapping_status to '{new_status}' for assignment_id: {assignment_id}")
        else:
            error_msg = f"Không tìm thấy Assignment ID {assignment_id}."
            if conn: conn.rollback()
    except psycopg2.Error as db_err:
        error_msg = f"Lỗi CSDL: {db_err}"
        if current_app: current_app.logger.error(error_msg, exc_info=True)
        if conn: conn.rollback()
    except Exception as e:
        error_msg = f"Lỗi không xác định: {e}"
        if current_app: current_app.logger.error(error_msg, exc_info=True)
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success, error_msg



def get_active_task_for_device(device_id: str) -> dict | None:
    """
    Lấy thông tin task assignment đang hoạt động (assigned hoặc running)
    cho một device_id cụ thể, ưu tiên theo priority.

    Args:
        device_id: ID của thiết bị.

    Returns:
        Dictionary chứa thông tin task assignment hoặc None nếu không có task phù hợp.
    """
    if not device_id:
        return None

    task = None
    conn = None
    cur = None
    # Query tìm task có status là 'assigned' hoặc 'running' cho device_id này,
    # sắp xếp theo priority giảm dần (cao hơn được ưu tiên), sau đó theo created_at tăng dần (cũ hơn chạy trước)
    # Chỉ lấy 1 task phù hợp nhất.
    # Cần JOIN với device_accounts để liên kết device_id với assignment_id
    sql = """
        SELECT ta.*
        FROM public.task_assignments ta
        JOIN public.device_accounts da ON ta.device_account_id = da.device_account_id
        WHERE da.device_id = %s
          AND ta.status IN ('assigned', 'running') -- Chỉ lấy task đang chờ hoặc đang chạy
          AND (ta.schedule_start_time IS NULL OR ta.schedule_start_time <= NOW()) -- Kiểm tra thời gian bắt đầu (nếu có)
          AND (ta.schedule_end_time IS NULL OR ta.schedule_end_time > NOW())     -- Kiểm tra thời gian kết thúc (nếu có)
        ORDER BY ta.priority DESC, ta.created_at ASC
        LIMIT 1;
    """

    try:
        conn = get_db_connection()
        if not conn: return None
        cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute(sql, (device_id,))
        row = cur.fetchone()
        if row:
            task = dict(row)
            current_app.logger.debug(f"Found active task for device {device_id}: assignment_id={task.get('assignment_id')}, status={task.get('status')}")
        else:
             current_app.logger.debug(f"No active task found for device {device_id}")


    except psycopg2.Error as db_err:
        current_app.logger.error(f"DB Error getting active task for device {device_id}: {db_err}", exc_info=True)
    except Exception as e:
        current_app.logger.error(f"Unexpected Error getting active task for device {device_id}: {e}", exc_info=True)
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return task

def get_last_detailed_ui_state_for_screen(screen_id: str) -> dict | None:
    """
    Lấy dữ liệu UI state chi tiết (dạng dict) gần nhất được lưu trong
    phone_action_log mà có thể liên quan đến screen_id này.

    LƯU Ý: Logic hiện tại là tìm log gần nhất có received_state_json
    KHÔNG NULL cho BẤT KỲ device/account nào. Cần cải thiện để liên kết
    chính xác hơn với screen_id nếu có thể (ví dụ: thông qua assignment_id
    hoặc device/account liên quan đến screen đó).

    Args:
        screen_id: ID của màn hình (hiện tại chưa dùng trực tiếp để query log).

    Returns:
        Dictionary chứa dữ liệu UI state đã parse từ JSON,
        hoặc None nếu không tìm thấy log hợp lệ hoặc có lỗi.
    """
    logger = current_app.logger if current_app else print
    # TODO: Cần logic để lấy device_id/account_id liên quan đến screen_id này
    # Ví dụ: truy vấn Neo4j tìm node -> tìm cạnh vào -> lấy device/account từ log liên quan cạnh đó?
    # Tạm thời, chúng ta sẽ tìm log gần nhất có state không null BẤT KỲ.
    # Điều này có thể không chính xác nếu nhiều thiết bị đang chạy.
    # Cần cải thiện logic này sau.

    logger.warning(f"get_last_detailed_ui_state_for_screen: Current logic fetches the *absolute* latest log with UI state, not necessarily linked to screen_id '{screen_id}'. Needs improvement.")

    last_state_dict = None
    conn = get_db_connection() # Dùng hàm kết nối hiện có
    if not conn:
        logger.error("get_last_detailed_ui_state_for_screen: Cannot connect to DB.")
        return None

    cur = None
    try:
        # Dùng DictCursor để dễ lấy cột bằng tên
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        # Lấy received_state_json từ log gần nhất có giá trị này
        sql = """
            SELECT received_state_json
            FROM public.phone_action_log
            WHERE received_state_json IS NOT NULL
              AND jsonb_typeof(received_state_json) = 'object' -- Đảm bảo là object JSON
              AND received_state_json::text <> '{}'::text -- Đảm bảo không phải object rỗng
            ORDER BY "timestamp" DESC, log_id DESC -- Lấy log mới nhất
            LIMIT 1;
        """
        logger.debug(f"Executing query to get latest non-empty UI state log.")
        cur.execute(sql)
        row = cur.fetchone()

        if row and row['received_state_json']:
            # psycopg2 với JSONB thường tự trả về dict
            if isinstance(row['received_state_json'], dict):
                last_state_dict = row['received_state_json']
                # Kiểm tra xem có key 'elements' không
                if 'elements' not in last_state_dict:
                    logger.warning(f"Latest UI state log found (log_id unknown) does not contain 'elements' key.")
                    last_state_dict = None # Coi như không hợp lệ nếu thiếu elements
                else:
                    logger.debug(f"Found latest UI state log with elements.")

            # Không cần xử lý trường hợp string nữa vì đã ép kiểu JSONB
            # elif isinstance(row['received_state_json'], str): ...

            else:
                 logger.warning(f"Unexpected data type for received_state_json: {type(row['received_state_json'])}")

        else:
            logger.info(f"No recent log with non-empty UI state found in phone_action_log.")

    except psycopg2.Error as db_err:
        logger.error(f"DB Error in get_last_detailed_ui_state_for_screen: {db_err}", exc_info=True)
    except Exception as e:
        logger.error(f"Unexpected Error in get_last_detailed_ui_state_for_screen: {e}", exc_info=True)
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return last_state_dict

def upsert_element_classification(screen_id: str, element_id: str, identifier_type: str | None, classification: str, source: str = 'manual', notes: str | None = None) -> tuple[bool, str | None]:
        """
        Thêm mới hoặc cập nhật phân loại cho một element trên một màn hình.

        Args:
            screen_id: ID của màn hình.
            element_id: ID của element.
            identifier_type: Loại ID ('resource-id', 'content-desc', ...).
            classification: Phân loại mới.
            source: Nguồn ('manual' hoặc 'ai_suggested').
            notes: Ghi chú (tùy chọn).

        Returns:
            Tuple (bool, str | None): (True, None) nếu thành công, (False, error_message) nếu thất bại.
        """
        logger = current_app.logger if current_app else print
        if not screen_id or not element_id or not classification:
            return False, "Screen ID, Element ID, và Classification là bắt buộc."

        conn = get_db_connection()
        if not conn: return False, "Không thể kết nối CSDL."
        cur = None
        success = False
        error_msg = None

        # Câu lệnh UPSERT (INSERT ON CONFLICT UPDATE)
        sql = """
            INSERT INTO public.element_classifications
                (screen_id, element_id, identifier_type, classification, source, notes, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (screen_id, element_id) DO UPDATE SET
                identifier_type = EXCLUDED.identifier_type,
                classification = EXCLUDED.classification,
                source = EXCLUDED.source,
                notes = EXCLUDED.notes,
                updated_at = NOW();
        """
        params = (screen_id, element_id, identifier_type, classification, source, notes)

        try:
            cur = conn.cursor()
            logger.debug(f"Upserting classification for {screen_id} / {element_id} -> {classification}")
            cur.execute(sql, params)
            conn.commit()
            success = True
        except psycopg2.Error as db_err:
            error_msg = f"Lỗi CSDL khi lưu classification: {db_err}"
            logger.error(error_msg, exc_info=True)
            if conn: conn.rollback()
        except Exception as e:
            error_msg = f"Lỗi không xác định khi lưu classification: {e}"
            logger.error(error_msg, exc_info=True)
            if conn: conn.rollback()
        finally:
            if cur: cur.close()
            if conn: conn.close()

        return success, error_msg


def get_element_classifications_for_screen(screen_id: str) -> dict[str, dict] | None:
    """
    Lấy tất cả các phân loại và trạng thái ghi đè khám phá đã lưu cho một màn hình.

    Args:
        screen_id: ID của màn hình.

    Returns:
        Dictionary dạng {element_id: {'classification': str, 'override': bool|None}}
        hoặc None nếu lỗi. Trả về dict rỗng nếu không có dữ liệu.
    """
    logger = current_app.logger if current_app else print
    if not screen_id: return {}

    classifications_data = None
    conn = get_db_connection()
    if not conn: return None

    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        # === LẤY THÊM CỘT manual_explored_override ===
        sql = """
            SELECT element_id, classification, manual_explored_override
            FROM public.element_classifications
            WHERE screen_id = %s;
        """
        # ===========================================
        cur.execute(sql, (screen_id,))
        rows = cur.fetchall()
        # Chuyển kết quả thành dict {element_id: {classification: '...', override: ...}}
        classifications_data = {
            row['element_id']: {
                'classification': row['classification'],
                'override': row['manual_explored_override'] # Giá trị có thể là True, False, hoặc None
            } for row in rows
        } if rows else {}
        logger.debug(f"Fetched {len(classifications_data)} classifications/overrides for screen {screen_id}")

    except psycopg2.Error as db_err:
        logger.error(f"DB Error fetching classifications/overrides for screen {screen_id}: {db_err}", exc_info=True)
        classifications_data = None
    except Exception as e:
        logger.error(f"Unexpected error fetching classifications/overrides for screen {screen_id}: {e}", exc_info=True)
        classifications_data = None
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return classifications_data

def update_manual_explored_override(screen_id: str, element_id: str, override_status: bool | None) -> tuple[bool, str | None]:
    """
    Cập nhật trạng thái ghi đè khám phá thủ công cho một element.
    Sử dụng UPSERT để tạo bản ghi nếu chưa tồn tại.

    Args:
        screen_id: ID màn hình.
        element_id: ID element.
        override_status: Trạng thái mới (True, False, hoặc None để xóa ghi đè).

    Returns:
        Tuple (bool, str | None): (True, None) nếu thành công, (False, error_message) nếu thất bại.
    """
    logger = current_app.logger if current_app else print
    if not screen_id or not element_id:
        return False, "Screen ID và Element ID là bắt buộc."

    conn = get_db_connection()
    if not conn: return False, "Không thể kết nối CSDL."
    cur = None
    success = False
    error_msg = None

    # Câu lệnh UPSERT: Chèn nếu không có, cập nhật nếu có
    # Cần đặt giá trị mặc định cho classification nếu tạo mới
    sql = """
        INSERT INTO public.element_classifications
            (screen_id, element_id, classification, manual_explored_override, updated_at)
        VALUES (%s, %s, %s, %s, NOW())
        ON CONFLICT (screen_id, element_id) DO UPDATE SET
            manual_explored_override = EXCLUDED.manual_explored_override,
            updated_at = NOW();
    """
    # Giá trị classification mặc định nếu tạo mới bản ghi
    default_classification = 'unclassified'
    params = (screen_id, element_id, default_classification, override_status)

    try:
        cur = conn.cursor()
        logger.info(f"Updating manual_explored_override for {screen_id}/{element_id} to: {override_status}")
        cur.execute(sql, params)
        conn.commit()
        success = True
    except psycopg2.Error as db_err:
        error_msg = f"Lỗi CSDL khi cập nhật override status: {db_err}"
        logger.error(error_msg, exc_info=True)
        if conn: conn.rollback()
    except Exception as e:
        error_msg = f"Lỗi không xác định khi cập nhật override status: {e}"
        logger.error(error_msg, exc_info=True)
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return success, error_msg

# ... (Các hàm DB khác, bao gồm upsert_element_classification) ...
def get_screen_definitions_for_app(app_name: str, activity_name: str | None = None) -> list[dict] | None:
    """
    Lấy tất cả các cấu hình PIE cho một app_name và activity_name (tùy chọn).
    """
    conn = get_db_connection()
    if not conn:
        return None
    cur = None
    screen_defs = []
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        if activity_name:
            # Ưu tiên tìm cả app_name và activity_name
            sql = """
                SELECT definition_id, app_name, activity_name, logical_screen_name, 
                       defined_screen_id, identifying_elements_json, description
                FROM screen_definitions 
                WHERE app_name = %s AND activity_name = %s
                ORDER BY logical_screen_name;
            """
            cur.execute(sql, (app_name, activity_name))
        else:
            # Nếu không có activity_name, hoặc tìm theo activity_name không ra,
            # tìm các định nghĩa chỉ có app_name (activity_name IS NULL)
            sql = """
                SELECT definition_id, app_name, activity_name, logical_screen_name, 
                       defined_screen_id, identifying_elements_json, description
                FROM screen_definitions 
                WHERE app_name = %s AND activity_name IS NULL
                ORDER BY logical_screen_name;
            """
            cur.execute(sql, (app_name,))

        rows = cur.fetchall()
        for row in rows:
            screen_defs.append(dict(row))

        # Nếu tìm theo activity_name có kết quả thì trả về, nếu không thì thử tìm không activity_name
        if activity_name and not screen_defs:
            # current_app.logger.debug(f"No screen defs found for {app_name}/{activity_name}, trying with null activity.")
            sql_no_activity = """
                SELECT definition_id, app_name, activity_name, logical_screen_name, 
                       defined_screen_id, identifying_elements_json, description
                FROM screen_definitions 
                WHERE app_name = %s AND activity_name IS NULL
                ORDER BY logical_screen_name;
            """
            cur.execute(sql_no_activity, (app_name,))
            rows_no_activity = cur.fetchall()
            for row_na in rows_no_activity:
                screen_defs.append(dict(row_na))

        return screen_defs
    except Exception as e:
        # current_app.logger.error(f"Lỗi khi lấy screen_definitions cho app {app_name}: {e}", exc_info=True)
        # Sử dụng print nếu current_app.logger không có sẵn (ví dụ khi chạy script độc lập)
        print(f"Lỗi khi lấy screen_definitions cho app {app_name}: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        if cur: cur.close()
        if conn: conn.close()

def add_screen_definition(app_name: str, activity_name: str | None, 
                          logical_screen_name: str, defined_screen_id: str, 
                          identifying_elements_json: list, # Nhận list Python
                          description: str | None) -> tuple[bool, str | None, int | None]:
    """Thêm một định nghĩa PIE mới vào bảng screen_definitions.
    Trả về (success, error_message, new_definition_id).
    """
    conn = get_db_connection()
    if not conn:
        return False, "Không thể kết nối CSDL.", None
    cur = None
    # Validate identifying_elements_json là một list các dict
    if not isinstance(identifying_elements_json, list) or \
       not all(isinstance(item, dict) for item in identifying_elements_json):
        return False, "identifying_elements_json phải là một list các dictionary.", None

    try:
        # Chuyển list Python thành chuỗi JSON để lưu vào JSONB
        pie_json_str = json.dumps(identifying_elements_json)

        cur = conn.cursor()
        sql = """
            INSERT INTO screen_definitions 
                (app_name, activity_name, logical_screen_name, defined_screen_id, 
                 identifying_elements_json, description)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING definition_id;
        """
        cur.execute(sql, (app_name, activity_name if activity_name else None, 
                           logical_screen_name, defined_screen_id, 
                           pie_json_str, description if description else None))
        new_id = cur.fetchone()
        conn.commit()
        if new_id:
            # current_app.logger.info(f"Đã thêm screen_definition: {logical_screen_name}, ID: {new_id[0]}")
            return True, None, new_id[0]
        else:
            return False, "Không thể lấy ID sau khi insert.", None
    except psycopg2.IntegrityError as e:
        # current_app.logger.error(f"Lỗi IntegrityError khi thêm screen_definition: {e}")
        conn.rollback()
        error_msg = f"Lỗi CSDL: {e.diag.message_detail if e.diag else str(e)}. Có thể logical_screen_name hoặc defined_screen_id đã tồn tại."
        return False, error_msg, None
    except Exception as e:
        # current_app.logger.error(f"Lỗi khi thêm screen_definition: {e}", exc_info=True)
        conn.rollback()
        return False, f"Lỗi không xác định: {str(e)}", None
    finally:
        if cur: cur.close()
        if conn: conn.close()

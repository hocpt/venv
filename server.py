import os
import logging
from typing import Tuple, Optional, Dict, Any
import random
from flask import Flask, request, jsonify
import psycopg2
import psycopg2.extras # Để dùng DictCursor
from underthesea import word_tokenize # Thư viện NLP tiếng Việt
from dotenv import load_dotenv # Thư viện đọc file .env
import google.generativeai as genai

# --- Tải biến môi trường từ file .env ---
load_dotenv()

# --- Cấu hình Kết nối Database (Lấy từ biến môi trường) ---
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "automation")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD") # Lấy mật khẩu

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
# Cấu hình Gemini API Key
if GOOGLE_API_KEY:
    print("--- Các Model Có Sẵn (hỗ trợ generateContent) ---") # Không thụt lề
    try:                                                         # Không thụt lề
        genai.configure(api_key=GOOGLE_API_KEY)
        for m in genai.list_models():                             # Thụt vào 1 cấp (4 cách)
            if 'generateContent' in m.supported_generation_methods: # Thụt vào 2 cấp (8 cách)
                print(m.name)                                   # Thụt vào 3 cấp (12 cách)
    except Exception as list_err:                                 # Thụt vào 1 cấp (4 cách)
        print(f"Lỗi khi liệt kê model: {list_err}")            # Thụt vào 2 cấp (8 cách)
    print("-------------------------------------------------")
    
else:
    print("CẢNH BÁO: Biến môi trường GOOGLE_API_KEY chưa được đặt. Chức năng AI sẽ bị vô hiệu hóa.")
    
if not DB_PASSWORD:
    print("Lỗi: Biến môi trường DB_PASSWORD chưa được thiết lập.")
    # Có thể raise Exception ở đây hoặc thoát
    # exit(1)

# Hàm kết nối CSDL
def get_db_connection():
    conn = None # Khởi tạo conn là None
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            port=DB_PORT
        )
        print("INFO: Kết nối CSDL thành công.") # Thêm log
        return conn
    except psycopg2.Error as e:
        print(f"LỖI KẾT NỐI CSDL: {e}")
        # Đảm bảo conn là None nếu lỗi
        if conn:
             conn.close() # Đóng nếu lỡ mở được phần nào
        return None
    # Khối finally không cần thiết nếu dùng return trong try/except

# --- Khởi tạo Flask App ---
app = Flask(__name__)

# --- Route kiểm tra Server ---
@app.route('/')
def index():
    """Route cơ bản để kiểm tra server có hoạt động không."""
    return jsonify({"message": "Automation Server is running!"}), 200





# --- API Endpoint để nhận nội dung và tạo trả lời ---
@app.route('/receive_content_for_reply', methods=['POST'])
def handle_receive_content():
    reply_text = ""
    status = "error_unknown" # Trạng thái mặc định ban đầu
    conn = None
    cur = None
    history_id = None # ID của bản ghi log tương tác

    try:
        # 1. Nhận dữ liệu từ điện thoại
        data = request.get_json()
        if not data or 'received_text' not in data or 'account_id' not in data or 'app' not in data:
            print("LỖI: Dữ liệu gửi lên không hợp lệ hoặc thiếu trường.")
            return jsonify({"error": "Dữ liệu gửi lên không hợp lệ"}), 400

        account_id = data['account_id']
        app_name = data['app']
        received_text = data['received_text']
        thread_id = data.get('thread_id', None) # Lấy thread_id nếu có

        print(f"\n--- Nhận được yêu cầu mới ---")
        print(f"Account: {account_id}, App: {app_name}, Thread: {thread_id}")
        print(f"Input Text: '{received_text}'")

        # 2. Kết nối CSDL
        conn = get_db_connection()
        if conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor) # Dùng DictCursor để truy cập cột bằng tên
            print("DEBUG: Đã kết nối CSDL.")

            # 3. (Tùy chọn) Ghi log nội dung nhận được vào history
            try:
                 cur.execute("""
                     INSERT INTO interaction_history (account_id, app, thread_id, received_text, status)
                     VALUES (%s, %s, %s, %s, %s) RETURNING history_id;
                 """, (account_id, app_name, thread_id, received_text, 'received'))
                 history_id = cur.fetchone()['history_id']
                 conn.commit()
                 print(f"DEBUG: Đã ghi log nhận: ID {history_id}")
            except psycopg2.Error as log_err:
                conn.rollback()
                print(f"LỖI ghi log nhận: {log_err}")
                # Không dừng lại nếu chỉ lỗi ghi log, nhưng nên báo lỗi

            # 4. Phân tích Chủ đề (Ví dụ đơn giản, bạn có thể bỏ qua bước này ban đầu)
            detected_topic = None # Tạm thời chưa phân loại chủ đề
            # TODO: Thêm logic phát hiện chủ đề ở đây nếu muốn (dùng bảng topic_definitions)

            # 5. Kiểm tra Luật Cục bộ (Simple Rules)
            sql_query_rules = "SELECT trigger_keywords, response_template_ref FROM simple_rules "
            query_params = []
            # Nếu có chủ đề thì lọc, nếu không thì lấy luật chung hoặc tất cả (tùy logic)
            if detected_topic:
                sql_query_rules += "WHERE category = %s OR category = 'general' ORDER BY priority DESC"
                query_params.append(detected_topic)
            else:
                 sql_query_rules += "ORDER BY priority DESC" # Lấy tất cả nếu chưa có phân loại chủ đề

            cur.execute(sql_query_rules, query_params)
            rules = cur.fetchall()
            print(f"DEBUG: Tìm thấy {len(rules)} luật để kiểm tra.")

            tokens = word_tokenize(received_text.lower())
            print(f"DEBUG: Tokens sau khi tách từ: {tokens}")

            found_reply_rule = False
            matched_rule_ref = None
            for rule in rules:
                keywords = [kw.strip() for kw in rule['trigger_keywords'].lower().split(',')]
                # Kiểm tra khớp luật (có thể dùng cách đơn giản hơn là `keyword in raw_input_lower`)
                raw_input_lower = received_text.lower()
                rule_matched = False
                for keyword in keywords:
                    if keyword in tokens or keyword in raw_input_lower:
                         rule_matched = True
                         print(f"DEBUG: Khớp từ khóa '{keyword}' của luật ref '{rule['response_template_ref']}'")
                         break
                if rule_matched:
                    matched_rule_ref = rule['response_template_ref']
                    break # Dừng khi tìm thấy luật đầu tiên khớp

            if matched_rule_ref:
                print(f"DEBUG: LUẬT KHỚP! Tham chiếu template: {matched_rule_ref}")
                # Lấy các biến thể trả lời từ bảng variations
                cur.execute("SELECT variation_text FROM template_variations WHERE template_ref = %s", (matched_rule_ref,))
                variations = cur.fetchall()

                if variations:
                    selected_variation = random.choice(variations) # Chọn ngẫu nhiên
                    reply_text = selected_variation['variation_text']
                    status = "success_rule"
                    print(f"DEBUG: Tìm thấy {len(variations)} biến thể, chọn ngẫu nhiên: '{reply_text}'")
                    found_reply_rule = True
                else:
                    print(f"LỖI: Không tìm thấy biến thể nào cho ref '{matched_rule_ref}'!")
                    status = "error_no_variation" # Đặt trạng thái lỗi cụ thể

            # 6. Gọi LLM API (Giai đoạn 2 - Placeholder cho bây giờ)
            # --- KIỂM TRA LUẬT TRƯỚC ---
            # ... (phần code kiểm tra luật và đặt found_reply_rule như trước) ...
            # Giả sử sau vòng lặp for rule, found_reply_rule vẫn là False nếu không khớp luật nào

            # --- GỌI GEMINI API NẾU KHÔNG CÓ LUẬT KHỚP ---
            if not found_reply_rule and GOOGLE_API_KEY: # Chỉ gọi khi không có luật VÀ có API Key
                print("DEBUG: Không tìm thấy luật, đang thử gọi Gemini API...")
                try:
                    # Lấy thêm context về tài khoản (tùy chọn nhưng nên có)
                    account_platform = app_name # Dùng app_name từ request
                    account_notes = ""
                    try:
                        # Đảm bảo cursor và connection còn dùng được hoặc tạo mới nếu cần
                        if not cur or cur.closed:
                            if conn and not conn.closed: conn.close() # Đóng connection cũ nếu có
                            conn = get_db_connection()
                            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor) if conn else None

                        if cur:
                            cur.execute("SELECT notes FROM accounts WHERE account_id = %s", (account_id,))
                            acc_info = cur.fetchone()
                            if acc_info:
                                account_notes = acc_info['notes'] or "" # Lấy ghi chú tài khoản
                    except Exception as db_err_context:
                        print(f"DEBUG: Lỗi lấy context tài khoản khi gọi AI: {db_err_context}")
                        # Tiếp tục mà không có notes

                    # Tạo Prompt cho Gemini (Ví dụ - Cần tinh chỉnh thêm)
                    # Bạn có thể thêm lịch sử hội thoại vào đây nếu đã làm ở bước trước
                    prompt = f"""Bạn là trợ lý quản lý tài khoản mạng xã hội {account_platform}. ({account_notes}). \
                            Hãy trả lời bình luận/tin nhắn sau một cách thật ngắn gọn, tự nhiên và thân thiện bằng tiếng Việt: \"{received_text}\""""
                    print(f"DEBUG: Prompt gửi tới Gemini: {prompt}")

                    # Khởi tạo model Gemini (dùng flash cho nhanh)
                    model = genai.GenerativeModel('models/gemini-1.5-flash-latest')

                    # Gọi Gemini API
                    response = model.generate_content(prompt)

                    # Xử lý kết quả trả về
                    if not response.parts and response.prompt_feedback.block_reason:
                         print(f"DEBUG: Gemini bị chặn. Lý do: {response.prompt_feedback.block_reason}")
                         status = "error_ai_blocked"
                         reply_text = "" # Đảm bảo reply trống nếu bị chặn
                    else:
                        generated_text = response.text.strip()
                        print(f"DEBUG: Phản hồi từ Gemini: {generated_text}")
                        if generated_text:
                            reply_text = generated_text
                            status = "success_ai" # Đặt status thành công bởi AI
                        else:
                            print("DEBUG: Gemini trả về nội dung trống.")
                            status = "error_ai_empty_response"
                            reply_text = ""

                except Exception as ai_error:
                    print(f"LỖI khi gọi Gemini API: {ai_error}")
                    status = "error_ai_call" # Đặt status lỗi gọi AI
                    reply_text = "" # Đảm bảo reply trống khi lỗi

            elif not found_reply_rule and not GOOGLE_API_KEY:
                print("DEBUG: Không có luật khớp và không có API Key để gọi AI.")
                status = "no_rule_no_key" # Giữ status no_rule hoặc đặt status mới
                reply_text = ""
            # --- KẾT THÚC GỌI GEMINI API ---

            # Logic cập nhật log history và đóng CSDL vẫn giữ nguyên hoặc điều chỉnh
            # Đảm bảo nó cập nhật đúng status cuối cùng (success_rule, success_ai, no_rule, error_...)
            # ... (code cập nhật interaction_history) ...
            # ... (code đóng cur, conn trong khối finally) ...

        # ... (phần xử lý lỗi server và return jsonify như cũ) ...

            # 7. Cập nhật Log Cuối cùng (trạng thái và nội dung gửi đi)
            if history_id is not None:
                try:
                    cur.execute("""
                        UPDATE interaction_history SET sent_text = %s, status = %s
                        WHERE history_id = %s;
                    """, (reply_text or None, status, history_id))
                    conn.commit()
                    print(f"DEBUG: Đã cập nhật log cuối cùng cho ID {history_id} với status '{status}'")
                except psycopg2.Error as log_update_err:
                     conn.rollback()
                     print(f"LỖI cập nhật log cuối cùng: {log_update_err}")

        else:
             status = "error_db_connection"
             print("LỖI: Không thể kết nối CSDL trong request.")

    except Exception as e:
        print(f"LỖI SERVER NGHIÊM TRỌNG: {e}")
        status = "error_server"
        reply_text = "" # Đảm bảo trả về chuỗi trống khi có lỗi server

    finally:
        # Luôn đóng kết nối và con trỏ dù thành công hay thất bại
        if cur: cur.close()
        if conn: conn.close()
        print("DEBUG: Đã đóng kết nối CSDL (nếu có).")

    print(f"Trả về: status='{status}', reply_text='{reply_text or ''}'")
    print("--- Kết thúc xử lý yêu cầu ---\n")
    # Trả về JSON cho điện thoại
    return jsonify({"reply_text": reply_text or "", "status": status})








@app.route('/get_account_info', methods=['GET'])
def get_account_info():
    
    # Lấy account_id từ tham số URL (ví dụ: /get_account_info?account_id=zalo_main)
    account_id_to_get = request.args.get('account_id')

    if not account_id_to_get:
        return jsonify({"error": "Thiếu tham số account_id"}), 400

    conn = None
    cur = None
    account_data = None
    status = "error"

    try:
        conn = get_db_connection()
        if conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            # Truy vấn thông tin từ bảng accounts
            cur.execute("SELECT account_id, platform, username, status, notes FROM accounts WHERE account_id = %s", (account_id_to_get,))
            account_row = cur.fetchone()

            if account_row:
                # Chuyển kết quả thành dictionary để tạo JSON
                account_data = dict(account_row)
                status = "success"
                print(f"Đã tìm thấy thông tin cho: {account_id_to_get}")
            else:
                status = "not_found"
                print(f"Không tìm thấy tài khoản: {account_id_to_get}")

            cur.close()
            conn.close()
        else:
            status = "error_db_connection"

    except Exception as e:
        print(f"Lỗi khi lấy thông tin tài khoản: {e}")
        status = "error_server"
        if cur: cur.close()
        if conn: conn.close()

    if account_data:
        return jsonify({"status": status, "data": account_data})
    else:
        # Trả về lỗi nếu không tìm thấy hoặc có lỗi khác
        error_message = "Không tìm thấy tài khoản." if status == "not_found" else "Lỗi server hoặc CSDL."
        status_code = 404 if status == "not_found" else 500
        return jsonify({"status": status, "error": error_message}), status_code


    reply_text = ""
    status = "no_rule"
    conn = None
    cur = None
    history_id = None # Khởi tạo history_id

    try:
        data = request.get_json()
        if not data or 'received_text' not in data: # Bỏ bớt check account_id, app cho dễ debug
            return jsonify({"error": "Dữ liệu gửi lên không hợp lệ hoặc thiếu received_text"}), 400

        received_text = data['received_text']
        print(f"\n--- Nhận được yêu cầu mới ---") # Log bắt đầu
        print(f"Input Text: '{received_text}'") # Log input gốc

        conn = get_db_connection()
        if conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            print("DEBUG: Đã kết nối CSDL.")

            # Ghi log nhận (nên có để debug)
            try:
                # Giả sử account_id và app cũng được gửi lên
                account_id = data.get('account_id', 'unknown')
                app_name = data.get('app', 'unknown')
                cur.execute("""
                    INSERT INTO interaction_history (account_id, app, received_text, status)
                    VALUES (%s, %s, %s, %s) RETURNING history_id;
                """, (account_id, app_name, received_text, 'received'))
                history_id = cur.fetchone()['history_id']
                conn.commit()
                print(f"DEBUG: Đã ghi log nhận: ID {history_id}")
            except psycopg2.Error as log_err:
                conn.rollback()
                print(f"LỖI ghi log nhận: {log_err}")


            # Phân tích luật
            cur.execute("SELECT trigger_keywords, response_template_ref FROM simple_rules")
            rules = cur.fetchall()
            print(f"DEBUG: Tìm thấy {len(rules)} luật trong CSDL.")

            tokens = word_tokenize(received_text.lower())
            print(f"DEBUG: Tokens sau khi tách từ: {tokens}") # Log kết quả tách từ

            found_reply = False
            for rule in rules:
                print(f"DEBUG: Đang kiểm tra luật với keywords: '{rule['trigger_keywords']}'")
                keywords = [kw.strip() for kw in rule['trigger_keywords'].lower().split(',')]
                print(f"DEBUG: Keywords đã xử lý: {keywords}")

                # Sửa đổi cách kiểm tra để linh hoạt hơn
                raw_input_lower = received_text.lower()
                rule_matched = False
                for keyword in keywords:
                    # Thử kiểm tra xem keyword có LÀ MỘT TOKEN hoặc có NẰM TRONG input không
                    if keyword in tokens or keyword in raw_input_lower:
                        rule_matched = True
                        print(f"DEBUG: Khớp từ khóa '{keyword}'!")
                        break # Chỉ cần 1 từ khóa khớp là đủ

                # if any(keyword in tokens for keyword in keywords): # Cách kiểm tra cũ
                if rule_matched:
                    print(f"DEBUG: LUẬT KHỚP! Tham chiếu template: {rule['response_template_ref']}")
                    cur.execute("SELECT template_text FROM response_templates WHERE template_ref = %s", (rule['response_template_ref'],))
                    template = cur.fetchone()
                    if template:
                        reply_text = template['template_text']
                        status = "success_rule"
                        print(f"DEBUG: Tìm thấy template: '{reply_text}'")
                        found_reply = True
                        break # Thoát vòng lặp khi tìm thấy luật phù hợp
                    else:
                        print(f"LỖI: Không tìm thấy template ứng với ref '{rule['response_template_ref']}'!")
            # Kết thúc vòng lặp for rule

            if not found_reply:
                print("DEBUG: Không có luật nào khớp.")
                status = "no_rule" # Đảm bảo status là no_rule nếu không khớp

            # Cập nhật log gửi đi (Nếu cần)
            # ... (code cập nhật log như trước) ...

            cur.close()
            conn.close()
            print("DEBUG: Đã đóng kết nối CSDL.")
        else:
             status = "error_db_connection"
             print("LỖI: Không thể kết nối CSDL.")



    except Exception as e:
        print(f"LỖI server nghiêm trọng: {e}")
        status = "error_server"
        if cur: cur.close()
        if conn: conn.close()

    print(f"Trả về: status='{status}', reply_text='{reply_text}'") # Log kết quả cuối cùng
    print("--- Kết thúc xử lý yêu cầu ---\n")
    return jsonify({"reply_text": reply_text, "status": status})

# ... (Các endpoint khác và phần chạy server) ...


    reply_text = ""
    status = "no_rule" # Trạng thái mặc định nếu không có luật, không có AI
    conn = None
    cur = None
    history_id = None

    try:
        data = request.get_json()
        if not data or 'received_text' not in data or 'account_id' not in data or 'app' not in data:
            return jsonify({"error": "Dữ liệu gửi lên không hợp lệ"}), 400

        account_id = data['account_id']
        app_name = data['app']
        received_text = data['received_text']
        print(f"\n--- Nhận được yêu cầu mới ---")
        print(f"Input Text: '{received_text}' (Account: {account_id}, App: {app_name})")

        conn = get_db_connection()
        if conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            print("DEBUG: Đã kết nối CSDL.")

            # Ghi log nhận
            try:
                 cur.execute("""
                     INSERT INTO interaction_history (account_id, app, received_text, status)
                     VALUES (%s, %s, %s, %s) RETURNING history_id;
                 """, (account_id, app_name, received_text, 'received'))
                 history_id = cur.fetchone()['history_id']
                 conn.commit()
                 print(f"DEBUG: Đã ghi log nhận: ID {history_id}")
            except psycopg2.Error as log_err:
                conn.rollback()
                print(f"LỖI ghi log nhận: {log_err}")

            # --- KIỂM TRA LUẬT TRƯỚC ---
            cur.execute("SELECT trigger_keywords, response_template_ref FROM simple_rules")
            rules = cur.fetchall()
            print(f"DEBUG: Tìm thấy {len(rules)} luật trong CSDL.")
            tokens = word_tokenize(received_text.lower())
            print(f"DEBUG: Tokens sau khi tách từ: {tokens}")

            found_reply_rule = False
            matched_rule_ref = None
            for rule in rules:
                # ... (Logic khớp luật như trước, dùng tokens hoặc raw_input_lower) ...
                raw_input_lower = received_text.lower()
                rule_matched = False
                keywords = [kw.strip() for kw in rule['trigger_keywords'].lower().split(',')]
                for keyword in keywords:
                    if keyword in tokens or keyword in raw_input_lower:
                        rule_matched = True
                        matched_rule_ref = rule['response_template_ref']
                        print(f"DEBUG: Khớp từ khóa '{keyword}'!")
                        break
                if rule_matched:
                    print(f"DEBUG: LUẬT KHỚP! Tham chiếu template: {matched_rule_ref}")
                    cur.execute("SELECT template_text FROM response_templates WHERE template_ref = %s", (matched_rule_ref,))
                    template = cur.fetchone()
                    if template:
                        reply_text = template['template_text']
                        status = "success_rule"
                        print(f"DEBUG: Tìm thấy template: '{reply_text}'")
                        found_reply_rule = True
                        break
                    else:
                         print(f"LỖI: Không tìm thấy template ứng với ref '{matched_rule_ref}'!")
            # --- KẾT THÚC KIỂM TRA LUẬT ---

            # --- GỌI GEMINI API NẾU KHÔNG CÓ LUẬT KHỚP ---
            if not found_reply_rule and GOOGLE_API_KEY: # Chỉ gọi khi không có luật VÀ có API Key
                print("DEBUG: Không tìm thấy luật, đang thử gọi Gemini API...")
                try:
                    # Lấy thêm context về tài khoản (tùy chọn)
                    account_platform = app_name
                    account_notes = ""
                    try:
                        cur.execute("SELECT platform, notes FROM accounts WHERE account_id = %s", (account_id,))
                        acc_info = cur.fetchone()
                        if acc_info:
                            account_platform = acc_info['platform']
                            account_notes = acc_info['notes']
                    except Exception as db_err_context:
                        print(f"DEBUG: Lỗi lấy context tài khoản: {db_err_context}")

                    # Tạo Prompt cho Gemini (Ví dụ - Cần tinh chỉnh nhiều!)
                    prompt = f"Hãy đóng vai một người dùng mạng xã hội {account_platform} ({account_notes}). Phản hồi bình luận sau một cách thật ngắn gọn, tự nhiên và thân thiện bằng tiếng Việt: \"{received_text}\""
                    print(f"DEBUG: Prompt gửi tới Gemini: {prompt}")

                    # Gọi Gemini API
                    model = genai.GenerativeModel('models/gemini-1.5-flash-latest')
                    # Cấu hình an toàn (tùy chọn, giảm chặn nếu cần nhưng cẩn thận)
                    # safety_settings = [
                    #     { "category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE" },
                    #     { "category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE" },
                    #     { "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE" },
                    #     { "category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
                    # ]
                    # response = model.generate_content(prompt, safety_settings=safety_settings)
                    response = model.generate_content(prompt)

                    # Xử lý kết quả trả về
                    # Kiểm tra xem có bị chặn không (optional but recommended)
                    if not response.parts and response.prompt_feedback.block_reason:
                         print(f"DEBUG: Gemini bị chặn. Lý do: {response.prompt_feedback.block_reason}")
                         status = "error_ai_blocked"
                    else:
                        generated_text = response.text.strip()
                        print(f"DEBUG: Phản hồi từ Gemini: {generated_text}")
                        if generated_text:
                            reply_text = generated_text
                            status = "success_ai"
                        else:
                            print("DEBUG: Gemini trả về nội dung trống.")
                            status = "error_ai_empty_response"

                except Exception as ai_error:
                    print(f"LỖI khi gọi Gemini API: {ai_error}")
                    status = "error_ai_call" # Đặt status lỗi gọi AI

            elif not found_reply_rule and not GOOGLE_API_KEY:
                print("DEBUG: Không có luật khớp và không có API Key để gọi AI.")
                status = "no_rule_no_key" # Giữ nguyên no_rule hoặc đặt status mới

            # --- KẾT THÚC GỌI GEMINI API ---

            # Cập nhật log cuối cùng trước khi đóng CSDL
            if history_id is not None and status not in ('received', 'error_db_connection', 'error_server'):
                try:
                    cur.execute("""
                        UPDATE interaction_history SET sent_text = %s, status = %s
                        WHERE history_id = %s;
                    """, (reply_text or None, status, history_id)) # Gửi None nếu reply_text trống
                    conn.commit()
                    print(f"DEBUG: Đã cập nhật log cuối cùng cho ID {history_id} với status {status}")
                except psycopg2.Error as log_update_err:
                     conn.rollback()
                     print(f"LỖI cập nhật log cuối cùng: {log_update_err}")

            if cur: cur.close()
            if conn: conn.close()
            print("DEBUG: Đã đóng kết nối CSDL.")
        else:
             status = "error_db_connection"

    except Exception as e:
        print(f"LỖI server nghiêm trọng: {e}")
        status = "error_server"
        reply_text = "" # Đảm bảo trả về chuỗi trống khi có lỗi server
        if cur: cur.close()
        if conn: conn.close()

    print(f"Trả về: status='{status}', reply_text='{reply_text or ''}'")
    print("--- Kết thúc xử lý yêu cầu ---\n")
    # Luôn trả về JSON hợp lệ
    return jsonify({"reply_text": reply_text or "", "status": status})

# ... (Endpoint /log_interaction và phần chạy server giữ nguyên) ...

# --- (Tùy chọn) Endpoint nhận log từ điện thoại ---
@app.route('/log_interaction', methods=['POST'])
def handle_log_interaction():
    # ... (Code để nhận và ghi log vào interaction_history từ điện thoại) ...
    print("INFO: Nhận được log tương tác từ điện thoại.")
    return jsonify({"status": "log_received"})

# --- Chạy Server ---
if __name__ == '__main__':
    # Nhớ đặt biến môi trường GOOGLE_API_KEY nếu bạn thêm code gọi AI
    print("INFO: Khởi động Flask server...")
    # Chạy trên tất cả các IP nội bộ, port 5000, bật debug mode khi phát triển
    app.run(host='0.0.0.0', port=5000, debug=True)

    

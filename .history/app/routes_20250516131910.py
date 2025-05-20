# backup/app/routes.py
from flask import Blueprint, request, jsonify, current_app # Đảm bảo có current_app
import random
import traceback
from flask import Blueprint, jsonify
from app import db_sqlalchemy
# Import các module cục bộ
from . import database as db
from . import ai_service
# from . import nlp_utils # Import nếu bạn dùng lại nlp_utils
from flask import current_app, send_from_directory
import os
from werkzeug.utils import secure_filename
main_bp = Blueprint('main', __name__)

@main_bp.route('/receive_content_for_reply', methods=['POST'])
def handle_receive_content():
    # --- Khởi tạo các biến ---
    reply_text = ""
    status = "error_unknown"
    next_action_suggestion = None
    history_id = None
    account_id = None
    received_text = None
    app_name = None
    thread_id = None
    data = None
    account_info = None # Thêm biến lưu account_info
    persona_id_to_use = None # Thêm biến lưu persona_id

    try:
        # --- Bước 1: Lấy và Kiểm tra Dữ liệu Input ---
        print("\n--- Bắt đầu handle_receive_content ---")
        data = request.get_json()
        if not data:
            status = "error_no_json_data"; raise ValueError("Không nhận được dữ liệu JSON.")

        print(f"DEBUG: Dữ liệu JSON nhận được: {data}")
        account_id = data.get('account_id')
        received_text = data.get('received_text')
        if not account_id or not received_text:
            status = "error_missing_data"; raise ValueError("Thiếu account_id hoặc received_text")

        app_name = data.get('app', 'unknown')
        thread_id = data.get('thread_id')

        print(f"INFO: Yêu cầu từ Acc='{account_id}', App='{app_name}', Thread='{thread_id}'")
        print(f"INFO: Input Text='{received_text}'")

        # --- Bước 1.5: Lấy thông tin tài khoản và Persona ID ---
        print("DEBUG: Lấy thông tin tài khoản và persona...")
        account_info = db.get_account_details(account_id) # Hàm này cần trả về cả default_persona_id
        if account_info:
            # Ưu tiên persona từ account, nếu không có thì lấy default từ config
            persona_id_to_use = account_info.get('default_persona_id') or current_app.config.get('DEFAULT_REPLY_PERSONA_ID', 'general_assistant') # <<< Lấy persona_id
            print(f"DEBUG: Sử dụng Persona ID: {persona_id_to_use}")
        else:
            print(f"WARNING: Không tìm thấy thông tin tài khoản cho {account_id}. Sử dụng persona mặc định.")
            persona_id_to_use = current_app.config.get('DEFAULT_REPLY_PERSONA_ID', 'general_assistant') # <<< Dùng default nếu không có account

        # --- Bước 2: Xác định Chiến lược và Giai đoạn Hiện tại ---
        print("DEBUG: Xác định strategy và stage...")
        # Lấy strategy từ account hoặc default nếu account không có
        strategy_id = account_info.get('default_strategy_id') if account_info else 'default_strategy' # <<< Có thể lấy từ account_info
        strategy_id = strategy_id or 'default_strategy' # Đảm bảo không None/rỗng
        last_stage = db.get_last_stage(thread_id)
        current_stage_id = last_stage if last_stage else db.get_initial_stage(strategy_id)
        current_stage_id = current_stage_id or 'initial' # Giai đoạn mặc định an toàn
        print(f"DEBUG: Strategy='{strategy_id}', Current Stage='{current_stage_id}'")

        # --- Bước 3: Phát hiện Ý định Người dùng (Truyền persona_id) ---
        print("DEBUG: Phát hiện user intent...")
        # <<< Truyền persona_id_to_use vào hàm detect >>>
        user_intent = ai_service.detect_user_intent_with_ai(received_text, persona_id=persona_id_to_use)
        print(f"DEBUG: Detected Intent='{user_intent}'")

        # --- Bước 4: Ghi log Nhận vào CSDL ---
        print("DEBUG: Ghi log nhận vào DB...")
        history_id = db.log_interaction_received(account_id, app_name, thread_id, received_text, strategy_id, current_stage_id, user_intent)
        print(f"DEBUG: Log nhận được ghi, history_id = {history_id}")
        if not history_id:
             # Nếu không ghi log được thì có thể dừng lại hoặc tiếp tục nhưng báo warning
             print(f"CRITICAL: Không thể ghi log ban đầu cho tương tác! Tiếp tục xử lý...")
             # status = "error_db_log_failed"; raise ValueError("Ghi log thất bại") # Hoặc dừng lại

        # --- Bước 5: Áp dụng Luật Chuyển tiếp Giai đoạn ---
        print("DEBUG: Tìm luật chuyển tiếp...")
        transition = db.find_transition(current_stage_id, user_intent)
        found_reply_strategy = False
        next_stage_id_for_log = current_stage_id

        if transition:
            next_stage_id_determined = transition.get('next_stage_id') or current_stage_id
            next_stage_id_for_log = next_stage_id_determined
            action_to_suggest_from_rule = transition.get('action_to_suggest')
            template_ref = transition.get('response_template_ref')
            print(f"DEBUG: Transition tìm thấy: NextStage='{next_stage_id_determined}', ActionSuggest='{action_to_suggest_from_rule}', TemplateRef='{template_ref}'")

            if template_ref:
                print(f"DEBUG: Lấy template variations cho ref '{template_ref}'...")
                variations = db.get_template_variations(template_ref)
                if variations:
                    reply_text = random.choice(variations).get('variation_text', '')
                    status = "success_strategy_template"
                    found_reply_strategy = True
                    print(f"DEBUG: Dùng template từ transition: '{reply_text[:100]}...'")
                else:
                    print(f"WARNING: Không tìm thấy biến thể cho ref '{template_ref}'")
                    status = "error_no_variation"

            if action_to_suggest_from_rule:
                # TODO: Xử lý action phức tạp hơn nếu cần (ví dụ trả về target_id)
                next_action_suggestion = {"type": action_to_suggest_from_rule}

        # --- Bước 6: Gọi AI nếu không có luật/template phù hợp ---
        if not found_reply_strategy:
            print(f"DEBUG: Không có luật/template khớp, gọi AI Service với Persona '{persona_id_to_use}'...")
            # Lấy các thông tin cần thiết cho prompt_data
            account_goal = account_info.get('goal', 'Không rõ') if account_info else 'Không rõ'
            account_notes = account_info.get('notes', '') if account_info else ''
            account_platform = account_info.get('platform', app_name) if account_info else app_name
            formatted_history = db.get_formatted_history(thread_id, limit=5)

            # Tạo dictionary prompt_data
            prompt_data = {
                "account_platform": account_platform,
                "account_notes": account_notes,
                "account_goal": account_goal,
                "current_stage_id": current_stage_id,
                "user_intent": user_intent,
                "formatted_history": formatted_history,
                "received_text": received_text
                # Thêm các biến khác mà prompt template của bạn cần
            }

            # <<< Gọi hàm generate_reply_with_ai đã refactor >>>
            ai_reply, ai_status = ai_service.generate_reply_with_ai(
                prompt_data=prompt_data,
                persona_id=persona_id_to_use
            )

            # Xử lý kết quả AI
            if ai_status.startswith("success") and ai_reply:
                reply_text = ai_reply
                status = ai_status # Giữ status thành công từ AI (success_ai hoặc success_fallback...)
                # Giữ nguyên stage sau khi AI trả lời (hoặc thay đổi theo logic của bạn)
                # next_stage_id_for_log = current_stage_id
            else:
                print(f"WARNING: AI không thành công hoặc không trả lời, status={ai_status}")
                status = ai_status # Giữ status lỗi từ AI
                reply_text = "" # Không có gì để trả lời

        # --- Bước 7: Cập nhật Log Cuối cùng ---
        if history_id:
            print(f"DEBUG: Cập nhật log cuối cùng cho history_id {history_id} với status {status}...")
            # Giả sử next_stage_id_for_log đã được xác định đúng ở Bước 5 hoặc 6
            db.update_interaction_log(history_id, reply_text, status, next_stage_id_for_log)

    except ValueError as ve: # Bắt lỗi validate dữ liệu đầu vào
         print(f"LỖI VALIDATION: {ve}")
         # Status đã được set trong các khối raise ValueError
         reply_text = "" # Không trả lời khi lỗi input
    except Exception as e:
        error_details = traceback.format_exc()
        print("\n" + "="*20 + " LỖI SERVER KHÔNG MONG MUỐN " + "="*20)
        print(f"Loại lỗi: {type(e).__name__}")
        print(f"Tham số lỗi: {e.args}")
        print("Traceback chi tiết:")
        print(error_details)
        print("="*60 + "\n")
        status = "error_server_unexpected"
        reply_text = ""
        # Cố gắng cập nhật log lỗi nếu có history_id
        if history_id:
             try:
                  db.update_interaction_log(history_id, reply_text, status, 'unknown') # Stage là unknown khi lỗi nặng
             except Exception as log_update_err:
                  print(f"LỖI NGHIÊM TRỌNG: Không thể cập nhật log lỗi: {log_update_err}")

    # --- Bước 8: Trả kết quả về điện thoại ---
    response_data = {"reply_text": reply_text or "", "status": status}
    if next_action_suggestion:
         response_data["next_action"] = next_action_suggestion

    print(f"--- Kết thúc yêu cầu: Trả về {response_data} --- \n")
    return jsonify(response_data)


@main_bp.route('/test-db')
def test_db():
    try:
        # Gửi truy vấn đơn giản để kiểm tra kết nối
        result = db_sqlalchemy.session.execute('SELECT 1').scalar()
        return jsonify({"status": "success", "result": result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})
# ... (Các route khác nếu có) ...
@main_bp.route('/favicon.ico')
def favicon():
    """
    Route xử lý yêu cầu /favicon.ico từ trình duyệt.
    Nó sẽ tìm và trả về file favicon.ico từ thư mục static đã cấu hình.
    """
    try:
        # current_app.static_folder là đường dẫn tương đối ('../static')
        # cần tạo đường dẫn tuyệt đối đến thư mục static
        static_dir = os.path.join(current_app.root_path, current_app.static_folder)
        # send_from_directory cần đường dẫn thư mục tuyệt đối
        return send_from_directory(static_dir,
                                   'favicon.ico',
                                   mimetype='image/vnd.microsoft.icon') # Đặt đúng mimetype
    except Exception as e:
        # Ghi log lỗi nếu không tìm thấy file hoặc có lỗi khác
        current_app.logger.error(f"Lỗi khi phục vụ favicon.ico: {e}")
        # Trả về lỗi 404 nếu không tìm thấy file hoặc lỗi
        return '', 404

@main_bp.route('/api/upload/screenshot', methods=['POST']) # Hoặc URL mà client của bạn thực sự gọi
def upload_screenshot_from_client(): # Đổi tên hàm cho rõ ràng
    logger = current_app.logger
    logger.info("PHONE_UPLOAD_API: Received new screenshot upload request.")

    if 'file' not in request.files:
        logger.warning("PHONE_UPLOAD_API: No 'file' part in request.files.")
        return jsonify({"success": False, "error": "Missing file part in request"}), 400
    
    uploaded_file = request.files['file']
    
    # filename này là tên file mà client đã báo trước đó (ví dụ: uuid.png)
    # và là tên file sẽ được lưu trên server.
    client_declared_filename = request.form.get('filename') 
    app_name_from_client = request.form.get('app_name')

    logger.debug(f"PHONE_UPLOAD_API: Received form data - filename: '{client_declared_filename}', app_name: '{app_name_from_client}'")
    logger.debug(f"PHONE_UPLOAD_API: Received file object - original client filename: '{uploaded_file.filename}'")

    if not client_declared_filename:
        logger.warning("PHONE_UPLOAD_API: Missing 'filename' form parameter.")
        return jsonify({"success": False, "error": "Missing 'filename' parameter"}), 400
    
    if not app_name_from_client:
        logger.warning("PHONE_UPLOAD_API: Missing 'app_name' form parameter.")
        return jsonify({"success": False, "error": "Missing 'app_name' parameter"}), 400

    if uploaded_file.filename == '' and not client_declared_filename : # Check kỹ hơn
        logger.warning("PHONE_UPLOAD_API: No file selected or invalid filename.")
        return jsonify({"success": False, "error": "No file selected or invalid filename"}), 400

    # Sử dụng client_declared_filename làm tên file cuối cùng, sau khi an toàn hóa
    final_filename_to_save = secure_filename(os.path.basename(client_declared_filename))
    # An toàn hóa app_name để dùng làm tên thư mục
    safe_app_name_folder = secure_filename(app_name_from_client)

    if not final_filename_to_save or not safe_app_name_folder:
        logger.error(f"PHONE_UPLOAD_API: Invalid filename or app_name after sanitization. Original filename: '{client_declared_filename}', app_name: '{app_name_from_client}'")
        return jsonify({"success": False, "error": "Invalid filename or app_name after sanitization."}), 400

    # Lấy đường dẫn lưu trữ gốc từ config
    storage_base_path = current_app.config.get('SCREENSHOT_STORAGE_PATH')
    if not storage_base_path:
        logger.critical("PHONE_UPLOAD_API: SCREENSHOT_STORAGE_PATH is not configured in the server!")
        return jsonify({"success": False, "error": "Server configuration error (storage path)."}), 500
    
    logger.info(f"PHONE_UPLOAD_API: Configured SCREENSHOT_STORAGE_PATH: '{storage_base_path}'")

    # Đường dẫn đến thư mục con của app: STORAGE_PATH / APP_NAME /
    app_specific_storage_directory = os.path.join(storage_base_path, safe_app_name_folder)
    logger.info(f"PHONE_UPLOAD_API: Target app-specific storage directory: '{app_specific_storage_directory}'")
    
    try:
        # Tạo thư mục con cho app_name nếu chưa tồn tại
        if not os.path.exists(app_specific_storage_directory):
            os.makedirs(app_specific_storage_directory, exist_ok=True)
            logger.info(f"PHONE_UPLOAD_API: Created directory: {app_specific_storage_directory}")
    except OSError as e:
        logger.error(f"PHONE_UPLOAD_API: Could not create directory '{app_specific_storage_directory}': {e}", exc_info=True)
        return jsonify({"success": False, "error": "Server error creating storage directory."}), 500
    
    # Đường dẫn đầy đủ để lưu file ảnh: STORAGE_PATH / APP_NAME / FILENAME
    full_path_to_save_file = os.path.join(app_specific_storage_directory, final_filename_to_save)
    logger.info(f"PHONE_UPLOAD_API: Attempting to save uploaded file to: '{full_path_to_save_file}'")
    
    try:
        uploaded_file.save(full_path_to_save_file)
        # Kiểm tra lại xem file đã thực sự được lưu chưa
        if os.path.exists(full_path_to_save_file):
            logger.info(f"PHONE_UPLOAD_API: SUCCESS - Image saved to: {full_path_to_save_file}")
            return jsonify({
                "success": True, 
                "message": "Screenshot uploaded successfully.", 
                "saved_server_path_debug": full_path_to_save_file # Chỉ để debug
            }), 201
        else:
            logger.error(f"PHONE_UPLOAD_API: FAILED - File NOT FOUND after save attempt at: {full_path_to_save_file}")
            return jsonify({"success": False, "error": "Server error: Could not confirm file save."}), 500
    except Exception as e:
        logger.error(f"PHONE_UPLOAD_API: FAILED to save file '{final_filename_to_save}' to '{app_specific_storage_directory}': {e}", exc_info=True)
        # Cố gắng xóa file nếu lưu lỗi (tùy chọn)
        if os.path.exists(full_path_to_save_file):
            try: os.remove(full_path_to_save_file) 
            except: pass
        return jsonify({"success": False, "error": "Server error while saving image file."}), 500
# backup/app/routes.py
from flask import Blueprint, request, jsonify, current_app # Đảm bảo có current_app
import random
import traceback

# Import các module cục bộ
from . import database as db
from . import ai_service
# from . import nlp_utils # Import nếu bạn dùng lại nlp_utils

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

# ... (Các route khác nếu có) ...
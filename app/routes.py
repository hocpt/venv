# app/routes.py
from flask import Blueprint, request, jsonify, current_app
import random
import traceback

# Import các module cục bộ
from . import database as db
from . import ai_service
from . import nlp_utils

main_bp = Blueprint('main', __name__)

@main_bp.route('/receive_content_for_reply', methods=['POST'])
def handle_receive_content():
    # --- Khởi tạo các biến ---
    reply_text = "" # Dùng chuỗi rỗng thay vì None để tránh lỗi khi trả về JSON
    status = "error_unknown"
    next_action_suggestion = None
    history_id = None
    # Khởi tạo các biến sẽ lấy từ data để tránh UnboundLocalError nếu có lỗi sớm
    account_id = None
    received_text = None
    app_name = None
    thread_id = None
    data = None

    try:
        # --- Bước 1: Lấy và Kiểm tra Dữ liệu Input ---
        print("\n--- Bắt đầu handle_receive_content ---")
        data = request.get_json()
        if not data:
            print("LỖI: Không nhận được dữ liệu JSON.")
            status = "error_no_json_data"
            raise ValueError("Không nhận được dữ liệu JSON.") # Raise lỗi để nhảy đến except

        print(f"DEBUG: Dữ liệu JSON nhận được: {data}")

        # Kiểm tra các trường bắt buộc và gán giá trị sớm
        if 'account_id' not in data or 'received_text' not in data:
            print("LỖI: Dữ liệu JSON thiếu account_id hoặc received_text.")
            status = "error_missing_data"
            raise ValueError("Thiếu account_id hoặc received_text")

        account_id = data['account_id']
        received_text = data['received_text']
        app_name = data.get('app', 'unknown') # Dùng giá trị mặc định nếu thiếu
        thread_id = data.get('thread_id') # Có thể là None nếu không có

        print(f"INFO: Yêu cầu từ Acc='{account_id}', App='{app_name}', Thread='{thread_id}'")
        print(f"INFO: Input Text='{received_text}'")

        # --- Bước 2: Xác định Chiến lược và Giai đoạn Hiện tại ---
        print("DEBUG: Xác định strategy và stage...")
        strategy_id = db.get_account_goal(account_id) or 'default_strategy'
        last_stage = db.get_last_stage(thread_id)
        current_stage_id = last_stage if last_stage else db.get_initial_stage(strategy_id)
        if not current_stage_id: current_stage_id = 'initial' # Giai đoạn mặc định an toàn
        print(f"DEBUG: Strategy='{strategy_id}', Current Stage='{current_stage_id}'")

        # --- Bước 3: Phát hiện Ý định Người dùng ---
        print("DEBUG: Phát hiện user intent...")
        user_intent = ai_service.detect_user_intent_with_ai(received_text)
        print(f"DEBUG: Detected Intent='{user_intent}'")

        # --- Bước 4: Ghi log Nhận vào CSDL ---
        print("DEBUG: Ghi log nhận vào DB...")
        history_id = db.log_interaction_received(account_id, app_name, thread_id, received_text, strategy_id, current_stage_id, user_intent)
        print(f"DEBUG: Log nhận được ghi, history_id = {history_id}")

        # --- Bước 5: Áp dụng Luật Chuyển tiếp Giai đoạn ---
        print("DEBUG: Tìm luật chuyển tiếp...")
        transition = db.find_transition(current_stage_id, user_intent)
        found_reply_strategy = False
        next_stage_id_for_log = current_stage_id # Mặc định

        if transition:
            next_stage_id_determined = transition.get('next_stage_id') or current_stage_id
            next_stage_id_for_log = next_stage_id_determined
            action_to_suggest_from_rule = transition.get('action_to_suggest')
            template_ref = transition.get('response_template_ref')
            print(f"DEBUG: Transition tìm thấy: NextStage='{next_stage_id_determined}', ActionSuggest='{action_to_suggest_from_rule}', TemplateRef='{template_ref}'")

            if template_ref:
                print(f"DEBUG: Lấy template cho ref '{template_ref}'...")
                variations = db.get_template_variations(template_ref)
                if variations and isinstance(variations, list) and len(variations) > 0:
                    reply_text = random.choice(variations).get('variation_text', '') # An toàn hơn
                    status = "success_strategy_template"
                    found_reply_strategy = True
                    print(f"DEBUG: Dùng template từ transition: '{reply_text[:100]}...'")
                else:
                    print(f"WARNING: Không tìm thấy biến thể hoặc format sai cho ref '{template_ref}'")
                    status = "error_no_variation" # Vẫn coi như chưa tìm được trả lời

            if action_to_suggest_from_rule:
                next_action_suggestion = {"type": action_to_suggest_from_rule} # Thêm target_id nếu cần

        # --- Bước 6: Gọi AI nếu không có luật/template phù hợp ---
        if not found_reply_strategy:
            print(f"DEBUG: Không có luật/template khớp, gọi AI Service...")
            # Lấy thông tin tài khoản và lịch sử
            account_info = db.get_account_details(account_id) # Giả sử hàm này đã tồn tại và đúng
            account_goal = account_info.get('goal', strategy_id) if account_info else strategy_id
            account_notes = account_info.get('notes', '') if account_info else ''
            account_platform_from_db = account_info.get('platform', app_name) if account_info else app_name
            formatted_history = db.get_formatted_history(thread_id, limit=5) # Giả sử hàm này đã tồn tại và đúng

            # Tạo prompt
            prompt = f"""Bạn là trợ lý ảo cho tài khoản mạng xã hội {account_platform_from_db} ({account_notes}).
                Mục tiêu chính là: '{account_goal}'. Giai đoạn hiện tại: '{current_stage_id}'. Ý định người dùng: '{user_intent}'.
                Lịch sử (nếu có):
                --- LỊCH SỬ ---
                {formatted_history}
                --- KẾT THÚC LỊCH SỬ ---
                Nội dung mới từ người dùng: "{received_text}"
                Hãy tạo phản hồi tiếng Việt phù hợp nhất."""
            print(f"DEBUG: Prompt cho AI (200 chars): {prompt[:200]}...")

            # Gọi hàm AI Service
            
            ai_reply, ai_status = ai_service.generate_reply_with_ai(
                prompt=prompt,
                account_goal=account_goal # <<< THÊM THAM SỐ NÀY
            )

            # Xử lý kết quả AI
            if ai_status == "success_ai" and ai_reply:
                reply_text = ai_reply
                status = "success_ai" # Đặt lại status thành công
                next_stage_id_for_log = current_stage_id # Giữ nguyên stage sau khi AI trả lời (có thể thay đổi logic này)
            else:
                print(f"WARNING: AI không thành công, status={ai_status}")
                status = ai_status # Giữ status lỗi từ AI
                reply_text = ""
                next_stage_id_for_log = current_stage_id # Giữ nguyên stage khi AI lỗi

        # --- Bước 7: Cập nhật Log Cuối cùng ---
        if history_id:
            print(f"DEBUG: Cập nhật log cuối cùng cho history_id {history_id} với status {status}...")
            db.update_interaction_log(history_id, reply_text, status, next_stage_id_for_log) # Giả sử hàm này tồn tại

    except Exception as e:
        # Ghi log lỗi chi tiết hơn
        error_details = traceback.format_exc()
        print("\n" + "="*20 + " LỖI SERVER KHÔNG MONG MUỐN " + "="*20)
        print(f"Loại lỗi: {type(e).__name__}")
        print(f"Tham số lỗi: {e.args}")
        print("Traceback chi tiết:")
        print(error_details)
        print("="*60 + "\n")
        status = "error_server_unexpected"
        reply_text = ""

    # --- Bước 8: Trả kết quả về điện thoại ---
    response_data = {"reply_text": reply_text or "", "status": status}
    if next_action_suggestion:
         response_data["next_action"] = next_action_suggestion

    print(f"--- Kết thúc yêu cầu: Trả về {response_data} --- \n")
    return jsonify(response_data)

# --- Route /log_interaction và các route khác giữ nguyên ---
# ... (Code route /log_interaction như trước) ...
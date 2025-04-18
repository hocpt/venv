# app/phone/controller.py
import json
import datetime
import traceback
from .. import database as db # Import db từ app cha
from .. import ai_service # Import ai_service nếu cần gọi AI


# --- Logic xử lý báo cáo trạng thái ---
def process_status_report(device_id: str, account_id: str, strategy_id: str, strategy_version: str | None, final_status: str, log_data: list) -> bool:
    """
    Lưu log thực thi từ điện thoại vào bảng phone_action_log.
    """
    print(f"DEBUG (Phone Controller): Processing status report for device={device_id}, account={account_id}, strategy={strategy_id}, status={final_status}")
    # TODO: Implement logic to parse log_data and write relevant information
    # to the 'phone_action_log' table using db functions.
    # Ví dụ: Lặp qua log_data, mỗi entry là một hành động đã thực thi
    # db.log_phone_action(session_id=f"{device_id}_{strategy_id}_{datetime.datetime.now().timestamp()}", ...)
    try:
        session_id = f"{device_id}_{strategy_id}_{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S')}"
        for log_entry in log_data:
            # Giả sử log_entry là dict chứa thông tin như: timestamp, macro_code, params, result, error_message, current_stage, ui_state_snapshot (tùy chọn)
            db.log_phone_action( # Cần tạo hàm này trong database.py
                session_id=session_id,
                timestamp=log_entry.get('timestamp'), # Cần chuẩn hóa datetime
                macro_code=log_entry.get('macro_code'),
                params_json=log_entry.get('params'), # Đảm bảo là JSON
                execution_status=log_entry.get('result', 'unknown'), # success, fail, skip...
                execution_error=log_entry.get('error_message'),
                current_stage=log_entry.get('current_stage'),
                # Có thể lưu cả state UI lúc đó nếu cần debug
                # received_state_json=log_entry.get('ui_state_snapshot')
            )
        print(f"INFO: Status report processed successfully for session {session_id}")
        return True
    except Exception as e:
        print(f"ERROR processing status report: {e}")
        print(traceback.format_exc())
        return False

# --- Logic tạo trả lời bình luận ---
def generate_comment_reply(account_id: str, comment_text: str, context_json: dict) -> str | None:
    """
    Tạo nội dung trả lời cho bình luận.
    Ưu tiên rule/template, sau đó dùng AI offline model.
    """
    print(f"DEBUG (Phone Controller): Generating comment reply for account={account_id}, comment='{comment_text[:50]}...'")
    reply = None

    # B1: (Chưa implement) Tìm rule/template phù hợp trong DB dựa trên comment_text/context
    # matched_template_ref = db.find_matching_reply_template(comment_text, context_json)
    # if matched_template_ref:
    #     variations = db.get_template_variations(matched_template_ref)
    #     if variations:
    #         import random
    #         reply = random.choice(variations).get('variation_text')
    #         print(f"INFO: Found matching template reply: '{reply[:50]}...'")

    # B2: Nếu không có template, gọi AI offline (hoặc Gemini nếu chưa có AI offline)
    if reply is None:
        print("INFO: No matching template found, calling AI to generate reply...")
        try:
            # Lấy persona của account
            account_details = db.get_account_details(account_id)
            persona_id = account_details.get('default_persona_id') if account_details else None
            # TODO: Tạo prompt chuyên biệt cho việc trả lời bình luận
            prompt = f"Tài khoản {account_id} (persona: {persona_id}) nhận được bình luận sau: '{comment_text}'. Ngữ cảnh: {context_json}. Hãy tạo một câu trả lời ngắn gọn, phù hợp."

            # TODO: Thay thế bằng lệnh gọi mô hình AI offline tự xây khi sẵn sàng
            # Hiện tại dùng lại ai_service (có thể là Gemini)
            generated_text, status = ai_service.call_generative_model(prompt, persona_id=persona_id) # Gọi hàm call API

            if status == 'success' and generated_text:
                reply = generated_text.strip()
                print(f"INFO: AI generated reply: '{reply[:50]}...'")
            else:
                print(f"WARN: AI failed to generate comment reply (Status: {status})")
                # Fallback cuối cùng?
                reply = "Cảm ơn bạn đã bình luận!" # Hoặc None để báo lỗi

        except Exception as e:
            print(f"ERROR calling AI for comment reply: {e}")
            reply = None # Trả về None nếu lỗi

    return reply


def compile_strategy_package(strategy_id: str, account_id: str | None = None, device_id: str | None = None) -> dict | None:
    """Biên dịch gói chiến lược JSON cho điện thoại."""
    print(f"DEBUG: Compiling strategy package for strategy_id={strategy_id}, account_id={account_id}")
    try:
        strategy_details = db.get_strategy_details(strategy_id)
        if not strategy_details: return None
        strategy_stages = db.get_stages_for_strategy(strategy_id)
        if strategy_stages is None: return None
        # Lấy chuỗi action đã được chuẩn bị (list các dict macro_code + params)
        action_sequence = db.get_strategy_action_sequence(strategy_id)
        if action_sequence is None: return None
        latest_version = db.get_strategy_version(strategy_id) # Dùng hàm mới

        strategy_package = {
            "package_format_version": "1.0",
            "strategy_id": strategy_id,
            "strategy_name": strategy_details.get('name'),
            "version": latest_version, # <<< Lấy version từ DB
            "initial_stage_id": strategy_details.get('initial_stage_id'),
            "stages_recognition": { # Quy tắc nhận diện stages
                stage['stage_id']: stage.get('identifying_elements')
                for stage in strategy_stages if stage.get('identifying_elements')
            },
            "action_sequence": action_sequence, # <<< Sử dụng chuỗi action đã lấy
            "execution_config": { # <<< Có thể lấy từ CSDL nếu cần cấu hình chi tiết
                 "max_run_time_minutes": 60,
                 "default_wait_ms": {"min": 800, "max": 1500}
            }
            # Có thể thêm account_context nếu cần
        }
        print(f"DEBUG: Strategy package for {strategy_id} compiled.")
        return strategy_package
    except Exception as e:
        print(f"ERROR compiling strategy package for {strategy_id}: {e}")
        print(traceback.format_exc())
        return None

def get_latest_strategy_version(strategy_id: str) -> str | None:
    """Helper để gọi hàm DB lấy version."""
    try:
        return db.get_strategy_version(strategy_id)
    except Exception as e:
        print(f"ERROR getting latest strategy version for {strategy_id}: {e}")
        return None
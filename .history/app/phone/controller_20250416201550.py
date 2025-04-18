# app/phone/controller.py
import json
import datetime
import traceback
from .. import database as db # Import db từ app cha
from .. import ai_service # Import ai_service nếu cần gọi AI

# --- Logic biên dịch Gói Chiến lược ---
def compile_strategy_package(strategy_id: str, account_id: str | None = None, device_id: str | None = None) -> dict | None:
    """
    Lấy định nghĩa chiến lược từ DB và biên dịch thành gói JSON cho điện thoại.
    Gói này chứa quy tắc nhận diện stage và chuỗi các bước (macro_code + params).
    """
    print(f"DEBUG (Phone Controller): Compiling strategy package for strategy_id={strategy_id}, account_id={account_id}")
    try:
        # B1: Lấy thông tin cơ bản của strategy
        strategy_details = db.get_strategy_details(strategy_id)
        if not strategy_details:
            print(f"ERROR: Strategy '{strategy_id}' not found.")
            return None

        # B2: Lấy tất cả stages thuộc strategy này (bao gồm cả identifying_elements)
        strategy_stages = db.get_stages_for_strategy(strategy_id)
        if strategy_stages is None: # Phân biệt lỗi DB và list rỗng
             print(f"ERROR: Failed to load stages for strategy '{strategy_id}'.")
             return None

        # B3: Lấy tất cả transitions thuộc strategy này (bao gồm cả action_to_suggest chứa macro_code+params)
        strategy_transitions = db.get_transitions_for_strategy(strategy_id)
        if strategy_transitions is None:
             print(f"ERROR: Failed to load transitions for strategy '{strategy_id}'.")
             return None

        # B4: Lấy định nghĩa các macro code (từ bảng macro_definitions mới)
        # Giả sử hàm này trả về dict {macro_code: {description: ..., params_schema: ...}}
        # macro_definitions = db.get_all_macro_definitions()
        # if macro_definitions is None:
        #      print(f"ERROR: Failed to load macro definitions.")
        #      return None
        # Tạm thời bỏ qua bước này nếu chưa có bảng macro_definitions

        # B5: Lấy phiên bản mới nhất của chiến lược (cần cơ chế versioning)
        latest_version = get_latest_strategy_version(strategy_id) # Hàm này cần được tạo

        # B6: Biên dịch thành cấu trúc JSON cuối cùng
        # Cấu trúc này cần được thống nhất giữa server và MacroDroid
        strategy_package = {
            "strategy_id": strategy_id,
            "strategy_name": strategy_details.get('name'),
            "version": latest_version,
            "initial_stage_id": strategy_details.get('initial_stage_id'),
            "stages": {
                stage['stage_id']: {
                    "description": stage.get('description'),
                    "identifying_elements": stage.get('identifying_elements') # Đây là JSONB từ DB
                } for stage in strategy_stages
            },
            "transitions": {
                # Key có thể là f"{current_stage_id}_{user_intent}" hoặc dùng cấu trúc list
                f"{t['current_stage_id']}_{t['user_intent']}_{t['priority']}": {
                    "current_stage_id": t.get('current_stage_id'),
                    "user_intent": t.get('user_intent'), # Intent hoặc Trigger Signal
                    "priority": t.get('priority', 0),
                    "condition_logic": t.get('condition_logic'), # Điều kiện tùy chọn
                    "next_stage_id": t.get('next_stage_id'),
                    # action_to_suggest bây giờ là JSON chứa {"macro_code": "...", "params": {...}}
                    "action": t.get('action_to_suggest') if isinstance(t.get('action_to_suggest'), dict) else json.loads(t.get('action_to_suggest', '{}')),
                } for t in strategy_transitions
            },
            "account_context": { # Có thể thêm ngữ cảnh tài khoản nếu cần
                "account_id": account_id,
                "goal": db.get_account_goal(account_id) if account_id else None
                # Thêm thông tin khác nếu cần
            },
            # Thêm các cấu hình khác: thời gian chạy tối đa, giới hạn hành động...
            "execution_config": {
                 "max_run_time_minutes": 60, # Ví dụ
                 "action_limits": {
                      "comment": 10, # Ví dụ: Giới hạn 10 comment mỗi lần chạy
                      "follow": 20
                 }
            }
        }
        print(f"DEBUG (Phone Controller): Strategy package compiled successfully for {strategy_id}.")
        return strategy_package

    except Exception as e:
        print(f"ERROR compiling strategy package for {strategy_id}: {e}")
        print(traceback.format_exc())
        return None

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

# --- Logic lấy phiên bản chiến lược ---
def get_latest_strategy_version(strategy_id: str) -> str | None:
    """
    Lấy mã phiên bản mới nhất của một chiến lược (cần implement cơ chế versioning).
    """
    print(f"DEBUG (Phone Controller): Getting latest version for strategy {strategy_id}")
    # TODO: Implement logic to retrieve version info from DB.
    # Ví dụ đơn giản: dùng timestamp cập nhật cuối cùng của strategy hoặc stages/transitions liên quan
    # Hoặc dùng một version number tăng dần.
    # Tạm thời trả về timestamp hiện tại làm version
    return datetime.datetime.now(datetime.timezone.utc).isoformat()
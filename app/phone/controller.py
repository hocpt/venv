# app/phone/controller.py
import json
import datetime
import traceback
from .. import database as db # Import db từ app cha
from .. import ai_service # Import ai_service nếu cần gọi AI (vd: cho generate_comment_reply sau này)

# --- Logic biên dịch Gói Chiến lược ---
def compile_strategy_package(strategy_id: str, account_id: str | None = None, device_id: str | None = None) -> dict | None:
    """Biên dịch gói chiến lược, bao gồm cả logic điều kiện và vòng lặp."""
    print(f"DEBUG (Phone Controller): Compiling strategy package for strategy_id={strategy_id}")
    if not db: print("ERROR: DB module not available."); return None
    try:
        # --- Lấy dữ liệu thô từ DB (bao gồm cả các trường loop_*) ---
        strategy_details = db.get_strategy_details(strategy_id)
        if not strategy_details: print(f"ERROR: Strategy '{strategy_id}' not found."); return None
        if strategy_details.get('strategy_type') != 'control': print(f"ERROR: Strategy '{strategy_id}' is not 'control' type."); return None # Chỉ biên dịch Control

        strategy_stages = db.get_stages_for_strategy(strategy_id)
        if strategy_stages is None: print(f"ERROR: Failed load stages for strategy '{strategy_id}'."); return None

        # Hàm này đã được cập nhật để lấy cả loop_* fields
        raw_transitions = db.get_strategy_action_sequence(strategy_id)
        if raw_transitions is None: print(f"ERROR: Failed load transitions for strategy '{strategy_id}'."); return None
        print(f"DEBUG: Found {len(raw_transitions)} raw transitions for compilation.")

        latest_version = get_latest_strategy_version(strategy_id) or datetime.datetime.now(datetime.timezone.utc).isoformat()
        account_context = {} # Lấy context nếu cần
        # ... (Logic lấy account_context) ...

        # --- Biên dịch Action Sequence ---
        compiled_action_sequence = []
        step_counter = 1 # Step ID duy nhất

        for transition in raw_transitions:
            action_data = transition.get('action_to_suggest') # Dict: {macro_code, params} or None
            condition_type = transition.get('condition_type')
            condition_value = transition.get('condition_value')
            # --- Lấy thông tin loop ---
            loop_type = transition.get('loop_type')
            loop_count = transition.get('loop_count')
            loop_condition_type = transition.get('loop_condition_type')
            loop_condition_value = transition.get('loop_condition_value')
            # loop_target_selector = transition.get('loop_target_selector') # Chưa dùng
            # loop_variable_name = transition.get('loop_variable_name') # Chưa dùng

            # Chỉ xử lý transition có action hợp lệ
            if not (isinstance(action_data, dict) and action_data.get('macro_code')):
                # print(f"DEBUG: Skipping transition {transition.get('transition_id')} - no valid action_to_suggest.")
                continue # Bỏ qua nếu không có macro code

            # --- Tạo Step Hành động Gốc (sẽ dùng trong 'then' hoặc 'sequence') ---
            action_step_content = {
                "macro_code": action_data.get('macro_code'),
                "params": action_data.get('params', {})
            }

            # --- Tạo Cấu trúc Step Cuối Cùng ---
            final_step = {"step_id": step_counter}
            final_step["trigger"] = { # Thêm trigger info để debug/hiểu rõ hơn
                "current_stage": transition.get('current_stage_id'),
                "user_intent": transition.get('user_intent')
            }

            # --- Xử lý Vòng lặp (Ưu tiên cao nhất) ---
            if loop_type and loop_type in ['repeat_n', 'while_condition_met']: # <<< Kiểm tra các loại loop hỗ trợ
                final_step["type"] = "loop"
                final_step["loop_config"] = {"type": loop_type}

                if loop_type == 'repeat_n':
                    if loop_count and loop_count > 0:
                        final_step["loop_config"]["count"] = loop_count
                    else:
                        print(f"WARN: Loop 'repeat_n' for transition {transition.get('transition_id')} missing valid count. Ignoring loop.")
                        # Fallback về simple/conditional hoặc bỏ qua? -> Fallback
                        loop_type = None # Bỏ qua vòng lặp
                elif loop_type == 'while_condition_met':
                    if loop_condition_type and loop_condition_value is not None: # Cho phép value rỗng
                         final_step["loop_config"]["condition"] = {
                             "check": loop_condition_type,
                             "value": loop_condition_value
                         }
                    else:
                         print(f"WARN: Loop 'while_condition_met' for transition {transition.get('transition_id')} missing valid condition. Ignoring loop.")
                         loop_type = None # Bỏ qua vòng lặp

                # Nếu loop_type vẫn hợp lệ sau kiểm tra -> đặt sequence
                if loop_type:
                     final_step["sequence"] = [action_step_content] # <<< Hành động gốc nằm trong sequence của loop
                     # Gán next_stage_id cho bước loop (là stage sau khi loop xong)
                     final_step["next_stage_id"] = transition.get('next_stage_id')

            # --- Nếu không phải loop, xử lý Điều kiện Chính ---
            if not loop_type: # Chỉ xử lý nếu không phải là loop hợp lệ
                if condition_type and condition_value is not None: # Cho phép value rỗng
                    final_step["type"] = "conditional"
                    final_step["condition"] = {
                        "check": condition_type,
                        "value": condition_value
                    }
                    final_step["then_sequence"] = [action_step_content] # <<< Action gốc trong then
                    final_step["else_sequence"] = [] # Else sequence (có thể mở rộng sau)
                    # Gán next_stage_id cho bước conditional (là stage sau khi chạy then/else)
                    final_step["next_stage_id"] = transition.get('next_stage_id')
                else:
                    # --- Nếu không có loop và không có condition -> Bước Đơn giản ---
                    # final_step["type"] = "simple" # Có thể bỏ type simple cho gọn
                    final_step.update(action_step_content) # Gộp trực tiếp macro/params vào step
                    # Gán next_stage_id cho bước simple
                    final_step["next_stage_id"] = transition.get('next_stage_id')


            # Thêm bước đã hoàn thiện vào chuỗi
            compiled_action_sequence.append(final_step)
            step_counter += 1

        # --- Tạo Gói JSON Cuối cùng (Giữ nguyên) ---
        strategy_package = {
            "package_format_version": "1.2", # <<< Tăng version để thể hiện cấu trúc loop
            "strategy_id": strategy_id,
            "strategy_name": strategy_details.get('name'),
            "version": latest_version,
            "initial_stage_id": strategy_details.get('initial_stage_id'),
            "stages_recognition": {
                stage['stage_id']: stage.get('identifying_elements')
                for stage in strategy_stages if stage.get('identifying_elements')
            },
            "action_sequence": compiled_action_sequence, # <<< Chuỗi action đã biên dịch (có thể có loop)
            "account_context": account_context,
            "execution_config": {
                 "max_run_time_minutes": 120,
                 "default_wait_ms": {"min": 800, "max": 1500},
                 "error_handling": "report_and_stop"
            }
        }
        print(f"DEBUG: Strategy package compiled. Sequence length: {len(compiled_action_sequence)}")
        return strategy_package

    except Exception as e:
        print(f"ERROR compiling strategy package for {strategy_id}: {e}")
        print(traceback.format_exc())
        return None
# --- Logic lấy phiên bản chiến lược ---
def get_latest_strategy_version(strategy_id: str) -> str | None:
    """Helper gọi hàm DB để lấy phiên bản mới nhất."""
    try:
        # Hàm db.get_strategy_version cần được implement để lấy version
        # (ví dụ: dựa trên timestamp cập nhật cuối của strategy/stages/transitions)
        version = db.get_strategy_version(strategy_id)
        return version
    except Exception as e:
        print(f"ERROR getting latest strategy version for {strategy_id}: {e}")
        return None # Trả về None nếu có lỗi

# --- Logic tạo trả lời bình luận (Giữ skeleton) ---
def generate_comment_reply(account_id: str, comment_text: str, context_json: dict) -> str | None:
    """
    Tạo nội dung trả lời cho bình luận.
    (Sẽ implement chi tiết sau - Giai đoạn 2/3)
    """
    print(f"DEBUG (Phone Controller): Generating comment reply for account={account_id} - (Logic not fully implemented)")
    # TODO: Implement Rule/Template matching
    # TODO: Implement call to offline AI model
    # Tạm thời trả về một câu trả lời mẫu hoặc None
    if "cảm ơn" in comment_text.lower():
        return "Không có gì bạn ơi ^^"
    elif "giá" in comment_text.lower():
         return "Bạn vui lòng inbox để mình báo giá chi tiết nhé."
    else:
        # return "Cảm ơn bạn đã bình luận!"
        return None # Trả về None để điện thoại biết là không tạo được trả lời

# --- Logic xử lý báo cáo trạng thái (Giữ skeleton) ---
def process_status_report(device_id: str, account_id: str, strategy_id: str, strategy_version: str | None, final_status: str, log_data: list) -> bool:
    """
    Xử lý và lưu log thực thi từ điện thoại.
    (Sẽ implement chi tiết sau)
    """
    print(f"DEBUG (Phone Controller): Processing status report for device={device_id} - (Logic not fully implemented)")
    try:
        # TODO: Implement logic to write to phone_action_log using db.log_phone_action
        # session_id = f"{device_id}_{strategy_id}_{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S')}"
        # for entry in log_data:
        #     db.log_phone_action(session_id=session_id, ...)
        print(f"INFO: Received status report: final_status={final_status}, log_entries={len(log_data)}")
        # Tạm thời luôn trả về True
        return True
    except Exception as e:
        print(f"ERROR processing status report: {e}")
        return False
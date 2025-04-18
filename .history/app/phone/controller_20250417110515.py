# app/phone/controller.py
import json
import datetime
import traceback
from .. import database as db # Import db từ app cha
from .. import ai_service # Import ai_service nếu cần gọi AI (vd: cho generate_comment_reply sau này)

# --- Logic biên dịch Gói Chiến lược ---
def compile_strategy_package(strategy_id: str, account_id: str | None = None, device_id: str | None = None) -> dict | None:
    """Biên dịch gói chiến lược, bao gồm cả logic điều kiện."""
    print(f"DEBUG (Phone Controller): Compiling strategy package for strategy_id={strategy_id}")
    if not db: print("ERROR: DB module not available."); return None
    try:
        # --- Lấy dữ liệu thô từ DB ---
        strategy_details = db.get_strategy_details(strategy_id)
        if not strategy_details: print(f"ERROR: Strategy '{strategy_id}' not found."); return None
        strategy_stages = db.get_stages_for_strategy(strategy_id)
        if strategy_stages is None: print(f"ERROR: Failed load stages for strategy '{strategy_id}'."); return None
        # Hàm này giờ trả về list các transition thô (bao gồm cả condition_type/value)
        raw_transitions = db.get_strategy_action_sequence(strategy_id) # Đổi tên biến cho rõ
        if raw_transitions is None: print(f"ERROR: Failed load transitions for strategy '{strategy_id}'."); return None
        latest_version = get_latest_strategy_version(strategy_id) or datetime.datetime.now(datetime.timezone.utc).isoformat()
        account_context = {} # ... (lấy account_context như cũ) ...
        if account_id:
            account_details = db.get_account_details(account_id)
            if account_details: account_context = {...} # Copy logic cũ

        # --- Biên dịch Action Sequence ---
        compiled_action_sequence = []
        step_counter = 1 # Để tạo step_id nếu muốn

        # TODO: Logic biên dịch phức tạp hơn cần ở đây để xử lý trình tự, ưu tiên, và tạo cấu trúc lồng nhau nếu cần.
        # Hiện tại, chúng ta sẽ chuyển đổi từng transition thành một bước (có thể là conditional).
        for transition in raw_transitions:
            action_data = transition.get('action_to_suggest') # Đây là dict {"macro_code": ..., "params": ...}
            condition_type = transition.get('condition_type')
            condition_value = transition.get('condition_value')

            # Chỉ tạo bước nếu có action_macro_code
            if isinstance(action_data, dict) and action_data.get('macro_code'):
                # Tạo action gốc
                macro_action_step = {
                    "macro_code": action_data.get('macro_code'),
                    "params": action_data.get('params', {})
                    # Có thể thêm các thông tin khác từ transition vào đây nếu client cần
                }

                # Nếu có điều kiện, tạo cấu trúc conditional
                if condition_type and condition_value:
                    conditional_step = {
                        "step_id": step_counter,
                        "type": "conditional",
                        "condition": {
                            "check": condition_type, # Client sẽ diễn giải loại check này
                            "value": condition_value
                        },
                        "then_sequence": [macro_action_step], # Action gốc nằm trong 'then'
                        "else_sequence": [] # Ban đầu để trống else
                         # Có thể thêm thông tin trigger từ transition để debug
                        # "trigger_info": {"stage": transition.get('current_stage_id'), "intent": transition.get('user_intent')}
                    }
                    compiled_action_sequence.append(conditional_step)
                else:
                    # Nếu không có điều kiện, chỉ thêm action gốc (có thể thêm type='simple' nếu muốn)
                     simple_step = {
                          "step_id": step_counter,
                          # "type": "simple", # Tùy chọn
                          "macro_code": macro_action_step["macro_code"],
                          "params": macro_action_step["params"]
                          # "trigger_info": {"stage": transition.get('current_stage_id'), "intent": transition.get('user_intent')}
                     }
                     compiled_action_sequence.append(simple_step)
                step_counter += 1
            # else: Bỏ qua transition không có action hợp lệ

        # --- Tạo Gói JSON Cuối cùng ---
        strategy_package = {
            "package_format_version": "1.1", # <<< Tăng version để thể hiện cấu trúc mới
            "strategy_id": strategy_id,
            "strategy_name": strategy_details.get('name'),
            "version": latest_version,
            "initial_stage_id": strategy_details.get('initial_stage_id'),
            "stages_recognition": {
                stage['stage_id']: stage.get('identifying_elements')
                for stage in strategy_stages if stage.get('identifying_elements')
            },
            "action_sequence": compiled_action_sequence, # <<< Chuỗi action đã biên dịch
            "account_context": account_context,
            "execution_config": { # ... (lấy execution config như cũ) ...
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
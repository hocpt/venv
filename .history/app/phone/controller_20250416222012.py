# app/phone/controller.py
import json
import datetime
import traceback
from .. import database as db # Import db từ app cha
from .. import ai_service # Import ai_service nếu cần gọi AI (vd: cho generate_comment_reply sau này)

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
            print(f"ERROR: Strategy '{strategy_id}' not found in DB.")
            return None

        # B2: Lấy tất cả stages thuộc strategy này (bao gồm cả identifying_elements)
        strategy_stages = db.get_stages_for_strategy(strategy_id)
        if strategy_stages is None: # Lỗi DB
             print(f"ERROR: Failed to load stages for strategy '{strategy_id}'.")
             return None

        # B3: Lấy chuỗi hành động đã được chuẩn bị từ DB
        # Hàm này đã được sửa để trả về list các dict {"macro_code": ..., "params": ..., "trigger": ..., ...}
        action_sequence = db.get_strategy_action_sequence(strategy_id)
        if action_sequence is None: # Lỗi DB
             print(f"ERROR: Failed to load action sequence for strategy '{strategy_id}'.")
             return None

        # B4: Lấy phiên bản mới nhất của chiến lược
        latest_version = get_latest_strategy_version(strategy_id) # Gọi hàm helper bên dưới
        if latest_version is None:
            print(f"WARN: Could not determine version for strategy '{strategy_id}'. Using current timestamp.")
            latest_version = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # B5: Lấy thông tin ngữ cảnh tài khoản (tùy chọn)
        account_context = {}
        if account_id:
            account_details = db.get_account_details(account_id)
            if account_details:
                account_context = {
                    "account_id": account_id,
                    "goal": account_details.get('goal'),
                    "persona_id": account_details.get('default_persona_id'),
                    "platform": account_details.get('platform')
                }

        # B6: Biên dịch thành cấu trúc JSON cuối cùng
        strategy_package = {
            "package_format_version": "1.0",
            "strategy_id": strategy_id,
            "strategy_name": strategy_details.get('name'),
            "version": latest_version,
            "initial_stage_id": strategy_details.get('initial_stage_id'),
            "stages_recognition": {
                stage['stage_id']: stage.get('identifying_elements') # Lưu quy tắc nhận diện
                for stage in strategy_stages if stage.get('identifying_elements') # Chỉ lưu stage có quy tắc
            },
            "action_sequence": action_sequence, # Chuỗi các bước {"macro_code": ..., "params": ...}
            "account_context": account_context, # Ngữ cảnh tài khoản
            "execution_config": { # Cấu hình thực thi (có thể lấy từ DB sau này)
                 "max_run_time_minutes": strategy_details.get('max_run_time', 120), # Ví dụ lấy từ DB hoặc default
                 "default_wait_ms": {"min": 800, "max": 1500},
                 "error_handling": strategy_details.get('error_handling_mode', 'report_and_stop')
                 # Thêm các giới hạn hành động nếu cần
            }
        }
        print(f"DEBUG (Phone Controller): Strategy package for {strategy_id} version {latest_version} compiled successfully.")
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
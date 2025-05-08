

import json
from datetime import datetime, timezone
from flask import current_app, jsonify
import traceback # Giữ lại import traceback
from .. import graph_db
# Import db từ app cha và ai_service nếu cần dùng sau này
from .. import database as db
from .. import ai_service # Import cả module ai_service
import hashlib 
import time
import random
from app.database import add_exploration_log
from flask import request, jsonify
from app import ai_service
# --- Helper Function (Giữ nguyên) ---

def parse_condition_value(value_str):
    """
    Hàm cố gắng parse giá trị điều kiện từ chuỗi.
    Có thể là số, boolean, chuỗi, hoặc JSON.
    """
    if value_str is None:
        return None
    value_str = str(value_str).strip() # Đảm bảo là chuỗi và xóa khoảng trắng thừa
    try:
        # Thử parse JSON trước (cho các giá trị phức tạp như list, dict)
        return json.loads(value_str)
    except json.JSONDecodeError:
        # Nếu không phải JSON, xử lý các kiểu cơ bản
        if value_str.lower() == 'true':
            return True
        if value_str.lower() == 'false':
            return False
        # Kiểm tra 'None' hoặc chuỗi rỗng một cách rõ ràng
        if value_str.lower() == 'none' or value_str == '':
             return None
        # Thử chuyển đổi sang số (int hoặc float)
        try:
            if '.' in value_str or 'e' in value_str.lower():
                return float(value_str)
            else:
                return int(value_str)
        except ValueError:
            # Nếu không phải số, trả về chuỗi gốc
            return value_str

# --- Hàm Compile Strategy Package (ĐÃ SỬA HOÀN CHỈNH) ---
def compile_strategy_package(strategy_id: str, assignment_id: int | None = None, target_data: dict | None = None) -> dict | None:
    """
    Biên dịch cấu hình chiến lược từ CSDL thành gói JSON để Client thực thi.
    Hỗ trợ các bước simple, conditional, và loop (repeat_n, while_condition_met).

    Args:
        strategy_id: ID của chiến lược cần biên dịch.
        assignment_id: (Tùy chọn) ID của nhiệm vụ được giao (nếu có).
        target_data: (Tùy chọn) Dữ liệu mục tiêu cụ thể cho nhiệm vụ này (nếu có).

    Returns:
        dict: Gói JSON chiến lược hoặc None nếu có lỗi.
    """
    logger = current_app.logger # Lấy logger từ app context
    logger.info(f"Bắt đầu biên dịch gói chiến lược: strategy_id={strategy_id}, assignment_id={assignment_id}")

    package_format_version = "1.2"  # Phiên bản cấu trúc gói, 1.2 hỗ trợ loop

    try:
        # 1. Lấy thông tin chi tiết chiến lược
        strategy_details = db.get_strategy_details(strategy_id)
        if not strategy_details:
            logger.error(f"Lỗi biên dịch: Không tìm thấy chiến lược với ID '{strategy_id}'.")
            return None
        # Chỉ biên dịch chiến lược loại 'control'
        if strategy_details.get('strategy_type') != 'control':
            logger.error(f"Lỗi biên dịch: Chỉ biên dịch được chiến lược loại 'control'. Strategy '{strategy_id}' có loại '{strategy_details.get('strategy_type')}'.")
            return None

        # 2. Lấy danh sách các Stages và quy tắc nhận diện
        strategy_stages_raw = db.get_stages_for_strategy(strategy_id)
        stages_recognition = {}
        if strategy_stages_raw:
            for stage in strategy_stages_raw:
                stage_id = stage.get('stage_id')
                if not stage_id: continue # Bỏ qua stage không có ID

                identifying_elements_data = stage.get('identifying_elements') # Đây là dict/list từ JSONB
                stage_desc = stage.get('description')
                rules = [] # Mặc định là list rỗng

                # Cố gắng lấy 'rules' nếu identifying_elements là dict
                if isinstance(identifying_elements_data, dict):
                    rules = identifying_elements_data.get('rules', [])
                    if not isinstance(rules, list): # Đảm bảo rules là list
                        logger.warning(f"Trường 'rules' trong identifying_elements của stage '{stage_id}' không phải là list. Sử dụng list rỗng.")
                        rules = []
                elif isinstance(identifying_elements_data, list):
                    # Cho phép cấu trúc cũ hơn nơi identifying_elements là list trực tiếp
                    rules = identifying_elements_data
                    logger.warning(f"Trường identifying_elements của stage '{stage_id}' là list trực tiếp (nên dùng dict chứa 'rules').")
                elif identifying_elements_data is not None:
                    logger.warning(f"Định dạng identifying_elements không mong đợi cho stage '{stage_id}': {type(identifying_elements_data)}. Bỏ qua.")

                stages_recognition[stage_id] = {
                    "description": stage_desc,
                    "rules": rules # Luôn là list
                }
        else:
            logger.warning(f"Không tìm thấy stage nào cho chiến lược '{strategy_id}'. Phần 'stages_recognition' sẽ rỗng.")

        # 3. Lấy chuỗi hành động (transitions) thô từ CSDL
        # Hàm này cần trả về list các dict, mỗi dict chứa đầy đủ các cột cần thiết
        # bao gồm action_macro_code, action_params (đã parse thành dict), loop_*...
        action_sequence_raw = db.get_strategy_action_sequence(strategy_id)

        # <<< LOG 1: Kiểm tra dữ liệu thô nhận về >>>
        logger.debug(f"Dữ liệu transitions thô từ DB: {action_sequence_raw}")

        if action_sequence_raw is None:
             logger.error(f"Lỗi biên dịch: Không thể tải transitions cho strategy '{strategy_id}'.")
             return None
        logger.info(f"Số lượng transitions thô lấy từ DB: {len(action_sequence_raw)}.")

        # 4. Biên dịch action_sequence
        compiled_sequence = []
        for transition in action_sequence_raw:
            # <<< LOG 2: Kiểm tra từng transition >>>
            logger.debug(f"Đang xử lý transition data: {transition}")

            # Lấy các trường từ dữ liệu transition (dùng .get() để an toàn)
            transition_id = transition.get('transition_id')
            current_stage_id = transition.get('current_stage_id')
            user_intent = transition.get('user_intent')
            next_stage_id = transition.get('next_stage_id')
            condition_type = transition.get('condition_type')
            condition_value = transition.get('condition_value') # Giá trị thô từ DB
            loop_type = transition.get('loop_type')
            loop_count = transition.get('loop_count') # Giá trị thô từ DB (có thể là string)
            loop_condition_type = transition.get('loop_condition_type')
            loop_condition_value = transition.get('loop_condition_value') # Giá trị thô từ DB
            # Lấy action đã được xử lý bởi hàm DB
            action_macro_code = transition.get('action_macro_code')
            action_params = transition.get('action_params', {}) # Nên là dict rỗng nếu không có

            # Kiểm tra các trường bắt buộc tối thiểu
            if transition_id is None or not current_stage_id or user_intent is None:
                logger.warning(f"Bỏ qua transition không hợp lệ (thiếu ID, current_stage, hoặc user_intent): {transition}")
                continue

            # Tạo cấu trúc step cơ bản
            step = {
                'step_id': transition_id, # Dùng transition_id làm step_id
                'trigger': {'current_stage': current_stage_id, 'user_intent': user_intent},
                'next_stage_id': next_stage_id # Có thể là None
            }

            # Xác định loại step và xây dựng cấu trúc tương ứng
            # Ưu tiên kiểm tra LOOP trước
            if loop_type:
                step['type'] = 'loop'
                step['loop_config'] = {'type': loop_type}
                # Hành động bên trong loop (lấy từ action_macro_code và action_params)
                step['sequence'] = [{
                    'macro_code': action_macro_code,
                    'params': action_params # Dùng dict đã parse
                }]

                # Xử lý cấu hình cụ thể cho từng loại loop
                if loop_type == 'repeat_n':
                    if loop_count is not None:
                        try:
                            count_int = int(loop_count) # Chuyển đổi sang số nguyên
                            if count_int <= 0: raise ValueError("Số lần lặp phải > 0")
                            step['loop_config']['count'] = count_int
                        except (ValueError, TypeError):
                            logger.warning(f"Bỏ qua step loop 'repeat_n' (ID: {transition_id}): loop_count '{loop_count}' không hợp lệ.")
                            continue # Bỏ qua step này
                    else:
                        logger.warning(f"Bỏ qua step loop 'repeat_n' (ID: {transition_id}): thiếu loop_count.")
                        continue # Bỏ qua step này
                elif loop_type == 'while_condition_met':
                    if loop_condition_type:
                         step['loop_config']['condition'] = {
                             'check': loop_condition_type,
                             'value': parse_condition_value(loop_condition_value) # Parse giá trị điều kiện
                         }
                         # Không cần `break_on_action_fail` ở đây, client tự xử lý
                    else:
                         logger.warning(f"Bỏ qua step loop 'while_condition_met' (ID: {transition_id}): thiếu loop_condition_type.")
                         continue # Bỏ qua step này
                else:
                     logger.warning(f"Bỏ qua step (ID: {transition_id}): không rõ loop_type '{loop_type}'.")
                     continue # Bỏ qua step này

            # Chỉ kiểm tra CONDITIONAL nếu KHÔNG phải là LOOP
            elif condition_type:
                step['type'] = 'conditional'
                step['condition'] = {
                    'check': condition_type,
                    'value': parse_condition_value(condition_value) # Parse giá trị điều kiện
                }
                # Hành động trong nhánh 'then' (luôn có)
                step['then_sequence'] = [{
                    'macro_code': action_macro_code,
                    'params': action_params
                }]
                # Nhánh 'else' hiện tại không được hỗ trợ cấu hình từ DB, mặc định là rỗng
                step['else_sequence'] = []

            # Nếu không phải loop và không có condition -> là SIMPLE
            else:
                step['type'] = 'simple'
                step['macro_code'] = action_macro_code
                step['params'] = action_params

            # <<< LOG 3: Kiểm tra step được tạo ra trước khi validate >>>
            logger.debug(f"Step được tạo (trước validate): {step}")

            # Kiểm tra cuối cùng xem bước có hợp lệ không (phải có macro_code)
            is_valid_step = True
            action_holder = None
            if step['type'] == 'simple':
                action_holder = step
            elif step['type'] == 'loop':
                # Hành động nằm trong sequence[0]
                action_holder = step['sequence'][0] if step.get('sequence') else None
            elif step['type'] == 'conditional':
                 # Hành động nằm trong then_sequence[0]
                action_holder = step['then_sequence'][0] if step.get('then_sequence') else None

            # <<< LOG 4: Kiểm tra action_holder và macro_code trước khi validate >>>
            logger.debug(f"Validity Check - action_holder: {action_holder}")
            macro_code_in_holder = action_holder.get('macro_code') if action_holder else None
            logger.debug(f"Validity Check - macro_code in holder: {macro_code_in_holder}")

            # Điều kiện hợp lệ: Phải có action_holder và macro_code bên trong nó phải có giá trị (khác None/rỗng)
            if not action_holder or not macro_code_in_holder:
                 is_valid_step = False
                 logger.warning(f"Step không hợp lệ cho transition ID {transition_id}: Thiếu action_holder hoặc macro_code bên trong. Type: {step.get('type')}")

            # <<< LOG 5: Kiểm tra kết quả is_valid_step >>>
            logger.debug(f"Transition ID {transition_id} - is_valid_step: {is_valid_step}")

            if is_valid_step:
                compiled_sequence.append(step)
            else:
                 logger.warning(f"Step cho transition ID {transition_id} KHÔNG được thêm vào action_sequence.")
            # Kết thúc vòng lặp for transition

        # 5. Lấy các cấu hình thực thi khác
        # Lấy từ strategy_details hoặc dùng giá trị mặc định cứng
        execution_config = {
            "initial_stage_id": strategy_details.get('initial_stage_id'),
            "max_run_time_minutes": strategy_details.get('max_run_time_minutes', 120),
            "error_handling": strategy_details.get('error_handling', "report_and_stop")
        }
        # Xử lý default_wait_ms (có thể là JSON string hoặc dict từ DB)
        default_wait_config = strategy_details.get('default_wait_ms')
        parsed_wait_ms = None
        if isinstance(default_wait_config, str):
            try: parsed_wait_ms = json.loads(default_wait_config)
            except json.JSONDecodeError: logger.warning(f"Lỗi parse default_wait_ms JSON string: {default_wait_config}")
        elif isinstance(default_wait_config, dict):
            parsed_wait_ms = default_wait_config

        if isinstance(parsed_wait_ms, dict) and 'min' in parsed_wait_ms and 'max' in parsed_wait_ms:
             execution_config["default_wait_ms"] = parsed_wait_ms
        else:
             logger.warning(f"Sử dụng default_wait_ms mặc định do cấu hình không hợp lệ: {default_wait_config}")
             execution_config["default_wait_ms"] = {"min": 800, "max": 1500} # Default cứng

        # 6. Lấy context tài khoản (kết hợp từ target_data nếu có)
        # target_data được truyền vào hàm, là dict hoặc None
        account_context = {
            "target_data": target_data or {} # Đảm bảo luôn là dict
            # Có thể thêm các thông tin khác của account nếu cần
        }

        # 7. Lấy phiên bản strategy
        # Hàm get_strategy_version cần tồn tại và hoạt động đúng
        latest_version = db.get_strategy_version(strategy_id) or datetime.now(timezone.utc).isoformat()

        # 8. Tạo gói JSON hoàn chỉnh
        strategy_package = {
            "metadata": {
                "package_format_version": package_format_version,
                "strategy_id": strategy_id,
                "strategy_name": strategy_details.get('name'),
                "strategy_version": latest_version,
                "compiled_at": datetime.now(timezone.utc).isoformat(),
                "assignment_id": assignment_id # Có thể là None
            },
            "execution_config": execution_config,
            "account_context": account_context,
            "stages_recognition": stages_recognition,
            "action_sequence": compiled_sequence # <<< List các step đã biên dịch
        }

        # <<< LOG 6: Kiểm tra compiled_sequence cuối cùng >>>
        logger.debug(f"Chuỗi action_sequence đã biên dịch cuối cùng: {compiled_sequence}")
        logger.info(f"Biên dịch thành công gói chiến lược cho strategy_id: {strategy_id}. Số bước trong sequence: {len(compiled_sequence)}")
        return strategy_package

    except Exception as e:
        # Ghi log lỗi chi tiết nếu có exception không mong muốn xảy ra
        logger.error(f"Lỗi nghiêm trọng khi biên dịch gói chiến lược cho {strategy_id}: {e}", exc_info=True)
        # exc_info=True sẽ tự động thêm traceback vào log
        # print(traceback.format_exc()) # Có thể print ra console để debug nếu cần
        return None


def get_latest_strategy_version(strategy_id: str) -> str | None:
    """Helper gọi hàm DB để lấy phiên bản mới nhất."""
    try:
        version = db.get_strategy_version(strategy_id) # Cần hàm này trong database.py
        return version
    except Exception as e:
        current_app.logger.error(f"ERROR getting latest strategy version for {strategy_id}: {e}")
        return None

def generate_comment_reply(account_id: str, comment_text: str, context_json: dict) -> str | None:
    """
    Tạo nội dung trả lời cho bình luận. (Skeleton)
    """
    current_app.logger.debug(f"Phone Controller: Generating comment reply for account={account_id} - (Logic not fully implemented)")
    # ... (logic tạm thời như cũ) ...
    if "cảm ơn" in comment_text.lower():
        return "Không có gì bạn ơi ^^"
    elif "giá" in comment_text.lower():
         return "Bạn vui lòng inbox để mình báo giá chi tiết nhé."
    else:
        return None


def process_phone_report(report_payload: dict, structured_ui_state_json: str | None = None) -> tuple[dict, int]:
    """
    Xử lý báo cáo trạng thái và danh sách log từ client gửi lên qua API /report_status.
    Bao gồm việc nhận và xử lý trạng thái UI thô (nếu có) và lưu vào log CSDL.
    Đã sửa để luôn gọi hàm ghi log nếu có UI state, ngay cả khi logs client rỗng.

    Args:
        report_payload: Dictionary chứa dữ liệu từ JSON request body của client.
        structured_ui_state_json: (Tùy chọn) Chuỗi JSON chứa trạng thái UI đã được xử lý.

    Returns:
        Tuple (dict, int): (Dictionary chứa kết quả xử lý, mã trạng thái HTTP).
    """
    logger = current_app.logger if current_app else print

    # --- Trích xuất thông tin từ report_payload ---
    device_id = report_payload.get('device_id')
    account_id = report_payload.get('account_id')
    assignment_id_str = report_payload.get('assignment_id') # Có thể None
    status_report = report_payload.get('status_report', {}) # Luôn là dict
    logs = report_payload.get('logs', []) # Luôn là list (có thể rỗng)

    # --- Parse assignment_id (nếu có) ---
    assignment_id = None
    if assignment_id_str is not None:
        try:
            assignment_id = int(assignment_id_str)
        except (ValueError, TypeError):
            logger.warning(f"process_phone_report: Invalid assignment_id format received: {assignment_id_str}. Treating as None.")

    # --- Trích xuất thông tin từ status_report ---
    current_status_from_client = status_report.get('current_status', 'unknown')
    error_message_from_client = status_report.get('error_message')
    progress_data = status_report.get('progress')
    final_result_data = status_report.get('result')

    # <<< SỬA LỖI UNBOUNDLOCALERROR: Khởi tạo các biến ở đây >>>
    status_update_success = True
    progress_update_success = True
    log_success = True
    # =====================================================

    logger.info(f"Controller processing report for Assignment: {assignment_id}, Device: {device_id}, Account: {account_id}. Client Status: {current_status_from_client}")

    # --- Bước 1: Ghi Logs Hành động và UI State vào CSDL PostgreSQL ---
    # <<< SỬA ĐỔI ĐIỀU KIỆN: Gọi hàm ghi log nếu có log TỪ CLIENT hoặc có UI STATE >>>
    if (logs and isinstance(logs, list) and len(logs) > 0) or structured_ui_state_json:
        logger.debug(f"Attempting to log actions (count: {len(logs)}) and/or UI state (present: {structured_ui_state_json is not None}) for assignment {assignment_id}.")
        # Kiểm tra module db và hàm tồn tại trước khi gọi
        if db and hasattr(db, 'add_phone_action_logs'):
            try:
                # Hàm db.add_phone_action_logs cần xử lý trường hợp logs=[] nhưng structured_ui_state_json có giá trị
                logger.debug(f"Calling db.add_phone_action_logs for assignment {assignment_id}...") # Thêm log trước khi gọi
                log_success = db.add_phone_action_logs(
                    assignment_id=assignment_id,
                    device_id=device_id,
                    account_id=account_id,
                    logs=logs, # Truyền list logs (có thể rỗng)
                    structured_ui_state_json=structured_ui_state_json # Truyền state UI
                )
                if not log_success:
                    logger.warning(f"Call to db.add_phone_action_logs returned False for assignment {assignment_id}.")
            except Exception as log_db_err:
                logger.error(f"Exception during db.add_phone_action_logs for assignment {assignment_id}: {log_db_err}", exc_info=True)
                log_success = False
        else:
            logger.error("Database module 'db' or function 'add_phone_action_logs' not available!")
            log_success = False # Coi như lỗi nếu không gọi được hàm DB
    else:
        logger.debug(f"No client log entries or UI state provided in report for assignment {assignment_id}. Skipping database log.")
        log_success = True # Vẫn coi là thành công nếu không có gì để log

    # --- Bước 2: Cập nhật Trạng thái và Tiến độ của Assignment (Chỉ thực hiện nếu có assignment_id) ---
    # (Giữ nguyên logic cập nhật status và progress như trước)
    # ... (code cập nhật status/progress của assignment_id) ...
    # Ví dụ (giữ nguyên từ code gốc):
    if assignment_id is not None:
        update_data = {}
        now_utc = datetime.now(timezone.utc)
        update_data['last_report_at'] = now_utc

        try:
            current_db_status = None
            if db and hasattr(db, 'get_task_assignment_status'):
                 current_db_status = db.get_task_assignment_status(assignment_id)

            is_starting = (current_status_from_client == 'running' and current_db_status not in ['running', 'completed', 'error', 'cancelled'])
            is_finishing = (current_status_from_client in ['completed', 'error', 'cancelled'] and current_db_status not in ['completed', 'error', 'cancelled'])

            if is_starting: update_data['started_at'] = now_utc; logger.debug(f"Setting started_at for assignment {assignment_id}")
            if is_finishing:
                update_data['completed_at'] = now_utc; logger.debug(f"Setting completed_at for assignment {assignment_id}")
                if final_result_data and isinstance(final_result_data, dict): update_data['result_data'] = final_result_data
                elif error_message_from_client: update_data['result_data'] = {'error': error_message_from_client}

            if db and hasattr(db, 'update_assignment_status'):
                status_update_success = db.update_assignment_status(
                    assignment_id=assignment_id, new_status=current_status_from_client, **update_data
                )
                if not status_update_success: logger.error(f"Failed status update for {assignment_id}")
            else:
                 logger.error("DB function 'update_assignment_status' not available!"); status_update_success = False

            if progress_data and isinstance(progress_data, dict):
                if db and hasattr(db, 'update_assignment_progress'):
                    progress_update_success = db.update_assignment_progress(assignment_id, progress_data)
                    if not progress_update_success: logger.warning(f"Failed progress update for {assignment_id}")
                else:
                     logger.error("DB function 'update_assignment_progress' not available!"); progress_update_success = False

        except Exception as update_err:
             logger.error(f"Exception during assignment update for {assignment_id}: {update_err}", exc_info=True)
             status_update_success = False; progress_update_success = False
    else: # Nếu không có assignment_id
        status_update_success = True # Coi như thành công vì không cần update
        progress_update_success = True


    # --- Bước 3: Trả về Kết quả ---
    final_success = log_success and status_update_success and progress_update_success

    if final_success:
        response_body = {"status": "success", "message": "Report processed successfully."}
        status_code = 200
    else:
        error_detail = "Failed to process report components (check server logs)."
        if not log_success: error_detail = "Failed to save action logs/UI state."
        elif not status_update_success: error_detail = "Failed to update assignment status."
        elif not progress_update_success: error_detail = "Failed to update assignment progress."
        response_body = {"status": "error", "message": error_detail}
        status_code = 500 if not status_update_success else 200 # Coi lỗi update status là nghiêm trọng

    return response_body, status_code


# --- Hàm xử lý Đăng ký Thiết bị MỚI ---
def handle_device_registration(data: dict) -> tuple[bool, str | None]:

    """
    Xử lý dữ liệu đăng ký từ client và gọi hàm DB.

    Args:
        data: Dictionary chứa dữ liệu từ JSON request của client.

    Returns:
        Tuple (bool, str | None): (True nếu thành công, None) hoặc (False, thông báo lỗi).
    """
    if not data or not isinstance(data, dict):
        return False, "Invalid registration data payload."

    device_id = data.get('device_id')
    device_info = data.get('device_info', {})
    client_version = data.get('client_version')
    managed_accounts = data.get('managed_accounts', [])

    if not device_id:
        return False, "Missing 'device_id'."
    if not isinstance(managed_accounts, list):
         return False, "'managed_accounts' must be a list."

    # Gọi hàm DB để thực hiện đăng ký/cập nhật
    try:
        success = db.register_or_update_device(device_id, device_info, client_version, managed_accounts)
        if success:
            return True, None
        else:
            # Hàm DB trả về False thường do lỗi bên trong đã được log
            return False, "Database operation failed (check server logs)."
    except Exception as e:
        current_app.logger.error(f"Exception during device registration handling for {device_id}: {e}", exc_info=True)
        return False, "Internal server error during registration."
    

# --- Hàm Hỗ trợ Parse Tọa độ ---
def _parse_coordinates(coord_str: str | None) -> dict | None:
    """Hàm phụ trợ để parse chuỗi 'x,y' thành {'x': int, 'y': int}."""
    if not coord_str or ',' not in coord_str:
        return None # Trả về None nếu chuỗi rỗng hoặc không có dấu phẩy
    try:
        # Tách chuỗi bằng dấu phẩy và chuyển thành số nguyên
        x, y = map(int, coord_str.split(','))
        return {"x": x, "y": y}
    except (ValueError, TypeError) as e:
        # Ghi log nếu không parse được (ví dụ: "100,abc")
        logger = current_app.logger if current_app else print
        logger.warning(f"Không thể parse tọa độ: '{coord_str}'. Lỗi: {e}")
        return None # Trả về None nếu lỗi

# --- Hàm Chính Xử lý Dữ liệu UI Thô ---
def process_raw_ui_state(ui_state_data: dict) -> dict | None:
    logger = current_app.logger if current_app else print

    if not isinstance(ui_state_data, dict):
        logger.error("LỖI (process_raw_ui_state): Dữ liệu đầu vào không phải là dictionary.")
        return None

    # Trích xuất dữ liệu
    timestamp = ui_state_data.get('timestamp')
    package_name = ui_state_data.get('package_name')
    activity_name = ui_state_data.get('activity_name')
    ids = ui_state_data.get('ids', [])
    texts = ui_state_data.get('texts', [])
    coords = ui_state_data.get('coords', [])
    # Lấy các mảng tùy chọn khác
    class_names = ui_state_data.get('class_names', [])
    # content_descs = ui_state_data.get('content_descs', []) # Ví dụ nếu có

    # === SỬA LỖI LOGIC KIỂM TRA ĐỘ DÀI ===
    # Chỉ kiểm tra độ dài các mảng cơ bản phải khớp nhau
    base_lengths = [len(ids), len(texts), len(coords)]
    if not base_lengths or len(set(base_lengths)) > 1:
        expected_len = min(base_lengths) if base_lengths else 0 # Lấy min nếu không khớp, 0 nếu list rỗng
        logger.warning(f"CẢNH BÁO (process_raw_ui_state): Độ dài các mảng cơ bản (ids, texts, coords) không khớp: {base_lengths}. Sử dụng độ dài ngắn nhất: {expected_len}.")
    elif base_lengths:
         expected_len = base_lengths[0] # OK nếu độ dài khớp
    else:
         expected_len = 0 # OK nếu tất cả mảng cơ bản đều rỗng

    # Lấy độ dài của các mảng tùy chọn để kiểm tra bên trong vòng lặp
    len_class_names = len(class_names)
    # len_content_descs = len(content_descs)

    # Xây dựng danh sách elements dựa trên expected_len từ các mảng cơ bản
    structured_elements = []
    for i in range(expected_len):
        # Lấy tọa độ an toàn
        coordinates = _parse_coordinates(coords[i])

        # Lấy class_name an toàn (kiểm tra index)
        class_name = class_names[i] if i < len_class_names and class_names[i] else None

        # Lấy content_description an toàn (ví dụ)
        # content_desc = content_descs[i] if i < len_content_descs and content_descs[i] else None

        element = {
            "index": i,
            "resource_id": ids[i] if ids[i] is not None else None,
            "text": texts[i] if texts[i] is not None else None,
            "coordinates": coordinates,
            "class_name": class_name,
            # "content_description": content_desc, # Ví dụ
            "clickable": True # Vẫn giữ lại vì giả định client lọc "Only Clickable"
        }
        structured_elements.append(element)
    # === KẾT THÚC SỬA LỖI LOGIC ===

    structured_state = {
        "timestamp": timestamp,
        "package_name": package_name,
        "activity_name": activity_name,
        "elements": structured_elements # Mảng này giờ sẽ có phần tử nếu ids, texts, coords có dữ liệu
    }

    logger.info(f"INFO (process_raw_ui_state): Đã xử lý thành công dữ liệu UI thô. Tìm thấy {len(structured_elements)} elements.")
    return structured_state


def handle_get_mainloop_strategy(device_id: str) -> dict:
    """
    Xử lý yêu cầu lấy Main Loop Strategy cho device.
    Lấy thông tin từ DB và đóng gói thành JSON package cho client.
    """
    logger = current_app.logger if current_app else print
    if not db:
        logger.error("Database module 'db' not available in phone controller.")
        return {"status": "error", "message": "Server database configuration error."}

    try:
        # 1. Lấy chi tiết thiết bị để tìm mainloop_strategy_id được gán
        # Hàm get_device_details cần trả về dict có cột 'mainloop_strategy_id'
        device_details = db.get_device_details(device_id)
        if not device_details:
            logger.warning(f"Device ID '{device_id}' not found when fetching mainloop strategy.")
            return {"status": "device_not_found", "message": "Device not registered."}

        mainloop_strategy_id = device_details.get('mainloop_strategy_id')
        if not mainloop_strategy_id:
            logger.info(f"Device '{device_id}' does not have a mainloop strategy assigned.")
            return {"status": "no_mainloop_strategy", "message": "No specific mainloop strategy assigned to this device."}

        logger.info(f"Device '{device_id}' assigned mainloop strategy: '{mainloop_strategy_id}'")

        # 2. Lấy định nghĩa chi tiết của Main Loop Strategy này
        strategy_info = db.get_strategy_details(mainloop_strategy_id)
        if not strategy_info or strategy_info.get('strategy_type') != 'mainloop':
            logger.error(f"Assigned mainloop strategy ID '{mainloop_strategy_id}' for device '{device_id}' not found or not type 'mainloop'.")
            return {"status": "error", "message": f"Assigned mainloop strategy '{mainloop_strategy_id}' is invalid."}

        # 3. Lấy Stages và Transitions của strategy
        strategy_stages = db.get_stages_for_strategy(mainloop_strategy_id) or []
        raw_transitions = db.get_strategy_action_sequence(mainloop_strategy_id) or [] # Hàm này trả về list dict đã parse JSON params

        # 4. Đóng gói thành cấu trúc JSON mà client mong đợi
        now_iso = datetime.now(timezone.utc).isoformat()

        # Xử lý action_sequence (tương tự compile_strategy_package nhưng đơn giản hơn?)
        # Cấu trúc này cần khớp với những gì Client Engine Main Loop mong đợi
        action_sequence = []
        for trans in raw_transitions:
            step = {
                "step_id": f"trans_{trans.get('transition_id', 'unk')}", # Tạo ID duy nhất cho step
                "trigger": {
                    "type": trans.get('user_intent', 'any'), # Dùng user_intent làm type trigger? Cần định nghĩa rõ
                    "current_stage_id": trans.get('current_stage_id')
                },
                # Logic điều kiện cần được client diễn giải
                "condition": {
                    "type": trans.get('condition_type'),
                    "value": trans.get('condition_value')
                } if trans.get('condition_type') else None,
                # Loại step (simple, conditional, loop) - Cần logic để xác định từ transition data
                # Tạm thời coi tất cả là simple hoặc dựa vào loop_type
                "type": "loop" if trans.get('loop_type') else "simple", # Ví dụ đơn giản
                # Hành động cần thực thi (Macro)
                "action": {
                    "macro_code": trans.get('action_macro_code'),
                    "params": trans.get('action_params') # Đã được parse thành dict bởi get_strategy_action_sequence
                } if trans.get('action_macro_code') else None,
                # Cấu hình vòng lặp (nếu có)
                "loop_config": {
                    "loop_type": trans.get('loop_type'),
                    "count": trans.get('loop_count'),
                    "condition_type": trans.get('loop_condition_type'),
                    "condition_value": trans.get('loop_condition_value'),
                    # "target_selector": trans.get('loop_target_selector'), # Cần parse JSONB
                    # "variable_name": trans.get('loop_variable_name')
                } if trans.get('loop_type') else None,
                 # Stage tiếp theo nếu step chạy xong
                "next_stage_id": trans.get('next_stage_id')
            }
            action_sequence.append(step)

        # Tạo gói JSON cuối cùng
        mainloop_package = {
            "metadata": {
                "package_format_version": "1.0-mainloop", # Phiên bản riêng cho mainloop
                "strategy_id": mainloop_strategy_id,
                "strategy_name": strategy_info.get('name'),
                "strategy_type": "mainloop",
                "strategy_version": strategy_info.get('updated_at').isoformat() if strategy_info.get('updated_at') else now_iso,
                "compiled_at": now_iso,
                "device_id": device_id # Trả về device_id để client xác nhận
            },
            "execution_config": strategy_info.get('execution_config') or { # Lấy từ strategy nếu có, nếu không dùng default
                 "default_time_slice_seconds": 600,
                 "error_retry_limit": 3,
                 "error_wait_seconds": 300,
                 "sleep_between_cycles_seconds": 60,
                 "report_interval_seconds": 1800
            },
            "device_context": { # Khởi tạo context rỗng hoặc với vài giá trị mặc định
                "managed_accounts_list": [], # Client sẽ tự điền khi chạy macro DEVICE_GET_ACCOUNTS
                "current_account_index": -1,
                "current_account_id": None,
                "account_status_map": {}
                # Thêm các biến mặc định khác nếu cần
            },
            # stages_recognition có thể không cần cho mainloop ban đầu
            # "stages_recognition": { ... },
            "action_sequence": action_sequence # Danh sách các step đã xử lý
        }

        logger.info(f"Successfully assembled mainloop package for device '{device_id}', strategy '{mainloop_strategy_id}'.")
        return mainloop_package

    except Exception as e:
        logger.error(f"Exception in handle_get_mainloop_strategy for device {device_id}: {e}", exc_info=True)
        return {"status": "error", "message": f"Server internal error processing request: {e}"}
def assemble_mainloop_package_from_definition(strategy_id: str) -> dict | None:
    """
    Đóng gói định nghĩa của một Mainloop Strategy thành cấu trúc JSON cho client.
    Hàm này KHÔNG kiểm tra device_id hay assignment.
    Chỉ dùng để xem cấu trúc ví dụ từ Admin UI.
    """
    logger = current_app.logger if current_app else print
    if not db:
        logger.error("Database module 'db' not available.")
        return None

    try:
        # 1. Lấy định nghĩa chi tiết của Main Loop Strategy
        strategy_info = db.get_strategy_details(strategy_id)
        if not strategy_info or strategy_info.get('strategy_type') != 'mainloop':
            logger.error(f"Strategy ID '{strategy_id}' not found or not type 'mainloop'.")
            return None # Trả về None nếu không hợp lệ

        # 2. Lấy Stages và Transitions
        strategy_stages = db.get_stages_for_strategy(strategy_id) or []
        raw_transitions = db.get_strategy_action_sequence(strategy_id) or []

        # 3. Đóng gói thành cấu trúc JSON (Logic tương tự handle_get_mainloop_strategy)
        now_iso = datetime.now(timezone.utc).isoformat()
        action_sequence = []
        for trans in raw_transitions:
            step = {
                "step_id": f"trans_{trans.get('transition_id', 'unk')}",
                "trigger": {
                    "type": trans.get('user_intent', 'any'),
                    "current_stage_id": trans.get('current_stage_id')
                },
                "condition": {
                    "type": trans.get('condition_type'),
                    "value": trans.get('condition_value')
                } if trans.get('condition_type') else None,
                "type": "loop" if trans.get('loop_type') else "simple",
                "action": {
                    "macro_code": trans.get('action_macro_code'),
                    "params": trans.get('action_params')
                } if trans.get('action_macro_code') else None,
                "loop_config": {
                    "loop_type": trans.get('loop_type'),
                    "count": trans.get('loop_count'),
                    "condition_type": trans.get('loop_condition_type'),
                    "condition_value": trans.get('loop_condition_value'),
                } if trans.get('loop_type') else None,
                "next_stage_id": trans.get('next_stage_id')
            }
            action_sequence.append(step)

        mainloop_package = {
            "metadata": {
                "package_format_version": "1.0-mainloop",
                "strategy_id": strategy_id,
                "strategy_name": strategy_info.get('name'),
                "strategy_type": "mainloop",
                "strategy_version": strategy_info.get('updated_at').isoformat() if strategy_info.get('updated_at') else now_iso,
                "compiled_at": now_iso,
                "device_id": "EXAMPLE_DEVICE_ID" # ID ví dụ
            },
            "execution_config": strategy_info.get('execution_config') or {
                 # Config mặc định nếu không có trong DB
                 "default_time_slice_seconds": 600, "error_retry_limit": 3,
                 "error_wait_seconds": 300, "sleep_between_cycles_seconds": 60,
                 "report_interval_seconds": 1800
            },
            "device_context": { # Context ví dụ
                "managed_accounts_list": [{"account_id": "example_acc_1", "clone_context": "main"}],
                "current_account_index": -1,
                "account_status_map": {"example_acc_1": "active_logged_in"}
            },
            "action_sequence": action_sequence
        }
        return mainloop_package

    except Exception as e:
        logger.error(f"Exception in assemble_mainloop_package_from_definition for {strategy_id}: {e}", exc_info=True)
        return None
    
# === HÀM LẬP KẾ HOẠCH KHÁM PHÁ ĐƠN GIẢN (ĐÃ CẬP NHẬT DÙNG NEO4J) ===
def plan_simple_exploration_action(app_name: str, current_screen_id: str,
                                   previous_action_context: dict | None) -> dict | None:
    """
    Quyết định hành động khám phá tiếp theo, tránh lặp lại hành động click
    không hiệu quả. Chỉ xem xét click các element có resource_id.
    Trả về cấu trúc nextAction chuẩn hóa.

    Args:
        app_name: Tên package của ứng dụng.
        current_screen_id: ID màn hình hiện tại đã được server xác nhận.
        previous_action_context: Dict chứa thông tin về hành động trước đó (nếu có).

    Returns:
        Dictionary chứa thông tin nextAction hoặc None nếu lỗi/không có hành động.
    """
    logger = current_app.logger if current_app else print
    logger.info(f"Planner: Planning action for app='{app_name}', screen='{current_screen_id}'")
    if previous_action_context: logger.debug(f"Planner: Previous action context: {previous_action_context}")

    # --- Kiểm tra đầu vào và module ---
    if not graph_db or not app_name or not current_screen_id:
        logger.error("Planner Error: Missing graph_db module, app_name, or screen_id.")
        return None

    next_action = None
    # --- Cấu hình Randomness ---
    ADD_RANDOM_DELAY = True; MIN_DELAY_MS = 150; MAX_DELAY_MS = 600
    ADD_RANDOM_OFFSET = True; MAX_OFFSET_X = 4; MAX_OFFSET_Y = 4
    # --------------------------

    try:
        # --- 1. Lấy Thông tin Màn hình và Transitions đã có từ Neo4j ---
        screen_details = graph_db.get_screen_properties(current_screen_id, app_name)
        outgoing_transitions = graph_db.get_outgoing_transitions(current_screen_id, app_name)

        if not screen_details:
            logger.warning(f"Planner Warning: Could not find screen details in Neo4j for {current_screen_id}. Cannot plan.")
            return None
        if outgoing_transitions is None:
             logger.error(f"Planner Error: Failed to get outgoing transitions for {current_screen_id}. Aborting.")
             return None

        # Lấy danh sách elements từ state đã lưu trong Neo4j
        processed_ui_state = screen_details.get('processed_ui_state')
        screen_elements = processed_ui_state.get('elements', []) if processed_ui_state else []
        logger.debug(f"Planner: Screen {current_screen_id} has {len(screen_elements)} elements. Found {len(outgoing_transitions)} outgoing transitions.")

        # --- 2. Kiểm tra Vòng lặp và Lấy Target của Hành động Trước đó ---
        is_loop = False
        previous_target_id = None # ID của element đã click gây ra loop (nếu có)

        if previous_action_context:
            source_context = previous_action_context.get('source_screen_context')
            action_details_from_prev = previous_action_context.get('action_details')
            if source_context and action_details_from_prev:
                previous_source_id = source_context.get('screenId')
                # Kiểm tra xem ID nguồn của hành động trước có trùng ID hiện tại không
                if previous_source_id == current_screen_id:
                    is_loop = True
                    # Nếu hành động trước đó là click, lấy ID target của nó
                    if action_details_from_prev.get('actionType') == 'click':
                         previous_target_id = action_details_from_prev.get('onElementId') # Lấy đúng key 'onElementId'
                    logger.info(f"Planner: Detected loop on screen {current_screen_id}. Previous action: {action_details_from_prev}. Previous click target ID: {previous_target_id}")

        # --- 3. Tìm hành động CLICK mới chưa được khám phá ---
        found_click_action = False
        if screen_elements:
            for element in screen_elements:
                element_id = element.get('resource_id')
                # <<< HEURISTIC: Chỉ xem xét click nếu element có resource_id >>>
                if not element_id:
                    continue

                # Kiểm tra xem đã có transition click nào đi ra từ screen này cho element này chưa
                click_tried = False
                for trans in outgoing_transitions:
                    # Chỉ khớp chính xác actionType='click' và onElementId
                    if trans.get('actionType') == 'click' and trans.get('onElementId') == element_id:
                        click_tried = True
                        # logger.debug(f"Planner: Element ID {element_id} already has an outgoing click transition.")
                        break

                # Nếu chưa thử click element này
                if not click_tried:
                    # <<< LOGIC TRÁNH LẶP CLICK >>>
                    # Nếu đang bị lặp (is_loop=True) VÀ hành động trước đó là click
                    # VÀ element hiện tại chính là element gây lặp -> Bỏ qua element này
                    if is_loop and previous_target_id is not None and previous_target_id == element_id:
                        logger.warning(f"Planner: Skipping element ID {element_id} because clicking it JUST caused the current loop.")
                        continue # <<< Xét element tiếp theo
                    # =================================

                    # Tìm thấy hành động click mới hợp lệ!
                    element_text = element.get('text')
                    element_class = element.get('class_name') # Vẫn lấy class nếu state có
                    element_coords = element.get('coordinates')
                    logger.info(f"Planner: Found unexplored clickable element: id='{element_id}', text='{element_text}'")

                    # Chuẩn bị params.target (bao gồm cả coordinates)
                    target_element_data = {
                        "resource_id": element_id,
                        "text": element_text,
                        "class_name": element_class, # Có thể là None
                        "coordinates": element_coords # Có thể là None
                    }
                    # Loại bỏ key có giá trị None khỏi target
                    target_element_data = {k:v for k,v in target_element_data.items() if v is not None}

                    # Chỉ tạo action nếu target có thông tin định danh (ít nhất là ID)
                    if target_element_data.get("resource_id"): # Kiểm tra lại ID vì heuristic dựa vào nó
                        # Tạo nextAction theo cấu trúc chuẩn
                        next_action = {
                            "actionType": "run_macro",
                            "macro_code": "UI_CLICK",
                            "params": {
                                "target": target_element_data
                            }
                        }
                        # Thêm randomness (tùy chọn)
                        if ADD_RANDOM_DELAY:
                            next_action["random_delay_ms"] = { "min": MIN_DELAY_MS, "max": MAX_DELAY_MS }
                        if ADD_RANDOM_OFFSET and element_coords: # Chỉ thêm offset nếu có tọa độ
                            next_action["random_offset_xy"] = { "x_max": MAX_OFFSET_X, "y_max": MAX_OFFSET_Y }

                        found_click_action = True
                        break # Dừng tìm kiếm khi đã tìm thấy hành động click mới
                    else:
                        logger.warning(f"Planner: Target element data for ID {element_id} became empty after cleaning None values. Skipping.")

        # --- 4. Nếu không tìm thấy CLICK mới -> Xử lý Fallback (tránh lặp fallback) ---
        if not found_click_action:
            # Kiểm tra các hành động fallback đã được thử TỪ node này chưa
            swipe_up_tried = any(t.get('actionType') == 'swipe_up' for t in outgoing_transitions)
            go_back_tried = any(t.get('actionType') == 'NAV_GO_BACK' for t in outgoing_transitions)

            if not swipe_up_tried:
                logger.info(f"Planner: No new clicks. Suggesting SWIPE_UP (untried from this screen state).")
                next_action = {
                    "actionType": "run_macro", "macro_code": "UI_SWIPE_UP",
                    "params": {}
                }
                if ADD_RANDOM_DELAY:
                    next_action["random_delay_ms"] = { "min": int(MIN_DELAY_MS/2), "max": int(MAX_DELAY_MS/2) }
            elif not go_back_tried:
                logger.info(f"Planner: No new clicks and SWIPE_UP already tried. Suggesting NAV_GO_BACK (untried).")
                next_action = {
                    "actionType": "run_macro", "macro_code": "NAV_GO_BACK",
                    "params": {}
                }
                # Có thể thêm delay cho Back
            else:
                # Đã thử hết các click khả thi (có ID) và cả swipe, back từ màn hình này
                logger.warning(f"Planner: No new actions found for screen {current_screen_id} (all clicks with ID, swipe, back seem explored from this state). Returning no_action.")
                next_action = None # -> Server sẽ trả status: "no_action"

    except Exception as e:
        logger.error(f"Planner: Error during planning for screen {current_screen_id}: {e}", exc_info=True)
        next_action = None

    # --- Log kết quả cuối cùng ---
    if next_action:
        logger.info(f"Planner: Final planned action for screen {current_screen_id}: {next_action.get('macro_code')}")
        logger.debug(f"Planner: Final nextAction details: {next_action}")
    else:
        logger.warning(f"Planner: Returning None for screen {current_screen_id} (no suitable action found or error occurred).")

    return next_action


def determine_screen_id_from_state(processed_ui_state: dict) -> str | None:
    """
    Xác định screenId duy nhất từ dữ liệu UI state đã được xử lý.
    Sử dụng logic tương tự như trong build_app_map_task.

    Args:
        processed_ui_state: Dictionary chứa thông tin UI đã xử lý
                           (gồm package_name, activity_name, elements list).

    Returns:
        Chuỗi screenId hoặc None nếu có lỗi.
    """
    logger = current_app.logger if current_app else print
    if not processed_ui_state or not isinstance(processed_ui_state, dict):
        logger.error("determine_screen_id_from_state: Invalid or empty processed_ui_state received.")
        return None

    app_name = processed_ui_state.get('package_name')
    activity_name = processed_ui_state.get('activity_name')
    elements = processed_ui_state.get('elements', [])

    # Nếu thiếu thông tin cơ bản, không thể tạo ID đáng tin cậy
    if not app_name:
        logger.warning("determine_screen_id_from_state: Missing package_name in UI state.")
        # Có thể trả về None hoặc một ID mặc định/lỗi tùy logic xử lý tiếp theo
        return f"error_missing_pkg_{int(time.time())}"

    screen_id_generated = None
    structure_hash_str = "default_screen_id" # Fallback nếu không có activity/elements

    try:
        # Tạo hash dựa trên activity và cấu trúc element (logic giống trong build_app_map_task)
        if activity_name or elements:
            # Tạo một chuỗi đại diện cấu trúc, sắp xếp để đảm bảo thứ tự không ảnh hưởng hash
            element_repr_list = sorted([
                f"id={el.get('resource_id','_')};txt={el.get('text','_')};cls={el.get('class_name','_')}" # Thêm class_name nếu có
                for el in elements if isinstance(el, dict) # Đảm bảo el là dict
            ])
            structure_string = f"{app_name}|{activity_name or 'UnknownActivity'}|{'|'.join(element_repr_list)}"
            # Sử dụng SHA256 và lấy một phần hex digest làm ID
            structure_hash_str = hashlib.sha256(structure_string.encode('utf-8')).hexdigest()[:24] # Lấy 24 ký tự

        screen_id_generated = structure_hash_str
        # logger.debug(f"Generated screen ID: {screen_id_generated} for activity '{activity_name}'") # Log nếu cần

    except Exception as hash_err:
         logger.error(f"Error generating screen hash for {app_name}, activity {activity_name}: {hash_err}", exc_info=True)
         screen_id_generated = f"error_hash_{int(time.time())}" # ID tạm thời nếu lỗi hash

    return screen_id_generated

def handle_explore_step():
    """Xử lý yêu cầu explore_step từ client."""
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()

    # --- Trích xuất dữ liệu từ request ---
    # !!! Quan trọng: Cần xác định cách lấy các thông tin này từ context hoặc request
    # Ví dụ: device_id có thể lấy từ header, session hoặc data?
    device_id = data.get('device_id', 'unknown_device') # Cần cơ chế lấy device_id đáng tin cậy
    account_id = data.get('account_id') # Cần cơ chế lấy account_id đáng tin cậy (kiểu dữ liệu khớp DB)
    app_name = data.get('app_name', 'unknown_app') # Nên yêu cầu client gửi app_name
    mapping_goal = data.get('mapping_goal') # Client có thể gửi mục tiêu hiện tại

    previous_action = data.get('previous_action') # Hành động client vừa thực hiện
    reported_ui_state = data.get('ui_state') # Trạng thái UI client báo cáo
    result_status = data.get('result_status', 'success') # Mặc định là success nếu không có lỗi báo về
    error_message = data.get('error_message')

    if not reported_ui_state:
         return jsonify({"error": "Missing 'ui_state' in request"}), 400
    if not previous_action:
         # Có thể chấp nhận nếu đây là bước đầu tiên? Hoặc yêu cầu luôn có?
         print("Warning: Missing 'previous_action' in explore_step request.")
         # previous_action = {"action": "start"} # Hoặc gán giá trị mặc định

    next_action = None # Khởi tạo
    screen_id_generated = None # Khởi tạo
    log_entry_data = {} # Khởi tạo
    try:
        # !!! Cần hàm lấy task đang active cho device !!!
        active_task = database.get_active_task_for_device(device_id) # Ví dụ

        if active_task and active_task.get('mapping_status') == 'paused':
            print(f"Mapping paused for device {device_id}, task {active_task.get('assignment_id')}")
            # Trả về action chờ 5 phút
            return jsonify({"action": "wait", "duration": 300, "reason": "Mapping is paused by admin"})

        # Nếu không paused hoặc không tìm thấy task active, tiếp tục bình thường
        mapping_goal = active_task.get('mapping_goal') if active_task else None
        # ... (tiếp tục gọi get_screen_with_elements, AI planner, ...)

    except Exception as task_check_error:
        print(f"Error checking task status for device {device_id}: {task_check_error}")
    try:
        # --- Tính toán Screen ID ---
        # !!! Cần đảm bảo hàm determine_screen_id_from_state tồn tại và hoạt động đúng
        screen_id_generated = determine_screen_id_from_state(reported_ui_state) # Gọi hàm tính screen_id

        screen_elements_from_db = graph_db.get_screen_with_elements(screen_id_generated)
        # screen_elements sẽ là list các dict elements hoặc None nếu screen mới
        current_screen_elements = screen_elements_from_db['elements'] if screen_elements_from_db and 'elements' in screen_elements_from_db else []

        # Lấy mapping_goal (ví dụ từ data request hoặc DB dựa trên device/task)
        mapping_goal = data.get('mapping_goal') # Hoặc lấy từ DB nếu được gán cho task

        # --- Gọi AI Planner đã nâng cấp ---
        next_action = ai_service.plan_exploration_action(
            current_screen_id=screen_id_generated,
            ui_state=reported_ui_state,
            screen_elements=current_screen_elements, # Truyền thông tin elements đã biết
            mapping_goal=mapping_goal # Truyền mục tiêu
        )

        # --- Xóa/Comment out các lệnh cập nhật Neo4j trực tiếp hoặc trigger task cũ ---
        # Ví dụ:
        # # graph_db.merge_screen(...) # <--- XÓA/COMMENT OUT
        # # graph_db.merge_transition(...) # <--- XÓA/COMMENT OUT
        # # trigger_background_task('build_app_map_task', ...) # <--- XÓA/COMMENT OUT

        # --- Chuẩn bị dữ liệu log ---
        log_entry_data = {
            'device_id': device_id,
            'account_id': account_id,
            'app_name': app_name,
            'mapping_goal': mapping_goal,
            'previous_action': previous_action,
            'reported_ui_state': reported_ui_state,
            'screen_id_generated': screen_id_generated,
            'result_status': result_status,
            'error_message': error_message,
            'next_action_suggested': next_action # Lưu lại gợi ý của AI
        }

        # --- Ghi Log vào PostgreSQL ---
        log_id = add_exploration_log(log_entry_data)
        if not log_id:
             print("Error: Failed to add exploration log to database.")
             # Có thể quyết định trả lỗi cho client hoặc tiếp tục trả next_action

        # --- Trả về hành động tiếp theo cho client ---
        return jsonify(next_action if next_action else {"action": "wait", "duration": 10, "reason": "No action planned"})

    except Exception as e:
        print(f"Error in handle_explore_step: {e}")
        traceback.print_exc() # In chi tiết lỗi và stack trace

        # Ghi log lỗi ngay cả khi có exception xảy ra trước khi gọi AI Planner
        if not log_entry_data: # Nếu lỗi xảy ra trước khi chuẩn bị xong log_data
             log_entry_data = {
                'device_id': device_id, 'account_id': account_id, 'app_name': app_name,
                'previous_action': previous_action, 'reported_ui_state': reported_ui_state,
                'screen_id_generated': screen_id_generated if screen_id_generated else 'error_before_sid',
                'result_status': 'error',
                'error_message': f"Server error: {e}",
                'next_action_suggested': None
             }
        else: # Nếu lỗi xảy ra sau khi đã có log_data cơ bản
            log_entry_data['result_status'] = 'error'
            log_entry_data['error_message'] = f"Server error during planning: {e}"
            log_entry_data['next_action_suggested'] = None

        try:
            add_exploration_log(log_entry_data)
        except Exception as log_err:
            print(f"CRITICAL: Failed to log error state: {log_err}")

        return jsonify({"error": "An internal server error occurred"}), 500
# ... (các hàm controller khác) ...




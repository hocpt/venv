
from .. import database as db
import json
from datetime import datetime, timezone
from flask import current_app, jsonify,request
import traceback # Giữ lại import traceback
from .. import graph_db
# Import db từ app cha và ai_service nếu cần dùng sau này
import traceback
from .. import ai_service # Import cả module ai_service
import hashlib 
import time
import random
from app.database import add_exploration_log
from app import ai_service
from urllib.parse import urlparse
from ..database import get_screen_definitions_for_app
ADD_RANDOM_DELAY = True
MIN_DELAY_MS = 150
MAX_DELAY_MS = 600
ADD_RANDOM_OFFSET = True
MAX_OFFSET_X = 4
MAX_OFFSET_Y = 4
try:
    # Nếu bạn đặt các hàm này trong utils.py cùng cấp với controller.py
    from .utils import determine_screen_id_from_state, process_raw_ui_state, _parse_coordinates_safe
    # Hoặc nếu chúng được định nghĩa trong chính controller.py
    # (Bạn cần đảm bảo các hàm này đã được định nghĩa)
    # from .controller import determine_screen_id_from_state, process_raw_ui_state, _parse_coordinates_safe
    # Hoặc nếu chúng ở cấp app
    # from ..utils import determine_screen_id_from_state, process_raw_ui_state, _parse_coordinates_safe
except ImportError:
     print("WARNING (phone/controller.py): Could not import helper functions (determine_screen_id_from_state, process_raw_ui_state). Define or import them.")
     # Định nghĩa tạm thời để tránh lỗi NameError khi chạy, nhưng cần thay thế bằng định nghĩa thật
     def determine_screen_id_from_state(state): return "placeholder_sid"
     def process_raw_ui_state(state): return state # Trả về nguyên trạng nếu không parse được
     def _parse_coordinates_safe(coord): return None

# Import hàm planner (đảm bảo tên hàm và vị trí đúng)
try:
    # Giả sử planner nằm trong ai_service.py
    from ..ai_service import plan_exploration_action
    # Hoặc nếu bạn dùng planner đơn giản:
    # from .planner import plan_simple_exploration_action as plan_exploration_action # Ví dụ tên hàm planner
except ImportError:
     print("WARNING (phone/controller.py): Could not import exploration planner function. Define or import it.")
     def plan_exploration_action(*args, **kwargs): return None 

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



# ... (Các hàm khác như compile_strategy_package, ...) ...

def handle_explore_step(device_id: str, account_id: str,
                        # current_screen_id_from_client: str | None, # Không cần thiết nữa nếu server tự xác định
                        raw_ui_state: dict, previous_action: dict | None,
                        screenshot_filename: str | None = None,
                        **kwargs) -> tuple[dict, int]:
    logger = current_app.logger if current_app else print
    logger.info(f"[Explore Step Ctrl] Handling step for device: {device_id}, account: {account_id}")
    # === Dòng log này giờ sẽ đúng vì tham số là screenshot_filename ===
    logger.debug(f"[Explore Step Ctrl] Received screenshot_filename in handle_explore_step: '{screenshot_filename}' (Type: {type(screenshot_filename)})")
    # ===============================================================
    is_screen_defined_by_pie = False # Cờ mới
    response_body = {}
    http_status_code = 500
    confirmed_target_screen_id = None
    app_name = None
    activity_name = None
    processed_ui_state = None
    next_action = None

    try:
        # 1. Xử lý State
        logger.debug("[Explore Step Ctrl] Processing raw UI state...")
        processed_ui_state = process_raw_ui_state(raw_ui_state)
        if not processed_ui_state:
            raise ValueError("Failed to process raw UI state.")
        logger.debug("[Explore Step Ctrl] Raw UI state processed.")
        app_name = processed_ui_state.get('package_name')
        if not app_name: raise ValueError("Cannot determine app_name from processed state.")
        activity_name = processed_ui_state.get('activity_name')
        elements_list_for_pie = processed_ui_state.get('elements', [])
        original_screen_width = processed_ui_state.get('screen_width')
        original_screen_height = processed_ui_state.get('screen_height')
        extracted_elements_for_neo4j = elements_list_for_pie # Dùng chung
        # 2. Xác định Screen ID Đích
        logger.debug("[Explore Step Ctrl] Determining target screen ID...")
        confirmed_target_screen_id = determine_screen_id_from_state(processed_ui_state)
        if not confirmed_target_screen_id or confirmed_target_screen_id.startswith("error_"):
            raise ValueError(f"Failed to determine valid target screen ID (Result: {confirmed_target_screen_id}).")
        logger.info(f"[Explore Step Ctrl] Confirmed Target Screen ID: {confirmed_target_screen_id}")
        screen_id_to_use = determine_screen_id_by_defined_pie(
            app_name, activity_name, elements_list_for_pie, get_screen_definitions_for_app
        )
        if screen_id_to_use:
            is_screen_defined_by_pie = True
            logger.info(f"[Explore Step Ctrl] Matched defined PIE. Screen ID to use: {screen_id_to_use}")
        else:
            # Không khớp PIE nào -> Tạo ID tạm thời dựa trên hash của tất cả element IDs hiện tại
            # Điều này giúp lưu lại màn hình lạ để admin xem xét sau
            # Nhưng screen_id này không phải là "chuẩn"
            logger.warning(f"[Explore Step Ctrl] No defined PIE matched. Generating temporary unknown screen_id.")
            all_element_ids_str = "|".join(sorted([str(el.get('element_id','')) for el in elements_list_for_pie]))
            temp_hash_input = f"{app_name}|{activity_name or 'UnknownActivity'}|{all_element_ids_str}"
            screen_id_to_use = f"unknown_{hashlib.sha256(temp_hash_input.encode('utf-8')).hexdigest()[:16]}"
            is_screen_defined_by_pie = False
            logger.info(f"[Explore Step Ctrl] Generated temporary unknown screen_id: {screen_id_to_use}")

        confirmed_target_screen_id = screen_id_to_use
        # 3. Lấy App Name, Activity Name
        app_name = processed_ui_state.get('package_name')
        if not app_name: raise ValueError("Cannot determine app_name from processed state.")
        activity_name = processed_ui_state.get('activity_name')
        logger.debug(f"[Explore Step Ctrl] App Name: {app_name}, Activity: {activity_name}")

        # === SỬ DỤNG screenshot_filename ĐỂ LƯU VÀO NEO4J ===
        # Giá trị này là tên file (hoặc path tương đối như 'screenshots/file.png' tùy vào client gửi gì)
        path_to_store_in_neo4j = screenshot_filename
        logger.debug(f"[Explore Step Ctrl] Path to store in Neo4j (from screenshot_filename): '{path_to_store_in_neo4j}'")
        # =================================================

        # 4. Ghi Log PostgreSQL
        try:
            ui_state_for_log_saving = json.dumps(processed_ui_state, ensure_ascii=False, default=str)
            placeholder_log_entry = {"macro": "SYSTEM_EXPLORE_STATE_RECEIVED", "status": "info"}
            if db and hasattr(db, 'add_phone_action_logs'):
                 db.add_phone_action_logs(assignment_id=None, device_id=device_id, account_id=account_id,
                                         logs=[placeholder_log_entry], structured_ui_state_json=ui_state_for_log_saving)
        except Exception as pg_log_err:
             logger.error(f"[Explore Step Ctrl] Error logging to PostgreSQL: {pg_log_err}", exc_info=True)


        # 5. Cập nhật Neo4j
        logger.info(f"[Explore Step Ctrl] Starting Neo4j update for screen: {confirmed_target_screen_id}...")
        extracted_elements_for_db = processed_ui_state.get('elements', [])

        # 5a. Merge Node Đích
        logger.debug(f"[Explore Step Ctrl] Calling graph_db.merge_screen with screenshot_path: '{path_to_store_in_neo4j}'")
        path_to_store_in_neo4j = screenshot_filename 
        node_success = graph_db.merge_screen(
            screen_id=confirmed_target_screen_id,
            app_name=app_name,
            activity_name=activity_name,
            extracted_elements=extracted_elements_for_neo4j,
            screenshot_path=path_to_store_in_neo4j,
            screen_width=original_screen_width,    
            screen_height=original_screen_height,
            is_defined_by_pie=is_screen_defined_by_pie # Truyền cờ này
        )
        logger.debug(f"[Explore Step Ctrl] Target node merge result: {node_success}")

        if not node_success:
            logger.error(f"[Explore Step Ctrl] Failed to merge target screen node {confirmed_target_screen_id}.")
        else:
            edge_success = True
            if previous_action and isinstance(previous_action, dict):
                 source_context = previous_action.get('source_screen_context')
                 action_details = previous_action.get('action_details')
                 result_status_prev = previous_action.get('result_status', 'success')
                 if source_context and action_details:
                     source_screen_id_prev = source_context.get('screenId')
                     if source_screen_id_prev and result_status_prev == 'success' and source_screen_id_prev != confirmed_target_screen_id:
                          edge_success = graph_db.merge_transition(
                              source_screen_id=source_screen_id_prev,
                              target_screen_id=confirmed_target_screen_id,
                              app_name=app_name,
                              action_details=action_details,
                              result_status=result_status_prev,
                              log_id=None
                          )
                          if not edge_success: logger.error(f"[Explore Step Ctrl] graph_db.merge_transition returned False.")
            neo4j_update_success = node_success and edge_success
            if neo4j_update_success: logger.info(f"[Explore Step Ctrl] Sync Neo4j update completed for target {confirmed_target_screen_id}.")
            else: logger.warning(f"[Explore Step Ctrl] Sync Neo4j update potentially incomplete for target {confirmed_target_screen_id} (NodeOK:{node_success}, EdgeOK:{edge_success}).")

        # 6. Gọi Planner
        logger.debug(f"[Explore Step Ctrl] Calling planner for screen: {confirmed_target_screen_id}...")
        next_action = plan_intelligent_exploration_action(
            current_screen_id=confirmed_target_screen_id, # screen_id đã xác nhận
            app_name=app_name,
            processed_ui_state=processed_ui_state, # Truyền state đã xử lý
            previous_action=previous_action
        )
        logger.debug(f"[Explore Step Ctrl] Planner returned: {next_action}")

        # 7. Xác định Kết quả Cuối cùng
        if next_action and isinstance(next_action, dict):
            response_body = {
                "status": "success", "message": "Next action planned.",
                "confirmedCurrentScreenId": confirmed_target_screen_id,
                "nextAction": next_action
            }
            http_status_code = 200
        else:
            response_body = {
                "status": "no_action", "message": "No further exploration action planned.",
                "confirmedCurrentScreenId": confirmed_target_screen_id,
                "nextAction": None
            }
            http_status_code = 200

    except ValueError as ve:
        logger.error(f"[Explore Step Ctrl] Validation Error (Device: {device_id}): {ve}", exc_info=True)
        response_body = {"status": "error", "message": str(ve), "confirmedCurrentScreenId": confirmed_target_screen_id, "nextAction": None}
        http_status_code = 400
    except Exception as e:
        logger.error(f"[Explore Step Ctrl] Unexpected Error (Device: {device_id}): {e}", exc_info=True)
        response_body = {"status": "error", "message": f"Internal server error: {type(e).__name__}", "confirmedCurrentScreenId": confirmed_target_screen_id, "nextAction": None}
        http_status_code = 500

    logger.info(f"[Explore Step Ctrl] Responding for {device_id}: Status={response_body.get('status')}, Screen={response_body.get('confirmedCurrentScreenId')}, NextAction={response_body.get('nextAction') is not None}")
    return response_body, http_status_code


def plan_sequential_click(current_screen_id: str, app_name: str,
                          processed_ui_state: dict | None,
                          previous_action: dict | None) -> dict | None:
    """
    Planner đơn giản: Click tuần tự element có ID (ưu tiên resource-id).
    Trả về cấu trúc nextAction chuẩn cho MacroDroid.
    """
    logger = current_app.logger if current_app else print
    logger.info(f"[Sequential Planner] Planning for screen: {current_screen_id}")

    next_action = None
    elements_to_consider = []
    if processed_ui_state and isinstance(processed_ui_state.get('elements'), list):
        elements_to_consider = processed_ui_state['elements']

    if not elements_to_consider:
        logger.warning(f"[Sequential Planner] No elements in processed state for {current_screen_id}.")
        # <<< Trả về cấu trúc BACK chuẩn >>>
        return {
            "actionType": "run_macro",
            "macro_code": "NAV_GO_BACK",
            "params": {},
            "reason": "No elements detected in current state."
        }

    try:
        # Lấy các hành động đã thử từ màn hình này
        outgoing_transitions = graph_db.get_outgoing_transitions(current_screen_id, app_name) or []
        tried_element_ids = set()
        tried_back = False
        for trans in outgoing_transitions:
            action = trans.get('action_details')
            if isinstance(action, dict):
                action_type = action.get('actionType')
                macro_code = action.get('macro_code') # Kiểm tra cả macro_code
                if action_type == 'run_macro':
                    if macro_code == 'UI_CLICK':
                        # Lấy ID từ params.target
                        target = action.get('params', {}).get('target', {})
                        el_id = target.get('element_id') or target.get('resource_id') # Ưu tiên element_id nếu có
                        if el_id: tried_element_ids.add(el_id)
                    elif macro_code == 'NAV_GO_BACK':
                        tried_back = True
                elif action_type == 'click': # Xử lý cả định dạng cũ nếu có
                    el_id = action.get('element_id') or action.get('onElementId')
                    if el_id: tried_element_ids.add(el_id)

        # Xác định element gây ra loop (nếu có)
        looping_element_id = None
        is_loop = False
        if previous_action and isinstance(previous_action, dict):
             source_context = previous_action.get('source_screen_context')
             action_details = previous_action.get('action_details')
             if source_context and action_details:
                 previous_source_id = source_context.get('screen_id')
                 if previous_source_id == current_screen_id:
                      is_loop = True
                      # Lấy ID từ action cũ (cần kiểm tra cả hai định dạng)
                      if action_details.get('actionType') == 'click':
                           looping_element_id = action_details.get('element_id') or action_details.get('onElementId')
                      elif action_details.get('actionType') == 'run_macro' and action_details.get('macro_code') == 'UI_CLICK':
                           target = action_details.get('params', {}).get('target', {})
                           looping_element_id = target.get('element_id') or target.get('resource_id')


        logger.debug(f"[Sequential Planner] Screen: {current_screen_id}, Tried elements: {tried_element_ids}, Tried back: {tried_back}, Is loop: {is_loop}, Looping element: {looping_element_id}")

        # Duyệt qua element để tìm hành động click mới
        for element in elements_to_consider:
            element_id = element.get('element_id')
            id_type = element.get('identifier_type')

            if element_id and id_type and (element_id not in tried_element_ids):
                if is_loop and looping_element_id == element_id:
                    logger.warning(f"[Sequential Planner] Skipping element '{element_id}' due to immediate loop.")
                    continue

                # Ưu tiên resource-id hoặc content-desc
                if id_type in ['resource-id', 'content-desc']:
                    logger.info(f"[Sequential Planner] Found UNTRIED element: id='{element_id}' (type='{id_type}'). Suggesting UI_CLICK.")

                    # <<< TẠO CẤU TRÚC OUTPUT CHUẨN >>>
                    target_params = {}
                    # Luôn thêm ID và Text nếu có
                    if id_type == 'resource-id': target_params['resource_id'] = element_id
                    elif id_type == 'content-desc': target_params['content_description'] = element_id # Hoặc dùng key khác nếu client cần
                    element_text = element.get('text_content')
                    if element_text: target_params['text'] = element_text

                    # Thêm coordinates nếu có
                    coords = element.get('coordinates')
                    if coords and isinstance(coords, dict):
                         target_params['coordinates'] = coords

                    # Thêm các thuộc tính khác nếu cần (ví dụ: class_name)
                    # element_type = element.get('element_type')
                    # if element_type: target_params['class_name'] = element_type

                    next_action = {
                        "actionType": "run_macro",
                        "macro_code": "UI_CLICK",
                        "params": {
                            "target": target_params
                        },
                        "reason": f"Clicking untried element ({id_type})" # Thêm reason để debug
                    }

                    # Thêm randomness
                    if ADD_RANDOM_DELAY:
                        next_action["random_delay_ms"] = { "min": MIN_DELAY_MS, "max": MAX_DELAY_MS }
                    if ADD_RANDOM_OFFSET and 'coordinates' in target_params: # Chỉ thêm offset nếu có tọa độ
                        next_action["random_offset_xy"] = { "x_max": MAX_OFFSET_X, "y_max": MAX_OFFSET_Y }

                    break # Đã tìm thấy hành động -> dừng

        # Nếu không tìm thấy hành động click mới
        if not next_action:
            logger.info(f"[Sequential Planner] No new elements to click on screen {current_screen_id}.")
            if not tried_back:
                logger.info("[Sequential Planner] Suggesting NAV_GO_BACK action.")
                # <<< Trả về cấu trúc BACK chuẩn >>>
                next_action = {
                    "actionType": "run_macro",
                    "macro_code": "NAV_GO_BACK",
                    "params": {},
                    "reason": "No new elements to click, trying back."
                }
            else:
                logger.warning(f"[Sequential Planner] All elements and BACK explored for screen {current_screen_id}. Stuck.")
                 # <<< Trả về cấu trúc STUCK chuẩn (nếu có) hoặc WAIT >>>
                 # Client của bạn có xử lý actionType "stuck" không? Nếu không, dùng "wait".
                next_action = {
                    "actionType": "wait", # Hoặc "stuck" nếu client hiểu
                    "duration": 60, # Chờ 1 phút ví dụ
                    "reason": "Explored all elements and back action."
                }

    except Exception as e:
        logger.error(f"[Sequential Planner] Error during planning for screen {current_screen_id}: {e}", exc_info=True)
         # <<< Trả về cấu trúc WAIT hoặc STUCK khi lỗi >>>
        next_action = {
            "actionType": "wait", # Hoặc "stuck"
            "duration": 60,
            "reason": f"Planner error: {e}"
        }

    logger.debug(f"[Sequential Planner] Planned nextAction: {next_action}")
    return next_action



# === HÀM PLANNER THÔNG MINH MỚI ===
def plan_intelligent_exploration_action(
    current_screen_id: str,
    app_name: str,
    processed_ui_state: dict | None,
    previous_action: dict | None
) -> dict | None:
    """
    Quyết định hành động khám phá tiếp theo một cách thông minh hơn,
    dựa vào phân loại element và lịch sử tương tác.

    Args:
        current_screen_id: ID màn hình hiện tại đã xác nhận.
        app_name: Tên package của ứng dụng.
        processed_ui_state: Dictionary chứa UI state đã xử lý của màn hình hiện tại.
        previous_action: Dictionary chứa thông tin về hành động trước đó.

    Returns:
        Dictionary chứa thông tin nextAction hoặc None nếu không có hành động phù hợp.
    """
    logger = current_app.logger if current_app else print
    logger.info(f"[Intelligent Planner] Planning for screen: {current_screen_id}, app: {app_name}")

    # --- Cấu hình Planner (Có thể chuyển ra config.py) ---
    CLASSIFICATION_PRIORITY = {
        'primary_action': 1,
        'input_field': 2,
        'navigation': 3,
        'strategy_critical': 4, # Ưu tiên cao nếu được đánh dấu
        'secondary_action': 5,
        'unclassified': 10,
        # 'non_interactive': 99, # Sẽ bị lọc bỏ
        # 'ignore': 100          # Sẽ bị lọc bỏ
    }
    DEFAULT_PRIORITY = 99
    INTERACTABLE_TYPES = ['resource-id', 'content-desc'] # Chỉ xem xét element có ID này
    NON_INTERACTIVE_CLASSES = ['ignore', 'non_interactive']
    # Randomness options
    ADD_RANDOM_DELAY = True; MIN_DELAY_MS = 150; MAX_DELAY_MS = 600
    ADD_RANDOM_OFFSET = True; MAX_OFFSET_X = 4; MAX_OFFSET_Y = 4
    # -----------------------------------------------------

    next_action = None

    # --- Bước 1: Kiểm tra Input và Lấy Dữ liệu Cần Thiết ---
    if not graph_db or not db or not ai_service:
        logger.error("[Intelligent Planner] Missing required DB/AI modules.")
        return {"actionType": "wait", "duration": 60, "reason": "Planner internal error (missing modules)"}

    if not processed_ui_state or not isinstance(processed_ui_state.get('elements'), list):
        logger.warning(f"[Intelligent Planner] Invalid or missing elements in processed_ui_state for {current_screen_id}.")
        return {"actionType": "back", "reason": "No element data received"} # Fallback về back nếu không có element

    current_elements_from_state = processed_ui_state['elements']

    # Lấy phân loại đã lưu từ PostgreSQL
    saved_classifications = db.get_element_classifications_for_screen(current_screen_id)
    if saved_classifications is None:
        logger.error(f"[Intelligent Planner] Failed to fetch classifications for screen {current_screen_id}. Assuming all 'unclassified'.")
        saved_classifications = {} # Coi như rỗng nếu lỗi DB

    # Lấy các transition đã thử từ Neo4j
    outgoing_transitions = graph_db.get_outgoing_transitions(current_screen_id, app_name)
    if outgoing_transitions is None:
        logger.error(f"[Intelligent Planner] Failed to fetch outgoing transitions for screen {current_screen_id}. Assuming no actions tried.")
        outgoing_transitions = []

    # Tạo set các element_id đã được thử click/input từ màn hình này
    tried_element_ids = set()
    tried_back = False
    tried_swipe_up = False
    for trans_props in outgoing_transitions: # trans_props là dict thuộc tính của cạnh
        action_type = trans_props.get('actionType')
        # === ĐẢM BẢO LẤY ĐÚNG KEY 'element_id' ===
        el_id = trans_props.get('element_id') # Key này phải khớp với key đã lưu trong merge_transition
        # ========================================
        macro_code = trans_props.get('macro_code') # Lấy thêm macro_code nếu có

        # Kiểm tra cả actionType và macro_code để xác định hành động
        is_click_or_input = (action_type in ['click', 'input']) or \
                            (action_type == 'run_macro' and macro_code in ['UI_CLICK', 'UI_INPUT_TEXT'])

        if is_click_or_input and el_id:
            tried_element_ids.add(el_id)
        elif action_type == 'back' or macro_code == 'NAV_GO_BACK':
            tried_back = True
        elif action_type == 'swipe_up' or macro_code == 'UI_SWIPE_UP':
             tried_swipe_up = True
        # Thêm các loại action khác nếu cần

    logger.debug(f"[Intelligent Planner] Screen {current_screen_id}: Tried elements={tried_element_ids}, Tried Back={tried_back}, Tried SwipeUp={tried_swipe_up}")

    # --- Bước 2: Xử lý Tránh Lặp Ngay Lập Tức ---
    looping_element_id = None
    if previous_action and isinstance(previous_action, dict):
         source_context = previous_action.get('source_screen_context')
         action_details = previous_action.get('action_details')
         if source_context and action_details and source_context.get('screenId') == current_screen_id:
              # Hành động trước đó bắt nguồn từ chính màn hình này -> Loop!
              # Lấy ID của element gây loop
              looping_element_id = action_details.get('element_id') or action_details.get('onElementId')
              logger.warning(f"[Intelligent Planner] Detected immediate loop on screen {current_screen_id}. Action that caused loop targeted element: {looping_element_id}")

    # --- Bước 3: Lọc và Ưu tiên Element ---
    eligible_elements = []
    for el in current_elements_from_state:
        el_id = el.get('element_id')
        id_type = el.get('identifier_type')
        classification = saved_classifications.get(el_id, 'unclassified') # Lấy class đã lưu hoặc mặc định

        # Điều kiện lọc cơ bản:
        if (el_id and id_type in INTERACTABLE_TYPES and # Phải có ID ổn định
            classification not in NON_INTERACTIVE_CLASSES and # Không phải loại bỏ qua/không tương tác
            el_id != looping_element_id): # Không phải element vừa gây loop
            priority = CLASSIFICATION_PRIORITY.get(classification, DEFAULT_PRIORITY)
            has_been_tried = el_id in tried_element_ids
            eligible_elements.append({
                'data': el, # Giữ lại dict element gốc
                'priority': priority,
                'tried': has_been_tried
            })

    # Sắp xếp ưu tiên: Chưa thử lên trước, sau đó theo classification priority
    eligible_elements.sort(key=lambda x: (x['tried'], x['priority']))

    logger.debug(f"[Intelligent Planner] Found {len(eligible_elements)} eligible elements for interaction. Sorted by priority (untried first):")
    # for i, el_info in enumerate(eligible_elements[:5]): logger.debug(f"  {i+1}. ID: {el_info['data'].get('element_id')}, Tried: {el_info['tried']}, Prio: {el_info['priority']}, Class: {saved_classifications.get(el_info['data'].get('element_id'), 'unclassified')}")
    # if len(eligible_elements) > 5: logger.debug("  ...")

    # --- Bước 4: Chọn Hành động Tốt nhất ---
    selected_element_data = None
    action_type = None

    if eligible_elements:
        # Lấy element ưu tiên nhất
        selected_element_info = eligible_elements[0]
        selected_element_data = selected_element_info['data']
        el_id = selected_element_data['element_id']
        classification = saved_classifications.get(el_id, 'unclassified')

        # Quyết định loại hành động
        if classification == 'input_field':
            action_type = 'input'
        else:
            action_type = 'click' # Mặc định là click cho các loại khác

        logger.info(f"[Intelligent Planner] Selected action '{action_type}' on element ID '{el_id}' (Class: {classification}, Tried: {selected_element_info['tried']})")

    # --- Bước 5: Xây dựng nextAction JSON ---
    if action_type and selected_element_data:
        target_params = { # Bắt đầu xây dựng target cho params
            "element_id": selected_element_data['element_id'],
            "identifier_type": selected_element_data['identifier_type']
        }
        # Thêm các thông tin khác vào target nếu có
        if selected_element_data.get('text_content'): target_params['text'] = selected_element_data['text_content']
        if selected_element_data.get('element_type'): target_params['class_name'] = selected_element_data['element_type']
        if selected_element_data.get('coordinates'): target_params['coordinates'] = selected_element_data['coordinates']

        next_action = {
            "actionType": "run_macro",
            "params": {"target": target_params}
        }

        if action_type == 'click':
            next_action["macro_code"] = "UI_CLICK"
        elif action_type == 'input':
            next_action["macro_code"] = "UI_INPUT_TEXT"
            # TODO: Quyết định text cần nhập. Tạm thời dùng placeholder.
            # Cần logic dựa trên mapping_goal hoặc context khác.
            input_text = f"test_{random.randint(100,999)}"
            next_action["params"]["text_to_input"] = input_text
            logger.info(f"[Intelligent Planner] Input action, using placeholder text: '{input_text}'")

        # Thêm randomness
        if ADD_RANDOM_DELAY: next_action["random_delay_ms"] = { "min": MIN_DELAY_MS, "max": MAX_DELAY_MS }
        if ADD_RANDOM_OFFSET and target_params.get('coordinates'): next_action["random_offset_xy"] = { "x_max": MAX_OFFSET_X, "y_max": MAX_OFFSET_Y }

    # --- Bước 6: Xử lý Fallback ---
    else:
        logger.warning(f"[Intelligent Planner] No eligible elements found for interaction on screen {current_screen_id}.")
        # (Thêm logic kiểm tra swipe nếu cần)
        # if not tried_swipe_up:
        #     logger.info("[Intelligent Planner] Fallback: Trying swipe up.")
        #     next_action = {"actionType": "run_macro", "macro_code": "UI_SWIPE_UP", "params": {}, "reason": "No elements to interact, trying swipe"}
        #     if ADD_RANDOM_DELAY: next_action["random_delay_ms"] = { "min": int(MIN_DELAY_MS/2), "max": int(MAX_DELAY_MS/2) }

        if not tried_back:
            logger.info("[Intelligent Planner] Fallback: Trying NAV_GO_BACK.")
            next_action = {"actionType": "run_macro", "macro_code": "NAV_GO_BACK", "params": {}, "reason": "No elements or swipe options, trying back"}
        else:
            # Đã thử hết mọi cách
            logger.error(f"[Intelligent Planner] Fallback: STUCK on screen {current_screen_id}. All interactable elements and back action seem tried.")
            next_action = {"actionType": "wait", "duration": 60, "reason": "Stuck - explored all options"} # Hoặc "stuck"

    logger.debug(f"[Intelligent Planner] Final planned nextAction: {next_action}")
    return next_action

# --- Sửa lại hàm handle_explore_step để gọi planner mới ---

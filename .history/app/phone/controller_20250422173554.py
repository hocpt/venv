# -*- coding: utf-8 -*-
"""
hpt/app/phone/controller.py

Controller functions for phone interactions and strategy compilation.
"""

import json
from datetime import datetime, timezone
from flask import current_app, jsonify
import traceback # Giữ lại import traceback

# Import db từ app cha và ai_service nếu cần dùng sau này
from .. import database as db
from .. import ai_service # Import cả module ai_service

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

def process_phone_report(report_data: dict) -> tuple[bool, str | None]:
    """
    Xử lý báo cáo trạng thái và danh sách log từ client gửi lên qua API /report_status.
    Bao gồm việc nhận và xử lý trạng thái UI thô (nếu có) và lưu vào log CSDL.

    Args:
        report_data: Dictionary chứa dữ liệu từ JSON request body của client.
                     Mong đợi có các key: 'assignment_id', 'device_id', 'account_id',
                     'status_report' (dict), 'logs' (list), 'current_ui_state' (dict, optional).

    Returns:
        Tuple (bool, str | None): (True nếu xử lý thành công, thông báo) hoặc (False, thông báo lỗi).
    """
    logger = current_app.logger
    # Lấy các thông tin cơ bản từ report_data
    assignment_id = report_data.get('assignment_id')
    device_id = report_data.get('device_id')
    account_id = report_data.get('account_id')
    status_report = report_data.get('status_report')
    logs = report_data.get('logs') # List các dict log thô từ client
    raw_ui_state = report_data.get('current_ui_state') # <<< Lấy dữ liệu UI thô

    # Kiểm tra các thông tin bắt buộc
    if not assignment_id or not status_report or not device_id or not account_id:
        logger.warning("process_phone_report: Thiếu thông tin bắt buộc trong report_data.")
        return False, "Thiếu thông tin bắt buộc (assignment_id, status_report, device_id, account_id)."

    # Lấy thông tin từ status_report
    current_status = status_report.get('current_status', 'unknown')
    error_message = status_report.get('error_message')
    progress_data = status_report.get('progress')
    final_result_data = status_report.get('result')

    logger.info(f"Processing report for assignment {assignment_id}, device {device_id}, account {account_id}. Status: {current_status}")

    # === Xử lý Trạng thái UI thô (nếu client gửi lên) ===
    structured_ui_state_json = None # Chuỗi JSON chuẩn bị để lưu vào DB
    if raw_ui_state and isinstance(raw_ui_state, dict):
        logger.debug(f"Processing raw UI state received with report for assignment {assignment_id}")
        # Gọi hàm xử lý đã tạo trước đó để chuyển đổi mảng thô -> cấu trúc JSON chuẩn
        structured_state = process_raw_ui_state(raw_ui_state)
        if structured_state:
            try:
                # Chuyển dictionary Python thành chuỗi JSON để lưu vào CSDL
                structured_ui_state_json = json.dumps(structured_state, ensure_ascii=False)
            except Exception as json_err:
                 logger.error(f"Lỗi chuyển đổi structured UI state thành JSON cho assignment {assignment_id}: {json_err}")
                 structured_ui_state_json = json.dumps({"error": "Failed to serialize processed UI state on server"})
        else:
            logger.warning(f"Hàm process_raw_ui_state trả về None cho assignment {assignment_id}.")
    else:
        logger.debug(f"Không có current_ui_state trong báo cáo cho assignment {assignment_id}.")

    # === Ghi Logs Hành động vào CSDL ===
    log_success = True # Mặc định thành công nếu không có log
    if logs and isinstance(logs, list) and len(logs) > 0:
        logger.debug(f"Attempting to add {len(logs)} log entries for assignment {assignment_id}.")
        # <<< Truyền structured_ui_state_json vào hàm log >>>
        # Hàm log sẽ gắn state này vào TẤT CẢ các entry trong batch log này
        log_success = db.add_phone_action_logs(assignment_id, device_id, account_id, logs, structured_ui_state_json)
        if not log_success:
            logger.warning(f"Có lỗi khi ghi action logs cho assignment {assignment_id}.")
            # Tùy vào độ quan trọng, có thể return False ở đây
    else:
        logger.debug(f"Không có logs nào trong báo cáo cho assignment {assignment_id}.")

    # === Cập nhật Trạng thái và Tiến độ của Assignment ===
    update_data = {}
    now_utc = datetime.now(timezone.utc)
    update_data['last_report_at'] = now_utc

    current_assignment_status = db.get_task_assignment_status(assignment_id)
    if current_status == 'running' and current_assignment_status != 'running':
        update_data['started_at'] = now_utc
    elif current_status in ['completed', 'error', 'cancelled'] and current_assignment_status not in ['completed', 'error', 'cancelled']:
        update_data['completed_at'] = now_utc
        if final_result_data:
             update_data['result_data'] = final_result_data

    status_update_success = db.update_assignment_status(assignment_id, current_status, **update_data)
    if not status_update_success:
         return False, f"Không thể cập nhật trạng thái cho assignment {assignment_id}."

    progress_update_success = True
    if progress_data and isinstance(progress_data, dict):
        progress_update_success = db.update_assignment_progress(assignment_id, progress_data)
        if not progress_update_success:
             logger.warning(f"Có lỗi khi cập nhật tiến độ (target_data) cho assignment {assignment_id}.")

    # === Trả về Kết quả ===
    final_success = status_update_success and log_success
    final_msg = "Báo cáo đã được xử lý thành công." if final_success else "Báo cáo được xử lý với một số cảnh báo (kiểm tra log server)."

    return final_success, final_msg
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
    """
    Xử lý dữ liệu trạng thái UI thô (các mảng ids, texts, coords...) từ client
    và chuyển đổi thành định dạng JSON có cấu trúc (mảng các element objects).

    Args:
        ui_state_data: Dictionary chứa các keys như 'timestamp', 'package_name',
                       'ids' (list), 'texts' (list), 'coords' (list).

    Returns:
        Một dictionary đại diện cho trạng thái UI có cấu trúc,
        hoặc None nếu dữ liệu đầu vào không hợp lệ.
    """
    logger = current_app.logger if current_app else print # Lấy logger

    if not isinstance(ui_state_data, dict):
        logger.error("LỖI (process_raw_ui_state): Dữ liệu đầu vào không phải là dictionary.")
        return None

    # Trích xuất dữ liệu từ dict đầu vào (dùng .get() với giá trị mặc định là list rỗng)
    timestamp = ui_state_data.get('timestamp')
    package_name = ui_state_data.get('package_name')
    activity_name = ui_state_data.get('activity_name')
    ids = ui_state_data.get('ids', [])
    texts = ui_state_data.get('texts', [])
    coords = ui_state_data.get('coords', [])
    # Thêm các mảng khác nếu client gửi lên (vd: 'clickables', 'content_descs')
    # clickables = ui_state_data.get('clickables', [])
    # content_descs = ui_state_data.get('content_descs', [])

    # Kiểm tra kiểu dữ liệu của các mảng
    if not isinstance(ids, list) or not isinstance(texts, list) or not isinstance(coords, list):
         logger.error("LỖI (process_raw_ui_state): Dữ liệu ids, texts, hoặc coords không phải là list.")
         return None

    # Kiểm tra sự đồng nhất về độ dài các mảng (chúng nên bằng nhau)
    expected_len = len(ids)
    if len(texts) != expected_len or len(coords) != expected_len: # Thêm kiểm tra các mảng khác nếu có
        logger.warning(f"CẢNH BÁO (process_raw_ui_state): Độ dài các mảng không khớp - ids:{len(ids)}, texts:{len(texts)}, coords:{len(coords)}. Sẽ xử lý dựa trên độ dài ngắn nhất.")
        # Lấy độ dài nhỏ nhất để tránh lỗi Index out of bounds
        expected_len = min(len(ids), len(texts), len(coords)) # Thêm các len() khác nếu cần

    # Xây dựng danh sách các element có cấu trúc
    structured_elements = []
    for i in range(expected_len):
        element = {
            "index": i + 1, # Dùng index từ 1 cho dễ đọc? Hoặc i nếu muốn từ 0
            "resource_id": ids[i] if ids[i] is not None else None,
            "text": texts[i] if texts[i] is not None else None,
            "coordinates": _parse_coordinates(coords[i]) # Dùng hàm phụ trợ để parse tọa độ
            # Thêm các trường khác tương ứng với mảng lấy từ AutoInput
            # "clickable": clickables[i] if i < len(clickables) else None,
            # "content_description": content_descs[i] if i < len(content_descs) else None,
        }
        structured_elements.append(element)

    # Tạo đối tượng JSON cấu trúc hoàn chỉnh
    structured_state = {
        "timestamp": timestamp,
        "package_name": package_name,
        "activity_name": activity_name,
        "elements": structured_elements # Mảng các đối tượng element
    }

    logger.info(f"INFO (process_raw_ui_state): Đã xử lý thành công dữ liệu UI thô. Tìm thấy {len(structured_elements)} elements.")
    return structured_state



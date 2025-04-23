# app/phone/controller.py

import json
from datetime import datetime, timezone
from flask import current_app, jsonify
import traceback # Giữ lại import traceback

# Import db từ app cha và ai_service nếu cần dùng sau này
from .. import database as db
from .. import ai_service
# --- Logic biên dịch Gói Chiến lược ---

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
        # Điều này hữu ích nếu giá trị điều kiện là một cấu trúc JSON
        # Ví dụ: {"resource_id": "com.abc.id", "text": "Some Text"}
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

# --- Main Controller Functions ---

def compile_strategy_package(strategy_id: str, assignment_id: str = None, target_data: dict = None):
    """
    Biên dịch chiến lược thành một gói JSON để Client thực thi.

    Args:
        strategy_id: ID của chiến lược cần biên dịch.
        assignment_id: (Optional) ID của nhiệm vụ được giao (nếu có).
        target_data: (Optional) Dữ liệu mục tiêu cụ thể cho nhiệm vụ này (nếu có).

    Returns:
        dict: Gói JSON chiến lược hoặc None nếu có lỗi.
    """
    current_app.logger.info(f"Compiling strategy package for strategy_id: {strategy_id}, assignment_id: {assignment_id}")

    package_format_version = "1.2"  # Phiên bản cấu trúc gói, 1.2 hỗ trợ loop

    try:
        # 1. Lấy thông tin chi tiết chiến lược
        strategy_details = db.get_strategy_details(strategy_id)
        if not strategy_details:
            current_app.logger.error(f"Strategy not found: {strategy_id}")
            return None
        # Chỉ biên dịch chiến lược loại 'control'
        if strategy_details.get('strategy_type') != 'control':
            current_app.logger.error(f"Cannot compile non-control strategy: {strategy_id} (type: {strategy_details.get('strategy_type')})")
            return None

        # 2. Lấy danh sách các Stages và quy tắc nhận diện
        strategy_stages = db.get_stages_for_strategy(strategy_id)
        stages_recognition = {}
        step_counter = 1
        if strategy_stages:
            for stage in strategy_stages:
                stage_id = stage.get('stage_id')
                # Lấy dữ liệu identifying_elements (đã là dict/list/None)
                identifying_elements_data = stage.get('identifying_elements')
                stage_desc = stage.get('description')
                rules = [] # Mặc định là list rỗng

                # --- SỬA LOGIC Ở ĐÂY ---
                # Không cần json.loads() nữa
                if identifying_elements_data is not None:
                    try:
                        # Kiểm tra nếu là dict và có key 'rules' chứa list (Cấu trúc mong muốn)
                        if isinstance(identifying_elements_data, dict) and isinstance(identifying_elements_data.get('rules'), list):
                            rules = identifying_elements_data['rules']
                        # Kiểm tra nếu trực tiếp là list (Cấu trúc cũ?)
                        elif isinstance(identifying_elements_data, list):
                             rules = identifying_elements_data
                             current_app.logger.warning(f"Identifying_elements for stage {stage_id} is a direct list, expected dict with 'rules' key.")
                        # Trường hợp khác không mong muốn
                        else:
                            current_app.logger.warning(f"Unexpected format for identifying_elements in stage {stage_id}. Expected dict with 'rules' key or list. Found: {type(identifying_elements_data)}")
                    except Exception as e: # Bắt lỗi chung phòng trường hợp dữ liệu lạ
                        current_app.logger.error(f"Error processing identifying_elements data for stage {stage_id}: {e}")
                # --- KẾT THÚC SỬA LOGIC ---

                # Lưu trữ vào stages_recognition
                stages_recognition[stage_id] = {
                    "description": stage_desc,
                    "rules": rules # Lưu list các rules đã được xử lý
                }
        else:
            current_app.logger.warning(f"No stages found for strategy {strategy_id}.")
        # 3. Lấy chuỗi hành động (transitions) thô
        # Hàm này cần trả về list các dict, mỗi dict chứa đủ thông tin của transition
        # bao gồm cả loop_* và condition_*
        action_sequence_raw = db.get_strategy_action_sequence(strategy_id)
        if action_sequence_raw is None:
            current_app.logger.error(f"Failed to load transitions for strategy {strategy_id}")
            return None
    # --- THÊM LOG Ở ĐÂY ---
        current_app.logger.debug(f"Fetched {len(action_sequence_raw)} raw transitions from DB.")
        # 4. Biên dịch action_sequence
        compiled_sequence = []
        for transition in action_sequence_raw:
            transition_id = transition.get('id')
            current_app.logger.debug(f"Processing transition ID: {transition_id}...")
            current_stage_id = transition.get('current_stage_id')
            user_intent = transition.get('user_intent')
            next_stage_id = transition.get('next_stage_id')
            condition_type = transition.get('condition_type')
            condition_value = transition.get('condition_value')
            loop_type = transition.get('loop_type')
            loop_count = transition.get('loop_count')
            loop_condition_type = transition.get('loop_condition_type')
            loop_condition_value = transition.get('loop_condition_value')
            # Lấy dữ liệu action_to_suggest (đã là dict hoặc None)
            action_to_suggest_data = transition.get('action_to_suggest') # <<< Đổi tên biến và không gọi .str

            if not current_stage_id:
                current_app.logger.warning(f"Skipping transition ID {transition_id} due to missing current_stage_id.")
                continue

            # --- SỬA LOGIC Ở ĐÂY ---
            # Kiểm tra action_to_suggest_data trực tiếp, không cần json.loads()
            action_details = {} # Khởi tạo là dict rỗng
            if action_to_suggest_data is not None:
                if isinstance(action_to_suggest_data, dict):
                    action_details = action_to_suggest_data # Gán trực tiếp nếu là dict
                else:
                    # Ghi log lỗi nếu dữ liệu không phải dict hoặc None
                    current_app.logger.error(f"Skipping transition ID {transition_id}: Invalid type for action_to_suggest ({type(action_to_suggest_data)}).")
                    continue # Bỏ qua transition lỗi action
            # Nếu action_to_suggest_data là None, action_details sẽ là dict rỗng {}

            # Kiểm tra xem có macro_code không (chỉ kiểm tra nếu action_details không rỗng)
            # Việc kiểm tra chi tiết sẽ làm ở phần xác định step type sau
            # if not action_details.get('macro_code'):
            #     current_app.logger.warning(f"Transition ID {transition_id} has action_to_suggest but missing 'macro_code'.")
            #     # Có thể bỏ qua hoặc cho phép tùy logic, hiện tại vẫn xử lý tiếp
            # --- KẾT THÚC SỬA LOGIC ---


            # --- Xử lý logic biên dịch (Giữ nguyên phần này) ---
            transition_id_val = transition.get('id') # Hoặc transition.get('transition_id')
            step_id_to_use = transition_id_val if transition_id_val is not None else transition.get('priority', step_counter) # Dùng priority hoặc số đếm làm fallback

            step = {
                'step_id': step_id_to_use, # <<< Sử dụng giá trị đã kiểm tra
                'trigger': {'current_stage': current_stage_id, 'user_intent': user_intent},
                'next_stage_id': next_stage_id
            }

            # ƯU TIÊN KIỂM TRA LOOP TRƯỚC
            if loop_type:
                step['type'] = 'loop'
                step['loop_config'] = {'type': loop_type}
                step['sequence'] = [{ # Hành động nằm trong sequence của loop
                    'macro_code': action_details.get('macro_code'), # Lấy từ action_details đã xử lý
                    'params': action_details.get('params', {})
                }]
                # ... (Phần xử lý count, condition của loop giữ nguyên) ...
                if loop_type == 'repeat_n':
                    # ... (logic kiểm tra loop_count) ...
                    if loop_count is not None:
                        try: step['loop_config']['count'] = int(loop_count)
                        except (ValueError, TypeError): continue # Skip step lỗi
                        if step['loop_config']['count'] <= 0: continue # Skip step lỗi
                    else: continue # Skip step lỗi
                elif loop_type == 'while_condition_met':
                    # ... (logic kiểm tra loop_condition_type) ...
                     if loop_condition_type:
                         step['loop_config']['condition'] = {
                             'check': loop_condition_type,
                             'value': parse_condition_value(loop_condition_value)
                         }
                     else: continue # Skip step lỗi
                else: continue # Skip step lỗi

            # CHỈ KIỂM TRA CONDITIONAL NẾU KHÔNG PHẢI LÀ LOOP
            elif condition_type:
                step['type'] = 'conditional'
                step['condition'] = {
                    'check': condition_type,
                    'value': parse_condition_value(condition_value)
                }
                step['then_sequence'] = [{ # Hành động nằm trong then_sequence
                    'macro_code': action_details.get('macro_code'), # Lấy từ action_details đã xử lý
                    'params': action_details.get('params', {})
                }]
                step['else_sequence'] = []

            # Nếu không phải loop và không có condition -> là SIMPLE
            else:
                step['type'] = 'simple'
                step['macro_code'] = action_details.get('macro_code') # Lấy từ action_details đã xử lý
                step['params'] = action_details.get('params', {})

            # Kiểm tra xem bước có hợp lệ không (ví dụ: có macro_code)
            is_valid_step = True
            action_holder = None
            if step['type'] == 'simple': action_holder = step
            elif step['type'] == 'loop': action_holder = step['sequence'][0] if step.get('sequence') else None
            elif step['type'] == 'conditional': action_holder = step['then_sequence'][0] if step.get('then_sequence') else None

            # Bỏ qua bước nếu không có macro_code (trừ khi là loop/conditional trống?)
            # Có thể cần logic phức tạp hơn nếu cho phép loop/conditional không có action
            if not action_holder or not action_holder.get('macro_code'):
                 is_valid_step = False
                 current_app.logger.warning(f"Step invalid for transition ID {transition_id}: Missing macro_code. Type: {step.get('type')}, Holder: {action_holder}")

            if is_valid_step:
                compiled_sequence.append(step)
            else:
                current_app.logger.warning(f"Final check failed for transition ID {transition_id}. Step not appended.")
            step_counter += 1
        # 5. Lấy các cấu hình khác (ví dụ từ strategy_details hoặc bảng cấu hình riêng)
        execution_config = {
            "initial_stage_id": strategy_details.get('initial_stage_id'),
            "max_run_time_minutes": strategy_details.get('max_run_time_minutes', 120),
            "default_wait_ms": strategy_details.get('default_wait_ms', {"min": 800, "max": 1500}), # Có thể là JSON string trong DB
            "error_handling": strategy_details.get('error_handling', "report_and_stop")
        }
        # Parse default_wait_ms nếu nó là string
        if isinstance(execution_config["default_wait_ms"], str):
            try:
                execution_config["default_wait_ms"] = json.loads(execution_config["default_wait_ms"])
            except json.JSONDecodeError:
                 current_app.logger.warning(f"Failed to parse default_wait_ms JSON for strategy {strategy_id}. Using default.")
                 execution_config["default_wait_ms"] = {"min": 800, "max": 1500}

        # 6. Lấy context tài khoản (tạm thời để trống, sẽ lấy từ assignment sau)
        account_context = {
            # Sẽ được ghi đè/bổ sung bởi thông tin từ task_assignment nếu có
             "target_data": target_data or {}
        }


        # 7. Tạo gói JSON hoàn chỉnh
        strategy_package = {
            "metadata": {
                "package_format_version": package_format_version,
                "strategy_id": strategy_id,
                "strategy_name": strategy_details.get('name'),
                # Thêm version của chiến lược (vd: thời gian cập nhật cuối) để client cache
                "strategy_version": strategy_details.get('updated_at', datetime.now(timezone.utc)).isoformat(),
                "compiled_at": datetime.now(timezone.utc).isoformat(),
                "assignment_id": assignment_id # Thêm assignment_id vào metadata
            },
            "execution_config": execution_config,
            "account_context": account_context,
            "stages_recognition": stages_recognition,
            "action_sequence": compiled_sequence
        }

        current_app.logger.info(f"Successfully compiled strategy package for strategy_id: {strategy_id}")
        # current_app.logger.debug(f"Compiled package: {json.dumps(strategy_package, indent=2)}") # Ghi log chi tiết nếu cần debug
        return strategy_package

    except Exception as e:
        current_app.logger.error(f"Error compiling strategy package for {strategy_id}: {e}", exc_info=True)
        return None


def process_phone_report(device_id: str, account_id: str, assignment_id: str, report_payload: dict):
    """
    Xử lý báo cáo trạng thái từ điện thoại.

    Args:
        device_id: ID của thiết bị gửi báo cáo.
        account_id: ID của tài khoản đang chạy.
        assignment_id: ID của nhiệm vụ đang thực thi.
        report_payload: Dữ liệu báo cáo từ client (đã được parse thành dict).

    Returns:
        dict: Phản hồi cho client (ví dụ: xác nhận, yêu cầu dừng).
        int: HTTP status code.
    """
    current_app.logger.info(f"Processing report from device: {device_id}, account: {account_id}, assignment: {assignment_id}")
    # current_app.logger.debug(f"Report payload: {report_payload}") # Ghi log chi tiết nếu cần

    if not report_payload or not isinstance(report_payload, dict):
         current_app.logger.error("Invalid report payload received.")
         return {"status": "error", "message": "Invalid payload"}, 400

    status_report = report_payload.get('status_report', {})
    current_status = status_report.get('current_status') # 'running', 'completed', 'error'
    progress_data = status_report.get('progress') # Dữ liệu cập nhật tiến độ
    error_message = status_report.get('error_message')
    logs = status_report.get('logs', []) # Log chi tiết từ client

    response_action = None # Hành động yêu cầu client thực hiện (vd: 'stop_assignment')

    try:
        # 1. (Quan trọng) Xác thực assignment_id và cập nhật trạng thái
        assignment = db.get_task_assignment_details(assignment_id)
        if not assignment:
            current_app.logger.error(f"Assignment not found: {assignment_id}. Ignoring report.")
            # Không nên báo lỗi cho client vì có thể assignment đã bị xóa
            return {"status": "ignored", "message": "Assignment not found."}, 200
        # (Tùy chọn) Kiểm tra xem device_id, account_id có khớp với assignment không
        # if assignment.get('device_id') != device_id or assignment.get('account_id') != account_id:
        #     current_app.logger.error(f"Report mismatch for assignment {assignment_id}. Device/Account mismatch.")
        #     return {"status": "error", "message": "Assignment mismatch"}, 403

        # Cập nhật thời gian báo cáo cuối
        db.update_task_assignment_last_report(assignment_id)

        # Cập nhật tiến độ (target_data là JSON)
        if progress_data and isinstance(progress_data, dict):
            current_target_data = assignment.get('target_data', {})
            if isinstance(current_target_data, str): # Nếu target_data lưu là string JSON
                try:
                    current_target_data = json.loads(current_target_data)
                except json.JSONDecodeError:
                     current_app.logger.error(f"Failed to parse current target_data for assignment {assignment_id}")
                     current_target_data = {}

            # Logic cập nhật tiến độ cụ thể (ví dụ: cộng dồn)
            # Cần chuẩn hóa cách client gửi progress và cách server cập nhật
            # Ví dụ: Client gửi {'followers_gained': 5}, Server cộng vào current_target_data['current_count']
            if 'followers_gained' in progress_data and 'current_count' in current_target_data:
                 try:
                     current_target_data['current_count'] = int(current_target_data.get('current_count', 0)) + int(progress_data['followers_gained'])
                 except (ValueError, TypeError):
                     current_app.logger.warning(f"Invalid progress data types for assignment {assignment_id}")

            # Lưu lại target_data đã cập nhật
            db.update_task_assignment_target_data(assignment_id, current_target_data)


        # Lưu logs chi tiết vào phone_action_log
        if logs and isinstance(logs, list):
            db.add_phone_action_logs(assignment_id, device_id, account_id, logs)


        # Xử lý trạng thái cuối cùng từ client
        final_status = None
        if current_status == 'completed':
            final_status = 'completed'
            # (Tùy chọn) Lưu kết quả cuối cùng vào result_data
            # db.update_task_assignment_result_data(assignment_id, progress_data)
        elif current_status == 'error':
            final_status = 'error'
            # (Tùy chọn) Lưu thông tin lỗi vào result_data hoặc trường riêng
            # db.update_task_assignment_result_data(assignment_id, {'error': error_message})

        if final_status:
            db.update_task_assignment_status(assignment_id, final_status)
            current_app.logger.info(f"Assignment {assignment_id} final status updated to: {final_status}")

        # Kiểm tra xem assignment có bị hủy bởi admin không
        # (Cần lấy lại trạng thái mới nhất từ DB sau các cập nhật trên nếu cần)
        current_assignment_status_db = db.get_task_assignment_status(assignment_id) # Cần hàm này
        if current_assignment_status_db == 'cancelled':
             response_action = 'stop_assignment'
             current_app.logger.info(f"Instructing client to stop cancelled assignment: {assignment_id}")


        # Chuẩn bị phản hồi cho client
        response_body = {"status": "success", "message": "Report received."}
        if response_action:
            response_body["action_required"] = response_action

        return response_body, 200

    except Exception as e:
        current_app.logger.error(f"Error processing phone report for assignment {assignment_id}: {e}", exc_info=True)
        return {"status": "error", "message": "Internal server error processing report."}, 500
# --- Logic lấy phiên bản chiến lược ---

def process_phone_report(device_id: str, account_id: str, assignment_id: str, report_payload: dict):
    """
    Xử lý báo cáo trạng thái từ điện thoại.

    Args:
        device_id: ID của thiết bị gửi báo cáo.
        account_id: ID của tài khoản đang chạy.
        assignment_id: ID của nhiệm vụ đang thực thi.
        report_payload: Dữ liệu báo cáo từ client (đã được parse thành dict).

    Returns:
        dict: Phản hồi cho client (ví dụ: xác nhận, yêu cầu dừng).
        int: HTTP status code.
    """
    current_app.logger.info(f"Processing report from device: {device_id}, account: {account_id}, assignment: {assignment_id}")
    # current_app.logger.debug(f"Report payload: {report_payload}") # Ghi log chi tiết nếu cần

    if not report_payload or not isinstance(report_payload, dict):
         current_app.logger.error("Invalid report payload received.")
         return {"status": "error", "message": "Invalid payload"}, 400

    status_report = report_payload.get('status_report', {})
    current_status = status_report.get('current_status') # 'running', 'completed', 'error'
    progress_data = status_report.get('progress') # Dữ liệu cập nhật tiến độ
    error_message = status_report.get('error_message')
    logs = status_report.get('logs', []) # Log chi tiết từ client

    response_action = None # Hành động yêu cầu client thực hiện (vd: 'stop_assignment')

    try:
        # 1. (Quan trọng) Xác thực assignment_id và cập nhật trạng thái
        assignment = db.get_task_assignment_details(assignment_id)
        if not assignment:
            current_app.logger.error(f"Assignment not found: {assignment_id}. Ignoring report.")
            # Không nên báo lỗi cho client vì có thể assignment đã bị xóa
            return {"status": "ignored", "message": "Assignment not found."}, 200
        # (Tùy chọn) Kiểm tra xem device_id, account_id có khớp với assignment không
        # if assignment.get('device_id') != device_id or assignment.get('account_id') != account_id:
        #     current_app.logger.error(f"Report mismatch for assignment {assignment_id}. Device/Account mismatch.")
        #     return {"status": "error", "message": "Assignment mismatch"}, 403

        # Cập nhật thời gian báo cáo cuối
        db.update_task_assignment_last_report(assignment_id)

        # Cập nhật tiến độ (target_data là JSON)
        if progress_data and isinstance(progress_data, dict):
            current_target_data = assignment.get('target_data', {})
            if isinstance(current_target_data, str): # Nếu target_data lưu là string JSON
                try:
                    current_target_data = json.loads(current_target_data)
                except json.JSONDecodeError:
                     current_app.logger.error(f"Failed to parse current target_data for assignment {assignment_id}")
                     current_target_data = {}

            # Logic cập nhật tiến độ cụ thể (ví dụ: cộng dồn)
            # Cần chuẩn hóa cách client gửi progress và cách server cập nhật
            # Ví dụ: Client gửi {'followers_gained': 5}, Server cộng vào current_target_data['current_count']
            if 'followers_gained' in progress_data and 'current_count' in current_target_data:
                 try:
                     current_target_data['current_count'] = int(current_target_data.get('current_count', 0)) + int(progress_data['followers_gained'])
                 except (ValueError, TypeError):
                     current_app.logger.warning(f"Invalid progress data types for assignment {assignment_id}")

            # Lưu lại target_data đã cập nhật
            db.update_task_assignment_target_data(assignment_id, current_target_data)


        # Lưu logs chi tiết vào phone_action_log
        if logs and isinstance(logs, list):
            db.add_phone_action_logs(assignment_id, device_id, account_id, logs)


        # Xử lý trạng thái cuối cùng từ client
        final_status = None
        if current_status == 'completed':
            final_status = 'completed'
            # (Tùy chọn) Lưu kết quả cuối cùng vào result_data
            # db.update_task_assignment_result_data(assignment_id, progress_data)
        elif current_status == 'error':
            final_status = 'error'
            # (Tùy chọn) Lưu thông tin lỗi vào result_data hoặc trường riêng
            # db.update_task_assignment_result_data(assignment_id, {'error': error_message})

        if final_status:
            db.update_task_assignment_status(assignment_id, final_status)
            current_app.logger.info(f"Assignment {assignment_id} final status updated to: {final_status}")

        # Kiểm tra xem assignment có bị hủy bởi admin không
        # (Cần lấy lại trạng thái mới nhất từ DB sau các cập nhật trên nếu cần)
        current_assignment_status_db = db.get_task_assignment_status(assignment_id) # Cần hàm này
        if current_assignment_status_db == 'cancelled':
             response_action = 'stop_assignment'
             current_app.logger.info(f"Instructing client to stop cancelled assignment: {assignment_id}")


        # Chuẩn bị phản hồi cho client
        response_body = {"status": "success", "message": "Report received."}
        if response_action:
            response_body["action_required"] = response_action

        return response_body, 200

    except Exception as e:
        current_app.logger.error(f"Error processing phone report for assignment {assignment_id}: {e}", exc_info=True)
        return {"status": "error", "message": "Internal server error processing report."}, 500

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
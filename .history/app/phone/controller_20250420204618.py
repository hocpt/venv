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
        if strategy_details.get('strategy_type') != 'control':
            current_app.logger.error(f"Cannot compile non-control strategy: {strategy_id} (type: {strategy_details.get('strategy_type')})")
            return None

        # 2. Lấy danh sách các Stages và quy tắc nhận diện
        strategy_stages = db.get_stages_for_strategy(strategy_id)
        stages_recognition = {}
        if strategy_stages:
            for stage in strategy_stages:
                stage_id = stage.get('stage_id')
                identifying_elements_data = stage.get('identifying_elements')
                stage_desc = stage.get('description')
                rules = []
                if identifying_elements_data is not None:
                    try:
                        if isinstance(identifying_elements_data, dict) and isinstance(identifying_elements_data.get('rules'), list):
                            rules = identifying_elements_data['rules']
                        elif isinstance(identifying_elements_data, list):
                             rules = identifying_elements_data
                             current_app.logger.warning(f"Identifying_elements for stage {stage_id} is a direct list, expected dict with 'rules' key.")
                        else:
                            current_app.logger.warning(f"Unexpected format for identifying_elements in stage {stage_id}. Expected dict with 'rules' key or list. Found: {type(identifying_elements_data)}")
                    except Exception as e:
                        current_app.logger.error(f"Error processing identifying_elements data for stage {stage_id}: {e}")
                stages_recognition[stage_id] = {
                    "description": stage_desc,
                    "rules": rules
                }
        else:
            current_app.logger.warning(f"No stages found for strategy {strategy_id}")


        # 3. Lấy chuỗi hành động (transitions) thô
        action_sequence_raw = db.get_strategy_action_sequence(strategy_id)
        if action_sequence_raw is None:
             current_app.logger.error(f"Failed to load transitions for strategy {strategy_id}")
             return None
        current_app.logger.debug(f"Fetched {len(action_sequence_raw)} raw transitions from DB.")

        # 4. Biên dịch action_sequence
        compiled_sequence = []
        # Không cần step_counter nữa

        for transition in action_sequence_raw:
            # Lấy transition_id (khóa chính, phải có)
            transition_id = transition.get('transition_id') # Key phải là 'transition_id'

            # <<< Log và Kiểm tra transition_id ngay lập tức >>>
            current_app.logger.debug(f"Processing transition - Raw ID fetched: {transition_id} (Type: {type(transition_id)})")
            if transition_id is None:
                # Log lỗi nghiêm trọng nếu ID bị thiếu (không nên xảy ra với PK)
                current_app.logger.error(f"Critical Error: Transition data missing 'transition_id'. Skipping. Data: {transition}")
                continue # Bỏ qua transition này

            # <<< Nếu ID hợp lệ, tiếp tục xử lý >>>
            current_app.logger.debug(f"Transition ID {transition_id} is valid. Proceeding...")

            # Lấy các thông tin khác
            current_stage_id = transition.get('current_stage_id')
            user_intent = transition.get('user_intent')
            next_stage_id = transition.get('next_stage_id')
            condition_type = transition.get('condition_type')
            condition_value = transition.get('condition_value')
            loop_type = transition.get('loop_type')
            loop_count = transition.get('loop_count')
            loop_condition_type = transition.get('loop_condition_type')
            loop_condition_value = transition.get('loop_condition_value')
            action_to_suggest_data = transition.get('action_to_suggest') # Đã là dict/None

            if not current_stage_id:
                current_app.logger.warning(f"Skipping transition ID {transition_id}: Missing current_stage_id.")
                continue

            # Xử lý action_details từ action_to_suggest_data
            action_details = {}
            if action_to_suggest_data is not None:
                if isinstance(action_to_suggest_data, dict):
                    action_details = action_to_suggest_data
                else:
                    current_app.logger.error(f"Skipping transition ID {transition_id}: Invalid type for action_to_suggest ({type(action_to_suggest_data)}).")
                    continue

            # Tạo cấu trúc step cơ bản với transition_id làm step_id
            step = {
                'step_id': transition_id, # <<< Gán ID đã xác thực
                'trigger': {'current_stage': current_stage_id, 'user_intent': user_intent},
                'next_stage_id': next_stage_id
            }

            # Ưu tiên kiểm tra LOOP trước
            if loop_type:
                step['type'] = 'loop'
                step['loop_config'] = {'type': loop_type}
                step['sequence'] = [{
                    'macro_code': action_details.get('macro_code'),
                    'params': action_details.get('params', {})
                }]

                if loop_type == 'repeat_n':
                    if loop_count is not None:
                        try:
                            count_int = int(loop_count)
                            if count_int <= 0: raise ValueError("Loop count must be positive")
                            step['loop_config']['count'] = count_int
                        except (ValueError, TypeError):
                            current_app.logger.warning(f"Invalid loop_count '{loop_count}' for repeat_n loop in transition ID {transition_id}. Skipping step.")
                            continue
                    else:
                        current_app.logger.warning(f"Missing loop_count for repeat_n loop in transition ID {transition_id}. Skipping step.")
                        continue
                elif loop_type == 'while_condition_met':
                    if loop_condition_type:
                         step['loop_config']['condition'] = {
                             'check': loop_condition_type,
                             'value': parse_condition_value(loop_condition_value)
                         }
                    else:
                         current_app.logger.warning(f"While loop transition (ID: {transition_id}) missing loop condition type. Skipping step.")
                         continue
                else:
                     current_app.logger.warning(f"Unknown loop_type '{loop_type}' in transition ID {transition_id}. Skipping step.")
                     continue

            # Chỉ kiểm tra CONDITIONAL nếu KHÔNG phải là LOOP
            elif condition_type:
                step['type'] = 'conditional'
                step['condition'] = {
                    'check': condition_type,
                    'value': parse_condition_value(condition_value)
                }
                step['then_sequence'] = [{
                    'macro_code': action_details.get('macro_code'),
                    'params': action_details.get('params', {})
                }]
                step['else_sequence'] = []

            # Nếu không phải loop và không có condition -> là SIMPLE
            else:
                step['type'] = 'simple'
                step['macro_code'] = action_details.get('macro_code')
                step['params'] = action_details.get('params', {})

            # Kiểm tra cuối cùng xem bước có hợp lệ không (phải có macro_code)
            is_valid_step = True
            action_holder = None
            if step['type'] == 'simple': action_holder = step
            elif step['type'] == 'loop': action_holder = step['sequence'][0] if step.get('sequence') else None
            elif step['type'] == 'conditional': action_holder = step['then_sequence'][0] if step.get('then_sequence') else None

            if not action_holder or not action_holder.get('macro_code'):
                 is_valid_step = False
                 current_app.logger.warning(f"Step invalid for transition ID {transition_id}: Missing macro_code. Type: {step.get('type')}, Holder: {action_holder}")

            if is_valid_step:
                compiled_sequence.append(step)
                current_app.logger.debug(f"Appended step with step_id {transition_id} (Type: {step.get('type')})")
            else:
                 current_app.logger.warning(f"Final check failed for transition ID {transition_id}. Step not appended.")
            # Kết thúc vòng lặp for transition

        # 5. Lấy các cấu hình khác (execution_config)
        execution_config = {
            "initial_stage_id": strategy_details.get('initial_stage_id'),
            "max_run_time_minutes": strategy_details.get('max_run_time_minutes', 120),
            "default_wait_ms": {"min": 800, "max": 1500}, # Giá trị mặc định cứng
            "error_handling": strategy_details.get('error_handling', "report_and_stop")
        }
        # Parse default_wait_ms từ DB nếu có và là JSON string
        db_wait_ms = strategy_details.get('default_wait_ms')
        if isinstance(db_wait_ms, str):
            try:
                parsed_wait = json.loads(db_wait_ms)
                if isinstance(parsed_wait, dict) and 'min' in parsed_wait and 'max' in parsed_wait:
                    execution_config["default_wait_ms"] = parsed_wait
                else:
                     current_app.logger.warning(f"Parsed default_wait_ms for strategy {strategy_id} is not a valid min/max dict.")
            except json.JSONDecodeError:
                 current_app.logger.warning(f"Failed to parse default_wait_ms JSON for strategy {strategy_id}. Using default.")

        # 6. Lấy context tài khoản (kết hợp từ target_data nếu có)
        account_context = {
            "target_data": target_data or {}
        }


        # 7. Tạo gói JSON hoàn chỉnh
        latest_version = db.get_strategy_version(strategy_id) or datetime.now(timezone.utc).isoformat()

        strategy_package = {
            "metadata": {
                "package_format_version": package_format_version,
                "strategy_id": strategy_id,
                "strategy_name": strategy_details.get('name'),
                "strategy_version": latest_version,
                "compiled_at": datetime.now(timezone.utc).isoformat(),
                "assignment_id": assignment_id
            },
            "execution_config": execution_config,
            "account_context": account_context,
            "stages_recognition": stages_recognition,
            "action_sequence": compiled_sequence
        }

        current_app.logger.info(f"Successfully compiled strategy package for strategy_id: {strategy_id}. Sequence length: {len(compiled_sequence)}")
        return strategy_package

    except Exception as e:
        current_app.logger.error(f"Error compiling strategy package for {strategy_id}: {e}", exc_info=True)
        print(traceback.format_exc()) # In traceback ra console để dễ debug hơn
        return None

# --- Các hàm khác trong controller.py (giữ nguyên) ---
# Ví dụ: process_phone_report, get_latest_strategy_version, generate_comment_reply
# ... (Copy các hàm đó vào đây nếu chúng tồn tại trong file gốc của bạn) ...

# Đảm bảo bạn có các hàm này nếu chúng được gọi từ đâu đó (ví dụ: routes.py)
# Nếu không dùng thì có thể xóa đi

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
 
def process_phone_report(device_id: str, account_id: str, assignment_id: int, report_payload: dict) -> tuple[dict, int]:
    """
    Xử lý báo cáo trạng thái từ điện thoại, cập nhật assignment và log.

    Args:
        device_id: ID của thiết bị.
        account_id: ID của tài khoản.
        assignment_id: ID của nhiệm vụ đang thực thi.
        report_payload: Dữ liệu báo cáo gốc từ client.

    Returns:
        Tuple (dict, int): (Nội dung phản hồi JSON cho client, HTTP status code).
    """
    current_app.logger.info(f"Processing report for assignment: {assignment_id}, device: {device_id}, account: {account_id}")

    # --- Validate input cơ bản ---
    if not report_payload or not isinstance(report_payload, dict):
         current_app.logger.error(f"Invalid report payload received for assignment {assignment_id}.")
         return {"status": "error", "message": "Invalid payload"}, 400
    if not assignment_id: # Cần assignment_id để xử lý
        current_app.logger.error(f"Missing assignment_id in report processing call for device {device_id}.")
        return {"status": "error", "message": "Missing assignment ID."}, 400 # Lỗi từ server call

    status_report = report_payload.get('status_report', {})
    current_status_from_client = status_report.get('current_status') # 'running', 'completed', 'error'
    progress_data = status_report.get('progress') # Dữ liệu cập nhật tiến độ (vd: {'followers_gained': 5})
    error_message = status_report.get('error_message')
    logs = status_report.get('logs', []) # Log chi tiết từ client

    response_action = None # Hành động yêu cầu client thực hiện (vd: 'stop_assignment')
    response_body = {"status": "success", "message": "Report received."} # Phản hồi mặc định
    status_code = 200 # Mã HTTP mặc định

    try:
        # --- Cập nhật CSDL ---
        # 1. Cập nhật thời gian báo cáo cuối
        db.update_assignment_last_report(assignment_id)

        # 2. Cập nhật tiến độ nếu có
        if progress_data and isinstance(progress_data, dict):
            db.update_assignment_progress(assignment_id, progress_data)

        # 3. Ghi log hành động chi tiết
        if logs and isinstance(logs, list):
            db.add_phone_action_logs(assignment_id, device_id, account_id, logs)

        # 4. Xử lý trạng thái cuối cùng từ client (nếu có)
        final_status_to_set = None
        result_payload_to_set = None
        completion_time = None

        if current_status_from_client == 'completed':
            final_status_to_set = 'completed'
            result_payload_to_set = progress_data # Lưu progress cuối làm kết quả
            completion_time = datetime.now(timezone.utc)
        elif current_status_from_client == 'error':
            final_status_to_set = 'error'
            result_payload_to_set = {'error': error_message, 'last_progress': progress_data}
            completion_time = datetime.now(timezone.utc)

        # Gọi cập nhật status nếu là trạng thái cuối cùng
        if final_status_to_set:
            update_status_success = db.update_assignment_status(
                assignment_id=assignment_id,
                new_status=final_status_to_set,
                completed_at=completion_time,
                result_data=result_payload_to_set
            )
            if update_status_success:
                 current_app.logger.info(f"Assignment {assignment_id} marked as '{final_status_to_set}'.")
            else:
                 # Ghi log nếu không cập nhật được status cuối cùng
                 current_app.logger.error(f"Failed to update final status '{final_status_to_set}' for assignment {assignment_id}.")


        # --- Kiểm tra xem Assignment có bị Admin hủy không ---
        current_assignment_status_db = db.get_task_assignment_status(assignment_id)
        if current_assignment_status_db == 'cancelled':
             response_action = 'stop_assignment'
             current_app.logger.info(f"Instructing client to stop cancelled assignment: {assignment_id}")
             response_body["message"] = "Report received. Assignment cancelled by admin."

        if response_action:
            response_body["action_required"] = response_action

    except Exception as e:
        current_app.logger.error(f"Error processing phone report for assignment {assignment_id}: {e}", exc_info=True)
        print(traceback.format_exc())
        response_body = {"status": "error", "message": "Internal server error processing report."}
        status_code = 500

    return response_body, status_code   


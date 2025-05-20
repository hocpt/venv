# app/phone/routes.py
import json
import os
import uuid
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, current_app
from . import phone_bp # Import blueprint từ __init__.py cùng cấp
from . import controller as phone_controller # Import module chứa logic xử lý
from .. import database as db # Import module database từ thư mục app cha (..)
from app import csrf
from datetime import datetime, timezone
import traceback
from . import controller

try:
    from .. import database as db
    from . import controller as phone_controller
except ImportError:
    # Fallback import nếu cấu trúc khác
    import database as db
    import controller as phone_controller
    current_app.logger.warning("Using fallback imports for db and phone.controller in phone/routes.py")

#phone_bp = Blueprint('phone', __name__, url_prefix='/phone')
# === API Endpoints cho Điện thoại ===
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

def allowed_file(filename):
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@phone_bp.route('/get_comment_reply', methods=['POST'])
def get_comment_reply():
    """
    Endpoint để điện thoại yêu cầu nội dung trả lời cho một bình luận.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON data"}), 400

    account_id = data.get('account_id')
    comment_text = data.get('comment_text')
    context = data.get('context', {}) # Ngữ cảnh bổ sung (vd: ID bài viết, ID người bình luận...)

    print(f"INFO (Phone Route): Request for comment reply: account={account_id}, context={context}")

    if not account_id or not comment_text:
        return jsonify({"error": "Missing account_id or comment_text"}), 400

    try:
        # Gọi hàm controller để lấy/tạo nội dung trả lời
        reply_text = phone_controller.generate_comment_reply(
            account_id=account_id,
            comment_text=comment_text,
            context_json=context
        )

        if reply_text is not None:
            # Trả về nội dung trả lời
            # Có thể trả về kèm mã macro input nếu muốn
            # return jsonify({"reply_text": reply_text})
            return jsonify({
                "action": "run_macro",
                "macro_code": "MACRO_INPUT_TEXT_AND_SEND", # Ví dụ mã macro
                "params": {
                    "text_to_input": reply_text,
                    # Thêm các params khác nếu macro cần (vd: target element ID)
                    "target_element_name": "comment_input"
                }
            })
        else:
            # Không thể tạo trả lời (do lỗi hoặc không tìm thấy rule/template/AI không trả lời)
            return jsonify({"error": "Could not generate reply"}), 500 # Hoặc 404 tùy logic

    except Exception as e:
        print(f"ERROR (Phone Route - get_comment_reply): {e}")
        return jsonify({"error": "Internal server error while generating reply"}), 500

@phone_bp.route('/check_strategy_version', methods=['GET'])
def check_strategy_version():
    """
    (Tùy chọn) Endpoint để điện thoại kiểm tra phiên bản chiến lược hiện tại.
    """
    strategy_id = request.args.get('strategy_id')
    current_version = request.args.get('current_version') # Version điện thoại đang giữ

    if not strategy_id:
        return jsonify({"error": "Missing strategy_id parameter"}), 400

    try:
        latest_version = phone_controller.get_latest_strategy_version(strategy_id)

        if latest_version is not None:
            is_latest = (str(current_version) == str(latest_version)) if current_version is not None else False
            return jsonify({
                "is_latest": is_latest,
                "latest_version": latest_version
            })
        else:
            return jsonify({"error": f"Strategy '{strategy_id}' not found or version info unavailable"}), 404

    except Exception as e:
        print(f"ERROR (Phone Route - check_strategy_version): {e}")
        return jsonify({"error": "Internal server error checking strategy version"}), 500



# --- Route Đăng ký/Cập nhật Thiết bị MỚI ---
@phone_bp.route('/register_device', methods=['POST'])
def register_device():
    """
    Endpoint để client đăng ký hoặc cập nhật thông tin.
    Client gửi JSON payload chứa device_id, device_info, client_version, managed_accounts.
    """
    ip_address = request.remote_addr # Lấy IP để log nếu cần
    current_app.logger.info(f"Received request at /register_device from {ip_address}")
    data = request.get_json()

    if not data or not isinstance(data, dict):
        current_app.logger.error("Register Device: Invalid payload - Not a JSON object.")
        return jsonify({"status": "error", "message": "Invalid JSON payload."}), 400

    device_id = data.get('device_id')
    if not device_id:
        current_app.logger.error("Register Device: Invalid payload - Missing 'device_id'.")
        return jsonify({"status": "error", "message": "Missing 'device_id'."}), 400

    current_app.logger.info(f"Processing registration for device_id: {device_id}")
    try:
        # Gọi controller xử lý logic đăng ký
        success, error_msg = phone_controller.handle_device_registration(data)

        if success:
            current_app.logger.info(f"Device {device_id} registered/updated successfully.")
            return jsonify({"status": "success", "message": "Device registered/updated."}), 200
        else:
            current_app.logger.error(f"Device registration failed for {device_id}: {error_msg}")
            # Trả về lỗi 500 nếu lỗi từ DB/Controller, 400 nếu lỗi input logic
            status_code = 500 if "Database operation failed" in (error_msg or "") else 400
            return jsonify({"status": "error", "message": error_msg or "Registration failed."}), status_code
    except Exception as e:
        current_app.logger.error(f"Unexpected server error during device registration for {device_id}: {e}", exc_info=True)
        print(traceback.format_exc()) # In traceback ra console
        return jsonify({"status": "error", "message": "Internal server error."}), 500

# --- Route Lấy Chiến lược/Nhiệm vụ (ĐÃ CẬP NHẬT) ---
@phone_bp.route('/get_strategy', methods=['POST'])
def get_strategy():
    """
    Client gửi device_id và account_id để hỏi xem có nhiệm vụ (assignment) nào cần thực thi không.
    """
    ip_address = request.remote_addr
    current_app.logger.info(f"Received request at /get_strategy from {ip_address}")
    data = request.get_json()

    if not data or not isinstance(data, dict):
        current_app.logger.error("Get Strategy: Invalid payload.")
        return jsonify({"status": "error", "message": "Invalid JSON payload."}), 400

    device_id = data.get('device_id')
    account_id = data.get('account_id')

    if not device_id or not account_id:
        current_app.logger.error(f"Get Strategy: Missing device_id or account_id. Received: {data}")
        return jsonify({"status": "error", "message": "Missing 'device_id' or 'account_id'."}), 400

    current_app.logger.info(f"Get Strategy request from Device: {device_id}, Account: {account_id}")

    try:
        # 1. Tìm device_account_id tương ứng
        device_account_id = db.get_device_account_id(device_id, account_id)
        if not device_account_id:
            current_app.logger.warning(f"Device/Account link not found for Device: {device_id}, Account: {account_id}")
            return jsonify({"status": "error", "message": "Device or Account not registered/linked correctly."}), 404

        # 2. Tìm assignment đang chờ cho device_account_id này
        assignment = db.get_pending_assignment(device_account_id)

        # 3. Xử lý kết quả
        if assignment:
            assignment_id = assignment['assignment_id']
            strategy_id = assignment['strategy_id']
            # Target data có thể là dict hoặc None từ DB (JSONB NULL)
            target_data = assignment.get('target_data') # Đã là dict hoặc None

            current_app.logger.info(f"Found assignment {assignment_id} (Strategy: {strategy_id}) for Device: {device_id}, Account: {account_id}")

            # 3a. Cập nhật trạng thái assignment thành 'assigned'
            # Chỉ cập nhật thời gian assigned_at lần đầu
            update_status_success = db.update_assignment_status(
                assignment_id=assignment_id,
                new_status='assigned',
                assigned_at=datetime.now(timezone.utc) # Thêm thời gian được gán
                # Cân nhắc: Chỉ cập nhật assigned_at nếu status hiện tại là 'pending'
            )
            if not update_status_success:
                 current_app.logger.warning(f"Failed to update status to 'assigned' for assignment {assignment_id}. Proceeding anyway.")

            # 3b. Biên dịch gói chiến lược (truyền cả assignment_id và target_data)
            strategy_package = phone_controller.compile_strategy_package(
                strategy_id=strategy_id,
                assignment_id=assignment_id,
                target_data=target_data # Truyền dict hoặc None
            )

            # 3c. Trả về gói JSON nếu biên dịch thành công
            if strategy_package:
                current_app.logger.info(f"Returning compiled strategy package for assignment {assignment_id}.")
                return jsonify(strategy_package), 200
            else:
                # Lỗi biên dịch (đã được log trong controller)
                current_app.logger.error(f"Failed to compile strategy package for assignment {assignment_id}, strategy {strategy_id}.")
                # Cập nhật status assignment thành 'error'
                db.update_assignment_status(
                    assignment_id=assignment_id,
                    new_status='error',
                    completed_at=datetime.now(timezone.utc), # Coi như kết thúc lỗi
                    result_data={'error': 'Strategy compilation failed on server.'}
                )
                return jsonify({"status": "error", "message": "Failed to compile strategy package."}), 500
        else:
            # Không có nhiệm vụ mới
            current_app.logger.info(f"No pending assignment found for Device: {device_id}, Account: {account_id}")
            return jsonify({"status": "no_task", "retry_after_seconds": 300}), 200 # 200 OK nhưng không có task

    except Exception as e:
        current_app.logger.error(f"Error processing /get_strategy for device {device_id}, account {account_id}: {e}", exc_info=True)
        print(traceback.format_exc())
        return jsonify({"status": "error", "message": "Internal server error."}), 500

# --- Route Báo cáo Trạng thái (ĐÃ CẬP NHẬT) ---
@phone_bp.route('/report_status', methods=['POST'])
def report_status():
    """
    Client gửi báo cáo tiến độ, log, trạng thái UI, và context hành động trước đó.
    Server xử lý báo cáo, cập nhật CSDL PostgreSQL, và đưa job xây dựng bản đồ vào queue.
    API này sẽ trả về phản hồi ACK nhanh chóng.
    """
    ip_address = request.remote_addr
    # Sử dụng logger của Flask app
    logger = current_app.logger if current_app else print

    logger.info(f"Received request at /report_status from {ip_address}")
    data = request.get_json()

    # 1. Kiểm tra Payload cơ bản
    if not data or not isinstance(data, dict):
        logger.error("Report Status: Invalid payload - Not a JSON object.")
        return jsonify({"status": "error", "message": "Invalid JSON payload."}), 400

    # 2. Trích xuất Dữ liệu từ Payload
    device_id = data.get('device_id')
    account_id = data.get('account_id')
    assignment_id_str = data.get('assignment_id') # Có thể là None
    status_report_payload = data.get('status_report')
    logs_payload = data.get('logs', [])
    raw_ui_state = data.get('current_ui_state')
    previous_action_context = data.get('previous_action')
    
    # 3. Validate Dữ liệu Bắt buộc (Đã nới lỏng assignment_id)
    errors = []
    assignment_id = None # Khởi tạo là None

    if not device_id: errors.append("Missing 'device_id'.")
    if not account_id: errors.append("Missing 'account_id'.")
    # Chỉ parse assignment_id nếu nó được cung cấp và không rỗng
    if assignment_id_str is not None and str(assignment_id_str).strip(): # Kiểm tra cả None và chuỗi rỗng
        try:
            assignment_id = int(assignment_id_str)
        except (ValueError, TypeError):
            errors.append("Invalid 'assignment_id' format (must be an integer if provided).")

    if not status_report_payload or not isinstance(status_report_payload, dict):
        errors.append("Missing or invalid 'status_report' object.")

    if errors:
        msg = "Invalid report data: " + ", ".join(errors)
        logger.error(f"Report Status Validation Failed: {msg}. Payload: {data}")
        return jsonify({"status": "error", "message": msg}), 400

    current_app.logger.info(f"Processing status report for Assignment: {assignment_id}, Device: {device_id}, Account: {account_id}")

    # 4. Xử lý UI State và Đưa Job Map Building vào Queue (nếu có UI state)
    processed_ui_state_for_map = None
    ui_state_for_log_saving = None # Chuỗi JSON để lưu vào log PostgreSQL

    if raw_ui_state and isinstance(raw_ui_state, dict):
        logger.debug(f"Raw UI state received for assignment {assignment_id}.")
        try:
            # Gọi controller để xử lý UI thô thành cấu trúc chuẩn
            # Đảm bảo hàm phone_controller.process_raw_ui_state tồn tại và hoạt động đúng
            if phone_controller and hasattr(phone_controller, 'process_raw_ui_state'):
                processed_ui_state_for_map = phone_controller.process_raw_ui_state(raw_ui_state)
            else:
                logger.error("phone_controller or process_raw_ui_state function is not available!")
                processed_ui_state_for_map = None # Đặt là None nếu không xử lý được

            if processed_ui_state_for_map:
                logger.debug(f"UI state processed successfully for assignment {assignment_id}.")
                # Chuẩn bị chuỗi JSON để lưu vào log PostgreSQL
                try:
                    ui_state_for_log_saving = json.dumps(processed_ui_state_for_map, ensure_ascii=False)
                except Exception as json_err:
                     logger.error(f"Error serializing processed UI state to JSON for PG log (assignment {assignment_id}): {json_err}")
                     ui_state_for_log_saving = json.dumps({"error": "Failed to serialize UI state on server"})

                # --- Đưa job 'build_map' vào queue ---
                map_job_payload = {
                    'device_id': device_id,
                    'account_id': account_id,
                    'assignment_id': assignment_id, # Có thể là None
                    'processed_ui_state': processed_ui_state_for_map, # Truyền dict đã xử lý
                    'previous_action': previous_action_context # Truyền context (có thể None)
                }
                try:
                    # Đảm bảo module db và hàm add_scheduler_command tồn tại
                    if db and hasattr(db, 'add_scheduler_command'):
                        command_id = db.add_scheduler_command(command_type='build_map', payload=map_job_payload)
                        if command_id:
                            logger.info(f"Enqueued 'build_map' task (Command ID: {command_id}) for assignment {assignment_id}.")
                        else:
                            logger.error(f"Failed to enqueue 'build_map' task (db.add_scheduler_command returned None) for assignment {assignment_id}.")
                    else:
                         logger.error("DB module or add_scheduler_command function not available!")
                except Exception as queue_err:
                    logger.error(f"Exception enqueuing 'build_map' task for assignment {assignment_id}: {queue_err}", exc_info=True)
                # --- Kết thúc đưa job vào queue ---

            else:
                 logger.warning(f"process_raw_ui_state returned None for assignment {assignment_id}. Map update skipped for this state.")

        except Exception as ui_proc_err:
             logger.error(f"Error during call to process_raw_ui_state for assignment {assignment_id}: {ui_proc_err}", exc_info=True)
             # Không enqueue job map nếu xử lý UI lỗi

    else:
        logger.debug(f"No 'current_ui_state' provided in report for assignment {assignment_id}.")

    # 5. Xử lý Phần Còn lại của Báo cáo (Cập nhật status PG, ghi log PG...)
    # Phần này chạy song song với việc job 'build_map' đang nằm trong queue
    try:
        # **QUAN TRỌNG:** Cần đảm bảo hàm phone_controller.process_phone_report
        # và db.add_phone_action_logs đã được sửa để nhận và lưu ui_state_for_log_saving
        if phone_controller and hasattr(phone_controller, 'process_phone_report'):
            # Gọi hàm controller chính để xử lý status_report và logs_payload
            # Truyền ui_state_for_log_saving vào để controller có thể đưa vào hàm log DB
            _, status_code = phone_controller.process_phone_report( # Không cần lưu response_body ở đây nữa
             
                report_payload=data,         # Truyền payload gốc
                structured_ui_state_json=ui_state_for_log_saving # <<< Truyền chuỗi JSON
                
            )
            # Nếu hàm controller chạy thành công (không raise exception), trả về ACK đơn giản
            logger.info(f"Report processed (PG update, logging) for assignment {assignment_id}. Returning simple ACK.")
            return jsonify({"status": "success", "message": "Report received and queued for processing."}), 200 # <<< Phản hồi ACK
        else:
             logger.error("phone_controller or process_phone_report function is not available!")
             # Trả về lỗi server nếu controller không có sẵn
             return jsonify({"status": "error", "message": "Internal server error (controller unavailable)."}), 500

    except Exception as e:
        # Lỗi không mong muốn xảy ra trong controller hoặc DB calls (PostgreSQL)
        logger.error(f"Error calling process_phone_report for assignment {assignment_id}: {e}", exc_info=True)
        # traceback.print_exc() # In traceback nếu cần debug
        return jsonify({"status": "error", "message": "Internal server error processing report data."}), 500

# Ví dụ: Route lấy danh sách account cho device (dùng cho form Admin - dropdown động)
@phone_bp.route('/_internal/accounts_for_device', methods=['GET'], endpoint='get_accounts_for_device_json') # <<< Thêm endpoint='...'
def internal_get_accounts_for_device():
    """
    API nội bộ trả về danh sách account (dạng JSON) cho một device_id cụ thể.
    """
    device_id = request.args.get('device_id')
    if not device_id:
        return jsonify({"error": "Missing device_id parameter"}), 400

    accounts_list = [] # Khởi tạo list rỗng
    try:
        accounts_list = db.get_accounts_for_device_select(device_id)
        if accounts_list is None: # Phân biệt lỗi DB và không có account
             current_app.logger.error(f"DB Error getting accounts for device {device_id}")
             return jsonify({"error": "Database error fetching accounts"}), 500
        # Nếu device_id không tồn tại, hàm DB sẽ trả về list rỗng [] là đúng

    except Exception as e:
        current_app.logger.error(f"Unexpected error in internal_get_accounts_for_device for {device_id}: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

    # Trả về danh sách account (có thể rỗng)
    return jsonify(accounts_list)

@phone_bp.route('/ping', methods=['GET'])
def phone_ping():
    return jsonify({"status": "pong from phone blueprint"})

@phone_bp.route('/process_ui_state', methods=['POST'])
def process_ui_state_route():
    """
    Endpoint để client gửi dữ liệu UI thô (dạng các mảng) lên
    cho server xử lý thành JSON có cấu trúc.
    Chủ yếu dùng để test và debug logic xử lý UI.
    """
    # Lấy dữ liệu JSON từ body của request
    data = request.get_json()
    if not data:
        current_app.logger.warning("API /process_ui_state: Request body không phải JSON hoặc rỗng.")
        return jsonify({"status": "error", "message": "Request body phải là JSON hợp lệ."}), 400

    # Lấy các thông tin cần thiết
    device_id = data.get('device_id')
    account_id = data.get('account_id')
    ui_state_data = data.get('ui_state') # Mong đợi dữ liệu thô nằm trong key 'ui_state'

    # Kiểm tra dữ liệu đầu vào
    if not device_id or not account_id:
         current_app.logger.warning(f"API /process_ui_state: Thiếu device_id hoặc account_id.")
         return jsonify({"status": "error", "message": "Thiếu device_id hoặc account_id."}), 400
    if not ui_state_data or not isinstance(ui_state_data, dict):
         current_app.logger.warning(f"API /process_ui_state: Thiếu hoặc không hợp lệ key 'ui_state' trong request.")
         return jsonify({"status": "error", "message": "Thiếu hoặc không hợp lệ trường 'ui_state' trong request body."}), 400

    current_app.logger.info(f"INFO: Nhận dữ liệu UI thô từ device={device_id}, account={account_id}")
    current_app.logger.debug(f"DEBUG: Dữ liệu ui_state thô: {ui_state_data}") # Log dữ liệu thô để kiểm tra

    # Gọi hàm controller để xử lý
    structured_state = phone_controller.process_raw_ui_state(ui_state_data)

    if structured_state:
        # Nếu xử lý thành công, trả về JSON có cấu trúc
        # Tùy chọn: Bạn có thể lưu structured_state này vào CSDL nếu muốn log lại trạng thái đã xử lý
        # db.log_phone_action(..., received_state_json=structured_state) # Ví dụ
        return jsonify({
            "status": "success",
            "message": "Đã xử lý dữ liệu UI thành công.",
            "processed_state": structured_state # Trả về kết quả đã xử lý
        }), 200
    else:
        # Nếu xử lý thất bại (lỗi đã được log trong controller)
        return jsonify({
            "status": "error",
            "message": "Không thể xử lý dữ liệu UI trên server."
        }), 500 

# === API MỚI ĐỂ CLIENT LẤY MAIN LOOP STRATEGY ===
@phone_bp.route('/get_mainloop_strategy', methods=['POST'])
def get_mainloop_strategy_route():
    """
    Endpoint cho client yêu cầu gói JSON của Main Loop Strategy được gán cho nó.
    Yêu cầu: POST JSON {"device_id": "..."}
    Trả về: Gói JSON Main Loop Strategy hoặc thông báo lỗi/không có chiến lược.
    """
    logger = current_app.logger if current_app else print
    if not request.is_json:
        logger.warning("Request to /get_mainloop_strategy is not JSON")
        return jsonify({"status": "error", "message": "Request must be JSON."}), 400

    data = request.get_json()
    device_id = data.get('device_id')

    if not device_id:
        logger.warning("Request to /get_mainloop_strategy missing 'device_id'")
        return jsonify({"status": "error", "message": "Missing 'device_id' in request."}), 400

    logger.info(f"Device '{device_id}' requesting mainloop strategy.")

    if not phone_controller:
         logger.error("Phone controller is not available!")
         return jsonify({"status": "error", "message": "Server internal error (controller)."}), 500

    # Gọi hàm xử lý trong controller
    try:
        response_data = phone_controller.handle_get_mainloop_strategy(device_id)
        # Hàm controller sẽ trả về dict chứa package hoặc dict báo lỗi/status
        if isinstance(response_data, dict):
            status_code = 200
            # Kiểm tra nếu controller trả về lỗi cụ thể
            if response_data.get("status") == "error":
                 status_code = 500 # Lỗi server
            elif response_data.get("status") == "no_mainloop_strategy":
                 status_code = 200 # Vẫn là 200 OK nhưng báo không có strategy
            elif response_data.get("status") == "device_not_found":
                 status_code = 404 # Device không tồn tại
            return jsonify(response_data), status_code
        else:
             # Trường hợp controller trả về không đúng định dạng
             logger.error(f"Controller handle_get_mainloop_strategy returned unexpected type for device {device_id}")
             return jsonify({"status": "error", "message": "Server internal error (controller response)."}), 500

    except Exception as e:
        logger.error(f"Exception in get_mainloop_strategy_route for device {device_id}: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"Server internal error: {e}"}), 500

# === API MỚI: CLIENT YÊU CẦU HÀNH ĐỘNG KHÁM PHÁ TIẾP THEO ===
@phone_bp.route('/get_next_exploration_action', methods=['POST'])
@csrf.exempt
def get_next_exploration_action():
    """
    Client gửi screenId hiện tại (hoặc null/unknown), server xác định màn hình
    và quyết định hành động tiếp theo để khám phá.
    """
    logger = current_app.logger if current_app else print
    # --- 1. Nhận và Validate Input Cơ bản ---
    data = request.get_json()

    if not data or not isinstance(data, dict):
        logger.error("Get Next Action: Invalid payload - Not a JSON object.")
        return jsonify({"status": "error", "message": "Invalid JSON payload."}), 400

    device_id = data.get('device_id')
    account_id = data.get('account_id')
    # Client có thể gửi null, chuỗi rỗng, hoặc "unknown" nếu không biết ID màn hình hiện tại
    current_screen_id_from_client = data.get('current_screen_id')

    errors = []
    if not device_id: errors.append("Missing 'device_id'.")
    if not account_id: errors.append("Missing 'account_id'.")
    # Không báo lỗi nếu current_screen_id_from_client bị thiếu hoặc null nữa

    if errors:
        msg = "Get Next Action: Missing required parameters: " + ", ".join(errors)
        logger.error(f"{msg} Received: {data}")
        return jsonify({"status": "error", "message": msg}), 400

    logger.info(f"Get Next Action request from Device: {device_id}, Account: {account_id}, Client Screen ID: '{current_screen_id_from_client}'")

    # --- 2. Xác định Screen ID thực tế (Confirmed Screen ID) ---
    confirmed_current_screen_id = None
    last_ui_state_dict = None # Biến lưu state cuối cùng nếu cần tra cứu

    try:
        # Ưu tiên ID client gửi nếu nó có vẻ hợp lệ (không null, không rỗng, không phải "unknown")
        if current_screen_id_from_client and isinstance(current_screen_id_from_client, str) and current_screen_id_from_client.lower() != 'unknown':
            confirmed_current_screen_id = current_screen_id_from_client
            logger.debug(f"Initially trusting client screen ID: {confirmed_current_screen_id}")
            # TODO (Future): Thêm logic kiểm tra xem ID này có thực sự tồn tại trong Neo4j không nếu muốn chắc chắn hơn.
        else:
            logger.warning(f"Client screen ID '{current_screen_id_from_client}' is unreliable. Attempting to determine from last report.")
            # --- Logic tra cứu state cuối cùng ---
            if db and hasattr(db, 'get_last_reported_ui_state'):
                # <<< GỌI HÀM DB MỚI >>>
                last_ui_state_dict = db.get_last_reported_ui_state(device_id, account_id)

                if last_ui_state_dict and isinstance(last_ui_state_dict, dict):
                    logger.debug("Found last reported UI state from DB.")
                    # <<< GỌI HÀM CONTROLLER MỚI >>>
                    if phone_controller and hasattr(phone_controller, 'determine_screen_id_from_state'):
                        # Tính toán screenId từ state lấy được
                        confirmed_current_screen_id = phone_controller.determine_screen_id_from_state(last_ui_state_dict)
                        if confirmed_current_screen_id:
                            logger.info(f"Determined screen ID from last report: {confirmed_current_screen_id}")
                        else:
                            logger.error(f"Failed to determine screen ID from last reported state for device {device_id}, account {account_id}.")
                    else:
                        logger.error("Server Error: 'determine_screen_id_from_state' function is missing in controller.")
                else:
                    logger.warning(f"Could not find last reported UI state in DB for device {device_id}, account {account_id}.")
            else:
                logger.error("Server Error: Database module or 'get_last_reported_ui_state' function is missing.")

            # Nếu vẫn không xác định được ID sau khi tra cứu
            if not confirmed_current_screen_id:
                return jsonify({
                    "status": "error",
                    "message": "Cannot determine current screen. Please ensure the client reported its UI state recently."
                }), 404 # Hoặc 400 tùy logic

    except Exception as screen_id_err:
        logger.error(f"Error determining confirmed screen ID: {screen_id_err}", exc_info=True)
        return jsonify({"status": "error", "message": "Internal server error determining screen ID."}), 500

    # --- 3. Logic Chính (Gọi Planner) ---
    next_action = None
    error_message = None

    try:
        # Lấy app_name (vẫn cần)
        app_name = None
        if db and hasattr(db, 'get_app_name_from_account'):
            app_name = db.get_app_name_from_account(account_id)
        elif last_ui_state_dict: # Thử lấy từ state đã tra cứu nếu có
             app_name = last_ui_state_dict.get('package_name')
             logger.info(f"Got app_name '{app_name}' from last reported state.")
        else: # Nếu không có state và không có hàm db
             app_name = data.get('app_name') # Thử lấy từ request gốc
             logger.warning("Could not get app_name from DB or last state, trying from request.")

        if not app_name:
            logger.error("Get Next Action: Cannot determine app_name.")
            return jsonify({"status": "error", "message": "Cannot determine app_name."}), 500

        # Kiểm tra controller và planner function
        if not phone_controller or not hasattr(phone_controller, 'plan_simple_exploration_action'):
            error_message = "Server Error: Planning function is unavailable."
            logger.critical(error_message)
            return jsonify({"status": "error", "message": error_message}), 500

        # Gọi hàm planner với confirmed_current_screen_id
        logger.debug(f"Calling planner for app '{app_name}', confirmed screen '{confirmed_current_screen_id}'")
        next_action = phone_controller.plan_simple_exploration_action(
            app_name=app_name,
            current_screen_id=confirmed_current_screen_id # <<< Sử dụng ID đã xác nhận
        )

    except Exception as e:
        logger.error(f"Error calling planner for screen {confirmed_current_screen_id}: {e}", exc_info=True)
        print(traceback.format_exc())
        return jsonify({"status": "error", "message": f"Internal server error during planning: {e}"}), 500

    # --- 4. Xử lý Kết quả và Trả về Response ---
    if next_action and isinstance(next_action, dict): # <<< Kiểm tra next_action là dict
        action_type_log = next_action.get('actionType', 'unknown')
        logger.info(f"Planned next action for screen {confirmed_current_screen_id}: {action_type_log}")
        response_data = {
            "status": "success",
            "confirmedCurrentScreenId": confirmed_current_screen_id, # <<< Luôn trả về ID đã dùng
            "nextAction": next_action,
            "message": f"Next action '{action_type_log}' planned."
        }
        return jsonify(response_data), 200
    else:
        # Planner trả về None hoặc không phải dict
        logger.warning(f"No valid next exploration action planned from screen {confirmed_current_screen_id}.")
        response_data = {
            "status": "no_action",
            "confirmedCurrentScreenId": confirmed_current_screen_id, # <<< Vẫn trả về ID đã dùng
            "nextAction": None,
            "message": "No further actions planned from this screen currently, or planner returned invalid data."
        }
        return jsonify(response_data), 200


@phone_bp.route('/explore_step', methods=['POST'])
# @require_api_key # Thêm xác thực nếu API này cần bảo vệ
def explore_step_api():
    """
    API Endpoint để client báo cáo trạng thái UI hiện tại và nhận hành động tiếp theo.
    """
    logger = current_app.logger
    if not request.is_json:
        logger.warning("Explore step request is not JSON.")
        return jsonify({"status": "error", "message": "Request must be JSON"}), 400

    data = request.get_json()
    logger.debug(f"[explore_step_api] Received explore_step data: {data}") # Log toàn bộ data

    device_id = data.get('device_id')
    account_id = data.get('account_id')
    raw_ui_state = data.get('raw_ui_state')
    if raw_ui_state is None:
        raw_ui_state = data.get('current_ui_state')
        if raw_ui_state:
            logger.info("[explore_step_api] Using 'current_ui_state' as raw_ui_state was not provided.")

    previous_action = data.get('previous_action')
    screenshot_filename = data.get('screenshot_filename') # Lấy từ client

    # === LOGGING CHI TIẾT CHO screenshot_filename ===
    logger.info(f"[explore_step_api] Value of 'screenshot_filename' from request data: '{screenshot_filename}' (Type: {type(screenshot_filename)})")
    if screenshot_filename == "":
        logger.warning("[explore_step_api] 'screenshot_filename' from request data is an EMPTY STRING.")
    elif screenshot_filename is None:
        logger.info("[explore_step_api] 'screenshot_filename' key was not found or was null in request data.")
    # ===============================================

    if not device_id or not raw_ui_state:
        missing_params = []
        if not device_id: missing_params.append('device_id')
        if not raw_ui_state: missing_params.append('raw_ui_state (or current_ui_state)')
        logger.warning(f"Explore step request missing required parameters: {', '.join(missing_params)}")
        return jsonify({"status": "error", "message": f"Missing required parameters: {', '.join(missing_params)}"}), 400

    try:
        response_data, status_code = controller.handle_explore_step(
            device_id=device_id,
            account_id=account_id,
            current_screen_id_from_client=None,
            raw_ui_state=raw_ui_state,
            previous_action=previous_action,
            screenshot_filename=screenshot_filename # Truyền giá trị đã lấy
        )
        return jsonify(response_data), status_code
    except Exception as e:
        logger.error(f"Error processing explore_step for device {device_id}: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Internal server error during explore step processing"}), 500


@phone_bp.route('/explore_step', methods=['POST'])
@csrf.exempt # <<< Thêm decorator này nếu API này cũng cần bỏ CSRF >>>
def handle_explore_step_route():
    # ... (code xử lý request và gọi controller.handle_explore_step) ...
    # Ví dụ:
    data = request.get_json()
    if not data: return jsonify({"error": "Missing JSON data"}), 400
    # Trích xuất các tham số cần thiết từ data...
    device_id = data.get('device_id')
    account_id = data.get('account_id')
    raw_ui_state = data.get('ui_state')
    previous_action = data.get('previous_action') # Context của action trước đó
    current_screen_id_client = data.get('current_screen_id') # ID client gửi lên (có thể không dùng)

    # Validate các tham số tối thiểu
    if not device_id or not account_id or not raw_ui_state:
         return jsonify({"error": "Missing device_id, account_id, or ui_state"}), 400

    # Gọi hàm xử lý logic trong controller
    response_body, status_code = controller.handle_explore_step(
        device_id=device_id,
        account_id=account_id,
        current_screen_id_from_client=current_screen_id_client,
        raw_ui_state=raw_ui_state,
        previous_action=previous_action
    )
    return jsonify(response_body), status_code

@phone_bp.route('/api/upload/screenshot', methods=['POST'])
def upload_screenshot_from_client(): # Đây là hàm bạn đang gặp lỗi
    logger = current_app.logger
    logger.info("PHONE_UPLOAD_API: Received new screenshot upload request.")
    
    logger.debug(f"PHONE_UPLOAD_API: Request Headers: {request.headers}")
    logger.debug(f"PHONE_UPLOAD_API: Request Form Data (request.form): {request.form.to_dict()}")
    logger.debug(f"PHONE_UPLOAD_API: Request Files Keys (request.files.keys()): {list(request.files.keys())}")

    # Dựa trên log "Request Files Keys: ['screenshot_file']"
    expected_file_field_name = 'screenshot_file' 

    if expected_file_field_name not in request.files:
        logger.warning(f"PHONE_UPLOAD_API: No '{expected_file_field_name}' part in request.files. Available keys: {list(request.files.keys())}")
        return jsonify({"success": False, "error": f"Không tìm thấy phần file với tên '{expected_file_field_name}' trong request."}), 400
    
    uploaded_file_storage = request.files[expected_file_field_name]
    
    # Server PHẢI nhận được 'filename' và 'app_name' từ request.form
    # Client (script curl hoặc MacroDroid) CẦN GỬI CÁC TRƯỜNG NÀY
    filename_for_server_storage = request.form.get('filename') 
    app_name_for_directory = request.form.get('app_name')

    logger.debug(f"PHONE_UPLOAD_API: Form data received - filename from form: '{filename_for_server_storage}', app_name from form: '{app_name_for_directory}'")
    logger.debug(f"PHONE_UPLOAD_API: Uploaded file object - original name on client's disk: '{uploaded_file_storage.filename}'")

    if not filename_for_server_storage:
        logger.warning("PHONE_UPLOAD_API: Missing 'filename' form parameter. This is required for server storage and matching with Neo4j.")
        return jsonify({"success": False, "error": "Thiếu tham số 'filename' trong dữ liệu form (cần để đặt tên file trên server)."}), 400
    
    if not app_name_for_directory:
        logger.warning("PHONE_UPLOAD_API: Missing 'app_name' form parameter. This is required for directory structure.")
        return jsonify({"success": False, "error": "Thiếu tham số 'app_name' trong dữ liệu form (cần để tạo thư mục)."}), 400
    
    # Kiểm tra xem có file nào được chọn thực sự không
    # uploaded_file_storage.filename là tên file gốc client gửi lên (ví dụ: screenshot.png)
    # Chúng ta sẽ dùng filename_for_server_storage để lưu file.
    if uploaded_file_storage.filename == '':
        logger.warning("PHONE_UPLOAD_API: No file selected by client (uploaded_file_storage.filename is empty).")
        return jsonify({"success": False, "error": "Không có file nào được chọn để upload."}), 400

    # An toàn hóa tên file (dựa trên filename_for_server_storage) và tên thư mục app_name
    final_safe_filename = secure_filename(os.path.basename(filename_for_server_storage))
    safe_app_name_folder = secure_filename(app_name_for_directory)

    if not final_safe_filename or not safe_app_name_folder:
        logger.error(f"PHONE_UPLOAD_API: Invalid filename or app_name after sanitization. Original form filename: '{filename_for_server_storage}', app_name: '{app_name_for_directory}'")
        return jsonify({"success": False, "error": "Tên file hoặc app_name không hợp lệ sau khi xử lý."}), 400

    storage_base_path = current_app.config.get('SCREENSHOT_STORAGE_PATH')
    if not storage_base_path:
        logger.critical("PHONE_UPLOAD_API: SCREENSHOT_STORAGE_PATH is NOT CONFIGURED!")
        return jsonify({"success": False, "error": "Lỗi cấu hình server (storage path missing)."}), 500
    
    logger.info(f"PHONE_UPLOAD_API: Configured SCREENSHOT_STORAGE_PATH: '{storage_base_path}'")

    app_specific_storage_directory = os.path.join(storage_base_path, safe_app_name_folder)
    logger.info(f"PHONE_UPLOAD_API: Target app-specific directory: '{app_specific_storage_directory}'")
    
    try:
        if not os.path.exists(app_specific_storage_directory):
            os.makedirs(app_specific_storage_directory, exist_ok=True)
            logger.info(f"PHONE_UPLOAD_API: Created directory: {app_specific_storage_directory}")
    except OSError as e:
        logger.error(f"PHONE_UPLOAD_API: Could not create directory '{app_specific_storage_directory}': {e}", exc_info=True)
        return jsonify({"success": False, "error": "Server error creating storage directory."}), 500
    
    full_path_to_save_file = os.path.join(app_specific_storage_directory, final_safe_filename)
    logger.info(f"PHONE_UPLOAD_API: Attempting to save uploaded file to: '{full_path_to_save_file}'")
    
    try:
        uploaded_file_storage.save(full_path_to_save_file)
        if os.path.exists(full_path_to_save_file) and os.path.getsize(full_path_to_save_file) > 0:
            logger.info(f"PHONE_UPLOAD_API: SUCCESS - Image saved to: {full_path_to_save_file}")
            return jsonify({
                "success": True, 
                "message": "Screenshot uploaded successfully.", 
            }), 201
        else:
            logger.error(f"PHONE_UPLOAD_API: FAILED - File not found or empty after save attempt at: {full_path_to_save_file}")
            return jsonify({"success": False, "error": "Server error: Could not confirm file save or file is empty."}), 500
    except Exception as e:
        logger.error(f"PHONE_UPLOAD_API: EXCEPTION during save of file '{final_safe_filename}' to '{app_specific_storage_directory}': {e}", exc_info=True)
        if os.path.exists(full_path_to_save_file):
            try: os.remove(full_path_to_save_file) 
            except: pass
        return jsonify({"success": False, "error": "Server error while saving image file."}), 500

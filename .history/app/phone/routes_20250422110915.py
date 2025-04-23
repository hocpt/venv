# app/phone/routes.py
from flask import Blueprint, request, jsonify, current_app
from . import phone_bp # Import blueprint từ __init__.py cùng cấp
from . import controller as phone_controller # Import module chứa logic xử lý
from .. import database as db # Import module database từ thư mục app cha (..)

from datetime import datetime, timezone
import traceback
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
    Client gửi báo cáo tiến độ, log, và trạng thái cuối cùng (nếu có) cho một assignment cụ thể.
    """
    ip_address = request.remote_addr
    current_app.logger.info(f"Received request at /report_status from {ip_address}")
    data = request.get_json()

    if not data or not isinstance(data, dict):
        current_app.logger.error("Report Status: Invalid payload.")
        return jsonify({"status": "error", "message": "Invalid JSON payload."}), 400

    # --- Extract và Validate dữ liệu cần thiết ---
    device_id = data.get('device_id')
    account_id = data.get('account_id')
    assignment_id_str = data.get('assignment_id') # Lấy dạng chuỗi trước
    status_report_payload = data.get('status_report') # Phần chứa log, progress, status...

    errors = []
    assignment_id = None # Khởi tạo là None
    if not device_id: errors.append("Missing 'device_id'.")
    if not account_id: errors.append("Missing 'account_id'.")
    if not assignment_id_str:
        errors.append("Missing 'assignment_id'.")
    else:
        try:
            assignment_id = int(assignment_id_str) # Chuyển đổi sang số nguyên
        except (ValueError, TypeError):
            errors.append("Invalid 'assignment_id' format (must be an integer).")

    if not status_report_payload or not isinstance(status_report_payload, dict):
        errors.append("Missing or invalid 'status_report' object.")

    if errors:
        msg = "Invalid report data: " + ", ".join(errors)
        current_app.logger.error(f"Report Status: {msg}. Payload: {data}")
        return jsonify({"status": "error", "message": msg}), 400

    # Nếu assignment_id hợp lệ thì mới xử lý tiếp
    current_app.logger.info(f"Processing status report for Assignment: {assignment_id}, Device: {device_id}, Account: {account_id}")

    # --- Gọi Controller để xử lý logic ---
    # Controller sẽ gọi các hàm DB để cập nhật status, progress, log...
    try:
        response_body, status_code = phone_controller.process_phone_report(
            device_id=device_id,
            account_id=account_id,
            assignment_id=assignment_id, # Truyền ID dạng số nguyên
            report_payload=data # Truyền cả payload gốc vào controller
        )
        # Trả về phản hồi từ controller
        return jsonify(response_body), status_code

    except Exception as e:
        # Lỗi không mong muốn xảy ra trong controller hoặc DB calls
        current_app.logger.error(f"Error processing /report_status for assignment {assignment_id}: {e}", exc_info=True)
        print(traceback.format_exc())
        return jsonify({"status": "error", "message": "Internal server error processing report."}), 500

# --- Các routes khác của phone blueprint nếu có ---

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

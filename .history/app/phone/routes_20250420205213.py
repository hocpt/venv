# app/phone/routes.py
from flask import Blueprint, request, jsonify, current_app
from . import phone_bp # Import blueprint từ __init__.py cùng cấp
from . import controller as phone_controller # Import module chứa logic xử lý
from .. import database as db # Import module database từ thư mục app cha (..)

from datetime import datetime, timezone
import traceback
phone_bp = Blueprint('phone', __name__, url_prefix='/phone')
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
    current_app.logger.info("Received request at /register_device")
    data = request.get_json()

    if not data or not isinstance(data, dict):
        current_app.logger.error("Invalid payload: Not a JSON object.")
        return jsonify({"status": "error", "message": "Invalid JSON payload."}), 400

    device_id = data.get('device_id')
    if not device_id:
        current_app.logger.error("Invalid payload: Missing 'device_id'.")
        return jsonify({"status": "error", "message": "Missing 'device_id'."}), 400

    current_app.logger.info(f"Processing registration for device_id: {device_id}")
    try:
        success, error_msg = phone_controller.handle_device_registration(data)
        if success:
            current_app.logger.info(f"Device {device_id} registered/updated successfully.")
            return jsonify({"status": "success", "message": "Device registered/updated."}), 200
        else:
            current_app.logger.error(f"Device registration failed for {device_id}: {error_msg}")
            return jsonify({"status": "error", "message": error_msg or "Registration failed."}), 400 # Hoặc 500 nếu lỗi server
    except Exception as e:
        current_app.logger.error(f"Unexpected server error during device registration for {device_id}: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Internal server error."}), 500

# --- Route Lấy Chiến lược/Nhiệm vụ (ĐÃ CẬP NHẬT) ---
@phone_bp.route('/get_strategy', methods=['POST'])
def get_strategy():
    """
    Client gửi device_id và account_id để hỏi xem có nhiệm vụ (assignment) nào cần thực thi không.
    Nếu có, server trả về Gói Chiến lược JSON đã biên dịch.
    Nếu không, trả về trạng thái 'no_task'.
    """
    current_app.logger.info("Received request at /get_strategy")
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
            # Có thể trả về no_task hoặc lỗi tùy logic mong muốn
            return jsonify({"status": "error", "message": "Device or Account not registered/linked correctly."}), 404 # Not Found

        # 2. Tìm assignment đang chờ cho device_account_id này
        assignment = db.get_pending_assignment(device_account_id)

        # 3. Xử lý kết quả tìm kiếm assignment
        if assignment:
            assignment_id = assignment['assignment_id']
            strategy_id = assignment['strategy_id']
            target_data = assignment.get('target_data') # Có thể là None hoặc dict

            current_app.logger.info(f"Found assignment {assignment_id} (Strategy: {strategy_id}) for Device: {device_id}, Account: {account_id}")

            # 3a. Cập nhật trạng thái assignment thành 'assigned' (nếu chưa phải running)
            # (Hàm update_assignment_status nên kiểm tra trạng thái hiện tại nếu cần)
            db.update_assignment_status(assignment_id, 'assigned', assigned_at=datetime.now(timezone.utc))

            # 3b. Biên dịch gói chiến lược
            strategy_package = phone_controller.compile_strategy_package(
                strategy_id=strategy_id,
                assignment_id=assignment_id,
                target_data=target_data
            )

            # 3c. Trả về gói JSON nếu biên dịch thành công
            if strategy_package:
                current_app.logger.info(f"Returning compiled strategy package for assignment {assignment_id}.")
                return jsonify(strategy_package), 200
            else:
                # Lỗi biên dịch (đã được log trong controller)
                current_app.logger.error(f"Failed to compile strategy package for assignment {assignment_id}, strategy {strategy_id}.")
                # Có thể cân nhắc cập nhật lại status assignment thành 'error' hoặc 'pending'
                db.update_assignment_status(assignment_id, 'error', result_data={'error': 'Strategy compilation failed'})
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
    Payload cần chứa: device_id, account_id, assignment_id, status_report {...}.
    """
    current_app.logger.info("Received request at /report_status")
    data = request.get_json()

    if not data or not isinstance(data, dict):
        current_app.logger.error("Report Status: Invalid payload.")
        return jsonify({"status": "error", "message": "Invalid JSON payload."}), 400

    # --- Extract và Validate dữ liệu cần thiết ---
    device_id = data.get('device_id')
    account_id = data.get('account_id')
    assignment_id = data.get('assignment_id') # Rất quan trọng
    status_report_payload = data.get('status_report') # Phần chứa log, progress, status...

    errors = []
    if not device_id: errors.append("Missing 'device_id'.")
    if not account_id: errors.append("Missing 'account_id'.")
    if not assignment_id: errors.append("Missing 'assignment_id'.")
    if not status_report_payload or not isinstance(status_report_payload, dict):
        errors.append("Missing or invalid 'status_report' object.")

    if errors:
        msg = "Invalid report data: " + ", ".join(errors)
        current_app.logger.error(f"Report Status: {msg}. Payload: {data}")
        return jsonify({"status": "error", "message": msg}), 400

    current_app.logger.info(f"Processing status report for Assignment: {assignment_id}, Device: {device_id}, Account: {account_id}")

    # --- Gọi Controller để xử lý logic ---
    # Controller sẽ gọi các hàm DB để cập nhật status, progress, log...
    try:
        response_body, status_code = phone_controller.process_phone_report(
            device_id=device_id,
            account_id=account_id,
            assignment_id=int(assignment_id), # Chuyển sang int nếu cần
            report_payload=data # Truyền cả payload gốc vào controller
        )
        # Trả về phản hồi từ controller
        return jsonify(response_body), status_code

    except ValueError: # Lỗi nếu assignment_id không phải số nguyên
        current_app.logger.error(f"Report Status: Invalid assignment_id format: {assignment_id}")
        return jsonify({"status": "error", "message": "Invalid assignment_id format."}), 400
    except Exception as e:
        current_app.logger.error(f"Error processing /report_status for assignment {assignment_id}: {e}", exc_info=True)
        print(traceback.format_exc())
        return jsonify({"status": "error", "message": "Internal server error processing report."}), 500




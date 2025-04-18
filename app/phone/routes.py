# app/phone/routes.py
from flask import request, jsonify, current_app
from . import phone_bp # Import blueprint từ __init__.py cùng cấp
from . import controller as phone_controller # Import module chứa logic xử lý
from .. import database as db # Import module database từ thư mục app cha (..)

# === API Endpoints cho Điện thoại ===

@phone_bp.route('/get_strategy', methods=['GET'])
def get_strategy():
    """
    Endpoint để điện thoại yêu cầu Gói Chiến lược (Strategy Package).
    Cần các tham số như device_id, account_id, strategy_id... tùy thiết kế.
    """
    # Lấy tham số từ query string
    device_id = request.args.get('device_id')
    account_id = request.args.get('account_id')
    strategy_id = request.args.get('strategy_id')
    # Thêm các tham số khác nếu cần (ví dụ: app_name, app_version)

    print(f"INFO (Phone Route): Request for strategy: device={device_id}, account={account_id}, strategy={strategy_id}")

    if not strategy_id:
        return jsonify({"error": "Missing strategy_id parameter"}), 400

    try:
        # Gọi hàm trong controller để biên dịch gói chiến lược
        strategy_package = phone_controller.compile_strategy_package(
            strategy_id=strategy_id,
            account_id=account_id,
            device_id=device_id
            # Truyền thêm các tham số ngữ cảnh nếu cần
        )

        if strategy_package:
            # Trả về gói chiến lược dạng JSON
            # strategy_package nên bao gồm cả version identifier
            return jsonify(strategy_package)
        else:
            # Trả về lỗi nếu không tìm thấy/biên dịch được chiến lược
            return jsonify({"error": f"Strategy '{strategy_id}' not found or compilation failed"}), 404

    except Exception as e:
        print(f"ERROR (Phone Route - get_strategy): {e}")
        # Log lỗi chi tiết vào file log của server
        # traceback.print_exc()
        return jsonify({"error": "Internal server error while compiling strategy"}), 500

@phone_bp.route('/report_status', methods=['POST'])
def report_status():
    """
    Endpoint để điện thoại gửi báo cáo trạng thái, log thực thi, lỗi.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON data"}), 400

    device_id = data.get('device_id')
    account_id = data.get('account_id')
    strategy_id = data.get('strategy_id')
    strategy_version = data.get('strategy_version') # Version của gói đang chạy
    logs = data.get('logs', []) # Danh sách các log entry
    final_status = data.get('final_status', 'unknown') # Trạng thái cuối cùng (completed, error, stopped)

    print(f"INFO (Phone Route): Status report received: device={device_id}, account={account_id}, strategy={strategy_id}, status={final_status}, log_entries={len(logs)}")

    if not device_id or not account_id or not strategy_id:
         return jsonify({"error": "Missing device_id, account_id, or strategy_id"}), 400

    try:
        # Gọi hàm controller để xử lý và lưu log báo cáo
        success = phone_controller.process_status_report(
            device_id=device_id,
            account_id=account_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            final_status=final_status,
            log_data=logs
        )

        if success:
            # Phản hồi đơn giản cho điện thoại biết đã nhận
            return jsonify({"status": "received"})
        else:
            # Có lỗi khi xử lý báo cáo phía server
            return jsonify({"error": "Failed to process status report on server"}), 500

    except Exception as e:
        print(f"ERROR (Phone Route - report_status): {e}")
        # Log lỗi chi tiết
        return jsonify({"error": "Internal server error while processing status report"}), 500

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

# Có thể thêm các route khác sau này, ví dụ: /phone/process_chat_message cho real-time chat
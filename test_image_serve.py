# File: htp6/test_image_serve.py
from flask import Flask, send_from_directory
import os
import sys # Import sys để kiểm tra lỗi socket

# === CẤU HÌNH THƯ MỤC CHỨA ẢNH TEST ===
# Đặt đường dẫn tuyệt đối đến thư mục chứa ảnh bạn muốn test
# Ví dụ: trỏ đến thư mục screenshots thực tế của bạn
IMAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), 'app', 'static', 'screenshots'))

# === TẠO ỨNG DỤNG FLASK NHỎ ===
app = Flask(__name__)
app.config['IMAGE_DIR'] = IMAGE_DIR # Lưu đường dẫn vào config

@app.route('/test_image/<path:filename>')
def serve_test_image(filename):
    image_directory = app.config['IMAGE_DIR']
    print(f"--- Yêu cầu file: {filename}")
    print(f"--- Tìm trong thư mục: {image_directory}")
    full_path = os.path.join(image_directory, filename)
    print(f"--- Đường dẫn đầy đủ: {full_path}")
    if not os.path.exists(full_path):
        print(f"--- LỖI: File không tồn tại!")
        return "File không tìm thấy", 404
    try:
        print(f"--- Đang gửi file...")
        return send_from_directory(image_directory, filename)
    except Exception as e:
        print(f"--- LỖI KHI GỬI FILE: {e}")
        return "Lỗi server khi gửi file", 500

if __name__ == '__main__':
    # === THAY ĐỔI CỔNG MẶC ĐỊNH ===
    test_port = 8181 # Sử dụng cổng 8181 thay vì 5001
    # ============================

    print(f"Thư mục phục vụ ảnh được đặt là: {IMAGE_DIR}")
    print("Đảm bảo có file ảnh trong thư mục này.")
    print(f"Chạy server test tại http://127.0.0.1:{test_port}")

    try:
        # Chạy trên cổng khác để tránh xung đột với app chính
        app.run(debug=True, host='0.0.0.0', port=test_port) # host='0.0.0.0' cho phép truy cập từ IP mạng LAN
    except OSError as e:
        # Bắt lỗi cụ thể nếu cổng bị chặn hoặc đang sử dụng
        if "forbidden by its access permissions" in str(e) or "Address already in use" in str(e):
             print(f"\n!!! LỖI KHỞI ĐỘNG SERVER TEST: Không thể chạy trên cổng {test_port}.")
             print(f"!!! Nguyên nhân có thể là cổng đang được sử dụng bởi ứng dụng khác hoặc bị chặn bởi Firewall/quyền hạn.")
             print(f"!!! Lỗi chi tiết: {e}")
             print(f"!!! Hãy thử đổi giá trị test_port trong script sang một cổng khác (ví dụ: 8088, 9099) hoặc kiểm tra ứng dụng/firewall đang chặn cổng này.")
        else:
             # In ra lỗi OSError khác nếu có
             print(f"\n!!! LỖI OSError KHÁC KHI KHỞI ĐỘNG SERVER: {e}")
        sys.exit(1) # Thoát script nếu không khởi động được server
    except Exception as e:
        # Bắt các lỗi khác có thể xảy ra
        print(f"\n!!! LỖI KHÔNG XÁC ĐỊNH KHI KHỞI ĐỘNG SERVER: {e}")
        sys.exit(1)


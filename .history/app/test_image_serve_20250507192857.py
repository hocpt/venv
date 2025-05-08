# File: htp6/test_image_serve.py
from flask import Flask, send_from_directory
import os

# === CẤU HÌNH THƯ MỤC CHỨA ẢNH TEST ===
# Đặt đường dẫn tuyệt đối đến thư mục chứa ảnh bạn muốn test
# Ví dụ: trỏ đến thư mục screenshots thực tế của bạn
IMAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), 'app', 'static', 'screenshots'))
# Hoặc bạn có thể tạo một thư mục test riêng và đặt ảnh vào đó
# IMAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), 'test_images'))
# if not os.path.exists(IMAGE_DIR):
#     os.makedirs(IMAGE_DIR)
#     print(f"Đã tạo thư mục test: {IMAGE_DIR}")
#     print("Hãy đặt một file ảnh (ví dụ: test.png) vào thư mục này.")

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
    print(f"Thư mục phục vụ ảnh được đặt là: {IMAGE_DIR}")
    print("Đảm bảo có file ảnh trong thư mục này.")
    print("Chạy server test tại http://127.0.0.1:5001")
    # Chạy trên cổng khác để tránh xung đột với app chính
    app.run(debug=True, port=5001)

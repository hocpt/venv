# run.py
# File chính để khởi chạy ứng dụng Flask

import os
from dotenv import load_dotenv
# Import hàm serve từ waitress (cần cài đặt: pip install waitress)
from waitress import serve

# --- Bước 1: Nạp Biến Môi trường từ file .env TRƯỚC TIÊN ---
# Điều này đảm bảo các cấu hình trong .env (DB, API Key,...)
# có sẵn khi ứng dụng Flask được tạo và cấu hình được nạp.
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    print(f"INFO: Đang nạp biến môi trường từ: {dotenv_path}")
    load_dotenv(dotenv_path=dotenv_path)
else:
    print("CẢNH BÁO: Không tìm thấy file .env trong thư mục gốc dự án. Sử dụng giá trị mặc định hoặc biến môi trường hệ thống (nếu có).")

# --- Bước 2: Import hàm tạo app từ package 'app' ---
# Việc import này xảy ra SAU KHI đã load_dotenv()
# Giả định bạn có thư mục 'app' với file '__init__.py' chứa hàm create_app()
try:
    from app import create_app
except ImportError as e:
    print(f"LỖI: Không thể import create_app từ package 'app': {e}")
    print("Hãy đảm bảo bạn có thư mục 'app' chứa file '__init__.py' và hàm 'create_app()'.")
    exit(1) # Thoát nếu không import được app

# --- Bước 3: Tạo đối tượng Flask app bằng hàm factory ---
# Hàm create_app() bên trong app/__init__.py sẽ đọc cấu hình từ config.py
# (config.py lại đọc từ biến môi trường đã được nạp bởi dotenv)
print("INFO: Đang tạo Flask app...")
app = create_app() # Gọi hàm factory để tạo instance app

# --- Bước 4: Chạy Server bằng Waitress ---
if __name__ == '__main__':
    # Kiểm tra xem app đã được tạo thành công chưa
    if app:
        # Lấy host và port từ biến môi trường hoặc dùng giá trị mặc định
        # Chạy trên 0.0.0.0 để có thể truy cập từ máy khác trong mạng LAN
        host = os.environ.get('FLASK_RUN_HOST', '0.0.0.0')
        port = int(os.environ.get('FLASK_RUN_PORT', 5000)) # Port 5000

        # Lấy chế độ debug từ config của app (đã được nạp từ Config class)
        # Lưu ý: Chế độ debug của Flask chủ yếu ảnh hưởng đến traceback lỗi và template reloading,
        # Waitress không có tính năng auto-reloading như server dev của Flask.
        is_debug = app.config.get('DEBUG', False)
        print(f"INFO: Khởi chạy Waitress server tại http://{host}:{port}/ (Flask Debug Mode: {is_debug})")
        print("INFO: Sử dụng Waitress thay vì server phát triển mặc định của Flask để ổn định hơn với APScheduler.")

        # Sử dụng waitress.serve để chạy ứng dụng
        # threads=10 là ví dụ, bạn có thể điều chỉnh
        serve(app, host=host, port=port, threads=10)
    else:
        print("ERROR: Không thể tạo Flask app. Không thể khởi chạy server.")
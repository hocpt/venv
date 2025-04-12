# run.py
import os
from dotenv import load_dotenv

# --- Bước 1: Nạp Biến Môi trường từ file .env TRƯỚC TIÊN ---
# Tìm file .env trong thư mục chứa run.py hoặc thư mục gốc dự án
# Điều chỉnh đường dẫn nếu cần
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    print(f"INFO: Đang nạp biến môi trường từ: {dotenv_path}")
    load_dotenv(dotenv_path=dotenv_path) # Nạp file .env
else:
    print("CẢNH BÁO: Không tìm thấy file .env trong thư mục gốc dự án.")
    # Bạn có thể quyết định dừng lại ở đây nếu thiếu .env là nghiêm trọng

# --- Bước 2: Import hàm tạo app từ package 'app' ---
# Việc import này chỉ nên xảy ra SAU KHI đã load_dotenv()
# Giả định bạn có thư mục 'app' với file '__init__.py' chứa hàm create_app()
try:
    from app import create_app
except ImportError as e:
    print(f"LỖI: Không thể import create_app từ package 'app': {e}")
    print("Hãy đảm bảo bạn có thư mục 'app' chứa file '__init__.py' và hàm 'create_app()'.")
    exit(1) # Thoát nếu không import được app

# --- Bước 3: Tạo đối tượng Flask app bằng hàm factory ---
# Hàm create_app() bên trong app/__init__.py sẽ tự động load config
print("INFO: Đang tạo Flask app...")
app = create_app()

# --- Bước 4: Chạy Flask Development Server ---
if __name__ == '__main__':
    # Lấy host và port từ biến môi trường hoặc dùng giá trị mặc định
    host = os.environ.get('FLASK_RUN_HOST', '0.0.0.0') # Chạy trên mọi IP của máy
    port = int(os.environ.get('FLASK_RUN_PORT', 5000)) # Port 5000
    # Đọc chế độ debug từ biến môi trường (mặc định là True khi phát triển)
    debug_mode = os.environ.get('FLASK_DEBUG', 'True').lower() in ['true', '1', 't']

    print(f"INFO: Khởi chạy Flask server tại http://{host}:{port}/ với debug={debug_mode}")
    # Chỉ dùng app.run() cho môi trường phát triển.
    # Khi triển khai thực tế (production), bạn nên dùng một WSGI server như Gunicorn hoặc Waitress.
    app.run(host=host, port=port, debug=debug_mode, use_reloader=False)
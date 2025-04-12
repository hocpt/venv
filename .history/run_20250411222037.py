# backup/run.py
import os
from dotenv import load_dotenv
from waitress import serve # <<< THÊM IMPORT NÀY

# --- Bước 1: Nạp Biến Môi trường ---
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    print(f"INFO: Đang nạp biến môi trường từ: {dotenv_path}")
    load_dotenv(dotenv_path=dotenv_path)
else:
    print("CẢNH BÁO: Không tìm thấy file .env...")

# --- Bước 2: Import hàm tạo app ---
try:
    from app import create_app
except ImportError as e:
    print(f"LỖI: Không thể import create_app từ package 'app': {e}")
    exit(1)

# --- Bước 3: Tạo đối tượng Flask app ---
print("INFO: Đang tạo Flask app...")
app = create_app() # Hàm create_app vẫn load config như cũ

# --- Bước 4: Chạy Server bằng Waitress ---
if __name__ == '__main__':
    host = os.environ.get('FLASK_RUN_HOST', '0.0.0.0')
    port = int(os.environ.get('FLASK_RUN_PORT', 5000))
    # debug_mode không dùng trực tiếp cho waitress nhưng Flask app vẫn load config DEBUG
    print(f"INFO: Khởi chạy Waitress server tại http://{host}:{port}/")

    # <<< COMMENT OUT HOẶC XÓA DÒNG app.run(...) >>>
    # app.run(host=host, port=port, debug=debug_mode, use_reloader=False)

    # <<< THAY BẰNG waitress.serve(...) >>>
    serve(app, host=host, port=port, threads=10) # threads=10 là ví dụ
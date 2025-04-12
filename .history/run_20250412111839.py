# backup/run.py
import os
from dotenv import load_dotenv
from waitress import serve
import threading # <<< 1. Import threading

# Import hàm tạo app và hàm chạy scheduler
try:
    from app import create_app
    # Import hàm run_scheduler từ module scheduler_runner trong package app
    from app.scheduler_runner import run_scheduler
except ImportError as e:
    print(f"LỖI: Không thể import create_app hoặc run_scheduler: {e}")
    print("Hãy đảm bảo cấu trúc thư mục đúng và không có lỗi cú pháp trong các file được import.")
    traceback.print_exc() # In traceback chi tiết của lỗi Import
    sys.exit(1) # Thoát nếu không import được
except Exception as general_import_err:
     print(f"LỖI không xác định khi import: {general_import_err}")
     traceback.print_exc()
     sys.exit(1)

# --- Nạp Biến Môi trường ---
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    print(f"INFO: Đang nạp biến môi trường từ: {dotenv_path}")
    load_dotenv(dotenv_path=dotenv_path)
else:
    print("CẢNH BÁO: Không tìm thấy file .env...")

# --- Tạo Flask app ---
print("INFO: Đang tạo Flask app...")
app = create_app() # Hàm create_app giờ đã được tối giản

# --- Bước 4: Chạy Server và Scheduler ---
if __name__ == '__main__':
    if app: # Kiểm tra app được tạo thành công
        host = os.environ.get('FLASK_RUN_HOST', '0.0.0.0')
        port = int(os.environ.get('FLASK_RUN_PORT', 5000))
        is_debug = app.config.get('DEBUG', False) # Lấy trạng thái debug từ config

        # <<< Khởi chạy Scheduler trong một Thread riêng biệt >>>
        print("INFO: Chuẩn bị khởi chạy Scheduler trong background thread...")
        # Truyền đối tượng 'app' vào hàm run_scheduler
        scheduler_thread = threading.Thread(target=run_scheduler, args=(app,), daemon=True)
        scheduler_thread.start()
        print("INFO: Background thread cho Scheduler đã được yêu cầu khởi chạy.")
        # <<< Kết thúc phần khởi chạy Scheduler >>>

        # --- Khởi chạy Waitress Server ---
        print(f"INFO: Khởi chạy Waitress server tại http://{host}:{port}/ (Flask Debug Mode: {is_debug})")
        # Waitress sẽ chạy ở luồng chính này
        serve(app, host=host, port=port, threads=10) # threads=10 là ví dụ

    else:
        print("ERROR: Không thể tạo Flask app. Không thể khởi chạy server.")
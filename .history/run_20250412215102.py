# backup/run.py
# File chính để khởi chạy ứng dụng Flask và Scheduler nền (kiến trúc tách rời)

import os
from dotenv import load_dotenv
from waitress import serve
import threading # Import threading
import sys
import traceback
# --- Bước 1: Nạp Biến Môi trường ---
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    print(f"INFO: Đang nạp biến môi trường từ: {dotenv_path}")
    load_dotenv(dotenv_path=dotenv_path)
else:
    print("CẢNH BÁO: Không tìm thấy file .env...")

# --- Bước 2: Import hàm tạo app và hàm chạy scheduler ---
try:
    from app import create_app
    # Import hàm run_scheduler từ module scheduler_runner
    from app.scheduler_runner import run_scheduler # <<< Import hàm chạy scheduler
except ImportError as e:
    print(f"LỖI: Không thể import create_app hoặc run_scheduler: {e}")
    print("Kiểm tra cấu trúc thư mục và các file __init__.py.")
    traceback.print_exc()
    sys.exit(1)
except Exception as general_import_err:
     print(f"LỖI không xác định khi import: {general_import_err}")
     traceback.print_exc()
     sys.exit(1)


# --- Bước 3: Tạo đối tượng Flask app ---
print("INFO: Đang tạo Flask app...")
# Hàm create_app giờ không còn code scheduler
app = create_app()

# --- Bước 4: Chạy Server và Scheduler ---
if __name__ == '__main__':
    if app: # Kiểm tra app được tạo thành công
        host = os.environ.get('FLASK_RUN_HOST', '0.0.0.0')
        port = int(os.environ.get('FLASK_RUN_PORT', 5000))
        is_debug = app.config.get('DEBUG', False)

        # <<< Khởi chạy Scheduler trong một Thread riêng biệt >>>
        print("INFO: Chuẩn bị khởi chạy Scheduler trong background thread...")
        # <<< KHÔNG TRUYỀN 'app' VÀO args NỮA >>>
        scheduler_thread = threading.Thread(target=run_scheduler, args=(), daemon=True) # args là tuple rỗng
        scheduler_thread.start()
        print("INFO: Background thread cho Scheduler đã được yêu cầu khởi chạy.")
        # <<< Kết thúc phần khởi chạy Scheduler >>>

        # --- Khởi chạy Waitress Server ---
        print(f"INFO: Khởi chạy Waitress server tại http://{host}:{port}/ (Flask Debug Mode: {is_debug})")
        serve(app, host=host, port=port, threads=10) # Waitress chạy ở luồng chính

    else:
        print("ERROR: Không thể tạo Flask app. Không thể khởi chạy server.")
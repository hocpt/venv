# backup/app/__init__.py
from datetime import datetime
from flask import Flask
import config
from flask_apscheduler import APScheduler
from flask_sqlalchemy import SQLAlchemy
import importlib
import os
import traceback
import logging
import sys
from datetime import datetime, timedelta


# --- Khởi tạo Extension Instances ---
db_sqlalchemy = SQLAlchemy()
scheduler = APScheduler()



# --- Hàm Create App ---
def create_app(config_class=config.Config):
    app = Flask(
        __name__,
        static_folder='static',
        template_folder='templates'
    )
    app.config['JSON_AS_ASCII'] = False

    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
            try:
                # <<< THAY THẾ/BỔ SUNG PHẦN LOGGING CONFIG >>>
                log_level_name = app.config.get('SCHEDULER_LOG_LEVEL_NAME', 'DEBUG') # Lấy tên level từ config (vd: DEBUG, INFO)
                log_level = getattr(logging, log_level_name.upper(), logging.INFO) # Chuyển tên thành level object
    
                # Cấu hình handler để ghi ra console (stdout)
                stream_handler = logging.StreamHandler(sys.stdout)
                stream_handler.setLevel(log_level)
                stream_handler.setFormatter(logging.Formatter(
                    '%(asctime)s %(levelname)-8s %(name)-25s %(threadName)s : %(message)s' # Thêm tên logger dài hơn
                ))
    
                # Lấy root logger và cấu hình
                root_logger = logging.getLogger()
                root_logger.setLevel(log_level)
                # Xóa handler mặc định (nếu có) và thêm handler mới để tránh log trùng lặp
                # for handler in root_logger.handlers[:]: root_logger.removeHandler(handler) # Cẩn thận khi xóa handler mặc định của Flask
                root_logger.addHandler(stream_handler)
    
    
                # Lấy logger của APScheduler và đặt level, đảm bảo nó dùng handler đã cấu hình
                apscheduler_logger = logging.getLogger('apscheduler')
                apscheduler_logger.setLevel(log_level)
                # apscheduler_logger.addHandler(stream_handler) # Thường không cần nếu root logger đã có handler
                apscheduler_logger.propagate = True # Cho phép log lan truyền lên root logger
    
                print(f"INFO: Logging configured. Root level: {logging.getLevelName(root_logger.level)}, APScheduler level: {logging.getLevelName(apscheduler_logger.level)}")
                # <<< KẾT THÚC PHẦN LOGGING CONFIG >>>
    
                # Bắt đầu scheduler và load jobs (giữ nguyên)
                scheduler.start()
                print("INFO: APScheduler đã bắt đầu.")
                load_scheduled_jobs(app) # Vẫn giữ phiên bản load job date trigger để test nhanh
    
            except Exception as start_err:
                 print(f"ERROR: Lỗi nghiêm trọng khi khởi động scheduler hoặc load jobs: {start_err}")
                 print(traceback.format_exc())
        else:
            print("INFO: APScheduler khởi tạo nhưng không start trong tiến trình reloader phụ.")

    # --- Nạp Cấu hình ---
    print(f"INFO: Đang nạp cấu hình từ class {config_class.__name__}")
    app.config.from_object(config_class)

    # --- Khởi tạo SQLAlchemy với App ---
    try:
        db_sqlalchemy.init_app(app)
        print("INFO: SQLAlchemy initialized.")
    except Exception as sql_err:
         print(f"ERROR: Lỗi khi khởi tạo SQLAlchemy: {sql_err}")

    # --- Khởi tạo Scheduler với App ---
    try:
        scheduler.init_app(app)
        print("INFO: Flask-APScheduler initialized.")
    except Exception as sched_init_err:
         print(f"ERROR: Lỗi khi khởi tạo Flask-APScheduler: {sched_init_err}")

    # --- Bắt đầu scheduler và load jobs (GỌI TRỰC TIẾP - KHÔNG CÓ IF CHECK RELOADER) ---
    print("DEBUG: Attempting to start scheduler and load jobs...")
    try:
        # Cấu hình logging (có thể đặt ở đây hoặc global tùy scope bạn muốn)
        log_level = app.config.get('SCHEDULER_LOG_LEVEL', logging.INFO)
        logging.basicConfig(stream=sys.stdout, level=log_level,
                            format='%(asctime)s %(levelname)-8s %(name)-15s %(threadName)s : %(message)s')
        logging.getLogger('apscheduler').setLevel(logging.DEBUG) # Giữ DEBUG để xem log scheduler
        print(f"INFO: Root logger level set to: {logging.getLogger().level}")
        print(f"INFO: APScheduler logger level set to: DEBUG")

        # Bắt đầu scheduler
        scheduler.start()
        print("INFO: APScheduler đã bắt đầu.")

        # Load jobs từ DB
        load_scheduled_jobs(app)

    except Exception as start_err:
         print(f"ERROR: Lỗi nghiêm trọng khi khởi động scheduler hoặc load jobs: {start_err}")
         print(traceback.format_exc())

    # --- Đăng ký Blueprint ---
    print("DEBUG: Registering blueprints...")
    try:
        from .routes import main_bp
        app.register_blueprint(main_bp)
        print("INFO: Đã đăng ký main_bp.")

        from .admin_routes import admin_bp
        app.register_blueprint(admin_bp)
        print("INFO: Đã đăng ký admin_bp.")
    except Exception as bp_err:
         print(f"ERROR: Lỗi khi đăng ký blueprint: {bp_err}")

    print("INFO: Khởi tạo Flask app thành công.")
    return app

# === Sửa lại hàm load_scheduled_jobs trong backup/app/__init__.py ===
# (Nhớ import datetime và timedelta ở đầu file __init__.py nếu chưa có)


def load_scheduled_jobs(app):
    """[PHIÊN BẢN DEBUG] Load job 'suggestion_job' để chạy 1 lần sau 15 giây."""
    with app.app_context():
        try:
            from . import database as db # Vẫn cần để code khác không lỗi, dù không dùng trong hàm này nữa
            print("INFO: [DEBUG] Forcing 'suggestion_job' to run once in 15 seconds.")

            job_id_to_debug = 'suggestion_job'
            function_path_to_debug = 'app.background_tasks.analyze_interactions_and_suggest' # Phải đúng path

            try:
                # Vẫn cần import hàm để add vào scheduler
                module_path, func_name = function_path_to_debug.rsplit('.', 1)
                module = importlib.import_module(module_path)
                func = getattr(module, func_name)

                # Tính thời điểm chạy (15 giây sau bây giờ)
                run_time = datetime.now() + timedelta(seconds=15)

                # Thêm job với trigger 'date'
                scheduler.add_job(
                    id=job_id_to_debug,
                    func=func,
                    trigger='date', # <<< Dùng trigger date
                    run_date=run_time, # <<< Thời điểm chạy
                    replace_existing=True
                )
                print(f"SUCCESS: [DEBUG] Scheduled job '{job_id_to_debug}' to run once at {run_time.strftime('%Y-%m-%d %H:%M:%S')}.")

            except (ImportError, AttributeError) as import_err:
                print(f"ERROR (load_scheduled_jobs - Debug): Cannot import function '{function_path_to_debug}': {import_err}")
            except Exception as add_job_err:
                print(f"ERROR (load_scheduled_jobs - Debug): Failed to add debug job '{job_id_to_debug}': {add_job_err}")
                print(traceback.format_exc())

        except Exception as e:
            print(f"LỖI NGHIÊM TRỌNG khi đang load scheduled jobs (DEBUG): {e}")
            print(traceback.format_exc())

# ... (Hàm create_app giữ nguyên phiên bản cuối cùng của bạn, đảm bảo scheduler.start() được gọi đúng chỗ) ...
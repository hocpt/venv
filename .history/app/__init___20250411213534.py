# backup/app/__init__.py
from flask import Flask
import config
from flask_apscheduler import APScheduler
# from flask_sqlalchemy import SQLAlchemy # Tạm thời không dùng
import logging
import sys
from datetime import datetime # Cần cho hàm test job

# Khởi tạo scheduler
scheduler = APScheduler()
# db_sqlalchemy = SQLAlchemy() # Tạm thời không dùng

# Hàm test job đơn giản
def simple_test_job():
    print(f"++++++++++++ SIMPLE TEST JOB EXECUTED AT {datetime.now()} +++++++++++++")

# Hàm tạo app tối giản
def create_app(config_class=config.Config):
    app = Flask(__name__)
    print("INFO: Creating minimal app for scheduler test...")
    app.config.from_object(config_class)

    # --- Chỉ khởi tạo Scheduler ---
    try:
        scheduler.init_app(app)
        print("INFO: Flask-APScheduler initialized (using default MemoryJobStore).")
    except Exception as sched_init_err:
         print(f"ERROR: Lỗi khi khởi tạo Flask-APScheduler: {sched_init_err}")
         return None # Không thể chạy nếu scheduler lỗi

    # --- Cấu hình Logging ---
    try:
        log_level_name = app.config.get('SCHEDULER_LOG_LEVEL_NAME', 'DEBUG')
        log_level = getattr(logging, log_level_name.upper(), logging.DEBUG)
        logging.basicConfig(stream=sys.stdout, level=log_level,
                            format='%(asctime)s %(levelname)-8s %(name)-25s %(threadName)s : %(message)s')
        logging.getLogger('apscheduler').setLevel(logging.DEBUG)
        print(f"INFO: Logging configured. APScheduler level: DEBUG")
    except Exception as log_config_err:
         print(f"ERROR: Lỗi khi cấu hình logging: {log_config_err}")


    # --- Thêm Job Test và Start Scheduler ---
    # Chỉ chạy trong tiến trình chính (nếu reloader vẫn đang chạy - dù không nên)
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
        try:
            # Thêm job test chạy mỗi 15 giây
            if not scheduler.get_job('simple_test'):
                print("INFO: Adding simple_test_job (15 seconds interval)...")
                scheduler.add_job(id='simple_test', func=simple_test_job, trigger='interval', seconds=15, replace_existing=True)
            else:
                 print("INFO: simple_test_job already exists.")

            # Bắt đầu scheduler
            if not scheduler.running: # Chỉ start nếu chưa chạy
                scheduler.start()
                print("INFO: APScheduler started.")
            else:
                print("INFO: APScheduler already running.")

        except Exception as start_err:
             print(f"ERROR: Lỗi khi thêm job hoặc start scheduler: {start_err}")
             print(traceback.format_exc())
    else:
         print("INFO: Scheduler not started in secondary reloader process.")


    # Tạm thời không đăng ký blueprint
    # from .routes import main_bp
    # app.register_blueprint(main_bp)
    # from .admin_routes import admin_bp
    # app.register_blueprint(admin_bp)

    print("INFO: Khởi tạo Flask app tối giản thành công.")
    return app
# backup/app/__init__.py
from datetime import datetime, timedelta # Thêm timedelta nếu chưa có
from flask import Flask, current_app # Thêm current_app
import config
from flask_apscheduler import APScheduler
from flask_sqlalchemy import SQLAlchemy
import importlib
import os
import traceback
import logging
import sys
import time # Thêm time cho sleep trong job test

db_sqlalchemy = SQLAlchemy()
scheduler = APScheduler()

# Hàm load jobs từ DB (Giữ nguyên phiên bản đọc từ DB)
def load_scheduled_jobs(app):
    # ... (Code load jobs từ DB như cũ) ...
    pass

# === Hàm Job Test Đơn Giản - Thử truy cập current_app ===
def simple_context_test_job():
    """Job test đơn giản để kiểm tra app context."""
    print(f"++++++++++++ SIMPLE CONTEXT TEST JOB RUNNING at {datetime.now()} +++++++++++++")
    try:
        # Thử truy cập một thuộc tính của current_app (ví dụ: tên app)
        app_name = current_app.name
        print(f"++++++++++++ SUCCESS: Accessed current_app.name = {app_name} +++++++++++++")
    except RuntimeError as e:
        # Lỗi này xảy ra nếu không có app context
        print(f"!!!!!!!!!!!! ERROR: Cannot access current_app inside job: {e} !!!!!!!!!!!!")
    except Exception as e_other:
        print(f"!!!!!!!!!!!! ERROR: Unexpected error inside job: {e_other} !!!!!!!!!!!!")

# Hàm tạo app
def create_app(config_class=config.Config):
    app = Flask(...)
    app.config.from_object(config_class)

    # Init DB
    db_sqlalchemy.init_app(app)
    print("INFO: SQLAlchemy initialized.")

    # Init Scheduler
    scheduler.init_app(app)
    print("INFO: Flask-APScheduler initialized.")

    # Khối Start Scheduler, Load Jobs, Logging (Khôi phục if check)
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        try:
            # Cấu hình Logging (Giữ nguyên như lần sửa cuối)
            log_level_name = app.config.get('SCHEDULER_LOG_LEVEL_NAME', 'DEBUG')
            log_level = getattr(logging, log_level_name.upper(), logging.DEBUG)
            logging.basicConfig(...) # Giữ nguyên cấu hình basicConfig
            logging.getLogger('apscheduler').setLevel(log_level)
            print(f"INFO: Logging configured. APScheduler level: {log_level_name}")

            # Start scheduler
            scheduler.start()
            print("INFO: APScheduler đã bắt đầu.")

            # Load jobs từ DB
            load_scheduled_jobs(app) # Load job 'suggestion_job'

            # <<< THÊM JOB TEST ĐƠN GIẢN VÀO ĐÂY >>>
            try:
                if not scheduler.get_job('simple_context_test_job'):
                    print("INFO: Adding simple_context_test_job (interval: 15 seconds)...")
                    scheduler.add_job(
                        id='simple_context_test_job',
                        func=simple_context_test_job,
                        trigger='interval',
                        seconds=15, # Chạy sau mỗi 15 giây để test nhanh
                        replace_existing=True
                    )
                else:
                     print("INFO: simple_context_test_job already exists.")
            except Exception as add_test_job_err:
                 print(f"ERROR: Không thể thêm simple_context_test_job: {add_test_job_err}")
            # <<< KẾT THÚC THÊM JOB TEST >>>

        except Exception as start_err:
             print(f"ERROR: Lỗi nghiêm trọng khi khởi động scheduler hoặc load jobs: {start_err}")
             print(traceback.format_exc())
    else:
        print("INFO: APScheduler khởi tạo nhưng không start trong tiến trình reloader phụ.")

    # Register Blueprints (Giữ nguyên)
    # ...

    print("INFO: Khởi tạo Flask app thành công.")
    return app
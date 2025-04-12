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
    """Hàm helper để load và đăng ký jobs từ DB."""
    with app.app_context():
        try:
            from . import database as db
            print("INFO: Đang tải cấu hình scheduled jobs từ DB...")
            job_configs = db.get_all_job_configs()

            if job_configs is None:
                print("LỖI: Không thể tải cấu hình jobs từ DB.")
                return
            if not job_configs:
                print("INFO: Không tìm thấy cấu hình job nào trong DB.")
                return

            # print(f"DEBUG: Job configs found in DB: {job_configs}") # Có thể comment lại nếu quá dài

            added_count = 0
            for job_config in job_configs:
                job_id = job_config.get('job_id')
                is_enabled = job_config.get('is_enabled', False)
                function_path = job_config.get('job_function_path')
                trigger_type = job_config.get('trigger_type')
                trigger_args = job_config.get('trigger_args') # Là dict từ DB

                # print(f"\nDEBUG: Processing job config: ID='{job_id}', Enabled={is_enabled}, Path='{function_path}', Trigger='{trigger_type}', Args={trigger_args}")

                if not job_id or not function_path or not trigger_type or trigger_args is None:
                    print(f"WARNING: Bỏ qua job config không hợp lệ: {job_config}")
                    continue
                if not is_enabled:
                    print(f"INFO: Job '{job_id}' đang bị tắt, bỏ qua.")
                    continue

                try:
                    module_path, func_name = function_path.rsplit('.', 1)
                    module = importlib.import_module(module_path)
                    func = getattr(module, func_name)

                    scheduler.add_job(
                        id=job_id, func=func, trigger=trigger_type,
                        replace_existing=True, **trigger_args
                    )
                    print(f"SUCCESS: Đã thêm/cập nhật job '{job_id}' vào scheduler.")
                    added_count += 1
                except (ImportError, AttributeError) as import_err:
                    print(f"ERROR (load_scheduled_jobs): Lỗi import/attribute cho job '{job_id}', path '{function_path}': {import_err}")
                except (TypeError, ValueError) as trigger_err:
                    print(f"ERROR (load_scheduled_jobs): Lỗi trigger args cho job '{job_id}', type '{trigger_type}', args {trigger_args}: {trigger_err}")
                except Exception as add_job_err:
                    print(f"ERROR (load_scheduled_jobs): Lỗi khác khi thêm job '{job_id}': {add_job_err}")
                    print(traceback.format_exc())

            print(f"INFO: Hoàn tất load jobs từ DB. Đã đăng ký/cập nhật {added_count} jobs.")

        except Exception as e:
            print(f"LỖI NGHIÊM TRỌNG khi đang load scheduled jobs: {e}")
            print(traceback.format_exc())

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
    app = Flask(__name__, static_folder='static', template_folder='templates')

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
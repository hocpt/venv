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

def simple_context_test_job_with_context():
     app_ctx_test = current_app._get_current_object()
     if not app_ctx_test:
         print(f"!!!!!!!!!!!! ERROR: Cannot get app instance in simple_context_test_job !!!!!!!!!!!!")
         return
     with app_ctx_test.app_context():
         print(f"++++++++++++ SIMPLE CONTEXT TEST JOB RUNNING (ctx) at {datetime.now()} +++++++++++++")
         try:
             app_name = current_app.name
             print(f"++++++++++++ SUCCESS: Accessed current_app.name = {app_name} +++++++++++++")
         except RuntimeError as e:
             print(f"!!!!!!!!!!!! ERROR: Cannot access current_app inside job: {e} !!!!!!!!!!!!")
         except Exception as e_other:
              print(f"!!!!!!!!!!!! ERROR: Unexpected error inside job: {e_other} !!!!!!!!!!!!")
# Hàm tạo app
def create_app(config_class=config.Config):
    app = Flask(
        __name__,
        static_folder='static',
        template_folder='templates'
    )
    app.config['JSON_AS_ASCII'] = False

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

    # --- Bắt đầu scheduler, load jobs, cấu hình logging TRỰC TIẾP ---
    # (Vì đang dùng waitress hoặc use_reloader=False, create_app chỉ chạy 1 lần)
    print("DEBUG: Attempting direct start scheduler and load jobs...")
    try:
        # Cấu hình Logging
        log_level_name = app.config.get('SCHEDULER_LOG_LEVEL_NAME', 'DEBUG')
        log_level = getattr(logging, log_level_name.upper(), logging.DEBUG)
        logging.basicConfig(stream=sys.stdout, level=log_level,
                            format='%(asctime)s %(levelname)-8s %(name)-25s %(threadName)s : %(message)s')
        logging.getLogger('apscheduler').setLevel(log_level)
        print(f"INFO: Logging configured. APScheduler level: {log_level_name}")

        # Bắt đầu scheduler
        if not scheduler.running: # Chỉ start nếu chưa chạy
             scheduler.start()
             print("INFO: APScheduler đã bắt đầu.")
        else:
             print("INFO: APScheduler already running (possibly from previous init phase - check for duplicate starts).")


        # Load job chính từ DB
        load_scheduled_jobs(app)

        # Thêm job test context (tùy chọn)
        # try:
        #     if not scheduler.get_job('simple_context_test_job'):
        #         print("INFO: Adding simple_context_test_job (interval: 30 seconds)...")
        #         scheduler.add_job(...) # Thêm job test như trước
        #     else: print("INFO: simple_context_test_job already exists.")
        # except Exception as add_test_job_err:
        #      print(f"ERROR: Không thể thêm simple_context_test_job: {add_test_job_err}")

    except Exception as start_err:
         print(f"ERROR: Lỗi nghiêm trọng khi khởi động scheduler hoặc load jobs: {start_err}")
         print(traceback.format_exc())
    # <<< KHÔNG CÒN else: print("INFO: APScheduler khởi tạo nhưng không start...") >>>


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





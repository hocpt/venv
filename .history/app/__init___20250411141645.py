# backup/app/__init__.py
from datetime import datetime
from flask import Flask
import config
from flask_apscheduler import APScheduler
from flask_sqlalchemy import SQLAlchemy
import importlib
import os
import traceback # <<< 1. THÊM IMPORT NÀY
import logging # <<< Thêm import này
import sys
# --- Khởi tạo Scheduler ---
scheduler = APScheduler()
db_sqlalchemy = SQLAlchemy()
# --- Hàm Load Jobs (Đã xóa dòng print lỗi) ---
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

            # Bỏ dòng print(f"DEBUG: Job configs found in DB: {job_configs}") nếu quá dài
            # print(f"DEBUG: Job configs found in DB: {job_configs}")

            added_count = 0
            for job_config in job_configs:
                job_id = job_config.get('job_id')
                is_enabled = job_config.get('is_enabled', False)
                function_path = job_config.get('job_function_path')
                trigger_type = job_config.get('trigger_type')
                trigger_args = job_config.get('trigger_args')

                # Bỏ dòng print debug dài dòng nếu muốn
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
                        id=job_id,
                        func=func,
                        trigger=trigger_type,
                        replace_existing=True,
                        **trigger_args
                    )
                    print(f"SUCCESS: Đã thêm/cập nhật job '{job_id}' vào scheduler.")
                    added_count += 1
                except (ImportError, AttributeError) as import_err:
                    print(f"ERROR (load_scheduled_jobs): Lỗi import/attribute cho job '{job_id}', path '{function_path}': {import_err}")
                except (TypeError, ValueError) as trigger_err:
                    print(f"ERROR (load_scheduled_jobs): Lỗi trigger args cho job '{job_id}', type '{trigger_type}', args {trigger_args}: {trigger_err}")
                except Exception as add_job_err:
                    print(f"ERROR (load_scheduled_jobs): Lỗi khác khi thêm job '{job_id}': {add_job_err}")
                    print(traceback.format_exc()) # In traceback đầy đủ

            print(f"INFO: Hoàn tất load jobs từ DB. Đã đăng ký/cập nhật {added_count} jobs.")

        except Exception as e:
            # <<< 2. XÓA DÒNG PRINT GÂY LỖI config_class Ở ĐÂY >>>
            # print(f"INFO: Đang nạp cấu hình từ class {config_class.__name__}") <--- XÓA DÒNG NÀY
            print(f"LỖI NGHIÊM TRỌNG khi đang load scheduled jobs: {e}")
            print(traceback.format_exc()) # In traceback


# --- Hàm Create App (Đã khôi phục if check) ---
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
    # <<< 3. Init SQLAlchemy TRƯỚC Scheduler >>>
    try:
        db_sqlalchemy.init_app(app)
        print("INFO: SQLAlchemy initialized.")
    except Exception as sql_err:
         print(f"ERROR: Lỗi khi khởi tạo SQLAlchemy: {sql_err}")
         # Có thể raise lỗi ở đây để dừng app nếu DB quan trọng

    # --- Khởi tạo Scheduler với App ---
    # init_app sẽ tự đọc cấu hình SCHEDULER_* từ app.config
    try:
        scheduler.init_app(app)
        print("INFO: Flask-APScheduler initialized.")
    except Exception as sched_init_err:
         print(f"ERROR: Lỗi khi khởi tạo Flask-APScheduler: {sched_init_err}")

   # --- Bắt đầu scheduler và load jobs (Giữ lại if check reloader) ---
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        try:
            # <<< 4. XÓA dòng app.scheduler = scheduler (nếu còn) >>>
            # Việc gắn kết nên được xử lý bởi init_app hoặc import trực tiếp
            log_level = app.config.get('SCHEDULER_LOG_LEVEL', logging.INFO)
            # Cấu hình cơ bản để stream log ra console (stdout)
            logging.basicConfig(stream=sys.stdout, level=log_level,
                                format='%(asctime)s %(levelname)-8s %(name)-15s %(threadName)s : %(message)s')
            # Đặt level DEBUG cho các logger của APScheduler
            logging.getLogger('apscheduler').setLevel(logging.DEBUG)
            # logging.getLogger('apscheduler.scheduler').setLevel(logging.DEBUG)
            # logging.getLogger('apscheduler.executors').setLevel(logging.DEBUG)
            # logging.getLogger('apscheduler.jobstores').setLevel(logging.DEBUG)
            print(f"INFO: Root logger level set to: {logging.getLogger().level}")
            print(f"INFO: APScheduler logger level set to: DEBUG")
            scheduler.start() # <<< 5. Start scheduler >>>
            print("INFO: APScheduler đã bắt đầu.")

            # Load jobs từ DB (hàm này vẫn giữ nguyên)
            load_scheduled_jobs(app)
        except Exception as start_err:
            print(f"ERROR: Lỗi nghiêm trọng khi khởi động scheduler hoặc load jobs: {start_err}")
            print(traceback.format_exc())
    else:
        print("INFO: APScheduler khởi tạo nhưng không start trong tiến trình reloader phụ.")

    # --- Đăng ký Blueprint ---
    # ... (Giữ nguyên phần đăng ký blueprint) ...
    print("DEBUG: Registering blueprints...")
    try:
        from .routes import main_bp
        app.register_blueprint(main_bp)
        print("INFO: Đã đăng ký main_bp.")

        from .admin_routes import admin_bp # Import admin_routes ở đây
        app.register_blueprint(admin_bp)
        print("INFO: Đã đăng ký admin_bp.")
    except Exception as bp_err:
        print(f"ERROR: Lỗi khi đăng ký blueprint: {bp_err}")


    print("INFO: Khởi tạo Flask app thành công.")
    return app

  
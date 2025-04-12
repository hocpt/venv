# backup/app/__init__.py
from datetime import datetime
from flask import Flask
import config
from flask_apscheduler import APScheduler
import importlib
import os
import traceback # <<< 1. THÊM IMPORT NÀY

# --- Khởi tạo Scheduler ---
scheduler = APScheduler()

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

    # --- Khởi tạo Scheduler với App ---
    scheduler.init_app(app)

    # --- Bắt đầu scheduler và load jobs (KHÔI PHỤC LẠI if/else) ---
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        try:
            scheduler.start()
            print("INFO: APScheduler đã được khởi tạo và bắt đầu.")
            load_scheduled_jobs(app) # Load jobs chỉ trong tiến trình chính
        except Exception as start_err:
             print(f"ERROR: Lỗi nghiêm trọng khi khởi động scheduler hoặc load jobs: {start_err}")
             print(traceback.format_exc()) # Dùng traceback đã import
    else:
        print("INFO: APScheduler khởi tạo nhưng không start trong tiến trình reloader phụ.")

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
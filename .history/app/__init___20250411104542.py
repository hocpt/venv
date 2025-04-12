# app/__init__.py
from datetime import datetime
from flask import Flask
import config # Import file config.py (chứa class Config)
from flask_apscheduler import APScheduler
import importlib # <<< 1. Import importlib
import os 
# Import các extension khác nếu cần, ví dụ:
# from flask_sqlalchemy import SQLAlchemy
# Khởi tạo các extension (nếu có) ở đây nhưng chưa cấu hình app
# db = SQLAlchemy()
scheduler = APScheduler()

def load_scheduled_jobs(app):
    """Hàm helper để load và đăng ký jobs từ DB."""
    # Cần app context để dùng db.get_db_connection (vì nó dùng current_app.config)
    with app.app_context():
        try:
            from . import database as db # Import db trong context
            print("INFO: Đang tải cấu hình scheduled jobs từ DB...")
            job_configs = db.get_all_job_configs() # Hàm đã tạo ở bước trước

            if job_configs is None:
                print("LỖI: Không thể tải cấu hình jobs từ DB.")
                return

            if not job_configs:
                print("INFO: Không tìm thấy cấu hình job nào trong DB.")
                return
            print(f"DEBUG: Job configs found in DB: {job_configs}")
            added_count = 0
            for job_config in job_configs:
                job_id = job_config.get('job_id')
                is_enabled = job_config.get('is_enabled', False)
                function_path = job_config.get('job_function_path')
                trigger_type = job_config.get('trigger_type')
                trigger_args = job_config.get('trigger_args') # Đây là dict từ JSONB
                print(f"\nDEBUG: Processing job config: ID='{job_id}', Enabled={is_enabled}, Path='{function_path}', Trigger='{trigger_type}', Args={trigger_args}")
                if not job_id or not function_path or not trigger_type or trigger_args is None:
                    print(f"WARNING: Bỏ qua job config không hợp lệ (thiếu thông tin): {job_config}")
                    continue

                if not is_enabled:
                    print(f"INFO: Job '{job_id}' đang bị tắt (disabled), bỏ qua.")
                    continue

                try:
                    module_path, func_name = function_path.rsplit('.', 1)
                    print(f"DEBUG: Importing module '{module_path}' for job '{job_id}'...")
                    module = importlib.import_module(module_path)
                    print(f"DEBUG: Getting function '{func_name}' from module...")
                    func = getattr(module, func_name)
                    print(f"DEBUG: Function '{func_name}' obtained successfully.")

                    print(f"DEBUG: Attempting scheduler.add_job for '{job_id}'...")
                    scheduler.add_job(
                        id=job_id,
                        func=func,
                        trigger=trigger_type,
                        replace_existing=True,
                        **trigger_args
                    )
                    # <<< DEBUG: Log thành công >>>
                    print(f"SUCCESS: Đã thêm/cập nhật job '{job_id}' vào scheduler.")
                    added_count += 1

                except (ImportError, AttributeError) as import_err:
                    # <<< DEBUG: Log lỗi import cụ thể >>>
                    print(f"ERROR (load_scheduled_jobs): Lỗi import/attribute cho job '{job_id}', path '{function_path}': {import_err}")
                except (TypeError, ValueError) as trigger_err:
                    # <<< DEBUG: Log lỗi trigger args cụ thể >>>
                     print(f"ERROR (load_scheduled_jobs): Lỗi trigger args cho job '{job_id}', type '{trigger_type}', args {trigger_args}: {trigger_err}")
                except Exception as add_job_err:
                    # <<< DEBUG: Log lỗi add_job chung >>>
                    print(f"ERROR (load_scheduled_jobs): Lỗi khác khi thêm job '{job_id}': {add_job_err}")
                    print(traceback.format_exc()) # In traceback đầy đủ


            print(f"INFO: Hoàn tất load jobs từ DB. Đã đăng ký/cập nhật {added_count} jobs.")

        except Exception as e:
            print(f"LỖI NGHIÊM TRỌNG khi đang load scheduled jobs: {e}")
            # Có thể không nên dừng app ở đây, nhưng cần ghi log rõ ràng


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
    # <<< 4. Bắt đầu scheduler (vẫn giữ kiểm tra reloader) >>>
    # Chỉ start khi không ở debug mode HOẶC trong tiến trình chính của Werkzeug reloader
    print("DEBUG: !!! Forcing scheduler start and job loading (DEBUGGING STEP) !!!")
    try:
        scheduler.start()
        print("INFO: APScheduler đã được khởi tạo và bắt đầu (forced for debug).")
        # Gọi hàm load jobs ngay sau khi start
        load_scheduled_jobs(app)
    except Exception as start_err:
        print(f"ERROR: Lỗi nghiêm trọng khi khởi động scheduler hoặc load jobs: {start_err}")
        print(traceback.format_exc()) # In traceback để rõ lỗi hơn


    # --- Khởi tạo các Extension khác (nếu có) ---

    # --- Đăng ký Blueprint ---
    from .routes import main_bp
    app.register_blueprint(main_bp)
    print("INFO: Đã đăng ký main_bp.")

    from .admin_routes import admin_bp
    app.register_blueprint(admin_bp)
    print("INFO: Đã đăng ký admin_bp.")

    # <<< 3. XÓA bỏ phần đăng ký job cứng ở đây (nếu có) >>>
    # Ví dụ: KHÔNG còn dòng scheduler.add_job(id='suggestion_job', ...) ở đây nữa

    print("INFO: Khởi tạo Flask app thành công.")
    return app

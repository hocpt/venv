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

            added_count = 0
            for job_config in job_configs:
                job_id = job_config.get('job_id')
                is_enabled = job_config.get('is_enabled', False)
                function_path = job_config.get('job_function_path')
                trigger_type = job_config.get('trigger_type')
                trigger_args = job_config.get('trigger_args') # Đây là dict từ JSONB

                if not job_id or not function_path or not trigger_type or trigger_args is None:
                    print(f"WARNING: Bỏ qua job config không hợp lệ (thiếu thông tin): {job_config}")
                    continue

                if not is_enabled:
                    print(f"INFO: Job '{job_id}' đang bị tắt (disabled), bỏ qua.")
                    continue

                try:
                    # Tách module path và function name
                    module_path, func_name = function_path.rsplit('.', 1)
                    # Import module động
                    module = importlib.import_module(module_path)
                    # Lấy đối tượng hàm
                    func = getattr(module, func_name)

                    # Thêm job vào scheduler
                    # Sử dụng **trigger_args để giải nén dict thành keyword arguments
                    scheduler.add_job(
                        id=job_id,
                        func=func,
                        trigger=trigger_type,
                        replace_existing=True, # Ghi đè nếu job đã tồn tại (quan trọng khi restart)
                        **trigger_args # Ví dụ: hours=1, minute=30,...
                    )
                    print(f"INFO: Đã đăng ký/cập nhật job '{job_id}' với trigger '{trigger_type}' args {trigger_args}")
                    added_count += 1

                except (ImportError, AttributeError) as import_err:
                    print(f"LỖI: Không thể import hoặc tìm thấy hàm '{function_path}' cho job '{job_id}': {import_err}")
                except TypeError as trigger_err:
                     print(f"LỖI: Trigger args không hợp lệ cho job '{job_id}'. Args: {trigger_args}. Lỗi: {trigger_err}")
                except Exception as add_job_err:
                    print(f"LỖI: Không thể thêm job '{job_id}' vào scheduler: {add_job_err}")

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
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        scheduler.start()
        print("INFO: APScheduler đã được khởi tạo và bắt đầu.")
        # <<< 5. Load jobs từ DB SAU KHI scheduler start >>>
        # Cần chắc chắn scheduler đã start trước khi thêm job động từ DB
        load_scheduled_jobs(app)
    else:
        print("INFO: APScheduler khởi tạo nhưng không start trong tiến trình reloader phụ.")


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

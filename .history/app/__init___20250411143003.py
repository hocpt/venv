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

# --- Khởi tạo Extension Instances ---
db_sqlalchemy = SQLAlchemy()
scheduler = APScheduler()

# --- Hàm Load Jobs (Giữ nguyên) ---
def load_scheduled_jobs(app):
    # ... (Nội dung hàm load_scheduled_jobs giữ nguyên như bạn đã cung cấp) ...
    pass

# --- Hàm Create App ---
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
# backup/app/__init__.py
# Phiên bản đã xóa bỏ APScheduler khỏi __init__

from flask import Flask
import config
from flask_sqlalchemy import SQLAlchemy # <<< Giữ lại nếu bạn dùng SQLAlchemy cho việc khác
import os # <<< Giữ lại nếu config.py hoặc phần khác cần

# --- Khởi tạo Extension Instances (Chỉ giữ lại những cái cần thiết cho Flask app) ---
db_sqlalchemy = SQLAlchemy() # <<< Giữ lại nếu dùng
# scheduler = APScheduler() # <<< XÓA BỎ DÒNG NÀY >>>

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

    # --- Khởi tạo SQLAlchemy với App (Giữ lại nếu dùng) ---
    try:
        db_sqlalchemy.init_app(app)
        print("INFO: SQLAlchemy initialized.")
    except Exception as sql_err:
         print(f"ERROR: Lỗi khi khởi tạo SQLAlchemy: {sql_err}")

   
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

    print("INFO: Khởi tạo Flask app thành công (Scheduler sẽ chạy ở thread riêng).")
    return app
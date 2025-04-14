# backup/app/__init__.py
from flask import Flask, app
import config
from flask_sqlalchemy import SQLAlchemy
import os

db_sqlalchemy = SQLAlchemy()

def create_app(config_class=config.Config):
    app = Flask(
        __name__,
        static_folder='static',
        template_folder='templates'
        from .admin_routes import admin_bp
        app.register_blueprint(admin_bp)
    )
    app.config['JSON_AS_ASCII'] = False

    print(f"INFO: Đang nạp cấu hình từ class {config_class.__name__}")
    app.config.from_object(config_class)

    try:
        db_sqlalchemy.init_app(app)
        print("INFO: SQLAlchemy initialized.")
    except Exception as sql_err:
         print(f"ERROR: Lỗi khi khởi tạo SQLAlchemy: {sql_err}")

    # --- KHÔNG CÓ CODE APSCHEDULER Ở ĐÂY ---

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
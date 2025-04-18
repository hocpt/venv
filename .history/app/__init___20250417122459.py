# backup/app/__init__.py
from flask import Flask, app
import config
from flask_sqlalchemy import SQLAlchemy
import os
db_sqlalchemy = SQLAlchemy()

def create_app(config_class=config.Config):
    app = Flask( __name__, static_folder='static', template_folder='templates' )
    # ... (app.config.from_object...) ...
    # ... (db_sqlalchemy.init_app...) ...

    print("DEBUG: Registering blueprints...")
    try:
        # Đảm bảo import và đăng ký admin_bp ở đây
        from .admin_routes import admin_bp
        app.register_blueprint(admin_bp)
        print("INFO: Đã đăng ký admin_bp.")

        # Import và đăng ký các blueprint khác (main_bp, phone_bp...)
        from .routes import main_bp
        app.register_blueprint(main_bp)
        print("INFO: Đã đăng ký main_bp.")

        # Ví dụ đăng ký phone_bp (nếu đã tạo)
        # from .phone import phone_bp
        # app.register_blueprint(phone_bp)
        # print("INFO: Đã đăng ký phone_bp.")

    except ImportError as bp_import_err:
         print(f"ERROR: Lỗi Import khi đăng ký blueprint: {bp_import_err}")
         # Có thể raise lỗi ở đây
    except Exception as bp_err:
         print(f"ERROR: Lỗi không xác định khi đăng ký blueprint: {bp_err}")

    print("INFO: Khởi tạo Flask app thành công.")
    return app
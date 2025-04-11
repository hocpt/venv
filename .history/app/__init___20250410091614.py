# app/__init__.py
from datetime import datetime
from flask import Flask
import config # Import file config.py (chứa class Config)
# Import các extension khác nếu cần, ví dụ:
# from flask_sqlalchemy import SQLAlchemy
# Khởi tạo các extension (nếu có) ở đây nhưng chưa cấu hình app
# db = SQLAlchemy()

def create_app(config_class=config.Config): # Mặc định dùng class Config từ config.py
    """Application Factory Pattern"""
    app = Flask(
    __name__,
    static_folder='static',              # Chỉ định thư mục chứa file tĩnh
    template_folder='templates'          # Chỉ định thư mục chứa HTML
    )
    
    app.config['JSON_AS_ASCII'] = False # <<< THÊM DÒNG NÀY
    from .routes import main_bp
    app.register_blueprint(main_bp)
    # --- Nạp Cấu hình ---
    # Nạp các biến từ class config được chỉ định (config.py)
    # File config.py đọc giá trị từ os.environ (đã được load_dotenv() nạp từ .env trong run.py)
    print(f"INFO: Đang nạp cấu hình từ class {config_class.__name__}")
    app.config.from_object(config_class)

    # --- Khởi tạo các Extension với app ---
    # Ví dụ: db.init_app(app)
    # --- Đăng ký Blueprint ---
    from .admin_routes import admin_bp # Đảm bảo admin_bp có tên khác 'main'
    app.register_blueprint(admin_bp)
    print("INFO: Đã đăng ký main_bp.") # Thêm log để xác nhận

 

    print("INFO: Khởi tạo Flask app thành công.")
    return app

# app/phone/__init__.py
from flask import Blueprint, Flask
from flask_sqlalchemy import SQLAlchemy 
import os 
import config
# Tạo blueprint 'phone' với tiền tố URL là /phone
# Tất cả các route định nghĩa trong blueprint này sẽ bắt đầu bằng /phone
phone_bp = Blueprint(
    'phone',
    __name__,
    url_prefix='/phone'
    # Nếu có templates hoặc static files riêng cho blueprint này thì thêm:
    # template_folder='templates',
    # static_folder='static'
)

# Import các routes của blueprint này (phải đặt sau khi tạo phone_bp)
# File routes.py sẽ chứa các @phone_bp.route(...)
from . import routes

print("DEBUG: Blueprint 'phone' created.")
def create_app(config_class=config.Config):
    app = Flask(
        __name__,
        static_folder='static', # Đường dẫn static folder so với thư mục app
        template_folder='templates' # Đường dẫn template folder so với thư mục app
        # Nếu templates và static của bạn nằm ở gốc cùng cấp với run.py,
        # bạn cần điều chỉnh lại đường dẫn ở đây hoặc trong Blueprint
        # Ví dụ: static_folder='../static', template_folder='../templates'
        # Hoặc cấu hình khi tạo app: app = Flask(__name__, static_folder='static', template_folder='templates')
    )
    app.config['JSON_AS_ASCII'] = False
    print(f"INFO: Đang nạp cấu hình từ class {config_class.__name__}")
    app.config.from_object(config_class)

    # Khởi tạo các extension khác nếu có (ví dụ SQLAlchemy)
    # try:
    #     db_sqlalchemy.init_app(app)
    #     print("INFO: SQLAlchemy initialized (if used).")
    # except Exception as sql_err:
    #      print(f"ERROR: Lỗi khi khởi tạo SQLAlchemy: {sql_err}")

    print("DEBUG: Registering blueprints...")
    try:
        # Đăng ký các blueprint hiện có
        from .routes import main_bp # Giả sử bạn có main_bp cho các route chính
        app.register_blueprint(main_bp)
        print("INFO: Đã đăng ký main_bp.")

        from .admin_routes import admin_bp
        app.register_blueprint(admin_bp)
        print("INFO: Đã đăng ký admin_bp.")

        # --- ĐĂNG KÝ BLUEPRINT MỚI 'phone' ---
        from .phone import phone_bp # Import từ package 'phone' vừa tạo
        app.register_blueprint(phone_bp)
        print("INFO: Đã đăng ký phone_bp.")
        # --- KẾT THÚC ĐĂNG KÝ BLUEPRINT 'phone' ---

    except ImportError as bp_import_err:
         print(f"ERROR: Lỗi Import khi đăng ký blueprint: {bp_import_err}")
         print("Kiểm tra lại cấu trúc file __init__.py và các file route.")
         # Có thể raise lỗi ở đây để dừng chương trình nếu blueprint là cốt lõi
    except Exception as bp_err:
         print(f"ERROR: Lỗi không xác định khi đăng ký blueprint: {bp_err}")

    print("INFO: Khởi tạo Flask app thành công.")
    return app



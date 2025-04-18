# app/__init__.py
import os
import traceback
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import config # Import lớp Config từ config.py

# Khởi tạo extension SQLAlchemy (dùng cho APScheduler JobStore)
# Để ở global scope để các module khác có thể import nếu cần (mặc dù không phổ biến)
db_sqlalchemy = SQLAlchemy()

def create_app(config_class=config.Config):
    """
    Hàm Factory để tạo và cấu hình đối tượng ứng dụng Flask.
    """
    print("INFO (app/__init__): Bắt đầu tạo Flask app...")
    # Tạo đối tượng Flask app
    # Giả sử thư mục static và templates nằm cùng cấp với run.py (ở gốc dự án)
    # Nếu chúng nằm trong thư mục 'app', hãy đổi thành static_folder='static', template_folder='templates'
    app = Flask(
        __name__,
        static_folder='../static', # Đường dẫn tương đối từ 'app' ra thư mục gốc rồi vào 'static'
        template_folder='../templates' # Đường dẫn tương đối từ 'app' ra thư mục gốc rồi vào 'templates'
    )

    # Nạp cấu hình từ class Config (hoặc biến môi trường)
    try:
        app.config.from_object(config_class)
        print(f"INFO (app/__init__): Đã nạp cấu hình từ class '{config_class.__name__}'.")
        # Cho phép hiển thị tiếng Việt đúng trong JSON response
        app.config['JSON_AS_ASCII'] = False
    except Exception as config_err:
         print(f"CRITICAL ERROR (app/__init__): Lỗi khi nạp cấu hình: {config_err}")
         # Có thể nên dừng ứng dụng ở đây
         raise config_err # Ném lại lỗi để dừng

    # Khởi tạo các extension với đối tượng app
    try:
        db_sqlalchemy.init_app(app)
        print("INFO (app/__init__): SQLAlchemy initialized.")
    except Exception as sql_err:
         # Lỗi này nghiêm trọng vì APScheduler cần SQLAlchemyJobStore
         print(f"CRITICAL ERROR (app/__init__): Lỗi khi khởi tạo SQLAlchemy (Cần cho APScheduler JobStore): {sql_err}")
         print(traceback.format_exc())
         # Cân nhắc dừng ứng dụng

    # --- Đăng ký các Blueprints ---
    print("INFO (app/__init__): Bắt đầu đăng ký blueprints...")
    try:
        # Blueprint chính (cho các route như /receive_content_for_reply)
        from . import routes as main_routes # Đổi tên import để tránh trùng lặp
        app.register_blueprint(main_routes.main_bp)
        print("INFO (app/__init__): Đã đăng ký main_bp.")

        # Blueprint cho trang Admin
        from . import admin_routes # Import blueprint từ module
        app.register_blueprint(admin_routes.admin_bp)
        print("INFO (app/__init__): Đã đăng ký admin_bp.")

        # Blueprint cho API điều khiển điện thoại
        from .phone import phone_bp # Import blueprint từ package 'phone'
        app.register_blueprint(phone_bp)
        print("INFO (app/__init__): Đã đăng ký phone_bp.")

  
        # Đăng ký các blueprint khác nếu có...

    except ImportError as bp_import_err:
         # Lỗi này cũng nghiêm trọng, có thể do cấu trúc file/folder sai
         print(f"CRITICAL ERROR (app/__init__): Lỗi Import khi đăng ký blueprint: {bp_import_err}")
         print("Kiểm tra lại cấu trúc file __init__.py và các file route (ví dụ: admin_routes.py, routes.py, phone/__init__.py).")
         print(traceback.format_exc())
         raise bp_import_err # Dừng ứng dụng nếu không import được blueprint cốt lõi
    except Exception as bp_err:
         print(f"CRITICAL ERROR (app/__init__): Lỗi không xác định khi đăng ký blueprint: {bp_err}")
         print(traceback.format_exc())
         raise bp_err

    print("INFO (app/__init__): Khởi tạo Flask app thành công.")
    return app
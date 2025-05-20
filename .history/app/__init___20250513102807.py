# app/__init__.py
import os
import traceback
from flask import Flask,send_from_directory
from flask_sqlalchemy import SQLAlchemy
import config # Import lớp Config từ config.py
from . import graph_db 
from flask_wtf.csrf import CSRFProtect
# Khởi tạo extension SQLAlchemy (dùng cho APScheduler JobStore)
# Để ở global scope để các module khác có thể import nếu cần (mặc dù không phổ biến)
db_sqlalchemy = SQLAlchemy()
csrf = CSRFProtect()
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
        static_folder='../static',
        #url_prefix='/admin', # Đường dẫn tương đối từ 'app' ra thư mục gốc rồi vào 'static'
        template_folder='../templates' # Đường dẫn tương đối từ 'app' ra thư mục gốc rồi vào 'templates'
    )
    
    try:
        graph_db.init_app(app)
        print("INFO (app/__init__): Neo4j Driver management initialized.")
    except Exception as graph_init_err:
         print(f"WARNING (app/__init__): Could not initialize Neo4j management: {graph_init_err}")
    from .admin_routes import admin_bp # Hoặc from app.admin_routes import admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')
    csrf.init_app(app)
    app.jinja_env.add_extension('jinja2.ext.do')
    app.jinja_env.globals.update(
            max=max,
            min=min
            # Bạn có thể thêm các hàm khác nếu cần
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
    # === TẠO THƯ MỤC UPLOAD NẾU CHƯA CÓ ===
    # Thiết lập logging nếu chưa có
    if not app.debug and not app.testing:
        if not os.path.exists('logs'):
            os.mkdir('logs')
        # Cấu hình logging của bạn ở đây (ví dụ: file handler)
        # Ví dụ cơ bản:
        # file_handler = logging.FileHandler('logs/hpt_automation.log')
        # file_handler.setFormatter(logging.Formatter(
        #     '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'))
        # file_handler.setLevel(logging.INFO)
        # app.logger.addHandler(file_handler)
        # app.logger.setLevel(logging.INFO)
        # app.logger.info('HPT Automation startup')
        pass # Giả sử bạn đã có cấu hình logging

    upload_folder_path = app.config.get('UPLOAD_FOLDER')
    if upload_folder_path and not os.path.exists(upload_folder_path):
        try:
            os.makedirs(upload_folder_path)
            app.logger.info(f"Đã tạo thư mục upload: {upload_folder_path}")
        except OSError as e:
            app.logger.error(f"Không thể tạo thư mục upload {upload_folder_path}: {e}")

    # === THÊM ROUTE TÙY CHỈNH ĐỂ PHỤC VỤ SCREENSHOT TỪ app/static/screenshots ===
    # URL sẽ có dạng /app_screenshots/ten_file.png
    @app.route('/app_screenshots/<path:filename>')
    def serve_app_specific_screenshot(filename): # Tên hàm này sẽ là tên endpoint
        logger = app.logger
        # UPLOAD_FOLDER đã được cấu hình là htp6/app/static/screenshots/
        screenshots_dir = app.config['UPLOAD_FOLDER']
        logger.info(f"[serve_app_specific_screenshot] Yêu cầu phục vụ file: '{filename}'")
        logger.debug(f"[serve_app_specific_screenshot] Từ thư mục: '{screenshots_dir}'")

        file_path_to_check = os.path.join(screenshots_dir, filename)
        if not os.path.exists(file_path_to_check):
            logger.error(f"[serve_app_specific_screenshot] Lỗi 404: File không tồn tại: '{file_path_to_check}'")
            return "File ảnh không tìm thấy", 404
        try:
            return send_from_directory(screenshots_dir, filename)
        except Exception as e:
            logger.error(f"[serve_app_specific_screenshot] Lỗi khi gửi file '{filename}': {e}", exc_info=True)
            return "Lỗi server khi phục vụ file", 500
    # ========================================================================
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
        csrf.exempt(phone_bp)
        app.register_blueprint(phone_bp)
        print("INFO (app/__init__): Đã đăng ký phone_bp.")
        
       #app.register_blueprint(admin_routes.admin_bp, url_prefix='/admin')
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
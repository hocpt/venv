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
    @app.route('/screenshots/<string:app_name>/<string:filename>')
    def serve_screenshot_for_app(app_name, filename):
        logger = app.logger
        screenshots_base_dir = app.config.get('SCREENSHOT_STORAGE_PATH')
        
        if not screenshots_base_dir:
            logger.error("[Serve Screenshot] SCREENSHOT_STORAGE_PATH is not configured!")
            return "Server configuration error: Screenshot storage path not set.", 500

        # An toàn hóa tên
        safe_app_name = "".join(c for c in app_name if c.isalnum() or c in ['.', '_', '-'])
        safe_filename = "".join(c for c in filename if c.isalnum() or c in ['.', '_', '-'])

        if not safe_app_name or not safe_filename:
            logger.error(f"[Serve Screenshot] Invalid app_name or filename. Original: app='{app_name}', file='{filename}'")
            return "App name hoặc filename không hợp lệ.", 400
            
        # Thư mục con của app
        app_specific_dir = os.path.join(screenshots_base_dir, safe_app_name)
        
        logger.info(f"[Serve Screenshot] Request for App: '{safe_app_name}', File: '{safe_filename}'")
        logger.debug(f"[Serve Screenshot] Base storage directory: '{screenshots_base_dir}'")
        logger.debug(f"[Serve Screenshot] App specific directory: '{app_specific_dir}'")

        # Tạo đường dẫn tuyệt đối đến file một cách an toàn
        try:
            # safe_join sẽ kiểm tra path traversal và trả về None nếu không an toàn
            # hoặc ném NotFound nếu path không nằm trong root (ở đây root là app_specific_dir)
            # Tuy nhiên, chúng ta sẽ tự kiểm tra sự tồn tại sau.
            # path_to_file = safe_join(app_specific_dir, safe_filename) # Cách này có thể hơi chặt chẽ
            
            # Cách thông thường với os.path.join và sau đó kiểm tra
            path_to_file_abs = os.path.abspath(os.path.join(app_specific_dir, safe_filename))
            logger.debug(f"[Serve Screenshot] Absolute path to file being checked: '{path_to_file_abs}'")

            # Kiểm tra xem path_to_file_abs có thực sự nằm trong app_specific_dir không để tăng bảo mật
            if not path_to_file_abs.startswith(os.path.abspath(app_specific_dir)):
                logger.error(f"[Serve Screenshot] Path traversal attempt or invalid path construction: '{path_to_file_abs}' is not within '{os.path.abspath(app_specific_dir)}'")
                raise NotFound()

            if not os.path.isfile(path_to_file_abs):
                logger.error(f"[Serve Screenshot] File IS NOT FOUND at (checked by os.path.isfile): '{path_to_file_abs}'")
                # Nếu file không tồn tại, send_from_directory cũng sẽ raise NotFound.
                # Có thể thử đọc file thủ công để xem lỗi gì xảy ra.
                try:
                    # Thử mở file để xem có lỗi quyền không
                    with open(path_to_file_abs, 'rb') as f_test:
                        logger.debug(f"[Serve Screenshot] Test open file '{path_to_file_abs}' successful (this shouldn't happen if isfile is false).")
                except Exception as e_open:
                    logger.error(f"[Serve Screenshot] Test open file '{path_to_file_abs}' FAILED: {e_open}")
                
                raise NotFound() # Ném lỗi NotFound chuẩn của Werkzeug
            else:
                logger.info(f"[Serve Screenshot] File FOUND at (checked by os.path.isfile): '{path_to_file_abs}'")

            # Nếu os.path.isfile(path_to_file_abs) là True, send_from_directory NÊN hoạt động.
            logger.debug(f"[Serve Screenshot] Attempting to send_from_directory: directory='{app_specific_dir}', filename='{safe_filename}'")
            return send_from_directory(app_specific_dir, safe_filename, as_attachment=False)

        except NotFound: # Bắt lỗi NotFound được ném từ check isfile hoặc từ send_from_directory
            logger.error(f"[Serve Screenshot] Caught NotFound for: '{safe_filename}' in '{app_specific_dir}'")
            # Trả về 404 rõ ràng hơn cho client thay vì 500
            response = make_response("File ảnh không tìm thấy trên server.", 404)
            response.headers["Content-Type"] = "text/plain"
            return response
        except Exception as e:
            logger.error(f"[Serve Screenshot] Unhandled error sending file '{safe_filename}' from '{app_specific_dir}': {e}", exc_info=True)
            response = make_response("Lỗi server nội bộ khi phục vụ file.", 500)
            response.headers["Content-Type"] = "text/plain"
            return response
    # ========================================================================
    try:
        # Blueprint chính (cho các route như /receive_content_for_reply)
        from . import routes as main_routes # Đổi tên import để tránh trùng lặp
        app.register_blueprint(main_routes.main_bp)
        print("INFO (app/__init__): Đã đăng ký main_bp.")

        # Blueprint cho trang Admin
        from . import admin_routes # Import blueprint từ module
        #app.register_blueprint(admin_routes.admin_bp, url_prefix='/admin')
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
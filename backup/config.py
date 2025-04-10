# config.py
import os

# Lấy đường dẫn thư mục chứa file config.py này
basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    # Cấu hình chung
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'ban-nen-thay-doi-key-nay'
    FLASK_APP = os.environ.get('FLASK_APP') or 'run.py'
    FLASK_ENV = os.environ.get('FLASK_ENV') or 'development'
    # Đọc chế độ DEBUG từ biến môi trường
    DEBUG = os.environ.get('FLASK_DEBUG', 'True').lower() in ['true', '1', 't']

    # Cấu hình Database (Đọc từ biến môi trường được nạp bởi .env)
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = os.environ.get("DB_PORT", "5432")
    DB_NAME = os.environ.get("DB_NAME")
    DB_USER = os.environ.get("DB_USER")
    DB_PASSWORD = os.environ.get("DB_PASSWORD")

    # Cấu hình API AI
    GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

    # Kiểm tra các biến môi trường bắt buộc
    if not DB_NAME or not DB_USER or not DB_PASSWORD:
        # Trong ứng dụng thực tế, nên raise lỗi hoặc ghi log nghiêm trọng
        print("CẢNH BÁO NGHIÊM TRỌNG: Thiếu cấu hình CSDL (DB_NAME, DB_USER, DB_PASSWORD) trong file .env hoặc biến môi trường!")
    if not GOOGLE_API_KEY:
         print("CẢNH BÁO: Thiếu GOOGLE_API_KEY trong file .env hoặc biến môi trường. Chức năng AI có thể không hoạt động.")

# Bạn có thể thêm các class cấu hình khác kế thừa từ Config
# class DevelopmentConfig(Config):
#     DEBUG = True
# class ProductionConfig(Config):
#     DEBUG = False
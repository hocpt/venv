# config.py
import os

import logging

# Lấy đường dẫn thư mục chứa file config.py này
basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    # Cấu hình chung
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
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

    # Ví dụ: Thêm vào đầu file backup/app/admin_routes.py
    VALID_PLATFORMS = ['facebook', 'tiktok', 'zalo', 'youtube', 'other']
    VALID_GOALS = ['follow','make_friend', 'product_sales', 'lead_generation', 'support', 'other']

    VALID_INTENTS_FOR_TRANSITION = [
        'greeting', 'price_query', 'shipping_query', 'product_info_query',
        'compliment', 'complaint', 'connection_request', 'spam',
        'positive_generic', 'negative_generic', 'other', 'any' # Thêm 'any'
    ]
     # ID của Persona mặc định sẽ dùng để trả lời nếu Account không có chỉ định
    # Bạn cần tạo Persona với ID này trong Admin UI
    DEFAULT_REPLY_PERSONA_ID = 'general_assistant'

    # ID của Persona sẽ dùng trong tác vụ nền để phân tích và đề xuất rule/template
    # Bạn cần tạo Persona với ID này trong Admin UI
    SUGGESTION_ANALYSIS_PERSONA_ID = 'rule_suggester'
    if DB_USER and DB_PASSWORD and DB_HOST and DB_PORT and DB_NAME:
        SQLALCHEMY_DATABASE_URI = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    else:
        SQLALCHEMY_DATABASE_URI = None # Sẽ báo lỗi nếu thiếu khi khởi tạo SQLAlchemy
        print("CẢNH BÁO NGHIÊM TRỌNG: Thiếu cấu hình DB cho SQLAlchemy!")

    # --- Cấu hình APScheduler ---
    # Chỉ định Job Store mặc định là SQLAlchemyJobStore, sử dụng URI từ SQLAlchemy
    SCHEDULER_JOBSTORES = {
        'default': {'type': 'sqlalchemy', 'url': SQLALCHEMY_DATABASE_URI}
        # Bạn cũng có thể cấu hình trực tiếp URI ở đây nếu không muốn phụ thuộc vào SQLAlchemy config key
        # 'default': {'type': 'sqlalchemy', 'url': f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"}
    }
    SCHEDULER_API_ENABLED = True
    SCHEDULER_LOG_LEVEL = logging.DEBUG # Hoặc dùng số 10
# Bạn có thể thêm các class cấu hình khác kế thừa từ Config
# class DevelopmentConfig(Config):
#     DEBUG = True
# class ProductionConfig(Config):
#     DEBUG = False
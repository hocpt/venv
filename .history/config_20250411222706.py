# config.py
import os
import logging # Import logging để dùng logging.DEBUG

# Lấy đường dẫn thư mục chứa file config.py này (thường không cần thiết nếu dùng os.environ)
# basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    """Lớp cấu hình chính cho ứng dụng Flask."""

    # --- Cấu hình Flask cơ bản ---
    # Lấy từ biến môi trường hoặc dùng giá trị mặc định an toàn/phát triển
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'mot-secret-key-rat-manh-va-kho-doan!'
    FLASK_APP = os.environ.get('FLASK_APP') or 'run.py' # Thường không cần đặt ở đây nếu dùng run.py
    FLASK_ENV = os.environ.get('FLASK_ENV') or 'development'
    # Đọc chế độ DEBUG từ biến môi trường (True/False)
    DEBUG = os.environ.get('FLASK_DEBUG', 'True').lower() in ['true', '1', 't']

    # Cấu hình Database PostgreSQL (Đọc từ biến môi trường)
    # Các biến này nên được đặt trong file .env của bạn
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = os.environ.get("DB_PORT", "5432")
    DB_NAME = os.environ.get("DB_NAME")
    DB_USER = os.environ.get("DB_USER")
    DB_PASSWORD = os.environ.get("DB_PASSWORD")

    # Cấu hình API Key cho Google AI (Gemini)
    GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

    # --- Kiểm tra các biến môi trường quan trọng ---
    # In cảnh báo nếu thiếu, trong production nên raise Exception
    if not DB_NAME or not DB_USER or not DB_PASSWORD:
        print("CRITICAL WARNING: Missing Database configuration (DB_NAME, DB_USER, DB_PASSWORD) in .env or environment variables!")
    if not GOOGLE_API_KEY:
        print("WARNING: Missing GOOGLE_API_KEY in .env or environment variables. AI features might fail.")

    # --- Cấu hình SQLAlchemy ---
    SQLALCHEMY_TRACK_MODIFICATIONS = False # Tắt tính năng track không cần thiết của SQLAlchemy
    # Tạo URI kết nối CSDL cho SQLAlchemy
    if DB_USER and DB_PASSWORD and DB_HOST and DB_PORT and DB_NAME:
        SQLALCHEMY_DATABASE_URI = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    else:
        SQLALCHEMY_DATABASE_URI = None # Sẽ gây lỗi nếu SQLAlchemy được khởi tạo mà không có URI

    # --- Cấu hình APScheduler ---
    SCHEDULER_API_ENABLED = True
    # Sử dụng SQLAlchemyJobStore làm kho lưu trữ job mặc định
    if SQLALCHEMY_DATABASE_URI: # Chỉ cấu hình jobstore nếu có URI database
        SCHEDULER_JOBSTORES = {
            # 'default': SQLAlchemyJobStore(url=SQLALCHEMY_DATABASE_URI) # Cách cũ
             'default': {'type': 'sqlalchemy', 'url': SQLALCHEMY_DATABASE_URI} # Cách cấu hình qua dict
        }
    else:
        print("WARNING: Cannot configure SQLAlchemyJobStore for APScheduler due to missing DB URI.")
        SCHEDULER_JOBSTORES = {
             'default': {'type': 'memory'} # Fallback về MemoryJobStore nếu lỗi DB config
        }
        print("WARNING: APScheduler falling back to MemoryJobStore!")

    # Cấu hình Executor (ThreadPool là mặc định và thường đủ dùng)
    SCHEDULER_EXECUTORS = {
       'default': {'type': 'threadpool', 'max_workers': 10}
       # Hoặc dùng ProcessPool nếu ThreadPool gặp vấn đề:
       # 'default': {'type': 'processpool', 'max_workers': 5}
    }
    # Cấu hình mặc định cho các job (tùy chọn)
    SCHEDULER_JOB_DEFAULTS = {
        'coalesce': False,      # Không gộp các lần chạy bị lỡ
        'max_instances': 1      # Chỉ cho phép 1 instance của job chạy cùng lúc
    }
    # Bật log DEBUG cho APScheduler để dễ gỡ lỗi
    SCHEDULER_LOG_LEVEL_NAME = 'DEBUG' # Biến này sẽ được đọc trong __init__.py


    # --- Các danh sách và hằng số tùy chỉnh của ứng dụng ---
    VALID_PLATFORMS = ['facebook', 'tiktok', 'zalo', 'youtube', 'instagram', 'website', 'other']
    VALID_GOALS = ['follow','make_friend', 'product_sales', 'lead_generation', 'support', 'other']
    VALID_INTENTS_FOR_TRANSITION = [
        'greeting', 'price_query', 'shipping_query', 'product_info_query',
        'compliment', 'complaint', 'connection_request', 'spam',
        'positive_generic', 'negative_generic', 'other', 'any'
    ]
    # ID Persona mặc định
    DEFAULT_REPLY_PERSONA_ID = 'general_assistant'
    SUGGESTION_ANALYSIS_PERSONA_ID = 'rule_suggester'

    # Tên Model Gemini mặc định (tùy chọn, có thể ghi đè trong Persona)
    GEMINI_DEFAULT_MODEL = 'models/gemini-1.5-flash-latest'
    GEMINI_REPLY_MODEL = os.environ.get('GEMINI_REPLY_MODEL', GEMINI_DEFAULT_MODEL)
    GEMINI_CLASSIFY_MODEL = os.environ.get('GEMINI_CLASSIFY_MODEL', GEMINI_DEFAULT_MODEL)
    GEMINI_SUGGEST_MODEL = os.environ.get('GEMINI_SUGGEST_MODEL', GEMINI_DEFAULT_MODEL)

    # Cấu hình sinh text Gemini mặc định (có thể ghi đè trong Persona)
    GEMINI_REPLY_TEMPERATURE = 0.7
    GEMINI_REPLY_MAX_TOKENS = 1000


# Có thể thêm các class config khác cho môi trường khác nhau nếu cần
# class DevelopmentConfig(Config):
#     DEBUG = True
#     SCHEDULER_LOG_LEVEL_NAME = 'DEBUG'

# class ProductionConfig(Config):
#     DEBUG = False
#     SCHEDULER_LOG_LEVEL_NAME = 'INFO'
#     # Các cấu hình khác cho production...
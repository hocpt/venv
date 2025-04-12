# backup/app/scheduler_runner.py
import logging
import traceback
import time
import importlib
import json
import os # <<< Thêm import os để đọc biến môi trường
import psycopg2 # <<< Thêm import psycopg2 để kết nối DB trực tiếp
import psycopg2.extras # <<< Thêm để dùng DictCursor
from datetime import datetime
# from flask import Flask # <<< Không cần import Flask nữa
from flask_apscheduler import APScheduler
# Import các thành phần của APScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor # Hoặc ProcessPoolExecutor
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

# Biến toàn cục giữ instance scheduler đang chạy
live_scheduler = None
live_scheduler = APScheduler()
log = logging.getLogger(__name__)

# --- Hàm Load Jobs (Phiên bản Standalone - Kết nối DB trực tiếp) ---
def load_scheduled_jobs_standalone(scheduler: BackgroundScheduler, db_config: dict):
    global live_scheduler

    # Nạp biến môi trường từ .env nếu có
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)

    # Cấu hình logger
    logging.basicConfig(level=logging.DEBUG,
        format='%(asctime)s %(levelname)-8s %(name)-25s %(threadName)s : %(message)s')

    # Lấy URL DB cho JobStore từ biến môi trường
    db_url = os.environ.get("SQLALCHEMY_DATABASE_URI")
    if not db_url:
        db_user = os.environ.get("DB_USER")
        db_password = os.environ.get("DB_PASSWORD")
        db_host = os.environ.get("DB_HOST", "localhost")
        db_port = os.environ.get("DB_PORT", "5432")
        db_name = os.environ.get("DB_NAME")
        db_url = f"postgresql+psycopg2://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

    jobstores = {
        'default': SQLAlchemyJobStore(url=db_url)
    }
    executors = {
        'default': {'type': 'processpool', 'max_workers': 5}
    }
    job_defaults = {
        'coalesce': False,
        'max_instances': 3
    }

    scheduler = BackgroundScheduler(jobstores=jobstores,
                                    executors=executors,
                                    job_defaults=job_defaults,
                                    timezone='UTC')

    # Load job (ví dụ hardcode job)
    try:
        scheduler.add_job(
            id='suggestion_job',
            func='app.background_tasks.analyze_interactions_and_suggest',
            trigger='interval',
            seconds=20,
            replace_existing=True
        )
        logging.info("✅ Đã thêm job suggestion_job vào scheduler.")
    except Exception as e:
        logging.error(f"❌ Lỗi khi thêm job: {e}")

    try:
        scheduler.start()
        live_scheduler = scheduler
        logging.info("✅ APScheduler đã khởi động.")
    except Exception as e:
        logging.error(f"❌ Lỗi khởi động scheduler: {e}")
        live_scheduler = None
# --- Kết thúc file app/scheduler_runner.py ---
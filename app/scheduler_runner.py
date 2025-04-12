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

# Import các thành phần của APScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor # Hoặc ProcessPoolExecutor
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

# Biến toàn cục giữ instance scheduler đang chạy
live_scheduler = None

log = logging.getLogger(__name__)

# --- Hàm Load Jobs (Phiên bản Standalone - Kết nối DB trực tiếp) ---
def load_scheduled_jobs_standalone(scheduler: BackgroundScheduler, db_config: dict):
    """
    Hàm helper để load và đăng ký jobs từ DB vào instance scheduler được cung cấp.
    Kết nối DB trực tiếp bằng psycopg2, không cần app context.

    Args:
        scheduler: Instance BackgroundScheduler đang chạy.
        db_config: Dictionary chứa thông tin kết nối DB ('host', 'port', 'dbname', 'user', 'password').
    """
    print("INFO (scheduler_runner): Starting to load scheduled jobs from DB (standalone)...")
    conn = None
    cur = None
    job_configs = []

    # Kết nối CSDL trực tiếp
    try:
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor) # Dùng DictCursor
        print(f"DEBUG (scheduler_runner): Connected to DB directly to fetch jobs.")
        cur.execute("""
            SELECT job_id, job_function_path, trigger_type, trigger_args, is_enabled, description
            FROM scheduled_jobs ORDER BY job_id;
        """)
        rows = cur.fetchall()
        job_configs = [dict(row) for row in rows] if rows else []
        print(f"DEBUG (scheduler_runner): Found {len(job_configs)} job configs in DB.")

    except psycopg2.Error as db_err:
        print(f"ERROR (scheduler_runner): Failed to connect or query scheduled_jobs table: {db_err}")
        print(traceback.format_exc())
        # Không thể load job nếu lỗi DB
        return
    except Exception as e:
        print(f"ERROR (scheduler_runner): Unexpected error fetching jobs from DB: {e}")
        print(traceback.format_exc())
        return
    finally:
        if cur: cur.close()
        if conn: conn.close()
        print(f"DEBUG (scheduler_runner): Closed direct DB connection after fetching jobs.")


    # Xử lý và thêm jobs vào scheduler
    added_count = 0
    if not job_configs:
        print("INFO (scheduler_runner): No job configurations found in DB to load.")
        return

    for job_config in job_configs:
        job_id = job_config.get('job_id')
        is_enabled = job_config.get('is_enabled', False)
        function_path = job_config.get('job_function_path')
        trigger_type = job_config.get('trigger_type')
        trigger_args_dict = job_config.get('trigger_args', {}) # Là dict từ JSONB

        print(f"DEBUG (scheduler_runner): Processing job config: ID='{job_id}', Enabled={is_enabled}, Path='{function_path}', Trigger='{trigger_type}', Args={trigger_args_dict}")

        if not job_id or not function_path or not trigger_type or trigger_args_dict is None:
            print(f"WARNING (scheduler_runner): Skipping invalid job config: {job_config}")
            continue

        # Xóa job khỏi scheduler nếu nó bị disable trong DB
        # Quan trọng khi restart, đảm bảo job bị tắt sẽ bị xóa khỏi lịch chạy
        if not is_enabled:
            print(f"INFO (scheduler_runner): Job '{job_id}' is disabled in config.")
            try:
                 if scheduler.get_job(job_id):
                      scheduler.remove_job(job_id)
                      print(f"INFO (scheduler_runner): Removed disabled job '{job_id}' from running scheduler.")
            except Exception as e_remove:
                 print(f"ERROR (scheduler_runner): Failed to remove disabled job '{job_id}' from scheduler: {e_remove}")
            continue # Bỏ qua không thêm lại job bị disable

        # Chỉ xử lý các job được enable
        try:
            # Import hàm
            module_path, func_name = function_path.rsplit('.', 1)
            module = importlib.import_module(module_path)
            func = getattr(module, func_name)

            # Tạo đối tượng trigger (vẫn cần chuyển đổi kiểu số)
            trigger_obj = None
            numeric_keys = ['weeks', 'days', 'hours', 'minutes', 'seconds', 'jitter', 'year', 'month', 'day', 'week', 'hour', 'minute', 'second']
            converted_args = trigger_args_dict.copy()
            for key in numeric_keys:
                if key in converted_args and isinstance(converted_args[key], str):
                     value_str = converted_args[key].strip()
                     if not value_str: del converted_args[key]; continue
                     try:
                         if '.' in value_str: converted_args[key] = float(value_str)
                         else: converted_args[key] = int(value_str)
                     except (ValueError, TypeError): raise ValueError(f"Invalid numeric value for '{key}': '{value_str}'")

            if trigger_type == 'interval':
                trigger_obj = IntervalTrigger(**converted_args)
            elif trigger_type == 'cron':
                trigger_obj = CronTrigger(**converted_args)
            elif trigger_type == 'date':
                trigger_obj = DateTrigger(**converted_args)
            else:
                 raise ValueError(f"Unsupported trigger type: {trigger_type}")

            # Thêm hoặc cập nhật job trong scheduler
            # <<< KHÔNG CÒN args=(app,) >>>
            scheduler.add_job(
                id=job_id,
                func=func, # Hàm background_task không cần nhận app nữa
                trigger=trigger_obj,
                replace_existing=True,
                name=job_config.get('description', job_id) # Lấy tên từ description nếu có
            )
            print(f"SUCCESS (scheduler_runner): Added/Updated job '{job_id}' in scheduler.")
            added_count += 1

        except (ValueError, ImportError, AttributeError) as config_err:
            print(f"ERROR (scheduler_runner): Invalid config for job '{job_id}': {config_err}")
        except (TypeError) as trigger_err:
            print(f"ERROR (scheduler_runner): Invalid trigger args for job '{job_id}', type '{trigger_type}', args {trigger_args_dict}: {trigger_err}")
        except Exception as add_job_err:
            print(f"ERROR (scheduler_runner): Failed to add/update job '{job_id}' to scheduler: {add_job_err}")
            print(traceback.format_exc())

    print(f"INFO (scheduler_runner): Finished loading jobs from DB. Added/Updated {added_count} enabled jobs.")


# <<< HÀM run_scheduler KHÔNG NHẬN app NỮA >>>
def run_scheduler():
    """
    Hàm chính chạy trong thread riêng, khởi tạo và chạy BackgroundScheduler.
    Đã thêm log debug chi tiết.
    """
    global live_scheduler
    print("--- THREAD SCHEDULER: Starting run_scheduler function ---") # Log ngay khi vào hàm

    try:
        print("DEBUG (scheduler_runner): Reading DB config from environment...")
        # --- Đọc cấu hình CSDL ---
        db_config = {
            "host": os.environ.get("DB_HOST", "localhost"),
            "port": os.environ.get("DB_PORT", "5432"),
            "dbname": os.environ.get("DB_NAME"),
            "user": os.environ.get("DB_USER"),
            "password": os.environ.get("DB_PASSWORD")
        }
        if not all(db_config.values()):
            print("CRITICAL ERROR (scheduler_runner): Missing Database configuration environment variables. Scheduler thread stopping.")
            return

        db_uri = f"postgresql+psycopg2://{db_config['user']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['dbname']}"
        print(f"DEBUG (scheduler_runner): Database URI for JobStore: {db_uri.replace(db_config['password'],'***')}")

        # --- Cấu hình Jobstore và Executor ---
        print("DEBUG (scheduler_runner): Configuring jobstore (SQLAlchemy)...")
        jobstores = { 'default': SQLAlchemyJobStore(url=db_uri) }
        print("DEBUG (scheduler_runner): Configuring executor (ThreadPool)...")
        executors = { 'default': ThreadPoolExecutor(max_workers=10) } # Lấy max_workers từ config app nếu muốn
        job_defaults = {'coalesce': False, 'max_instances': 1}
        timezone = 'Asia/Ho_Chi_Minh' # Hoặc timezone từ config
        print(f"DEBUG (scheduler_runner): Jobstore, Executor, Defaults, Timezone configured.")

        # --- Khởi tạo BackgroundScheduler ---
        print("DEBUG (scheduler_runner): Initializing BackgroundScheduler...")
        scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone=timezone
        )
        print("DEBUG (scheduler_runner): BackgroundScheduler initialized object created.")

        # Gán vào biến toàn cục
        live_scheduler = scheduler
        print(f"INFO (scheduler_runner): BackgroundScheduler instance assigned to 'live_scheduler'.")

        # Load jobs từ DB
        print("DEBUG (scheduler_runner): Calling load_scheduled_jobs_standalone...")
        # Hàm này cần db_config để kết nối DB trực tiếp
        load_scheduled_jobs_standalone(live_scheduler, db_config)
        print("DEBUG (scheduler_runner): Finished call to load_scheduled_jobs_standalone.")

        # Bắt đầu chạy scheduler
        print("INFO (scheduler_runner): Starting BackgroundScheduler loop...")
        live_scheduler.start()
        print("SUCCESS (scheduler_runner): BackgroundScheduler started successfully in separate thread.")

        # Giữ thread sống
        print("INFO (scheduler_runner): Entering keep-alive loop (sleep 1 hour)...")
        while True:
            time.sleep(3600)

    except (KeyboardInterrupt, SystemExit):
         print("INFO (scheduler_runner): Shutdown signal received in main loop...")
         # Việc shutdown sẽ được xử lý trong finally

    except Exception as e:
        # Bắt tất cả lỗi xảy ra trong quá trình khởi tạo/chạy scheduler
        print(f"CRITICAL ERROR initializing or running the scheduler in thread: {e}")
        print(traceback.format_exc())
        live_scheduler = None # Đặt lại là None nếu lỗi nghiêm trọng
    finally:
        # Dọn dẹp khi thread kết thúc
        print("INFO (scheduler_runner): Entering finally block...")
        if live_scheduler and live_scheduler.running:
            print("INFO (scheduler_runner): Shutting down scheduler...")
            live_scheduler.shutdown()
            print("INFO (scheduler_runner): Scheduler shut down.")
        print("--- THREAD SCHEDULER: Exiting run_scheduler function ---")
# --- Kết thúc file app/scheduler_runner.py ---
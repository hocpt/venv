# backup/app/scheduler_runner.py
import logging
import traceback
import time
import importlib
import json
import os
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta, timezone # <<< Thêm timezone
import pytz # <<< Thêm pytz
import uuid # <<< Thêm uuid

# Import các thành phần APScheduler
from flask_apscheduler import APScheduler # Giữ lại nếu cần kiểu dữ liệu
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.job import Job
from dotenv import load_dotenv

# Import các hàm DB và hàm tác vụ nền
try:
    from . import database as db
    from .background_tasks import run_ai_conversation_simulation # Import hàm mô phỏng
    # Import thêm hàm tạo app nếu cần (ví dụ cho context trong monitor/processor nếu cần)
    from . import create_app
except ImportError:
    try:
        import database as db
        from background_tasks import run_ai_conversation_simulation
        import create_app # Thử import create_app từ cấp ngoài nếu cần
        print("WARNING (scheduler_runner): Using fallback imports for db, background_tasks, create_app.")
    except ImportError as imp_err:
         print(f"CRITICAL ERROR (scheduler_runner): Cannot import db/background_tasks/create_app: {imp_err}")
         db = None
         run_ai_conversation_simulation = None
         create_app = None


# Biến toàn cục giữ instance scheduler đang chạy
live_scheduler: BackgroundScheduler | None = None
log = logging.getLogger(__name__)
SCHEDULER_TIMEZONE = pytz.timezone('Asia/Ho_Chi_Minh')

# --- Hàm đọc cấu hình DB (Giữ nguyên) ---
def _get_db_config():
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
    return {
        'host': os.environ.get("DB_HOST", "localhost"),
        'port': os.environ.get("DB_PORT", "5432"),
        'dbname': os.environ.get("DB_NAME"),
        'user': os.environ.get("DB_USER"),
        'password': os.environ.get("DB_PASSWORD")
    }

# --- Hàm Load Jobs (Giữ nguyên code cũ) ---
def load_scheduled_jobs_standalone(scheduler: BackgroundScheduler, db_config: dict):
    # ... (Dán code đầy đủ của hàm này từ các bước trước vào đây) ...
    print("INFO (scheduler_runner): Starting to load scheduled jobs from DB (standalone)...")
    conn = None
    cur = None
    job_configs = []
    try:
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        print(f"DEBUG (scheduler_runner): Connected DB for jobs.")
        cur.execute("""
            SELECT job_id, job_function_path, trigger_type, trigger_args, is_enabled, description
            FROM scheduled_jobs ORDER BY job_id;
        """)
        rows = cur.fetchall()
        job_configs = [dict(row) for row in rows] if rows else []
        print(f"DEBUG (scheduler_runner): Found {len(job_configs)} job configs.")
    except psycopg2.Error as db_err:
        print(f"ERROR (scheduler_runner): Failed query scheduled_jobs: {db_err}")
        return
    except Exception as e:
        print(f"ERROR (scheduler_runner): Unexpected error fetching jobs: {e}")
        return
    finally:
        if cur: cur.close()
        if conn: conn.close()
        print(f"DEBUG (scheduler_runner): Closed DB connection after fetching jobs.")

    added_count = 0
    if not job_configs: return

    for job_config in job_configs:
        job_id = job_config.get('job_id'); is_enabled = job_config.get('is_enabled', False)
        function_path = job_config.get('job_function_path'); trigger_type = job_config.get('trigger_type')
        trigger_args_dict = job_config.get('trigger_args', {})
        if not all([job_id, function_path, trigger_type, trigger_args_dict is not None]): continue
        if not is_enabled: continue # Chỉ load job enabled

        try:
            module_path, func_name = function_path.rsplit('.', 1)
            module = importlib.import_module(module_path); func = getattr(module, func_name)
            trigger_obj = None
            numeric_keys = ['weeks','days','hours','minutes','seconds','jitter','year','month','day','week','hour','minute','second']
            converted_args = trigger_args_dict.copy()
            for key in numeric_keys:
                if key in converted_args and isinstance(converted_args[key], str):
                     val_str = converted_args[key].strip()
                     if not val_str: del converted_args[key]; continue
                     try: converted_args[key] = float(val_str) if '.' in val_str else int(val_str)
                     except (ValueError, TypeError): raise ValueError(f"Invalid num '{key}': '{val_str}'")
            if trigger_type == 'interval': trigger_obj = IntervalTrigger(**converted_args)
            elif trigger_type == 'cron': trigger_obj = CronTrigger(**converted_args)
            elif trigger_type == 'date': trigger_obj = DateTrigger(**converted_args)
            else: raise ValueError(f"Unsupported trigger: {trigger_type}")
            scheduler.add_job(id=job_id,func=func,trigger=trigger_obj,replace_existing=True,name=job_config.get('description', job_id))
            added_count += 1
        except Exception as add_job_err: print(f"ERROR adding job '{job_id}': {add_job_err}")
    print(f"INFO (scheduler_runner): Loaded {added_count} enabled jobs.")


# --- Hàm Giám Sát Trạng Thái Job (Giữ nguyên code cũ) ---
def _monitor_and_sync_job_status():
    # ... (Dán code đầy đủ của hàm này từ các bước trước vào đây) ...
    global live_scheduler
    if not live_scheduler or not live_scheduler.running: return
    print(f"DEBUG (Monitor Job): Running DB sync check... ({datetime.now(SCHEDULER_TIMEZONE).strftime('%H:%M:%S')})")
    db_config = _get_db_config()
    db_statuses = {}
    conn = None; cur = None
    try:
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT job_id, is_enabled FROM scheduled_jobs;")
        rows = cur.fetchall(); db_statuses = {row['job_id']: row['is_enabled'] for row in rows} if rows else {}
    except Exception as e: print(f"ERROR (Monitor Job): Query DB failed: {e}"); return
    finally:
        if cur: cur.close();
        if conn: conn.close()
    if not db_statuses: return
    try: live_jobs = live_scheduler.get_jobs(jobstore='default'); live_job_dict = {job.id: job for job in live_jobs}
    except Exception as e_get: print(f"ERROR (Monitor Job): Get live jobs failed: {e_get}"); return
    for job_id, is_enabled_in_db in db_statuses.items():
        live_job = live_job_dict.get(job_id)
        if live_job:
            is_paused = live_job.next_run_time is None
            if is_enabled_in_db and is_paused:
                try: live_scheduler.resume_job(job_id, jobstore='default'); print(f"INFO (Monitor Job): Resumed '{job_id}'.")
                except Exception as e_res: print(f"ERROR (Monitor Job): Resume '{job_id}' failed: {e_res}")
            elif not is_enabled_in_db and not is_paused:
                try: live_scheduler.pause_job(job_id, jobstore='default'); print(f"INFO (Monitor Job): Paused '{job_id}'.")
                except Exception as e_pau: print(f"ERROR (Monitor Job): Pause '{job_id}' failed: {e_pau}")


# --- === HÀM MỚI: XỬ LÝ LỆNH TỪ DATABASE === ---
def _process_pending_commands():
    """
    Kiểm tra bảng scheduler_commands và thực thi các lệnh đang chờ.
    """
    global live_scheduler
    if not live_scheduler or not live_scheduler.running: return
    if not db or not run_ai_conversation_simulation:
        print("ERROR (Command Processor): DB/background_task function not available.")
        return

    print(f"DEBUG (Command Processor): Checking for pending commands...")
    conn = None
    try:
        conn = db.get_db_connection()
        if not conn:
            print("ERROR (Command Processor): Cannot get DB connection for command processing.")
            return
        conn.autocommit = False # Bắt đầu Transaction

        pending_commands = db.get_pending_commands(command_type='run_simulation', limit=5)

        if not pending_commands:
            conn.commit() # Commit để giải phóng lock (nếu có)
            return

        print(f"INFO (Command Processor): Found {len(pending_commands)} pending 'run_simulation' commands.")

        for command in pending_commands:
            command_id = command['command_id']
            payload_str = command['payload']
            print(f"DEBUG (Command Processor): Processing command ID: {command_id}")

            # 1. Đánh dấu là đang xử lý
            updated_processing = db.update_command_status(conn, command_id, 'processing')
            if not updated_processing:
                print(f"WARNING (Command Processor): Could not mark command {command_id} as processing. Skipping.")
                continue

            try:
                # 2. Parse Payload và chuẩn bị Args
                params = json.loads(payload_str)
                persona_a_id = params.get('persona_a_id')
                persona_b_id = params.get('persona_b_id')
                strategy_id = params.get('strategy_id')
                max_turns = int(params.get('max_turns', 5))
                starting_prompt = params.get('starting_prompt') or "Xin chào!"
                sim_account_id = params.get('sim_account_id') or f"sim_{command_id}"
                sim_thread_id_base = params.get('sim_thread_id_base') or f"sim_{command_id}"
                sim_goal = params.get('sim_goal') or "simulation"

                if not all([persona_a_id, persona_b_id, strategy_id]):
                    raise ValueError("Missing required parameters in payload")

                job_id = f"sim_run_{sim_thread_id_base}_{uuid.uuid4().hex[:8]}"
                job_args = (
                    persona_a_id, persona_b_id, strategy_id, max_turns,
                    starting_prompt, sim_account_id, sim_thread_id_base, sim_goal
                )
                # Lên lịch chạy sau ~2 giây từ bây giờ
                run_time = datetime.now(SCHEDULER_TIMEZONE) + timedelta(seconds=2)

                print(f"DEBUG (Command Processor): Scheduling job '{job_id}' with args: {job_args}")

                # 3. Thêm Job vào Scheduler (an toàn từ luồng này)
                live_scheduler.add_job(
                    id=job_id,
                    func=run_ai_conversation_simulation, # Hàm tác vụ
                    args=job_args,
                    trigger='date',
                    run_date=run_time,
                    jobstore='default',
                    executor='processpool', # Chạy trong process riêng
                    replace_existing=False,
                    misfire_grace_time=120
                )

                # 4. Cập nhật Status thành Done
                db.update_command_status(conn, command_id, 'done')
                print(f"INFO (Command Processor): Successfully scheduled job for command {command_id}")

            except Exception as processing_err:
                # 5. Xử lý lỗi -> Cập nhật Status thành Error
                error_msg = f"Error processing command {command_id}: {type(processing_err).__name__} - {processing_err}"
                print(error_msg)
                # print(traceback.format_exc()) # Bỏ comment nếu cần debug sâu
                db.update_command_status(conn, command_id, 'error', error_message=str(processing_err)[:500])

        # Commit tất cả thay đổi status của batch này
        conn.commit()
        print(f"DEBUG (Command Processor): Finished processing command batch.")

    except Exception as e:
        print(f"ERROR (Command Processor): Unexpected error: {e}")
        if conn: conn.rollback() # Rollback nếu có lỗi lớn
    finally:
        if conn:
             conn.autocommit = True
             conn.close()


# --- HÀM RUN SCHEDULER (Thêm job xử lý lệnh) ---
def run_scheduler():
    global live_scheduler

    # ... (Lấy db_config, cấu hình logger) ...
    db_config = _get_db_config(); # ... (kiểm tra config) ...
    if not all(db_config.values()): print("CRITICAL ERROR: Missing DB config."); return
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(name)-25s %(threadName)s : %(message)s')
    logging.getLogger('apscheduler').setLevel(logging.WARNING) # Giảm log APScheduler

    # ... (Lấy db_url, cấu hình jobstores, executors, job_defaults) ...
    db_url = os.environ.get("SQLALCHEMY_DATABASE_URI")
    if not db_url: db_url = f"postgresql+psycopg2://{db_config['user']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['dbname']}"
    jobstores = { 'default': SQLAlchemyJobStore(url=db_url) }
    executors = {
        'default': {'type': 'threadpool', 'max_workers': 5},
        'processpool': {'type': 'processpool', 'max_workers': os.cpu_count() or 2} # Dùng số CPU hoặc 2
    }
    job_defaults = { 'coalesce': False, 'max_instances': 1, 'misfire_grace_time': 60 }

    # Tạo scheduler
    scheduler = BackgroundScheduler(
        jobstores=jobstores, executors=executors, job_defaults=job_defaults,
        timezone=SCHEDULER_TIMEZONE
    )

    # --- Load jobs cấu hình từ DB ---
    try: load_scheduled_jobs_standalone(scheduler, db_config)
    except Exception as load_err: print(f"ERROR loading jobs: {load_err}")

    # --- Thêm Job Giám Sát Trạng Thái ---
    try:
        scheduler.add_job(id='_monitor_db_config', func=_monitor_and_sync_job_status, trigger='interval', minutes=1, replace_existing=True, executor='default')
        print("INFO (scheduler_runner): Added job status monitor.")
    except Exception as monitor_err: print(f"ERROR adding monitor job: {monitor_err}")

    # --- === THÊM JOB XỬ LÝ LỆNH === ---
    try:
        scheduler.add_job(
            id='_process_commands',
            func=_process_pending_commands, # <<< Hàm mới
            trigger='interval',
            seconds=15, # <<< Chạy mỗi 15 giây
            replace_existing=True,
            executor='default' # <<< Chạy trong threadpool
        )
        print("INFO (scheduler_runner): Added command processor job.")
    except Exception as cmd_proc_err:
        print(f"ERROR adding command processor job: {cmd_proc_err}")

    # --- Khởi động Scheduler ---
    try:
        scheduler.start(paused=False)
        live_scheduler = scheduler
        print("INFO (scheduler_runner): APScheduler started successfully.")
    except Exception as start_err:
        print(f"CRITICAL ERROR starting scheduler: {start_err}")
        live_scheduler = None

# --- Main Execution (Giữ nguyên) ---
if __name__ == "__main__":
    print("INFO: Running scheduler_runner.py directly for testing...")
    run_scheduler()
    try:
         while True: time.sleep(2)
    except (KeyboardInterrupt, SystemExit):
         if live_scheduler: print("INFO: Shutting down scheduler..."); live_scheduler.shutdown()
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
# Import các thành phần APScheduler (giữ nguyên)
from flask_apscheduler import APScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor # <<< Thêm ProcessPoolExecutor nếu dùng
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.job import Job
from dotenv import load_dotenv
from apscheduler.jobstores.base import JobLookupError
# <<< Import các hàm DB và hàm tác vụ nền >>>
try:
    # Thử import tương đối (cách chuẩn)
    from . import database as db
    from .background_tasks import run_ai_conversation_simulation, analyze_interactions_and_suggest, approve_all_suggestions_task # <<< Thêm approve_all
    from . import create_app
except ImportError:
    # Nếu thất bại, thử import trực tiếp (ít tin cậy hơn)
    try:
        import database as db
        from background_tasks import run_ai_conversation_simulation, analyze_interactions_and_suggest, approve_all_suggestions_task
        import create_app
        print("WARNING (scheduler_runner): Using fallback imports...")
    except ImportError as imp_err:
        print(f"CRIT ERROR: Cannot import db/tasks/create_app: {imp_err}")
        db=None; run_ai_conversation_simulation=None; analyze_interactions_and_suggest=None; approve_all_suggestions_task=None; create_app=None
# Biến toàn cục giữ instance scheduler đang chạy
live_scheduler: BackgroundScheduler | None = None # Type hint cho rõ
log = logging.getLogger(__name__)
SCHEDULER_TIMEZONE = pytz.timezone('Asia/Ho_Chi_Minh') # <<< Định nghĩa timezone chung

# --- Hàm đọc cấu hình DB (Tách ra để dùng lại) ---
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

# --- Hàm Load Jobs (Giữ nguyên - không thay đổi) ---
def load_scheduled_jobs_standalone(scheduler: BackgroundScheduler, db_config: dict):
    # ... (code của hàm load_scheduled_jobs_standalone giữ nguyên) ...
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
        if not is_enabled:
            print(f"INFO (scheduler_runner): Job '{job_id}' is disabled in config.")
            try:
                 existing_job = scheduler.get_job(job_id)
                 if existing_job:
                      scheduler.remove_job(job_id)
                      print(f"INFO (scheduler_runner): Removed disabled job '{job_id}' from scheduler during load.")
            except Exception as e_remove:
                 print(f"ERROR (scheduler_runner): Failed to remove disabled job '{job_id}' during load: {e_remove}")
            continue # Bỏ qua không thêm lại job bị disable

        # Chỉ xử lý các job được enable
        try:
            module_path, func_name = function_path.rsplit('.', 1)
            module = importlib.import_module(module_path)
            func = getattr(module, func_name)

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

            scheduler.add_job(
                id=job_id,
                func=func,
                trigger=trigger_obj,
                replace_existing=True,
                name=job_config.get('description', job_id)
                # <<< KHÔNG CÓ PAUSED BAN ĐẦU NỮA, SẼ DO MONITOR XỬ LÝ >>>
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


# --- === HÀM XỬ LÝ LỆNH TỪ DATABASE (PHIÊN BẢN HOÀN CHỈNH) === ---

def _process_pending_commands():
    # ... (code lấy connection, lấy các loại lệnh pending như cũ, bao gồm cả approve_all nếu cần) ...
    global live_scheduler
    if not live_scheduler or not live_scheduler.running: return
    if not db: print("ERROR (Cmd Proc): DB module missing."); return
    print(f"DEBUG (Cmd Proc): Checking pending commands...")
    conn = None
    try:
        conn = db.get_db_connection(); # ... (kiểm tra conn) ...
        if not conn: print("ERROR (Cmd Proc): Cannot get DB conn."); return
        conn.autocommit = False

        # Lấy các lệnh đang chờ
        pending_sim = db.get_pending_commands(command_type='run_simulation', limit=5) or []
        pending_run_suggest = db.get_pending_commands(command_type='run_suggestion_job_now', limit=5) or []
        pending_cancel = db.get_pending_commands(command_type='cancel_job', limit=10) or []
        pending_approve_all = db.get_pending_commands(command_type='approve_all_suggestions', limit=2) or [] # <<< Lấy lệnh approve all

        all_pending = pending_sim + pending_run_suggest + pending_cancel + pending_approve_all # <<< Thêm vào list tổng

        if not all_pending: conn.commit(); if conn: conn.close(); return # Commit, đóng và thoát nếu không có gì
        print(f"INFO (Cmd Proc): Found {len(all_pending)} pending command(s).")

        processed_count = 0
        for command in all_pending:
            # ... (code lấy command_id, type, payload, đánh dấu processing như cũ) ...
            command_id = command['command_id']; command_type = command['command_type']; payload = command['payload']
            print(f"DEBUG (Cmd Proc): Processing command ID: {command_id}, Type: {command_type}")
            updated_processing = db.update_command_status(conn, command_id, 'processing')
            if not updated_processing: print(f"WARN (Cmd Proc): Skip cmd {command_id}, cannot mark processing."); continue

            try:
                # --- Phân loại và Xử lý Lệnh ---
                if command_type == 'run_simulation':
                    # ... (Code xử lý run_simulation như cũ) ...
                    if not run_ai_conversation_simulation: raise ImportError("Sim func missing")
                    # ... (trích xuất args, tạo job_id, gọi add_job) ...
                    live_scheduler.add_job(..., func=run_ai_conversation_simulation, ...)
                    db.update_command_status(conn, command_id, 'done')
                    processed_count += 1

                elif command_type == 'run_suggestion_job_now':
                     # ... (Code xử lý run_suggestion_job_now như cũ) ...
                     if not analyze_interactions_and_suggest: raise ImportError("Suggest func missing")
                     # ... (tạo job_id, gọi add_job) ...
                     live_scheduler.add_job(..., func=analyze_interactions_and_suggest, args=(), ...)
                     db.update_command_status(conn, command_id, 'done')
                     processed_count += 1

                elif command_type == 'cancel_job':
                     # ... (Code xử lý cancel_job như cũ) ...
                     job_id_to_cancel = payload.get('job_id_to_cancel')
                     if not job_id_to_cancel: raise ValueError("Missing job_id_to_cancel")
                     try:
                          live_scheduler.remove_job(job_id_to_cancel, jobstore='default')
                          print(f"INFO (Cmd Proc): Removed job '{job_id_to_cancel}'.")
                          db.update_command_status(conn, command_id, 'done')
                     except JobLookupError:
                          print(f"WARN (Cmd Proc): Job '{job_id_to_cancel}' not found for cancellation.")
                          db.update_command_status(conn, command_id, 'done') # Vẫn đánh dấu done
                     processed_count += 1

                # --- === THÊM XỬ LÝ CHO LỆNH APPROVE_ALL_SUGGESTIONS === ---
                elif command_type == 'approve_all_suggestions':
                     if not approve_all_suggestions_task: raise ImportError("approve_all_suggestions_task function not available")
                     job_id = f"approve_all_run_{uuid.uuid4().hex[:8]}"
                     run_time = datetime.now(SCHEDULER_TIMEZONE) + timedelta(seconds=1)
                     print(f"DEBUG (Cmd Proc): Scheduling job '{job_id}' Func='approve_all_suggestions_task'")
                     # Tác vụ này có thể không quá nặng, dùng threadpool? Hoặc processpool cho an toàn? -> Dùng processpool
                     live_scheduler.add_job(
                          id=job_id,
                          func=approve_all_suggestions_task, # Hàm duyệt hàng loạt
                          args=(), # Hàm này không cần args từ payload
                          trigger='date',
                          run_date=run_time,
                          jobstore='default',
                          executor='processpool', # Chạy riêng để không ảnh hưởng nhiều
                          replace_existing=False,
                          misfire_grace_time=300 # Cho phép trễ 5 phút
                     )
                     db.update_command_status(conn, command_id, 'done') # Đánh dấu lệnh gốc là done
                     print(f"INFO (Cmd Proc): Scheduled job '{job_id}' for cmd {command_id}.")
                     processed_count += 1
                # --- === KẾT THÚC XỬ LÝ LỆNH MỚI === ---

                else:
                    raise ValueError(f"Unknown command_type: {command_type}")

            except Exception as processing_err:
                # ... (Xử lý lỗi cho từng command như cũ) ...
                error_msg = f"Error processing command {command_id} ({command_type}): {type(processing_err).__name__} - {processing_err}"
                print(error_msg)
                db.update_command_status(conn, command_id, 'error', error_message=str(processing_err)[:500])

        # Commit transaction
        conn.commit()
        if processed_count > 0:
             print(f"DEBUG (Command Processor): Finished processing batch of {processed_count} command(s).")

    except Exception as e:
        # ... (Xử lý lỗi và finally như cũ) ...
        print(f"ERROR (Cmd Proc): Unexpected error: {e}")
        if conn: conn.rollback()
    finally:
        if conn: conn.autocommit = True; conn.close()
# --- HÀM GIÁM SÁT MỚI ---
def _monitor_and_sync_job_status():
    global live_scheduler
    if not live_scheduler or not live_scheduler.running:
        # print("DEBUG (Monitor Job): Scheduler not running, skipping sync.")
        return

    print(f"DEBUG (Monitor Job): Running DB sync check... ({datetime.now().strftime('%H:%M:%S')})")
    db_config = _get_db_config()
    db_statuses = {} # Dict để lưu {job_id: is_enabled} từ DB

    # 1. Lấy trạng thái is_enabled mới nhất từ DB
    conn = None
    cur = None
    try:
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT job_id, is_enabled FROM scheduled_jobs;")
        rows = cur.fetchall()
        db_statuses = {row['job_id']: row['is_enabled'] for row in rows} if rows else {}
    except psycopg2.Error as db_err:
        print(f"ERROR (Monitor Job): Failed to query DB for job statuses: {db_err}")
        return # Bỏ qua lần sync này nếu lỗi DB
    except Exception as e:
        print(f"ERROR (Monitor Job): Unexpected error querying DB: {e}")
        return
    finally:
        if cur: cur.close()
        if conn: conn.close()

    if not db_statuses:
         # print("DEBUG (Monitor Job): No job configurations found in DB to sync.")
         return

    # 2. Lấy danh sách các job đang thực sự chạy trong scheduler
    try:
         live_jobs = live_scheduler.get_jobs(jobstore='default') # Lấy job từ jobstore default
         live_job_dict: dict[str, Job] = {job.id: job for job in live_jobs} # Dict job đang chạy
    except Exception as e_get_jobs:
        print(f"ERROR (Monitor Job): Failed to get live jobs from scheduler: {e_get_jobs}")
        return

    # 3. Đồng bộ trạng thái
    for job_id, is_enabled_in_db in db_statuses.items():
        live_job = live_job_dict.get(job_id)

        if live_job:
            # Job đang tồn tại trong scheduler
            is_paused_in_scheduler = live_job.next_run_time is None # Kiểm tra trạng thái paused
            # print(f"DEBUG (Monitor Job): Checking '{job_id}'. DB Enabled: {is_enabled_in_db}, Scheduler Paused: {is_paused_in_scheduler}")

            if is_enabled_in_db and is_paused_in_scheduler:
                # Cần resume job
                try:
                    live_scheduler.resume_job(job_id, jobstore='default')
                    print(f"INFO (Monitor Job): Resumed job '{job_id}' based on DB config.")
                except Exception as e_resume:
                    print(f"ERROR (Monitor Job): Failed to resume job '{job_id}': {e_resume}")
            elif not is_enabled_in_db and not is_paused_in_scheduler:
                # Cần pause job
                try:
                    live_scheduler.pause_job(job_id, jobstore='default')
                    print(f"INFO (Monitor Job): Paused job '{job_id}' based on DB config.")
                except Exception as e_pause:
                    print(f"ERROR (Monitor Job): Failed to pause job '{job_id}': {e_pause}")
        # else:
             # Job có trong DB nhưng không có trong scheduler (có thể do chưa restart hoặc lỗi load)
             # Việc tự động thêm job ở đây phức tạp hơn, tạm bỏ qua. Monitor chủ yếu sync pause/resume.
             # print(f"DEBUG (Monitor Job): Job '{job_id}' found in DB but not live in scheduler.")

# --- HÀM RUN SCHEDULER (Thêm job giám sát) ---
def run_scheduler():
    global live_scheduler

    # ... (Lấy db_config, cấu hình logger giữ nguyên) ...
    db_config = _get_db_config()
    if not all(db_config.values()):
         print("CRITICAL ERROR (scheduler_runner): Missing database configuration. Cannot start scheduler.")
         return
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(name)-25s %(threadName)s : %(message)s')
    logging.getLogger('apscheduler.scheduler').setLevel(logging.WARNING)
    logging.getLogger('apscheduler.jobstores').setLevel(logging.WARNING)
    logging.getLogger('apscheduler.executors').setLevel(logging.WARNING)

    # ... (Lấy db_url, cấu hình jobstores, executors, job_defaults giữ nguyên) ...
    db_url = os.environ.get("SQLALCHEMY_DATABASE_URI")
    if not db_url:
        db_url = f"postgresql+psycopg2://{db_config['user']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['dbname']}"
    jobstores = { 'default': SQLAlchemyJobStore(url=db_url) }
    executors = {
        'default': {'type': 'threadpool', 'max_workers': 5}, # Cho monitor, command processor
        'processpool': {'type': 'processpool', 'max_workers': 2} # Cho simulation, suggestion
    }
    job_defaults = { 'coalesce': False, 'max_instances': 1, 'misfire_grace_time': 60 }

    # Tạo scheduler với timezone
    scheduler = BackgroundScheduler(
        jobstores=jobstores,
        executors=executors,
        job_defaults=job_defaults,
        timezone=SCHEDULER_TIMEZONE # <<< Sử dụng timezone đã định nghĩa
    )

    # --- Load jobs cấu hình từ DB ---
    try:
        print("INFO (scheduler_runner): Loading initial job configurations from database...")
        load_scheduled_jobs_standalone(scheduler, db_config)
    except Exception as load_err:
         print(f"CRITICAL ERROR (scheduler_runner): Failed initial job loading: {load_err}")
         # return # Cân nhắc dừng lại nếu load lỗi

    # --- Thêm Job Giám Sát Trạng Thái (như cũ) ---
    try:
        scheduler.add_job(
            id='_monitor_db_config',
            func=_monitor_and_sync_job_status,
            trigger='interval',
            minutes=1, # Chạy mỗi phút
            replace_existing=True,
            jobstore='default',
            executor='default' # Chạy trong threadpool
        )
        print("INFO (scheduler_runner): Added internal job status monitor.")
    except Exception as monitor_err:
        print(f"ERROR (scheduler_runner): Failed to add monitor job: {monitor_err}")

    # --- === THÊM JOB MỚI: XỬ LÝ LỆNH === ---
    try:
        scheduler.add_job(
            id='_process_commands', # ID nội bộ
            func=_process_pending_commands, # Hàm xử lý lệnh mới
            trigger='interval',
            seconds=15, # <<< Chạy thường xuyên hơn (ví dụ: 15 giây)
            replace_existing=True,
            jobstore='default',
            executor='default' # Chạy trong threadpool (nhẹ nhàng)
        )
        print("INFO (scheduler_runner): Added internal command processor job.")
    except Exception as cmd_proc_err:
        print(f"ERROR (scheduler_runner): Failed to add command processor job: {cmd_proc_err}")


    # --- Khởi động Scheduler ---
    try:
        scheduler.start(paused=False)
        live_scheduler = scheduler # Gán vào biến toàn cục
        print("INFO (scheduler_runner): APScheduler started successfully.")
    except Exception as start_err:
        print(f"CRITICAL ERROR (scheduler_runner): Failed to start APScheduler: {start_err}")
        print(traceback.format_exc())
        live_scheduler = None



    # Lấy URL DB cho JobStore từ biến môi trường hoặc xây dựng
    db_url = os.environ.get("SQLALCHEMY_DATABASE_URI")
    if not db_url:
        db_url = f"postgresql+psycopg2://{db_config['user']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['dbname']}"

    jobstores = {
        'default': SQLAlchemyJobStore(url=db_url)
    }
    executors = {
        # Chạy monitor trong threadpool, tác vụ chính trong processpool
        'default': {'type': 'threadpool', 'max_workers': 5}, # Cho monitor và các job nhẹ
        'processpool': {'type': 'processpool', 'max_workers': 3} # Cho các job nặng như AI
    }
    job_defaults = {
        'coalesce': False,
        'max_instances': 1, # Chỉ chạy 1 instance của mỗi job cùng lúc
        'misfire_grace_time': 60 # Cho phép trễ 60s
    }

    scheduler = BackgroundScheduler(jobstores=jobstores,
                                    executors=executors,
                                    job_defaults=job_defaults,
                                    timezone='Asia/Ho_Chi_Minh') # <<< Đặt timezone phù hợp

    # --- Load jobs từ DB ---
    try:
        print("INFO (scheduler_runner): Initializing scheduler and loading jobs from database...")
        load_scheduled_jobs_standalone(scheduler, db_config)
    except Exception as load_err:
         print(f"CRITICAL ERROR (scheduler_runner): Failed during initial job loading: {load_err}")
         print(traceback.format_exc())
         # Có thể quyết định dừng lại nếu load lỗi
         # return

    # --- Thêm Job Giám Sát ---
    try:
        scheduler.add_job(
            id='_monitor_db_config', # ID nội bộ
            func=_monitor_and_sync_job_status,
            trigger='interval',
            minutes=1, # Chạy mỗi phút (hoặc 30 giây: seconds=30)
            replace_existing=True,
            jobstore='default', # Chạy trên jobstore default
            executor='default' # Chạy trong threadpool (nhẹ nhàng)
        )
        print("INFO (scheduler_runner): Added internal job status monitor.")
    except Exception as monitor_err:
        print(f"ERROR (scheduler_runner): Failed to add monitor job: {monitor_err}")


    # --- Khởi động Scheduler ---
    try:
        scheduler.start(paused=False) # Đảm bảo start không bị paused
        live_scheduler = scheduler # Gán vào biến toàn cục
        print("INFO (scheduler_runner): APScheduler started successfully.")
        # Giữ luồng chạy (không cần thiết nếu dùng daemon=True khi tạo thread)
        # while True:
        #     time.sleep(10)
    except Exception as start_err:
        print(f"CRITICAL ERROR (scheduler_runner): Failed to start APScheduler: {start_err}")
        print(traceback.format_exc())
        live_scheduler = None

# --- Main Execution (Chỉ khi chạy file này trực tiếp - dùng để test) ---
if __name__ == "__main__":
    print("INFO: Running scheduler_runner.py directly for testing...")
    run_scheduler()
    # Giữ cho script chạy để scheduler hoạt động
    try:
         while True:
              time.sleep(2)
    except (KeyboardInterrupt, SystemExit):
         if live_scheduler:
              print("INFO: Shutting down scheduler...")
              live_scheduler.shutdown()
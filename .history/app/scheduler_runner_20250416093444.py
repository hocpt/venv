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
import importlib
from apscheduler.jobstores.base import JobLookupError
# <<< Import các hàm DB và hàm tác vụ nền >>>
print("DEBUG (scheduler_runner): Attempting application imports...")
from . import database as db
from .background_tasks import run_ai_conversation_simulation, analyze_interactions_and_suggest, approve_all_suggestions_task
from . import create_app
_imports_successful = False # Mặc định là False
try:
    if db and run_ai_conversation_simulation and analyze_interactions_and_suggest and approve_all_suggestions_task and create_app:
        print("INFO (scheduler_runner): Application modules imported successfully.")
        _imports_successful = True
    else:
        print("CRITICAL ERROR (scheduler_runner): One or more imported application modules are None or invalid AFTER import attempt.")
except NameError:
     # Trường hợp một trong các tên không được định nghĩa sau import (dù không nên xảy ra nếu import thành công)
     print("CRITICAL ERROR (scheduler_runner): NameError after imports, indicates severe import failure.")

if not _imports_successful:
     print("!!! Halting further scheduler setup due to import errors. !!!")
    # Đặt các biến thành None để code sau không chạy nếu import lỗi
    db = None
    run_ai_conversation_simulation = None
    analyze_interactions_and_suggest = None
    approve_all_suggestions_task = None
    create_app = None
    _imports_successful = False
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
                # <<< SỬA CÁCH GỌI NÀY >>>
                # trigger_obj = IntervalTrigger(**converted_args) # Cách cũ dùng **
                trigger_obj = IntervalTrigger(
                    weeks=converted_args.get('weeks'),
                    days=converted_args.get('days'),
                    hours=converted_args.get('hours'),
                    minutes=converted_args.get('minutes'),
                    seconds=converted_args.get('seconds'),
                    start_date=converted_args.get('start_date'), # Vẫn lấy từ dict
                    end_date=converted_args.get('end_date'),
                    timezone=SCHEDULER_TIMEZONE, # <<< Có thể chỉ định timezone ở đây
                    jitter=converted_args.get('jitter')
            )
            # <<< KẾT THÚC SỬA >>>
            elif trigger_type == 'cron':
                # Giữ nguyên hoặc sửa tương tự nếu CronTrigger cũng lỗi
                # trigger_obj = CronTrigger(**converted_args)
                # Hoặc:
                trigger_obj = CronTrigger(
                    year=converted_args.get('year'), month=converted_args.get('month'), day=converted_args.get('day'),
                    week=converted_args.get('week'), day_of_week=converted_args.get('day_of_week'),
                    hour=converted_args.get('hour'), minute=converted_args.get('minute'), second=converted_args.get('second'),
                    start_date=converted_args.get('start_date'), end_date=converted_args.get('end_date'),
                    timezone=SCHEDULER_TIMEZONE, jitter=converted_args.get('jitter')
                )
            elif trigger_type == 'date':
                # trigger_obj = DateTrigger(**converted_args)
                # Hoặc:
                trigger_obj = DateTrigger(
                    run_date=converted_args.get('run_date'), # Tham số chính
                    timezone=SCHEDULER_TIMEZONE
                )
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
    """
    Kiểm tra bảng scheduler_commands và thực thi các lệnh đang chờ
    (run_simulation, run_suggestion_job_now, cancel_job, approve_all_suggestions).
    """
    global live_scheduler
    # Kiểm tra các điều kiện cần thiết để chạy
    if not live_scheduler or not live_scheduler.running:
        # print("DEBUG (Command Processor): Scheduler not running.")
        return
    if not db:
        print("ERROR (Command Processor): DB module missing.")
        return

    # Lấy các hàm tác vụ một cách an toàn hơn
    run_sim_func = globals().get('run_ai_conversation_simulation')
    suggest_func = globals().get('analyze_interactions_and_suggest')
    approve_all_func = globals().get('approve_all_suggestions_task')

    print(f"DEBUG (Command Processor): Checking for pending commands...")
    conn = None
    processed_count = 0 # Đếm số lệnh đã xử lý trong lần chạy này

    try:
        conn = db.get_db_connection()
        if not conn:
            print("ERROR (Command Processor): Cannot get DB connection for command processing.")
            return
        conn.autocommit = False # Bắt đầu Transaction

        # Lấy các loại lệnh đang chờ (pending)
        # Tăng giới hạn một chút để đảm bảo xử lý kịp thời
        pending_sim = db.get_pending_commands(command_type='run_simulation', limit=10) or []
        pending_run_suggest = db.get_pending_commands(command_type='run_suggestion_job_now', limit=5) or []
        pending_approve_all = db.get_pending_commands(command_type='approve_all_suggestions', limit=5) or []
        pending_cancel = db.get_pending_commands(command_type='cancel_job', limit=10) or []

        # Ưu tiên xử lý lệnh cancel trước? (Tùy chọn)
        all_pending = pending_cancel + pending_sim + pending_run_suggest + pending_approve_all

        if not all_pending:
            conn.commit() # Commit để giải phóng lock (nếu có)
            if conn: conn.close()
            return

        print(f"INFO (Command Processor): Found {len(all_pending)} pending command(s).")

        for command in all_pending:
            command_id = command['command_id']
            command_type = command['command_type']
            payload = command['payload'] # Đã là dict
            print(f"DEBUG (Cmd Proc): Processing command ID: {command_id}, Type: {command_type}")

            # 1. Đánh dấu processing (quan trọng)
            updated_processing = db.update_command_status(conn, command_id, 'processing')
            if not updated_processing:
                print(f"WARN (Cmd Proc): Skip cmd {command_id}, cannot mark processing.")
                continue # Bỏ qua nếu không đánh dấu được

            try:
                # --- Phân loại và Xử lý Lệnh ---

                # --- LỆNH HỦY JOB ---
                if command_type == 'cancel_job':
                    job_id_to_cancel = payload.get('job_id_to_cancel')
                    if not job_id_to_cancel:
                        raise ValueError("Missing 'job_id_to_cancel' in payload for cancel_job.")

                    print(f"DEBUG (Cmd Proc): Attempting to remove job ID: {job_id_to_cancel}")
                    try:
                        live_scheduler.remove_job(job_id_to_cancel, jobstore='default')
                        print(f"INFO (Cmd Proc): Successfully removed job '{job_id_to_cancel}'.")
                        db.update_command_status(conn, command_id, 'done')
                    except JobLookupError:
                        print(f"WARN (Cmd Proc): Job '{job_id_to_cancel}' not found for cancellation. Marking command done.")
                        db.update_command_status(conn, command_id, 'done')
                    # Các lỗi khác khi remove_job sẽ bị bắt bởi khối except bên ngoài

                # --- LỆNH CHẠY MÔ PHỎNG ---
                elif command_type == 'run_simulation':
                    if not run_sim_func: raise ImportError("run_ai_conversation_simulation function not available")
                    params = payload
                    # Trích xuất args
                    persona_a_id = params.get('persona_a_id'); persona_b_id = params.get('persona_b_id')
                    strategy_id = params.get('strategy_id'); max_turns = int(params.get('max_turns', 5))
                    starting_prompt = params.get('starting_prompt') or "Xin chào!"
                    log_account_id_a = params.get('log_account_id_a'); log_account_id_b = params.get('log_account_id_b')
                    sim_thread_id_base = params.get('sim_thread_id_base') or f"sim_{log_account_id_a[:5]}_vs_{log_account_id_b[:5]}"
                    sim_goal = params.get('sim_goal') or "simulation"
                    if not all([persona_a_id, persona_b_id, strategy_id, log_account_id_a, log_account_id_b]):
                        raise ValueError("Missing required params for simulation payload")

                    # <<< SỬA DÒNG TẠO JOB_ID >>>
                    job_id = f"sim_run_{command_id}_{uuid.uuid4().hex[:8]}" # Chèn command_id vào đây

                    job_args = (persona_a_id, persona_b_id, strategy_id, max_turns, starting_prompt,
                                log_account_id_a, log_account_id_b, sim_thread_id_base, sim_goal)
                    run_time = datetime.now(SCHEDULER_TIMEZONE) + timedelta(seconds=2)

                    # <<< TẠO JOB NAME MÔ TẢ >>>
                    job_name_display = f"SimCmd{command_id}: {persona_a_id} vs {persona_b_id} ({strategy_id})"

                    print(f"DEBUG (Cmd Proc): Scheduling job '{job_id}' Name='{job_name_display}'")

                    live_scheduler.add_job(id=job_id, func=run_sim_func, args=job_args, trigger='date', run_date=run_time,
                                           jobstore='default', executor='processpool', replace_existing=False, misfire_grace_time=120,
                                           name=job_name_display) # <<< THÊM THAM SỐ name >>>
                    db.update_command_status(conn, command_id, 'done')
                    print(f"INFO (Cmd Proc): Scheduled job '{job_id}' for cmd {command_id}.")
                    processed_count += 1
                # --- LỆNH CHẠY JOB ĐỀ XUẤT NGAY ---
                elif command_type == 'run_suggestion_job_now':
                     if not suggest_func: raise ImportError("analyze_interactions_and_suggest function not available")
                     job_id = f"manual_suggestion_run_{uuid.uuid4().hex[:8]}"
                     run_time = datetime.now(SCHEDULER_TIMEZONE) + timedelta(seconds=1)
                     live_scheduler.add_job(id=job_id, func=suggest_func, args=(), trigger='date', run_date=run_time,
                                            jobstore='default', executor='processpool', replace_existing=False, misfire_grace_time=120,
                                            name="Manual Suggestion Run")
                     db.update_command_status(conn, command_id, 'done')
                     print(f"INFO (Cmd Proc): Scheduled job '{job_id}' for cmd {command_id}.")

                # --- LỆNH DUYỆT TẤT CẢ ĐỀ XUẤT ---
                elif command_type == 'approve_all_suggestions':
                     if not approve_all_func: raise ImportError("approve_all_suggestions_task function not available")
                     job_id = f"approve_all_run_{uuid.uuid4().hex[:8]}"
                     run_time = datetime.now(SCHEDULER_TIMEZONE) + timedelta(seconds=1)
                     live_scheduler.add_job(id=job_id, func=approve_all_func, args=(), trigger='date', run_date=run_time,
                                            jobstore='default', executor='default', # Có thể dùng threadpool cho tác vụ này?
                                            replace_existing=False, misfire_grace_time=300,
                                            name="Bulk Approve Suggestions")
                     db.update_command_status(conn, command_id, 'done')
                     print(f"INFO (Cmd Proc): Scheduled job '{job_id}' for cmd {command_id}.")

                # --- CÁC LOẠI LỆNH KHÁC ---
                else:
                    # Nếu có loại lệnh không xác định, ghi lỗi và đánh dấu error
                    raise ValueError(f"Unknown command_type encountered: {command_type}")

                # Nếu xử lý thành công (không raise exception)
                processed_count += 1

            except Exception as processing_err:
                # Xử lý lỗi khi parse payload, kiểm tra tham số, hoặc thêm/xóa job
                error_msg = f"Error processing command {command_id} ({command_type}): {type(processing_err).__name__} - {processing_err}"
                print(error_msg)
                # print(traceback.format_exc()) # Bỏ comment nếu cần debug sâu
                # Cập nhật status thành 'error' và lưu lỗi
                db.update_command_status(conn, command_id, 'error', error_message=str(processing_err)[:500])
                # Không rollback ở đây, tiếp tục xử lý các lệnh khác nếu có

        # Commit tất cả các thay đổi status thành công hoặc lỗi sau khi xử lý xong batch
        conn.commit()
        if processed_count > 0:
             print(f"DEBUG (Command Processor): Finished processing batch. Updated status for {processed_count} command(s).")

    except psycopg2.Error as db_conn_err: # Lỗi kết nối hoặc transaction lớn
         print(f"ERROR (Command Processor): Database connection/transaction error: {db_conn_err}")
         if conn: conn.rollback() # Rollback nếu lỗi transaction
    except Exception as e: # Lỗi không mong muốn khác
        print(f"ERROR (Command Processor): Unexpected error in command processor loop: {e}")
        print(traceback.format_exc())
        if conn: conn.rollback() # Rollback nếu lỗi không rõ
    finally:
    # <<< THAY THẾ KHỐI FINALLY NÀY >>>
        if conn: # Chỉ thực hiện nếu conn đã được tạo
            try:
                # Kiểm tra xem kết nối có bị đóng chưa
                if not conn.closed:
                    # Nếu chưa đóng, thì đóng nó đi
                    conn.close()
                    # print("DEBUG (Command Processor): DB Connection closed in finally.")
                # else: # Nếu đã đóng rồi thì không cần làm gì
                    # print("DEBUG (Command Processor): DB Connection was already closed before finally.")
            except psycopg2.Error as close_err:
                # Bắt lỗi có thể xảy ra khi kiểm tra conn.closed hoặc conn.close()
                print(f"ERROR (Command Processor): Error during connection cleanup in finally: {close_err}")
            except Exception as general_close_err:
                print(f"ERROR (Command Processor): Unexpected error during connection cleanup in finally: {general_close_err}")
        # <<< KẾT THÚC THAY THẾ KHỐI FINALLY >>>
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


print("DEBUG: app/database.py - Module loaded completely.")
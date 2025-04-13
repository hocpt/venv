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
# <<< Import các hàm DB và hàm tác vụ nền >>>
try:
    # Giả định database.py và background_tasks.py cùng cấp với scheduler_runner.py trong thư mục app
    from . import database as db
    from .background_tasks import run_ai_conversation_simulation
except ImportError:
    # Fallback nếu cấu trúc khác (ít xảy ra nếu chạy từ run.py)
    try:
        import database as db
        from background_tasks import run_ai_conversation_simulation
        print("WARNING (scheduler_runner): Using fallback imports for db and background_tasks.")
    except ImportError as imp_err:
         print(f"CRITICAL ERROR (scheduler_runner): Cannot import database or background_tasks: {imp_err}")
         db = None
         run_ai_conversation_simulation = None
         create_app = None
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

# --- === HÀM MỚI: XỬ LÝ LỆNH TỪ DATABASE === ---
def _process_pending_commands():
    """
    Kiểm tra bảng scheduler_commands và thực thi các lệnh đang chờ,
    ví dụ như lên lịch chạy mô phỏng AI.
    """
    global live_scheduler
    if not live_scheduler or not live_scheduler.running:
        # print("DEBUG (Command Processor): Scheduler not running.")
        return
    if not db or not run_ai_conversation_simulation:
        print("ERROR (Command Processor): DB module or simulation function not available.")
        return

    print(f"DEBUG (Command Processor): Checking for pending commands... ({datetime.now(SCHEDULER_TIMEZONE).strftime('%H:%M:%S')})")
    commands_to_process = []
    conn = None # Khởi tạo connection bên ngoài try

    try:
        # Sử dụng transaction để đảm bảo tính nhất quán
        conn = db.get_db_connection()
        if not conn:
             print("ERROR (Command Processor): Cannot get DB connection.")
             return
        conn.autocommit = False # Bắt đầu transaction

        # Lấy các lệnh đang chờ (hàm get_pending_commands dùng FOR UPDATE SKIP LOCKED)
        # Giới hạn số lệnh xử lý mỗi lần để tránh quá tải
        pending_commands = db.get_pending_commands(command_type='run_simulation', limit=5) # <<< Giới hạn 5 lệnh/lần

        if not pending_commands:
            # print("DEBUG (Command Processor): No pending 'run_simulation' commands found.")
            conn.commit() # Commit để giải phóng lock (nếu có)
            return

        print(f"INFO (Command Processor): Found {len(pending_commands)} pending 'run_simulation' command(s).")

        for command in pending_commands:
            command_id = command['command_id']
            # payload_str = command['payload'] # <<< Lấy payload gốc (đã là dict)
            print(f"DEBUG (Command Processor): Processing command ID: {command_id}")

            # 1. Đánh dấu là đang xử lý (giữ nguyên)
            updated_processing = db.update_command_status(conn, command_id, 'processing')
            if not updated_processing:
                print(f"WARNING (Command Processor): Could not mark command {command_id} as processing. Skipping.")
                continue

            try:
                # 2. Parse Payload và chuẩn bị Args
                # <<< THAY ĐỔI CHÍNH: BỎ json.loads, DÙNG TRỰC TIẾP payload >>>
                # params = json.loads(payload_str) # <<< BỎ DÒNG NÀY
                params = command['payload'] # <<< DÙNG TRỰC TIẾP DICT TỪ DB
                # <<< KẾT THÚC THAY ĐỔI CHÍNH >>>

                if not isinstance(params, dict): # Thêm kiểm tra phòng ngừa
                    raise TypeError(f"Payload for command {command_id} is not a dictionary.")

                # Trích xuất các tham số cần thiết (giữ nguyên)
                persona_a_id = params.get('persona_a_id')
                persona_b_id = params.get('persona_b_id')
                strategy_id = params.get('strategy_id')
                max_turns = int(params.get('max_turns', 5))
                starting_prompt = params.get('starting_prompt') or "Xin chào!"
                sim_account_id = params.get('sim_account_id') or f"sim_{command_id}"
                sim_thread_id_base = params.get('sim_thread_id_base') or f"sim_{command_id}"
                sim_goal = params.get('sim_goal') or "simulation"
                log_account_id_a = params.get('log_account_id_a') # <<< Lấy ID log A
                log_account_id_b = params.get('log_account_id_b') # <<< Lấy ID log B
                sim_thread_id_base = params.get('sim_thread_id_base') or f"sim_{log_account_id_a[:5]}_vs_{log_account_id_b[:5]}" # <<< Tạo thread base từ ID log
                
                # Validate (giữ nguyên)
                if not all([persona_a_id, persona_b_id, strategy_id]):
                    raise ValueError("Missing required parameters in payload")

                # Chuẩn bị Job (giữ nguyên)
                job_id = f"sim_run_{sim_thread_id_base}_{uuid.uuid4().hex[:8]}"
                job_args = (
                persona_a_id,           # 1
                persona_b_id,           # 2
                strategy_id,            # 3
                max_turns,              # 4
                starting_prompt,        # 5
                log_account_id_a,       # 6
                log_account_id_b,       # 7
                sim_thread_id_base,     # 8
                sim_goal                # 9 <<< Bây giờ biến này đã tồn tại
            )
                run_time = datetime.now(SCHEDULER_TIMEZONE) + timedelta(seconds=2)

                print(f"DEBUG (Command Processor): Scheduling job '{job_id}' with args: {job_args}")
                print(f"DEBUG (Command Processor): Final job_args for add_job = {job_args}")

                # 3. Thêm Job vào Scheduler (giữ nguyên)
                live_scheduler.add_job(
                    id=job_id,
                    func=run_ai_conversation_simulation,
                    args=job_args,
                    trigger='date', run_date=run_time,
                    jobstore='default', executor='processpool',
                    replace_existing=False, misfire_grace_time=120
                )

                # 4. Cập nhật Status thành Done (giữ nguyên)
                db.update_command_status(conn, command_id, 'done')
                print(f"INFO (Command Processor): Successfully scheduled job for command {command_id}")

            except Exception as processing_err:
                # 5. Xử lý lỗi (giữ nguyên)
                error_msg = f"Error processing command {command_id}: {type(processing_err).__name__} - {processing_err}"
                print(error_msg)
                db.update_command_status(conn, command_id, 'error', error_message=str(processing_err)[:500])

        # Commit tất cả các thay đổi status sau khi xử lý xong batch
        conn.commit()
        print(f"DEBUG (Command Processor): Finished processing batch.")

    except psycopg2.Error as db_conn_err:
         print(f"ERROR (Command Processor): Database connection/transaction error: {db_conn_err}")
         if conn: conn.rollback() # Rollback nếu lỗi transaction
    except Exception as e:
        print(f"ERROR (Command Processor): Unexpected error: {e}")
        print(traceback.format_exc())
        if conn: conn.rollback() # Rollback nếu lỗi không rõ
    finally:
        if conn:
             conn.autocommit = True # Trả về trạng thái autocommit mặc định
             conn.close()
             # print("DEBUG (Command Processor): DB Connection closed.")
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
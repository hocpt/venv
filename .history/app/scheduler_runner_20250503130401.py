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
import atexit
from apscheduler.jobstores.base import JobLookupError
# <<< Import các hàm DB và hàm tác vụ nền >>>
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
# Import các hàm tác vụ nền
from app.background_tasks import (
    # analyze_interactions_and_suggest, # Giữ lại job cũ nếu cần
    # run_ai_conversation_simulation,
    analyze_logs_and_update_map # Thêm job mới
)
try:
    # ... (các import hiện có) ...
    # THÊM IMPORT HÀM TASK MỚI
    from app.background_tasks import build_app_map_task
    print("INFO (scheduler_runner): Imported build_app_map_task successfully.")
except ImportError as e:
    print(f"CRITICAL ERROR (scheduler_runner): Failed import build_app_map_task: {e}.")
    build_app_map_task = None


print("DEBUG (scheduler_runner): Attempting application imports...")
try:
    from flask import Flask, current_app  # Vẫn cần nếu dùng current_app
    from app import create_app  # Import trực tiếp từ package 'app'
    from app import database as db # <<< SỬA Ở ĐÂY: Import tuyệt đối
    from app import ai_service # Import tuyệt đối
    from app.background_tasks import run_ai_conversation_simulation, analyze_interactions_and_suggest, approve_all_suggestions_task # Import tuyệt đối

    print("INFO (scheduler_runner): Application modules imported successfully via absolute paths.")
    _imports_successful_bgt = True
except ImportError as e:
    print(f"CRITICAL ERROR (scheduler_runner): Failed to import dependencies via absolute path: {e}.")
    print("Check project structure, __init__.py files, and ensure modules exist at 'app.*'.")
    print(traceback.format_exc()) # In traceback chi tiết
    # Đặt các biến thành None nếu import lỗi
    db = None
    ai_service = None
    create_app = None
    current_app = None
    run_ai_conversation_simulation = None
    analyze_interactions_and_suggest = None
    approve_all_suggestions_task = None
    _imports_successful_bgt = False
# Biến toàn cục giữ instance scheduler đang chạy
scheduler = BackgroundScheduler(daemon=True)
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
    """
    Tải cấu hình jobs từ CSDL và thêm/cập nhật chúng vào scheduler.
    Đã sửa lỗi trigger args và thêm xử lý job_args (kwargs).
    """
    # Sử dụng print hoặc logger tùy cấu hình của bạn
    print("INFO (scheduler_runner): Starting to load scheduled jobs from DB (standalone)...")
    conn = None
    cur = None
    job_configs = []

    # 1. Kết nối CSDL và lấy cấu hình jobs (bao gồm cả job_args)
    try:
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor) # Dùng DictCursor
        print(f"DEBUG (scheduler_runner): Connected to DB to fetch jobs.")
        # Lấy đủ các cột cần thiết
        # <<< ĐẢM BẢO CÓ CỘT job_args TRONG SELECT >>>
        cur.execute("""
            SELECT job_id, job_function_path, trigger_type, trigger_args, job_args, is_enabled, description
            FROM public.scheduled_jobs ORDER BY job_id;
        """)
        rows = cur.fetchall()
        job_configs = [dict(row) for row in rows] if rows else []
        print(f"DEBUG (scheduler_runner): Found {len(job_configs)} job configs in DB.")

    except psycopg2.Error as db_err:
        print(f"ERROR (scheduler_runner): Failed to connect or query scheduled_jobs table: {db_err}")
        print(traceback.format_exc())
        return # Thoát nếu lỗi DB
    except Exception as e:
        print(f"ERROR (scheduler_runner): Unexpected error fetching jobs from DB: {e}")
        print(traceback.format_exc())
        return # Thoát nếu lỗi khác
    finally:
        if cur: cur.close()
        if conn: conn.close()
        print(f"DEBUG (scheduler_runner): Closed direct DB connection after fetching jobs.")

    # 2. Xử lý và thêm jobs vào scheduler
    added_count = 0
    if not job_configs:
        print("INFO (scheduler_runner): No job configurations found in DB to load.")
        return

    for job_config in job_configs:
        job_id = job_config.get('job_id')
        is_enabled = job_config.get('is_enabled', False)
        function_path = job_config.get('job_function_path')
        trigger_type = job_config.get('trigger_type')
        trigger_args_dict = job_config.get('trigger_args', {}) # Đã là dict
        # === LẤY VÀ XỬ LÝ job_args MỘT CÁCH AN TOÀN ===
        job_args_dict = job_config.get('job_args') # Lấy từ kết quả DictCursor
        if job_args_dict is None:
            job_args_dict = {} # Đảm bảo là dict rỗng nếu null
        elif not isinstance(job_args_dict, dict): # Xử lý nếu không phải dict (ví dụ: chuỗi JSON cũ)
             print(f"WARNING (scheduler_runner): job_args for job '{job_id}' is not a dict ({type(job_args_dict)}). Attempting to parse.")
             if isinstance(job_args_dict, str):
                 try:
                     parsed = json.loads(job_args_dict)
                     job_args_dict = parsed if isinstance(parsed, dict) else {}
                 except json.JSONDecodeError: job_args_dict = {}
             else: job_args_dict = {} # Reset về rỗng nếu kiểu lạ
        # ============================================

        print(f"DEBUG (scheduler_runner): Processing job config: ID='{job_id}', Enabled={is_enabled}, Path='{function_path}', Trigger='{trigger_type}', T_Args={trigger_args_dict}, J_Args={job_args_dict}")

        if not job_id or not function_path or not trigger_type or trigger_args_dict is None:
            print(f"WARNING (scheduler_runner): Skipping invalid job config (missing required fields): {job_config}")
            continue

        # Xử lý job bị disable
        if not is_enabled:
            print(f"INFO (scheduler_runner): Job '{job_id}' is disabled in config.")
            try:
                existing_job = scheduler.get_job(job_id, jobstore='default')
                if existing_job:
                    scheduler.remove_job(job_id, jobstore='default')
                    print(f"INFO (scheduler_runner): Removed disabled job '{job_id}' from scheduler during load.")
            except JobLookupError: pass
            except Exception as e_remove: print(f"ERROR (scheduler_runner): Failed check/remove disabled job '{job_id}': {e_remove}")
            continue

        # Chỉ xử lý các job được enable
        try:
            # Import function
            module_path, func_name = function_path.rsplit('.', 1)
            module = importlib.import_module(module_path)
            func = getattr(module, func_name)

            # Tạo Trigger Object (Đã sửa lỗi NoneType)
            trigger_obj = None
            converted_trigger_args = trigger_args_dict.copy()
            numeric_keys_trigger = ['weeks', 'days', 'hours', 'minutes', 'seconds', 'jitter', 'year', 'month', 'day', 'week', 'hour', 'minute', 'second']
            for key in numeric_keys_trigger:
                if key in converted_trigger_args and isinstance(converted_trigger_args[key], str):
                    value_str = converted_trigger_args[key].strip()
                    if not value_str: del converted_trigger_args[key]; continue
                    try:
                        if '.' in value_str or 'e' in value_str.lower(): converted_trigger_args[key] = float(value_str)
                        else: converted_trigger_args[key] = int(value_str)
                    except (ValueError, TypeError): raise ValueError(f"Invalid numeric value for trigger arg '{key}': '{value_str}'")

            if trigger_type == 'interval':
                trigger_obj = IntervalTrigger(
                    weeks=converted_trigger_args.get('weeks', 0), days=converted_trigger_args.get('days', 0),
                    hours=converted_trigger_args.get('hours', 0), minutes=converted_trigger_args.get('minutes', 0),
                    seconds=converted_trigger_args.get('seconds', 0), start_date=converted_trigger_args.get('start_date'),
                    end_date=converted_trigger_args.get('end_date'), timezone=SCHEDULER_TIMEZONE,
                    jitter=converted_trigger_args.get('jitter')
                )
            elif trigger_type == 'cron':
                 trigger_obj = CronTrigger(
                    year=converted_trigger_args.get('year'), month=converted_trigger_args.get('month'), day=converted_trigger_args.get('day'),
                    week=converted_trigger_args.get('week'), day_of_week=converted_trigger_args.get('day_of_week'),
                    hour=converted_trigger_args.get('hour', 0), minute=converted_trigger_args.get('minute', 0),
                    second=converted_trigger_args.get('second', 0), start_date=converted_trigger_args.get('start_date'),
                    end_date=converted_trigger_args.get('end_date'), timezone=SCHEDULER_TIMEZONE,
                    jitter=converted_trigger_args.get('jitter')
                )
            elif trigger_type == 'date':
                 trigger_obj = DateTrigger(run_date=converted_trigger_args.get('run_date'), timezone=SCHEDULER_TIMEZONE)
            else:
                raise ValueError(f"Unsupported trigger type: {trigger_type}")

            # === Gọi scheduler.add_job VỚI KWARGS ===
            print(f"DEBUG (scheduler_runner): Adding job '{job_id}' with function '{func.__name__}', trigger '{trigger_type}', kwargs: {job_args_dict}")
            scheduler.add_job(
                id=job_id,
                func=func,
                trigger=trigger_obj,
                kwargs=job_args_dict,  # <<< TRUYỀN THAM SỐ CHO HÀM JOB TẠI ĐÂY
                replace_existing=True, # Cập nhật job nếu ID đã tồn tại
                misfire_grace_time=job_config.get('misfire_grace_time', 60),
                max_instances=job_config.get('max_instances', 1),
                name=job_config.get('description', job_id) # Dùng description làm tên job
            )
            # =======================================
            print(f"SUCCESS (scheduler_runner): Added/Updated job '{job_id}' in scheduler.")
            added_count += 1

        except (ValueError, ImportError, AttributeError) as config_err:
            # Lỗi cấu hình không hợp lệ
            print(f"ERROR (scheduler_runner): Invalid config for job '{job_id}': {config_err}")
        except TypeError as type_err:
            # Lỗi kiểu dữ liệu khi gọi add_job (thường do kwargs/trigger args sai)
            print(f"ERROR (scheduler_runner): TypeError adding job '{job_id}'. Args mismatch? Trigger={trigger_args_dict}, JobArgs={job_args_dict}. Error: {type_err}")
        except Exception as add_job_err:
            # Các lỗi khác khi thêm job
            print(f"ERROR (scheduler_runner): Failed to add/update job '{job_id}' to scheduler: {add_job_err}")
            print(traceback.format_exc()) # In traceback để debug

    print(f"INFO (scheduler_runner): Finished loading jobs from DB. Added/Updated {added_count} enabled jobs.")
# =============================================================

def _process_pending_commands():
    """
    Kiểm tra bảng scheduler_commands và thực thi các lệnh đang chờ.
    """
    global live_scheduler

    # 1. Kiểm tra các điều kiện cần thiết
    if not live_scheduler or not live_scheduler.running:
        return
    if not db:
        print("ERROR (Command Processor): Database module (db) not available.")
        return

    # Lấy các hàm tác vụ (giữ nguyên)
    run_sim_func = globals().get('run_ai_conversation_simulation')
    suggest_func = globals().get('analyze_interactions_and_suggest')
    approve_all_func = globals().get('approve_all_suggestions_task')
    build_map_func = globals().get('build_app_map_task')

    conn = None
    processed_count = 0

    try:
        # 2. Lấy kết nối CSDL (cho việc update status và commit/rollback)
        conn = db.get_db_connection()
        if not conn:
            print("ERROR (Command Processor): Cannot get DB connection.")
            return
        conn.autocommit = False # Bắt đầu Transaction

        # 3. Lấy các lệnh đang chờ xử lý (pending)
        # === SỬA LỖI: BỎ conn=conn KHỎI CÁC LẦN GỌI get_pending_commands ===
        pending_sim = db.get_pending_commands(command_type='run_simulation', limit=10) or []
        pending_run_suggest = db.get_pending_commands(command_type='run_suggestion_job_now', limit=5) or []
        pending_approve_all = db.get_pending_commands(command_type='approve_all_suggestions', limit=5) or []
        pending_cancel = db.get_pending_commands(command_type='cancel_job', limit=10) or []
        pending_build_map = db.get_pending_commands(command_type='build_map', limit=20) or []
        # =====================================================================

        # Gom tất cả lại
        all_pending = pending_cancel + pending_sim + pending_run_suggest + pending_approve_all + pending_build_map

        if not all_pending:
            conn.commit() # Commit nếu không có gì để làm
            if conn: conn.close()
            return

        print(f"INFO (Command Processor): Found {len(all_pending)} pending command(s).")

        # 4. Lặp qua từng lệnh và xử lý
        for command in all_pending:
            command_id = command.get('command_id')
            command_type = command.get('command_type')
            payload = command.get('payload')

            if not command_id or not command_type:
                 print(f"WARN (Cmd Proc): Skipping invalid command data: {command}")
                 continue

            print(f"DEBUG (Cmd Proc): Processing command ID: {command_id}, Type: {command_type}")

            # 4a. Đánh dấu 'processing' (DÙNG connection chính của hàm này)
            updated_processing = db.update_command_status(conn, command_id, 'processing')
            if not updated_processing:
                print(f"WARN (Cmd Proc): Could not mark command {command_id} as processing. Skipping.")
                continue

            # 4b. Khối try/except xử lý từng lệnh (giữ nguyên logic bên trong như cũ)
            try:
                if command_type == 'cancel_job':
                    job_id_to_cancel = payload.get('job_id_to_cancel')
                    if not job_id_to_cancel: raise ValueError("Missing 'job_id_to_cancel'")
                    print(f"DEBUG (Cmd Proc): Attempting remove job ID: {job_id_to_cancel}")
                    try:
                        live_scheduler.remove_job(job_id_to_cancel, jobstore='default')
                        print(f"INFO (Cmd Proc): Successfully removed job '{job_id_to_cancel}'")
                        db.update_command_status(conn, command_id, 'done')
                    except JobLookupError:
                        print(f"WARN (Cmd Proc): Job '{job_id_to_cancel}' not found. Marking done.")
                        db.update_command_status(conn, command_id, 'done')

                elif command_type == 'run_simulation':
                    if not run_sim_func: raise ImportError("run_sim_func not available")
                    # ... (code trích xuất params và add_job như cũ) ...
                    params = payload
                    persona_a_id=params.get('persona_a_id'); persona_b_id=params.get('persona_b_id')
                    strategy_id=params.get('strategy_id'); max_turns=int(params.get('max_turns', 5))
                    starting_prompt=params.get('starting_prompt') or "Xin chào!"
                    log_account_id_a=params.get('log_account_id_a'); log_account_id_b=params.get('log_account_id_b')
                    sim_thread_id_base=params.get('sim_thread_id_base') or f"sim_{log_account_id_a[:5]}_vs_{log_account_id_b[:5]}"
                    sim_goal=params.get('sim_goal') or "adhoc_simulation"
                    if not all([persona_a_id, persona_b_id, strategy_id, log_account_id_a, log_account_id_b]):
                         raise ValueError("Missing required simulation params")
                    job_id = f"sim_run_{command_id}_{uuid.uuid4().hex[:8]}"
                    job_name_display = f"SimCmd{command_id}: {persona_a_id} vs {persona_b_id}"
                    run_time = datetime.now(SCHEDULER_TIMEZONE) + timedelta(seconds=2)
                    job_args = (persona_a_id, persona_b_id, strategy_id, max_turns, starting_prompt,
                                log_account_id_a, log_account_id_b, sim_thread_id_base, sim_goal)
                    live_scheduler.add_job(id=job_id, func=run_sim_func, args=job_args, trigger='date', run_date=run_time,
                                          jobstore='default', executor='processpool', replace_existing=False, misfire_grace_time=120,
                                          name=job_name_display)
                    db.update_command_status(conn, command_id, 'done')
                    print(f"INFO (Cmd Proc): Scheduled job '{job_id}' for sim cmd {command_id}.")


                elif command_type == 'run_suggestion_job_now':
                    if not suggest_func: raise ImportError("suggest_func not available")
                    # ... (code add_job như cũ) ...
                    job_id = f"manual_suggestion_run_{uuid.uuid4().hex[:8]}"
                    run_time = datetime.now(SCHEDULER_TIMEZONE) + timedelta(seconds=1)
                    live_scheduler.add_job(id=job_id, func=suggest_func, args=(), trigger='date', run_date=run_time,
                                            jobstore='default', executor='processpool', replace_existing=False, misfire_grace_time=120,
                                            name="Manual Suggestion Run")
                    db.update_command_status(conn, command_id, 'done')
                    print(f"INFO (Cmd Proc): Scheduled job '{job_id}' for suggestion cmd {command_id}.")

                elif command_type == 'approve_all_suggestions':
                    if not approve_all_func: raise ImportError("approve_all_func not available")
                    # ... (code add_job như cũ) ...
                    job_id = f"approve_all_run_{uuid.uuid4().hex[:8]}"
                    run_time = datetime.now(SCHEDULER_TIMEZONE) + timedelta(seconds=1)
                    live_scheduler.add_job(id=job_id, func=approve_all_func, args=(), trigger='date', run_date=run_time,
                                           jobstore='default', executor='default',
                                           replace_existing=False, misfire_grace_time=300,
                                           name="Bulk Approve Suggestions")
                    db.update_command_status(conn, command_id, 'done')
                    print(f"INFO (Cmd Proc): Scheduled job '{job_id}' for bulk approve cmd {command_id}.")

                elif command_type == 'build_map': # <<< Xử lý lệnh mới
                    if not build_map_func: raise ImportError("build_map_func not available.")
                    if not payload: raise ValueError("Missing payload for build_map command.")
                    try:
                        build_map_func(payload) # Gọi hàm task trực tiếp
                        db.update_command_status(conn, command_id, 'done') # Đánh dấu done nếu thành công
                        print(f"INFO (Cmd Proc): Executed build_map task for cmd {command_id}.")
                    except Exception as map_task_error:
                        error_msg_map = f"Error during build_map task execution: {map_task_error}"
                        print(f"ERROR (Cmd Proc): {error_msg_map}")
                        db.update_command_status(conn, command_id, 'error', error_message=str(map_task_error)[:500])
                        # Không raise lại lỗi, để vòng lặp tiếp tục

                else:
                    raise ValueError(f"Unknown command_type: {command_type}")

                processed_count += 1

            except Exception as processing_err:
                # Bắt lỗi khi xử lý MỘT lệnh (validate payload, lỗi add/remove job,...)
                error_message = f"Error processing command {command_id} ({command_type}): {type(processing_err).__name__} - {processing_err}"
                print(error_message)
                traceback.print_exc()
                # Cập nhật status thành 'error' dùng connection chính
                db.update_command_status(conn, command_id, 'error', error_message=str(processing_err)[:500])

        # 5. Commit Transaction sau khi xử lý hết batch
        conn.commit()
        if processed_count > 0:
             print(f"DEBUG (Command Processor): Finished batch. Committed status updates for {processed_count} command(s).")

    except psycopg2.Error as db_conn_err:
         print(f"ERROR (Command Processor): Database connection/transaction error: {db_conn_err}")
         if conn: conn.rollback()
         traceback.print_exc()
    except Exception as loop_err:
        print(f"ERROR (Command Processor): Unexpected error in command processor loop: {loop_err}")
        print(traceback.format_exc())
        if conn: conn.rollback()
    finally:
        # 6. Luôn đóng kết nối CSDL
        if conn:
            try:
                if not conn.closed:
                    conn.close()
            except Exception as close_err:
                print(f"ERROR (Command Processor): Error during connection cleanup: {close_err}")
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

def start_scheduler():
    global scheduler
    print("Starting scheduler...")

    # --- Xóa hoặc sửa đổi job cũ liên quan đến map (nếu có) ---
    # Ví dụ: nếu có job 'build_app_map_task' thì xóa hoặc thay thế
    # try:
    #     scheduler.remove_job('build_app_map_task_job')
    # except:
    #     pass

    # --- Đăng ký job mới ---
    scheduler.add_job(
        func=analyze_logs_and_update_map,
        trigger=IntervalTrigger(seconds=60), # Chạy mỗi 60 giây (hoặc tùy chỉnh)
        id='analyze_map_logs_job',
        name='Analyze exploration logs and update app map',
        replace_existing=True
    )

    # --- Giữ lại các job khác nếu cần ---
    # scheduler.add_job(...)

    scheduler.start()
    print("Scheduler started.")

    # Keep the main thread alive for the scheduler to run
    # Hoặc nếu chạy trong Flask/Waitress, không cần vòng lặp này
    # try:
    #     while True:
    #         time.sleep(2)
    # except (KeyboardInterrupt, SystemExit):
    #     scheduler.shutdown()

def shutdown_scheduler():
    global scheduler
    if scheduler.running:
        print("Shutting down scheduler...")
        scheduler.shutdown()
        print("Scheduler shut down.")

    # Ensure scheduler is shutdown when the application exits
    atexit.register(shutdown_scheduler)




print("DEBUG: app/database.py - Module loaded completely.")



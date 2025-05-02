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
    Hàm này chạy độc lập khi scheduler khởi động.
    Đã sửa lỗi trigger args và thêm xử lý job_args (kwargs).
    """
    print("INFO (scheduler_runner): Starting to load scheduled jobs from DB (standalone)...") # Hoặc dùng logger
    conn = None
    cur = None
    job_configs = []

    # 1. Kết nối CSDL và lấy cấu hình jobs (bao gồm cả job_args)
    try:
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor) # Dùng DictCursor
        print(f"DEBUG (scheduler_runner): Connected to DB to fetch jobs.")
        # <<< Đảm bảo SELECT có cột job_args >>>
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
        return
    except Exception as e:
        print(f"ERROR (scheduler_runner): Unexpected error fetching jobs from DB: {e}")
        print(traceback.format_exc())
        return
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
        trigger_args_dict = job_config.get('trigger_args', {}) # Là dict từ JSONB
        # === LẤY VÀ XỬ LÝ job_args ===
        job_args_dict = job_config.get('job_args') # DictCursor thường tự parse JSONB
        if job_args_dict is None:
            job_args_dict = {} # Đảm bảo là dict rỗng nếu null
        elif not isinstance(job_args_dict, dict): # Kiểm tra nếu không phải dict
             print(f"WARNING (scheduler_runner): job_args for job '{job_id}' is not a dict ({type(job_args_dict)}). Attempting to parse if string.")
             if isinstance(job_args_dict, str):
                 try:
                     parsed = json.loads(job_args_dict)
                     if isinstance(parsed, dict): job_args_dict = parsed
                     else: job_args_dict = {}
                 except json.JSONDecodeError: job_args_dict = {}
             else: job_args_dict = {} # Reset về rỗng nếu không phải string hoặc dict
        # ============================

        print(f"DEBUG (scheduler_runner): Processing job config: ID='{job_id}', Enabled={is_enabled}, Path='{function_path}', Trigger='{trigger_type}', T_Args={trigger_args_dict}, J_Args={job_args_dict}")

        if not job_id or not function_path or not trigger_type or trigger_args_dict is None:
            print(f"WARNING (scheduler_runner): Skipping invalid job config (missing required fields): {job_config}")
            continue

        # Xóa job khỏi scheduler nếu nó bị disable trong DB
        if not is_enabled:
            print(f"INFO (scheduler_runner): Job '{job_id}' is disabled in config.")
            try:
                 existing_job = scheduler.get_job(job_id, jobstore='default') # Kiểm tra jobstore default
                 if existing_job:
                      scheduler.remove_job(job_id, jobstore='default')
                      print(f"INFO (scheduler_runner): Removed disabled job '{job_id}' from scheduler during load.")
            except JobLookupError:
                 pass # Job không tồn tại, không cần làm gì
            except Exception as e_remove:
                 print(f"ERROR (scheduler_runner): Failed to check/remove disabled job '{job_id}' during load: {e_remove}")
            continue # Bỏ qua không thêm lại job bị disable

        # Chỉ xử lý các job được enable
        try:
            # Import function
            module_path, func_name = function_path.rsplit('.', 1)
            module = importlib.import_module(module_path)
            func = getattr(module, func_name)

            # Tạo Trigger Object (Đã sửa lỗi NoneType)
            trigger_obj = None
            # Chuyển đổi các giá trị trigger_args sang số nếu cần
            numeric_keys_trigger = ['weeks', 'days', 'hours', 'minutes', 'seconds', 'jitter', 'year', 'month', 'day', 'week', 'hour', 'minute', 'second']
            converted_trigger_args = trigger_args_dict.copy()
            for key in numeric_keys_trigger:
                if key in converted_trigger_args and isinstance(converted_trigger_args[key], str):
                    value_str = converted_trigger_args[key].strip()
                    if not value_str: del converted_trigger_args[key]; continue
                    try:
                        if '.' in value_str or 'e' in value_str.lower(): converted_trigger_args[key] = float(value_str)
                        else: converted_trigger_args[key] = int(value_str)
                    except (ValueError, TypeError):
                        raise ValueError(f"Invalid numeric value for trigger arg '{key}': '{value_str}'")

            if trigger_type == 'interval':
                trigger_obj = IntervalTrigger(
                    weeks=converted_trigger_args.get('weeks', 0),
                    days=converted_trigger_args.get('days', 0),
                    hours=converted_trigger_args.get('hours', 0),
                    minutes=converted_trigger_args.get('minutes', 0),
                    seconds=converted_trigger_args.get('seconds', 0),
                    start_date=converted_trigger_args.get('start_date'),
                    end_date=converted_trigger_args.get('end_date'),
                    timezone=SCHEDULER_TIMEZONE,
                    jitter=converted_trigger_args.get('jitter')
                )
            elif trigger_type == 'cron':
                trigger_obj = CronTrigger(
                    year=converted_trigger_args.get('year'), month=converted_trigger_args.get('month'), day=converted_trigger_args.get('day'),
                    week=converted_trigger_args.get('week'), day_of_week=converted_trigger_args.get('day_of_week'),
                    hour=converted_trigger_args.get('hour', 0),
                    minute=converted_trigger_args.get('minute', 0),
                    second=converted_trigger_args.get('second', 0),
                    start_date=converted_trigger_args.get('start_date'), end_date=converted_trigger_args.get('end_date'),
                    timezone=SCHEDULER_TIMEZONE, jitter=converted_trigger_args.get('jitter')
                )
            elif trigger_type == 'date':
                trigger_obj = DateTrigger(
                    run_date=converted_trigger_args.get('run_date'),
                    timezone=SCHEDULER_TIMEZONE
                )
            else:
                raise ValueError(f"Unsupported trigger type: {trigger_type}")

            # Thêm Job vào Scheduler với kwargs
            print(f"DEBUG (scheduler_runner): Adding job '{job_id}' with kwargs: {job_args_dict}")
            scheduler.add_job(
                id=job_id,
                func=func,
                trigger=trigger_obj,
                kwargs=job_args_dict,  # <<< THÊM KWARGS Ở ĐÂY
                replace_existing=True, # Cập nhật job nếu ID đã tồn tại
                misfire_grace_time=job_config.get('misfire_grace_time', 60), # Lấy từ config hoặc default
                max_instances=job_config.get('max_instances', 1),       # Lấy từ config hoặc default
                # Có thể thêm các tùy chọn khác từ job_config nếu cần
                name=job_config.get('description', job_id) # Dùng description làm tên job
            )
            print(f"SUCCESS (scheduler_runner): Added/Updated job '{job_id}' in scheduler.")
            added_count += 1

        except (ValueError, ImportError, AttributeError) as config_err:
            # Lỗi cấu hình (sai path, trigger type, giá trị trigger/job args không hợp lệ...)
            print(f"ERROR (scheduler_runner): Invalid config for job '{job_id}': {config_err}")
            # In traceback để debug dễ hơn
            # print(traceback.format_exc())
        except TypeError as type_err:
            # Lỗi kiểu dữ liệu khi gọi add_job (thường do kwargs hoặc trigger args sai)
            print(f"ERROR (scheduler_runner): TypeError adding job '{job_id}'. Args mismatch? Trigger={trigger_args_dict}, JobArgs={job_args_dict}. Error: {type_err}")
            # print(traceback.format_exc())
        except Exception as add_job_err:
            # Các lỗi khác khi thêm job
            print(f"ERROR (scheduler_runner): Failed to add/update job '{job_id}' to scheduler: {add_job_err}")
            print(traceback.format_exc())

    print(f"INFO (scheduler_runner): Finished loading jobs from DB. Added/Updated {added_count} enabled jobs.")
# =============================================================

def _process_pending_commands():
    """
    Kiểm tra bảng scheduler_commands và thực thi các lệnh đang chờ
    (run_simulation, run_suggestion_job_now, cancel_job, approve_all_suggestions, build_map).
    """
    global live_scheduler # Cần truy cập scheduler đang chạy để thêm/xóa job

    # 1. Kiểm tra các điều kiện cần thiết
    if not live_scheduler or not live_scheduler.running:
        # print("DEBUG (Command Processor): Scheduler not running.") # Có thể bỏ comment để debug
        return
    if not db:
        print("ERROR (Command Processor): Database module (db) not available.")
        return

    # Lấy các hàm tác vụ một cách an toàn (đã import ở trên)
    run_sim_func = globals().get('run_ai_conversation_simulation')
    suggest_func = globals().get('analyze_interactions_and_suggest')
    approve_all_func = globals().get('approve_all_suggestions_task')
    build_map_func = globals().get('build_app_map_task') # <<< Lấy hàm task mới

    # print(f"DEBUG (Command Processor): Checking for pending commands... ({datetime.now().strftime('%H:%M:%S')})") # Log nếu cần

    conn = None
    processed_count = 0 # Đếm số lệnh đã xử lý trong lần chạy này

    try:
        # 2. Lấy kết nối CSDL
        conn = db.get_db_connection()
        if not conn:
            print("ERROR (Command Processor): Cannot get DB connection.")
            return
        conn.autocommit = False # Bắt đầu Transaction

        # 3. Lấy các lệnh đang chờ xử lý (pending)
        # Lấy với giới hạn nhất định để tránh xử lý quá nhiều cùng lúc
        pending_sim = db.get_pending_commands(conn=conn, command_type='run_simulation', limit=10) or []
        pending_run_suggest = db.get_pending_commands(conn=conn, command_type='run_suggestion_job_now', limit=5) or []
        pending_approve_all = db.get_pending_commands(conn=conn, command_type='approve_all_suggestions', limit=5) or []
        pending_cancel = db.get_pending_commands(conn=conn, command_type='cancel_job', limit=10) or []
        pending_build_map = db.get_pending_commands(conn=conn, command_type='build_map', limit=20) or [] # <<< Lấy lệnh mới

        # Gom tất cả lại (có thể ưu tiên thứ tự nếu cần, ví dụ cancel trước)
        all_pending = pending_cancel + pending_sim + pending_run_suggest + pending_approve_all + pending_build_map

        if not all_pending:
            # Không có lệnh nào, commit để giải phóng transaction và thoát
            conn.commit()
            if conn: conn.close()
            return

        print(f"INFO (Command Processor): Found {len(all_pending)} pending command(s).")

        # 4. Lặp qua từng lệnh và xử lý
        for command in all_pending:
            command_id = command.get('command_id')
            command_type = command.get('command_type')
            payload = command.get('payload') # Đã là dict nếu dùng DictCursor

            if not command_id or not command_type:
                 print(f"WARN (Cmd Proc): Skipping invalid command data: {command}")
                 continue

            print(f"DEBUG (Cmd Proc): Processing command ID: {command_id}, Type: {command_type}")

            # 4a. Đánh dấu lệnh là 'processing' NGAY LẬP TỨC trong transaction
            updated_processing = db.update_command_status(conn, command_id, 'processing')
            if not updated_processing:
                print(f"WARN (Cmd Proc): Could not mark command {command_id} as processing. Skipping.")
                # Có thể lệnh này đã bị xử lý bởi một worker khác?
                continue # Bỏ qua lệnh này

            # 4b. Khối try/except riêng cho việc xử lý từng lệnh
            try:
                # --- Xử lý lệnh HỦY JOB ---
                if command_type == 'cancel_job':
                    job_id_to_cancel = payload.get('job_id_to_cancel')
                    if not job_id_to_cancel:
                        raise ValueError("Missing 'job_id_to_cancel' in payload for cancel_job command.")

                    print(f"DEBUG (Cmd Proc): Attempting to remove scheduled job ID: {job_id_to_cancel}")
                    try:
                        live_scheduler.remove_job(job_id_to_cancel, jobstore='default')
                        print(f"INFO (Cmd Proc): Successfully removed job '{job_id_to_cancel}' from scheduler.")
                        db.update_command_status(conn, command_id, 'done') # Đánh dấu thành công
                    except JobLookupError:
                        print(f"WARN (Cmd Proc): Job '{job_id_to_cancel}' not found in scheduler for cancellation. Marking command done anyway.")
                        db.update_command_status(conn, command_id, 'done')
                    # Các lỗi khác khi remove_job sẽ bị bắt bởi except bên ngoài

                # --- Xử lý lệnh CHẠY MÔ PHỎNG ---
                elif command_type == 'run_simulation':
                    if not run_sim_func: raise ImportError("run_ai_conversation_simulation function not available")
                    # Trích xuất và validate params từ payload
                    params = payload
                    persona_a_id = params.get('persona_a_id')
                    persona_b_id = params.get('persona_b_id')
                    strategy_id = params.get('strategy_id')
                    max_turns = int(params.get('max_turns', 5)) # Chuyển sang int
                    starting_prompt = params.get('starting_prompt') or "Xin chào!"
                    log_account_id_a = params.get('log_account_id_a')
                    log_account_id_b = params.get('log_account_id_b')
                    sim_thread_id_base = params.get('sim_thread_id_base') or f"sim_{log_account_id_a[:5]}_vs_{log_account_id_b[:5]}"
                    sim_goal = params.get('sim_goal') or "adhoc_simulation"

                    if not all([persona_a_id, persona_b_id, strategy_id, log_account_id_a, log_account_id_b]):
                        raise ValueError("Missing required parameters in simulation payload.")

                    # Tạo job ID duy nhất
                    job_id = f"sim_run_{command_id}_{uuid.uuid4().hex[:8]}"
                    job_name_display = f"SimCmd{command_id}: {persona_a_id} vs {persona_b_id}"
                    run_time = datetime.now(SCHEDULER_TIMEZONE) + timedelta(seconds=2) # Chạy sau 2 giây
                    job_args = (persona_a_id, persona_b_id, strategy_id, max_turns, starting_prompt,
                                log_account_id_a, log_account_id_b, sim_thread_id_base, sim_goal)

                    print(f"DEBUG (Cmd Proc): Scheduling adhoc job '{job_id}' Name='{job_name_display}'")
                    live_scheduler.add_job(id=job_id, func=run_sim_func, args=job_args, trigger='date', run_date=run_time,
                                           jobstore='default', executor='processpool', replace_existing=False, misfire_grace_time=120,
                                           name=job_name_display)
                    db.update_command_status(conn, command_id, 'done') # Đánh dấu lệnh gốc là done
                    print(f"INFO (Cmd Proc): Scheduled job '{job_id}' for simulation command {command_id}.")

                # --- Xử lý lệnh CHẠY JOB ĐỀ XUẤT NGAY ---
                elif command_type == 'run_suggestion_job_now':
                     if not suggest_func: raise ImportError("analyze_interactions_and_suggest function not available")
                     job_id = f"manual_suggestion_run_{uuid.uuid4().hex[:8]}"
                     run_time = datetime.now(SCHEDULER_TIMEZONE) + timedelta(seconds=1)
                     live_scheduler.add_job(id=job_id, func=suggest_func, args=(), trigger='date', run_date=run_time,
                                            jobstore='default', executor='processpool', replace_existing=False, misfire_grace_time=120,
                                            name="Manual Suggestion Run")
                     db.update_command_status(conn, command_id, 'done')
                     print(f"INFO (Cmd Proc): Scheduled job '{job_id}' for suggestion command {command_id}.")

                # --- Xử lý lệnh DUYỆT TẤT CẢ ĐỀ XUẤT ---
                elif command_type == 'approve_all_suggestions':
                     if not approve_all_func: raise ImportError("approve_all_suggestions_task function not available")
                     job_id = f"approve_all_run_{uuid.uuid4().hex[:8]}"
                     run_time = datetime.now(SCHEDULER_TIMEZONE) + timedelta(seconds=1)
                     live_scheduler.add_job(id=job_id, func=approve_all_func, args=(), trigger='date', run_date=run_time,
                                            jobstore='default', executor='default', # Có thể chạy trong threadpool
                                            replace_existing=False, misfire_grace_time=300,
                                            name="Bulk Approve Suggestions")
                     db.update_command_status(conn, command_id, 'done')
                     print(f"INFO (Cmd Proc): Scheduled job '{job_id}' for bulk approve command {command_id}.")

                # --- XỬ LÝ LỆNH MỚI: BUILD APP MAP ---
                elif command_type == 'build_map':
                    if not build_map_func: raise ImportError("build_app_map_task function not available.")

                    if not payload: raise ValueError("Missing payload for build_map command.")

                    # Gọi trực tiếp hàm task (vì nó tự tạo app context)
                    try:
                        # Truyền payload (là dict) vào hàm task
                        build_map_func(payload)
                        # Nếu hàm chạy xong không lỗi -> đánh dấu done
                        db.update_command_status(conn, command_id, 'done')
                        print(f"INFO (Cmd Proc): Executed build_map task successfully for cmd {command_id}.")
                    except Exception as map_task_error:
                        # Nếu hàm build_app_map_task báo lỗi
                        error_msg_map = f"Error during build_map task execution: {map_task_error}"
                        print(f"ERROR (Cmd Proc): {error_msg_map}")
                        db.update_command_status(conn, command_id, 'error', error_message=str(map_task_error)[:500])
                        # Không ném lại lỗi ở đây để vòng lặp tiếp tục xử lý lệnh khác

                # --- Lệnh không xác định ---
                else:
                    raise ValueError(f"Unknown command_type encountered: {command_type}")

                # Nếu xử lý thành công (không raise exception trong khối try này)
                processed_count += 1

            except Exception as processing_err:
                # Bắt lỗi xảy ra KHI xử lý MỘT lệnh cụ thể (ví dụ: validate payload, lỗi khi add_job/remove_job)
                error_message = f"Error processing command {command_id} ({command_type}): {type(processing_err).__name__} - {processing_err}"
                print(error_message)
                traceback.print_exc() # In traceback để debug
                # Cập nhật status của lệnh này thành 'error'
                db.update_command_status(conn, command_id, 'error', error_message=str(processing_err)[:500])
                # Không rollback transaction ở đây, để các lệnh khác (nếu có) vẫn được xử lý và commit status lỗi

        # 5. Commit Transaction sau khi xử lý hết các lệnh trong batch
        conn.commit()
        if processed_count > 0:
             print(f"DEBUG (Command Processor): Finished processing batch. Committed status updates for {processed_count} command(s).")

    except psycopg2.Error as db_conn_err: # Lỗi kết nối hoặc transaction lớn
         print(f"ERROR (Command Processor): Database connection/transaction error: {db_conn_err}")
         if conn: conn.rollback() # Rollback nếu lỗi transaction lớn
         traceback.print_exc()
    except Exception as loop_err: # Lỗi không mong muốn khác trong vòng lặp chính
        print(f"ERROR (Command Processor): Unexpected error in command processor loop: {loop_err}")
        print(traceback.format_exc())
        if conn: conn.rollback() # Rollback nếu lỗi không rõ
    finally:
        # 6. Luôn đóng kết nối CSDL
        if conn:
            try:
                if not conn.closed:
                    conn.close()
                    # print("DEBUG (Command Processor): DB Connection closed in finally.")
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


print("DEBUG: app/database.py - Module loaded completely.")
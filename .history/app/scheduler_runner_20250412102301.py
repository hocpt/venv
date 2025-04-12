# backup/app/scheduler_runner.py
import logging
import traceback
import time
import importlib
import json
from datetime import datetime
from flask import Flask # Cần Flask để dùng app_context

# Import các thành phần của APScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor # Có thể chọn
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

# Import module database cục bộ
try:
    from . import database as db
except ImportError:
    import database as db # Fallback

# Biến toàn cục để giữ instance scheduler đang chạy (cho các route admin truy cập)
live_scheduler = None

log = logging.getLogger(__name__) # Tạo logger riêng cho module này

def load_scheduled_jobs_standalone(app: Flask, scheduler: BackgroundScheduler):
    """
    Hàm helper để load và đăng ký jobs từ DB vào instance scheduler được cung cấp.
    Chạy bên trong app_context để truy cập db.
    """
    print("INFO (scheduler_runner): Starting to load scheduled jobs from DB...")
    # Cần app context để dùng db.get_db_connection (vì nó dùng current_app.config)
    with app.app_context():
        try:
            job_configs = db.get_all_job_configs() # Lấy cấu hình từ bảng scheduled_jobs

            if job_configs is None:
                print("ERROR (scheduler_runner): Failed to load job configurations from DB.")
                return

            if not job_configs:
                print("INFO (scheduler_runner): No job configurations found in DB.")
                return

            added_count = 0
            for job_config in job_configs:
                job_id = job_config.get('job_id')
                is_enabled = job_config.get('is_enabled', False)
                function_path = job_config.get('job_function_path')
                trigger_type = job_config.get('trigger_type')
                # trigger_args lấy từ DB đã là dict (do kiểu JSONB)
                trigger_args_dict = job_config.get('trigger_args', {})

                print(f"DEBUG (scheduler_runner): Processing job config: ID='{job_id}', Enabled={is_enabled}, Path='{function_path}', Trigger='{trigger_type}', Args={trigger_args_dict}")

                if not job_id or not function_path or not trigger_type or trigger_args_dict is None:
                    print(f"WARNING (scheduler_runner): Skipping invalid job config: {job_config}")
                    continue

                # Lưu ý: Job bị disable trong DB sẽ không được thêm vào scheduler đang chạy
                if not is_enabled:
                    print(f"INFO (scheduler_runner): Job '{job_id}' is disabled in config, skipping add.")
                    # Đảm bảo xóa job khỏi scheduler nếu nó đang chạy (trường hợp disable sau)
                    try:
                         if scheduler.get_job(job_id):
                              scheduler.remove_job(job_id)
                              print(f"INFO (scheduler_runner): Removed disabled job '{job_id}' from running scheduler.")
                    except Exception as e_remove:
                         print(f"ERROR (scheduler_runner): Failed to remove disabled job '{job_id}' from scheduler: {e_remove}")
                    continue # Bỏ qua không thêm job bị disable

                try:
                    # Import hàm
                    module_path, func_name = function_path.rsplit('.', 1)
                    module = importlib.import_module(module_path)
                    func = getattr(module, func_name)

                    # Tạo đối tượng trigger
                    trigger_obj = None
                    # Chuyển đổi kiểu dữ liệu số cho trigger args (vẫn cần thiết)
                    numeric_keys = ['weeks', 'days', 'hours', 'minutes', 'seconds', 'jitter', 'year', 'month', 'day', 'week', 'hour', 'minute', 'second']
                    converted_args = trigger_args_dict.copy() # Tạo bản copy để không sửa dict gốc
                    for key in numeric_keys:
                        if key in converted_args and isinstance(converted_args[key], str):
                             value_str = converted_args[key].strip()
                             if not value_str:
                                  del converted_args[key]
                                  continue
                             try:
                                 if '.' in value_str: converted_args[key] = float(value_str)
                                 else: converted_args[key] = int(value_str)
                             except (ValueError, TypeError):
                                  raise ValueError(f"Invalid numeric value for '{key}': '{value_str}'")

                    if trigger_type == 'interval':
                        trigger_obj = IntervalTrigger(**converted_args)
                    elif trigger_type == 'cron':
                        trigger_obj = CronTrigger(**converted_args)
                    elif trigger_type == 'date':
                        trigger_obj = DateTrigger(**converted_args)
                    else:
                        raise ValueError(f"Unsupported trigger type: {trigger_type}")

                    # Thêm hoặc cập nhật job trong scheduler
                    scheduler.add_job(
                        id=job_id,
                        func=func, # Đây là hàm analyze_interactions_and_suggest(app)
                        trigger=trigger_obj,
                        replace_existing=True,
                        args=(app,), # <<< THÊM THAM SỐ NÀY ĐỂ TRUYỀN app VÀO HÀM TÁC VỤ >>>
                        name=f"Job for {func_name}"
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

        except Exception as e:
            print(f"CRITICAL ERROR during loading scheduled jobs: {e}")
            print(traceback.format_exc())


def run_scheduler(app: Flask):
    """
    Hàm chính để khởi tạo, cấu hình và chạy BackgroundScheduler độc lập.
    Hàm này sẽ chạy trong một thread riêng biệt.
    """
    global live_scheduler # Khai báo để gán giá trị cho biến toàn cục
    print("INFO: Initializing independent BackgroundScheduler...")

    # Lấy cấu hình CSDL từ app config để dùng cho SQLAlchemyJobStore
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI')
    if not db_uri:
        print("CRITICAL ERROR (scheduler_runner): SQLALCHEMY_DATABASE_URI not found in app config. Cannot start scheduler with SQLAlchemyJobStore.")
        return

    # Cấu hình Jobstore và Executor
    jobstores = {
        'default': SQLAlchemyJobStore(url=db_uri)
    }
    # Chọn Executor (ThreadPool thường đơn giản hơn ProcessPool)
    executors = {
        'default': ThreadPoolExecutor(max_workers=app.config.get('SCHEDULER_DEFAULT_MAX_WORKERS', 10))
        # 'default': ProcessPoolExecutor(max_workers=app.config.get('SCHEDULER_DEFAULT_MAX_PROCESSES', 5))
    }
    job_defaults = app.config.get('SCHEDULER_JOB_DEFAULTS', {'coalesce': False, 'max_instances': 1})
    timezone = app.config.get('SCHEDULER_TIMEZONE', 'UTC') # Lấy timezone từ config hoặc mặc định UTC

    try:
        # Khởi tạo BackgroundScheduler với cấu hình
        scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone=timezone
        )

        # Gán instance đang chạy vào biến toàn cục để các module khác có thể truy cập
        live_scheduler = scheduler
        #print(f"INFO (scheduler_runner): BackgroundScheduler instance created and assigned to 'live_scheduler'. Jobstore: SQLAlchemy, Executor: {executors['default']['type']}")
        executor_instance = executors.get('default') # Lấy object executor
        executor_type_name = type(executor_instance).__name__ if executor_instance else 'N/A' # Lấy tên class
        print(f"INFO (scheduler_runner): BackgroundScheduler instance created. Jobstore: SQLAlchemy, Executor Type: {executor_type_name}")
        # Load các jobs đã cấu hình trong DB vào scheduler này
        # Chạy trong app_context vì load_scheduled_jobs_standalone cần nó
        load_scheduled_jobs_standalone(app, live_scheduler)

        # Bắt đầu chạy scheduler
        print("INFO (scheduler_runner): Starting BackgroundScheduler...")
        live_scheduler.start()
        print("SUCCESS (scheduler_runner): BackgroundScheduler started successfully in a separate thread.")

        # Giữ cho thread này sống mãi mãi (hoặc cho đến khi bị ngắt)
        # APScheduler chạy nền nên không cần vòng lặp vô hạn ở đây nếu start() không block
        # Tuy nhiên, nếu thread này kết thúc thì scheduler cũng dừng.
        # Cách đơn giản là dùng vòng lặp sleep
        try:
            while True:
                time.sleep(3600) # Ngủ 1 tiếng rồi kiểm tra lại (hoặc một khoảng thời gian lớn)
                # Có thể thêm logic kiểm tra sức khỏe scheduler ở đây nếu cần
        except (KeyboardInterrupt, SystemExit):
            print("INFO (scheduler_runner): Shutdown signal received...")

    except Exception as e:
        print(f"CRITICAL ERROR initializing or running the scheduler: {e}")
        print(traceback.format_exc())
        # Đảm bảo gán lại live_scheduler là None nếu có lỗi khởi tạo
        live_scheduler = None
    finally:
        # Dọn dẹp khi thread kết thúc (ví dụ khi nhận KeyboardInterrupt)
        if live_scheduler and live_scheduler.running:
            print("INFO (scheduler_runner): Shutting down scheduler...")
            live_scheduler.shutdown()
            print("INFO (scheduler_runner): Scheduler shut down.")

# --- Kết thúc file app/scheduler_runner.py ---
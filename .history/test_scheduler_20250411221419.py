# test_scheduler.py
import logging
import sys
import time
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

# Cấu hình logging cơ bản để xem output của scheduler và job
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG,
                    format='%(asctime)s %(levelname)-8s %(name)-15s : %(message)s')
logging.getLogger('apscheduler').setLevel(logging.DEBUG)

# Hàm job đơn giản chỉ để in ra log
def simple_print_job():
    """Một job đơn giản chỉ in ra thông báo."""
    print(f"++++++++++++ STANDALONE APSCHEDULER JOB EXECUTED AT {datetime.now()} +++++++++++++")

if __name__ == '__main__':
    print("--- Starting Standalone APScheduler Test ---")

    # Khởi tạo scheduler nền (dùng MemoryJobStore mặc định)
    scheduler = BackgroundScheduler()
    print("--- Scheduler Initialized ---")

    try:
        # Thêm job test chạy mỗi 5 giây
        print("--- Adding test job (interval: 5 seconds)... ---")
        scheduler.add_job(
            id='standalone_test_job',
            func=simple_print_job,
            trigger='interval',
            seconds=5, # Chạy mỗi 5 giây để nhanh thấy kết quả
            replace_existing=True
        )
        print("--- Test job added ---")

        # Bắt đầu scheduler
        print("--- Starting scheduler... ---")
        scheduler.start()
        print("--- Scheduler supposedly started. Keeping main thread alive... (Press Ctrl+C to stop) ---")

        # Giữ cho script chính chạy để scheduler nền có thời gian hoạt động
        try:
            while True:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            print("\n--- Shutting down scheduler... ---")
            scheduler.shutdown()
            print("--- Scheduler shut down. Exiting. ---")

    except Exception as e:
        print(f"\n--- An error occurred: {e} ---")
        logging.exception("Error during scheduler setup or run:")
        # Cố gắng shutdown nếu scheduler đã start
        if scheduler.running:
             scheduler.shutdown()
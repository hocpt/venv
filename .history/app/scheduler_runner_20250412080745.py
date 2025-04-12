import threading
from time import sleep
from datetime import datetime
from flask_apscheduler import APScheduler

scheduler = APScheduler()

def test_job():
    print(f"[TEST_JOB] Chạy lúc: {datetime.now()}")

def run_scheduler(app):
    with app.app_context():
        # ✅ Cấu hình rõ ràng trong Python (tránh xung đột config)
        scheduler.configure({
            'SCHEDULER_JOBSTORES': {
                'default': {'type': 'memory'}
            },
            'SCHEDULER_EXECUTORS': {
                'default': {'type': 'threadpool', 'max_workers': 5}
            },
            'SCHEDULER_API_ENABLED': True
        })
        scheduler.init_app(app)
        scheduler.start()

        scheduler.add_job(
            id='test_hello_job',
            func=test_job,
            trigger='interval',
            seconds=10,
            replace_existing=True
        )

        print("✅ Scheduler đã khởi động và đăng ký job.")

        while True:
            sleep(60)

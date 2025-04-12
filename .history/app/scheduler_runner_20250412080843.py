import threading
from time import sleep
from datetime import datetime
from flask_apscheduler import APScheduler

scheduler = APScheduler()

def test_job():
    print(f"[TEST_JOB] Chạy lúc: {datetime.now()}")

def run_scheduler(app):
    with app.app_context():
        # ✅ Đúng cú pháp: cấu hình thông qua .scheduler
        scheduler.init_app(app)

        scheduler.scheduler.configure({
            'jobstores': {
                'default': {'type': 'memory'}
            },
            'executors': {
                'default': {'type': 'threadpool', 'max_workers': 5}
            },
            'job_defaults': {
                'coalesce': False,
                'max_instances': 3
            },
            'timezone': 'UTC'
        })

        scheduler.start()

        # ✅ Thêm job test
        scheduler.add_job(
            id='test_hello_job',
            func=test_job,
            trigger='interval',
            seconds=10,
            replace_existing=True
        )

        print("✅ Scheduler đã khởi động và đăng ký job.")

        # Giữ thread sống
        while True:
            sleep(60)


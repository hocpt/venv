import threading
from time import sleep
from datetime import datetime
from flask_apscheduler import APScheduler

scheduler = APScheduler()

def test_job():
    print(f"[TEST_JOB] Chạy lúc: {datetime.now()}")

def run_scheduler(app):
    with app.app_context():
        scheduler.init_app(app)
        scheduler.start()

        # Job test đơn giản
        scheduler.add_job(
            id='test_hello_job',
            func=test_job,
            trigger='interval',
            seconds=10,
            replace_existing=True
        )

        print("✅ Scheduler đã khởi động và đăng ký job.")

        # Giữ thread sống (dù không cần, giúp debug dễ)
        while True:
            sleep(60)

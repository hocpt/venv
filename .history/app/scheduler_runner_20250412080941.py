import threading
from time import sleep
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

def test_job():
    print(f"[TEST_JOB] Chạy lúc: {datetime.now()}")

def run_scheduler():
    scheduler = BackgroundScheduler({
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

    scheduler.add_job(
        id='test_hello_job',
        func=test_job,
        trigger='interval',
        seconds=10,
        replace_existing=True
    )

    print("✅ Scheduler chạy nền đã khởi động.")
    while True:
        sleep(60)

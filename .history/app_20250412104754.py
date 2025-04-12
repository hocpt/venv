from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_apscheduler import APScheduler
from config import Config
import datetime

# Tạo app + cấu hình
app = Flask(__name__)
app.config.from_object(Config)

# Khởi tạo extension
db = SQLAlchemy(app)
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

# Job cần chạy
def my_job():
    print(f"📢 Job đang chạy! {datetime.datetime.now().strftime('%H:%M:%S')}")

# Thêm job vào scheduler (chạy mỗi 10 giây)
scheduler.add_job(
    id='demo_job',
    func=my_job,
    trigger='interval',
    seconds=10,
    replace_existing=True
)

@app.route('/')
def index():
    return "✅ Flask đang chạy + Scheduler hoạt động!"

if __name__ == '__main__':
    app.run(debug=True)

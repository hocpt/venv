# app/phone/__init__.py
from flask import Blueprint

# Tạo blueprint 'phone' với tiền tố URL là /phone
# Tất cả các route định nghĩa trong blueprint này sẽ bắt đầu bằng /phone
phone_bp = Blueprint(
    'phone',
    __name__,
    url_prefix='/phone'
    # Nếu có templates hoặc static files riêng cho blueprint này thì thêm:
    # template_folder='templates',
    # static_folder='static'
)

# Import các routes của blueprint này (phải đặt sau khi tạo phone_bp)
# File routes.py sẽ chứa các @phone_bp.route(...)
from . import routes

print("DEBUG: Blueprint 'phone' created.")
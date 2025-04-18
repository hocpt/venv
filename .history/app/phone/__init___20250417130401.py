# app/phone/__init__.py

from flask import Blueprint

# 1. Tạo đối tượng Blueprint
#    - 'phone': Tên của blueprint (dùng nội bộ và trong url_for, ví dụ: 'phone.get_strategy')
#    - __name__: Giúp Flask xác định vị trí của blueprint
#    - url_prefix='/phone': Tất cả các route trong blueprint này sẽ bắt đầu bằng '/phone'
#      (Ví dụ: /phone/get_strategy, /phone/report_status)
phone_bp = Blueprint(
    'phone',
    __name__,
    url_prefix='/phone'
    # Nếu bạn có template hoặc static file riêng cho phần phone này, có thể thêm:
    # template_folder='templates',
    # static_folder='static'
    # Nhưng thường thì dùng chung template và static của thư mục app chính.
)

# 2. Import các module chứa routes của blueprint này
#    Quan trọng: Lệnh import này phải đặt *sau* khi phone_bp được tạo.
#    Nó sẽ tìm file routes.py trong cùng thư mục app/phone/ và đăng ký các
#    route được định nghĩa bằng @phone_bp.route(...) trong file đó.
from . import routes

# (Tùy chọn) Thêm lệnh print để xác nhận blueprint được tạo khi server khởi động
print(f"DEBUG (app/phone/__init__.py): Blueprint '{phone_bp.name}' created with url_prefix '{phone_bp.url_prefix}'.")
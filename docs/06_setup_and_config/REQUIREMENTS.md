
# Hướng dẫn Cài đặt và Yêu cầu Hệ thống

Tài liệu này mô tả các yêu cầu hệ thống, các bước cài đặt môi trường và các thư viện cần thiết để triển khai và chạy ứng dụng HPT11.

## 1. Yêu cầu Hệ thống

Để chạy ứng dụng HPT11, môi trường của bạn cần đáp ứng các yêu cầu sau:

* **Python:** Phiên bản 3.9 trở lên.
* **Cơ sở dữ liệu PostgreSQL:**
    * Phiên bản khuyến nghị: 12.x trở lên.
    * Cần có quyền tạo database, user, và schema.
* **Cơ sở dữ liệu Neo4j:**
    * Phiên bản khuyến nghị: 4.x hoặc 5.x.
    * Cần có thông tin URI, user, và password để kết nối.
* **Hệ điều hành:**
    * Ưu tiên: Linux (ví dụ: Ubuntu, CentOS).
    * Có thể chạy trên: macOS, Windows (với WSL2 cho trải nghiệm tốt hơn đối với một số thành phần).
* **Trình quản lý gói Python:** `pip` (thường đi kèm với Python).
* **Git:** Để clone mã nguồn dự án (nếu có).

## 2. Cài đặt Môi trường Python

Khuyến khích sử dụng môi trường ảo (virtual environment) để quản lý các gói phụ thuộc của dự án một cách độc lập.

### 2.1. Tạo Môi trường ảo (sử dụng `venv`)

Mở terminal hoặc command prompt, di chuyển đến thư mục gốc của dự án và thực hiện lệnh sau:

```bash
# Đối với Linux/macOS
python3 -m venv venv

# Đối với Windows
python -m venv venv
2.2. Kích hoạt Môi trường ảo
Linux/macOS:
Bash

source venv/bin/activate
Windows (Command Prompt):
Bash

.\venv\Scripts\activate.bat
Windows (PowerShell):
Bash

.\venv\Scripts\Activate.ps1
Sau khi kích hoạt, tên môi trường ảo (ví dụ: (venv)) sẽ xuất hiện ở đầu dòng lệnh của bạn.

3. Cài đặt các Thư viện Python
Dự án sử dụng hai tệp requirements.txt và requirements2.txt để quản lý các gói phụ thuộc.

Thực hiện các lệnh sau để cài đặt:

Bash

pip install -r requirements.txt
pip install -r requirements2.txt
Một số thư viện chính và mục đích của chúng:

Flask, Flask-SQLAlchemy, Flask-WTF: Nền tảng web framework, tương tác CSDL quan hệ, xử lý form.
psycopg2-binary: PostgreSQL adapter cho Python.
neo4j: Thư viện chính thức của Neo4j cho Python để tương tác với CSDL đồ thị.
APScheduler: Thư viện lập lịch tác vụ.
SQLAlchemy: ORM (Object Relational Mapper) được APScheduler sử dụng cho JobStore.
Markdown: Thư viện chuyển đổi văn bản Markdown sang HTML (dùng cho trang tài liệu).
Pygments: Thư viện tô sáng cú pháp cho các khối mã (dùng cho trang tài liệu).
google-generativeai: Thư viện Python cho Google Gemini API.
Pillow (PIL Fork): Thư viện xử lý ảnh (ví dụ: đọc kích thước ảnh screenshot).
python-dotenv: Đọc các biến môi trường từ file .env.
pytz: Xử lý múi giờ.
cryptography: Thư viện mã hóa (được sử dụng bởi app/encryption.py).
Werkzeug: Bộ công cụ WSGI, là một dependency của Flask.
Jinja2: Template engine cho Flask.
MarkupSafe: Xử lý chuỗi an toàn cho HTML (dependency của Jinja2).
(Liệt kê các thư viện khác nếu cần thiết)
4. Cài đặt Cơ sở dữ liệu
4.1. PostgreSQL
Cài đặt PostgreSQL Server:
Tham khảo tài liệu chính thức của PostgreSQL: https://www.postgresql.org/download/
Tạo Database và User:
Sau khi cài đặt, bạn cần tạo một database và một user riêng cho ứng dụng HPT11. Ví dụ, sử dụng psql:
SQL

CREATE DATABASE hpt11_db;
CREATE USER hpt11_user WITH PASSWORD 'your_strong_password';
GRANT ALL PRIVILEGES ON DATABASE hpt11_db TO hpt11_user;
ALTER ROLE hpt11_user SET client_encoding TO 'utf8';
ALTER ROLE hpt11_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE hpt11_user SET timezone TO 'UTC'; -- Hoặc múi giờ của bạn
Lưu ý: Thay hpt11_db, hpt11_user, và your_strong_password bằng các giá trị thực tế của bạn.
Cấu hình kết nối: Cập nhật biến môi trường DATABASE_URL (và SQLALCHEMY_DATABASE_URI) trong file .env hoặc trong cấu hình hệ thống của bạn. Xem chi tiết tại ENVIRONMENT_VARIABLES.md.
4.2. Neo4j
Cài đặt Neo4j Server:
Tham khảo tài liệu chính thức của Neo4j: https://neo4j.com/download-center/ (Chọn phiên bản Community hoặc Desktop).
Cấu hình Neo4j:
Sau khi cài đặt, Neo4j thường chạy trên bolt://localhost:7687.
User mặc định thường là neo4j với password ban đầu bạn đặt khi cài đặt (hoặc neo4j cho một số phiên bản cũ hơn).
Cấu hình kết nối: Cập nhật các biến môi trường NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, và NEO4J_DATABASE trong file .env hoặc cấu hình hệ thống. Xem chi tiết tại ENVIRONMENT_VARIABLES.md.
5. Thiết lập Dự án
Clone Repository (Nếu có):
Nếu mã nguồn được quản lý trên Git, clone repository về máy của bạn.

Bash

git clone <repository_url>
cd <project_directory>
Cấu hình Biến Môi trường:

Tạo một file .env ở thư mục gốc của dự án (cùng cấp với run.py).
Sao chép nội dung từ file example.env (nếu có) hoặc tự định nghĩa các biến môi trường cần thiết như mô tả trong ENVIRONMENT_VARIABLES.md.
Đặc biệt quan trọng là các biến kết nối CSDL (DATABASE_URL, NEO4J_URI, v.v.) và SECRET_KEY, ENCRYPTION_KEY.
Bạn có thể tạo SECRET_KEY và ENCRYPTION_KEY bằng cách chạy script generate_key.py (nếu có) hoặc sử dụng các công cụ tạo key ngẫu nhiên.
Áp dụng Lược đồ CSDL (PostgreSQL):

Kết nối vào database PostgreSQL bạn đã tạo (ví dụ: hpt11_db) bằng psql hoặc một công cụ quản trị CSDL.
Chạy nội dung của file automation_schema.sql để tạo tất cả các bảng và cấu trúc cần thiết.
Bash

# Ví dụ dùng psql
psql -U hpt11_user -d hpt11_db -f automation_schema.sql
Chạy Dữ liệu Mẫu (Seed Data - Tùy chọn):

Nếu dự án có file seed_data.sql, bạn có thể chạy nó tương tự như bước trên để chèn dữ liệu mẫu ban đầu.
Bash

psql -U hpt11_user -d hpt11_db -f seed_data.sql
Tham khảo SEED_DATA.md để biết thêm chi tiết về dữ liệu mẫu.
Tạo Thư mục Upload (Nếu cần):

Ứng dụng có thể cần một thư mục để lưu các file được tải lên (ví dụ: ảnh chụp màn hình). Đảm bảo thư mục được chỉ định trong UPLOAD_FOLDER hoặc SCREENSHOT_STORAGE_PATH trong config.py tồn tại và ứng dụng có quyền ghi vào đó.
Hàm create_app trong app/__init__.py có logic tạo thư mục UPLOAD_FOLDER nếu chưa có.
6. Chạy Ứng dụng
Sau khi hoàn tất các bước cài đặt và cấu hình:

6.1. Chạy Flask Web Server
Mở terminal, đảm bảo môi trường ảo đã được kích hoạt, và chạy lệnh:

Bash

flask run
# Hoặc nếu bạn có file run.py:
# python run.py
Ứng dụng web (bao gồm cả giao diện admin) thường sẽ chạy tại http://127.0.0.1:5000/.

6.2. Chạy Scheduler Runner
Để các tác vụ nền được lập lịch (scheduled tasks) hoạt động, bạn cần chạy script scheduler_runner.py trong một terminal riêng biệt:

Bash

# Đảm bảo môi trường ảo đã được kích hoạt
python app/scheduler_runner.py
Script này sẽ kết nối đến CSDL, nạp các job đã cấu hình và bắt đầu thực thi chúng theo lịch trình.

7. Gỡ lỗi và Troubleshooting
Kiểm tra kỹ các biến môi trường, đặc biệt là các chuỗi kết nối CSDL.
Đảm bảo các dịch vụ CSDL (PostgreSQL, Neo4j) đang chạy.
Xem log của ứng dụng Flask và log của scheduler_runner.py để tìm thông báo lỗi chi tiết.
Nếu có lỗi liên quan đến thư viện, đảm bảo tất cả các gói trong requirements.txt và requirements2.txt đã được cài đặt đúng cách trong môi trường ảo.
<!-- end list -->


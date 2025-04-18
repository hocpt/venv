# README - Dự án Tự Động Hóa với AI

## Mục tiêu
Dự án này nhằm xây dựng một hệ thống tự động hóa thông minh, có khả năng:
* Tương tác qua tin nhắn/bình luận dựa trên chiến lược và ngữ cảnh.
* Sử dụng AI (Google Gemini) để tạo phản hồi, phân tích ý định, và đề xuất quy luật mới.
* Quản lý các cấu hình (Tài khoản, Luật, Templates, Personas, Strategies...) qua giao diện Web Admin.
* Chạy các tác vụ nền tự động (phân tích, đề xuất, mô phỏng...).
* Mô phỏng hội thoại AI-vs-AI để tạo dữ liệu.
* Quản lý và sử dụng nhiều API Key để tránh giới hạn quota.
* (Hướng phát triển) Tích hợp khả năng điều khiển thiết bị (điện thoại) dựa trên quyết định của AI.

## Công nghệ chính
* **Backend:** Flask (Python)
* **Database:** PostgreSQL
* **AI:** Google Gemini API (thông qua thư viện google-generativeai)
* **Scheduler:** APScheduler (chạy nền, dùng SQLAlchemyJobStore)
* **Server:** Waitress
* **Frontend (Admin):** Jinja2 Templates, HTML, CSS, (một chút JavaScript)
* **Khác:** python-dotenv, psycopg2-binary, cryptography

## Cài đặt và Chạy
1.  **Tạo môi trường ảo:**
    ```bash
    python -m venv venv
    ```
2.  **Kích hoạt môi trường ảo:**
    * Windows: `.\venv\Scripts\activate`
    * Linux/macOS: `source venv/bin/activate`
3.  **Cài đặt thư viện:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Cấu hình Môi trường:**
    * Sao chép file `.env.example` thành `.env` (nếu có).
    * Điền các thông tin cần thiết vào file `.env`:
        * Thông tin kết nối Database PostgreSQL (`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`).
        * Ít nhất một API Key của Google AI (`GOOGLE_API_KEY`).
        * Tạo và thêm khóa mã hóa `API_ENCRYPTION_KEY` (chạy `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` để tạo).
        * (Tùy chọn) Các cấu hình khác như `SECRET_KEY`.
5.  **Khởi tạo CSDL:** Chạy các lệnh SQL trong `new_automation_schema.sql` và `seed_data.sql` (nếu cần dữ liệu mẫu) vào database PostgreSQL của bạn. Đảm bảo đã tạo bảng `api_keys` và `ai_simulation_configs`, `scheduler_commands` và các ràng buộc UNIQUE.
6.  **Chạy ứng dụng:**
    ```bash
    python run.py
    ```
7.  **Truy cập:** Mở trình duyệt và vào địa chỉ hiển thị (thường là `http://localhost:5000` hoặc `http://0.0.0.0:5000`). Truy cập `/admin` để vào giao diện quản trị.

## Tính năng nổi bật
* Giao diện Admin quản lý toàn diện.
* Hệ thống Chiến lược/Giai đoạn/Luật chuyển tiếp linh hoạt.
* Tích hợp AI Gemini cho nhiều tác vụ.
* Tác vụ nền tự động (tạo đề xuất, duyệt đề xuất, xử lý lệnh).
* Mô phỏng hội thoại AI để sinh dữ liệu.
* Quản lý và xoay vòng đa API Key.
* Xử lý lỗi API (Retry/Backoff).
* Phân trang và bộ lọc cho các trang danh sách.
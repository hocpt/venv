# Các Tác vụ Nền và Lập lịch (Scheduled Tasks)

Hệ thống HPT11 sử dụng APScheduler để thực hiện các tác vụ nền tự động theo lịch trình. Điều này cho phép hệ thống thực hiện các hoạt động bảo trì, phân tích dữ liệu, hoặc các quy trình tự động khác mà không cần sự can thiệp trực tiếp của người dùng và không làm ảnh hưởng đến hiệu suất của các yêu cầu API chính.

## 1. Giới thiệu về APScheduler

APScheduler là một thư viện Python cho phép bạn lập lịch các hàm Python để thực thi vào những thời điểm cụ thể hoặc theo các khoảng thời gian định kỳ. Trong dự án này, APScheduler được cấu hình để:

* Sử dụng `SQLAlchemyJobStore` để lưu trữ thông tin về các job đã được lập lịch vào CSDL PostgreSQL (bảng `apscheduler_jobs`). Điều này đảm bảo rằng các job sẽ không bị mất nếu server khởi động lại.
* Hoạt động theo múi giờ được cấu hình (ví dụ: `SCHEDULER_TIMEZONE = 'Asia/Ho_Chi_Minh'`).

## 2. Cấu hình và Quản lý Jobs

### 2.1. Bảng `scheduled_jobs` (PostgreSQL)

Bảng này trong CSDL PostgreSQL được sử dụng để lưu trữ **cấu hình** của các tác vụ nền mà người dùng (admin) muốn hệ thống thực thi. Các trường chính bao gồm:

* `job_id` (VARCHAR, PK): ID duy nhất của cấu hình job (ví dụ: "suggestion_job", "simulation_cleanup_job").
* `job_function_path` (VARCHAR, NOT NULL): Đường dẫn Python đầy đủ đến hàm sẽ được thực thi (ví dụ: "app.background_tasks.analyze_interactions_and_suggest").
* `trigger_type` (VARCHAR, NOT NULL): Loại trigger (ví dụ: 'interval', 'cron', 'date').
* `trigger_args_str` (TEXT, NOT NULL): Một chuỗi JSON chứa các tham số cho trigger (ví dụ: `{"minutes": 30}` cho interval, hoặc `{"hour": "2", "minute": "0"}` cho cron).
* `job_args_str` (TEXT, optional): Một chuỗi JSON chứa các tham số sẽ được truyền vào `job_function_path` khi nó được thực thi.
* `is_enabled` (BOOLEAN, DEFAULT true): Cho biết cấu hình job này có được kích hoạt để scheduler nạp và chạy hay không.
* `description` (TEXT): Mô tả về mục đích của job.
* `last_run_status` (VARCHAR, optional): Trạng thái của lần chạy cuối cùng (ví dụ: 'success', 'error'). (Có thể được cập nhật bởi chính tác vụ nền).
* `last_run_time` (TIMESTAMP WITH TIME ZONE, optional): Thời điểm lần chạy cuối cùng.
* `next_scheduled_run_time` (TIMESTAMP WITH TIME ZONE, optional): Thời điểm dự kiến chạy tiếp theo (thông tin này có thể được scheduler cập nhật sau khi nạp job).

### 2.2. Bảng `scheduler_commands` (PostgreSQL)

Bảng này hoạt động như một hàng đợi lệnh (command queue) để giao tiếp với tiến trình scheduler đang chạy (`scheduler_runner.py`). Điều này cho phép ứng dụng web Flask (hoặc các tiến trình khác) yêu cầu scheduler thực hiện các hành động mà không cần tương tác trực tiếp với đối tượng scheduler.

* `command_id` (SERIAL, PK): ID của lệnh.
* `command_type` (VARCHAR, NOT NULL): Loại lệnh, ví dụ:
    * `reload_jobs`: Yêu cầu scheduler tải lại tất cả các cấu hình job từ bảng `scheduled_jobs`.
    * `run_job_now`: Yêu cầu chạy một job cụ thể ngay lập tức.
    * `add_job`: (Ít dùng nếu cấu hình qua bảng `scheduled_jobs`) Thêm một job mới vào scheduler.
    * `remove_job`: Yêu cầu xóa một job khỏi scheduler đang chạy.
    * `pause_job`: Tạm dừng một job.
    * `resume_job`: Tiếp tục một job đã tạm dừng.
    * `run_simulation`: Yêu cầu chạy một tác vụ mô phỏng AI (sử dụng bởi tính năng AI Simulations).
    * `approve_all_suggestions`: Yêu cầu chạy tác vụ tự động duyệt tất cả đề xuất AI.
    * `cancel_job`: Yêu cầu hủy một job đang chạy hoặc đã được lên lịch (sử dụng bởi AI Simulations).
* `payload` (JSONB): Dữ liệu bổ sung cho lệnh (ví dụ: `job_id` cho `run_job_now`, hoặc các tham số cho `run_simulation`).
* `status` (VARCHAR, DEFAULT 'pending'): Trạng thái của lệnh ('pending', 'processing', 'done', 'error').
* `created_at`, `processed_at`, `error_message`.

### 2.3. `scheduler_runner.py`

Đây là một script Python độc lập, có nhiệm vụ:

1.  **Khởi tạo Scheduler:** Tạo một đối tượng `BackgroundScheduler` của APScheduler với `SQLAlchemyJobStore`.
2.  **Nạp Jobs từ CSDL:** Khi khởi động, và định kỳ (hoặc khi có lệnh `reload_jobs`), nó sẽ:
    * Đọc các cấu hình job từ bảng `scheduled_jobs` có `is_enabled = true`.
    * Thêm hoặc cập nhật các job này vào đối tượng scheduler.
3.  **Xử lý Command Queue:**
    * Định kỳ kiểm tra bảng `scheduler_commands` để tìm các lệnh mới (`status = 'pending'`).
    * Thực thi các lệnh này (ví dụ: `scheduler.add_job()`, `scheduler.remove_job()`, `job.modify()`, `job.reschedule()`, hoặc chạy một job ngay lập tức bằng `scheduler.add_job` với trigger `date` là `now`).
    * Cập nhật `status` của lệnh sau khi xử lý.
4.  **Chạy Scheduler:** Gọi `scheduler.start()` để bắt đầu vòng lặp chính của scheduler, thực thi các job đã được lập lịch.
5.  **Xử lý Tắt Scheduler An toàn:** Đảm bảo `scheduler.shutdown()` được gọi khi script kết thúc.

### 2.4. Bảng `apscheduler_jobs` (PostgreSQL)

Bảng này được APScheduler tự động tạo và quản lý thông qua `SQLAlchemyJobStore`. Nó chứa trạng thái **live** của các job đang được scheduler quản lý, bao gồm `id` (job_id), `next_run_time`, `job_state` (dạng binary). **Không nên sửa đổi trực tiếp bảng này.**

## 3. Danh sách Các Tác vụ Nền Mặc định

Các tác vụ nền chính được định nghĩa trong `app/background_tasks.py` và được liệt kê trong `AVAILABLE_SCHEDULED_TASKS` (file `app/admin_routes.py`) để có thể được chọn từ giao diện admin khi thêm/sửa `scheduled_jobs`.

* **`app.background_tasks.analyze_interactions_and_suggest` (Phân tích & Đề xuất AI):**
    * **Mục đích:** Phân tích các bản ghi trong `interaction_history` mà AI chưa xem xét, sau đó gọi AI service để tạo ra các gợi ý (suggestions) về luật mới hoặc template mới.
    * **Đầu vào:** Đọc `task_states` để biết `last_analyzed_suggestion_id`. Đọc các bản ghi `interaction_history` sau ID đó có trạng thái phù hợp (ví dụ: `success_ai`, `success_ai_sim_A/B`).
    * **Xử lý:** Gọi `ai_service.suggest_rules_from_interaction_text` hoặc các hàm tương tự.
    * **Đầu ra:** Lưu các gợi ý vào bảng `ai_suggestions`. Cập nhật `last_analyzed_suggestion_id` trong `task_states`.
* **`app.background_tasks.approve_all_suggestions_task` (Tự động Duyệt Tất Cả Đề Xuất):**
    * **Mục đích:** Tự động phê duyệt tất cả các gợi ý AI đang ở trạng thái 'pending' trong bảng `ai_suggestions`.
    * **Đầu vào:** Đọc các suggestions 'pending'.
    * **Xử lý:** Với mỗi suggestion, tự động tạo rule và template tương ứng (tương tự như logic phê duyệt thủ công nhưng có thể với các giá trị mặc định).
    * **Đầu ra:** Cập nhật trạng thái các suggestions thành 'approved', tạo bản ghi mới trong `simple_rules`, `response_templates`, `template_variations`.
* **`app.background_tasks.run_ai_conversation_simulation` (Chạy Mô phỏng Hội thoại AI):**
    * **Mục đích:** Thực hiện một cuộc hội thoại mô phỏng giữa hai AI personas.
    * **Đầu vào:** Nhận các tham số từ `job_args_str` (được định nghĩa trong `scheduled_jobs` hoặc payload của lệnh `run_simulation`), bao gồm `persona_a_id`, `persona_b_id`, `log_account_id_a`, `log_account_id_b`, `strategy_id` (nếu cần cho ngữ cảnh hội thoại), `max_turns`, `starting_prompt`, `sim_thread_id_base`, `sim_goal`.
    * **Xử lý:** Mô phỏng cuộc hội thoại từng lượt, gọi AI service cho mỗi lượt nói.
    * **Đầu ra:** Ghi lại từng lượt nói của cả hai personas vào bảng `interaction_history` sử dụng các `log_account_id` và `sim_thread_id_base` đã cung cấp. Cập nhật trạng thái của lệnh `run_simulation` trong `scheduler_commands` thành 'done' hoặc 'error'.

## 4. Quản lý qua Giao diện Admin (`/admin/scheduled-jobs`)

Trang quản trị cung cấp các chức năng sau:

* **Xem danh sách Cấu hình Jobs:** Hiển thị các job đã được cấu hình trong bảng `scheduled_jobs`, bao gồm `job_id`, `function_path`, trigger, trạng thái `is_enabled`, mô tả.
* **Xem Trạng thái Live:** Hiển thị thời gian chạy kế tiếp (`next_run_time`) của các job đang được APScheduler quản lý (lấy từ bảng `apscheduler_jobs`) và trạng thái của chúng (Scheduled, Paused, Not Scheduled/Error).
* **Thêm Cấu hình Job Mới:** Cho phép admin định nghĩa một job mới bằng cách chọn `job_function_path` từ `AVAILABLE_SCHEDULED_TASKS_LIST`, đặt `job_id`, chọn `trigger_type`, nhập `trigger_args_str` (JSON), `job_args_str` (JSON, đặc biệt quan trọng khi job là `run_ai_conversation_simulation` để chọn `simulation_config_id`), mô tả, và trạng thái `is_enabled`.
* **Sửa Cấu hình Job:** Cho phép chỉnh sửa các thông tin của một cấu hình job đã có (ngoại trừ `job_id` và `job_function_path`).
* **Xóa Cấu hình Job:** Xóa một cấu hình job khỏi bảng `scheduled_jobs`. **Lưu ý:** Hành động này chỉ xóa cấu hình. Nếu job đang chạy trong scheduler, nó có thể cần một lệnh `remove_job` gửi đến `scheduler_commands` hoặc khởi động lại `scheduler_runner.py` để loại bỏ hoàn toàn. Hiện tại, logic xóa chỉ xóa khỏi DB.
* **Bật/Tắt Cấu hình Job:** Thay đổi giá trị `is_enabled` của một cấu hình job trong bảng `scheduled_jobs`. Tương tự như xóa, việc này cần scheduler tải lại cấu hình (ví dụ, thông qua lệnh `reload_jobs` hoặc khởi động lại `scheduler_runner.py`) để có hiệu lực đối với scheduler đang chạy. Hiện tại, logic chỉ cập nhật DB.
* **Chạy Job Ngay (Run Now):** Đối với một số job cụ thể như `suggestion_job`, có nút "Run Now" để gửi lệnh `run_suggestion_job_now` vào `scheduler_commands`, yêu cầu `scheduler_runner.py` thực thi job đó ngay lập tức (ngoài lịch trìnhปกติ).

**Lưu ý quan trọng về việc áp dụng thay đổi:**
Do `scheduler_runner.py` chạy như một tiến trình riêng biệt, các thay đổi về cấu hình job (Thêm, Sửa, Xóa, Bật/Tắt) trong bảng `scheduled_jobs` sẽ **không tự động** được áp dụng ngay lập tức cho scheduler đang chạy. Cần có một cơ chế để `scheduler_runner.py` nhận biết và tải lại các thay đổi này. Cách tiếp cận hiện tại dựa vào việc `scheduler_runner.py` xử lý lệnh `reload_jobs` từ bảng `scheduler_commands` hoặc việc khởi động lại tiến trình scheduler.
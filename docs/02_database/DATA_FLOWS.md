```markdown
# Các Luồng Dữ liệu Chính

## 1. Luồng Xử lý Yêu cầu Trả lời từ Client (Ví dụ: Mobile App)

1.  **Client Gửi Yêu cầu:**
    * Ứng dụng di động gửi một HTTP POST request đến endpoint `/receive_content_for_reply` trên Flask backend.
    * Payload JSON chứa: `account_id`, `received_text`, `app` (tên ứng dụng), `thread_id`.
2.  **Flask Backend Xử lý (trong `app/routes.py` -> `handle_receive_content`):**
    * **Xác thực và Lấy Dữ liệu:** Kiểm tra dữ liệu đầu vào.
    * **Lấy Thông tin Tài khoản:** Truy vấn PostgreSQL (qua `database.py`) để lấy chi tiết tài khoản, bao gồm `default_strategy_id` và `default_persona_id`.
    * **Xác định Chiến lược và Giai đoạn:** Lấy `strategy_id` từ tài khoản (hoặc default). Lấy `last_stage` từ PostgreSQL cho `thread_id` hoặc `initial_stage` của strategy.
    * **Phát hiện Ý định:** Gọi `ai_service.detect_user_intent_with_ai` (truyền `received_text` và `persona_id`).
    * **Ghi Log Nhận:** Gọi `database.log_interaction_received` để lưu thông tin ban đầu vào PostgreSQL.
    * **Tìm Luật Chuyển tiếp:** Gọi `database.find_transition` dựa trên `current_stage_id` và `user_intent`.
        * **Nếu tìm thấy transition và có template:** Lấy `response_template_ref`, truy vấn `database.get_template_variations`, chọn một variation và tạo `reply_text`. Đặt status `success_strategy_template`.
        * Cập nhật `next_action_suggestion` nếu có.
    * **Gọi AI nếu không có luật/template:**
        * Chuẩn bị `prompt_data` (bao gồm thông tin tài khoản, lịch sử chat từ `database.get_formatted_history`, etc.).
        * Gọi `ai_service.generate_reply_with_ai` (truyền `prompt_data` và `persona_id`).
        * Xử lý `ai_reply` và `ai_status` từ AI.
    * **Cập nhật Log Cuối cùng:** Gọi `database.update_interaction_log` với `reply_text`, `status` cuối cùng, và `next_stage_id`.
3.  **Flask Backend Trả Phản hồi:**
    * Trả về JSON response cho client chứa `reply_text`, `status`, và `next_action` (nếu có).

## 2. Luồng Điều khiển Thiết bị (Control/MainLoop Strategy)

1.  **Client (Thiết bị) Yêu cầu Gói Chiến lược:**
    * Thiết bị gửi yêu cầu đến một endpoint như `/phone/request_control_package` (cần xác định endpoint cụ thể từ `app/phone/routes.py`). Payload có thể chứa `device_id`, `account_id`, `current_task_assignment_id`.
2.  **Flask Backend Xử lý (trong `app/phone/controller.py` -> `compile_strategy_package` hoặc tương tự):**
    * **Xác định Strategy:** Dựa trên `task_assignment` hoặc `device_default_mainloop_strategy`.
    * **Truy vấn CSDL (PostgreSQL):**
        * Lấy chi tiết `strategy` (ví dụ: `initial_stage_id`).
        * Lấy tất cả `stages` thuộc strategy đó.
        * Lấy tất cả `transitions` (action sequence) thuộc strategy đó.
    * **Biên dịch Gói JSON:** Tạo một cấu trúc JSON chứa thông tin strategy, stages, và transitions đã được xử lý và định dạng cho client dễ hiểu.
        * Thông tin mỗi stage: `stage_id`, `description`, `identifying_elements` (nếu là Control Strategy).
        * Thông tin mỗi transition: `current_stage_id`, `user_intent` (trigger), `priority`, `conditions` (loại, giá trị), `next_stage_id`, `action` (macro code, params), `response_template_ref` (nếu có), `loop_config`.
3.  **Flask Backend Trả Gói JSON:**
    * Gửi gói JSON đã biên dịch về cho thiết bị.
4.  **Client (Thiết bị) Thực thi Chiến lược:**
    * Phân tích gói JSON.
    * Bắt đầu từ `initial_stage_id`.
    * **Tại mỗi stage:**
        * Thực hiện hành động `on_stage_entry` (nếu có).
        * Quan sát trạng thái UI, phát hiện các element (nếu là Control/MainLoop).
        * Chờ trigger (ví dụ: element xuất hiện, user input, API callback).
        * **Khi trigger khớp với `user_intent` của một transition:**
            * Kiểm tra `conditions` của transition.
            * Nếu điều kiện thỏa mãn và priority cao nhất:
                * Thực thi `action` (run macro, gửi input, click, etc.).
                * Nếu có `response_template_ref`, hiển thị nội dung (ít dùng cho Control).
                * Chuyển sang `next_stage_id`.
                * Xử lý vòng lặp (`loop_config`) nếu có.
    * **Gửi Log Trạng thái:** Thiết bị có thể gửi log về trạng thái thực thi, kết quả macro, hoặc trạng thái UI hiện tại về backend (ví dụ: endpoint `/phone/log_ui_state`).
5.  **Flask Backend Nhận Log từ Thiết bị:**
    * Lưu log vào PostgreSQL (bảng `task_assignment_logs` hoặc tương tự).
    * Cập nhật trạng thái `task_assignment` (ví dụ: `running`, `completed`, `error`).

## 3. Luồng Phân tích và Đề xuất AI (Tác vụ Nền)

1.  **APScheduler Kích hoạt Tác vụ:**
    * Job `analyze_interactions_and_suggest` (trong `app/background_tasks.py`) được kích hoạt theo lịch.
2.  **Tác vụ Nền Thực thi:**
    * **Lấy Tương tác Chưa Phân tích:** Truy vấn PostgreSQL (qua `database.py`) để lấy các bản ghi `interaction_history` có status nhất định (ví dụ: `success_ai`) và chưa được xử lý (dựa trên `last_processed_interaction_id` lưu trong `task_states`).
    * **Gọi AI Service:** Với mỗi nhóm tương tác (ví dụ: theo `thread_id` hoặc theo cặp `account_id` - `user_intent`), gọi `ai_service.suggest_new_rules_from_interactions` (hoặc hàm tương tự). Hàm này sẽ:
        * Chuẩn bị prompt dựa trên các tương tác.
        * Yêu cầu AI tạo ra đề xuất về `keywords`, `category`, `template_text`, `template_ref`.
    * **Lưu Đề xuất:** Nếu AI trả về đề xuất hợp lệ, lưu vào bảng `ai_suggestions` trong PostgreSQL với status `pending`.
    * **Cập nhật `last_processed_interaction_id`:** Ghi lại ID của tương tác cuối cùng đã xử lý.

## 4. Luồng Upload Ảnh chụp màn hình và Xử lý UI State (App Mapping)

1.  **Client (Thiết bị) Chụp Ảnh và Gửi Dữ liệu:**
    * Sau một hành động hoặc theo định kỳ, thiết bị chụp ảnh màn hình.
    * Thu thập thông tin các phần tử UI trên màn hình hiện tại (text, ID, bounds, class, etc.).
    * Nén dữ liệu UI thành JSON.
    * Gửi ảnh và JSON state về backend qua API (ví dụ: `/phone/upload_ui_state` hoặc một endpoint riêng cho ảnh `/api/upload/screenshot` và một cho state).
        * Form data cho ảnh có thể chứa: `file` (ảnh), `filename` (tên file client tự gen, ví dụ UUID.png), `app_name`.
2.  **Flask Backend Xử lý (trong `app/phone/routes.py` hoặc `app/routes.py`):**
    * **Lưu Ảnh:**
        * Lưu file ảnh vào thư mục `SCREENSHOT_STORAGE_PATH/app_name/filename.png`.
    * **Xử lý UI State JSON:**
        * Parse JSON nhận được.
        * **Tạo/Cập nhật Screen Node trong Neo4j:** (Logic trong `app/phone/controller.py` hoặc `app/graph_db.py`)
            * Tính toán `screen_id` (ví dụ: hash của cấu trúc element hoặc activity name + checksum).
            * Kiểm tra xem `screen_id` đã tồn tại cho `app_name` đó chưa.
            * Nếu chưa, tạo Node `:Screen` mới với các thuộc tính: `screen_id`, `app_name`, `activity_name`, `screenshot_path` (tên file đã lưu), `element_count`, `status` ('unknown' hoặc 'new'), `created_at`, `last_seen`, `width`, `height` (kích thước ảnh).
            * Nếu đã tồn tại, cập nhật `last_seen`, `screenshot_path` (nếu mới hơn), `element_count`.
        * **Lưu Chi tiết UI State vào PostgreSQL:** (Bảng `detailed_ui_states` hoặc tương tự)
            * Lưu `screen_id`, `timestamp`, và toàn bộ JSON string của UI state. Điều này giúp truy vấn lại các element sau này.
        * **(Tùy chọn) Phân loại Element bằng AI:** Gọi `ai_service.suggest_element_classifications` để gợi ý phân loại cho các element mới. Lưu kết quả này vào `element_classifications` trong PostgreSQL hoặc trực tiếp vào Neo4j node properties.
        * **Tạo Transition Edge (nếu có thông tin hành động trước đó):**
            * Nếu request này là kết quả của một hành động từ màn hình A sang màn hình B, tạo một Edge `:TRANSITION` từ Node A sang Node B trong Neo4j.
            * Thuộc tính của Edge: `actionType` (click, input), `element_id` (của element tương tác), `macro_code` (nếu chạy macro), `params_json_str`, `status` ('provisional').
3.  **Admin UI Hiển thị (Trang App Mapping Viewer):**
    * Gọi API `/api/mapping_data?app_name=<app_name>` (trong `app/admin_routes.py`).
    * API này truy vấn Neo4j (qua `graph_db.py`) để lấy tất cả Nodes `:Screen` và Edges `:TRANSITION` cho `app_name` đã chọn.
    * Dữ liệu được trả về dưới dạng JSON phù hợp cho Cytoscape.js để vẽ đồ thị.
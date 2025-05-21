# Tích hợp AI (AI Integration)

Hệ thống HPT11 tích hợp Trí tuệ Nhân tạo (AI), cụ thể là mô hình Gemini của Google, để nâng cao khả năng tương tác, tự động hóa và đưa ra quyết định thông minh. Các khía cạnh chính của việc tích hợp AI bao gồm: AI Personas, Prompt Templates, AI Playground, Gợi ý từ AI, và Mô phỏng Hội thoại AI.

Việc quản lý API key cho các dịch vụ AI được thực hiện thông qua trang "Quản lý API Keys" (`/admin/api-keys`) và lưu trong bảng `api_keys` (giá trị key được mã hóa).

## 1. AI Personas (Tính cách AI)

* **Mục đích:** AI Personas cho phép định nghĩa các "tính cách" hoặc "vai trò" khác nhau cho AI. Mỗi Persona có thể có một `base_prompt` (prompt nền tảng) riêng, `model_name` (tên model AI sử dụng, ví dụ: 'gemini-pro'), và `generation_config` (cấu hình sinh văn bản như temperature, top_p, top_k, max_output_tokens). Điều này giúp AI có những phản hồi phù hợp với từng ngữ cảnh hoặc mục tiêu cụ thể.
* **Lưu trữ:** Thông tin về AI Personas được lưu trong bảng `ai_personas` của CSDL PostgreSQL. Các trường chính bao gồm:
    * `persona_id` (VARCHAR, PK): ID duy nhất của Persona.
    * `name` (VARCHAR, UNIQUE): Tên gợi nhớ của Persona.
    * `description` (TEXT): Mô tả chi tiết.
    * `base_prompt` (TEXT): Prompt nền tảng, hướng dẫn chung cho AI về vai trò và cách ứng xử của Persona này.
    * `model_name` (VARCHAR): Tên model AI được sử dụng (ví dụ: "gemini-1.0-pro", "gemini-1.5-pro-latest").
    * `generation_config` (JSONB): Cấu hình sinh văn bản cho model (ví dụ: `{"temperature": 0.7, "max_output_tokens": 2048}`).
* **Sử dụng:**
    * Khi hệ thống cần AI tạo phản hồi (trong `handle_receive_content`) hoặc đưa ra gợi ý, một `persona_id` sẽ được sử dụng.
    * `persona_id` này có thể được lấy từ `default_persona_id` trong thông tin tài khoản (`accounts` table) hoặc `DEFAULT_REPLY_PERSONA_ID` từ file cấu hình `config.py` nếu tài khoản không có thiết lập riêng.
    * Module `ai_service.py` sử dụng thông tin Persona để tương tác với model AI.
* **Quản lý:** Admin có thể Xem, Thêm, Sửa, Xóa các AI Personas thông qua giao diện tại `/admin/ai-personas`.

## 2. Prompt Templates (Mẫu Prompt)

* **Mục đích:** Prompt Templates cung cấp các mẫu văn bản chuẩn hóa để xây dựng các prompts hoàn chỉnh gửi đến mô hình AI cho các tác vụ cụ thể. Điều này giúp đảm bảo tính nhất quán và dễ dàng quản lý các loại yêu cầu khác nhau gửi đến AI.
* **Lưu trữ:** Thông tin về Prompt Templates được lưu trong bảng `prompt_templates` của CSDL PostgreSQL. Các trường chính:
    * `prompt_template_id` (SERIAL, PK): ID tự tăng.
    * `name` (VARCHAR, UNIQUE): Tên định danh cho template (ví dụ: "generate_reply_default", "suggest_rule_from_interaction").
    * `task_type` (VARCHAR): Loại tác vụ mà template này dùng cho (ví dụ: 'generate_reply', 'suggest_rule', 'detect_intent', 'other'). Danh sách các `PROMPT_TASK_TYPES` hợp lệ được định nghĩa trong `admin_routes.py`.
    * `template_content` (TEXT): Nội dung của mẫu prompt, có thể chứa các placeholder (ví dụ: `{{received_text}}`, `{{history}}`) sẽ được thay thế bằng dữ liệu thực tế khi sử dụng.
* **Sử dụng:** Module `ai_service.py` (cụ thể là hàm `_get_prompt_template_content` và các hàm gọi nó như `generate_reply_with_ai`, `suggest_rules_from_interaction_text`, `detect_user_intent_with_ai`) sẽ truy vấn bảng `prompt_templates` để lấy `template_content` dựa trên `task_type` (hoặc một `name` cụ thể). Sau đó, nó sẽ điền các giá trị từ `prompt_data` vào các placeholder trong template để tạo ra prompt cuối cùng gửi đến AI model.
* **Quản lý:** Admin có thể Xem, Thêm, Sửa, Xóa các Prompt Templates thông qua giao diện tại `/admin/prompt-templates`.

## 3. AI Playground (Sân chơi AI)

* **Mục đích:** Trang `/admin/ai-playground` cung cấp một giao diện tiện ích cho phép quản trị viên tương tác (chat) trực tiếp với mô hình AI đã cấu hình.
* **Chức năng:**
    * Người dùng nhập một yêu cầu (prompt) vào ô văn bản.
    * Có thể chọn một `AI Persona` từ danh sách thả xuống để AI sử dụng `base_prompt` và `generation_config` của Persona đó. Nếu không chọn, Persona mặc định (hoặc không có Persona cụ thể) sẽ được sử dụng.
    * Hệ thống gửi yêu cầu đến `ai_service.call_generative_model` (truyền `persona_id` đã chọn).
    * Phản hồi từ AI được hiển thị trên giao diện.
* **Lợi ích:** Giúp kiểm thử nhanh các Persona, thử nghiệm các loại prompt khác nhau, và hiểu rõ hơn về khả năng của mô hình AI.

## 4. AI Suggestions (Gợi ý từ AI)

* **Mục đích:** Tự động hóa việc phân tích các tương tác của người dùng và đề xuất các luật (Simple Rules) hoặc mẫu phản hồi (Templates & Variations) mới để cải thiện hiệu quả của hệ thống.
* **Luồng hoạt động:**
    1.  **Tác vụ nền `analyze_interactions_and_suggest`:**
        * Được lập lịch chạy định kỳ (thông qua `scheduled_jobs` và `scheduler_runner.py`).
        * Truy vấn bảng `interaction_history` để tìm các tương tác chưa được phân tích (ví dụ: dựa trên `last_analyzed_suggestion_id` trong `task_states`).
        * Đối với mỗi tương tác phù hợp, nó chuẩn bị dữ liệu và gọi hàm `ai_service.suggest_rules_from_interaction_text` (hoặc một hàm tương tự) để yêu cầu AI đưa ra gợi ý.
        * AI có thể gợi ý:
            * Từ khóa (`suggested_keywords`).
            * Danh mục (`suggested_category`).
            * Tham chiếu template (`suggested_template_ref`).
            * Nội dung template mới (`suggested_template_text`).
    2.  **Lưu trữ Gợi ý:** Các gợi ý từ AI được lưu vào bảng `ai_suggestions` trong CSDL PostgreSQL với trạng thái ban đầu là `pending`.
    3.  **Quản lý Gợi ý qua Admin UI (`/admin/suggestions`):**
        * Hiển thị danh sách các gợi ý đang ở trạng thái `pending`.
        * Admin có thể **Xem chi tiết** từng gợi ý.
        * **Sửa đổi và Phê duyệt (`/admin/suggestions/<id>/edit`):** Admin có thể chỉnh sửa các trường do AI gợi ý (keywords, category, template_ref, template_text, priority) trước khi phê duyệt. Khi phê duyệt, hệ thống sẽ:
            * Thêm template mới (nếu `template_ref` chưa tồn tại) và variation đầu tiên vào bảng `response_templates` và `template_variations`.
            * Thêm rule mới vào bảng `simple_rules` với các thông tin đã sửa.
            * Cập nhật trạng thái của suggestion thành `approved`.
        * **Phê duyệt Trực tiếp (`/admin/suggestions/<id>/approve-direct`):** Phê duyệt gợi ý mà không cần sửa đổi, tạo rule và template dựa trên các giá trị AI đề xuất.
        * **Từ chối (`/admin/suggestions/<id>/reject`):** Cập nhật trạng thái của suggestion thành `rejected`.
        * **Duyệt Tất cả Đề xuất (`/admin/suggestions/approve-all-start-job`):** Kích hoạt một tác vụ nền (`approve_all_suggestions_task`) để tự động phê duyệt tất cả các gợi ý `pending` (có thể với một số điều kiện mặc định).

## 5. AI Conversation Simulations (Mô phỏng Hội thoại AI)

* **Mục đích:** Cho phép tạo ra các cuộc hội thoại mô phỏng giữa hai AI Personas khác nhau để kiểm thử các kịch bản tương tác, đánh giá hiệu quả của các Persona và Strategy, hoặc thu thập dữ liệu hội thoại mẫu.
* **Lưu trữ Cấu hình (`ai_simulation_configs`):**
    * Bảng này lưu trữ các cấu hình mô phỏng đã được người dùng định nghĩa.
    * **Thuộc tính:** `config_id`, `config_name`, `description`, `persona_a_id`, `persona_b_id`, `log_account_id_a`, `log_account_id_b`, `strategy_id` (chiến lược chung cho cả hai, hoặc có thể mở rộng để mỗi persona có strategy riêng), `max_turns`, `starting_prompt`, `simulation_goal`, `is_enabled`.
* **Luồng hoạt động:**
    1.  **Tạo/Quản lý Cấu hình (`/admin/ai-simulations`):**
        * Admin có thể Xem, Thêm, Sửa, Xóa, Bật/Tắt các cấu hình mô phỏng.
    2.  **Chạy Mô phỏng:**
        * **Ad-hoc:** Admin có thể chạy mô phỏng trực tiếp từ form trên trang `/admin/ai-simulations` bằng cách chọn Persona A, Persona B, Account Log A/B, Strategy, và các tham số khác.
        * **Từ Cấu hình đã lưu:** Admin có thể chọn một cấu hình đã lưu và nhấn nút "Chạy".
        * **Theo lịch trình:** Một cấu hình mô phỏng có thể được liên kết với một `scheduled_job` có `job_function_path` là `app.background_tasks.run_ai_conversation_simulation` và `job_args_str` chứa các tham số của cấu hình đó.
    3.  **Thêm Lệnh vào Queue:** Khi một mô phỏng được yêu cầu chạy (ad-hoc, từ config, hoặc theo lịch), một lệnh với `command_type='run_simulation'` và payload chứa các tham số mô phỏng sẽ được thêm vào bảng `scheduler_commands`.
    4.  **Thực thi Mô phỏng (`app.background_tasks.run_ai_conversation_simulation`):**
        * Scheduler Runner sẽ nhận lệnh từ queue và thực thi hàm này.
        * Hàm mô phỏng sẽ:
            * Khởi tạo hai "agent" AI dựa trên `persona_a_id` và `persona_b_id`.
            * Bắt đầu với `starting_prompt` (Persona A nói trước).
            * Lần lượt cho Persona B rồi Persona A trả lời, tối đa `max_turns`.
            * Mỗi lượt nói của AI được tạo ra bằng cách gọi `ai_service.call_generative_model` (hoặc một hàm tương tự) với prompt là lịch sử hội thoại và lượt nói trước đó.
            * **Ghi log:** Mỗi lượt nói (cả prompt và response) của cả hai Persona được ghi vào bảng `interaction_history` với `account_id` là `log_account_id_a` và `log_account_id_b` tương ứng. `thread_id` sẽ được tạo dựa trên `sim_thread_id_base` (ví dụ: `sim_thread_scheduled_sim_123_turn_1`). `app_name` có thể là 'simulation'.
    5.  **Xem Kết quả (`/admin/simulations/results/<command_id>`):**
        * Admin có thể xem chi tiết cuộc hội thoại của một lần chạy mô phỏng bằng cách truy vấn `interaction_history` dựa trên `thread_id` (được suy ra từ `command_id` và payload của lệnh).

## 6. Chức năng Phân loại Phần tử UI (Element Classification)

* **Mục đích:** AI có thể được sử dụng để gợi ý phân loại (classification) cho các phần tử UI được thu thập từ các màn hình ứng dụng, giúp việc xây dựng PIE và hiểu màn hình nhanh hơn.
* **Luồng hoạt động:**
    1.  **Admin UI (`/admin/screen/<screen_id>/elements`):**
        * Admin xem danh sách các elements của một màn hình.
        * Có thể yêu cầu AI gợi ý classification cho các elements chưa được phân loại.
    2.  **Gọi API `/admin/api/screen/{screen_id}/suggest_classifications`:**
        * Frontend gửi danh sách các elements (với các thuộc tính như `text`, `resource_id`, `class_name`) đến API này.
    3.  **Xử lý ở Backend (`ai_service.suggest_element_classifications`):**
        * Hàm này nhận danh sách elements.
        * Với mỗi element, nó tạo một prompt phù hợp (có thể sử dụng một `Prompt Template` với `task_type='classify_element'`) để yêu cầu AI đưa ra một classification từ danh sách `VALID_CLASSIFICATIONS` (định nghĩa trong `ai_service.py`).
        * Kết quả gợi ý được trả về cho frontend.
    4.  **Hiển thị Gợi ý:** Frontend hiển thị các gợi ý classification, admin có thể chấp nhận hoặc sửa đổi trước khi lưu vào CSDL (qua API `/admin/api/element/classify`).
* **`VALID_CLASSIFICATIONS`:** Danh sách các nhãn phân loại hợp lệ cho element (ví dụ: 'button_confirm', 'input_username', 'image_avatar', 'text_title', 'link_forgot_password', 'icon_menu', 'list_item', 'advertisement', 'unclassified', 'other_interactive', 'other_static'). Được định nghĩa trong `ai_service.py`.
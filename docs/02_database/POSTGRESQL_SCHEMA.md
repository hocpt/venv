# Schema Cơ sở dữ liệu PostgreSQL

Dự án sử dụng PostgreSQL để lưu trữ dữ liệu có cấu trúc. Dưới đây là mô tả sơ bộ về các bảng chính dựa trên `automation_schema.sql` và các chức năng của hệ thống.

**(Lưu ý: Đây là tổng hợp dựa trên tên bảng và các trường thường gặp. Cần rà soát và bổ sung chi tiết từ file `automation_schema.sql` thực tế và mã nguồn `database.py`.)**

## Bảng `accounts`
Lưu trữ thông tin về các tài khoản người dùng hoặc tài khoản được quản lý.

* `account_id` (VARCHAR, PK): ID duy nhất của tài khoản.
* `platform` (VARCHAR): Nền tảng của tài khoản (ví dụ: 'tiktok', 'zalo', 'system').
* `username` (VARCHAR): Tên người dùng.
* `status` (VARCHAR): Trạng thái tài khoản (ví dụ: 'active', 'inactive').
* `notes` (TEXT): Ghi chú về tài khoản.
* `goal` (TEXT): Mục tiêu của tài khoản.
* `default_strategy_id` (VARCHAR, FK -> strategies.strategy_id): Chiến lược mặc định cho tài khoản này.
* `default_persona_id` (VARCHAR, FK -> ai_personas.persona_id): Persona AI mặc định cho tài khoản.
* `created_at` (TIMESTAMP): Thời gian tạo.
* `updated_at` (TIMESTAMP): Thời gian cập nhật lần cuối.

## Bảng `devices`
Lưu trữ thông tin về các thiết bị vật lý được kết nối hoặc quản lý.

* `device_id` (VARCHAR, PK): ID duy nhất của thiết bị (do client tự sinh hoặc admin nhập).
* `device_name` (VARCHAR): Tên gợi nhớ cho thiết bị.
* `os_info` (VARCHAR): Thông tin hệ điều hành.
* `macrodroid_version` (VARCHAR): Phiên bản Macrodroid (nếu sử dụng).
* `status` (VARCHAR): Trạng thái của thiết bị (ví dụ: 'online', 'offline', 'disabled', 'error').
* `last_seen_at` (TIMESTAMP): Thời điểm cuối cùng thiết bị gửi tín hiệu.
* `registered_at` (TIMESTAMP): Thời điểm thiết bị được đăng ký.
* `notes` (TEXT): Ghi chú thêm.
* `mainloop_strategy_id` (VARCHAR, FK -> strategies.strategy_id): Chiến lược MainLoop mặc định cho thiết bị này.

## Bảng `device_accounts`
Bảng liên kết giữa thiết bị và tài khoản (một thiết bị có thể sử dụng nhiều tài khoản, một tài khoản có thể đăng nhập trên nhiều thiết bị).

* `device_account_id` (SERIAL, PK): ID tự tăng của liên kết.
* `device_id` (VARCHAR, FK -> devices.device_id): ID của thiết bị.
* `account_id` (VARCHAR, FK -> accounts.account_id): ID của tài khoản.
* `clone_context` (VARCHAR): Thông tin về context/clone app (nếu có, ví dụ: "0", "1" cho app nhân bản).
* `app_package_name` (VARCHAR): Tên package của ứng dụng mà tài khoản này sử dụng trên thiết bị.
* `status` (VARCHAR): Trạng thái của liên kết này (ví dụ: 'active_logged_in', 'login_required', 'error').
* `linked_at` (TIMESTAMP): Thời gian tạo liên kết.
* `notes` (TEXT): Ghi chú về liên kết này.
* UNIQUE (`device_id`, `account_id`, `clone_context`, `app_package_name`)

## Bảng `simple_rules`
Lưu trữ các luật đơn giản để tìm phản hồi dựa trên keywords.

* `rule_id` (SERIAL, PK): ID tự tăng của luật.
* `trigger_keywords` (TEXT): Các từ khóa kích hoạt luật (phân tách bằng dấu phẩy).
* `category` (VARCHAR): Danh mục của luật (tùy chọn).
* `response_template_ref` (VARCHAR, FK -> response_templates.template_ref): Tham chiếu đến mẫu trả lời.
* `priority` (INTEGER): Độ ưu tiên của luật (số nhỏ hơn ưu tiên cao hơn).
* `notes` (TEXT): Ghi chú.
* `created_at` (TIMESTAMP).
* `updated_at` (TIMESTAMP).
* UNIQUE (`trigger_keywords`, `category`, `response_template_ref`)

## Bảng `response_templates`
Lưu trữ các mẫu tham chiếu cho câu trả lời.

* `template_ref` (VARCHAR, PK): ID tham chiếu duy nhất cho mẫu (ví dụ: 'greeting_01', 'price_info_general').
* `description` (TEXT): Mô tả về mẫu template.
* `category` (VARCHAR): Danh mục của template.
* `created_at` (TIMESTAMP).
* `updated_at` (TIMESTAMP).

## Bảng `template_variations`
Lưu trữ các biến thể khác nhau của một mẫu câu trả lời.

* `variation_id` (SERIAL, PK): ID tự tăng.
* `template_ref` (VARCHAR, FK -> response_templates.template_ref ON DELETE CASCADE): Tham chiếu đến mẫu gốc.
* `variation_text` (TEXT): Nội dung của biến thể.
* `created_at` (TIMESTAMP).
* `updated_at` (TIMESTAMP).

## Bảng `interaction_history`
Ghi lại lịch sử tương tác giữa hệ thống và người dùng/client.

* `history_id` (SERIAL, PK): ID tự tăng.
* `account_id` (VARCHAR, FK -> accounts.account_id): Tài khoản liên quan.
* `app_name` (VARCHAR): Tên ứng dụng client.
* `thread_id` (VARCHAR): ID của luồng hội thoại.
* `received_text` (TEXT): Nội dung nhận được từ client.
* `reply_text` (TEXT): Nội dung hệ thống trả lời.
* `strategy_id` (VARCHAR): Chiến lược được áp dụng.
* `current_stage_id` (VARCHAR): Giai đoạn hiện tại khi nhận.
* `next_stage_id` (VARCHAR): Giai đoạn tiếp theo sau khi xử lý.
* `user_intent` (VARCHAR): Ý định của người dùng được phát hiện.
* `status` (VARCHAR): Trạng thái xử lý (ví dụ: 'received', 'success_strategy_template', 'success_ai', 'error_ai_call').
* `timestamp` (TIMESTAMP): Thời điểm ghi log.
* `processed_for_suggestion` (BOOLEAN DEFAULT FALSE): Đánh dấu đã được xử lý để tạo đề xuất AI chưa.

## Bảng `ai_suggestions`
Lưu trữ các đề xuất tạo luật/template từ AI.

* `suggestion_id` (SERIAL, PK): ID tự tăng.
* `based_on_interaction_ids` (TEXT): Danh sách ID từ `interaction_history` làm cơ sở cho đề xuất.
* `suggested_keywords` (TEXT): Từ khóa AI đề xuất.
* `suggested_category` (VARCHAR): Danh mục AI đề xuất.
* `suggested_template_ref` (VARCHAR): Template ref AI đề xuất (có thể là mới hoặc hiện có).
* `suggested_template_text` (TEXT): Nội dung template AI đề xuất.
* `status` (VARCHAR): Trạng thái ('pending', 'approved', 'rejected', 'error').
* `ai_confidence` (FLOAT): Độ tin cậy của AI (nếu có).
* `created_at` (TIMESTAMP).
* `processed_at` (TIMESTAMP): Thời gian xử lý (approved/rejected).

## Bảng `strategies`
Lưu trữ định nghĩa các chiến lược (Language, Control, MainLoop).

* `strategy_id` (VARCHAR, PK): ID duy nhất của chiến lược.
* `name` (VARCHAR): Tên gợi nhớ của chiến lược.
* `description` (TEXT): Mô tả.
* `strategy_type` (VARCHAR): Loại chiến lược ('language', 'control', 'mainloop').
* `initial_stage_id` (VARCHAR, FK -> strategy_stages.stage_id): Stage bắt đầu của chiến lược này.
* `created_at` (TIMESTAMP).
* `updated_at` (TIMESTAMP).

## Bảng `strategy_stages`
Lưu trữ các giai đoạn (states) trong một chiến lược.

* `id` (SERIAL, PK): ID tự tăng.
* `stage_id` (VARCHAR): ID duy nhất của stage trong phạm vi strategy (ví dụ: 'S1_GREET', 'S2_ASK_PRICE').
* `strategy_id` (VARCHAR, FK -> strategies.strategy_id ON DELETE CASCADE): Chiến lược cha.
* `description` (TEXT): Mô tả stage.
* `stage_order` (INTEGER): Thứ tự của stage (tùy chọn, để sắp xếp).
* `identifying_elements_json` (JSONB): (Chỉ dùng cho Control/MainLoop stage) Mảng JSON chứa các element đặc trưng để nhận diện stage này trên UI.
* `created_at` (TIMESTAMP).
* `updated_at` (TIMESTAMP).
* UNIQUE (`strategy_id`, `stage_id`)

## Bảng `stage_transitions`
Lưu trữ các luật chuyển tiếp giữa các stage trong một chiến lược.

* `transition_id` (SERIAL, PK): ID tự tăng.
* `strategy_id` (VARCHAR, FK -> strategies.strategy_id ON DELETE CASCADE): Chiến lược chứa transition này.
* `current_stage_id` (VARCHAR): Stage hiện tại (tham chiếu đến `strategy_stages.stage_id` - cần FK nếu `stage_id` là duy nhất toàn cục, hoặc kiểm tra logic).
* `user_intent` (VARCHAR): Ý định của người dùng hoặc trigger (ví dụ: 'price_query', 'on_stage_entry', 'element_clicked:button_buy').
* `priority` (INTEGER DEFAULT 0): Độ ưu tiên của transition.
* `condition_type` (VARCHAR): Loại điều kiện (ví dụ: 'element_exists_text', 'variable_equals').
* `condition_value` (TEXT): Giá trị của điều kiện.
* `next_stage_id` (VARCHAR): Stage tiếp theo nếu transition được kích hoạt.
* `response_template_ref` (VARCHAR, FK -> response_templates.template_ref): (Cho Language Strategy) Template trả lời.
* `action_macro_code` (VARCHAR, FK -> macro_definitions.macro_code): (Cho Control/MainLoop Strategy) Macro code để thực thi.
* `action_params_str` (TEXT): Chuỗi JSON chứa tham số cho macro.
* `loop_type` (VARCHAR): Loại vòng lặp ('repeat_n', 'while_condition_met', 'for_each').
* `loop_count` (INTEGER): Số lần lặp (cho 'repeat_n').
* `loop_condition_type` (VARCHAR): Loại điều kiện cho vòng lặp 'while'.
* `loop_condition_value` (TEXT): Giá trị điều kiện cho vòng lặp 'while'.
* `loop_target_selector_str` (TEXT): Chuỗi JSON selector cho 'for_each'.
* `loop_variable_name` (VARCHAR): Tên biến lưu phần tử lặp cho 'for_each'.
* `notes` (TEXT): Ghi chú thêm.
* `created_at` (TIMESTAMP).
* `updated_at` (TIMESTAMP).

## Bảng `ai_personas`
Lưu trữ các "tính cách" cho AI để tùy chỉnh prompt và hành vi.

* `persona_id` (VARCHAR, PK): ID duy nhất của persona.
* `name` (VARCHAR, UNIQUE): Tên gợi nhớ.
* `description` (TEXT): Mô tả.
* `base_prompt` (TEXT NOT NULL): Prompt nền tảng cho persona này.
* `model_name` (VARCHAR): Tên model AI cụ thể (nếu cần).
* `generation_config_json` (JSONB): Cấu hình sinh của model (temperature, top_p, etc.).
* `created_at` (TIMESTAMP).
* `updated_at` (TIMESTAMP).

## Bảng `prompt_templates`
Lưu trữ các mẫu prompt cho các tác vụ AI khác nhau.

* `prompt_template_id` (SERIAL, PK): ID tự tăng.
* `name` (VARCHAR, UNIQUE): Tên gợi nhớ của mẫu prompt.
* `task_type` (VARCHAR): Loại tác vụ mà prompt này dùng (ví dụ: 'generate_reply', 'suggest_rule', 'detect_intent').
* `template_content` (TEXT NOT NULL): Nội dung của mẫu prompt (sử dụng Jinja2 hoặc f-string syntax).
* `created_at` (TIMESTAMP).
* `updated_at` (TIMESTAMP).

## Bảng `scheduled_jobs` (Cấu hình cho APScheduler)
Lưu trữ cấu hình cho các tác vụ nền được lên lịch.

* `job_id` (VARCHAR, PK): ID duy nhất của job (ví dụ: 'suggestion_job', 'simulation_config_123').
* `job_function_path` (VARCHAR NOT NULL): Đường dẫn Python đầy đủ đến hàm thực thi (ví dụ: 'app.background_tasks.analyze_interactions_and_suggest').
* `trigger_type` (VARCHAR NOT NULL): Loại trigger ('interval', 'cron', 'date').
* `trigger_args_str` (TEXT NOT NULL): Chuỗi JSON chứa các tham số cho trigger (ví dụ: `{"minutes": 30}` cho interval, `{"day_of_week": "mon-fri", "hour": 9}` cho cron).
* `job_args_str` (TEXT): Chuỗi JSON chứa các tham số cố định truyền vào hàm job (nếu có).
* `description` (TEXT): Mô tả job.
* `is_enabled` (BOOLEAN DEFAULT TRUE): Job có đang được bật hay không.
* `last_run_at` (TIMESTAMP): Thời điểm chạy thành công lần cuối (do scheduler tự cập nhật hoặc logic của bạn).
* `next_run_time_manual` (TIMESTAMP): Thời gian chạy dự kiến tiếp theo (do scheduler tự cập nhật hoặc logic của bạn).
* `created_at` (TIMESTAMP).
* `updated_at` (TIMESTAMP).

## Bảng `scheduler_commands`
Hàng đợi lệnh cho scheduler để thực hiện các hành động như reload jobs, run job now, cancel job.

* `command_id` (SERIAL, PK).
* `command_type` (VARCHAR NOT NULL): Loại lệnh (ví dụ: 'reload_jobs', 'run_job_now', 'cancel_job', 'run_simulation', 'approve_all_suggestions').
* `payload_json` (JSONB): Dữ liệu kèm theo lệnh.
* `status` (VARCHAR DEFAULT 'pending'): Trạng thái ('pending', 'processing', 'done', 'error').
* `error_message` (TEXT): Thông báo lỗi nếu có.
* `created_at` (TIMESTAMP).
* `processed_at` (TIMESTAMP).

## Bảng `task_states` (Lưu trạng thái xử lý của các tác vụ lặp lại)
* `task_name` (VARCHAR, PK): Tên duy nhất của tác vụ (ví dụ: 'suggestion_job_last_id').
* `state_value` (TEXT): Giá trị trạng thái (ví dụ: ID của bản ghi cuối cùng đã xử lý).
* `updated_at` (TIMESTAMP).

## Bảng `ai_simulation_configs`
Lưu trữ các cấu hình mô phỏng hội thoại AI đã lưu.

* `config_id` (SERIAL, PK).
* `config_name` (VARCHAR UNIQUE NOT NULL): Tên gợi nhớ cho cấu hình.
* `description` (TEXT).
* `persona_a_id` (VARCHAR, FK -> ai_personas.persona_id).
* `persona_b_id` (VARCHAR, FK -> ai_personas.persona_id).
* `log_account_id_a` (VARCHAR, FK -> accounts.account_id): Account để ghi log cho Persona A.
* `log_account_id_b` (VARCHAR, FK -> accounts.account_id): Account để ghi log cho Persona B.
* `strategy_id` (VARCHAR, FK -> strategies.strategy_id): Chiến lược hội thoại áp dụng.
* `max_turns` (INTEGER DEFAULT 5).
* `starting_prompt` (TEXT): Câu mở đầu cho mô phỏng.
* `simulation_goal` (TEXT): Mục tiêu của mô phỏng này.
* `is_enabled` (BOOLEAN DEFAULT TRUE): Cấu hình này có đang được bật để lên lịch không.
* `created_at` (TIMESTAMP).
* `updated_at` (TIMESTAMP).

## Bảng `api_keys`
Lưu trữ các API key cho dịch vụ bên ngoài (ví dụ: Google Gemini).

* `key_id` (SERIAL, PK).
* `key_name` (VARCHAR UNIQUE NOT NULL): Tên gợi nhớ cho key.
* `provider` (VARCHAR NOT NULL): Nhà cung cấp (ví dụ: 'google_gemini').
* `encrypted_api_key` (TEXT NOT NULL): Giá trị API key đã được mã hóa.
* `status` (VARCHAR DEFAULT 'active'): Trạng thái ('active', 'inactive', 'rate_limited').
* `notes` (TEXT).
* `created_at` (TIMESTAMP).
* `updated_at` (TIMESTAMP).

## Bảng `macro_definitions`
Định nghĩa các macro code có thể được gọi từ Control/MainLoop strategies.

* `macro_code` (VARCHAR, PK): Mã định danh duy nhất cho macro (ví dụ: 'UI_CLICK_ELEMENT', 'SEND_MESSAGE').
* `description` (TEXT): Mô tả chức năng của macro.
* `app_target` (VARCHAR): Ứng dụng mục tiêu ('system', 'generic', 'tiktok', etc.) hoặc 'all'.
* `params_schema_json` (JSONB): (Tùy chọn) Schema JSON mô tả các tham số đầu vào mà macro này chấp nhận.
* `notes` (TEXT).
* `created_at` (TIMESTAMP).
* `updated_at` (TIMESTAMP).

## Bảng `task_assignments`
Giao việc (chiến lược) cho một tài khoản trên một thiết bị cụ thể.

* `assignment_id` (SERIAL, PK).
* `device_account_id` (INTEGER, FK -> device_accounts.device_account_id ON DELETE CASCADE): Liên kết device-account cụ thể.
* `strategy_id` (VARCHAR, FK -> strategies.strategy_id): Chiến lược được giao.
* `priority` (INTEGER DEFAULT 0).
* `status` (VARCHAR DEFAULT 'pending'): Trạng thái ('pending', 'assigned', 'running', 'completed', 'error', 'cancelled', 'paused').
* `target_data_json` (JSONB): Dữ liệu mục tiêu cho task (ví dụ: URL, user ID để tương tác).
* `result_data_json` (JSONB): Kết quả của task sau khi hoàn thành.
* `notes` (TEXT).
* `created_at` (TIMESTAMP).
* `assigned_at` (TIMESTAMP): Thời điểm được gán cho thiết bị.
* `started_at` (TIMESTAMP): Thời điểm bắt đầu chạy.
* `completed_at` (TIMESTAMP): Thời điểm hoàn thành/lỗi/hủy.
* `schedule_start_time` (TIMESTAMP): Thời gian dự kiến bắt đầu (nếu lên lịch).
* `schedule_end_time` (TIMESTAMP): Thời gian dự kiến kết thúc/hết hạn.

## Bảng `task_assignment_logs`
Ghi log chi tiết các bước thực thi của một task assignment.

* `log_id` (SERIAL, PK).
* `assignment_id` (INTEGER, FK -> task_assignments.assignment_id ON DELETE CASCADE).
* `timestamp` (TIMESTAMP DEFAULT CURRENT_TIMESTAMP).
* `log_level` (VARCHAR DEFAULT 'INFO'): Mức độ log ('INFO', 'DEBUG', 'WARN', 'ERROR').
* `message` (TEXT): Nội dung log.
* `current_stage_id` (VARCHAR): Stage hiện tại khi log được ghi.
* `action_taken` (TEXT): Hành động vừa thực hiện.
* `received_ui_state_json` (JSONB): (Tùy chọn) Trạng thái UI nhận được từ thiết bị tại thời điểm log.

## Bảng `screen_definitions` (PIE - Primary Identifying Elements)
Định nghĩa các màn hình logic và các phần tử nhận dạng chính của chúng.

* `definition_id` (SERIAL, PK).
* `app_name` (VARCHAR NOT NULL): Tên ứng dụng (ví dụ: 'com.tiktok.app').
* `activity_name` (VARCHAR): (Tùy chọn) Tên activity nếu PIE chỉ áp dụng cho activity cụ thể.
* `logical_screen_name` (VARCHAR NOT NULL): Tên logic, gợi nhớ do người dùng đặt (ví dụ: 'UserProfilePage', 'FeedScreen').
* `defined_screen_id` (VARCHAR NOT NULL): ID duy nhất cho màn hình đã định nghĩa này (ví dụ: `tiktok_profile_v1`). Dùng để map với node `:Screen(status='defined')` trong Neo4j.
* `identifying_elements_json` (JSONB NOT NULL): Mảng JSON chứa các phần tử nhận dạng chính. Mỗi phần tử là một object có `attribute` (ví dụ: 'resource_id', 'text', 'xpath'), `comparison` (ví dụ: 'equals', 'contains'), `value`.
* `description` (TEXT): Mô tả chi tiết về màn hình này.
* `conditions_json` (JSONB): (Mới) Mảng JSON chứa các điều kiện phụ trợ để phân biệt giữa các PIE có thể trùng lặp một phần. Mỗi điều kiện có `attribute`, `comparison`, `value`.
* `created_at` (TIMESTAMP).
* `updated_at` (TIMESTAMP).
* UNIQUE (`app_name`, `defined_screen_id`)
* UNIQUE (`app_name`, `logical_screen_name`)

## Bảng `element_classifications` (PostgreSQL)
Lưu trữ phân loại (classification) và trạng thái khám phá thủ công (manual_explored_override) cho các phần tử UI từ Neo4j.

* `id` (SERIAL, PK).
* `screen_id` (VARCHAR NOT NULL): ID của màn hình (khớp với `Screen.screen_id` trong Neo4j).
* `element_id` (VARCHAR NOT NULL): ID của phần tử (khớp với `element_id` trong log UI hoặc `resource-id` của Android).
* `identifier_type` (VARCHAR): Loại định danh của element_id (ví dụ: 'resource_id', 'xpath', 'description', 'text_match').
* `classification` (VARCHAR): Phân loại do AI gợi ý hoặc người dùng đặt (ví dụ: 'button_primary', 'input_text', 'icon_settings').
* `source` (VARCHAR): Nguồn gốc của phân loại ('ai_suggested', 'manual').
* `manual_explored_override` (BOOLEAN NULLABLE): `TRUE` để ép là đã khám phá, `FALSE` để ép là chưa khám phá, `NULL` để dùng logic tự động.
* `updated_at` (TIMESTAMP).
* UNIQUE (`screen_id`, `element_id`)

## Bảng `detailed_ui_states`
Lưu trữ toàn bộ JSON UI state nhận được từ client cho mỗi `screen_id` tại một thời điểm.

* `id` (SERIAL, PK).
* `screen_id` (VARCHAR NOT NULL): ID màn hình mà state này thuộc về.
* `app_name` (VARCHAR): Tên ứng dụng.
* `timestamp` (TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP): Thời điểm state này được ghi nhận.
* `ui_state_json` (JSONB NOT NULL): Toàn bộ cấu trúc JSON của UI state.
* `screenshot_filename` (VARCHAR): Tên file ảnh chụp màn hình tương ứng (nếu có).
* INDEX (`screen_id`, `timestamp` DESC)
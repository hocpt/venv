-- PostgreSQL Seed Data for HPT Automation Project
-- Version: 2025-04-23 (Final Corrected Version)
-- ASSUMES TABLES WERE CLEANLY CREATED BY THE LATEST automation_schema.sql
-- Uses BEGIN/COMMIT for deferrable constraints.

BEGIN; -- Bắt đầu Transaction

-- === Dữ liệu Cơ bản ===

INSERT INTO public.accounts (account_id, platform, username, status, default_persona_id, default_strategy_id) VALUES
('tiktok_test_1', 'tiktok', 'Test User One', 'active', NULL, NULL), -- Tạm thời NULL default_strategy_id
('system_admin', 'system', 'Admin', 'active', NULL, NULL),
('fb_test_user', 'facebook', 'FB Test Acc', 'active', NULL, NULL);

INSERT INTO public.devices (device_id, device_name, os_info, macrodroid_version, status, last_seen_at) VALUES
('test_device_001', 'Samsung A51 Test', 'Android 12, SM-A515F', '5.35', 'offline', NOW() - INTERVAL '1 hour'),
('test_device_002', 'Nox Player Test', 'Android 9, Nox', '5.30', 'offline', NOW() - INTERVAL '2 day');

INSERT INTO public.macro_definitions (macro_code, description, app_target, params_schema, notes) VALUES
('SYS_WAIT', 'Chờ một khoảng thời gian cố định', 'system', $$ {"type": "object", "properties": {"duration_ms": {"type": "integer", "description": "Thời gian chờ (ms). Bắt buộc."}}, "required": ["duration_ms"]} $$, 'Dừng thực thi X ms.'),
('APP_OPEN', 'Mở một ứng dụng bằng package name', 'system', $$ {"type": "object", "properties": {"package_name": {"type": "string", "description": "Package name của app. Bắt buộc."}}, "required": ["package_name"]} $$, NULL),
('NAV_GO_BACK', 'Nhấn nút Back hệ thống', 'system', $$ {} $$, 'Tương đương nút Back vật lý/điều hướng.'),
('UI_CLICK', 'Nhấp vào phần tử UI', 'generic', $$ {"type": "object", "properties": {"target": {"type": "object", "description": "Cách xác định mục tiêu (text, resource_id, content_description, point, xpath...)", "minProperties": 1}}, "required": ["target"]} $$, 'Nhấp vào nút, link, ảnh... Xác định bằng text, id, tọa độ, xpath...'),
('UI_INPUT_TEXT', 'Nhập text vào ô input', 'generic', $$ {"type": "object", "properties": {"target": {"type": "object", "description": "Cách xác định ô input", "minProperties": 1}, "text_to_input": {"type": "string", "description": "Nội dung cần nhập"}}, "required": ["target", "text_to_input"]} $$, 'Điền form, nhập liệu.'),
('UI_SWIPE_UP', 'Vuốt màn hình lên', 'generic', $$ {"type": "object", "properties": {"duration_ms": {"type": "integer", "default": 300}}} $$, 'Vuốt từ dưới lên để xem tiếp feed (vd: TikTok, FB Reels).'),
('SYS_LOG', 'Ghi log tùy chỉnh', 'system', $$ {"type": "object", "properties": {"message": {"type": "string"}, "log_level": {"type": "string", "default": "INFO"}}, "required": ["message"]} $$, 'Ghi log ra hệ thống (server hoặc client).');

-- === Language AI Components (Ví dụ) ===
INSERT INTO public.templates (template_ref, category, description) VALUES
('lang_greeting_1', 'greeting', 'Chào hỏi thân thiện'),
('lang_price_ask_inbox', 'price_query', 'Yêu cầu inbox để báo giá');

INSERT INTO public.template_variations (template_ref, variation_text) VALUES
('lang_greeting_1', 'Chào bạn! Shop có thể giúp gì cho bạn ạ?'),
('lang_greeting_1', 'Xin chào, cảm ơn bạn đã quan tâm!'),
('lang_price_ask_inbox', 'Bạn vui lòng inbox để shop báo giá chi tiết nhé!'),
('lang_price_ask_inbox', 'Dạ bạn check inbox giúp shop nha.');

INSERT INTO public.ai_personas (persona_id, name, description, base_prompt, model_name, generation_config, fallback_template_ref) VALUES
('general_assistant', 'Trợ lý Chung', 'Trợ lý AI cơ bản, hữu ích và trung lập.', 'You are a helpful assistant.', 'models/gemini-1.5-flash-latest', $$ {"temperature": 0.7} $$, 'lang_greeting_1'),
('rule_suggester', 'AI Gợi ý Rule', 'Phân tích hội thoại và đề xuất.', 'Analyze the interaction. Output MUST be in format: Keywords: <keywords>\nCategory: <category>\nTemplate Ref: <ref>\nTemplate Text: <text>', 'models/gemini-1.5-flash-latest', $$ {"temperature": 0.2} $$, NULL);

-- === Strategy Definitions ===

-- Strategy: simple_control_test
INSERT INTO public.strategies (strategy_id, name, description, strategy_type, initial_stage_id, is_active) VALUES
('simple_control_test', 'Test Control Đơn giản', 'Mở app com.example, chờ, click "Tiếp tục", nhập "Hello", back', 'control', NULL, true); -- Tạm NULL

-- Strategy: tiktok_basic_swipe_like
INSERT INTO public.strategies (strategy_id, name, description, strategy_type, initial_stage_id, is_active) VALUES
('tiktok_basic_swipe_like', 'TikTok Cơ bản: Lướt và Like', 'Mở TikTok, chờ, lướt 3 lần, like video, kết thúc.', 'control', NULL, true); -- Tạm NULL

-- Strategy: default_sales (Language example)
INSERT INTO public.strategies (strategy_id, name, description, strategy_type, initial_stage_id, is_active) VALUES
('default_sales', 'Luồng Trả lời Bán hàng', 'Luồng xử lý hội thoại cơ bản cho bán hàng', 'language', NULL, true); -- Tạm NULL


-- === Strategy Stages ===

-- Stages cho simple_control_test
INSERT INTO public.strategy_stages (strategy_id, stage_id, description, stage_order, identifying_elements) VALUES
('simple_control_test', 'start', 'Giai đoạn bắt đầu', 0, $$ {} $$),
('simple_control_test', 'app_opened', 'Đã mở app com.example', 1, $$ {"rules": [{"check": "element_exists", "value": {"package_name": "com.example.targetapp"}}]} $$), -- Nhớ sửa package name
('simple_control_test', 'waited', 'Đã chờ sau khi mở app', 2, $$ {} $$),
('simple_control_test', 'element_clicked', 'Đã nhấp nút Tiếp tục', 3, $$ {} $$),
('simple_control_test', 'text_inputted', 'Đã nhập text Hello', 4, $$ {} $$),
('simple_control_test', 'finished', 'Hoàn thành', 10, $$ {} $$);

-- Stages cho tiktok_basic_swipe_like
INSERT INTO public.strategy_stages (strategy_id, stage_id, description, stage_order, identifying_elements) VALUES
('tiktok_basic_swipe_like', 'start', 'Bắt đầu quy trình', 0, $$ {} $$),
('tiktok_basic_swipe_like', 'tiktok_opened', 'Đã mở ứng dụng TikTok', 1, $$ {"rules": [{"check": "element_exists", "value": {"package_name": "com.zhiliaoapp.musically"}}]} $$), -- Xác nhận package name
('tiktok_basic_swipe_like', 'feed_viewed', 'Đang ở màn hình xem video (Feed)', 2, $$ {"rules": [{"check": "element_exists", "value": {"resource_id": "com.zhiliaoapp.musically:id/view_pager"}}]} $$), -- Xác nhận ID
('tiktok_basic_swipe_like', 'videos_swiped', 'Đã hoàn thành lướt video', 3, $$ {} $$),
('tiktok_basic_swipe_like', 'video_liked', 'Đã nhấn nút Like video', 4, $$ {} $$),
('tiktok_basic_swipe_like', 'finished', 'Kết thúc quy trình', 10, $$ {} $$);

-- Stages cho default_sales (Language example)
INSERT INTO public.strategy_stages (strategy_id, stage_id, description, stage_order) VALUES
('default_sales', 'initial', 'Bắt đầu hội thoại', 0),
('default_sales', 'providing_info', 'Đang cung cấp thông tin SP', 1),
('default_sales', 'asking_price', 'Khách hỏi giá', 2),
('default_sales', 'handling_objection', 'Xử lý từ chối', 3),
('default_sales', 'closing_sale', 'Chốt đơn', 4),
('default_sales', 'finished', 'Kết thúc hội thoại', 10);


-- === UPDATE initial_stage_id cho Strategies ===
UPDATE public.strategies SET initial_stage_id = 'start' WHERE strategy_id = 'simple_control_test';
UPDATE public.strategies SET initial_stage_id = 'start' WHERE strategy_id = 'tiktok_basic_swipe_like';
UPDATE public.strategies SET initial_stage_id = 'initial' WHERE strategy_id = 'default_sales';

-- === Stage Transitions ===

-- Transitions cho simple_control_test
INSERT INTO public.stage_transitions (strategy_id, current_stage_id, user_intent, priority, action_macro_code, action_params_str, next_stage_id, notes) VALUES
('simple_control_test', 'start', 'init', 0, 'APP_OPEN', $$ {"package_name": "com.example.targetapp"} $$, 'app_opened', 'Mở ứng dụng ví dụ'),
('simple_control_test', 'app_opened', 'wait_after_open', 0, 'SYS_WAIT', $$ {"duration_ms": 2000} $$, 'waited', 'Chờ 2 giây'),
('simple_control_test', 'waited', 'click_continue', 0, 'UI_CLICK', $$ {"target": {"text": "Tiếp tục"}} $$, 'element_clicked', 'Click nút Tiếp tục'),
('simple_control_test', 'element_clicked', 'input_data', 0, 'UI_INPUT_TEXT', $$ {"target": {"resource_id": "com.example:id/input"}, "text_to_input": "Hello World"} $$, 'text_inputted', 'Nhập text vào ô'),
('simple_control_test', 'text_inputted', 'go_back', 0, 'NAV_GO_BACK', NULL, 'finished', 'Nhấn back và kết thúc');

-- Transitions cho tiktok_basic_swipe_like
INSERT INTO public.stage_transitions (strategy_id, current_stage_id, user_intent, priority, action_macro_code, action_params_str, next_stage_id) VALUES
('tiktok_basic_swipe_like', 'start', 'start_flow', 0, 'APP_OPEN', $$ {"package_name": "com.zhiliaoapp.musically"} $$, 'tiktok_opened');
INSERT INTO public.stage_transitions (strategy_id, current_stage_id, user_intent, priority, action_macro_code, action_params_str, next_stage_id) VALUES
('tiktok_basic_swipe_like', 'tiktok_opened', 'wait_for_load', 0, 'SYS_WAIT', $$ {"duration_ms": 3000} $$, 'feed_viewed');
INSERT INTO public.stage_transitions (strategy_id, current_stage_id, user_intent, priority, action_macro_code, action_params_str, next_stage_id, loop_type, loop_count) VALUES
('tiktok_basic_swipe_like', 'feed_viewed', 'swipe_videos', 10, 'UI_SWIPE_UP', $$ {} $$, 'videos_swiped', 'repeat_n', 3);
INSERT INTO public.stage_transitions (strategy_id, current_stage_id, user_intent, priority, action_macro_code, action_params_str, next_stage_id) VALUES
('tiktok_basic_swipe_like', 'videos_swiped', 'like_video', 0, 'UI_CLICK', $$ {"target": {"resource_id": "com.zhiliaoapp.musically:id/like_icon"}} $$, 'video_liked'); -- Xác nhận ID
INSERT INTO public.stage_transitions (strategy_id, current_stage_id, user_intent, priority, action_macro_code, action_params_str, next_stage_id) VALUES
('tiktok_basic_swipe_like', 'video_liked', 'finish_flow', 0, 'SYS_LOG', $$ {"message": "TikTok basic flow completed."} $$, 'finished');

-- Transitions cho default_sales (Language example)
INSERT INTO public.stage_transitions (strategy_id, current_stage_id, user_intent, priority, response_template_ref, next_stage_id) VALUES
('default_sales', 'initial', 'greeting', 10, 'lang_greeting_1', 'providing_info'),
('default_sales', 'initial', 'price_query', 10, 'lang_price_ask_inbox', 'asking_price'),
('default_sales', 'providing_info', 'price_query', 10, 'lang_price_ask_inbox', 'asking_price'),
('default_sales', 'asking_price', 'any', 0, NULL, 'finished'); -- Kết thúc sau khi báo giá/inbox

-- === UPDATE default_strategy_id cho Accounts ===
UPDATE public.accounts SET default_strategy_id = 'tiktok_basic_swipe_like' WHERE account_id = 'tiktok_test_1';
UPDATE public.accounts SET default_strategy_id = 'default_sales' WHERE account_id = 'fb_test_user';

-- === Device Accounts (Đã INSERT ở trên) ===

-- === Task Assignments ===
-- Giao chiến lược 'tiktok_basic_swipe_like' cho account 'tiktok_test_1' trên 'test_device_001'
INSERT INTO public.task_assignments (device_account_id, strategy_id, status, priority, target_data, notes)
SELECT
    da.device_account_id,
    'tiktok_basic_swipe_like',
    'pending',
    5,
    $$ {"goal_type": "engagement", "target_count": 10, "current_count": 0} $$, -- Ví dụ mục tiêu
    'Giao việc lướt và like TikTok'
FROM public.device_accounts da
WHERE da.device_id = 'test_device_001' AND da.account_id = 'tiktok_test_1';

-- === API Documentation Data ===
INSERT INTO public.api_documentation (endpoint_path, http_method, summary, description, request_notes, request_example, response_notes, success_response_example, error_response_example, is_active) VALUES
(
    '/phone/get_strategy',
    'POST',
    'Client yêu cầu nhận nhiệm vụ và gói chiến lược để thực thi.',
    'Client gửi device_id và account_id. Server kiểm tra xem có task assignment nào đang chờ cho cặp này không. Nếu có, biên dịch chiến lược tương ứng thành JSON package và trả về. Nếu không, trả về status "no_task".',
    'Request Body phải là JSON object. Header Content-Type phải là application/json.',
    $${\n  "device_id": "your_device_unique_id",\n  "account_id": "account_id_on_device"\n}$$ ,
    'Thành công có 2 dạng: có task (HTTP 200, trả về JSON package lớn) hoặc không có task (HTTP 200, trả về JSON status "no_task"). Lỗi trả về HTTP 400/404/500 với JSON status "error".',
    $${\n  "metadata": { "assignment_id": 123, ... },\n  "execution_config": { ... },\n  "account_context": { ... },\n  "stages_recognition": { ... },\n  "action_sequence": [ ... ]\n} \n\n// Hoặc (Không có task):\n{\n  "status": "no_task",\n  "message": "No pending assignment found.",\n  "retry_after_seconds": 300\n}$$ ,
    $${\n  "status": "error",\n  "message": "Device or Account not registered/linked correctly."\n}\n// Hoặc:\n{\n  "status": "error",\n  "message": "Missing 'device_id' or 'account_id'."\n}\n// Hoặc:\n{\n  "status": "error",\n  "message": "Failed to compile strategy package."\n}$$ ,
    true
),
(
    '/phone/report_status',
    'POST',
    'Client gửi báo cáo tiến độ, log thực thi và trạng thái UI.',
    'Client gửi assignment_id đã nhận, device_id, account_id, cùng với status_report (chứa trạng thái hiện tại, tiến độ, kết quả/lỗi), logs (danh sách các hành động đã thực hiện) và current_ui_state (dữ liệu UI thô mới nhất). Server cập nhật CSDL và có thể trả về yêu cầu hành động (vd: dừng).',
    'Request Body là JSON object. Header Content-Type: application/json.',
    $${\n  "assignment_id": 123,\n  "device_id": "your_device_unique_id",\n  "account_id": "account_id_on_device",\n  "status_report": {\n    "current_status": "running",\n    "progress": {"videos_watched": 5},\n    "result": null,\n    "error_message": null\n  },\n  "logs": [\n    {"timestamp": "...", "macro": "UI_SWIPE_UP", "status": "success", ...}\n  ],\n  "current_ui_state": {\n    "timestamp": "...",\n    "package_name": "...",\n    "ids": [...],\n    "texts": [...],\n    "coords": [...]\n  }\n}$$ ,
    'Thành công trả về HTTP 200 với JSON xác nhận. Có thể kèm "action_required". Lỗi trả về HTTP 400/500.',
    $${\n  "status": "success",\n  "message": "Report received.",\n  "action_required": null \n}\n// Hoặc:\n{\n  "status": "success",\n  "message": "Report received. Assignment cancelled by admin.",\n  "action_required": "stop_assignment"\n}$$ ,
    $${\n  "status": "error",\n  "message": "Invalid report data: Missing 'assignment_id'."\n}\n// Hoặc:\n{\n  "status": "error",\n  "message": "Internal server error processing report."\n}$$ ,
    true
),
(
    '/phone/register_device',
    'POST',
    'Client đăng ký hoặc cập nhật thông tin với server.',
    'Client gửi thông tin về device (ID, OS, model, version client) và danh sách các tài khoản được quản lý trên thiết bị đó (kèm platform, clone_context, status đăng nhập). Server sẽ tạo/cập nhật bản ghi trong bảng devices và device_accounts.',
    'Request Body là JSON object. Header Content-Type: application/json.',
    $${\n  "device_id": "your_device_unique_id",\n  "device_info": { "os": "Android 13", "model": "Pixel 7"}, \n  "client_version": "1.1.0",\n  "managed_accounts": [\n    {"account_id": "tiktok_main", "platform": "tiktok", "status": "active_logged_in"},\n    {"account_id": "tiktok_clone", "platform": "tiktok", "clone_context": "dual", "status": "login_required"}\n  ]\n}$$ ,
    'Thành công trả về HTTP 200.',
    $${\n  "status": "success",\n  "message": "Device registered/updated."\n}$$ ,
    $${\n  "status": "error",\n  "message": "Missing 'device_id'."\n}\n// Hoặc:\n{\n  "status": "error",\n  "message": "Internal server error during registration."\n}$$ ,
    true
);

COMMIT; -- Kết thúc Transaction

RAISE NOTICE '=== Seed data inserted successfully. ===';
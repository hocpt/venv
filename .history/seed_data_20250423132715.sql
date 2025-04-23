-- PostgreSQL Seed Data for HPT Automation Project
-- Version: 2025-04-23 (Final Corrected Version)
-- ASSUMES TABLES WERE CLEANLY CREATED BY THE LATEST automation_schema.sql
-- Uses BEGIN/COMMIT for deferrable constraints.

BEGIN; -- Bắt đầu Transaction Lớn

RAISE NOTICE '=== Starting Seed Data Insertion ===';

-- === Dữ liệu Cơ bản (Ít phụ thuộc) ===
RAISE NOTICE 'Inserting base data (accounts, devices, macros, templates, personas)...';

-- Accounts (Chưa đặt default_strategy_id/default_persona_id)
INSERT INTO public.accounts (account_id, platform, username, status, notes, goal) VALUES
('tiktok_test_1', 'tiktok', 'Test User TikTok 1', 'active', 'TK để test luồng control', 'engagement'),
('system_admin', 'system', 'Admin', 'active', 'TK hệ thống', NULL),
('fb_test_user', 'facebook', 'FB Test Bán hàng', 'active', 'TK để test luồng language', 'product_sales');

-- Devices
INSERT INTO public.devices (device_id, device_name, os_info, macrodroid_version, status, last_seen_at) VALUES
('test_device_001', 'Samsung A51 Test', 'Android 12, SM-A515F', '5.35', 'offline', NOW() - INTERVAL '1 hour'),
('test_device_002', 'Nox Player Test', 'Android 9, Nox', '5.30', 'offline', NOW() - INTERVAL '2 day');

-- Macro Definitions
INSERT INTO public.macro_definitions (macro_code, description, app_target, params_schema, notes) VALUES
('SYS_WAIT', 'Chờ một khoảng thời gian cố định', 'system', $$ {"type": "object", "properties": {"duration_ms": {"type": "integer"}}, "required": ["duration_ms"]} $$, 'Dừng thực thi X ms.'),
('APP_OPEN', 'Mở một ứng dụng bằng package name', 'system', $$ {"type": "object", "properties": {"package_name": {"type": "string"}}, "required": ["package_name"]} $$, NULL),
('NAV_GO_BACK', 'Nhấn nút Back hệ thống', 'system', $$ {} $$, 'Tương đương nút Back.'),
('UI_CLICK', 'Nhấp vào phần tử UI', 'generic', $$ {"type": "object", "properties": {"target": {"type": "object", "minProperties": 1}}, "required": ["target"]} $$, 'Nhấp vào nút, link... Target: text, resource_id, content_description, point, xpath...'),
('UI_INPUT_TEXT', 'Nhập text vào ô input', 'generic', $$ {"type": "object", "properties": {"target": {"type": "object", "minProperties": 1}, "text_to_input": {"type": "string"}}, "required": ["target", "text_to_input"]} $$, 'Điền form.'),
('UI_SWIPE_UP', 'Vuốt màn hình lên', 'generic', $$ {"type": "object", "properties": {"duration_ms": {"type": "integer", "default": 300}}} $$, 'Vuốt từ dưới lên.'),
('SYS_LOG', 'Ghi log tùy chỉnh', 'system', $$ {"type": "object", "properties": {"message": {"type": "string"}, "log_level": {"type": "string", "default": "INFO"}}, "required": ["message"]} $$, 'Ghi log.');

-- Templates (Bảng templates gốc)
INSERT INTO public.templates (template_ref, category, description) VALUES
('lang_greeting_1', 'greeting', 'Chào hỏi thân thiện'),
('lang_price_ask_inbox', 'price_query', 'Yêu cầu inbox để báo giá'),
('fallback_generic', 'fallback', 'Trả lời chung khi AI lỗi');

-- AI Personas (Tham chiếu đến templates)
INSERT INTO public.ai_personas (persona_id, name, description, base_prompt, model_name, generation_config, fallback_template_ref) VALUES
('general_assistant', 'Trợ lý Chung', 'Trợ lý AI cơ bản, hữu ích và trung lập.', 'You are a helpful assistant.', 'models/gemini-1.5-flash-latest', $$ {"temperature": 0.7} $$, 'fallback_generic'),
('rule_suggester', 'AI Gợi ý Rule', 'Phân tích hội thoại và đề xuất.', 'Analyze the interaction. Output MUST be in format: Keywords: <keywords>\nCategory: <category>\nTemplate Ref: <ref>\nTemplate Text: <text>', 'models/gemini-1.5-flash-latest', $$ {"temperature": 0.2} $$, NULL);

-- === Strategies ===
RAISE NOTICE 'Inserting strategies (step 1: initial_stage_id=NULL)...';
INSERT INTO public.strategies (strategy_id, name, description, strategy_type, initial_stage_id, is_active) VALUES
('simple_control_test', 'Test Control Đơn giản', 'Mở app com.example, chờ, click "Tiếp tục", nhập "Hello", back', 'control', NULL, true),
('tiktok_basic_swipe_like', 'TikTok Cơ bản: Lướt và Like', 'Mở TikTok, chờ, lướt 3 lần, like video, kết thúc.', 'control', NULL, true),
('default_sales', 'Luồng Trả lời Bán hàng', 'Luồng xử lý hội thoại cơ bản cho bán hàng', 'language', NULL, true);

-- === Strategy Stages ===
RAISE NOTICE 'Inserting strategy stages...';
-- Stages cho simple_control_test
INSERT INTO public.strategy_stages (strategy_id, stage_id, description, stage_order, identifying_elements) VALUES
('simple_control_test', 'start', 'Bắt đầu', 0, $$ {} $$),
('simple_control_test', 'app_opened', 'Đã mở app com.example', 1, $$ {"rules": [{"check": "element_exists", "value": {"package_name": "com.example.targetapp"}}]} $$),
('simple_control_test', 'waited', 'Đã chờ', 2, $$ {} $$),
('simple_control_test', 'element_clicked', 'Đã click Tiếp tục', 3, $$ {} $$),
('simple_control_test', 'text_inputted', 'Đã nhập Hello', 4, $$ {} $$),
('simple_control_test', 'finished', 'Kết thúc', 10, $$ {} $$);
-- Stages cho tiktok_basic_swipe_like
INSERT INTO public.strategy_stages (strategy_id, stage_id, description, stage_order, identifying_elements) VALUES
('tiktok_basic_swipe_like', 'start', 'Bắt đầu', 0, $$ {} $$),
('tiktok_basic_swipe_like', 'tiktok_opened', 'Đã mở TikTok', 1, $$ {"rules": [{"check": "element_exists", "value": {"package_name": "com.zhiliaoapp.musically"}}]} $$),
('tiktok_basic_swipe_like', 'feed_viewed', 'Ở màn hình Feed', 2, $$ {"rules": [{"check": "element_exists", "value": {"resource_id": "com.zhiliaoapp.musically:id/view_pager"}}]} $$),
('tiktok_basic_swipe_like', 'videos_swiped', 'Đã lướt xong', 3, $$ {} $$),
('tiktok_basic_swipe_like', 'video_liked', 'Đã like video', 4, $$ {} $$),
('tiktok_basic_swipe_like', 'finished', 'Kết thúc', 10, $$ {} $$);
-- Stages cho default_sales
INSERT INTO public.strategy_stages (strategy_id, stage_id, description, stage_order) VALUES
('default_sales', 'initial', 'Bắt đầu hội thoại', 0),
('default_sales', 'providing_info', 'Đang cung cấp thông tin SP', 1),
('default_sales', 'asking_price', 'Khách hỏi giá', 2),
('default_sales', 'handling_objection', 'Xử lý từ chối', 3),
('default_sales', 'closing_sale', 'Chốt đơn', 4),
('default_sales', 'finished', 'Kết thúc hội thoại', 10);

-- === UPDATE initial_stage_id cho Strategies (Step 2) ===
RAISE NOTICE 'Updating strategies (step 2: set initial_stage_id)...';
UPDATE public.strategies SET initial_stage_id = 'start' WHERE strategy_id = 'simple_control_test';
UPDATE public.strategies SET initial_stage_id = 'start' WHERE strategy_id = 'tiktok_basic_swipe_like';
UPDATE public.strategies SET initial_stage_id = 'initial' WHERE strategy_id = 'default_sales';

-- === Cập nhật FK cho Accounts (Sau khi Strategies tồn tại) ===
RAISE NOTICE 'Updating FKs for accounts...';
UPDATE public.accounts SET default_strategy_id = 'tiktok_basic_swipe_like' WHERE account_id = 'tiktok_test_1';
UPDATE public.accounts SET default_strategy_id = 'default_sales' WHERE account_id = 'fb_test_user';
UPDATE public.accounts SET default_persona_id = 'general_assistant' WHERE account_id = 'tiktok_test_1';

-- === Template Variations (Sau khi templates tồn tại) ===
RAISE NOTICE 'Inserting template variations...';
INSERT INTO public.template_variations (template_ref, variation_text) VALUES
('lang_greeting_1', 'Chào bạn! Shop có thể giúp gì cho bạn ạ?'),
('lang_greeting_1', 'Xin chào, cảm ơn bạn đã quan tâm!'),
('lang_price_ask_inbox', 'Bạn vui lòng inbox để shop báo giá chi tiết nhé!'),
('lang_price_ask_inbox', 'Dạ bạn check inbox giúp shop nha.'),
('fallback_generic', 'Xin lỗi, tôi chưa hiểu ý bạn lắm. Bạn có thể nói rõ hơn không?');

-- === Rules (Sau khi strategies và templates tồn tại) ===
RAISE NOTICE 'Inserting rules...';
INSERT INTO public.rules (strategy_id, trigger_keywords, category, response_template_ref, priority) VALUES
('default_sales', 'hello, hi, shop ơi, chào', 'greeting', 'lang_greeting_1', 10),
('default_sales', 'giá, nhiêu tiền, giá sao, bao nhiêu', 'price_query', 'lang_price_ask_inbox', 10);

-- === Stage Transitions (Sau khi strategies, stages, macros, templates tồn tại) ===
RAISE NOTICE 'Inserting stage transitions...';
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
-- Transitions cho default_sales
INSERT INTO public.stage_transitions (strategy_id, current_stage_id, user_intent, priority, response_template_ref, next_stage_id) VALUES
('default_sales', 'initial', 'greeting', 10, 'lang_greeting_1', 'providing_info'),
('default_sales', 'initial', 'price_query', 10, 'lang_price_ask_inbox', 'asking_price'),
('default_sales', 'providing_info', 'price_query', 10, 'lang_price_ask_inbox', 'asking_price'),
('default_sales', 'asking_price', 'any', 0, NULL, 'finished');

-- === Device Accounts (Sau khi devices và accounts tồn tại) ===
RAISE NOTICE 'Inserting device_accounts...';
INSERT INTO public.device_accounts (device_id, account_id, clone_context, status, last_check_at) VALUES
('test_device_001', 'tiktok_test_1', 'main', 'active_logged_in', NOW()),
('test_device_001', 'fb_test_user', 'dual', 'login_required', NOW() - INTERVAL '1 day'); -- Giả sử FB cần login trên clone dual

-- === Task Assignments (Sau khi device_accounts và strategies tồn tại) ===
RAISE NOTICE 'Inserting task_assignments...';
-- Giao việc cho tiktok_test_1 trên test_device_001 (cần lấy device_account_id)
INSERT INTO public.task_assignments (device_account_id, strategy_id, status, priority, target_data, notes)
SELECT
    da.device_account_id,
    'tiktok_basic_swipe_like', -- Strategy control
    'pending',
    5,
    $$ {"goal_type": "engagement", "target_count": 10, "current_count": 0} $$,
    'Giao việc lướt và like TikTok'
FROM public.device_accounts da
WHERE da.device_id = 'test_device_001' AND da.account_id = 'tiktok_test_1' AND da.clone_context = 'main';

-- Giao việc cho fb_test_user trên test_device_001 (clone dual)
INSERT INTO public.task_assignments (device_account_id, strategy_id, status, priority, target_data, notes)
SELECT
    da.device_account_id,
    'default_sales', -- Strategy language
    'pending', -- Language strategy không có trạng thái chạy thực sự, có thể dùng status khác
    10,
    NULL,
    'Giao việc trả lời tự động FB'
FROM public.device_accounts da
WHERE da.device_id = 'test_device_001' AND da.account_id = 'fb_test_user' AND da.clone_context = 'dual';


-- === API Documentation Data ===
RAISE NOTICE 'Inserting api_documentation...';
INSERT INTO public.api_documentation (endpoint_path, http_method, summary, description, request_notes, request_example, response_notes, success_response_example, error_response_example) VALUES
(
    '/phone/get_strategy', 'POST', 'Client lấy nhiệm vụ/chiến lược mới.',
    'Client gửi device_id, account_id. Server tìm assignment phù hợp và trả về gói JSON chiến lược đã biên dịch (nếu có) hoặc status "no_task".',
    'Content-Type: application/json', $${\n  "device_id": "...",\n  "account_id": "..."\n}$$ ,
    'Thành công 200 OK: Trả về JSON package HOẶC {status: "no_task"}. Lỗi 400/404/500: Trả về {status: "error", message: "..."}.',
    $${\n  "metadata": { "assignment_id": 123, ... }, ... \n}\n// HOẶC\n{\n  "status": "no_task", ...\n}$$ ,
    $${\n  "status": "error",\n  "message": "Device or Account not registered/linked correctly."\n}$$
),
(
    '/phone/report_status', 'POST', 'Client báo cáo trạng thái, log, và UI state.',
    'Client gửi assignment_id, device_id, account_id, status_report (status, progress, result, error), logs (array), và current_ui_state (optional, chứa các mảng ids, texts, coords...).',
    'Content-Type: application/json. Logs và UI State là tùy chọn.',
    $${\n  "assignment_id": 123,\n  "device_id": "...",\n  "account_id": "...",\n  "status_report": { "current_status": "running", "progress": {...} },\n  "logs": [ ... ],\n  "current_ui_state": { "ids": [...], ... }\n}$$ ,
    'Thành công 200 OK: Trả về {status: "success", message: "..."}. Có thể kèm "action_required": "stop_assignment". Lỗi 400/500: Trả về {status: "error", message: "..."}.',
    $${\n  "status": "success",\n  "message": "Report received.",\n  "action_required": null\n}$$ ,
    $${\n  "status": "error",\n  "message": "Internal server error processing report."\n}$$
),
(
    '/phone/register_device', 'POST', 'Client đăng ký/cập nhật thông tin thiết bị.',
    'Client gửi device_id, device_info (os, model), client_version, và managed_accounts (list các account trên máy kèm status, clone_context).',
    'Content-Type: application/json.',
    $${\n  "device_id": "...",\n  "device_info": { ... },\n  "client_version": "...",\n  "managed_accounts": [ {"account_id": ..., "platform": ..., "status": ...}, ... ]\n}$$ ,
    'Thành công 200 OK: Trả về {status: "success", message: "..."}. Lỗi 400/500: Trả về {status: "error", message: "..."}.',
    $${\n  "status": "success",\n  "message": "Device registered/updated."\n}$$ ,
    $${\n  "status": "error",\n  "message": "Missing 'device_id'."\n}$$
);

COMMIT; -- Kết thúc Transaction Lớn

RAISE NOTICE '=== Seed data insertion completed. ===';
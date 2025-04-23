-- PostgreSQL Seed Data for HPT Automation Project
-- Version: 2025-04-21 (Final Corrected Version)
-- STRATEGY: Assumes tables are empty (created by corrected automation_schema.sql).
-- Uses BEGIN/COMMIT for deferrable constraints.

BEGIN; -- Start Transaction

-- === Base Data ===

INSERT INTO public.accounts (account_id, platform, username, status, default_persona_id, default_strategy_id) VALUES
('tiktok_test_1', 'tiktok', 'Test User One', 'active', 'general_assistant', 'tiktok_basic_swipe_like'),
('system_admin', 'system', 'Admin', 'active', NULL, NULL),
('fb_test_user', 'facebook', 'FB Test Acc', 'active', NULL, NULL);

INSERT INTO public.devices (device_id, device_name, os_info, macrodroid_version, status, last_seen_at) VALUES
('test_device_001', 'Samsung A51 Test', 'Android 12, SM-A515F', '5.35', 'offline', NOW() - INTERVAL '1 hour'),
('test_device_002', 'Nox Player Test', 'Android 9, Nox', '5.30', 'offline', NOW() - INTERVAL '2 day');

INSERT INTO public.device_accounts (device_id, account_id, clone_context, app_package_name, status, last_check_at) VALUES
('test_device_001', 'tiktok_test_1', 'main', NULL, 'active_logged_in', NOW()), -- TikTok test account on device 1 (main app)
('test_device_001', 'fb_test_user', 'com.facebook.katana.dual', 'com.facebook.katana.dual', 'login_required', NOW() - INTERVAL '1 day'); -- FB test account on device 1 (clone)

INSERT INTO public.macro_definitions (macro_code, description, app_target, params_schema, notes) VALUES
('SYS_WAIT', 'Chờ một khoảng thời gian cố định', 'system', $$ {"type": "object", "properties": {"duration_ms": {"type": "integer", "description": "Thời gian chờ (ms). Bắt buộc."}}, "required": ["duration_ms"]} $$, 'Dừng thực thi X ms.'),
('APP_OPEN', 'Mở một ứng dụng bằng package name', 'system', $$ {"type": "object", "properties": {"package_name": {"type": "string", "description": "Package name của app. Bắt buộc."}}, "required": ["package_name"]} $$, NULL),
('NAV_GO_BACK', 'Nhấn nút Back hệ thống', 'system', $$ {} $$, 'Tương đương nút Back vật lý/điều hướng.'),
('UI_CLICK', 'Nhấp vào phần tử UI', 'generic', $$ {"type": "object", "properties": {"target": {"type": "object", "description": "Cách xác định mục tiêu (text, resource_id, content_description, point, xpath...)", "minProperties": 1}}, "required": ["target"]} $$, 'Nhấp vào nút, link, ảnh... Xác định bằng text, id, tọa độ, xpath...'),
('UI_INPUT_TEXT', 'Nhập text vào ô input', 'generic', $$ {"type": "object", "properties": {"target": {"type": "object", "description": "Cách xác định ô input", "minProperties": 1}, "text_to_input": {"type": "string", "description": "Nội dung cần nhập"}}, "required": ["target", "text_to_input"]} $$, 'Điền form, nhập liệu.'),
('UI_SWIPE_UP', 'Vuốt màn hình lên', 'generic', $$ {"type": "object", "properties": {"duration_ms": {"type": "integer", "default": 300}}} $$, 'Vuốt từ dưới lên để xem tiếp feed (vd: TikTok, FB Reels).'),
('SYS_LOG', 'Ghi log tùy chỉnh', 'system', $$ {"type": "object", "properties": {"message": {"type": "string"}, "log_level": {"type": "string", "default": "INFO"}}, "required": ["message"]} $$, 'Ghi log ra hệ thống (server hoặc client).');

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
('rule_suggester', 'AI Gợi ý Rule', 'Phân tích hội thoại và đề xuất Keywords, Category, Template Ref, Template Text.', 'Analyze the interaction. Extract keywords. Suggest a category (e.g., price_query). Suggest a concise template_ref (lowercase_snake_case). Suggest a generic template text. Output MUST be in format: Keywords: <keywords>\nCategory: <category>\nTemplate Ref: <ref>\nTemplate Text: <text>', 'models/gemini-1.5-flash-latest', $$ {"temperature": 0.2} $$, NULL);

-- === Strategy: simple_control_test ===
-- 1a. Insert Strategy (initial_stage_id = NULL)
INSERT INTO public.strategies (strategy_id, name, description, strategy_type, initial_stage_id, is_active) VALUES
('simple_control_test', 'Test Control Đơn giản', 'Mở app com.example, chờ, click "Tiếp tục", nhập "Hello", back', 'control', NULL, true);
-- 1b. Insert Stages
INSERT INTO public.strategy_stages (strategy_id, stage_id, description, stage_order, identifying_elements) VALUES
('simple_control_test', 'start', 'Giai đoạn bắt đầu', 0, $$ {} $$),
('simple_control_test', 'app_opened', 'Đã mở app com.example', 1, $$ {"rules": [{"check": "element_exists", "value": {"package_name": "com.example.targetapp"}}]} $$), -- Nhớ sửa package name
('simple_control_test', 'waited', 'Đã chờ sau khi mở app', 2, $$ {} $$), -- Thêm stage waited
('simple_control_test', 'element_clicked', 'Đã nhấp nút Tiếp tục', 3, $$ {} $$),
('simple_control_test', 'text_inputted', 'Đã nhập text Hello', 4, $$ {} $$),
('simple_control_test', 'finished', 'Hoàn thành', 10, $$ {} $$);
-- 1c. Update Strategy initial_stage_id
UPDATE public.strategies SET initial_stage_id = 'start' WHERE strategy_id = 'simple_control_test';
-- 1d. Insert Transitions
INSERT INTO public.stage_transitions (strategy_id, current_stage_id, user_intent, priority, action_macro_code, action_params_str, next_stage_id, notes) VALUES
('simple_control_test', 'start', 'init', 0, 'APP_OPEN', $$ {"package_name": "com.example.targetapp"} $$, 'app_opened', 'Mở ứng dụng ví dụ'),
('simple_control_test', 'app_opened', 'wait_after_open', 0, 'SYS_WAIT', $$ {"duration_ms": 2000} $$, 'waited', 'Chờ 2 giây'), -- Chuyển đến waited
('simple_control_test', 'waited', 'click_continue', 0, 'UI_CLICK', $$ {"target": {"text": "Tiếp tục"}} $$, 'element_clicked', 'Click nút Tiếp tục'), -- Bắt đầu từ waited
('simple_control_test', 'element_clicked', 'input_data', 0, 'UI_INPUT_TEXT', $$ {"target": {"resource_id": "com.example:id/input"}, "text_to_input": "Hello World"} $$, 'text_inputted', 'Nhập text vào ô'), -- Sửa ID nếu cần
('simple_control_test', 'text_inputted', 'go_back', 0, 'NAV_GO_BACK', NULL, 'finished', 'Nhấn back và kết thúc'); -- next_stage_id là finished

-- === Strategy: tiktok_basic_swipe_like ===
-- 2a. Insert Strategy (initial_stage_id = NULL)
INSERT INTO public.strategies (strategy_id, name, description, strategy_type, initial_stage_id, is_active) VALUES
('tiktok_basic_swipe_like', 'TikTok Cơ bản: Lướt và Like', 'Mở TikTok, chờ, lướt 3 lần, like video, kết thúc.', 'control', NULL, true);
-- 2b. Insert Stages
INSERT INTO public.strategy_stages (strategy_id, stage_id, description, stage_order, identifying_elements) VALUES
('tiktok_basic_swipe_like', 'start', 'Bắt đầu quy trình', 0, $$ {} $$),
('tiktok_basic_swipe_like', 'tiktok_opened', 'Đã mở ứng dụng TikTok', 1, $$ {"rules": [{"check": "element_exists", "value": {"package_name": "com.zhiliaoapp.musically"}}]} $$), -- Cần xác nhận package name
('tiktok_basic_swipe_like', 'feed_viewed', 'Đang ở màn hình xem video (Feed)', 2, $$ {"rules": [{"check": "element_exists", "value": {"resource_id": "com.zhiliaoapp.musically:id/view_pager"}}]} $$), -- Cần xác nhận ID
('tiktok_basic_swipe_like', 'videos_swiped', 'Đã hoàn thành lướt video', 3, $$ {} $$),
('tiktok_basic_swipe_like', 'video_liked', 'Đã nhấn nút Like video', 4, $$ {} $$),
('tiktok_basic_swipe_like', 'finished', 'Kết thúc quy trình', 10, $$ {} $$);
-- 2c. Update Strategy initial_stage_id
UPDATE public.strategies SET initial_stage_id = 'start' WHERE strategy_id = 'tiktok_basic_swipe_like';
-- 2d. Insert Transitions
INSERT INTO public.stage_transitions (strategy_id, current_stage_id, user_intent, priority, action_macro_code, action_params_str, next_stage_id) VALUES
('tiktok_basic_swipe_like', 'start', 'start_flow', 0, 'APP_OPEN', $$ {"package_name": "com.zhiliaoapp.musically"} $$, 'tiktok_opened');
INSERT INTO public.stage_transitions (strategy_id, current_stage_id, user_intent, priority, action_macro_code, action_params_str, next_stage_id) VALUES
('tiktok_basic_swipe_like', 'tiktok_opened', 'wait_for_load', 0, 'SYS_WAIT', $$ {"duration_ms": 3000} $$, 'feed_viewed');
-- Lặp lại việc lướt 3 lần
INSERT INTO public.stage_transitions (strategy_id, current_stage_id, user_intent, priority, action_macro_code, action_params_str, next_stage_id, loop_type, loop_count) VALUES
('tiktok_basic_swipe_like', 'feed_viewed', 'swipe_videos', 10, 'UI_SWIPE_UP', $$ {} $$, 'videos_swiped', 'repeat_n', 3); -- Sau khi lặp xong sẽ sang 'videos_swiped'
-- Like video
INSERT INTO public.stage_transitions (strategy_id, current_stage_id, user_intent, priority, action_macro_code, action_params_str, next_stage_id) VALUES
('tiktok_basic_swipe_like', 'videos_swiped', 'like_video', 0, 'UI_CLICK', $$ {"target": {"resource_id": "com.zhiliaoapp.musically:id/like_icon"}} $$, 'video_liked'); -- Cần xác nhận ID
-- Kết thúc
INSERT INTO public.stage_transitions (strategy_id, current_stage_id, user_intent, priority, action_macro_code, action_params_str, next_stage_id) VALUES
('tiktok_basic_swipe_like', 'video_liked', 'finish_flow', 0, 'SYS_LOG', $$ {"message": "TikTok basic flow completed."} $$, 'finished');

-- === Task Assignments ===
-- Giao chiến lược 'simple_control_test' cho account 'tiktok_test_1' trên 'test_device_001'
INSERT INTO public.task_assignments (device_account_id, strategy_id, status, priority, target_data, notes)
SELECT
    da.device_account_id,
    'simple_control_test',
    'pending',
    10,
    $$ {"goal_type": "test_run", "target_count": 1, "current_count": 0} $$,
    'Giao việc test control đơn giản'
FROM public.device_accounts da
WHERE da.device_id = 'test_device_001' AND da.account_id = 'tiktok_test_1';

-- Giao chiến lược 'tiktok_basic_swipe_like' cho cùng account/device
INSERT INTO public.task_assignments (device_account_id, strategy_id, status, priority, target_data, notes)
SELECT
    da.device_account_id,
    'tiktok_basic_swipe_like',
    'pending',
    5, -- Ưu tiên thấp hơn
    $$ {"goal_type": "engagement", "target_count": 1, "current_count": 0} $$,
    'Giao việc lướt và like TikTok'
FROM public.device_accounts da
WHERE da.device_id = 'test_device_001' AND da.account_id = 'tiktok_test_1';


COMMIT; -- End Transaction
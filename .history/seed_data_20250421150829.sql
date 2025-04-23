-- PostgreSQL Seed Data for HPT Automation Project

-- === Accounts ===
-- Xóa account cũ nếu cần để tránh trùng PK
DELETE FROM public.accounts WHERE account_id IN ('tiktok_test_1', 'system_admin');

INSERT INTO public.accounts (account_id, platform, username, status) VALUES
('tiktok_test_1', 'tiktok', 'Test User One', 'active'),
('system_admin', 'system', 'Admin', 'active'); -- Tài khoản hệ thống nếu cần

-- === Devices ===
-- Xóa device cũ nếu cần
DELETE FROM public.devices WHERE device_id IN ('test_device_001', 'test_device_002');

INSERT INTO public.devices (device_id, device_name, os_info, status) VALUES
('test_device_001', 'Samsung A51 Test', 'Android 12, SM-A515F', 'offline'),
('test_device_002', 'Nox Player Test', 'Android 9, Nox', 'offline');

-- === Device Accounts (Liên kết) ===
-- Xóa liên kết cũ nếu cần
DELETE FROM public.device_accounts WHERE device_id = 'test_device_001' AND account_id = 'tiktok_test_1';

-- Liên kết account 'tiktok_test_1' với 'test_device_001', chạy trên app chính
INSERT INTO public.device_accounts (device_id, account_id, clone_context, status) VALUES
('test_device_001', 'tiktok_test_1', 'main', 'active_logged_in');

-- === Macro Definitions ===
-- Xóa các macro cũ trước khi thêm lại (nếu cần đảm bảo sạch)
DELETE FROM public.macro_definitions WHERE macro_code IN ('SYS_WAIT', 'APP_OPEN', 'NAV_GO_BACK', 'UI_CLICK', 'UI_INPUT_TEXT');

INSERT INTO public.macro_definitions (macro_code, description, app_target, params_schema, notes) VALUES
('SYS_WAIT', 'Chờ một khoảng thời gian cố định', 'system', $$ {"type": "object", "properties": {"duration_ms": {"type": "integer", "description": "Thời gian chờ (ms). Bắt buộc."}}, "required": ["duration_ms"]} $$, 'Dừng thực thi X ms.'),
('APP_OPEN', 'Mở một ứng dụng', 'system', $$ {"type": "object", "properties": {"package_name": {"type": "string", "description": "Package name của app. Bắt buộc."}}, "required": ["package_name"]} $$, 'Mở app bằng package name.'),
('NAV_GO_BACK', 'Nhấn nút Back hệ thống', 'system', $$ {} $$, 'Tương đương nút Back.'),
('UI_CLICK', 'Nhấp vào phần tử UI', 'generic', $$ {"type": "object", "properties": {"target": {"type": "object", "description": "Cách xác định mục tiêu (text, resource_id, point...)", "minProperties": 1}}, "required": ["target"]} $$, 'Nhấp vào nút, link...'),
('UI_INPUT_TEXT', 'Nhập text vào ô input', 'generic', $$ {"type": "object", "properties": {"target": {"type": "object", "description": "Cách xác định ô input", "minProperties": 1}, "text_to_input": {"type": "string", "description": "Nội dung cần nhập"}}, "required": ["target", "text_to_input"]} $$, 'Điền form.');


-- === Strategies (Control) ===
-- Xóa strategy cũ nếu cần
DELETE FROM public.strategies WHERE strategy_id = 'simple_control_test';

INSERT INTO public.strategies (strategy_id, name, description, strategy_type, initial_stage_id, is_active) VALUES
('simple_control_test', 'Test Control Đơn giản', 'Mở app, chờ, click, nhập text, back', 'control', 'start', true);

-- === Strategy Stages (cho simple_control_test) ===
-- Xóa stages cũ của strategy này
DELETE FROM public.strategy_stages WHERE strategy_id = 'simple_control_test';

INSERT INTO public.strategy_stages (strategy_id, stage_id, description, stage_order, identifying_elements) VALUES
('simple_control_test', 'start', 'Giai đoạn bắt đầu', 0, $$ {} $$),
('simple_control_test', 'app_opened', 'Đã mở ứng dụng mục tiêu', 1, $$ {"rules": [{"check": "element_exists", "value": {"package_name_contains": "com.example.targetapp"}}]} $$), -- Thay com.example.targetapp
('simple_control_test', 'element_clicked', 'Đã nhấp vào nút', 2, $$ {} $$),
('simple_control_test', 'text_inputted', 'Đã nhập text', 3, $$ {} $$),
('simple_control_test', 'finished', 'Hoàn thành', 10, $$ {} $$);

-- === Stage Transitions (cho simple_control_test) ===
-- Xóa transitions cũ của strategy này
DELETE FROM public.stage_transitions WHERE strategy_id = 'simple_control_test';

-- 1. Từ 'start', mở app 'com.example.targetapp', chuyển sang 'app_opened'
INSERT INTO public.stage_transitions (strategy_id, current_stage_id, user_intent, priority, action_macro_code, action_params_str, next_stage_id) VALUES
('simple_control_test', 'start', 'init', 0, 'APP_OPEN', $$ {"package_name": "com.example.targetapp"} $$, 'app_opened'); -- Nhớ sửa package name

-- 2. Từ 'app_opened', chờ 2 giây, vẫn ở 'app_opened' (transition này không chuyển stage nhưng lặp 1 lần chờ)
--    Sử dụng loop repeat_n = 1 để chỉ chạy SYS_WAIT 1 lần rồi mới xét tiếp transition khác từ app_opened
INSERT INTO public.stage_transitions (strategy_id, current_stage_id, user_intent, priority, action_macro_code, action_params_str, next_stage_id, loop_type, loop_count) VALUES
('simple_control_test', 'app_opened', 'wait_a_bit', 10, 'SYS_WAIT', $$ {"duration_ms": 2000} $$, 'app_opened', 'repeat_n', 1);

-- 3. Từ 'app_opened', click vào nút có text 'Tiếp tục', chuyển sang 'element_clicked'
INSERT INTO public.stage_transitions (strategy_id, current_stage_id, user_intent, priority, action_macro_code, action_params_str, next_stage_id) VALUES
('simple_control_test', 'app_opened', 'click_continue', 5, 'UI_CLICK', $$ {"target": {"text": "Tiếp tục"}} $$, 'element_clicked'); -- Sửa text nếu cần

-- 4. Từ 'element_clicked', nhập "Hello" vào ô có ID "com.example:id/input", chuyển sang 'text_inputted'
INSERT INTO public.stage_transitions (strategy_id, current_stage_id, user_intent, priority, action_macro_code, action_params_str, next_stage_id) VALUES
('simple_control_test', 'element_clicked', 'input_data', 0, 'UI_INPUT_TEXT', $$ {"target": {"resource_id": "com.example:id/input"}, "text_to_input": "Hello World"} $$, 'text_inputted'); -- Sửa ID và text nếu cần

-- 5. Từ 'text_inputted', nhấn back, chuyển sang 'finished'
INSERT INTO public.stage_transitions (strategy_id, current_stage_id, user_intent, priority, action_macro_code, next_stage_id) VALUES
('simple_control_test', 'text_inputted', 'go_back', 0, 'NAV_GO_BACK', 'finished');


-- === Task Assignments (Giao việc) ===
-- Xóa assignment cũ nếu cần
DELETE FROM public.task_assignments WHERE device_account_id = (SELECT device_account_id from public.device_accounts WHERE device_id = 'test_device_001' AND account_id = 'tiktok_test_1');

-- Giao chiến lược 'simple_control_test' cho account 'tiktok_test_1' trên 'test_device_001'
-- Cần lấy device_account_id tương ứng
INSERT INTO public.task_assignments (device_account_id, strategy_id, status, priority, target_data)
SELECT
    da.device_account_id,
    'simple_control_test',
    'pending',
    10,
    $$ {"goal_type": "test_run", "target_count": 1, "current_count": 0} $$
FROM public.device_accounts da
WHERE da.device_id = 'test_device_001' AND da.account_id = 'tiktok_test_1';

-- Lưu ý: Các lệnh DELETE ở đầu mỗi khối là tùy chọn, dùng khi bạn muốn xóa sạch dữ liệu cũ trước khi thêm mới.
-- Hãy cẩn thận khi chạy các lệnh DELETE trên CSDL production.
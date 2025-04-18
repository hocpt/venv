-- Seed data for Automation Project
-- Version: 2025-04-19

-- AI Personas (Thêm persona mặc định)
INSERT INTO public.ai_personas (persona_id, name, description, system_prompt) VALUES
('default_friendly', 'Friendly Assistant', 'A generally helpful and friendly assistant.', 'You are a helpful assistant. Be friendly and concise.')
ON CONFLICT (persona_id) DO NOTHING;

-- Accounts (Thêm tài khoản mẫu)
INSERT INTO public.accounts (account_id, platform, username, default_persona_id, status) VALUES
('test_tiktok_1', 'tiktok', 'tiktok_user_1', 'default_friendly', 'active'),
('test_fb_1', 'facebook', 'fb_user_1', 'default_friendly', 'active')
ON CONFLICT (account_id) DO NOTHING;

-- Response Templates (Mẫu gốc)
INSERT INTO public.response_templates (template_ref, description, category) VALUES
('greeting_standard', 'Standard greeting response', 'greeting'),
('price_inquiry_default', 'Default response to price inquiries', 'inquiry'),
('thank_you_reply', 'Simple thank you reply', 'generic')
ON CONFLICT (template_ref) DO NOTHING;

-- Template Variations (Biến thể)
INSERT INTO public.template_variations (template_ref, content, language) VALUES
('greeting_standard', 'Xin chào bạn!', 'vi'),
('greeting_standard', 'Chào bạn, mình có thể giúp gì ạ?', 'vi'),
('greeting_standard', 'Hello there!', 'en'),
('price_inquiry_default', 'Chào bạn, bạn vui lòng inbox để mình tư vấn giá chi tiết nhé!', 'vi'),
('price_inquiry_default', 'Bạn quan tâm sản phẩm nào ạ? Inbox mình báo giá nha.', 'vi'),
('thank_you_reply', 'Cảm ơn bạn nhiều!', 'vi'),
('thank_you_reply', 'Thanks!', 'en')
ON CONFLICT DO NOTHING; -- Lưu ý: Không có ràng buộc UNIQUE nên có thể bị trùng nếu chạy lại

-- Strategies (Thêm strategy mẫu cho cả language và control)
INSERT INTO public.strategies (strategy_id, name, description, initial_stage_id, strategy_type) VALUES
('default_interaction', 'Default Conversational Interaction', 'Handles basic greetings and inquiries.', 'greeting_stage', 'language'),
('map_settings_app', 'Explore Settings App', 'Navigates through basic Android Settings screens.', 'settings_main', 'control')
ON CONFLICT (strategy_id) DO NOTHING;

-- Strategy Stages (Thêm stage mẫu)
-- Cho default_interaction (language)
INSERT INTO public.strategy_stages (stage_id, strategy_id, description, stage_order) VALUES
('greeting_stage', 'default_interaction', 'Initial greeting state', 0),
('info_query_stage', 'default_interaction', 'User is asking for information', 1),
('closing_stage', 'default_interaction', 'Ending the conversation', 10)
ON CONFLICT (stage_id) DO NOTHING;
-- Cho map_settings_app (control)
INSERT INTO public.strategy_stages (stage_id, strategy_id, description, stage_order, identifying_elements) VALUES
('settings_main', 'map_settings_app', 'Main Android Settings Screen', 0, '{"has_text": ["Settings", "Network & internet"], "has_id_suffix": [":id/search_bar", ":id/dashboard_container"]}'),
('settings_network', 'map_settings_app', 'Network & internet Screen', 1, '{"has_text": ["Network & internet", "Wi-Fi", "Mobile network"]}'),
('settings_wifi', 'map_settings_app', 'Wi-Fi Screen', 2, '{"has_text": ["Wi‑Fi", "Use Wi‑Fi"], "has_id_suffix": [":id/switch_bar"]}'),
('settings_end', 'map_settings_app', 'End state for mapping', 99, '{}')
ON CONFLICT (stage_id) DO NOTHING;

-- Macro Definitions (Thêm các macro cơ bản)
INSERT INTO public.macro_definitions (macro_code, description, app_target, params_schema) VALUES
('SYS_OPEN_APP', 'Opens an application by package name.', 'system', '{"type": "object", "properties": {"package_name": {"type": "string"}}, "required": ["package_name"]}'),
('SYS_WAIT', 'Pauses execution for a duration.', 'system', '{"type": "object", "properties": {"duration_ms": {"type": "integer"}, "min_ms": {"type": "integer"}, "max_ms": {"type": "integer"}}, "anyOf": [{"required": ["duration_ms"]}, {"required": ["min_ms", "max_ms"]}]}'),
('UI_CLICK', 'Clicks a UI element (by text, id, etc.) or coordinates.', 'generic', '{"type": "object", "properties": {"target": {"type": "object", "properties": {"text": {"type": "string"}, "id": {"type": "string"}, "content_desc": {"type": "string"}, "coords": {"type": "object"}}}}, "required": ["target"]}'),
('UI_SWIPE', 'Performs a swipe gesture.', 'generic', '{"type": "object", "properties": {"direction": {"enum": ["up", "down", "left", "right"]}, "startX": {}, "startY": {}, "endX": {}, "endY": {}, "duration_ms": {}}}'),
('NAV_GO_BACK', 'Simulates the system Back button press.', 'system', '{}')
ON CONFLICT (macro_code) DO NOTHING;

-- Stage Transitions (Thêm transition mẫu)
-- Cho default_interaction (language)
INSERT INTO public.stage_transitions (current_stage_id, user_intent, next_stage_id, response_template_ref, priority) VALUES
('greeting_stage', 'greeting', NULL, 'greeting_standard', 0), -- Ở lại stage greeting, trả lời greeting
('greeting_stage', 'price_query', 'info_query_stage', 'price_inquiry_default', 0), -- Chuyển sang stage hỏi thông tin, trả lời giá
('greeting_stage', 'thank_you', 'closing_stage', 'thank_you_reply', 0), -- Chuyển sang stage kết thúc, cảm ơn
('info_query_stage', 'any', 'greeting_stage', NULL, -1) -- Từ stage hỏi thông tin, nếu user nói gì khác thì quay về greeting (ưu tiên thấp)
ON CONFLICT DO NOTHING; -- Cần khóa UNIQUE(current_stage_id, user_intent, priority) để ON CONFLICT hoạt động đúng

-- Cho map_settings_app (control)
INSERT INTO public.stage_transitions (current_stage_id, user_intent, next_stage_id, action_to_suggest, priority, condition_type, condition_value, loop_type, loop_count) VALUES
-- Từ Main -> Network
('settings_main', 'goto_network', 'settings_network', '{"macro_code": "UI_CLICK", "params": {"target": {"text": "Network & internet"}}}', 0, NULL, NULL, NULL, NULL),
-- Chờ sau khi click
('settings_network', 'wait_after_entry', NULL, '{"macro_code": "SYS_WAIT", "params": {"duration_ms": 1000}}', 10, NULL, NULL, NULL, NULL), -- Ưu tiên cao hơn để chạy trước goto_wifi
-- Từ Network -> Wifi
('settings_network', 'goto_wifi', 'settings_wifi', '{"macro_code": "UI_CLICK", "params": {"target": {"text": "Wi‑Fi"}}}', 0, NULL, NULL, NULL, NULL),
-- Chờ ở màn hình Wifi và quay lại (ví dụ lặp)
('settings_wifi', 'wait_and_back', 'settings_network', '{"macro_code": "SYS_WAIT", "params": {"duration_ms": 1500}}', 10, NULL, NULL, 'repeat_n', 2), -- <<< VÍ DỤ LOOP: Chờ 2 lần
('settings_wifi', 'go_back_action', 'settings_network', '{"macro_code": "NAV_GO_BACK", "params": {}}', 0, NULL, NULL, NULL, NULL), -- Hành động quay lại sau khi lặp xong (priority thấp hơn wait_and_back)
-- Từ Network -> Main
('settings_network', 'go_back_to_main', 'settings_main', '{"macro_code": "NAV_GO_BACK", "params": {}}', 0, 'element_exists_text', 'Mobile network', NULL, NULL), -- <<< VÍ DỤ CONDITION: Chỉ back nếu thấy chữ Mobile network
-- Chuyển về End khi ở Main (ví dụ)
('settings_main', 'finish_mapping', 'settings_end', '{"macro_code": "SYS_WAIT", "params": {"duration_ms": 500}}', -1, NULL, NULL, NULL, NULL) -- Ưu tiên thấp
ON CONFLICT DO NOTHING;

-- Thêm dữ liệu cho các bảng khác nếu cần (prompt_templates, api_keys, etc.)
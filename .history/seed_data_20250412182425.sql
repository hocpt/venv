-- ====================================================================
-- Script SQL tạo dữ liệu mẫu (Seed Data) cho database 'automation'
-- ====================================================================

-- TÙY CHỌN: Xóa dữ liệu cũ trong các bảng cấu hình trước khi thêm mới
-- Lưu ý thứ tự xóa để tránh lỗi khóa ngoại!
/*
DELETE FROM public.stage_transitions;
DELETE FROM public.template_variations;
DELETE FROM public.response_templates;
DELETE FROM public.simple_rules; -- Nếu bạn có dùng bảng này
DELETE FROM public.accounts WHERE default_persona_id IS NOT NULL; -- Xóa account có FK trước
DELETE FROM public.ai_personas;
DELETE FROM public.strategy_stages;
DELETE FROM public.strategies;
DELETE FROM public.prompt_templates;
DELETE FROM public.task_state WHERE task_name = 'suggestion_job';
-- Không nên xóa accounts, interaction_history, suggested_rules trừ khi test lại từ đầu hẳn
*/

-- Bắt đầu một transaction để đảm bảo tất cả lệnh chạy thành công hoặc không lệnh nào cả
BEGIN;

-- 1. AI Personas (Thêm các persona mặc định và ví dụ)
-- Đảm bảo các ID này khớp với cấu hình trong config.py
INSERT INTO public.ai_personas (persona_id, name, description, base_prompt, model_name, generation_config, updated_at) VALUES
('general_assistant', 'Trợ lý Chung', 'Persona trả lời mặc định, phong cách thân thiện, hữu ích.', E'Bạn là một trợ lý ảo tên Linh, rất thân thiện và luôn cố gắng giúp đỡ người dùng một cách nhiệt tình nhất có thể. Hãy trả lời các câu hỏi một cách rõ ràng, ngắn gọn và lịch sự.', 'models/gemini-1.5-flash-latest', NULL, NOW()),
('rule_suggester', 'Bộ Đề xuất Luật', 'Persona chuyên phân tích các cuộc hội thoại thành công để đề xuất keywords và template mới.', E'Phân tích tương tác được cung cấp. Nhiệm vụ của bạn là xác định các từ khóa kích hoạt cốt lõi (ngắn gọn, tiếng Việt, phân cách bằng dấu phẩy) từ lời nói của người dùng và tạo ra một mẫu trả lời chung chung, có thể tái sử dụng (bằng tiếng Việt) từ phản hồi của trợ lý. Đề xuất thêm một Category phù hợp (từ danh sách được cung cấp hoặc "other") và một Template Ref gợi nhớ (viết thường, không dấu, dùng gạch dưới). Ưu tiên sự ngắn gọn và khả năng áp dụng rộng rãi cho keywords và template ref. Nếu không thể tổng quát hóa template text, ghi rõ "Cannot generalize".', 'models/gemini-1.5-flash-latest', '{"temperature": 0.2, "max_output_tokens": 400}', NOW()),
('sales_friendly_female', 'NV Bán hàng Nữ Thân thiện', 'Nhân viên bán hàng nữ, khoảng 25 tuổi, giọng văn tươi tắn, tập trung vào việc giới thiệu sản phẩm và chốt đơn.', E'Bạn là một nhân viên bán hàng nữ tên Mai, 25 tuổi, làm việc tại cửa hàng [Tên cửa hàng]. Phong cách của bạn rất thân thiện, nhiệt tình và luôn tươi cười. Mục tiêu chính là giới thiệu sản phẩm [Tên Sản Phẩm], giải đáp thắc mắc và thuyết phục khách hàng mua hàng. Hãy sử dụng các biểu cảm vui vẻ (ví dụ: ^^, 😊) và ngôn ngữ gần gũi, tự nhiên.', NULL, '{"temperature": 0.8}', NOW())
ON CONFLICT (persona_id) DO UPDATE SET -- Cập nhật nếu ID đã tồn tại
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    base_prompt = EXCLUDED.base_prompt,
    model_name = EXCLUDED.model_name,
    generation_config = EXCLUDED.generation_config,
    updated_at = NOW();

-- 2. Prompt Templates (Thêm các template cho các tác vụ chính)
INSERT INTO public.prompt_templates (name, task_type, template_content, updated_at) VALUES
(
    'Default Generate Reply', 'generate_reply',
    E'{{ base_prompt | default("Bạn là một trợ lý ảo hữu ích.") }}\n\n### Ngữ cảnh Hội thoại:\n- Nền tảng: {{ account_platform | default("Không rõ") }}\n- Mục tiêu Tài khoản: {{ account_goal | default("Không rõ") }}\n- Giai đoạn Hiện tại: {{ current_stage_id | default("Không rõ") }}\n- Ý định Người dùng (đã phát hiện): {{ user_intent | default("Chưa rõ") }}\n- Ghi chú về Tài khoản: {{ account_notes | default("Không có") }}\n\n### Lịch sử Hội thoại Gần đây (Từ cũ đến mới nhất):\n{% if formatted_history %}{{ formatted_history }}{% else %}Chưa có lịch sử.{% endif %}\n\n### Tin nhắn Mới Nhất từ Người dùng:\n"""\n{{ received_text }}\n"""\n\n### Nhiệm vụ của bạn:\nDựa vào vai trò được mô tả trong prompt nền tảng, ngữ cảnh hội thoại, lịch sử và tin nhắn mới nhất của người dùng, hãy tạo ra một câu trả lời bằng **tiếng Việt** phù hợp, tự nhiên, đúng với giọng văn của vai trò và hướng tới mục tiêu của tài khoản. Trả lời trực tiếp, không dùng lời dẫn như "Câu trả lời của tôi là:". Tránh dùng placeholder bạn không thể tự điền.',
    NOW()
),
(
    'Default Suggest Rule Enhanced', 'suggest_rule',
    E'{{ base_prompt | default("Bạn là một AI phân tích hội thoại.") }}\n\nPhân tích tương tác thành công sau đây, nơi mà phản hồi của trợ lý được tạo bởi một AI khác:\n\n### Ngữ cảnh Tương tác:\n- User Intent Detected: {{ user_intent | default("N/A") }}\n- Conversation Stage: {{ stage_id | default("N/A") }}\n- Overall Strategy: {{ strategy_id | default("N/A") }}\n\n### Nội dung Tương tác:\n- User Said: """{{ received_text }}"""\n- Assistant (AI) Replied: """{{ sent_text }}"""\n\n### Nhiệm vụ của bạn:\n1.  **Identify Trigger Keywords:** Trích xuất keywords/cụm từ ngắn gọn (tiếng Việt, phẩy cách) từ "User Said" đại diện lý do chính cho phản hồi.\n2.  **Suggest Category:** Đề xuất MỘT category phù hợp từ danh sách sau nếu có: [greeting, price_query, shipping_query, product_info_query, compliment, complaint, connection_request, spam, fallback, clarification, other]. Nếu không, đề xuất "other".\n3.  **Suggest Template Ref:** Đề xuất một mã tham chiếu ngắn gọn, mô tả, duy nhất (chữ thường, số, gạch dưới, vd: `reply_price_general`, `ask_shipping_details`).\n4.  **Create Reusable Template Text:** Tổng quát hóa "Assistant (AI) Replied" thành mẫu văn bản tiếng Việt tái sử dụng. Thay chi tiết bằng placeholder [Name], [Time], [ID], [Number] nếu hợp lý. Nếu không thể, ghi "Cannot generalize".\n\n### Định dạng Output:\nChỉ trả lời theo **chính xác** định dạng sau, mỗi mục trên một dòng:\nKeywords: <keywords>\nCategory: <category>\nTemplate Ref: <template_ref>\nTemplate Text: <template text hoặc "Cannot generalize">',
    NOW()
),
(
    'Default Detect Intent', 'detect_intent',
    E'Phân loại ý định chính của tin nhắn tiếng Việt sau đây vào MỘT trong các loại sau: [{{ valid_intents_list | join(", ") }}].\n\nTin nhắn:\n"""\n{{ text }}\n"""\n\nChỉ trả về DUY NHẤT nhãn ý định (viết thường, tiếng Anh, không dấu, không giải thích). Ví dụ: price_query',
    NOW()
)
ON CONFLICT (name) DO UPDATE SET -- Cập nhật nếu tên đã tồn tại
    template_content = EXCLUDED.template_content,
    task_type = EXCLUDED.task_type,
    updated_at = NOW();

-- 3. Strategies (Thêm chiến lược mặc định - Bước 1)
INSERT INTO public.strategies (strategy_id, name, description, initial_stage_id) VALUES
('default_strategy', 'Default Interaction', 'Luồng tương tác chung, mặc định.', NULL) -- Initial stage tạm thời NULL
ON CONFLICT (strategy_id) DO NOTHING;

-- 4. Strategy Stages (Thêm các stage cho chiến lược mặc định)
INSERT INTO public.strategy_stages (stage_id, strategy_id, description, stage_order) VALUES
('initial', 'default_strategy', 'Giai đoạn bắt đầu tương tác', 0),
('information_gathering', 'default_strategy', 'Giai đoạn thu thập thêm thông tin', 1),
('providing_info', 'default_strategy', 'Giai đoạn cung cấp thông tin / trả lời', 2),
('closing', 'default_strategy', 'Giai đoạn kết thúc hội thoại', 99)
ON CONFLICT (stage_id) DO NOTHING;

-- 4.5 Cập nhật initial_stage_id cho strategies
UPDATE public.strategies SET initial_stage_id = 'initial' WHERE strategy_id = 'default_strategy';

-- 5. Response Templates (Thêm vài template cơ bản)
INSERT INTO public.response_templates (template_ref, category, description) VALUES
('greet_hello', 'greeting', 'Chào hỏi thông thường'),
('fallback_generic', 'fallback', 'Phản hồi chung khi không biết trả lời gì'),
('ask_more_info', 'clarification', 'Hỏi thêm chi tiết'),
('confirm_received', 'confirmation', 'Xác nhận đã nhận thông tin'),
('fallback_make_friend', 'fallback', 'Phản hồi dự phòng cho mục tiêu Kết bạn'),
('fallback_product_sales', 'fallback', 'Phản hồi dự phòng cho mục tiêu Bán hàng')
ON CONFLICT (template_ref) DO NOTHING;

-- 6. Template Variations (Thêm biến thể)
INSERT INTO public.template_variations (template_ref, variation_text) VALUES
('greet_hello', 'Xin chào bạn!'),
('greet_hello', 'Chào bạn, mình có thể giúp gì?'),
('greet_hello', 'Hi bạn ^^'),
('fallback_generic', 'Cảm ơn bạn đã chia sẻ thông tin ạ.'),
('fallback_generic', 'Mình đã ghi nhận thông tin này rồi nhé.'),
('fallback_generic', 'Hmm, để mình xem lại vấn đề này một chút.'),
('ask_more_info', 'Bạn có thể nói rõ hơn được không ạ?'),
('ask_more_info', 'Để hiểu rõ hơn, bạn cung cấp thêm chi tiết giúp mình nhé?'),
('ask_more_info', 'Mình chưa rõ lắm ý bạn, bạn giải thích thêm được không?'),
('confirm_received', 'Ok bạn, mình nhận được rồi nhé.'),
('confirm_received', 'Đã nhận thông tin ạ.'),
('confirm_received', 'Okie bạn!'),
('fallback_make_friend','Oke bạn! ^^'),
('fallback_make_friend','Cảm ơn bạn nha!'),
('fallback_product_sales','Dạ vâng ạ.'),
('fallback_product_sales','Cảm ơn bạn đã quan tâm ạ!')
ON CONFLICT DO NOTHING; -- Giả định không có ràng buộc UNIQUE(template_ref, variation_text)

-- 7. Accounts (Thêm tài khoản ví dụ)
INSERT INTO public.accounts (account_id, platform, username, status, goal, notes, default_strategy_id, default_persona_id, created_at, updated_at) VALUES
('test_fb_01', 'facebook', 'FB Test User', 'active', 'make_friend', 'Tài khoản dùng để test kết bạn', 'default_strategy', 'general_assistant', NOW(), NOW()),
('test_tiktok_01', 'tiktok', 'TikTok Sales Test', 'active', 'product_sales', 'Tài khoản test bán hàng', 'default_strategy', 'sales_friendly_female', NOW(), NOW())
ON CONFLICT (account_id) DO NOTHING;

-- 8. Stage Transitions (Thêm luật chuyển tiếp cơ bản)
INSERT INTO public.stage_transitions (current_stage_id, user_intent, condition_logic, next_stage_id, action_to_suggest, response_template_ref, priority) VALUES
('initial', 'greeting', NULL, 'initial', NULL, 'greet_hello', 10),
('initial', 'product_info_query', NULL, 'information_gathering', NULL, 'ask_more_info', 5),
('initial', 'price_query', NULL, 'information_gathering', NULL, 'ask_more_info', 5),
('information_gathering', 'positive_generic', NULL, 'providing_info', NULL, 'confirm_received', 5),
('information_gathering', 'compliment', NULL, 'providing_info', NULL, 'confirm_received', 5),
('initial', 'any', NULL, 'providing_info', NULL, NULL, 0), -- Nếu không khớp gì ở initial -> để AI xử lý và sang providing_info
('information_gathering', 'any', NULL, 'providing_info', NULL, NULL, 0), -- Nếu đang hỏi mà nhận được gì khác -> để AI xử lý và sang providing_info
('providing_info', 'compliment', NULL, 'closing', NULL, 'fallback_generic', 5), -- Nhận lời khen -> cảm ơn và kết thúc
('providing_info', 'greeting', NULL, 'providing_info', NULL, 'greet_hello', 1) -- Nếu đang nói chuyện mà chào -> chào lại
ON CONFLICT (transition_id) DO NOTHING; -- transition_id là SERIAL

-- 9. Task State (Khởi tạo trạng thái cho tác vụ nền)
INSERT INTO public.task_state (task_name, last_processed_id, last_run_timestamp) VALUES
('suggestion_job', 0, NULL)
ON CONFLICT (task_name) DO UPDATE SET
    last_processed_id = LEAST(EXCLUDED.last_processed_id, public.task_state.last_processed_id), -- Giữ ID cũ hơn nếu chạy lại script
    last_run_timestamp = NULL; -- Reset thời gian chạy cuối


COMMIT; -- Kết thúc transaction
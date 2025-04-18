-- PostgreSQL Schema for Automation Project
-- Version: 2025-04-19 (Tổng hợp các thay đổi)

-- Xóa bảng cũ nếu tồn tại (cẩn thận khi chạy trên DB có dữ liệu)
-- DROP TABLE IF EXISTS public.phone_action_log CASCADE;
-- DROP TABLE IF EXISTS public.stage_transitions CASCADE;
-- DROP TABLE IF EXISTS public.strategy_stages CASCADE;
-- DROP TABLE IF EXISTS public.strategies CASCADE;
-- DROP TABLE IF EXISTS public.macro_definitions CASCADE;
-- DROP TABLE IF EXISTS public.accounts CASCADE;
-- DROP TABLE IF EXISTS public.template_variations CASCADE;
-- DROP TABLE IF EXISTS public.response_templates CASCADE;
-- DROP TABLE IF EXISTS public.simple_rules CASCADE;
-- DROP TABLE IF EXISTS public.ai_personas CASCADE;
-- DROP TABLE IF EXISTS public.prompt_templates CASCADE;
-- DROP TABLE IF EXISTS public.interaction_history CASCADE;
-- DROP TABLE IF EXISTS public.ai_suggestions CASCADE;
-- DROP TABLE IF EXISTS public.api_keys CASCADE;
-- DROP TABLE IF EXISTS public.scheduled_jobs CASCADE;
-- DROP TABLE IF EXISTS public.simulation_configs CASCADE;
-- DROP TABLE IF EXISTS public.simulation_results CASCADE;

-- Bảng: AI Personas (Tính cách AI)
CREATE TABLE IF NOT EXISTS public.ai_personas (
    persona_id character varying(50) NOT NULL PRIMARY KEY,
    name character varying(100) NOT NULL,
    description text,
    system_prompt text, -- Prompt hệ thống mặc định cho persona này
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone
);
COMMENT ON TABLE public.ai_personas IS 'Định nghĩa các tính cách/vai trò khác nhau cho AI.';

-- Bảng: Accounts (Tài khoản MXH)
CREATE TABLE IF NOT EXISTS public.accounts (
    account_id character varying(50) NOT NULL PRIMARY KEY,
    platform character varying(50), -- Vd: facebook, tiktok, zalo...
    username character varying(100),
    details jsonb, -- Lưu token, cookie, proxy, etc.
    status character varying(50) DEFAULT 'active', -- Vd: active, inactive, error
    last_used timestamp with time zone,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone,
    goal text, -- Mục tiêu khi chạy automation cho tài khoản này
    default_persona_id character varying(50) REFERENCES public.ai_personas(persona_id) ON DELETE SET NULL -- Persona mặc định
);
COMMENT ON TABLE public.accounts IS 'Quản lý thông tin các tài khoản mạng xã hội cần tự động hóa.';
CREATE INDEX IF NOT EXISTS idx_accounts_platform ON public.accounts(platform);
CREATE INDEX IF NOT EXISTS idx_accounts_status ON public.accounts(status);

-- Bảng: Simple Rules (Luật đơn giản cho AI Ngôn ngữ)
CREATE TABLE IF NOT EXISTS public.simple_rules (
    rule_id character varying(50) NOT NULL PRIMARY KEY,
    name character varying(100),
    description text,
    conditions jsonb, -- JSON chứa điều kiện (vd: keywords, intent, sentiment)
    action_type character varying(50), -- Vd: reply_template, set_variable, trigger_strategy
    action_value text, -- Vd: template_ref, variable_name=value, strategy_id
    priority integer DEFAULT 0,
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone
);
COMMENT ON TABLE public.simple_rules IS 'Các luật đơn giản dạng If-Then cho AI hội thoại.';
CREATE INDEX IF NOT EXISTS idx_simple_rules_active ON public.simple_rules(is_active);

-- Bảng: Response Templates (Mẫu câu trả lời gốc)
CREATE TABLE IF NOT EXISTS public.response_templates (
    template_ref character varying(100) NOT NULL PRIMARY KEY,
    description text,
    category character varying(50),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone
);
COMMENT ON TABLE public.response_templates IS 'Quản lý các nhóm mẫu câu trả lời.';
CREATE INDEX IF NOT EXISTS idx_response_templates_category ON public.response_templates(category);

-- Bảng: Template Variations (Các biến thể của mẫu câu)
CREATE TABLE IF NOT EXISTS public.template_variations (
    variation_id SERIAL PRIMARY KEY,
    template_ref character varying(100) NOT NULL REFERENCES public.response_templates(template_ref) ON DELETE CASCADE,
    content text NOT NULL, -- Nội dung biến thể
    language character varying(10) DEFAULT 'vi',
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone
);
COMMENT ON TABLE public.template_variations IS 'Lưu các biến thể cụ thể cho mỗi mẫu câu trả lời.';
CREATE INDEX IF NOT EXISTS idx_template_variations_ref ON public.template_variations(template_ref);

-- Bảng: Strategies (Chiến lược tổng thể)
CREATE TABLE IF NOT EXISTS public.strategies (
    strategy_id character varying(50) NOT NULL PRIMARY KEY,
    name character varying(100) NOT NULL UNIQUE,
    description text,
    initial_stage_id character varying(50), -- Stage bắt đầu (sẽ thêm FK sau)
    strategy_type VARCHAR(20) NOT NULL DEFAULT 'language' CHECK (strategy_type IN ('language', 'control')), -- Loại chiến lược
    updated_at timestamp with time zone -- Thời gian cập nhật cuối
);
COMMENT ON TABLE public.strategies IS 'Định nghĩa các chiến lược tổng thể (hội thoại hoặc điều khiển).';
CREATE INDEX IF NOT EXISTS idx_strategies_type ON public.strategies(strategy_type);

-- Bảng: Strategy Stages (Các giai đoạn/màn hình trong chiến lược)
CREATE TABLE IF NOT EXISTS public.strategy_stages (
    stage_id character varying(50) NOT NULL PRIMARY KEY,
    strategy_id character varying(50) NOT NULL REFERENCES public.strategies(strategy_id) ON DELETE CASCADE, -- Liên kết với strategy
    description text,
    stage_order integer DEFAULT 0, -- Thứ tự hiển thị (tùy chọn)
    identifying_elements jsonb NULL -- Quy tắc JSON để nhận diện stage (cho control)
);
COMMENT ON TABLE public.strategy_stages IS 'Các giai đoạn (hội thoại) hoặc trạng thái màn hình (điều khiển) trong một chiến lược.';
CREATE INDEX IF NOT EXISTS idx_strategy_stages_strategy ON public.strategy_stages(strategy_id);

-- Thêm lại FK cho strategies.initial_stage_id sau khi strategy_stages được tạo
-- Chạy riêng lệnh này sau khi cả 2 bảng đã được tạo
-- ALTER TABLE public.strategies
-- ADD CONSTRAINT fk_strategies_initial_stage
-- FOREIGN KEY (initial_stage_id) REFERENCES public.strategy_stages(stage_id) ON DELETE SET NULL;

-- Bảng: Stage Transitions (Luật chuyển đổi giữa các giai đoạn/hành động)
CREATE TABLE IF NOT EXISTS public.stage_transitions (
    transition_id SERIAL PRIMARY KEY,
    current_stage_id character varying(50) NOT NULL REFERENCES public.strategy_stages(stage_id) ON DELETE CASCADE,
    user_intent character varying(100) NOT NULL, -- Ý định người dùng hoặc tín hiệu trigger
    next_stage_id character varying(50) NULL REFERENCES public.strategy_stages(stage_id) ON DELETE SET NULL, -- Stage kế tiếp (có thể NULL)
    priority integer DEFAULT 0 NOT NULL,
    -- Cho AI Ngôn ngữ
    response_template_ref character varying(100) NULL REFERENCES public.response_templates(template_ref) ON DELETE SET NULL,
    -- Cho AI Điều khiển
    action_to_suggest jsonb NULL, -- JSON chứa {"macro_code": "...", "params": {...}}
    condition_type character varying(50) NULL, -- Loại điều kiện kích hoạt action/transition
    condition_value text NULL, -- Giá trị điều kiện
    -- Cho Vòng lặp (AI Điều khiển)
    loop_type VARCHAR(20) NULL,
    loop_count INTEGER NULL,
    loop_condition_type VARCHAR(50) NULL,
    loop_condition_value TEXT NULL,
    loop_target_selector JSONB NULL,
    loop_variable_name VARCHAR(50) NULL,
    -- Chung
    updated_at timestamp with time zone -- Thời gian cập nhật cuối (NÊN THÊM Trigger để tự động cập nhật)
);
COMMENT ON TABLE public.stage_transitions IS 'Các luật chuyển đổi giữa các stage hoặc hành động thực thi tại một stage.';
CREATE INDEX IF NOT EXISTS idx_stage_transitions_current_stage ON public.stage_transitions(current_stage_id);
CREATE INDEX IF NOT EXISTS idx_stage_transitions_intent ON public.stage_transitions(user_intent);

-- Bảng: Macro Definitions (Định nghĩa Macro Code cho AI Điều khiển)
CREATE TABLE IF NOT EXISTS public.macro_definitions (
    macro_code character varying(100) NOT NULL PRIMARY KEY,
    description text,
    app_target character varying(50) DEFAULT 'system', -- system, generic, tiktok, zalo...
    params_schema jsonb, -- JSON Schema mô tả params cần thiết (tùy chọn)
    notes text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone
);
COMMENT ON TABLE public.macro_definitions IS 'Lưu trữ định nghĩa và mô tả cho các Macro Code điều khiển.';
CREATE INDEX IF NOT EXISTS idx_macro_definitions_app ON public.macro_definitions(app_target);

-- Bảng: Phone Action Log (Log hành động của AI Điều khiển)
CREATE TABLE IF NOT EXISTS public.phone_action_log (
    log_id SERIAL PRIMARY KEY,
    session_id character varying(100), -- ID của một phiên chạy chiến lược
    timestamp timestamp with time zone DEFAULT CURRENT_TIMESTAMP, -- Thời gian log được ghi
    device_id character varying(100), -- ID thiết bị (nếu có)
    account_id character varying(50), -- ID tài khoản đang chạy
    strategy_id character varying(50), -- ID chiến lược đang chạy
    strategy_version character varying(50), -- Version của gói chiến lược
    current_stage character varying(50), -- Stage hiện tại khi action xảy ra
    action_macro_code character varying(100), -- Macro code được thực thi
    action_params_json jsonb, -- Tham số đã dùng cho macro
    execution_status character varying(20), -- success, fail, skipped...
    execution_error text, -- Thông báo lỗi nếu thất bại
    received_state_json jsonb -- JSON trạng thái UI nhận được trước khi thực thi (tùy chọn, có thể rất lớn)
);
COMMENT ON TABLE public.phone_action_log IS 'Log chi tiết các hành động được thực thi bởi AI điều khiển trên điện thoại.';
CREATE INDEX IF NOT EXISTS idx_phone_log_session ON public.phone_action_log(session_id);
CREATE INDEX IF NOT EXISTS idx_phone_log_timestamp ON public.phone_action_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_phone_log_account ON public.phone_action_log(account_id);
CREATE INDEX IF NOT EXISTS idx_phone_log_strategy ON public.phone_action_log(strategy_id);

-- Bảng: Interaction History (Lịch sử tương tác AI Ngôn ngữ - giữ cấu trúc cũ nếu có)
CREATE TABLE IF NOT EXISTS public.interaction_history (
    interaction_id SERIAL PRIMARY KEY,
    session_id character varying(100) NOT NULL, -- ID của phiên hội thoại
    "timestamp" timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    user_input text,
    detected_intent character varying(100),
    matched_rule_id character varying(50),
    matched_template_ref character varying(100),
    ai_response text,
    current_stage character varying(50),
    next_stage character varying(50),
    metadata jsonb -- Lưu thông tin khác nếu cần
);
COMMENT ON TABLE public.interaction_history IS 'Lịch sử chi tiết các lượt tương tác trong hội thoại.';
CREATE INDEX IF NOT EXISTS idx_interaction_history_session ON public.interaction_history(session_id);
CREATE INDEX IF NOT EXISTS idx_interaction_history_timestamp ON public.interaction_history("timestamp");

-- Bảng: Prompt Templates (Mẫu prompt cho LLM)
CREATE TABLE IF NOT EXISTS public.prompt_templates (
    prompt_ref character varying(100) NOT NULL PRIMARY KEY,
    description text,
    template_content text NOT NULL, -- Nội dung prompt với các placeholder
    variables text[], -- Mảng chứa tên các biến placeholder
    category character varying(50),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone
);
COMMENT ON TABLE public.prompt_templates IS 'Quản lý các mẫu prompt dùng để gọi LLM.';

-- Bảng: AI Suggestions (Gợi ý trả lời từ AI - cần xem lại logic sử dụng)
CREATE TABLE IF NOT EXISTS public.ai_suggestions (
    suggestion_id SERIAL PRIMARY KEY,
    interaction_id integer REFERENCES public.interaction_history(interaction_id) ON DELETE SET NULL, -- Liên kết với lịch sử
    prompt_ref character varying(100) REFERENCES public.prompt_templates(prompt_ref) ON DELETE SET NULL,
    input_context text, -- Ngữ cảnh đầu vào khi gọi AI
    generated_response text, -- Nội dung AI tạo ra
    status character varying(20) DEFAULT 'pending', -- pending, accepted, rejected
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE public.ai_suggestions IS 'Lưu trữ các gợi ý trả lời do AI tạo ra.';

-- Bảng: API Keys (Quản lý khóa API truy cập hệ thống)
CREATE TABLE IF NOT EXISTS public.api_keys (
    key_id SERIAL PRIMARY KEY,
    api_key character varying(128) NOT NULL UNIQUE, -- Khóa API thực tế
    description text,
    permissions jsonb, -- Quyền hạn của khóa (vd: {'read': true, 'write_control': false})
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    last_used timestamp with time zone,
    expires_at timestamp with time zone
);
COMMENT ON TABLE public.api_keys IS 'Quản lý các khóa API để truy cập hệ thống.';
CREATE INDEX IF NOT EXISTS idx_api_keys_key ON public.api_keys(api_key);

-- Bảng: Scheduled Jobs (Lưu trữ thông tin các tác vụ nền - cấu trúc có thể thay đổi tùy thư viện)
-- Cấu trúc này đơn giản, có thể cần điều chỉnh nếu dùng SQLAlchemyJobStore của APScheduler
CREATE TABLE IF NOT EXISTS public.scheduled_jobs (
    job_id character varying(191) NOT NULL PRIMARY KEY, -- Thường là string do APScheduler tạo
    job_type character varying(100), -- Loại công việc (vd: 'run_strategy', 'cleanup_logs')
    trigger_type character varying(50), -- Kiểu trigger (vd: 'interval', 'cron', 'date')
    trigger_config jsonb, -- Cấu hình chi tiết của trigger
    func_ref character varying(255), -- Đường dẫn đến hàm thực thi
    args jsonb, -- Tham số dạng list cho hàm
    kwargs jsonb, -- Tham số dạng dict cho hàm
    next_run_time timestamp with time zone,
    status character varying(20) DEFAULT 'active', -- active, paused
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone
);
COMMENT ON TABLE public.scheduled_jobs IS 'Thông tin về các tác vụ được lên lịch chạy tự động.';
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_next_run ON public.scheduled_jobs(next_run_time);
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_status ON public.scheduled_jobs(status);

-- Bảng: Simulation Configs (Cấu hình các kịch bản mô phỏng)
CREATE TABLE IF NOT EXISTS public.simulation_configs (
    config_id SERIAL PRIMARY KEY,
    name character varying(100) NOT NULL,
    description text,
    strategy_id character varying(50) REFERENCES public.strategies(strategy_id) ON DELETE SET NULL,
    persona_id character varying(50) REFERENCES public.ai_personas(persona_id) ON DELETE SET NULL,
    simulation_parameters jsonb, -- Các tham số đặc biệt cho mô phỏng
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE public.simulation_configs IS 'Lưu cấu hình cho các kịch bản mô phỏng AI.';

-- Bảng: Simulation Results (Kết quả các lần chạy mô phỏng)
CREATE TABLE IF NOT EXISTS public.simulation_results (
    result_id SERIAL PRIMARY KEY,
    config_id integer NOT NULL REFERENCES public.simulation_configs(config_id) ON DELETE CASCADE,
    start_time timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    end_time timestamp with time zone,
    status character varying(50), -- completed, failed, running
    summary_metrics jsonb, -- Các chỉ số tổng hợp kết quả
    full_log text -- Log chi tiết của lần chạy mô phỏng (có thể rất lớn)
);
COMMENT ON TABLE public.simulation_results IS 'Lưu kết quả chi tiết của các lần chạy mô phỏng AI.';
CREATE INDEX IF NOT EXISTS idx_simulation_results_config ON public.simulation_results(config_id);
CREATE INDEX IF NOT EXISTS idx_simulation_results_status ON public.simulation_results(status);


-- Thêm các FKs còn thiếu (chạy sau khi tất cả bảng đã tạo)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_strategies_initial_stage') THEN
        ALTER TABLE public.strategies
        ADD CONSTRAINT fk_strategies_initial_stage
        FOREIGN KEY (initial_stage_id) REFERENCES public.strategy_stages(stage_id) ON DELETE SET NULL;
        RAISE NOTICE 'Constraint fk_strategies_initial_stage added.';
    ELSE
        RAISE NOTICE 'Constraint fk_strategies_initial_stage already exists.';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_transitions_next_stage') THEN
        ALTER TABLE public.stage_transitions
        ADD CONSTRAINT fk_transitions_next_stage
        FOREIGN KEY (next_stage_id) REFERENCES public.strategy_stages(stage_id) ON DELETE SET NULL;
         RAISE NOTICE 'Constraint fk_transitions_next_stage added.';
    ELSE
        RAISE NOTICE 'Constraint fk_transitions_next_stage already exists.';
    END IF;

    -- Thêm các FK khác nếu cần...

END $$;
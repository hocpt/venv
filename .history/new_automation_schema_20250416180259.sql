-- PostgreSQL database dump
-- Cập nhật lần cuối: 2025-04-16

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;
SET default_tablespace = '';
SET default_table_access_method = heap;

-- Bảng: AI Personas
CREATE TABLE public.ai_personas (
    persona_id character varying(50) NOT NULL PRIMARY KEY,
    name character varying(100) NOT NULL UNIQUE,
    description text,
    base_prompt text NOT NULL,
    model_name character varying(100),
    generation_config jsonb,
    fallback_template_ref character varying(50), -- Thêm cột này
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone
);
COMMENT ON TABLE public.ai_personas IS 'Lưu trữ các cấu hình tính cách AI cơ bản (persona).';
COMMENT ON COLUMN public.ai_personas.fallback_template_ref IS 'Template Ref dùng làm fallback nếu AI trả lời không phù hợp.';

-- Bảng: Accounts
CREATE TABLE public.accounts (
    account_id character varying(50) NOT NULL PRIMARY KEY,
    platform character varying(20) NOT NULL,
    username character varying(100),
    password character varying(255), -- Cân nhắc mã hóa nếu lưu password thật
    cookie text,
    proxy character varying(100),
    status character varying(20) DEFAULT 'active'::character varying NOT NULL CHECK (status IN ('active', 'inactive', 'error', 'limited')),
    goal character varying(50),
    notes text,
    default_strategy_id character varying(50),
    default_persona_id character varying(50),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone
);
COMMENT ON TABLE public.accounts IS 'Lưu trữ thông tin các tài khoản mạng xã hội hoặc đối tượng tương tác.';

-- Bảng: Response Templates (Chứa Ref)
CREATE TABLE public.response_templates (
    template_ref character varying(50) NOT NULL PRIMARY KEY,
    category character varying(50),
    description text
);
COMMENT ON TABLE public.response_templates IS 'Lưu trữ mã tham chiếu và thông tin chung của các mẫu câu trả lời.';

-- Bảng: Template Variations (Chứa nội dung cụ thể)
CREATE TABLE public.template_variations (
    variation_id SERIAL PRIMARY KEY,
    template_ref character varying(50) NOT NULL,
    variation_text text NOT NULL
    -- Ràng buộc UNIQUE đã thêm ở bước trước
    -- CONSTRAINT template_variations_ref_text_unique UNIQUE (template_ref, variation_text)
);
COMMENT ON TABLE public.template_variations IS 'Lưu trữ các biến thể nội dung cho mỗi mẫu câu trả lời (template_ref).';
CREATE INDEX idx_template_variations_ref ON public.template_variations(template_ref);

-- Bảng: Simple Rules (Luật đơn giản dựa trên Keywords)
CREATE TABLE public.simple_rules (
    rule_id SERIAL PRIMARY KEY,
    trigger_keywords text NOT NULL,
    category character varying(50),
    condition_logic character varying(50) DEFAULT 'CONTAINS_ANY'::character varying,
    response_template_ref character varying(50) NOT NULL,
    priority integer DEFAULT 0 NOT NULL,
    notes text
    -- Ràng buộc UNIQUE đã thêm ở bước trước
    -- CONSTRAINT simple_rules_kw_cat_ref_unique UNIQUE (trigger_keywords, category, response_template_ref)
);
COMMENT ON TABLE public.simple_rules IS 'Lưu trữ các luật đơn giản dựa trên keywords.';
CREATE INDEX idx_simple_rules_category ON public.simple_rules(category);

-- Bảng: Strategies (Chiến lược)
CREATE TABLE public.strategies (
    strategy_id character varying(50) NOT NULL PRIMARY KEY,
    name character varying(100) NOT NULL UNIQUE, -- Thêm UNIQUE
    description text,
    initial_stage_id character varying(50) -- Khóa ngoại sẽ thêm sau khi có strategy_stages
);
COMMENT ON TABLE public.strategies IS 'Định nghĩa các chiến lược tương tác tổng thể.';

-- Bảng: Strategy Stages (Các giai đoạn trong chiến lược)
CREATE TABLE public.strategy_stages (
    stage_id character varying(50) NOT NULL PRIMARY KEY,
    strategy_id character varying(50) NOT NULL,
    stage_order integer DEFAULT 0 NOT NULL,
    description text,
    identifying_elements jsonb -- (Mới) Lưu các đặc điểm nhận dạng màn hình (tùy chọn)
);
COMMENT ON TABLE public.strategy_stages IS 'Định nghĩa các giai đoạn (màn hình/trạng thái) trong một chiến lược.';
COMMENT ON COLUMN public.strategy_stages.identifying_elements IS 'JSONB chứa các quy tắc/element ID/text để nhận dạng stage này từ dữ liệu UI.';
CREATE INDEX idx_strategy_stages_strategy_id ON public.strategy_stages(strategy_id);

-- Bảng: Stage Transitions (Luật chuyển tiếp giữa các giai đoạn)
CREATE TABLE public.stage_transitions (
    transition_id SERIAL PRIMARY KEY,
    current_stage_id character varying(50) NOT NULL,
    user_intent character varying(50) NOT NULL, -- Hoặc Trigger Signal
    condition_logic text, -- Điều kiện phức tạp (tùy chọn)
    next_stage_id character varying(50),
    action_to_suggest jsonb, -- (Sửa) Lưu lệnh action dạng JSON cho điện thoại
    response_template_ref character varying(50),
    priority integer DEFAULT 0 NOT NULL
);
COMMENT ON TABLE public.stage_transitions IS 'Định nghĩa các luật chuyển đổi giữa các giai đoạn dựa trên intent hoặc trigger.';
COMMENT ON COLUMN public.stage_transitions.user_intent IS 'Ý định người dùng hoặc tín hiệu trigger để kích hoạt transition.';
COMMENT ON COLUMN public.stage_transitions.action_to_suggest IS 'Lệnh hành động JSON cụ thể gửi cho điện thoại để thực thi transition này.';
CREATE INDEX idx_stage_transitions_lookup ON public.stage_transitions(current_stage_id, user_intent);

-- Bảng: Interaction History (Lịch sử tương tác)
CREATE TABLE public.interaction_history (
    history_id SERIAL PRIMARY KEY,
    "timestamp" timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    account_id character varying(50),
    app character varying(20),
    thread_id character varying(255),
    received_text text,
    detected_user_intent character varying(50),
    sent_text text,
    status character varying(30) NOT NULL,
    strategy_id character varying(50),
    stage_id character varying(50) -- Stage trước khi thực hiện hành động
);
CREATE INDEX idx_interaction_history_thread ON public.interaction_history(thread_id, "timestamp" DESC);
CREATE INDEX idx_interaction_history_account ON public.interaction_history(account_id);
CREATE INDEX idx_interaction_history_status ON public.interaction_history(status);

-- Bảng: Suggested Rules (Đề xuất từ AI)
CREATE TABLE public.suggested_rules (
    suggestion_id SERIAL PRIMARY KEY,
    suggested_keywords text,
    suggested_template_text text,
    suggested_category character varying(50),
    suggested_template_ref character varying(50),
    source_examples jsonb,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL CHECK (status IN ('pending', 'approved', 'rejected', 'error_bulk_approve', 'duplicate', 'error_missing_data')),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);

-- Bảng: Prompt Templates
CREATE TABLE public.prompt_templates (
    prompt_template_id SERIAL PRIMARY KEY,
    name character varying(100) NOT NULL UNIQUE,
    task_type character varying(50) NOT NULL,
    template_content text NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone
);
CREATE INDEX idx_prompt_templates_task_type ON public.prompt_templates(task_type);

-- Bảng: Task State (Trạng thái tác vụ nền)
CREATE TABLE public.task_state (
    task_name character varying(100) NOT NULL PRIMARY KEY,
    last_processed_id integer DEFAULT 0,
    last_run_timestamp timestamp with time zone,
    notes text
);
COMMENT ON TABLE public.task_state IS 'Lưu ID bản ghi cuối cùng đã xử lý cho các tác vụ lặp lại.';

-- Bảng: Scheduled Jobs (Cấu hình Job cho APScheduler)
CREATE TABLE public.scheduled_jobs (
    job_id character varying(100) NOT NULL PRIMARY KEY,
    job_function_path character varying(255) NOT NULL,
    trigger_type character varying(20) NOT NULL CHECK (trigger_type IN ('interval', 'cron', 'date')),
    trigger_args jsonb NOT NULL,
    is_enabled boolean DEFAULT true NOT NULL,
    description text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone
);
COMMENT ON TABLE public.scheduled_jobs IS 'Lưu cấu hình các tác vụ nền được lên lịch.';

-- Bảng: APScheduler Jobs (Trạng thái live của APScheduler)
CREATE TABLE public.apscheduler_jobs (
    id character varying(191) NOT NULL PRIMARY KEY,
    next_run_time double precision,
    job_state bytea NOT NULL
);
CREATE INDEX ix_apscheduler_jobs_next_run_time ON public.apscheduler_jobs(next_run_time);

-- Bảng: API Keys (Quản lý Key API)
CREATE TABLE public.api_keys (
    key_id SERIAL PRIMARY KEY,
    key_name character varying(100) NOT NULL UNIQUE,
    provider character varying(50) NOT NULL DEFAULT 'google_gemini',
    api_key_value text NOT NULL, -- Giá trị key đã mã hóa
    status character varying(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'rate_limited')),
    notes text,
    last_used_at timestamp with time zone,
    rate_limited_until timestamp with time zone,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone
);
COMMENT ON TABLE public.api_keys IS 'Lưu trữ thông tin và trạng thái các API key (đã mã hóa).';
CREATE INDEX idx_api_keys_provider_status ON public.api_keys(provider, status);

-- Bảng: AI Simulation Configs (Cấu hình Mô phỏng Đã Lưu)
CREATE TABLE public.ai_simulation_configs (
    config_id SERIAL PRIMARY KEY,
    config_name character varying(100) NOT NULL UNIQUE,
    description text,
    persona_a_id character varying(50) NOT NULL,
    persona_b_id character varying(50) NOT NULL,
    log_account_id_a character varying(50) NOT NULL,
    log_account_id_b character varying(50) NOT NULL,
    strategy_id character varying(50) NOT NULL,
    max_turns integer DEFAULT 5 NOT NULL CHECK (max_turns > 0 AND max_turns <= 50),
    starting_prompt text,
    simulation_goal character varying(100) DEFAULT 'general_chat',
    is_enabled boolean DEFAULT true NOT NULL,
    api_key_id_a INTEGER NULL, -- Key ID tùy chọn cho Persona A
    api_key_id_b INTEGER NULL, -- Key ID tùy chọn cho Persona B
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone
    -- Các ràng buộc khác nếu cần
    -- CONSTRAINT check_different_personas CHECK (persona_a_id <> persona_b_id)
);
COMMENT ON TABLE public.ai_simulation_configs IS 'Lưu trữ các cấu hình định sẵn cho việc chạy mô phỏng hội thoại AI.';
-- Thêm index cho các khóa ngoại của bảng này
CREATE INDEX idx_sim_configs_pa ON public.ai_simulation_configs(persona_a_id);
CREATE INDEX idx_sim_configs_pb ON public.ai_simulation_configs(persona_b_id);
CREATE INDEX idx_sim_configs_la ON public.ai_simulation_configs(log_account_id_a);
CREATE INDEX idx_sim_configs_lb ON public.ai_simulation_configs(log_account_id_b);
CREATE INDEX idx_sim_configs_strat ON public.ai_simulation_configs(strategy_id);
CREATE INDEX idx_sim_configs_key_a ON public.ai_simulation_configs(api_key_id_a);
CREATE INDEX idx_sim_configs_key_b ON public.ai_simulation_configs(api_key_id_b);

-- Bảng: Scheduler Commands (Hàng đợi Lệnh cho Scheduler)
CREATE TABLE public.scheduler_commands (
    command_id SERIAL PRIMARY KEY,
    command_type character varying(50) NOT NULL,
    payload jsonb NOT NULL,
    status character varying(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'done', 'error', 'cancelled')),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    processed_at timestamp with time zone,
    error_message text
);
COMMENT ON TABLE public.scheduler_commands IS 'Hàng đợi lệnh bất đồng bộ yêu cầu scheduler thực hiện (vd: chạy mô phỏng, hủy job).';
CREATE INDEX idx_scheduler_commands_pending ON public.scheduler_commands (status, created_at) WHERE status = 'pending';

-- Bảng: Phone Action Log (Log tương tác với Điện thoại - **Mới**)
CREATE TABLE public.phone_action_log (
    log_id SERIAL PRIMARY KEY,
    session_id character varying(100) NOT NULL, -- ID để nhóm các hành động trong 1 phiên/chiến lược
    "timestamp" timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    received_state_json jsonb, -- Dữ liệu UI JSON từ điện thoại (AutoInput)
    analyzed_state jsonb, -- Kết quả phân tích state của AI (tùy chọn)
    goal_context text, -- Mục tiêu/ngữ cảnh lúc ra quyết định
    llm_prompt text, -- Prompt đã gửi cho LLM để quyết định hành động (tùy chọn, để debug)
    llm_action_response jsonb, -- JSON Lệnh hành động do LLM/Server quyết định
    execution_status character varying(20), -- Trạng thái thực thi từ điện thoại (vd: 'sent', 'success', 'fail_element_not_found', 'fail_other')
    execution_error text -- Chi tiết lỗi nếu thực thi thất bại
);
COMMENT ON TABLE public.phone_action_log IS 'Ghi log chi tiết quá trình tương tác AI điều khiển điện thoại.';
CREATE INDEX idx_phone_action_log_session ON public.phone_action_log(session_id, "timestamp" DESC);


-- === FOREIGN KEY CONSTRAINTS ===
-- (Thêm các FK vào cuối sau khi tất cả bảng đã được tạo)

-- Accounts
ALTER TABLE ONLY public.accounts ADD CONSTRAINT accounts_default_persona_id_fkey FOREIGN KEY (default_persona_id) REFERENCES public.ai_personas(persona_id) ON DELETE SET NULL;
ALTER TABLE ONLY public.accounts ADD CONSTRAINT accounts_default_strategy_id_fkey FOREIGN KEY (default_strategy_id) REFERENCES public.strategies(strategy_id) ON DELETE SET NULL;

-- AI Personas (FK trỏ đến templates)
ALTER TABLE ONLY public.ai_personas ADD CONSTRAINT ai_personas_fallback_template_ref_fkey FOREIGN KEY (fallback_template_ref) REFERENCES public.response_templates(template_ref) ON DELETE SET NULL;

-- Interaction History
ALTER TABLE ONLY public.interaction_history ADD CONSTRAINT interaction_history_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(account_id) ON DELETE CASCADE; -- Xóa history nếu account bị xóa? Hay SET NULL? -> CASCADE nếu history chỉ gắn với account đó.
ALTER TABLE ONLY public.interaction_history ADD CONSTRAINT interaction_history_stage_id_fkey FOREIGN KEY (stage_id) REFERENCES public.strategy_stages(stage_id) ON DELETE SET NULL;
ALTER TABLE ONLY public.interaction_history ADD CONSTRAINT interaction_history_strategy_id_fkey FOREIGN KEY (strategy_id) REFERENCES public.strategies(strategy_id) ON DELETE SET NULL;

-- Simple Rules
ALTER TABLE ONLY public.simple_rules ADD CONSTRAINT simple_rules_response_template_ref_fkey FOREIGN KEY (response_template_ref) REFERENCES public.response_templates(template_ref) ON DELETE RESTRICT; -- Ngăn xóa template nếu đang dùng trong rule

-- Strategies
ALTER TABLE ONLY public.strategies ADD CONSTRAINT fk_initial_stage FOREIGN KEY (initial_stage_id) REFERENCES public.strategy_stages(stage_id) ON DELETE SET NULL;

-- Strategy Stages
ALTER TABLE ONLY public.strategy_stages ADD CONSTRAINT strategy_stages_strategy_id_fkey FOREIGN KEY (strategy_id) REFERENCES public.strategies(strategy_id) ON DELETE CASCADE; -- Xóa stages nếu strategy bị xóa

-- Stage Transitions
ALTER TABLE ONLY public.stage_transitions ADD CONSTRAINT stage_transitions_current_stage_id_fkey FOREIGN KEY (current_stage_id) REFERENCES public.strategy_stages(stage_id) ON DELETE CASCADE; -- Xóa transition nếu stage bắt đầu bị xóa
ALTER TABLE ONLY public.stage_transitions ADD CONSTRAINT stage_transitions_next_stage_id_fkey FOREIGN KEY (next_stage_id) REFERENCES public.strategy_stages(stage_id) ON DELETE SET NULL; -- Đặt NULL nếu stage đích bị xóa
ALTER TABLE ONLY public.stage_transitions ADD CONSTRAINT stage_transitions_response_template_ref_fkey FOREIGN KEY (response_template_ref) REFERENCES public.response_templates(template_ref) ON DELETE SET NULL; -- Đặt NULL nếu template bị xóa

-- Template Variations
ALTER TABLE ONLY public.template_variations ADD CONSTRAINT template_variations_template_ref_fkey FOREIGN KEY (template_ref) REFERENCES public.response_templates(template_ref) ON DELETE CASCADE; -- Xóa variations nếu template ref bị xóa

-- AI Simulation Configs (FKs cho bảng này)
ALTER TABLE ONLY public.ai_simulation_configs ADD CONSTRAINT fk_persona_a FOREIGN KEY (persona_a_id) REFERENCES public.ai_personas(persona_id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.ai_simulation_configs ADD CONSTRAINT fk_persona_b FOREIGN KEY (persona_b_id) REFERENCES public.ai_personas(persona_id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.ai_simulation_configs ADD CONSTRAINT fk_log_account_a FOREIGN KEY (log_account_id_a) REFERENCES public.accounts(account_id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.ai_simulation_configs ADD CONSTRAINT fk_log_account_b FOREIGN KEY (log_account_id_b) REFERENCES public.accounts(account_id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.ai_simulation_configs ADD CONSTRAINT fk_strategy FOREIGN KEY (strategy_id) REFERENCES public.strategies(strategy_id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.ai_simulation_configs ADD CONSTRAINT fk_api_key_a FOREIGN KEY (api_key_id_a) REFERENCES public.api_keys(key_id) ON DELETE SET NULL;
ALTER TABLE ONLY public.ai_simulation_configs ADD CONSTRAINT fk_api_key_b FOREIGN KEY (api_key_id_b) REFERENCES public.api_keys(key_id) ON DELETE SET NULL;


-- Thêm các ràng buộc UNIQUE đã thảo luận
ALTER TABLE public.template_variations ADD CONSTRAINT template_variations_ref_text_unique UNIQUE (template_ref, variation_text);
ALTER TABLE public.simple_rules ADD CONSTRAINT simple_rules_kw_cat_ref_unique UNIQUE (trigger_keywords, category, response_template_ref);


-- PostgreSQL database dump complete
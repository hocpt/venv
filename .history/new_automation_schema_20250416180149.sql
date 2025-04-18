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

-- Bảng:
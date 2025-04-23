-- PostgreSQL Schema for HPT Automation Project
-- Version: 2025-04-23 (Final Corrected - Drop & Recreate)

-- === CẢNH BÁO: XÓA BẢNG CŨ (SẼ MẤT HẾT DỮ LIỆU!) ===
DROP TABLE IF EXISTS public.phone_action_log CASCADE;
DROP TABLE IF EXISTS public.task_assignments CASCADE;
DROP TABLE IF EXISTS public.stage_transitions CASCADE;
DROP TABLE IF EXISTS public.rules CASCADE; -- Tên bảng là 'rules'
DROP TABLE IF EXISTS public.template_variations CASCADE;
DROP TABLE IF EXISTS public.ai_simulation_configs CASCADE;
DROP TABLE IF EXISTS public.scheduled_jobs CASCADE;
DROP TABLE IF EXISTS public.scheduler_commands CASCADE;
DROP TABLE IF EXISTS public.task_state CASCADE;
DROP TABLE IF EXISTS public.suggested_rules CASCADE;
DROP TABLE IF EXISTS public.api_documentation CASCADE;
DROP TABLE IF EXISTS public.strategy_stages CASCADE;
DROP TABLE IF EXISTS public.strategies CASCADE;
DROP TABLE IF EXISTS public.templates CASCADE; -- Bảng templates gốc
DROP TABLE IF EXISTS public.prompt_templates CASCADE;
DROP TABLE IF EXISTS public.ai_personas CASCADE;
DROP TABLE IF EXISTS public.api_keys CASCADE;
DROP TABLE IF EXISTS public.device_accounts CASCADE;
DROP TABLE IF EXISTS public.accounts CASCADE;
DROP TABLE IF EXISTS public.devices CASCADE;
DROP TABLE IF EXISTS public.macro_definitions CASCADE;
-- Bảng apscheduler_jobs sẽ do APScheduler tự tạo.
-- Bảng topic_definitions chưa được định nghĩa.

RAISE NOTICE '=== Đã xóa các bảng cũ. Bắt đầu tạo schema mới... ===';

-- === TẠO LẠI CÁC BẢNG ===

-- Bảng ít phụ thuộc
CREATE TABLE public.accounts (
    account_id TEXT PRIMARY KEY, platform VARCHAR(50) NOT NULL, username TEXT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'active', notes TEXT NULL, goal TEXT NULL,
    default_strategy_id TEXT NULL, default_persona_id TEXT NULL, -- FKs added later
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NULL DEFAULT NOW()
);
COMMENT ON TABLE public.accounts IS 'Lưu tài khoản ứng dụng được quản lý.';

CREATE TABLE public.devices (
    device_id TEXT PRIMARY KEY, device_name TEXT NULL, os_info TEXT NULL,
    macrodroid_version TEXT NULL, status VARCHAR(50) NOT NULL DEFAULT 'offline',
    last_seen_at TIMESTAMPTZ NULL, registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes TEXT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NULL DEFAULT NOW()
);
COMMENT ON TABLE public.devices IS 'Lưu thiết bị vật lý (điện thoại).';

CREATE TABLE public.api_keys (
    key_id SERIAL PRIMARY KEY, key_name VARCHAR(100) UNIQUE NOT NULL, provider VARCHAR(50) NOT NULL,
    api_key_value TEXT NOT NULL, status VARCHAR(20) NOT NULL DEFAULT 'active',
    last_used_at TIMESTAMPTZ NULL, rate_limited_until TIMESTAMPTZ NULL, notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NULL DEFAULT NOW()
);
COMMENT ON TABLE public.api_keys IS 'Quản lý API key đã mã hóa.';

CREATE TABLE public.ai_personas (
    persona_id TEXT PRIMARY KEY, name VARCHAR(100) UNIQUE NOT NULL, description TEXT,
    base_prompt TEXT NOT NULL, model_name VARCHAR(100) NULL, generation_config JSONB NULL,
    fallback_template_ref TEXT NULL, notes TEXT, -- FK to templates added later
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NULL DEFAULT NOW()
);
COMMENT ON TABLE public.ai_personas IS 'Định nghĩa các vai trò/tính cách AI.';

CREATE TABLE public.macro_definitions (
    macro_code TEXT PRIMARY KEY, description TEXT NULL, app_target VARCHAR(50) NULL DEFAULT 'generic',
    params_schema JSONB NULL DEFAULT '{}', notes TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NULL DEFAULT NOW()
);
COMMENT ON TABLE public.macro_definitions IS 'Định nghĩa các hành động macro cơ bản.';

-- Bảng templates (thay cho response_templates)
CREATE TABLE public.templates (
    template_ref TEXT PRIMARY KEY, category VARCHAR(100) NULL, description TEXT,
    notes TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NULL DEFAULT NOW()
);
COMMENT ON TABLE public.templates IS 'Quản lý các mẫu trả lời (Lưu ref, category, desc).';

CREATE TABLE public.prompt_templates (
    prompt_template_id SERIAL PRIMARY KEY, name VARCHAR(100) UNIQUE NOT NULL, task_type VARCHAR(50) NOT NULL,
    description TEXT, template_content TEXT NOT NULL, notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NULL DEFAULT NOW()
);
COMMENT ON TABLE public.prompt_templates IS 'Lưu trữ các mẫu prompt tái sử dụng được.';

CREATE TABLE public.scheduled_jobs (
    job_id TEXT PRIMARY KEY, job_function_path TEXT NOT NULL, description TEXT,
    trigger_type VARCHAR(20) NOT NULL DEFAULT 'interval', trigger_args JSONB NOT NULL,
    job_args JSONB NULL DEFAULT '{}', is_enabled BOOLEAN DEFAULT true, notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NULL DEFAULT NOW()
);
COMMENT ON TABLE public.scheduled_jobs IS 'Lưu cấu hình cho các tác vụ nền được lập lịch.';

CREATE TABLE public.scheduler_commands (
    command_id SERIAL PRIMARY KEY, command_type VARCHAR(50) NOT NULL, payload JSONB NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ NULL, error_message TEXT NULL
);
COMMENT ON TABLE public.scheduler_commands IS 'Hàng đợi lệnh để kích hoạt tác vụ nền.';

CREATE TABLE public.task_state (
    task_name TEXT PRIMARY KEY, last_processed_id BIGINT NULL,
    last_run_timestamp TIMESTAMPTZ NULL, notes TEXT
);
COMMENT ON TABLE public.task_state IS 'Lưu trạng thái xử lý cuối cùng cho các tác vụ nền.';

CREATE TABLE public.suggested_rules (
    suggestion_id SERIAL PRIMARY KEY, suggested_keywords TEXT NULL, suggested_category VARCHAR(100) NULL,
    suggested_template_ref TEXT NULL, suggested_template_text TEXT NULL, source_examples JSONB NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending', notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NULL DEFAULT NOW()
);
COMMENT ON TABLE public.suggested_rules IS 'Lưu trữ các đề xuất luật/template từ AI.';

CREATE TABLE public.api_documentation (
    doc_id SERIAL PRIMARY KEY, endpoint_path TEXT UNIQUE NOT NULL, http_method VARCHAR(10) NOT NULL,
    summary TEXT NOT NULL, description TEXT NULL, request_notes TEXT NULL, request_example TEXT NULL,
    response_notes TEXT NULL, success_response_example TEXT NULL, error_response_example TEXT NULL,
    is_active BOOLEAN DEFAULT true, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NULL DEFAULT NOW()
);
COMMENT ON TABLE public.api_documentation IS 'Lưu trữ tài liệu mô tả các API endpoint cho client.';

-- Bảng có Phụ thuộc (Tạo theo thứ tự)
CREATE TABLE public.strategies (
    strategy_id TEXT PRIMARY KEY, name VARCHAR(150) NOT NULL, description TEXT,
    strategy_type VARCHAR(20) NOT NULL CHECK (strategy_type IN ('language', 'control')),
    initial_stage_id TEXT NULL, max_run_time_minutes INTEGER DEFAULT 120,
    default_wait_ms JSONB NULL DEFAULT '{"min": 800, "max": 1500}',
    error_handling VARCHAR(50) DEFAULT 'report_and_stop', is_active BOOLEAN DEFAULT true, notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NULL DEFAULT NOW()
);
COMMENT ON TABLE public.strategies IS 'Định nghĩa các chiến lược tổng thể.';

CREATE TABLE public.strategy_stages (
    strategy_id TEXT NOT NULL, stage_id TEXT NOT NULL, description TEXT, stage_order INTEGER DEFAULT 0,
    identifying_elements JSONB NULL DEFAULT '{}', notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NULL DEFAULT NOW(),
    PRIMARY KEY (strategy_id, stage_id) -- Khóa chính phức hợp
);
COMMENT ON TABLE public.strategy_stages IS 'Các giai đoạn/trạng thái trong một chiến lược.';

CREATE TABLE public.rules ( -- Bảng rules (thay cho simple_rules)
    rule_id SERIAL PRIMARY KEY, strategy_id TEXT NOT NULL, -- FK thêm sau
    trigger_keywords TEXT NOT NULL, category VARCHAR(100) NULL,
    response_template_ref TEXT NULL, -- FK thêm sau (references templates)
    priority INTEGER DEFAULT 0, notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NULL DEFAULT NOW()
);
COMMENT ON TABLE public.rules IS 'Các luật đơn giản dựa trên keywords (cho Language AI).';

CREATE TABLE public.template_variations (
    variation_id SERIAL PRIMARY KEY, template_ref TEXT NOT NULL, -- FK thêm sau (references templates)
    variation_text TEXT NOT NULL, notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NULL DEFAULT NOW(),
    UNIQUE (template_ref, variation_text)
);
COMMENT ON TABLE public.template_variations IS 'Các biến thể nội dung cho mỗi template.';

CREATE TABLE public.stage_transitions (
    transition_id SERIAL PRIMARY KEY, strategy_id TEXT NOT NULL, current_stage_id TEXT NOT NULL,
    user_intent TEXT NULL, priority INTEGER DEFAULT 0, condition_type VARCHAR(50) NULL, condition_value TEXT NULL,
    action_macro_code TEXT NULL, action_params_str TEXT NULL, response_template_ref TEXT NULL,
    next_stage_id TEXT NULL, loop_type VARCHAR(30) NULL CHECK (loop_type IS NULL OR loop_type IN ('repeat_n', 'while_condition_met', 'for_each')),
    loop_count INTEGER NULL, loop_condition_type VARCHAR(50) NULL, loop_condition_value TEXT NULL,
    loop_target_selector JSONB NULL, loop_variable_name TEXT NULL, notes TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NULL DEFAULT NOW()
);
COMMENT ON TABLE public.stage_transitions IS 'Các luật chuyển tiếp giữa các stage.';

CREATE TABLE public.device_accounts (
    device_account_id SERIAL PRIMARY KEY, device_id TEXT NOT NULL, account_id TEXT NOT NULL,
    clone_context TEXT NULL, app_package_name TEXT NULL, status VARCHAR(50) NOT NULL DEFAULT 'unknown',
    last_check_at TIMESTAMPTZ NULL, notes TEXT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NULL DEFAULT NOW(), UNIQUE (device_id, account_id, clone_context)
);
COMMENT ON TABLE public.device_accounts IS 'Liên kết Devices và Accounts, hỗ trợ clones.';

CREATE TABLE public.task_assignments (
    assignment_id SERIAL PRIMARY KEY, device_account_id INTEGER NOT NULL, strategy_id TEXT NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending', priority INTEGER NOT NULL DEFAULT 0,
    schedule_start_time TIMESTAMPTZ NULL, schedule_end_time TIMESTAMPTZ NULL,
    target_data JSONB NULL, result_data JSONB NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    assigned_at TIMESTAMPTZ NULL, started_at TIMESTAMPTZ NULL, last_report_at TIMESTAMPTZ NULL,
    completed_at TIMESTAMPTZ NULL, notes TEXT NULL
);
COMMENT ON TABLE public.task_assignments IS 'Giao nhiệm vụ (Strategy) cho một Device-Account.';

CREATE TABLE public.phone_action_log (
    log_id BIGSERIAL PRIMARY KEY, assignment_id INTEGER NULL, device_id TEXT NULL, account_id TEXT NULL,
    "timestamp" TIMESTAMPTZ NOT NULL DEFAULT NOW(), current_stage TEXT NULL, action_macro_code TEXT NULL,
    params_json JSONB NULL, execution_status VARCHAR(50) NOT NULL, execution_error TEXT NULL,
    received_state_json JSONB NULL
);
COMMENT ON TABLE public.phone_action_log IS 'Log chi tiết các hành động client thực thi.';

CREATE TABLE public.ai_simulation_configs (
    config_id SERIAL PRIMARY KEY, config_name VARCHAR(100) UNIQUE NOT NULL, description TEXT,
    persona_a_id TEXT NOT NULL, persona_b_id TEXT NOT NULL, log_account_id_a TEXT NOT NULL, log_account_id_b TEXT NOT NULL,
    strategy_id TEXT NOT NULL, max_turns INTEGER DEFAULT 10 CHECK (max_turns > 0 AND max_turns <= 50),
    starting_prompt TEXT NULL, simulation_goal TEXT NULL, is_enabled BOOLEAN DEFAULT true, notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NULL DEFAULT NOW()
);
COMMENT ON TABLE public.ai_simulation_configs IS 'Lưu cấu hình cho các lần mô phỏng AI vs AI.';

CREATE TABLE public.interaction_history (
    history_id BIGSERIAL PRIMARY KEY, account_id TEXT NULL, app TEXT NULL, thread_id TEXT NULL,
    "timestamp" TIMESTAMPTZ NOT NULL DEFAULT NOW(), received_text TEXT NULL, sent_text TEXT NULL,
    status VARCHAR(100) NULL, strategy_id TEXT NULL, stage_id TEXT NULL, detected_user_intent TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NULL DEFAULT NOW()
);
COMMENT ON TABLE public.interaction_history IS 'Log các tương tác hội thoại (Language AI).';


-- === ADD FOREIGN KEYS (CUỐI CÙNG) ===
RAISE NOTICE 'Adding Foreign Keys...';

-- FKs for accounts
ALTER TABLE public.accounts ADD CONSTRAINT accounts_default_strategy_id_fkey FOREIGN KEY (default_strategy_id) REFERENCES public.strategies(strategy_id) ON DELETE SET NULL;
ALTER TABLE public.accounts ADD CONSTRAINT accounts_default_persona_id_fkey FOREIGN KEY (default_persona_id) REFERENCES public.ai_personas(persona_id) ON DELETE SET NULL;

-- FKs for ai_personas
ALTER TABLE public.ai_personas ADD CONSTRAINT ai_personas_fallback_template_ref_fkey FOREIGN KEY (fallback_template_ref) REFERENCES public.templates(template_ref) ON DELETE SET NULL;

-- FKs for template_variations
ALTER TABLE public.template_variations ADD CONSTRAINT template_variations_template_ref_fkey FOREIGN KEY (template_ref) REFERENCES public.templates(template_ref) ON DELETE CASCADE;

-- FKs for rules
ALTER TABLE public.rules ADD CONSTRAINT rules_strategy_id_fkey FOREIGN KEY (strategy_id) REFERENCES public.strategies(strategy_id) ON DELETE CASCADE;
ALTER TABLE public.rules ADD CONSTRAINT rules_response_template_ref_fkey FOREIGN KEY (response_template_ref) REFERENCES public.templates(template_ref) ON DELETE SET NULL;

-- FKs for device_accounts
ALTER TABLE public.device_accounts ADD CONSTRAINT device_accounts_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.devices(device_id) ON DELETE CASCADE;
ALTER TABLE public.device_accounts ADD CONSTRAINT device_accounts_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(account_id) ON DELETE CASCADE;

-- FKs for strategy_stages (DEFERRABLE)
ALTER TABLE public.strategy_stages ADD CONSTRAINT strategy_stages_strategy_id_fkey FOREIGN KEY (strategy_id) REFERENCES public.strategies(strategy_id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;

-- FKs for strategies (DEFERRABLE - Composite)
ALTER TABLE public.strategies ADD CONSTRAINT fk_initial_stage FOREIGN KEY (strategy_id, initial_stage_id) REFERENCES public.strategy_stages(strategy_id, stage_id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;

-- FKs for stage_transitions (DEFERRABLE and others)
ALTER TABLE public.stage_transitions ADD CONSTRAINT stage_transitions_strategy_id_fkey FOREIGN KEY (strategy_id) REFERENCES public.strategies(strategy_id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE public.stage_transitions ADD CONSTRAINT fk_transitions_current_stage FOREIGN KEY (strategy_id, current_stage_id) REFERENCES public.strategy_stages(strategy_id, stage_id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE public.stage_transitions ADD CONSTRAINT fk_transitions_next_stage FOREIGN KEY (strategy_id, next_stage_id) REFERENCES public.strategy_stages(strategy_id, stage_id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE public.stage_transitions ADD CONSTRAINT stage_transitions_action_macro_code_fkey FOREIGN KEY (action_macro_code) REFERENCES public.macro_definitions(macro_code) ON DELETE SET NULL;
ALTER TABLE public.stage_transitions ADD CONSTRAINT stage_transitions_response_template_ref_fkey FOREIGN KEY (response_template_ref) REFERENCES public.templates(template_ref) ON DELETE SET NULL;

-- FKs for task_assignments
ALTER TABLE public.task_assignments ADD CONSTRAINT task_assignments_device_account_id_fkey FOREIGN KEY (device_account_id) REFERENCES public.device_accounts(device_account_id) ON DELETE CASCADE;
ALTER TABLE public.task_assignments ADD CONSTRAINT task_assignments_strategy_id_fkey FOREIGN KEY (strategy_id) REFERENCES public.strategies(strategy_id) ON DELETE RESTRICT;

-- FKs for phone_action_log
ALTER TABLE public.phone_action_log ADD CONSTRAINT fk_phone_action_log_assignment FOREIGN KEY (assignment_id) REFERENCES public.task_assignments(assignment_id) ON DELETE SET NULL;

-- FKs for ai_simulation_configs
ALTER TABLE public.ai_simulation_configs ADD CONSTRAINT fk_ai_simulation_configs_persona_a FOREIGN KEY (persona_a_id) REFERENCES public.ai_personas(persona_id) ON DELETE RESTRICT;
ALTER TABLE public.ai_simulation_configs ADD CONSTRAINT fk_ai_simulation_configs_persona_b FOREIGN KEY (persona_b_id) REFERENCES public.ai_personas(persona_id) ON DELETE RESTRICT;
ALTER TABLE public.ai_simulation_configs ADD CONSTRAINT fk_ai_simulation_configs_account_a FOREIGN KEY (log_account_id_a) REFERENCES public.accounts(account_id) ON DELETE CASCADE;
ALTER TABLE public.ai_simulation_configs ADD CONSTRAINT fk_ai_simulation_configs_account_b FOREIGN KEY (log_account_id_b) REFERENCES public.accounts(account_id) ON DELETE CASCADE;
ALTER TABLE public.ai_simulation_configs ADD CONSTRAINT fk_ai_simulation_configs_strategy FOREIGN KEY (strategy_id) REFERENCES public.strategies(strategy_id) ON DELETE RESTRICT;

-- FKs for interaction_history
ALTER TABLE public.interaction_history ADD CONSTRAINT interaction_history_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(account_id) ON DELETE CASCADE;
ALTER TABLE public.interaction_history ADD CONSTRAINT interaction_history_strategy_id_fkey FOREIGN KEY (strategy_id) REFERENCES public.strategies(strategy_id) ON DELETE SET NULL;


RAISE NOTICE '=== Foreign Keys added successfully. ===';

-- === INDEXES ===
RAISE NOTICE 'Adding Indexes...';
CREATE INDEX IF NOT EXISTS idx_device_accounts_device_id ON public.device_accounts(device_id);
CREATE INDEX IF NOT EXISTS idx_device_accounts_account_id ON public.device_accounts(account_id);
CREATE INDEX IF NOT EXISTS idx_task_assignments_status ON public.task_assignments(status);
CREATE INDEX IF NOT EXISTS idx_task_assignments_device_account_id ON public.task_assignments(device_account_id);
CREATE INDEX IF NOT EXISTS idx_phone_action_log_assignment_id ON public.phone_action_log(assignment_id);
CREATE INDEX IF NOT EXISTS idx_phone_action_log_timestamp ON public.phone_action_log("timestamp");
-- No index needed for (strategy_id, stage_id) on strategy_stages due to PK
-- No index needed for (strategy_id, current_stage_id) on stage_transitions due to FK
-- No index needed for (strategy_id, next_stage_id) on stage_transitions due to FK
CREATE INDEX IF NOT EXISTS idx_rules_strategy_id ON public.rules(strategy_id);
CREATE INDEX IF NOT EXISTS idx_template_variations_template_ref ON public.template_variations(template_ref);
CREATE INDEX IF NOT EXISTS idx_interaction_history_thread ON public.interaction_history(thread_id, "timestamp");
CREATE INDEX IF NOT EXISTS idx_api_documentation_method ON public.api_documentation(http_method);

RAISE NOTICE '=== Schema creation/update process completed. ===';

-- === END SCHEMA ===
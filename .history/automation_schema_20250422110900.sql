-- PostgreSQL Schema for HPT Automation Project
-- Version: 2025-04-21 (Final Corrected Version)
-- NOTES:
-- - Includes fixes for all previously reported column/constraint errors.
-- - Uses Composite Primary Key for strategy_stages.
-- - Uses DEFERRABLE Foreign Keys for circular dependencies.
-- - Assumes ON DELETE CASCADE/SET NULL appropriately based on previous discussions.

-- === WARNING: DROP EXISTING TABLES (DELETES ALL DATA IN THESE TABLES!) ===
-- Drop tables in reverse dependency order or use CASCADE
DROP TABLE IF EXISTS public.phone_action_log CASCADE;
DROP TABLE IF EXISTS public.task_assignments CASCADE;
DROP TABLE IF EXISTS public.stage_transitions CASCADE;
DROP TABLE IF EXISTS public.rules CASCADE; -- Assuming related to strategies/templates
DROP TABLE IF EXISTS public.template_variations CASCADE; -- Assuming related to templates
DROP TABLE IF EXISTS public.ai_simulation_configs CASCADE; -- Assuming related to strategies
DROP TABLE IF EXISTS public.scheduled_jobs CASCADE;
DROP TABLE IF EXISTS public.scheduler_commands CASCADE;
DROP TABLE IF EXISTS public.strategy_stages CASCADE; -- Depends on strategies
DROP TABLE IF EXISTS public.strategies CASCADE; -- Depends on accounts etc.
DROP TABLE IF EXISTS public.templates CASCADE; -- For Language AI
DROP TABLE IF EXISTS public.prompt_templates CASCADE; -- Depends on ai_personas
DROP TABLE IF EXISTS public.ai_personas CASCADE;
DROP TABLE IF EXISTS public.api_keys CASCADE;
DROP TABLE IF EXISTS public.device_accounts CASCADE; -- Depends on accounts, devices
DROP TABLE IF EXISTS public.accounts CASCADE;
DROP TABLE IF EXISTS public.devices CASCADE;
DROP TABLE IF EXISTS public.macro_definitions CASCADE;
-- Add other tables if they exist and need dropping

-- === CREATE TABLES (IN CORRECT DEPENDENCY ORDER) ===

-- Tables with few or no dependencies
CREATE TABLE IF NOT EXISTS public.accounts (
    account_id TEXT PRIMARY KEY,
    platform VARCHAR(50) NOT NULL,
    username TEXT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    notes TEXT NULL,
    goal TEXT NULL,
    default_strategy_id TEXT NULL, -- FK added later AFTER strategies table
    default_persona_id TEXT NULL, -- FK added later AFTER ai_personas table
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NULL
);
COMMENT ON TABLE public.accounts IS 'Stores managed application accounts.';

CREATE TABLE IF NOT EXISTS public.devices (
    device_id TEXT PRIMARY KEY,
    device_name TEXT NULL,
    os_info TEXT NULL,
    macrodroid_version TEXT NULL, -- Client version from device
    status VARCHAR(50) NOT NULL DEFAULT 'offline', -- online, offline, running_task, error, disabled
    last_seen_at TIMESTAMPTZ NULL,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes TEXT NULL
);
COMMENT ON TABLE public.devices IS 'Stores physical devices managed by the system.';

CREATE TABLE IF NOT EXISTS public.api_keys (
    key_id SERIAL PRIMARY KEY,
    key_name VARCHAR(100) UNIQUE NOT NULL, -- Added UNIQUE constraint
    provider VARCHAR(50) NOT NULL, -- 'google_gemini', 'openai', etc.
    api_key_value TEXT NOT NULL, -- Encrypted key value
    status VARCHAR(20) NOT NULL DEFAULT 'active', -- active, inactive, rate_limited
    last_used_at TIMESTAMPTZ NULL,
    rate_limited_until TIMESTAMPTZ NULL,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NULL
);
COMMENT ON TABLE public.api_keys IS 'Manages encrypted API keys for external services.';

CREATE TABLE IF NOT EXISTS public.ai_personas (
    persona_id TEXT PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL, -- Added UNIQUE constraint
    description TEXT,
    base_prompt TEXT NOT NULL, -- Base instructions for the AI persona
    model_name VARCHAR(100) NULL, -- Specific AI model if needed (e.g., gemini-1.5-flash)
    generation_config JSONB NULL, -- JSON containing generation parameters (temp, top_p etc.)
    fallback_template_ref TEXT NULL, -- FK added later AFTER templates table
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NULL
);
COMMENT ON TABLE public.ai_personas IS 'Defines different AI personalities/roles.';

CREATE TABLE IF NOT EXISTS public.prompt_templates (
    prompt_template_id SERIAL PRIMARY KEY, -- Changed to SERIAL PK
    name VARCHAR(100) UNIQUE NOT NULL, -- Added UNIQUE constraint
    task_type VARCHAR(50) NOT NULL, -- e.g., 'generate_reply', 'suggest_rule', 'detect_intent'
    description TEXT,
    template_content TEXT NOT NULL, -- Jinja2/F-string template content
    -- persona_id TEXT NULL REFERENCES public.ai_personas(persona_id) ON DELETE SET NULL, -- FK moved to ALTER TABLE
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NULL
);
COMMENT ON TABLE public.prompt_templates IS 'Stores reusable prompt templates.';

CREATE TABLE IF NOT EXISTS public.macro_definitions (
    macro_code TEXT PRIMARY KEY,
    description TEXT NULL,
    app_target VARCHAR(50) NULL DEFAULT 'generic',
    params_schema JSONB NULL DEFAULT '{}', -- JSON Schema for parameters
    notes TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NULL
);
COMMENT ON TABLE public.macro_definitions IS 'Definitions of reusable macro actions.';

CREATE TABLE IF NOT EXISTS public.templates ( -- For Language AI replies
    template_ref TEXT PRIMARY KEY,
    category VARCHAR(100) NULL, -- Added category
    description TEXT,            -- Added description
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NULL
);
COMMENT ON TABLE public.templates IS 'Manages response templates (references).';

CREATE TABLE IF NOT EXISTS public.scheduled_jobs ( -- For APScheduler config
    job_id TEXT PRIMARY KEY,
    job_function_path TEXT NOT NULL, -- Changed name from job_function
    description TEXT,
    trigger_type VARCHAR(20) NOT NULL DEFAULT 'interval',
    trigger_args JSONB NOT NULL,
    job_args JSONB NULL DEFAULT '{}', -- Added
    is_enabled BOOLEAN DEFAULT true,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NULL
    -- Removed job_type as function path is enough
);
COMMENT ON TABLE public.scheduled_jobs IS 'Configuration for background scheduled jobs.';

CREATE TABLE IF NOT EXISTS public.scheduler_commands ( -- For triggering jobs
    command_id SERIAL PRIMARY KEY,
    command_type VARCHAR(50) NOT NULL, -- e.g., 'run_simulation', 'run_suggestion_job_now'
    payload JSONB NULL, -- Changed from params, target_id combined
    status VARCHAR(20) NOT NULL DEFAULT 'pending', -- pending, processing, done, error
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ NULL,
    error_message TEXT NULL -- Changed from result_message
);
COMMENT ON TABLE public.scheduler_commands IS 'Queue for commands to trigger background jobs.';

CREATE TABLE IF NOT EXISTS public.task_state ( -- For background job state tracking
    task_name TEXT PRIMARY KEY,
    last_processed_id BIGINT NULL, -- Can be NULL if task tracks time
    last_run_timestamp TIMESTAMPTZ NULL,
    notes TEXT
);
COMMENT ON TABLE public.task_state IS 'Stores the last processed state for background tasks.';

CREATE TABLE IF NOT EXISTS public.suggested_rules ( -- For AI suggestions
    suggestion_id SERIAL PRIMARY KEY,
    suggested_keywords TEXT NULL,
    suggested_category VARCHAR(100) NULL, -- Added
    suggested_template_ref TEXT NULL,   -- Added
    suggested_template_text TEXT NULL,
    source_examples JSONB NULL, -- e.g., {"history_ids": [1, 5], "run_type": "...", "timestamp": "..."}
    status VARCHAR(20) NOT NULL DEFAULT 'pending', -- pending, approved, rejected, error
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NULL
);
COMMENT ON TABLE public.suggested_rules IS 'Stores suggestions generated by AI.';

CREATE TABLE IF NOT EXISTS public.interaction_history ( -- For Language AI logs
    history_id BIGSERIAL PRIMARY KEY, -- Changed from interaction_id for consistency
    account_id TEXT NULL, -- FK added later
    app TEXT NULL, -- Added app name
    thread_id TEXT NULL, -- Added thread ID
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    received_text TEXT NULL, -- Text received from user/platform
    sent_text TEXT NULL, -- Text sent by bot/AI
    status VARCHAR(100) NULL, -- Status of the processing (e.g., received, success_template, success_ai, error_...)
    strategy_id TEXT NULL, -- FK added later
    stage_id TEXT NULL, -- Stage at the time of interaction
    detected_user_intent TEXT NULL, -- Intent detected in received_text
    -- Removed less relevant fields like source, message_type, other FKs for simplicity
    -- Add them back if needed for language AI
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- Added standard timestamp
    updated_at TIMESTAMPTZ NULL -- Added standard timestamp
);
COMMENT ON TABLE public.interaction_history IS 'Log of language-based interactions.';

-- Tables with dependencies

CREATE TABLE IF NOT EXISTS public.device_accounts (
    device_account_id SERIAL PRIMARY KEY,
    device_id TEXT NOT NULL, -- FK added later
    account_id TEXT NOT NULL, -- FK added later
    clone_context TEXT NULL, -- e.g., 'main', 'dual', 'secure', 'user_10'
    app_package_name TEXT NULL, -- Package name if different from platform default
    status VARCHAR(50) NOT NULL DEFAULT 'unknown', -- Status of the account on this device (active_logged_in, login_required...)
    last_check_at TIMESTAMPTZ NULL, -- Last time status was verified/updated by client
    notes TEXT NULL,
    UNIQUE (device_id, account_id, clone_context) -- Allow same account on same device IF clone_context differs
);
COMMENT ON TABLE public.device_accounts IS 'Links devices to accounts, handling clones.';

CREATE TABLE IF NOT EXISTS public.strategies ( -- Need to create this before stages/transitions
    strategy_id TEXT PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    description TEXT,
    strategy_type VARCHAR(20) NOT NULL CHECK (strategy_type IN ('language', 'control')),
    initial_stage_id TEXT NULL, -- FK added later
    max_run_time_minutes INTEGER DEFAULT 120,
    default_wait_ms JSONB NULL DEFAULT '{"min": 800, "max": 1500}',
    error_handling VARCHAR(50) DEFAULT 'report_and_stop',
    is_active BOOLEAN DEFAULT true,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NULL
    -- Cannot add FK to strategy_stages here yet
);
COMMENT ON TABLE public.strategies IS 'Defines overall strategies (language or control).';

CREATE TABLE IF NOT EXISTS public.strategy_stages (
    strategy_id TEXT NOT NULL, -- FK added later
    stage_id TEXT NOT NULL,
    description TEXT,
    stage_order INTEGER DEFAULT 0,
    identifying_elements JSONB NULL DEFAULT '{}', -- JSON rules for stage recognition
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NULL,
    PRIMARY KEY (strategy_id, stage_id) -- COMPOSITE PRIMARY KEY
);
COMMENT ON TABLE public.strategy_stages IS 'Stages/screens within a specific strategy.';

CREATE TABLE IF NOT EXISTS public.stage_transitions (
    transition_id SERIAL PRIMARY KEY,
    strategy_id TEXT NOT NULL, -- FK added later
    current_stage_id TEXT NOT NULL, -- Part of composite FK added later
    user_intent TEXT NULL, -- Trigger signal or language intent
    priority INTEGER DEFAULT 0, -- Higher number runs first if multiple match
    condition_type VARCHAR(50) NULL, -- Condition check type
    condition_value TEXT NULL, -- Value for the condition check
    action_macro_code TEXT NULL, -- FK added later (Control)
    action_params_str TEXT NULL, -- Params for macro (Control) - Stored as TEXT
    response_template_ref TEXT NULL, -- FK added later (Language)
    next_stage_id TEXT NULL, -- Part of composite FK added later
    loop_type VARCHAR(30) NULL CHECK (loop_type IS NULL OR loop_type IN ('repeat_n', 'while_condition_met', 'for_each')),
    loop_count INTEGER NULL,
    loop_condition_type VARCHAR(50) NULL,
    loop_condition_value TEXT NULL,
    loop_target_selector JSONB NULL, -- JSONB for complex selectors
    loop_variable_name TEXT NULL,
    notes TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NULL
    -- Composite FKs added via ALTER TABLE
);
COMMENT ON TABLE public.stage_transitions IS 'Rules for moving between stages within a strategy.';

CREATE TABLE IF NOT EXISTS public.template_variations ( -- For Language AI replies
    variation_id SERIAL PRIMARY KEY,
    template_ref TEXT NOT NULL, -- FK added later
    variation_text TEXT NOT NULL,
    -- Removed less used columns like language, is_default, usage_count for simplicity
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NULL,
    UNIQUE (template_ref, variation_text) -- Prevent identical variations for same template
);
COMMENT ON TABLE public.template_variations IS 'Variations for response templates.';

CREATE TABLE IF NOT EXISTS public.rules ( -- Simple rules (maybe Language AI specific)
    rule_id SERIAL PRIMARY KEY,
    trigger_keywords TEXT NOT NULL, -- Changed from name/pattern for simplicity
    category VARCHAR(100) NULL, -- Added category
    response_template_ref TEXT NOT NULL, -- FK added later
    priority INTEGER DEFAULT 0,
    notes TEXT,
    -- Removed account_id, match_type, is_active, action_* for simplicity if focusing on basic keyword->template mapping
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NULL,
    UNIQUE (trigger_keywords, category, response_template_ref) -- Example UNIQUE constraint
);
COMMENT ON TABLE public.rules IS 'Simple keyword-based rules mapping to response templates.';


CREATE TABLE IF NOT EXISTS public.task_assignments (
    assignment_id SERIAL PRIMARY KEY,
    device_account_id INTEGER NOT NULL, -- FK added later
    strategy_id TEXT NOT NULL, -- FK added later
    status VARCHAR(50) NOT NULL DEFAULT 'pending', -- pending, assigned, running, completed, error, cancelled, paused
    priority INTEGER NOT NULL DEFAULT 0,
    schedule_start_time TIMESTAMPTZ NULL,
    schedule_end_time TIMESTAMPTZ NULL,
    target_data JSONB NULL, -- Goal details (e.g., {"target_count": 100, "current_count": 10})
    result_data JSONB NULL, -- Final result or error details
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    assigned_at TIMESTAMPTZ NULL, -- Time client picked up the task
    started_at TIMESTAMPTZ NULL, -- Time client started execution
    last_report_at TIMESTAMPTZ NULL, -- Last time client sent progress
    completed_at TIMESTAMPTZ NULL, -- Time task finished (successfully or not)
    notes TEXT NULL
);
COMMENT ON TABLE public.task_assignments IS 'Assigns specific strategies (tasks) to device-account links.';

CREATE TABLE IF NOT EXISTS public.phone_action_log (
    log_id BIGSERIAL PRIMARY KEY, -- Use BIGSERIAL for potentially large logs
    assignment_id INTEGER NULL, -- FK added later
    device_id TEXT NULL, -- Denormalized for easier querying
    account_id TEXT NULL, -- Denormalized for easier querying
    "timestamp" TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- Use quoted "timestamp"
    current_stage TEXT NULL, -- Stage when action was attempted
    action_macro_code TEXT NULL, -- Macro executed
    params_json JSONB NULL, -- Params used (JSONB)
    execution_status VARCHAR(50) NOT NULL, -- success, fail, skipped, error
    execution_error TEXT NULL, -- Error message if status is fail/error
    received_state_json JSONB NULL -- Optional: Full UI state received before action
    -- Removed strategy_id, strategy_version, session_id if less critical now
);
COMMENT ON TABLE public.phone_action_log IS 'Detailed log of actions executed by the client.';

CREATE TABLE IF NOT EXISTS public.ai_simulation_configs (
    config_id SERIAL PRIMARY KEY,
    config_name VARCHAR(100) UNIQUE NOT NULL, -- Make name unique
    description TEXT,
    persona_a_id TEXT NOT NULL, -- FK added later
    persona_b_id TEXT NOT NULL, -- FK added later
    log_account_id_a TEXT NOT NULL, -- FK added later
    log_account_id_b TEXT NOT NULL, -- FK added later
    strategy_id TEXT NOT NULL, -- FK added later
    max_turns INTEGER DEFAULT 10 CHECK (max_turns > 0 AND max_turns <= 50), -- Add sensible check
    starting_prompt TEXT NULL,
    simulation_goal TEXT NULL,
    is_enabled BOOLEAN DEFAULT true,
    -- Removed evaluation_criteria for simplicity, can add back later
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NULL
);
COMMENT ON TABLE public.ai_simulation_configs IS 'Stores saved configurations for AI vs AI simulations.';


-- === ADD FOREIGN KEYS AND INDEXES ===
-- Run these AFTER all tables are created

-- Accounts FKs
ALTER TABLE public.accounts DROP CONSTRAINT IF EXISTS accounts_default_strategy_id_fkey;
ALTER TABLE public.accounts
    ADD CONSTRAINT accounts_default_strategy_id_fkey
    FOREIGN KEY (default_strategy_id) REFERENCES public.strategies(strategy_id) ON DELETE SET NULL;

ALTER TABLE public.accounts DROP CONSTRAINT IF EXISTS accounts_default_persona_id_fkey;
ALTER TABLE public.accounts
    ADD CONSTRAINT accounts_default_persona_id_fkey
    FOREIGN KEY (default_persona_id) REFERENCES public.ai_personas(persona_id) ON DELETE SET NULL;

-- AI Personas FKs
ALTER TABLE public.ai_personas DROP CONSTRAINT IF EXISTS ai_personas_fallback_template_ref_fkey;
ALTER TABLE public.ai_personas
    ADD CONSTRAINT ai_personas_fallback_template_ref_fkey
    FOREIGN KEY (fallback_template_ref) REFERENCES public.templates(template_ref) ON DELETE SET NULL;

-- Prompt Templates FKs
ALTER TABLE public.prompt_templates DROP CONSTRAINT IF EXISTS prompt_templates_persona_id_fkey;
-- ALTER TABLE public.prompt_templates
--     ADD CONSTRAINT prompt_templates_persona_id_fkey
--     FOREIGN KEY (persona_id) REFERENCES public.ai_personas(persona_id) ON DELETE SET NULL; -- Removed for simplicity, can add back

-- Interaction History FKs
ALTER TABLE public.interaction_history DROP CONSTRAINT IF EXISTS interaction_history_account_id_fkey;
ALTER TABLE public.interaction_history
    ADD CONSTRAINT interaction_history_account_id_fkey
    FOREIGN KEY (account_id) REFERENCES public.accounts(account_id) ON DELETE CASCADE; -- Cascade delete history if account deleted

ALTER TABLE public.interaction_history DROP CONSTRAINT IF EXISTS interaction_history_strategy_id_fkey;
-- ALTER TABLE public.interaction_history
--    ADD CONSTRAINT interaction_history_strategy_id_fkey
--    FOREIGN KEY (strategy_id) REFERENCES public.strategies(strategy_id) ON DELETE SET NULL; -- Removed for simplicity

-- Device Accounts FKs
ALTER TABLE public.device_accounts DROP CONSTRAINT IF EXISTS device_accounts_device_id_fkey;
ALTER TABLE public.device_accounts
    ADD CONSTRAINT device_accounts_device_id_fkey
    FOREIGN KEY (device_id) REFERENCES public.devices(device_id) ON DELETE CASCADE;

ALTER TABLE public.device_accounts DROP CONSTRAINT IF EXISTS device_accounts_account_id_fkey;
ALTER TABLE public.device_accounts
    ADD CONSTRAINT device_accounts_account_id_fkey
    FOREIGN KEY (account_id) REFERENCES public.accounts(account_id) ON DELETE CASCADE;

-- Strategy Stages FKs
ALTER TABLE public.strategy_stages DROP CONSTRAINT IF EXISTS strategy_stages_strategy_id_fkey;
ALTER TABLE public.strategy_stages
    ADD CONSTRAINT strategy_stages_strategy_id_fkey
    FOREIGN KEY (strategy_id) REFERENCES public.strategies(strategy_id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;

-- Strategies FKs
ALTER TABLE public.strategies DROP CONSTRAINT IF EXISTS fk_initial_stage;
ALTER TABLE public.strategies
    ADD CONSTRAINT fk_initial_stage
    FOREIGN KEY (strategy_id, initial_stage_id) REFERENCES public.strategy_stages(strategy_id, stage_id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;

-- Stage Transitions FKs
ALTER TABLE public.stage_transitions DROP CONSTRAINT IF EXISTS stage_transitions_strategy_id_fkey;
ALTER TABLE public.stage_transitions
    ADD CONSTRAINT stage_transitions_strategy_id_fkey
    FOREIGN KEY (strategy_id) REFERENCES public.strategies(strategy_id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE public.stage_transitions DROP CONSTRAINT IF EXISTS fk_transitions_current_stage;
ALTER TABLE public.stage_transitions
    ADD CONSTRAINT fk_transitions_current_stage
    FOREIGN KEY (strategy_id, current_stage_id) REFERENCES public.strategy_stages(strategy_id, stage_id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE public.stage_transitions DROP CONSTRAINT IF EXISTS fk_transitions_next_stage;
ALTER TABLE public.stage_transitions
    ADD CONSTRAINT fk_transitions_next_stage
    FOREIGN KEY (strategy_id, next_stage_id) REFERENCES public.strategy_stages(strategy_id, stage_id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED; -- SET NULL if target stage deleted

ALTER TABLE public.stage_transitions DROP CONSTRAINT IF EXISTS stage_transitions_action_macro_code_fkey;
ALTER TABLE public.stage_transitions
    ADD CONSTRAINT stage_transitions_action_macro_code_fkey
    FOREIGN KEY (action_macro_code) REFERENCES public.macro_definitions(macro_code) ON DELETE SET NULL; -- SET NULL if macro deleted

ALTER TABLE public.stage_transitions DROP CONSTRAINT IF EXISTS stage_transitions_response_template_ref_fkey;
ALTER TABLE public.stage_transitions
    ADD CONSTRAINT stage_transitions_response_template_ref_fkey
    FOREIGN KEY (response_template_ref) REFERENCES public.templates(template_ref) ON DELETE SET NULL; -- SET NULL if template deleted

-- Template Variations FKs
ALTER TABLE public.template_variations DROP CONSTRAINT IF EXISTS template_variations_template_ref_fkey;
ALTER TABLE public.template_variations
    ADD CONSTRAINT template_variations_template_ref_fkey
    FOREIGN KEY (template_ref) REFERENCES public.templates(template_ref) ON DELETE CASCADE; -- Cascade delete variations if template deleted

-- Rules FKs
ALTER TABLE public.rules DROP CONSTRAINT IF EXISTS rules_response_template_ref_fkey;
ALTER TABLE public.rules
    ADD CONSTRAINT rules_response_template_ref_fkey
    FOREIGN KEY (response_template_ref) REFERENCES public.templates(template_ref) ON DELETE CASCADE; -- Cascade delete rules if template deleted

-- Task Assignments FKs
ALTER TABLE public.task_assignments DROP CONSTRAINT IF EXISTS task_assignments_device_account_id_fkey;
ALTER TABLE public.task_assignments
    ADD CONSTRAINT task_assignments_device_account_id_fkey
    FOREIGN KEY (device_account_id) REFERENCES public.device_accounts(device_account_id) ON DELETE CASCADE; -- Cascade delete assignment if link deleted

ALTER TABLE public.task_assignments DROP CONSTRAINT IF EXISTS task_assignments_strategy_id_fkey;
ALTER TABLE public.task_assignments
    ADD CONSTRAINT task_assignments_strategy_id_fkey
    FOREIGN KEY (strategy_id) REFERENCES public.strategies(strategy_id) ON DELETE RESTRICT; -- RESTRICT deletion of strategy if used in assignments

-- Phone Action Log FKs
ALTER TABLE public.phone_action_log DROP CONSTRAINT IF EXISTS fk_phone_action_log_assignment;
ALTER TABLE public.phone_action_log
    ADD CONSTRAINT fk_phone_action_log_assignment
    FOREIGN KEY (assignment_id) REFERENCES public.task_assignments(assignment_id) ON DELETE SET NULL; -- Keep logs even if assignment deleted

-- AI Simulation Configs FKs
ALTER TABLE public.ai_simulation_configs DROP CONSTRAINT IF EXISTS fk_ai_simulation_configs_persona_a;
ALTER TABLE public.ai_simulation_configs
    ADD CONSTRAINT fk_ai_simulation_configs_persona_a
    FOREIGN KEY (persona_a_id) REFERENCES public.ai_personas(persona_id) ON DELETE RESTRICT; -- Prevent deleting persona if used

ALTER TABLE public.ai_simulation_configs DROP CONSTRAINT IF EXISTS fk_ai_simulation_configs_persona_b;
ALTER TABLE public.ai_simulation_configs
    ADD CONSTRAINT fk_ai_simulation_configs_persona_b
    FOREIGN KEY (persona_b_id) REFERENCES public.ai_personas(persona_id) ON DELETE RESTRICT;

ALTER TABLE public.ai_simulation_configs DROP CONSTRAINT IF EXISTS fk_ai_simulation_configs_account_a;
ALTER TABLE public.ai_simulation_configs
    ADD CONSTRAINT fk_ai_simulation_configs_account_a
    FOREIGN KEY (log_account_id_a) REFERENCES public.accounts(account_id) ON DELETE CASCADE; -- Allow deleting account even if used in sim config? Or RESTRICT?

ALTER TABLE public.ai_simulation_configs DROP CONSTRAINT IF EXISTS fk_ai_simulation_configs_account_b;
ALTER TABLE public.ai_simulation_configs
    ADD CONSTRAINT fk_ai_simulation_configs_account_b
    FOREIGN KEY (log_account_id_b) REFERENCES public.accounts(account_id) ON DELETE CASCADE;

ALTER TABLE public.ai_simulation_configs DROP CONSTRAINT IF EXISTS fk_ai_simulation_configs_strategy;
ALTER TABLE public.ai_simulation_configs
    ADD CONSTRAINT fk_ai_simulation_configs_strategy
    FOREIGN KEY (strategy_id) REFERENCES public.strategies(strategy_id) ON DELETE RESTRICT; -- Prevent deleting strategy if used

-- === INDEXES ===
-- Add indexes for frequently queried/joined columns
CREATE INDEX IF NOT EXISTS idx_device_accounts_device_id ON public.device_accounts(device_id);
CREATE INDEX IF NOT EXISTS idx_device_accounts_account_id ON public.device_accounts(account_id);
CREATE INDEX IF NOT EXISTS idx_task_assignments_status ON public.task_assignments(status);
CREATE INDEX IF NOT EXISTS idx_task_assignments_device_account_id ON public.task_assignments(device_account_id);
CREATE INDEX IF NOT EXISTS idx_phone_action_log_assignment_id ON public.phone_action_log(assignment_id);
CREATE INDEX IF NOT EXISTS idx_phone_action_log_timestamp ON public.phone_action_log("timestamp");
CREATE INDEX IF NOT EXISTS idx_stage_transitions_strategy_current ON public.stage_transitions(strategy_id, current_stage_id);
-- No need for idx_strategy_stages_strategy because it's part of the PK
CREATE INDEX IF NOT EXISTS idx_rules_category ON public.rules(category);
CREATE INDEX IF NOT EXISTS idx_template_variations_template_ref ON public.template_variations(template_ref);
CREATE INDEX IF NOT EXISTS idx_interaction_history_account_thread ON public.interaction_history(account_id, thread_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_ai_simulation_configs_name ON public.ai_simulation_configs(config_name);

-- Add other indexes as needed based on query patterns.

-- === END SCHEMA ===
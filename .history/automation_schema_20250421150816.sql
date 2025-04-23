-- PostgreSQL Schema for HPT Automation Project
-- Version: 2025-04-21

-- Xóa bảng cũ theo đúng thứ tự phụ thuộc ngược (NẾU CẦN CHẠY LẠI TỪ ĐẦU - CẨN THẬN!)
/*
DROP INDEX IF EXISTS idx_phone_action_log_timestamp;
DROP INDEX IF EXISTS idx_phone_action_log_assignment_id;
DROP INDEX IF EXISTS idx_task_assignments_status;
DROP INDEX IF EXISTS idx_task_assignments_device_account_id;
DROP INDEX IF EXISTS idx_device_accounts_account_id;
DROP INDEX IF EXISTS idx_device_accounts_device_id;
DROP TABLE IF EXISTS public.phone_action_log;
DROP TABLE IF EXISTS public.task_assignments;
DROP TABLE IF EXISTS public.device_accounts;
DROP TABLE IF EXISTS public.devices;
DROP TABLE IF EXISTS public.stage_transitions;
DROP TABLE IF EXISTS public.macro_definitions;
DROP TABLE IF EXISTS public.strategy_stages;
DROP TABLE IF EXISTS public.template_variations;
DROP TABLE IF EXISTS public.rules;
DROP TABLE IF EXISTS public.templates;
DROP TABLE IF EXISTS public.scheduler_commands;
DROP TABLE IF EXISTS public.scheduled_jobs;
DROP TABLE IF EXISTS public.strategies;
DROP TABLE IF EXISTS public.accounts;
DROP TABLE IF EXISTS public.prompt_templates;
DROP TABLE IF EXISTS public.ai_personas;
DROP TABLE IF EXISTS public.api_keys;
*/


-- === Bảng không có hoặc ít phụ thuộc ===

-- Bảng: API Keys
CREATE TABLE IF NOT EXISTS public.api_keys (
    id SERIAL PRIMARY KEY,
    provider VARCHAR(50) NOT NULL, -- 'google', 'openai', etc.
    api_key_encrypted TEXT NOT NULL, -- Key đã được mã hóa
    is_active BOOLEAN DEFAULT true,
    last_used TIMESTAMPTZ NULL,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NULL
);
COMMENT ON TABLE public.api_keys IS 'Quản lý các API key cho các dịch vụ bên ngoài (đã mã hóa).';

-- Bảng: AI Personas
CREATE TABLE IF NOT EXISTS public.ai_personas (
    persona_id TEXT PRIMARY KEY, -- ID định danh cho persona (vd: 'neutral_assistant')
    name VARCHAR(100) NOT NULL,
    description TEXT,
    system_prompt TEXT, -- System prompt chính cho persona này
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NULL
);
COMMENT ON TABLE public.ai_personas IS 'Định nghĩa các tính cách/vai trò cho AI.';

-- Bảng: Prompt Templates
CREATE TABLE IF NOT EXISTS public.prompt_templates (
    template_id TEXT PRIMARY KEY, -- ID định danh cho prompt template (vd: 'summarize_comment')
    name VARCHAR(100) NOT NULL,
    description TEXT,
    template_content TEXT NOT NULL, -- Nội dung template với các placeholder (vd: {{user_input}})
    persona_id TEXT NULL REFERENCES public.ai_personas(persona_id) ON DELETE SET NULL, -- Persona mặc định (tùy chọn)
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NULL
);
COMMENT ON TABLE public.prompt_templates IS 'Lưu trữ các mẫu prompt tái sử dụng được.';

-- Bảng: Macro Definitions
CREATE TABLE IF NOT EXISTS public.macro_definitions (
    macro_code TEXT PRIMARY KEY, -- Mã định danh duy nhất cho macro (vd: UI_CLICK)
    description TEXT NULL, -- Mô tả chức năng
    app_target VARCHAR(50) NULL DEFAULT 'generic', -- Ứng dụng mục tiêu (system, generic, tiktok, facebook...)
    params_schema JSONB NULL DEFAULT '{}', -- JSON Schema mô tả cấu trúc tham số đầu vào
    notes TEXT NULL, -- Ghi chú thêm
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NULL
);
COMMENT ON TABLE public.macro_definitions IS 'Định nghĩa các hành động macro cơ bản, tái sử dụng được.';
COMMENT ON COLUMN public.macro_definitions.params_schema IS 'JSON Schema mô tả cấu trúc tham số mà macro này chấp nhận.';

-- Bảng: Strategies
CREATE TABLE IF NOT EXISTS public.strategies (
    strategy_id TEXT PRIMARY KEY, -- ID định danh chiến lược (vd: 'sales_reply_flow', 'tiktok_follow_control')
    name VARCHAR(150) NOT NULL,
    description TEXT,
    strategy_type VARCHAR(20) NOT NULL CHECK (strategy_type IN ('language', 'control')), -- Loại chiến lược
    initial_stage_id TEXT NULL, -- Stage bắt đầu (tham chiếu đến strategy_stages.stage_id sau)
    max_run_time_minutes INTEGER DEFAULT 120, -- Cấu hình cho control strategy
    default_wait_ms JSONB NULL DEFAULT '{"min": 800, "max": 1500}', -- Cấu hình cho control strategy
    error_handling VARCHAR(50) DEFAULT 'report_and_stop', -- Cấu hình cho control strategy
    is_active BOOLEAN DEFAULT true,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NULL
    -- FK initial_stage_id sẽ thêm sau khi strategy_stages được tạo (hoặc không cần FK cứng)
);
COMMENT ON TABLE public.strategies IS 'Định nghĩa các chiến lược tổng thể (ngôn ngữ hoặc điều khiển).';
COMMENT ON COLUMN public.strategies.strategy_type IS 'Phân loại chiến lược: language hoặc control.';
COMMENT ON COLUMN public.strategies.initial_stage_id IS 'ID của stage bắt đầu cho chiến lược này.';

-- Bảng: Accounts
CREATE TABLE IF NOT EXISTS public.accounts (
    account_id TEXT PRIMARY KEY, -- ID duy nhất cho tài khoản (vd: tiktok_userA, fb_userB)
    platform VARCHAR(50) NOT NULL, -- Nền tảng (tiktok, facebook, zalo, system...)
    username TEXT NULL, -- Tên username của tài khoản (nếu có)
    status VARCHAR(50) NOT NULL DEFAULT 'active', -- Trạng thái tài khoản (active, inactive, login_required, banned...)
    notes TEXT NULL,
    goal TEXT NULL,
    default_strategy_id TEXT NULL REFERENCES public.strategies(strategy_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NULL
);
COMMENT ON TABLE public.accounts IS 'Lưu thông tin các tài khoản ứng dụng được quản lý.';

-- Bảng: Devices
CREATE TABLE IF NOT EXISTS public.devices (
    device_id TEXT PRIMARY KEY,
    device_name TEXT NULL,
    os_info TEXT NULL,
    macrodroid_version TEXT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'offline',
    last_seen_at TIMESTAMPTZ NULL,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes TEXT NULL
);
COMMENT ON TABLE public.devices IS 'Lưu thông tin các thiết bị vật lý (điện thoại) được quản lý.';

-- Bảng: Scheduled Jobs (Cấu hình job nền - APScheduler)
CREATE TABLE IF NOT EXISTS public.scheduled_jobs (
    job_id TEXT PRIMARY KEY, -- ID duy nhất cho job config (vd: 'suggestion_job_hourly')
    job_type VARCHAR(50) NOT NULL, -- Loại job (vd: 'suggestion_generator', 'simulation_runner')
    description TEXT,
    trigger_type VARCHAR(20) NOT NULL DEFAULT 'interval', -- 'interval', 'cron', 'date'
    trigger_args JSONB NOT NULL, -- Tham số cho trigger (vd: {"minutes": 60} hoặc {"hour": 3, "minute": 0})
    job_function TEXT NOT NULL, -- Tên hàm Python sẽ chạy (vd: 'app.background_tasks.suggestion_job')
    job_args JSONB NULL DEFAULT '{}', -- Tham số cố định cho hàm job
    is_enabled BOOLEAN DEFAULT true, -- Có bật job này trong cấu hình không?
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NULL
);
COMMENT ON TABLE public.scheduled_jobs IS 'Lưu cấu hình cho các tác vụ nền được lập lịch bởi APScheduler.';
COMMENT ON COLUMN public.scheduled_jobs.trigger_args IS 'JSON chứa các tham số cho trigger (interval, cron, date).';
COMMENT ON COLUMN public.scheduled_jobs.job_args IS 'JSON chứa các tham số cố định truyền vào hàm job khi chạy.';

-- Bảng: Scheduler Commands (Hàng đợi lệnh cho scheduler)
CREATE TABLE IF NOT EXISTS public.scheduler_commands (
    command_id SERIAL PRIMARY KEY,
    command_type VARCHAR(50) NOT NULL, -- VD: 'run_simulation', 'run_suggestion_job', 'approve_all_suggestions'
    target_id TEXT NULL, -- ID liên quan (vd: simulation_config_id, job_id)
    params JSONB NULL, -- Tham số bổ sung cho lệnh
    status VARCHAR(20) NOT NULL DEFAULT 'pending', -- pending, processing, completed, error
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ NULL,
    result_message TEXT NULL
);
COMMENT ON TABLE public.scheduler_commands IS 'Hàng đợi lệnh để thực thi các tác vụ nền không đồng bộ.';


-- === Bảng có phụ thuộc cấp 1 ===

-- Bảng: Templates (Cho AI Ngôn ngữ)
CREATE TABLE IF NOT EXISTS public.templates (
    template_ref TEXT PRIMARY KEY, -- Mã định danh template (vd: 'greeting_standard', 'price_quote_v1')
    name VARCHAR(150) NOT NULL,
    description TEXT,
    account_id TEXT NULL REFERENCES public.accounts(account_id) ON DELETE SET NULL, -- Account mặc định (tùy chọn)
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NULL
);
COMMENT ON TABLE public.templates IS 'Quản lý các mẫu trả lời/hành động cơ bản.';

-- Bảng: Rules (Cho AI Ngôn ngữ)
CREATE TABLE IF NOT EXISTS public.rules (
    rule_id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    description TEXT,
    account_id TEXT NULL REFERENCES public.accounts(account_id) ON DELETE SET NULL, -- Áp dụng cho account nào (NULL là chung)
    match_pattern TEXT NOT NULL, -- Biểu thức chính quy hoặc từ khóa để khớp
    match_type VARCHAR(20) DEFAULT 'keyword', -- 'keyword', 'regex'
    priority INTEGER DEFAULT 0, -- Độ ưu tiên (cao hơn khớp trước)
    is_active BOOLEAN DEFAULT true,
    response_template_ref TEXT NULL REFERENCES public.templates(template_ref) ON DELETE SET NULL, -- Template trả lời nếu khớp rule này
    action_type VARCHAR(50) NULL, -- Hành động khác nếu cần (vd: 'assign_tag')
    action_value TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NULL
);
COMMENT ON TABLE public.rules IS 'Các luật để xử lý input dựa trên pattern.';

-- Bảng: Strategy Stages
CREATE TABLE IF NOT EXISTS public.strategy_stages (
    stage_internal_id SERIAL PRIMARY KEY, -- Khóa chính tự tăng nội bộ
    strategy_id TEXT NOT NULL REFERENCES public.strategies(strategy_id) ON DELETE CASCADE, -- Thuộc chiến lược nào
    stage_id TEXT NOT NULL, -- ID định danh stage trong chiến lược (vd: 'greeting', 'get_info')
    description TEXT,
    stage_order INTEGER DEFAULT 0, -- Thứ tự hiển thị (tùy chọn)
    identifying_elements JSONB NULL DEFAULT '{}', -- JSON chứa luật nhận diện màn hình cho Control Strategy
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NULL,
    UNIQUE (strategy_id, stage_id) -- Đảm bảo stage_id là duy nhất trong mỗi strategy
);
COMMENT ON TABLE public.strategy_stages IS 'Các giai đoạn/trạng thái/màn hình trong một chiến lược.';
COMMENT ON COLUMN public.strategy_stages.identifying_elements IS 'JSON chứa quy tắc nhận diện màn hình (dùng cho Control Strategy).';

-- Bảng: Device Accounts
CREATE TABLE IF NOT EXISTS public.device_accounts (
    device_account_id SERIAL PRIMARY KEY,
    device_id TEXT NOT NULL REFERENCES public.devices(device_id) ON DELETE CASCADE,
    account_id TEXT NOT NULL REFERENCES public.accounts(account_id) ON DELETE CASCADE,
    clone_context TEXT NULL,
    app_package_name TEXT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'unknown',
    last_check_at TIMESTAMPTZ NULL,
    notes TEXT NULL,
    UNIQUE (device_id, account_id)
);
COMMENT ON TABLE public.device_accounts IS 'Liên kết giữa thiết bị vật lý và tài khoản ứng dụng, bao gồm ngữ cảnh clone.';


-- === Bảng có phụ thuộc cấp 2 ===

-- Bảng: Template Variations (Cho AI Ngôn ngữ)
CREATE TABLE IF NOT EXISTS public.template_variations (
    variation_id SERIAL PRIMARY KEY,
    template_ref TEXT NOT NULL REFERENCES public.templates(template_ref) ON DELETE CASCADE, -- Thuộc template nào
    content TEXT NOT NULL, -- Nội dung biến thể
    language VARCHAR(10) DEFAULT 'vi',
    is_default BOOLEAN DEFAULT false,
    usage_count INTEGER DEFAULT 0,
    last_used_at TIMESTAMPTZ NULL,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NULL
);
COMMENT ON TABLE public.template_variations IS 'Các biến thể nội dung cho mỗi template.';

-- Bảng: Stage Transitions
CREATE TABLE IF NOT EXISTS public.stage_transitions (
    transition_id SERIAL PRIMARY KEY,
    strategy_id TEXT NOT NULL, -- FK sẽ thêm sau bằng ALTER
    current_stage_id TEXT NOT NULL, -- FK sẽ thêm sau bằng ALTER
    user_intent TEXT NULL, -- Ý định hoặc tín hiệu kích hoạt
    priority INTEGER DEFAULT 0, -- Độ ưu tiên xử lý
    condition_type VARCHAR(50) NULL, -- Điều kiện để transition này được kích hoạt
    condition_value TEXT NULL, -- Giá trị cho điều kiện (có thể là JSON string)
    action_macro_code TEXT NULL REFERENCES public.macro_definitions(macro_code) ON DELETE SET NULL, -- Macro thực thi (cho Control)
    action_params_str TEXT NULL, -- Chuỗi JSON chứa tham số thực tế cho macro (cho Control)
    response_template_ref TEXT NULL REFERENCES public.templates(template_ref) ON DELETE SET NULL, -- Template trả lời (cho Language)
    next_stage_id TEXT NULL, -- Stage tiếp theo sau transition (tham chiếu đến stage_id của cùng strategy_id)
    loop_type VARCHAR(30) NULL CHECK (loop_type IS NULL OR loop_type IN ('repeat_n', 'while_condition_met', 'for_each')), -- Loại vòng lặp (cho Control)
    loop_count INTEGER NULL, -- Số lần lặp cho repeat_n
    loop_condition_type VARCHAR(50) NULL, -- Điều kiện cho while_condition_met
    loop_condition_value TEXT NULL, -- Giá trị điều kiện cho while_condition_met
    loop_target_selector JSONB NULL, -- Bộ chọn element/dữ liệu để lặp for_each (Nâng cao)
    loop_variable_name TEXT NULL, -- Tên biến lưu từng item khi lặp for_each (Nâng cao)
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NULL
    -- Ràng buộc FK đến strategy_stages sẽ phức tạp vì stage_id không phải PK
    -- UNIQUE (strategy_id, current_stage_id, user_intent, priority)? Cần xem xét
);
COMMENT ON TABLE public.stage_transitions IS 'Các luật chuyển tiếp giữa các stage trong một chiến lược.';
COMMENT ON COLUMN public.stage_transitions.user_intent IS 'Ý định của người dùng (language) hoặc tín hiệu kích hoạt (control).';
COMMENT ON COLUMN public.stage_transitions.action_macro_code IS 'Tham chiếu đến macro_definitions sẽ được thực thi (Control).';
COMMENT ON COLUMN public.stage_transitions.action_params_str IS 'Chuỗi JSON chứa các tham số thực tế cho macro (Control).';
COMMENT ON COLUMN public.stage_transitions.response_template_ref IS 'Tham chiếu đến template trả lời sẽ được sử dụng (Language).';
COMMENT ON COLUMN public.stage_transitions.loop_type IS 'Loại vòng lặp áp dụng cho action (Control).';


-- Bảng: Task Assignments
CREATE TABLE IF NOT EXISTS public.task_assignments (
    assignment_id SERIAL PRIMARY KEY,
    device_account_id INTEGER NOT NULL REFERENCES public.device_accounts(device_account_id) ON DELETE CASCADE,
    strategy_id TEXT NOT NULL REFERENCES public.strategies(strategy_id) ON DELETE RESTRICT,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    priority INTEGER NOT NULL DEFAULT 0,
    schedule_start_time TIMESTAMPTZ NULL,
    schedule_end_time TIMESTAMPTZ NULL,
    target_data JSONB NULL,
    result_data JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    assigned_at TIMESTAMPTZ NULL,
    started_at TIMESTAMPTZ NULL,
    last_report_at TIMESTAMPTZ NULL,
    completed_at TIMESTAMPTZ NULL,
    notes TEXT NULL
);
COMMENT ON TABLE public.task_assignments IS 'Giao nhiệm vụ (Strategy) cụ thể cho một Tài khoản trên một Thiết bị.';


-- === Bảng Log cuối cùng ===

-- Bảng: Phone Action Log
CREATE TABLE IF NOT EXISTS public.phone_action_log (
    log_id SERIAL PRIMARY KEY,
    -- Giữ lại các cột cũ nếu cần
    session_id TEXT NULL,
    "timestamp" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    device_id TEXT NULL,
    account_id TEXT NULL,
    strategy_id TEXT NULL,
    strategy_version TEXT NULL,
    current_stage TEXT NULL,
    action_macro_code TEXT NULL,
    params_json JSONB NULL, -- Đổi tên từ action_params_json
    execution_status VARCHAR(50) NOT NULL, -- success, fail, skipped...
    execution_error TEXT NULL,
    received_state_json JSONB NULL,
    -- Thêm cột assignment_id (sẽ thêm FK sau)
    assignment_id INTEGER NULL
);
COMMENT ON TABLE public.phone_action_log IS 'Log chi tiết các hành động được thực thi bởi Client.';

-- === THÊM KHÓA NGOẠI VÀ INDEX ===

-- Thêm FK cho phone_action_log.assignment_id
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'phone_action_log' AND column_name = 'assignment_id')
       AND NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name = 'fk_phone_action_log_assignment' AND table_name = 'phone_action_log')
    THEN
        ALTER TABLE public.phone_action_log ADD CONSTRAINT fk_phone_action_log_assignment
        FOREIGN KEY (assignment_id) REFERENCES public.task_assignments(assignment_id) ON DELETE SET NULL;
        RAISE NOTICE 'FK fk_phone_action_log_assignment created.';
    END IF;
END $$;

-- Thêm các Index
CREATE INDEX IF NOT EXISTS idx_device_accounts_device_id ON public.device_accounts(device_id);
CREATE INDEX IF NOT EXISTS idx_device_accounts_account_id ON public.device_accounts(account_id);
CREATE INDEX IF NOT EXISTS idx_task_assignments_device_account_id ON public.task_assignments(device_account_id);
CREATE INDEX IF NOT EXISTS idx_task_assignments_status ON public.task_assignments(status);
CREATE INDEX IF NOT EXISTS idx_phone_action_log_assignment_id ON public.phone_action_log(assignment_id);
CREATE INDEX IF NOT EXISTS idx_phone_action_log_timestamp ON public.phone_action_log("timestamp");
CREATE INDEX IF NOT EXISTS idx_stage_transitions_strategy ON public.stage_transitions(strategy_id, current_stage_id);
CREATE INDEX IF NOT EXISTS idx_strategy_stages_strategy ON public.strategy_stages(strategy_id);
CREATE INDEX IF NOT EXISTS idx_rules_account ON public.rules(account_id);
CREATE INDEX IF NOT EXISTS idx_templates_account ON public.templates(account_id);

-- (Có thể cần thêm các FK khác cho stage_transitions nếu muốn chặt chẽ hơn, nhưng sẽ phức tạp)
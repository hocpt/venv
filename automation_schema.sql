--
-- PostgreSQL database dump
--

-- Dumped from database version 17.4
-- Dumped by pg_dump version 17.4

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: accounts; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.accounts (
    account_id text NOT NULL,
    platform character varying(50) NOT NULL,
    username text,
    status character varying(50) DEFAULT 'active'::character varying NOT NULL,
    notes text,
    goal text,
    default_strategy_id text,
    default_persona_id text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone
);


ALTER TABLE public.accounts OWNER TO postgres;

--
-- Name: TABLE accounts; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.accounts IS 'Stores managed application accounts.';


--
-- Name: ai_personas; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.ai_personas (
    persona_id text NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    base_prompt text NOT NULL,
    model_name character varying(100),
    generation_config jsonb,
    fallback_template_ref text,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone
);


ALTER TABLE public.ai_personas OWNER TO postgres;

--
-- Name: TABLE ai_personas; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.ai_personas IS 'Defines different AI personalities/roles.';


--
-- Name: ai_simulation_configs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.ai_simulation_configs (
    config_id integer NOT NULL,
    config_name character varying(100) NOT NULL,
    description text,
    persona_a_id text NOT NULL,
    persona_b_id text NOT NULL,
    log_account_id_a text NOT NULL,
    log_account_id_b text NOT NULL,
    strategy_id text NOT NULL,
    max_turns integer DEFAULT 10,
    starting_prompt text,
    simulation_goal text,
    is_enabled boolean DEFAULT true,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone,
    CONSTRAINT ai_simulation_configs_max_turns_check CHECK (((max_turns > 0) AND (max_turns <= 50)))
);


ALTER TABLE public.ai_simulation_configs OWNER TO postgres;

--
-- Name: TABLE ai_simulation_configs; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.ai_simulation_configs IS 'Stores saved configurations for AI vs AI simulations.';


--
-- Name: ai_simulation_configs_config_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.ai_simulation_configs_config_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.ai_simulation_configs_config_id_seq OWNER TO postgres;

--
-- Name: ai_simulation_configs_config_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.ai_simulation_configs_config_id_seq OWNED BY public.ai_simulation_configs.config_id;


--
-- Name: api_documentation; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.api_documentation (
    doc_id integer NOT NULL,
    endpoint_path text NOT NULL,
    http_method character varying(10) NOT NULL,
    summary text NOT NULL,
    description text,
    request_notes text,
    request_example text,
    response_notes text,
    success_response_example text,
    error_response_example text,
    notes text,
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.api_documentation OWNER TO postgres;

--
-- Name: api_documentation_doc_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.api_documentation_doc_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.api_documentation_doc_id_seq OWNER TO postgres;

--
-- Name: api_documentation_doc_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.api_documentation_doc_id_seq OWNED BY public.api_documentation.doc_id;


--
-- Name: api_keys; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.api_keys (
    key_id integer NOT NULL,
    key_name character varying(100) NOT NULL,
    provider character varying(50) NOT NULL,
    api_key_value text NOT NULL,
    status character varying(20) DEFAULT 'active'::character varying NOT NULL,
    last_used_at timestamp with time zone,
    rate_limited_until timestamp with time zone,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone
);


ALTER TABLE public.api_keys OWNER TO postgres;

--
-- Name: TABLE api_keys; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.api_keys IS 'Manages encrypted API keys for external services.';


--
-- Name: api_keys_key_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.api_keys_key_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.api_keys_key_id_seq OWNER TO postgres;

--
-- Name: api_keys_key_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.api_keys_key_id_seq OWNED BY public.api_keys.key_id;


--
-- Name: apscheduler_jobs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.apscheduler_jobs (
    id character varying(191) NOT NULL,
    next_run_time double precision,
    job_state bytea NOT NULL
);


ALTER TABLE public.apscheduler_jobs OWNER TO postgres;

--
-- Name: TABLE apscheduler_jobs; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.apscheduler_jobs IS 'Lưu trữ trạng thái các job của APScheduler khi dùng SQLAlchemyJobStore.';


--
-- Name: device_accounts; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.device_accounts (
    device_account_id integer NOT NULL,
    device_id text NOT NULL,
    account_id text NOT NULL,
    clone_context text,
    app_package_name text,
    status character varying(50) DEFAULT 'unknown'::character varying NOT NULL,
    last_check_at timestamp with time zone,
    notes text
);


ALTER TABLE public.device_accounts OWNER TO postgres;

--
-- Name: TABLE device_accounts; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.device_accounts IS 'Links devices to accounts, handling clones.';


--
-- Name: device_accounts_device_account_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.device_accounts_device_account_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.device_accounts_device_account_id_seq OWNER TO postgres;

--
-- Name: device_accounts_device_account_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.device_accounts_device_account_id_seq OWNED BY public.device_accounts.device_account_id;


--
-- Name: devices; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.devices (
    device_id text NOT NULL,
    device_name text,
    os_info text,
    macrodroid_version text,
    status character varying(50) DEFAULT 'offline'::character varying NOT NULL,
    last_seen_at timestamp with time zone,
    registered_at timestamp with time zone DEFAULT now() NOT NULL,
    notes text,
    mainloop_strategy_id text
);


ALTER TABLE public.devices OWNER TO postgres;

--
-- Name: TABLE devices; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.devices IS 'Stores physical devices managed by the system.';


--
-- Name: COLUMN devices.mainloop_strategy_id; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.devices.mainloop_strategy_id IS 'ID (Text) của chiến lược Main Loop được gán cho thiết bị này (FK đến strategies.strategy_id)';


--
-- Name: interaction_history; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.interaction_history (
    history_id integer NOT NULL,
    "timestamp" timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    account_id character varying(50),
    app character varying(20),
    thread_id character varying(255),
    action_type character varying(50),
    target_id character varying(100),
    received_text text,
    detected_user_intent character varying(50),
    sent_text text,
    status character varying(30) NOT NULL,
    strategy_id character varying(50),
    stage_id character varying(50)
);


ALTER TABLE public.interaction_history OWNER TO postgres;

--
-- Name: TABLE interaction_history; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.interaction_history IS 'Log of language-based interactions.';


--
-- Name: interaction_history_history_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.interaction_history_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.interaction_history_history_id_seq OWNER TO postgres;

--
-- Name: interaction_history_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.interaction_history_history_id_seq OWNED BY public.interaction_history.history_id;


--
-- Name: macro_definitions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.macro_definitions (
    macro_code text NOT NULL,
    description text,
    app_target character varying(50) DEFAULT 'generic'::character varying,
    params_schema jsonb DEFAULT '{}'::jsonb,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone
);


ALTER TABLE public.macro_definitions OWNER TO postgres;

--
-- Name: TABLE macro_definitions; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.macro_definitions IS 'Definitions of reusable macro actions.';


--
-- Name: phone_action_log; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.phone_action_log (
    log_id bigint NOT NULL,
    assignment_id integer,
    device_id text,
    account_id text,
    "timestamp" timestamp with time zone DEFAULT now() NOT NULL,
    current_stage text,
    action_macro_code text,
    params_json jsonb,
    execution_status character varying(50) NOT NULL,
    execution_error text,
    received_state_json jsonb
);


ALTER TABLE public.phone_action_log OWNER TO postgres;

--
-- Name: TABLE phone_action_log; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.phone_action_log IS 'Detailed log of actions executed by the client.';


--
-- Name: phone_action_log_log_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.phone_action_log_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.phone_action_log_log_id_seq OWNER TO postgres;

--
-- Name: phone_action_log_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.phone_action_log_log_id_seq OWNED BY public.phone_action_log.log_id;


--
-- Name: prompt_templates; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.prompt_templates (
    prompt_template_id integer NOT NULL,
    name character varying(100) NOT NULL,
    task_type character varying(50) NOT NULL,
    description text,
    template_content text NOT NULL,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone
);


ALTER TABLE public.prompt_templates OWNER TO postgres;

--
-- Name: TABLE prompt_templates; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.prompt_templates IS 'Stores reusable prompt templates.';


--
-- Name: prompt_templates_prompt_template_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.prompt_templates_prompt_template_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.prompt_templates_prompt_template_id_seq OWNER TO postgres;

--
-- Name: prompt_templates_prompt_template_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.prompt_templates_prompt_template_id_seq OWNED BY public.prompt_templates.prompt_template_id;


--
-- Name: rules; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.rules (
    rule_id integer NOT NULL,
    trigger_keywords text NOT NULL,
    category character varying(100),
    response_template_ref text NOT NULL,
    priority integer DEFAULT 0,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone
);


ALTER TABLE public.rules OWNER TO postgres;

--
-- Name: TABLE rules; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.rules IS 'Simple keyword-based rules mapping to response templates.';


--
-- Name: rules_rule_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.rules_rule_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.rules_rule_id_seq OWNER TO postgres;

--
-- Name: rules_rule_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.rules_rule_id_seq OWNED BY public.rules.rule_id;


--
-- Name: scheduled_jobs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.scheduled_jobs (
    job_id text NOT NULL,
    job_function_path text NOT NULL,
    description text,
    trigger_type character varying(20) DEFAULT 'interval'::character varying NOT NULL,
    trigger_args jsonb NOT NULL,
    job_args jsonb DEFAULT '{}'::jsonb,
    is_enabled boolean DEFAULT true,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone
);


ALTER TABLE public.scheduled_jobs OWNER TO postgres;

--
-- Name: TABLE scheduled_jobs; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.scheduled_jobs IS 'Configuration for background scheduled jobs.';


--
-- Name: scheduler_commands; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.scheduler_commands (
    command_id integer NOT NULL,
    command_type character varying(50) NOT NULL,
    payload jsonb,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    processed_at timestamp with time zone,
    error_message text
);


ALTER TABLE public.scheduler_commands OWNER TO postgres;

--
-- Name: TABLE scheduler_commands; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.scheduler_commands IS 'Queue for commands to trigger background jobs.';


--
-- Name: scheduler_commands_command_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.scheduler_commands_command_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.scheduler_commands_command_id_seq OWNER TO postgres;

--
-- Name: scheduler_commands_command_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.scheduler_commands_command_id_seq OWNED BY public.scheduler_commands.command_id;


--
-- Name: stage_transitions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.stage_transitions (
    transition_id integer NOT NULL,
    strategy_id text NOT NULL,
    current_stage_id text NOT NULL,
    user_intent text,
    priority integer DEFAULT 0,
    condition_type character varying(50),
    condition_value text,
    action_macro_code text,
    action_params_str text,
    response_template_ref text,
    next_stage_id text,
    loop_type character varying(30),
    loop_count integer,
    loop_condition_type character varying(50),
    loop_condition_value text,
    loop_target_selector jsonb,
    loop_variable_name text,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone,
    CONSTRAINT stage_transitions_loop_type_check CHECK (((loop_type IS NULL) OR ((loop_type)::text = ANY ((ARRAY['repeat_n'::character varying, 'while_condition_met'::character varying, 'for_each'::character varying])::text[]))))
);


ALTER TABLE public.stage_transitions OWNER TO postgres;

--
-- Name: TABLE stage_transitions; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.stage_transitions IS 'Rules for moving between stages within a strategy.';


--
-- Name: stage_transitions_transition_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.stage_transitions_transition_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.stage_transitions_transition_id_seq OWNER TO postgres;

--
-- Name: stage_transitions_transition_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.stage_transitions_transition_id_seq OWNED BY public.stage_transitions.transition_id;


--
-- Name: strategies; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.strategies (
    strategy_id text NOT NULL,
    name character varying(150) NOT NULL,
    description text,
    strategy_type character varying(20) NOT NULL,
    initial_stage_id text,
    max_run_time_minutes integer DEFAULT 120,
    default_wait_ms jsonb DEFAULT '{"max": 1500, "min": 800}'::jsonb,
    error_handling character varying(50) DEFAULT 'report_and_stop'::character varying,
    is_active boolean DEFAULT true,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone,
    CONSTRAINT strategies_strategy_type_check CHECK (((strategy_type)::text = ANY ((ARRAY['language'::character varying, 'control'::character varying, 'mainloop'::character varying])::text[])))
);


ALTER TABLE public.strategies OWNER TO postgres;

--
-- Name: TABLE strategies; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.strategies IS 'Defines overall strategies (language or control).';


--
-- Name: strategy_stages; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.strategy_stages (
    strategy_id text NOT NULL,
    stage_id text NOT NULL,
    description text,
    stage_order integer DEFAULT 0,
    identifying_elements jsonb DEFAULT '{}'::jsonb,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone
);


ALTER TABLE public.strategy_stages OWNER TO postgres;

--
-- Name: TABLE strategy_stages; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.strategy_stages IS 'Stages/screens within a specific strategy.';


--
-- Name: suggested_rules; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.suggested_rules (
    suggestion_id integer NOT NULL,
    suggested_keywords text,
    suggested_template_text text,
    source_examples jsonb,
    status character varying(20) DEFAULT 'pending'::character varying,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    suggested_category character varying(50),
    suggested_template_ref character varying(50)
);


ALTER TABLE public.suggested_rules OWNER TO postgres;

--
-- Name: TABLE suggested_rules; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.suggested_rules IS 'Stores suggestions generated by AI.';


--
-- Name: COLUMN suggested_rules.suggested_category; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.suggested_rules.suggested_category IS 'Category được AI đề xuất cho rule/template.';


--
-- Name: COLUMN suggested_rules.suggested_template_ref; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.suggested_rules.suggested_template_ref IS 'Template Ref (mã tham chiếu) được AI đề xuất.';


--
-- Name: suggested_rules_suggestion_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.suggested_rules_suggestion_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.suggested_rules_suggestion_id_seq OWNER TO postgres;

--
-- Name: suggested_rules_suggestion_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.suggested_rules_suggestion_id_seq OWNED BY public.suggested_rules.suggestion_id;


--
-- Name: task_assignments; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.task_assignments (
    assignment_id integer NOT NULL,
    device_account_id integer NOT NULL,
    strategy_id text NOT NULL,
    status character varying(50) DEFAULT 'pending'::character varying NOT NULL,
    priority integer DEFAULT 0 NOT NULL,
    schedule_start_time timestamp with time zone,
    schedule_end_time timestamp with time zone,
    target_data jsonb,
    result_data jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    assigned_at timestamp with time zone,
    started_at timestamp with time zone,
    last_report_at timestamp with time zone,
    completed_at timestamp with time zone,
    notes text
);


ALTER TABLE public.task_assignments OWNER TO postgres;

--
-- Name: TABLE task_assignments; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.task_assignments IS 'Assigns specific strategies (tasks) to device-account links.';


--
-- Name: task_assignments_assignment_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.task_assignments_assignment_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.task_assignments_assignment_id_seq OWNER TO postgres;

--
-- Name: task_assignments_assignment_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.task_assignments_assignment_id_seq OWNED BY public.task_assignments.assignment_id;


--
-- Name: task_state; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.task_state (
    task_name character varying(100) NOT NULL,
    last_processed_id integer DEFAULT 0,
    last_run_timestamp timestamp with time zone,
    notes text
);


ALTER TABLE public.task_state OWNER TO postgres;

--
-- Name: TABLE task_state; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.task_state IS 'Stores the last processed state for background tasks.';


--
-- Name: COLUMN task_state.last_processed_id; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.task_state.last_processed_id IS 'ID của bản ghi cuối cùng đã được tác vụ xử lý thành công.';


--
-- Name: template_variations; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.template_variations (
    variation_id integer NOT NULL,
    template_ref text NOT NULL,
    variation_text text NOT NULL,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone
);


ALTER TABLE public.template_variations OWNER TO postgres;

--
-- Name: TABLE template_variations; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.template_variations IS 'Variations for response templates.';


--
-- Name: template_variations_variation_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.template_variations_variation_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.template_variations_variation_id_seq OWNER TO postgres;

--
-- Name: template_variations_variation_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.template_variations_variation_id_seq OWNED BY public.template_variations.variation_id;


--
-- Name: templates; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.templates (
    template_ref text NOT NULL,
    category character varying(100),
    description text,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone
);


ALTER TABLE public.templates OWNER TO postgres;

--
-- Name: TABLE templates; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.templates IS 'Manages response templates (references).';


--
-- Name: topic_definitions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.topic_definitions (
    topic_name character varying(50) NOT NULL,
    topic_keywords text NOT NULL
);


ALTER TABLE public.topic_definitions OWNER TO postgres;

--
-- Name: ai_simulation_configs config_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ai_simulation_configs ALTER COLUMN config_id SET DEFAULT nextval('public.ai_simulation_configs_config_id_seq'::regclass);


--
-- Name: api_documentation doc_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_documentation ALTER COLUMN doc_id SET DEFAULT nextval('public.api_documentation_doc_id_seq'::regclass);


--
-- Name: api_keys key_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_keys ALTER COLUMN key_id SET DEFAULT nextval('public.api_keys_key_id_seq'::regclass);


--
-- Name: device_accounts device_account_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.device_accounts ALTER COLUMN device_account_id SET DEFAULT nextval('public.device_accounts_device_account_id_seq'::regclass);


--
-- Name: interaction_history history_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.interaction_history ALTER COLUMN history_id SET DEFAULT nextval('public.interaction_history_history_id_seq'::regclass);


--
-- Name: phone_action_log log_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.phone_action_log ALTER COLUMN log_id SET DEFAULT nextval('public.phone_action_log_log_id_seq'::regclass);


--
-- Name: prompt_templates prompt_template_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.prompt_templates ALTER COLUMN prompt_template_id SET DEFAULT nextval('public.prompt_templates_prompt_template_id_seq'::regclass);


--
-- Name: rules rule_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.rules ALTER COLUMN rule_id SET DEFAULT nextval('public.rules_rule_id_seq'::regclass);


--
-- Name: scheduler_commands command_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.scheduler_commands ALTER COLUMN command_id SET DEFAULT nextval('public.scheduler_commands_command_id_seq'::regclass);


--
-- Name: stage_transitions transition_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.stage_transitions ALTER COLUMN transition_id SET DEFAULT nextval('public.stage_transitions_transition_id_seq'::regclass);


--
-- Name: suggested_rules suggestion_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.suggested_rules ALTER COLUMN suggestion_id SET DEFAULT nextval('public.suggested_rules_suggestion_id_seq'::regclass);


--
-- Name: task_assignments assignment_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.task_assignments ALTER COLUMN assignment_id SET DEFAULT nextval('public.task_assignments_assignment_id_seq'::regclass);


--
-- Name: template_variations variation_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.template_variations ALTER COLUMN variation_id SET DEFAULT nextval('public.template_variations_variation_id_seq'::regclass);


--
-- Name: accounts accounts_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.accounts
    ADD CONSTRAINT accounts_pkey PRIMARY KEY (account_id);


--
-- Name: ai_personas ai_personas_name_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ai_personas
    ADD CONSTRAINT ai_personas_name_key UNIQUE (name);


--
-- Name: ai_personas ai_personas_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ai_personas
    ADD CONSTRAINT ai_personas_pkey PRIMARY KEY (persona_id);


--
-- Name: ai_simulation_configs ai_simulation_configs_config_name_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ai_simulation_configs
    ADD CONSTRAINT ai_simulation_configs_config_name_key UNIQUE (config_name);


--
-- Name: ai_simulation_configs ai_simulation_configs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ai_simulation_configs
    ADD CONSTRAINT ai_simulation_configs_pkey PRIMARY KEY (config_id);


--
-- Name: api_documentation api_documentation_endpoint_path_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_documentation
    ADD CONSTRAINT api_documentation_endpoint_path_key UNIQUE (endpoint_path);


--
-- Name: api_documentation api_documentation_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_documentation
    ADD CONSTRAINT api_documentation_pkey PRIMARY KEY (doc_id);


--
-- Name: api_keys api_keys_key_name_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT api_keys_key_name_key UNIQUE (key_name);


--
-- Name: api_keys api_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT api_keys_pkey PRIMARY KEY (key_id);


--
-- Name: apscheduler_jobs apscheduler_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.apscheduler_jobs
    ADD CONSTRAINT apscheduler_jobs_pkey PRIMARY KEY (id);


--
-- Name: device_accounts device_accounts_device_id_account_id_clone_context_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.device_accounts
    ADD CONSTRAINT device_accounts_device_id_account_id_clone_context_key UNIQUE (device_id, account_id, clone_context);


--
-- Name: device_accounts device_accounts_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.device_accounts
    ADD CONSTRAINT device_accounts_pkey PRIMARY KEY (device_account_id);


--
-- Name: devices devices_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.devices
    ADD CONSTRAINT devices_pkey PRIMARY KEY (device_id);


--
-- Name: interaction_history interaction_history_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.interaction_history
    ADD CONSTRAINT interaction_history_pkey PRIMARY KEY (history_id);


--
-- Name: macro_definitions macro_definitions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.macro_definitions
    ADD CONSTRAINT macro_definitions_pkey PRIMARY KEY (macro_code);


--
-- Name: phone_action_log phone_action_log_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.phone_action_log
    ADD CONSTRAINT phone_action_log_pkey PRIMARY KEY (log_id);


--
-- Name: prompt_templates prompt_templates_name_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.prompt_templates
    ADD CONSTRAINT prompt_templates_name_key UNIQUE (name);


--
-- Name: prompt_templates prompt_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.prompt_templates
    ADD CONSTRAINT prompt_templates_pkey PRIMARY KEY (prompt_template_id);


--
-- Name: rules rules_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.rules
    ADD CONSTRAINT rules_pkey PRIMARY KEY (rule_id);


--
-- Name: rules rules_trigger_keywords_category_response_template_ref_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.rules
    ADD CONSTRAINT rules_trigger_keywords_category_response_template_ref_key UNIQUE (trigger_keywords, category, response_template_ref);


--
-- Name: scheduled_jobs scheduled_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.scheduled_jobs
    ADD CONSTRAINT scheduled_jobs_pkey PRIMARY KEY (job_id);


--
-- Name: scheduler_commands scheduler_commands_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.scheduler_commands
    ADD CONSTRAINT scheduler_commands_pkey PRIMARY KEY (command_id);


--
-- Name: stage_transitions stage_transitions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.stage_transitions
    ADD CONSTRAINT stage_transitions_pkey PRIMARY KEY (transition_id);


--
-- Name: strategies strategies_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.strategies
    ADD CONSTRAINT strategies_pkey PRIMARY KEY (strategy_id);


--
-- Name: strategy_stages strategy_stages_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.strategy_stages
    ADD CONSTRAINT strategy_stages_pkey PRIMARY KEY (strategy_id, stage_id);


--
-- Name: suggested_rules suggested_rules_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.suggested_rules
    ADD CONSTRAINT suggested_rules_pkey PRIMARY KEY (suggestion_id);


--
-- Name: task_assignments task_assignments_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.task_assignments
    ADD CONSTRAINT task_assignments_pkey PRIMARY KEY (assignment_id);


--
-- Name: task_state task_state_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.task_state
    ADD CONSTRAINT task_state_pkey PRIMARY KEY (task_name);


--
-- Name: template_variations template_variations_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.template_variations
    ADD CONSTRAINT template_variations_pkey PRIMARY KEY (variation_id);


--
-- Name: template_variations template_variations_template_ref_variation_text_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.template_variations
    ADD CONSTRAINT template_variations_template_ref_variation_text_key UNIQUE (template_ref, variation_text);


--
-- Name: templates templates_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.templates
    ADD CONSTRAINT templates_pkey PRIMARY KEY (template_ref);


--
-- Name: topic_definitions topic_definitions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.topic_definitions
    ADD CONSTRAINT topic_definitions_pkey PRIMARY KEY (topic_name);


--
-- Name: idx_ai_simulation_configs_name; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_ai_simulation_configs_name ON public.ai_simulation_configs USING btree (config_name);


--
-- Name: idx_device_accounts_account_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_device_accounts_account_id ON public.device_accounts USING btree (account_id);


--
-- Name: idx_device_accounts_device_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_device_accounts_device_id ON public.device_accounts USING btree (device_id);


--
-- Name: idx_interaction_history_account; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_interaction_history_account ON public.interaction_history USING btree (account_id);


--
-- Name: idx_interaction_history_account_thread; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_interaction_history_account_thread ON public.interaction_history USING btree (account_id, thread_id, "timestamp");


--
-- Name: idx_interaction_history_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_interaction_history_status ON public.interaction_history USING btree (status);


--
-- Name: idx_interaction_history_thread; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_interaction_history_thread ON public.interaction_history USING btree (thread_id, "timestamp" DESC);


--
-- Name: idx_phone_action_log_assignment_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_phone_action_log_assignment_id ON public.phone_action_log USING btree (assignment_id);


--
-- Name: idx_phone_action_log_timestamp; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_phone_action_log_timestamp ON public.phone_action_log USING btree ("timestamp");


--
-- Name: idx_rules_category; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_rules_category ON public.rules USING btree (category);


--
-- Name: idx_stage_transitions_strategy_current; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_stage_transitions_strategy_current ON public.stage_transitions USING btree (strategy_id, current_stage_id);


--
-- Name: idx_task_assignments_device_account_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_task_assignments_device_account_id ON public.task_assignments USING btree (device_account_id);


--
-- Name: idx_task_assignments_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_task_assignments_status ON public.task_assignments USING btree (status);


--
-- Name: idx_template_variations_template_ref; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_template_variations_template_ref ON public.template_variations USING btree (template_ref);


--
-- Name: ix_apscheduler_jobs_next_run_time; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_apscheduler_jobs_next_run_time ON public.apscheduler_jobs USING btree (next_run_time);


--
-- Name: accounts accounts_default_persona_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.accounts
    ADD CONSTRAINT accounts_default_persona_id_fkey FOREIGN KEY (default_persona_id) REFERENCES public.ai_personas(persona_id) ON DELETE SET NULL;


--
-- Name: accounts accounts_default_strategy_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.accounts
    ADD CONSTRAINT accounts_default_strategy_id_fkey FOREIGN KEY (default_strategy_id) REFERENCES public.strategies(strategy_id) ON DELETE SET NULL;


--
-- Name: ai_personas ai_personas_fallback_template_ref_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ai_personas
    ADD CONSTRAINT ai_personas_fallback_template_ref_fkey FOREIGN KEY (fallback_template_ref) REFERENCES public.templates(template_ref) ON DELETE SET NULL;


--
-- Name: device_accounts device_accounts_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.device_accounts
    ADD CONSTRAINT device_accounts_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(account_id) ON DELETE CASCADE;


--
-- Name: device_accounts device_accounts_device_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.device_accounts
    ADD CONSTRAINT device_accounts_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.devices(device_id) ON DELETE CASCADE;


--
-- Name: ai_simulation_configs fk_ai_simulation_configs_account_a; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ai_simulation_configs
    ADD CONSTRAINT fk_ai_simulation_configs_account_a FOREIGN KEY (log_account_id_a) REFERENCES public.accounts(account_id) ON DELETE CASCADE;


--
-- Name: ai_simulation_configs fk_ai_simulation_configs_account_b; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ai_simulation_configs
    ADD CONSTRAINT fk_ai_simulation_configs_account_b FOREIGN KEY (log_account_id_b) REFERENCES public.accounts(account_id) ON DELETE CASCADE;


--
-- Name: ai_simulation_configs fk_ai_simulation_configs_persona_a; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ai_simulation_configs
    ADD CONSTRAINT fk_ai_simulation_configs_persona_a FOREIGN KEY (persona_a_id) REFERENCES public.ai_personas(persona_id) ON DELETE RESTRICT;


--
-- Name: ai_simulation_configs fk_ai_simulation_configs_persona_b; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ai_simulation_configs
    ADD CONSTRAINT fk_ai_simulation_configs_persona_b FOREIGN KEY (persona_b_id) REFERENCES public.ai_personas(persona_id) ON DELETE RESTRICT;


--
-- Name: ai_simulation_configs fk_ai_simulation_configs_strategy; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ai_simulation_configs
    ADD CONSTRAINT fk_ai_simulation_configs_strategy FOREIGN KEY (strategy_id) REFERENCES public.strategies(strategy_id) ON DELETE RESTRICT;


--
-- Name: devices fk_devices_mainloop_strategy; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.devices
    ADD CONSTRAINT fk_devices_mainloop_strategy FOREIGN KEY (mainloop_strategy_id) REFERENCES public.strategies(strategy_id) ON DELETE SET NULL;


--
-- Name: strategies fk_initial_stage; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.strategies
    ADD CONSTRAINT fk_initial_stage FOREIGN KEY (strategy_id, initial_stage_id) REFERENCES public.strategy_stages(strategy_id, stage_id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;


--
-- Name: phone_action_log fk_phone_action_log_assignment; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.phone_action_log
    ADD CONSTRAINT fk_phone_action_log_assignment FOREIGN KEY (assignment_id) REFERENCES public.task_assignments(assignment_id) ON DELETE SET NULL;


--
-- Name: stage_transitions fk_transitions_current_stage; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.stage_transitions
    ADD CONSTRAINT fk_transitions_current_stage FOREIGN KEY (strategy_id, current_stage_id) REFERENCES public.strategy_stages(strategy_id, stage_id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;


--
-- Name: stage_transitions fk_transitions_next_stage; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.stage_transitions
    ADD CONSTRAINT fk_transitions_next_stage FOREIGN KEY (strategy_id, next_stage_id) REFERENCES public.strategy_stages(strategy_id, stage_id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;


--
-- Name: interaction_history interaction_history_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.interaction_history
    ADD CONSTRAINT interaction_history_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(account_id) ON DELETE CASCADE;


--
-- Name: rules rules_response_template_ref_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.rules
    ADD CONSTRAINT rules_response_template_ref_fkey FOREIGN KEY (response_template_ref) REFERENCES public.templates(template_ref) ON DELETE CASCADE;


--
-- Name: stage_transitions stage_transitions_action_macro_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.stage_transitions
    ADD CONSTRAINT stage_transitions_action_macro_code_fkey FOREIGN KEY (action_macro_code) REFERENCES public.macro_definitions(macro_code) ON DELETE SET NULL;


--
-- Name: stage_transitions stage_transitions_response_template_ref_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.stage_transitions
    ADD CONSTRAINT stage_transitions_response_template_ref_fkey FOREIGN KEY (response_template_ref) REFERENCES public.templates(template_ref) ON DELETE SET NULL;


--
-- Name: stage_transitions stage_transitions_strategy_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.stage_transitions
    ADD CONSTRAINT stage_transitions_strategy_id_fkey FOREIGN KEY (strategy_id) REFERENCES public.strategies(strategy_id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;


--
-- Name: strategy_stages strategy_stages_strategy_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.strategy_stages
    ADD CONSTRAINT strategy_stages_strategy_id_fkey FOREIGN KEY (strategy_id) REFERENCES public.strategies(strategy_id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;


--
-- Name: task_assignments task_assignments_device_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.task_assignments
    ADD CONSTRAINT task_assignments_device_account_id_fkey FOREIGN KEY (device_account_id) REFERENCES public.device_accounts(device_account_id) ON DELETE CASCADE;


--
-- Name: task_assignments task_assignments_strategy_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.task_assignments
    ADD CONSTRAINT task_assignments_strategy_id_fkey FOREIGN KEY (strategy_id) REFERENCES public.strategies(strategy_id) ON DELETE RESTRICT;


--
-- Name: template_variations template_variations_template_ref_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.template_variations
    ADD CONSTRAINT template_variations_template_ref_fkey FOREIGN KEY (template_ref) REFERENCES public.templates(template_ref) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--


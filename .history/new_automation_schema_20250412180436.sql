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
    account_id character varying(50) NOT NULL,
    platform character varying(20) NOT NULL,
    username character varying(100),
    password character varying(255),
    cookie text,
    proxy character varying(100),
    status character varying(20) DEFAULT 'active'::character varying,
    goal character varying(50),
    notes text,
    default_strategy_id character varying(50),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone,
    default_persona_id character varying(50),
    CONSTRAINT accounts_status_check CHECK (((status)::text = ANY ((ARRAY['active'::character varying, 'inactive'::character varying, 'error'::character varying, 'limited'::character varying])::text[])))
);


ALTER TABLE public.accounts OWNER TO postgres;

--
-- Name: ai_personas; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.ai_personas (
    persona_id character varying(50) NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    base_prompt text NOT NULL,
    model_name character varying(100),
    generation_config jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone
);


ALTER TABLE public.ai_personas OWNER TO postgres;

--
-- Name: TABLE ai_personas; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.ai_personas IS 'Lưu trữ các cấu hình tính cách AI cơ bản (persona).';


--
-- Name: COLUMN ai_personas.base_prompt; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.ai_personas.base_prompt IS 'Prompt nền tảng định nghĩa vai trò, tính cách, hướng dẫn chung cho AI.';


--
-- Name: COLUMN ai_personas.generation_config; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.ai_personas.generation_config IS 'Lưu cấu hình sinh text của model (temperature, max_tokens...) dạng JSON.';


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
-- Name: prompt_templates; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.prompt_templates (
    prompt_template_id integer NOT NULL,
    name character varying(100) NOT NULL,
    task_type character varying(50) NOT NULL,
    template_content text NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone
);


ALTER TABLE public.prompt_templates OWNER TO postgres;

--
-- Name: TABLE prompt_templates; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.prompt_templates IS 'Lưu trữ các mẫu prompt cho các tác vụ AI khác nhau.';


--
-- Name: COLUMN prompt_templates.task_type; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.prompt_templates.task_type IS 'Phân loại mục đích của prompt (vd: generate_reply, suggest_rule).';


--
-- Name: COLUMN prompt_templates.template_content; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.prompt_templates.template_content IS 'Nội dung prompt, có thể chứa biến dạng template (vd: {{ variable }}).';


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
-- Name: response_templates; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.response_templates (
    template_ref character varying(50) NOT NULL,
    category character varying(50),
    description text
);


ALTER TABLE public.response_templates OWNER TO postgres;

--
-- Name: scheduled_jobs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.scheduled_jobs (
    job_id character varying(100) NOT NULL,
    job_function_path character varying(255) NOT NULL,
    trigger_type character varying(20) NOT NULL,
    trigger_args jsonb NOT NULL,
    is_enabled boolean DEFAULT true NOT NULL,
    description text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone
);


ALTER TABLE public.scheduled_jobs OWNER TO postgres;

--
-- Name: TABLE scheduled_jobs; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.scheduled_jobs IS 'Lưu trữ cấu hình và trạng thái của các tác vụ nền được lên lịch bởi APScheduler.';


--
-- Name: COLUMN scheduled_jobs.job_function_path; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.scheduled_jobs.job_function_path IS 'Đường dẫn Python đầy đủ tới hàm sẽ được thực thi.';


--
-- Name: COLUMN scheduled_jobs.trigger_args; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.scheduled_jobs.trigger_args IS 'Các tham số cấu hình cho trigger (interval, cron, date) dưới dạng JSON.';


--
-- Name: COLUMN scheduled_jobs.is_enabled; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.scheduled_jobs.is_enabled IS 'Trạng thái bật/tắt của job trong lần khởi động tiếp theo.';


--
-- Name: simple_rules; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.simple_rules (
    rule_id integer NOT NULL,
    trigger_keywords text NOT NULL,
    category character varying(50),
    condition_logic character varying(50) DEFAULT 'CONTAINS_ANY'::character varying,
    response_template_ref character varying(50) NOT NULL,
    priority integer DEFAULT 0,
    notes text
);


ALTER TABLE public.simple_rules OWNER TO postgres;

--
-- Name: simple_rules_rule_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.simple_rules_rule_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.simple_rules_rule_id_seq OWNER TO postgres;

--
-- Name: simple_rules_rule_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.simple_rules_rule_id_seq OWNED BY public.simple_rules.rule_id;


--
-- Name: stage_transitions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.stage_transitions (
    transition_id integer NOT NULL,
    current_stage_id character varying(50) NOT NULL,
    user_intent character varying(50) NOT NULL,
    condition_logic text,
    next_stage_id character varying(50),
    action_to_suggest character varying(100),
    response_template_ref character varying(50),
    priority integer DEFAULT 0
);


ALTER TABLE public.stage_transitions OWNER TO postgres;

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
    strategy_id character varying(50) NOT NULL,
    description text,
    initial_stage_id character varying(50),
    name character varying(100) DEFAULT 'Unnamed Strategy'::character varying NOT NULL
);


ALTER TABLE public.strategies OWNER TO postgres;

--
-- Name: strategy_stages; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.strategy_stages (
    stage_id character varying(50) NOT NULL,
    strategy_id character varying(50) NOT NULL,
    stage_order integer DEFAULT 0,
    description text
);


ALTER TABLE public.strategy_stages OWNER TO postgres;

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

COMMENT ON TABLE public.task_state IS 'Lưu trữ trạng thái của các tác vụ nền, ví dụ ID bản ghi cuối cùng đã xử lý.';


--
-- Name: COLUMN task_state.last_processed_id; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.task_state.last_processed_id IS 'ID của bản ghi cuối cùng đã được tác vụ xử lý thành công.';


--
-- Name: template_variations; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.template_variations (
    variation_id integer NOT NULL,
    template_ref character varying(50) NOT NULL,
    variation_text text NOT NULL
);


ALTER TABLE public.template_variations OWNER TO postgres;

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
-- Name: topic_definitions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.topic_definitions (
    topic_name character varying(50) NOT NULL,
    topic_keywords text NOT NULL
);


ALTER TABLE public.topic_definitions OWNER TO postgres;

--
-- Name: interaction_history history_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.interaction_history ALTER COLUMN history_id SET DEFAULT nextval('public.interaction_history_history_id_seq'::regclass);


--
-- Name: prompt_templates prompt_template_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.prompt_templates ALTER COLUMN prompt_template_id SET DEFAULT nextval('public.prompt_templates_prompt_template_id_seq'::regclass);


--
-- Name: simple_rules rule_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.simple_rules ALTER COLUMN rule_id SET DEFAULT nextval('public.simple_rules_rule_id_seq'::regclass);


--
-- Name: stage_transitions transition_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.stage_transitions ALTER COLUMN transition_id SET DEFAULT nextval('public.stage_transitions_transition_id_seq'::regclass);


--
-- Name: suggested_rules suggestion_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.suggested_rules ALTER COLUMN suggestion_id SET DEFAULT nextval('public.suggested_rules_suggestion_id_seq'::regclass);


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
-- Name: ai_personas ai_personas_name_unique; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ai_personas
    ADD CONSTRAINT ai_personas_name_unique UNIQUE (name);


--
-- Name: ai_personas ai_personas_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ai_personas
    ADD CONSTRAINT ai_personas_pkey PRIMARY KEY (persona_id);


--
-- Name: apscheduler_jobs apscheduler_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.apscheduler_jobs
    ADD CONSTRAINT apscheduler_jobs_pkey PRIMARY KEY (id);


--
-- Name: interaction_history interaction_history_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.interaction_history
    ADD CONSTRAINT interaction_history_pkey PRIMARY KEY (history_id);


--
-- Name: prompt_templates prompt_templates_name_unique; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.prompt_templates
    ADD CONSTRAINT prompt_templates_name_unique UNIQUE (name);


--
-- Name: prompt_templates prompt_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.prompt_templates
    ADD CONSTRAINT prompt_templates_pkey PRIMARY KEY (prompt_template_id);


--
-- Name: response_templates response_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.response_templates
    ADD CONSTRAINT response_templates_pkey PRIMARY KEY (template_ref);


--
-- Name: scheduled_jobs scheduled_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.scheduled_jobs
    ADD CONSTRAINT scheduled_jobs_pkey PRIMARY KEY (job_id);


--
-- Name: simple_rules simple_rules_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.simple_rules
    ADD CONSTRAINT simple_rules_pkey PRIMARY KEY (rule_id);


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
    ADD CONSTRAINT strategy_stages_pkey PRIMARY KEY (stage_id);


--
-- Name: suggested_rules suggested_rules_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.suggested_rules
    ADD CONSTRAINT suggested_rules_pkey PRIMARY KEY (suggestion_id);


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
-- Name: topic_definitions topic_definitions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.topic_definitions
    ADD CONSTRAINT topic_definitions_pkey PRIMARY KEY (topic_name);


--
-- Name: idx_interaction_history_account; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_interaction_history_account ON public.interaction_history USING btree (account_id);


--
-- Name: idx_interaction_history_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_interaction_history_status ON public.interaction_history USING btree (status);


--
-- Name: idx_interaction_history_thread; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_interaction_history_thread ON public.interaction_history USING btree (thread_id, "timestamp" DESC);


--
-- Name: idx_prompt_templates_task_type; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_prompt_templates_task_type ON public.prompt_templates USING btree (task_type);


--
-- Name: idx_simple_rules_category; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_simple_rules_category ON public.simple_rules USING btree (category);


--
-- Name: idx_stage_transitions_lookup; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_stage_transitions_lookup ON public.stage_transitions USING btree (current_stage_id, user_intent);


--
-- Name: idx_template_variations_ref; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_template_variations_ref ON public.template_variations USING btree (template_ref);


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
-- Name: strategies fk_initial_stage; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.strategies
    ADD CONSTRAINT fk_initial_stage FOREIGN KEY (initial_stage_id) REFERENCES public.strategy_stages(stage_id) ON DELETE SET NULL;


--
-- Name: interaction_history interaction_history_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.interaction_history
    ADD CONSTRAINT interaction_history_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(account_id);


--
-- Name: simple_rules simple_rules_response_template_ref_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.simple_rules
    ADD CONSTRAINT simple_rules_response_template_ref_fkey FOREIGN KEY (response_template_ref) REFERENCES public.response_templates(template_ref);


--
-- Name: stage_transitions stage_transitions_current_stage_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.stage_transitions
    ADD CONSTRAINT stage_transitions_current_stage_id_fkey FOREIGN KEY (current_stage_id) REFERENCES public.strategy_stages(stage_id) ON DELETE CASCADE;


--
-- Name: stage_transitions stage_transitions_next_stage_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.stage_transitions
    ADD CONSTRAINT stage_transitions_next_stage_id_fkey FOREIGN KEY (next_stage_id) REFERENCES public.strategy_stages(stage_id) ON DELETE SET NULL;


--
-- Name: stage_transitions stage_transitions_response_template_ref_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.stage_transitions
    ADD CONSTRAINT stage_transitions_response_template_ref_fkey FOREIGN KEY (response_template_ref) REFERENCES public.response_templates(template_ref);


--
-- Name: strategy_stages strategy_stages_strategy_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.strategy_stages
    ADD CONSTRAINT strategy_stages_strategy_id_fkey FOREIGN KEY (strategy_id) REFERENCES public.strategies(strategy_id) ON DELETE CASCADE;


--
-- Name: template_variations template_variations_template_ref_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.template_variations
    ADD CONSTRAINT template_variations_template_ref_fkey FOREIGN KEY (template_ref) REFERENCES public.response_templates(template_ref) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--


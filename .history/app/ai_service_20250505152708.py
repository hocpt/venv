# app/ai_service.py (Phiên bản đầy đủ cuối cùng)
import os
import google.generativeai as genai
# from flask import current_app # Không dùng current_app nữa để linh hoạt hơn
import re
import traceback
import random
from datetime import datetime, timezone, timedelta
import pytz
import time
from google.api_core import exceptions as api_core_exceptions
import json
from flask import current_app
from jinja2 import Environment, Template
from . import database
# --- Import Database Module ---
try:
    from . import database as db
    # Kiểm tra xem các hàm cần thiết đã có trong db chưa
    if not all([hasattr(db, 'get_active_api_keys_by_provider'),
                hasattr(db, 'update_key_last_used'),
                hasattr(db, 'set_key_rate_limit_expiry'),
                hasattr(db, 'get_persona_details'),
                hasattr(db, 'get_prompt_template_by_task'),
                hasattr(db, 'get_template_variations')]):
        print("CRITICAL ERROR (ai_service): Database module is missing required functions.")
        db = None
    else:
        print("DEBUG (ai_service): Database module imported successfully.")
except ImportError:
    print("CRITICAL ERROR (ai_service): Cannot import database module.")
    db = None

# --- Import Cryptography for Encryption ---
try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:
    print("CRITICAL ERROR (ai_service): cryptography library not installed. API Key decryption will fail.")
    print("Please run: pip install cryptography")
    Fernet = None # Đặt là None để code kiểm tra sau này

# --- Constants for Retry Logic ---
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 5
BACKOFF_FACTOR = 2
MAX_JITTER_SECONDS = 1.5
MAX_RETRY_DELAY_SECONDS = 60.0

# --- DANH SÁCH INTENT ĐÃ ĐỊNH NGHĨA ---
# Nên đồng bộ với DB hoặc config
VALID_INTENTS = [
    'greeting', 'price_query', 'shipping_query', 'product_info_query',
    'compliment', 'complaint', 'connection_request', 'spam',
    'positive_generic', 'negative_generic', 'other', 'unknown', 'error',
    'start', 'simulated_turn', 'fallback', 'clarification', 'confirmation' # Bổ sung
]
DISABLED_KEYS = {}
DISABLE_DURATION = timedelta(minutes=5) 
# --- Encryption Helper ---
__fernet_instance = None
def _get_fernet() -> Fernet | None:
    """Lấy hoặc khởi tạo Fernet instance."""
    global __fernet_instance
    if __fernet_instance: return __fernet_instance
    if not Fernet: return None # Không thể tạo nếu import lỗi

    encryption_key = os.environ.get('API_ENCRYPTION_KEY')
    if not encryption_key:
        print("CRITICAL ERROR (ai_service): API_ENCRYPTION_KEY not set!")
        return None
    try:
        key_bytes = encryption_key.encode('utf-8')
        __fernet_instance = Fernet(key_bytes)
        print("DEBUG (ai_service): Fernet instance initialized.")
        return __fernet_instance
    except Exception as e:
        print(f"CRITICAL ERROR (ai_service): Failed to initialize Fernet: {e}")
        return None

# --- Helper Function: Parse Generation Config ---
def _parse_generation_config(config_str_or_dict) -> genai.types.GenerationConfig | None:
    """ Chuyển đổi chuỗi JSON hoặc dict thành GenerationConfig object. """
    if not config_str_or_dict: return None
    config_dict = None
    if isinstance(config_str_or_dict, str):
        try: config_dict = json.loads(config_str_or_dict)
        except json.JSONDecodeError: return None
    elif isinstance(config_str_or_dict, dict): config_dict = config_str_or_dict
    else: return None
    if config_dict and isinstance(config_dict, dict):
        try:
            # Các tham số hợp lệ cho GenerationConfig của Gemini
            valid_keys = {'temperature', 'top_p', 'top_k', 'candidate_count', 'max_output_tokens', 'stop_sequences'}
            valid_args = {k: v for k, v in config_dict.items() if k in valid_keys}
            if valid_args: return genai.types.GenerationConfig(**valid_args)
            else: return None
        except Exception as e: print(f"WARN: Error creating GenConfig from dict: {e}"); return None
    return None
VALID_CLASSIFICATIONS = [
    'unclassified',      # Chưa phân loại
    'non_interactive',   # Không tương tác (vd: TextView tĩnh, ImageView trang trí)
    'navigation',        # Điều hướng (vd: Tab, nút Back, Menu Item)
    'primary_action',    # Hành động chính (vd: Nút Login, Post, Save, Next)
    'secondary_action',  # Hành động phụ (vd: Link 'Forgot Password', nút 'Cancel')
    'input_field',       # Trường nhập liệu (vd: EditText, TextField)
    'strategy_critical', # Quan trọng đặc biệt cho chiến lược cụ thể (đánh dấu thủ công)
    'ignore'             # Bỏ qua hoàn toàn (vd: Quảng cáo, element không liên quan)
]
# --- Helper Function: Get Timezone ---
def _get_configured_timezone():
    try: return pytz.timezone('Asia/Ho_Chi_Minh') # Hoặc đọc từ config nếu có
    except: return pytz.utc

# --- === HÀM HELPER MỚI: LẤY VÀ CẤU HÌNH KEY XOAY VÒNG === ---
__current_configured_key_id = None
__last_configure_time = None
def _get_active_key_and_configure(provider: str = 'gemini') -> int | None:
    """Lấy API key active, chưa bị rate limit, cấu hình genai và trả về key_id."""
    global __current_configured_key_id, __last_configure_time
    if not db: print("ERROR (get_active_key): DB module not available."); return None
    if not Fernet: print("ERROR (get_active_key): Cryptography module not available."); return None

    print(f"DEBUG (get_active_key): Finding active key for '{provider}'...")
    try:
        active_keys = db.get_active_api_keys_by_provider(provider) # Hàm này cần trả về cả decrypted_value
        if not active_keys:
            print(f"ERROR (get_active_key): No active/usable keys found for '{provider}'.")
            return None

        # Chọn key đầu tiên (ưu tiên key dùng lâu nhất/chưa dùng)
        selected_key = active_keys[0]
        selected_key_id = selected_key['key_id']
        # Hàm get_active_api_keys_by_provider phải đảm bảo trả về 'decrypted_value'
        selected_key_value = selected_key.get('decrypted_value')

        if not selected_key_value:
             print(f"ERROR (get_active_key): Key ID {selected_key_id} missing decrypted value.")
             return None

        # Cấu hình genai (chỉ khi cần)
        now = time.time()
        if selected_key_id != __current_configured_key_id or __last_configure_time is None or (now - __last_configure_time > 60):
            try:
                print(f"DEBUG (get_active_key): Configuring genai with Key ID: {selected_key_id}...")
                genai.configure(api_key=selected_key_value)
                __current_configured_key_id = selected_key_id
                __last_configure_time = now
                print(f"INFO (get_active_key): Configured API Key ID: {selected_key_id}")
            except Exception as config_err:
                print(f"ERROR (get_active_key): Failed configure Key ID {selected_key_id}: {config_err}")
                return None
        # else: print(f"DEBUG (get_active_key): Reusing configured Key ID: {selected_key_id}")

        # Cập nhật last_used_at
        db.update_key_last_used(selected_key_id)
        return selected_key_id

    except Exception as e:
        print(f"ERROR (get_active_key): Unexpected error: {e}")
        # print(traceback.format_exc()) # Bỏ comment nếu cần debug sâu
        return None

# === HÀM GỌI API GEMINI TỔNG QUÁT (DÙNG KEY XOAY VÒNG VÀ RETRY) ===
def call_generative_model(prompt: str, persona_id: str | None = None) -> tuple[str | None, str]:
    """Hàm gọi API Gemini tổng quát với retry logic và sử dụng key xoay vòng."""
    print(f"DEBUG (call_generative_model): Start Call. Persona='{persona_id or 'Default'}', Prompt='{prompt[:100]}...'")
    response_text = None
    status = "error_unknown"
    key_id_used_for_this_call = None # Key dùng cho lần gọi thành công cuối cùng (nếu có)

    if not prompt: return None, "error_input_prompt_empty"
    if not db: return None, "error_db_module_missing"
    if not Fernet: return None, "error_cryptography_missing"

    # --- Lấy cấu hình Model và Generation Config ---
    # (Nên lấy thông tin này từ config chung hoặc persona)
    model_name = 'models/gemini-1.5-flash-latest' # Giá trị mặc định
    generation_config = genai.types.GenerationConfig(temperature=0.7, max_output_tokens=1000) # Mặc định
    if persona_id:
        try:
            persona = db.get_persona_details(persona_id)
            if persona:
                model_name = persona.get('model_name') or model_name
                persona_gen_config_obj = _parse_generation_config(persona.get('generation_config'))
                if persona_gen_config_obj: generation_config = persona_gen_config_obj
        except Exception as db_err: print(f"WARN getting persona config {persona_id}: {db_err}")
    print(f"DEBUG (call_generative_model): Using model: {model_name}")

    # --- Vòng lặp gọi API với Retry ---
    last_exception = None
    for attempt in range(MAX_RETRIES + 1):
        key_id_used_for_this_attempt = None
        try:
            # --- LẤY VÀ CẤU HÌNH KEY TRƯỚC MỖI LẦN THỬ ---
            key_id_used_for_this_attempt = _get_active_key_and_configure('gemini')
            if not key_id_used_for_this_attempt:
                status = "error_ai_no_active_key"
                print(f"ERROR ({status}): Không có API key khả dụng.")
                # Nếu không có key nào, không cần thử lại nữa
                # Set response_text thành thông báo lỗi
                response_text = "No active API keys available."
                break # Thoát vòng lặp retry

            # Lưu lại key ID dùng cho lần thử này, phòng trường hợp thành công
            key_id_used_for_this_call = key_id_used_for_this_attempt

            model = genai.GenerativeModel(model_name)
            print(f"DEBUG (call_generative_model): Attempt {attempt + 1}/{MAX_RETRIES + 1} using KeyID {key_id_used_for_this_call}...")
            response = model.generate_content(prompt, generation_config=generation_config)

            # --- Xử lý Response thành công ---
            response_text, status = None, "error_unknown" # Reset
            if response.parts:
                try:
                    response_text = response.text.strip(); status = 'success' if response_text else 'error_ai_empty'
                except Exception as e_text: status = "error_ai_text_access"; print(f"ERROR access text: {e_text}")
            elif hasattr(response, 'prompt_feedback') and response.prompt_feedback.block_reason:
                status = "error_ai_blocked"; response_text = f"Blocked: {response.prompt_feedback.block_reason}"; print(f"WARN: Blocked.")
                break # Thoát retry nếu bị chặn
            else:
                status = "error_ai_invalid_response"; print(f"WARN: Invalid response structure.")
                break # Thoát retry nếu response lạ

            # Thoát nếu thành công hoặc gặp lỗi không retry
            if status == 'success' or status == 'error_ai_empty' or status == 'error_ai_blocked' or status == 'error_ai_invalid_response':
                print(f"DEBUG (call_generative_model): Attempt {attempt + 1} Result Status: {status}")
                break

        # --- Xử lý lỗi có thể Retry (429) ---
        except api_core_exceptions.ResourceExhausted as e:
            last_exception = e
            print(f"WARN (call_generative_model): Attempt {attempt + 1} with KeyID {key_id_used_for_this_attempt} failed: Resource Exhausted (429).")
            if attempt >= MAX_RETRIES:
                status = "error_ai_rate_limited"; response_text = f"API rate limit hit after {MAX_RETRIES + 1} attempts."
                # Đánh dấu key bị rate limit
                if key_id_used_for_this_attempt:
                     suggested_delay_seconds = 60 # Mặc định
                     try: # Thử lấy delay gợi ý từ lỗi
                          delay_match = re.search(r'seconds:\s*(\d+)', str(e))
                          if delay_match: suggested_delay_seconds = int(delay_match.group(1)) + random.randint(5, 10) # Thêm buffer
                     except: pass
                     expiry_time = datetime.now(timezone.utc) + timedelta(seconds=suggested_delay_seconds)
                     db.set_key_rate_limit_expiry(key_id_used_for_this_attempt, expiry_time)
                     print(f"INFO: Marked KeyID {key_id_used_for_this_attempt} as rate limited until {expiry_time.isoformat()}")
                break

            # Tính toán thời gian chờ (như cũ)
            delay = INITIAL_BACKOFF_SECONDS * (BACKOFF_FACTOR ** attempt) + random.uniform(0, MAX_JITTER_SECONDS)
            # ... (code lấy suggested_delay từ lỗi như cũ) ...
            suggested_delay = None
            try: delay_match = re.search(r'seconds:\s*(\d+)', str(e)); suggested_delay = float(delay_match.group(1)) if delay_match else None
            except: pass
            if suggested_delay and suggested_delay > 0: delay = suggested_delay + random.uniform(0, MAX_JITTER_SECONDS)
            delay = min(delay, MAX_RETRY_DELAY_SECONDS)
            print(f"INFO (call_generative_model): Retrying in {delay:.2f} seconds...")
            time.sleep(delay)
            # continue vòng lặp

        # --- Xử lý các lỗi không mong muốn khác ---
        except Exception as e:
            print(f"ERROR (call_generative_model): Attempt {attempt + 1} failed: {type(e).__name__} - {e}")
            last_exception = e; status = "error_ai_exception"; response_text = f"Unexpected error: {e}"
            break # Thoát vòng lặp

    # --- Kết thúc vòng lặp retry ---
    print(f"INFO (call_generative_model): Call completed using KeyID {key_id_used_for_this_call}. Final Status: {status}")
    return response_text, status


# === CÁC HÀM AI CHÍNH (generate_reply, detect_intent, suggest_rule) ===
# Chúng gọi hàm call_generative_model nên không cần sửa logic retry bên trong

def generate_reply_with_ai(prompt_data: dict, persona_id: str) -> tuple[str | None, str]:
    """Tạo câu trả lời, sử dụng call_generative_model và xử lý fallback."""
    task_type = 'generate_reply'
    print(f"DEBUG (generate_reply): Start. Persona='{persona_id}', Task='{task_type}'")
    # ... (Lấy persona, template content như cũ) ...
    if not db: return None, "error_db_module_missing"
    persona = db.get_persona_details(persona_id)
    template_content = db.get_prompt_template_by_task(task_type)
    if not persona: return None, "error_ai_persona_not_found"
    if not template_content: return None, "error_ai_prompt_template_not_found"
    # ... (Render final_prompt như cũ) ...
    final_prompt = ""
    try:
        jinja_env = Environment(); jinja_template = jinja_env.from_string(template_content)
        render_context = {"base_prompt": persona.get('base_prompt', ''), **prompt_data}
        final_prompt = jinja_template.render(render_context)
    except Exception as render_err: return None, "error_ai_prompt_render_failed"

    # Gọi hàm call_generative_model
    generated_text, call_status = call_generative_model(prompt=final_prompt, persona_id=persona_id)

    # Xử lý kết quả và fallback
    processed_reply = generated_text
    final_status = call_status
    if final_status == 'success' or final_status == 'error_ai_empty':
        if not processed_reply: final_status = "error_ai_empty"
        else:
            # ... (Thay thế ngày tháng) ...
            try:
                server_tz = _get_configured_timezone()
                now = datetime.now(server_tz)
                processed_reply = processed_reply.replace("[Ngày hôm nay]", now.strftime("%d")).replace("[Tháng]", now.strftime("%m")).replace("[Năm]", now.strftime("%Y"))
            except Exception: pass # Bỏ qua lỗi thay thế ngày tháng
            # ... (Kiểm tra unhelpful và fallback như cũ) ...
            is_unhelpful = False # ... (logic kiểm tra) ...
            if any(p in processed_reply.lower() for p in ["tôi không biết", "tôi không chắc", "tôi không thể trả lời"]) or re.search(r'\[.*?\]', processed_reply): is_unhelpful = True
            if is_unhelpful:
                fallback_ref = persona.get('fallback_template_ref') # ... (logic chọn fallback_ref) ...
                if not fallback_ref: fallback_ref = 'fallback_generic' # Default
                variations = db.get_template_variations(fallback_ref) if db else None
                fallback_reply = random.choice(variations).get('variation_text') if variations else None
                if fallback_reply: processed_reply = fallback_reply; final_status = "success_fallback_template"
                else: final_status = "error_ai_unhelpful_no_fallback"; processed_reply = None
            else: final_status = "success_ai"
    elif final_status != 'success': processed_reply = None

    print(f"DEBUG (generate_reply): Return Status: {final_status}, Text: '{str(processed_reply)[:100]}...'")
    return processed_reply, final_status


def detect_user_intent_with_ai(text: str, persona_id: str | None = None) -> str:
    """Phân loại ý định, dùng call_generative_model."""
    task_type = 'detect_intent'
    print(f"DEBUG (detect_intent): Start. Persona='{persona_id or 'Default'}', Text='{text[:100]}...'")
    if not text or not text.strip(): return 'unknown'
    if not db: return 'error' # Cần DB để lấy template/persona
    final_prompt = ""
    persona_to_use_for_call = persona_id
    # --- Chuẩn bị prompt (Như code đã cung cấp trước đó) ---
    if persona_id:
        try:
            template_content = db.get_prompt_template_by_task(task_type)
            persona = db.get_persona_details(persona_id)
            if persona and template_content:
                 jinja_env=Environment(); jinja_template=jinja_env.from_string(template_content)
                 valid_intents_list_str = ", ".join([i for i in VALID_INTENTS if i not in ['unknown', 'error', 'start', 'simulated_turn']])
                 render_context = {"base_prompt": persona.get('base_prompt',''), "text": text, "valid_intents_list": valid_intents_list_str}
                 final_prompt = jinja_template.render(render_context)
            else: persona_to_use_for_call = None
        except Exception as e: print(f"WARN: Error get template/persona: {e}"); persona_to_use_for_call = None
    if not persona_to_use_for_call or not final_prompt:
        intent_list_str = ", ".join([i for i in VALID_INTENTS if i not in ['unknown', 'error', 'start', 'simulated_turn']])
        final_prompt = f"""Phân loại ý định... Tin nhắn: "{text}" ... [{intent_list_str}] ..."""
        persona_to_use_for_call = None # Dùng config AI mặc định
        print(f"DEBUG (detect_intent): Using default prompt.")
    # --- Hết chuẩn bị prompt ---

    response_text, call_status = call_generative_model(prompt=final_prompt, persona_id=persona_to_use_for_call)

    # --- Xử lý kết quả (như code đã cung cấp trước đó) ---
    detected_intent = 'error'
    if call_status == 'success' and response_text:
        try:
            raw_intent = response_text.strip().lower(); raw_intent = re.sub(r'[.!?:;"\']', '', raw_intent); raw_intent = raw_intent.split()[0]
            found_valid_intent = 'other'
            if raw_intent in VALID_INTENTS: found_valid_intent = raw_intent
            else:
                possible_matches = [vi for vi in VALID_INTENTS if vi not in ['other', 'unknown', 'error', 'start', 'simulated_turn']]
                for valid_intent in possible_matches:
                     if re.search(r'\b' + re.escape(valid_intent) + r'\b', raw_intent): found_valid_intent = valid_intent; break
            if found_valid_intent in VALID_INTENTS: detected_intent = found_valid_intent
            else: detected_intent = 'other'
        except Exception as parse_err: print(f"ERROR parsing intent: {parse_err}"); detected_intent = 'error'
    elif call_status == 'error_ai_empty': detected_intent = 'other'
    else: detected_intent = 'error'
    print(f"DEBUG (detect_intent): Final detected intent: '{detected_intent}'")
    return detected_intent


def suggest_rule_from_interaction(interaction_data: dict, persona_id: str) -> tuple[str | None, str | None, str | None, str | None]:
    """Đề xuất rule, dùng call_generative_model."""
    task_type = 'suggest_rule'
    print(f"DEBUG (suggest_rule): Start. PersonaID='{persona_id}'")
    # ... (Kiểm tra input interaction_data như cũ) ...
    if not interaction_data or not interaction_data.get('received_text') or not interaction_data.get('sent_text'): return None, None, None, None
    if not db: return None, None, None, None

    # --- Chuẩn bị prompt (Như code đã cung cấp trước đó) ---
    persona = db.get_persona_details(persona_id); template_content = db.get_prompt_template_by_task(task_type)
    if not persona: persona = {}
    if not template_content: print(f"ERROR: Template '{task_type}' not found."); return None, None, None, None
    final_prompt = ""
    try:
        jinja_env=Environment(); jinja_template=jinja_env.from_string(template_content)
        valid_categories_for_prompt = [c for c in VALID_INTENTS if c not in ['unknown', 'error', 'start', 'simulated_turn', 'any']]
        render_context = {"base_prompt": persona.get('base_prompt', ''), "valid_categories_list": valid_categories_for_prompt, **interaction_data}
        final_prompt = jinja_template.render(render_context)
    except Exception as render_err: print(f"ERROR render suggest prompt: {render_err}"); return None, None, None, None

    # --- Gọi API ---
    # Truyền persona_id để call_generative_model dùng đúng model/config (ví dụ temperature thấp cho suggestion)
    response_text, call_status = call_generative_model(prompt=final_prompt, persona_id=persona_id)

    # --- Xử lý kết quả (như cũ) ---
    suggested_keywords = suggested_category = suggested_template_ref = suggested_template = None
    if call_status == 'success' and response_text:
        print(f"DEBUG (suggest_rule): AI Raw Response:\n{response_text}")
        try:
            # ... (Logic parse regex để lấy 4 giá trị như cũ) ...
            def clean_extracted_text(text):
                 if text: text = text.split("Category:")[0].split("Template Ref:")[0].split("Template Text:")[0]; text = re.sub(r'^[\s*-]+|[\s*-]+$', '', text, flags=re.MULTILINE).strip(); return text if text else None; return None
            kw_match = re.search(r"^Keywords:(.*?)(\nCategory:|\nTemplate Ref:|\nTemplate Text:|\Z)", response_text, re.I|re.M|re.S)
            cat_match = re.search(r"^Category:(.*?)(\nTemplate Ref:|\nTemplate Text:|\Z)", response_text, re.I|re.M|re.S)
            ref_match = re.search(r"^Template Ref:(.*?)(\nTemplate Text:|\Z)", response_text, re.I|re.M|re.S)
            tpl_match = re.search(r"^Template Text:(.*)", response_text, re.I|re.M|re.S)
            suggested_keywords = clean_extracted_text(kw_match.group(1) if kw_match else None)
            suggested_category = clean_extracted_text(cat_match.group(1) if cat_match else None)
            suggested_template_ref = clean_extracted_text(ref_match.group(1) if ref_match else None)
            suggested_template = clean_extracted_text(tpl_match.group(1) if tpl_match else None)
            if suggested_template and "cannot generalize" in suggested_template.lower(): suggested_template = None
        except Exception as parse_err: print(f"ERROR parsing suggestion: {parse_err}")
    # else: # Các lỗi khác từ call_generative_model đã được log bên trong nó

    print(f"INFO (suggest_rule): Suggestion results - KW: {suggested_keywords is not None}, Cat: {suggested_category is not None}, Ref: {suggested_template_ref is not None}, Txt: {suggested_template is not None}")
    return suggested_keywords, suggested_category, suggested_template_ref, suggested_template

def suggest_element_classifications(elements_list):

    """
    Sử dụng AI để gợi ý phân loại cho danh sách các UI elements.

    Args:
        elements_list (list): List các dict element, mỗi dict chứa ít nhất
                              'element_id', 'element_type', 'text_content'.

    Returns:
        list: List các element ban đầu được bổ sung thêm key 'suggested_classification'.
              Trả về list gốc nếu có lỗi hoặc không có gợi ý.
    """
    if not elements_list:
        return elements_list

    print(f"Requesting AI suggestions for {len(elements_list)} elements...")

    # --- Xây dựng Prompt ---
    prompt = f"""
    Bạn là một chuyên gia phân tích giao diện người dùng ứng dụng di động. Nhiệm vụ của bạn là phân loại các yếu tố UI (elements) sau đây dựa trên loại (type), văn bản (text), và ID của chúng. Hãy gán cho mỗi element một loại classification phù hợp nhất từ danh sách sau:

    {', '.join(VALID_CLASSIFICATIONS)}

    Giải thích ngắn gọn về các loại:
    - non_interactive: Chỉ hiển thị thông tin, không thể click/nhập liệu (TextView, ImageView).
    - navigation: Dùng để di chuyển giữa các màn hình/phần (Tabs, Back button, Menu).
    - primary_action: Nút thực hiện hành động chính của màn hình (Login, Post, Save).
    - secondary_action: Hành động phụ, ít quan trọng hơn (Cancel, Forgot Password).
    - input_field: Trường để người dùng nhập liệu (EditText).
    - strategy_critical: Sẽ được gán thủ công sau nếu cực kỳ quan trọng.
    - ignore: Nên bỏ qua (Quảng cáo, phần tử không liên quan).
    - unclassified: Nếu không chắc chắn.

    Input là một danh sách JSON các elements. Output của bạn PHẢI là một danh sách JSON hợp lệ, chứa các đối tượng tương ứng với input, mỗi đối tượng được bổ sung thêm key "suggested_classification" với giá trị là một trong các loại trên.

    Ví dụ Input Element:
    {{ "element_id": "com.example:id/button_login", "element_type": "android.widget.Button", "text_content": "Login" }}

    Ví dụ Output mong muốn cho element đó:
    {{ "element_id": "com.example:id/button_login", "element_type": "android.widget.Button", "text_content": "Login", "suggested_classification": "primary_action" }}

    Đây là danh sách các elements cần phân loại:
    ```json
    {json.dumps(elements_list, indent=2)}
    Hãy cung cấp output chỉ là danh sách JSON các elements đã được phân loại.
    """

    try:
        # Sử dụng hàm gọi Gemini đã có (ví dụ: generate_content_with_retry)
        # Đảm bảo hàm này xử lý việc lấy API key và gọi API
        response_text = generate_content_with_retry(prompt) # Gọi hàm của bạn ở đây

        if not response_text:
            print("AI classification suggestion failed: No response.")
            return elements_list # Trả về list gốc

        # --- Parse Response ---
        # Cố gắng parse JSON từ response (AI có thể trả về text kèm theo ```json ... ```)
        try:
            # Tìm và trích xuất khối JSON
            json_start = response_text.find('```json')
            json_end = response_text.rfind('```')
            if json_start != -1 and json_end != -1:
                json_str = response_text[json_start + 7 : json_end].strip()
            else:
                # Nếu không có ```json, thử parse toàn bộ response
                json_str = response_text.strip()

            suggested_classifications = json.loads(json_str)

            if not isinstance(suggested_classifications, list) or len(suggested_classifications) != len(elements_list):
                print(f"AI classification suggestion failed: Output format mismatch. Expected list of {len(elements_list)} items.")
                print(f"Received: {suggested_classifications}")
                return elements_list

            # Ghép gợi ý vào list gốc dựa trên element_id
            suggestions_map = {item.get('element_id'): item.get('suggested_classification')
                            for item in suggested_classifications if item.get('element_id')}

            result_list = []
            for element in elements_list:
                el_id = element.get('element_id')
                suggestion = suggestions_map.get(el_id)
                if suggestion and suggestion in VALID_CLASSIFICATIONS:
                    element['suggested_classification'] = suggestion
                else:
                    # Giữ lại classification hiện có hoặc unclassified nếu không có gợi ý hợp lệ
                    element['suggested_classification'] = element.get('classification', 'unclassified')
                result_list.append(element)

            print("Successfully received and processed AI classification suggestions.")
            return result_list

        except json.JSONDecodeError as json_err:
            print(f"AI classification suggestion failed: JSON Decode Error - {json_err}")
            print(f"Raw response: {response_text}")
            return elements_list # Trả về list gốc

    except Exception as e:
        print(f"An error occurred during AI classification suggestion: {e}")
        import traceback
        traceback.print_exc()
        return elements_list


def get_gemini_client(api_key):
    """Khởi tạo client Gemini với API key."""
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash') # Hoặc model bạn muốn
        return model
    except Exception as e:
        print(f"Error configuring Gemini with key {api_key[:5]}...: {e}")
        return None

def get_next_api_key():
    """Lấy API key hợp lệ tiếp theo từ CSDL."""
    keys = database.get_valid_api_keys('gemini') # Lấy key từ DB
    if not keys:
        print("Error: No valid Gemini API keys found in database.")
        return None

    # Lọc các key đang bị disable tạm thời
    available_keys = [
        key for key in keys
        if key['api_key'] not in DISABLED_KEYS or datetime.now() > DISABLED_KEYS[key['api_key']]
    ]

    if not available_keys:
        print("Warning: All Gemini API keys are currently disabled.")
        # Có thể chờ một chút hoặc trả về None
        # Tìm key bị disable sớm nhất để biết khi nào có thể thử lại
        earliest_enable_time = min(DISABLED_KEYS.values()) if DISABLED_KEYS else None
        print(f"Earliest key enable time: {earliest_enable_time}")
        return None # Hoặc có thể chọn 1 key random từ keys gốc và thử vận may

    # Chọn ngẫu nhiên một key từ các key khả dụng
    selected_key_info = random.choice(available_keys)

    # Xóa key khỏi DISABLED_KEYS nếu nó đã hết hạn disable
    if selected_key_info['api_key'] in DISABLED_KEYS:
         del DISABLED_KEYS[selected_key_info['api_key']]

    print(f"Using Gemini API key ID: {selected_key_info['key_id']}")
    return selected_key_info['api_key']

def disable_api_key(api_key):
    """Disable một API key tạm thời."""
    if api_key:
        print(f"Disabling Gemini API key {api_key[:5]}... for {DISABLE_DURATION}")
        DISABLED_KEYS[api_key] = datetime.now() + DISABLE_DURATION
        # Cập nhật trạng thái trong DB nếu cần
        # database.update_api_key_status(api_key, 'disabled')


MAX_RETRIES = 3
RETRY_DELAY = 5 # seconds

def generate_content_with_retry(prompt, generation_config=None):
    """
    Gọi API Gemini với cơ chế retry và xoay vòng key.

    Args:
        prompt (str): Prompt cho Gemini.
        generation_config (dict, optional): Cấu hình generation (temperature, etc.).

    Returns:
        str: Nội dung text được tạo ra bởi Gemini, hoặc None nếu thất bại sau các lần thử.
    """
    retries = 0
    last_error = None

    default_config = genai.types.GenerationConfig(
        # candidate_count=1, # Mặc định là 1
        # stop_sequences=["..."], # Nếu cần stop sequence
        # max_output_tokens=2048, # Giới hạn output
        temperature=0.7, # Điều chỉnh độ sáng tạo
        # top_p=1.0,
        # top_k=1
    )
    current_config = generation_config if generation_config else default_config


    while retries < MAX_RETRIES:
        api_key = get_next_api_key()
        if not api_key:
            print("Generation failed: No available API keys.")
            return None # Không có key để thử

        model = get_gemini_client(api_key)
        if not model:
            disable_api_key(api_key) # Disable key nếu không configure được client
            retries += 1
            time.sleep(RETRY_DELAY)
            continue # Thử key tiếp theo

        try:
            print(f"Attempt {retries + 1}/{MAX_RETRIES} using key {api_key[:5]}...")
            # Thêm safety_settings nếu cần thiết
            safety_settings = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]
            response = model.generate_content(
                prompt,
                generation_config=current_config,
                safety_settings=safety_settings
                )

            # Kiểm tra xem response có bị block không (dựa vào prompt_feedback)
            if response.prompt_feedback.block_reason:
                 print(f"Warning: Prompt blocked for key {api_key[:5]}... Reason: {response.prompt_feedback.block_reason}")
                 # Coi như lỗi, disable key và retry
                 last_error = f"Prompt blocked: {response.prompt_feedback.block_reason}"
                 disable_api_key(api_key)
                 retries += 1
                 time.sleep(RETRY_DELAY)
                 continue

            # Kiểm tra xem có nội dung trả về không
            if not response.candidates or not response.text:
                 # Đôi khi không có text dù không bị block (vd: lỗi server?)
                 print(f"Warning: No content generated for key {api_key[:5]}... Candidates: {response.candidates}")
                 last_error = "No content generated"
                 # Có thể không cần disable key ngay, nhưng nên retry
                 retries += 1
                 time.sleep(RETRY_DELAY)
                 continue


            print("Gemini call successful.")
            return response.text # Trả về nội dung text

        except Exception as e:
            print(f"Error during Gemini API call with key {api_key[:5]}...: {e}")
            last_error = e
            # Phân tích lỗi cụ thể hơn nếu cần (vd: Quota exceeded, Invalid API Key)
            error_str = str(e).lower()
            if "api key not valid" in error_str or "permission denied" in error_str or "invalid" in error_str:
                print(f"Disabling potentially invalid API key: {api_key[:5]}...")
                disable_api_key(api_key)
                # Có thể cập nhật trạng thái key trong DB là 'invalid'
                # database.update_api_key_status(api_key, 'invalid')

            elif "quota" in error_str or "resource has been exhausted" in error_str:
                 print(f"Quota likely exceeded for key {api_key[:5]}... Disabling temporarily.")
                 disable_api_key(api_key) # Disable tạm thời

            # Lỗi khác thì chỉ retry
            retries += 1
            print(f"Retrying in {RETRY_DELAY} seconds...")
            time.sleep(RETRY_DELAY)

    print(f"Gemini generation failed after {MAX_RETRIES} retries. Last error: {last_error}")
    return None

def plan_exploration_action(current_screen_id: str, ui_state: dict | None, screen_elements: list | None, mapping_goal: str | None = None) -> dict | None:
    """
    Sử dụng AI (Gemini) để quyết định hành động khám phá (exploration) tiếp theo.
    Hàm này nhận thông tin màn hình hiện tại (từ client và từ Neo4j), mục tiêu (nếu có),
    và trả về một hành động đề xuất (click, input, back, stuck, wait).

    Args:
        current_screen_id: ID (đã chuẩn hóa) của màn hình hiện tại.
        ui_state: Dictionary chứa thông tin UI state thô hoặc đã xử lý từ client.
                  Cần có key 'elements' chứa list các element UI.
        screen_elements: List các dictionary element đã biết của màn hình này
                         (lấy từ Neo4j, chứa classification, counts...). Có thể None hoặc rỗng.
        mapping_goal: Mục tiêu mapping hiện tại (ví dụ: "Map Login Flow").

    Returns:
        Dictionary chứa thông tin nextAction hoặc None nếu có lỗi nghiêm trọng.
        Action có thể là 'click', 'input', 'back', 'stuck', 'wait'.
    """
    logger = current_app.logger if current_app else print
    logger.info(f"Planning next action for screen: {current_screen_id}, goal: {mapping_goal}")

    # --- Bước 1: Chuẩn bị Context về các Element có thể Tương tác ---
    potential_actions = []
    if not isinstance(ui_state, dict) or not isinstance(ui_state.get('elements'), list):
        logger.warning(f"plan_exploration_action: Invalid or missing 'elements' in ui_state for screen {current_screen_id}. Cannot plan effectively.")
        # Nếu không có element nào từ client -> fallback ngay?
        # return {"action": "back", "reason": "No element data received from client."} # Hoặc trả về stuck
    else:
        # Tạo map từ screen_elements (Neo4j) để tra cứu nhanh thông tin đã biết
        known_elements_map = {
            el.get('element_id'): el
            for el in (screen_elements or []) # Đảm bảo screen_elements là list
            if isinstance(el, dict) and el.get('element_id')
        }
        logger.debug(f"Known elements map from Neo4j for screen {current_screen_id}: {list(known_elements_map.keys())}")

        # Lặp qua các element client gửi lên (trong ui_state)
        processed_element_ids = set() # Để tránh trùng lặp nếu client gửi nhiều lần cùng 1 element
        for el_report in ui_state['elements']:
            if not isinstance(el_report, dict): continue

            # Ưu tiên lấy ID chuẩn hóa (đã được xử lý bởi process_raw_ui_state nếu có)
            el_id = el_report.get('element_id')
            id_type = el_report.get('identifier_type')

            # Nếu không có ID chuẩn hóa, thử lấy lại từ raw data (resource-id > content-desc)
            if not el_id:
                el_id = el_report.get('resource-id')
                id_type = 'resource-id'
                if not el_id:
                    el_id = el_report.get('content-desc')
                    id_type = 'content-desc'

            if not el_id or el_id in processed_element_ids: continue # Bỏ qua nếu không có ID hoặc đã xử lý
            processed_element_ids.add(el_id)

            known_info = known_elements_map.get(el_id, {}) # Lấy thông tin từ Neo4j nếu có

            action_candidate = {
                 # Thông tin cơ bản từ client report (đã chuẩn hóa tên nếu có)
                 'element_id': el_id,
                 'identifier_type': id_type or known_info.get('identifier_type'), # Ưu tiên id_type mới nhất
                 'element_type': el_report.get('element_type') or el_report.get('class_name') or known_info.get('element_type'),
                 'text_content': el_report.get('text_content') or el_report.get('text') or known_info.get('text_content'),
                 'content_desc': el_report.get('content_desc') or known_info.get('content_desc'), # Thêm content_desc
                 'coordinates': el_report.get('coordinates') or known_info.get('coordinates'),
                 'bounds': el_report.get('bounds'), # Lấy bounds nếu client gửi
                 # Thông tin từ Neo4j (có giá trị mặc định)
                 'classification': known_info.get('classification', 'unclassified'),
                 'is_clickable_observed': known_info.get('is_clickable_observed', False),
                 'is_editable_observed': known_info.get('is_editable_observed', False),
                 'attempt_count': known_info.get('attempt_count', 0),
                 'success_count': known_info.get('success_count', 0),
             }
             # Chỉ thêm các key có giá trị (loại bỏ None)
            potential_actions.append({k:v for k,v in action_candidate.items() if v is not None})

            logger.debug(f"Prepared {len(potential_actions)} potential actions for AI prompt.")
            # Log một vài action đầu tiên để kiểm tra
            if potential_actions:
                logger.debug(f"Sample potential actions: {json.dumps(potential_actions[:2], indent=2)}")


            # --- Bước 2: Xây dựng Prompt chi tiết cho AI ---
            prompt = f"""
            Bạn là AI điều phối viên thông minh cho việc khám phá tự động ứng dụng di động. Nhiệm vụ của bạn là phân tích trạng thái màn hình hiện tại và chọn ra hành động TỐT NHẤT tiếp theo để thực hiện nhằm mục đích xây dựng bản đồ ứng dụng (mapping).

            **Thông tin Màn hình Hiện tại:**
            * **Screen ID:** {current_screen_id}
            * **Mục tiêu Mapping:** {mapping_goal if mapping_goal else "General Exploration (Khám phá các tính năng chưa biết)"}

            **Các Yếu tố UI (Elements) có thể tương tác trên màn hình:**
            (Danh sách này bao gồm các element được phát hiện bởi client và thông tin đã biết về chúng từ lịch sử khám phá)
            ```json
            {json.dumps(potential_actions, indent=2)}
            Giải thích các trường quan trọng trong element:

            element_id: Mã định danh (resource-id hoặc content-desc).
            identifier_type: Loại mã định danh (resource-id hoặc content-desc).
            element_type: Loại class của UI (vd: android.widget.Button, android.widget.EditText, android.widget.ImageView).
            text_content: Văn bản hiển thị trên element.
            content_desc: Mô tả nội dung (thường dùng cho Button, ImageView không có text).
            classification: Phân loại do người dùng hoặc AI gán (unclassified, navigation, primary_action, input_field, non_interactive, ignore...).
            is_clickable_observed: true nếu đã từng click thành công vào element này.
            is_editable_observed: true nếu đã từng nhập liệu thành công vào element này.
            attempt_count: Số lần đã thử tương tác với element này từ màn hình này.
            success_count: Số lần tương tác thành công.
            Quy tắc Ưu tiên Chọn Hành động:

            Ưu tiên Mục tiêu (nếu có mapping_goal):

            Tìm các element có classification là 'strategy_critical', 'primary_action', 'navigation', 'input_field' mà có text_content hoặc element_id hoặc content_desc liên quan đến mục tiêu. Ví dụ: Nếu mục tiêu là "Login", ưu tiên click nút "Login", nhập liệu vào trường "username"/"password".
            Nếu tìm thấy element phù hợp mục tiêu và chưa được thử nhiều (attempt_count thấp), hãy chọn hành động tương tác với nó (click hoặc input).
            Ưu tiên Khám phá Element Mới/Chưa Tương tác Nhiều:

            Tìm element có classification không phải là 'non_interactive' hoặc 'ignore'.
            Trong số đó, ưu tiên những element có attempt_count bằng 0 (chưa thử bao giờ).
            Nếu không còn element chưa thử, ưu tiên element có attempt_count thấp và có tỷ lệ thành công không quá tệ (ví dụ: success_count / attempt_count >= 0.5).
            Đặc biệt chú ý các element có element_type thường là tương tác được như Button, EditText, CheckBox, ImageView (nếu có content_desc hoặc is_clickable_observed=true).
            Nếu tìm thấy element phù hợp để khám phá, hãy chọn hành động 'click' (hoặc 'input' nếu là EditText và mục tiêu yêu cầu).
            Xử lý Các Trường hợp Đặc biệt:

            Màn hình Ít Element (Có thể là Popup/Dialog): Nếu chỉ có vài element và có các nút với text như "OK", "Allow", "Dismiss", "Cancel", "Later", "Got it", hãy ưu tiên click các nút này hoặc thực hiện hành động 'back'.
            Tránh Lặp Ngay Lập Tức: (Logic ngoài sẽ hỗ trợ thêm) Cố gắng không chọn lại hành động vừa gây ra việc quay lại màn hình này (nếu thông tin này được cung cấp).
            Hành động Fallback (Khi không tìm thấy gì để click/input):

            Ưu tiên 1: Vuốt (Swipe): Nếu màn hình có thể cuộn (dựa vào context hoặc loại activity), hãy thử hành động 'swipe_up' hoặc 'swipe_down' nếu chưa thử từ trạng thái này. (Output: {{"action": "swipe_up", "reason": "No clear action, trying to scroll up"}})
            Ưu tiên 2: Back: Nếu không thể vuốt hoặc đã thử vuốt, hãy thử hành động 'back'. (Output: {{"action": "back", "reason": "No interactive elements found or swipe failed, trying back"}})
            Cuối cùng: Stuck: Nếu đã thử cả 'back' mà không thoát khỏi màn hình hoặc không có hành động nào khác, hãy báo cáo 'stuck'. (Output: {{"action": "stuck", "reason": "Cannot find any new action or navigate back"}})
            Yêu cầu Output:

            Output của bạn PHẢI là một đối tượng JSON DUY NHẤT đại diện cho hành động được chọn. Định dạng JSON phải tuân thủ một trong các cấu trúc sau:

            Click: {{"action": "click", "element_id": "...", "identifier_type": "...", "reason": "..."}} (Bắt buộc có element_id và identifier_type)
            Input: {{"action": "input", "element_id": "...", "identifier_type": "...", "text": "...", "reason": "..."}} (Bắt buộc có element_id, identifier_type. Quyết định text dựa vào mục tiêu hoặc dùng text mẫu)
            Swipe: {{"action": "swipe_up", "reason": "..."}} hoặc {{"action": "swipe_down", "reason": "..."}}
            Back: {{"action": "back", "reason": "..."}}
            Stuck: {{"action": "stuck", "reason": "..."}}
            Wait: {{"action": "wait", "duration": <số giây>, "reason": "..."}} (Chỉ dùng khi thực sự cần chờ đợi)
            Hãy phân tích kỹ lưỡng và chọn hành động TỐT NHẤT dựa trên các quy tắc và thông tin được cung cấp. Chỉ trả về đối tượng JSON của hành động đó.
            """

        try:
            # --- Bước 3: Gọi AI và Xử lý Response ---
            # Sử dụng hàm generate_content_with_retry đã có
            response_text = generate_content_with_retry(prompt)

            if not response_text:
                logger.error(f"AI Planner failed for screen {current_screen_id}: No response from AI.")
                # Fallback khi AI không phản hồi
                return {"action": "back", "reason": "AI Planner did not respond."}

            # Parse JSON response cẩn thận
            try:
                # Cố gắng tìm khối JSON hợp lệ đầu tiên trong response
                first_brace = response_text.find('{')
                last_brace = response_text.rfind('}')
                if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                    json_str = response_text[first_brace : last_brace + 1]
                    next_action = json.loads(json_str)
                else:
                    # Thử parse toàn bộ nếu không tìm thấy {} rõ ràng
                    next_action = json.loads(response_text.strip())

                # Validate cấu trúc cơ bản của action
                if isinstance(next_action, dict) and 'action' in next_action:
                    logger.info(f"AI Planner suggested action: {next_action}")
                    # Kiểm tra các trường bắt buộc cho từng loại action
                    action_type = next_action.get('action')
                    if action_type in ['click', 'input']:
                        if not next_action.get('element_id') or not next_action.get('identifier_type'):
                            logger.error(f"AI Planner Error: Missing 'element_id' or 'identifier_type' for action '{action_type}'. Raw response: {response_text}")
                            # Fallback nếu action không đủ thông tin
                            return {"action": "stuck", "reason": f"AI Planner returned incomplete action '{action_type}'"}
                    # Thêm các validate khác nếu cần (vd: kiểm tra duration cho wait)
                    return next_action # Trả về action hợp lệ
                else:
                    logger.error(f"AI Planner failed: Invalid action format in JSON. Parsed JSON: {next_action}. Raw response: {response_text}")
                    return {"action": "stuck", "reason": "AI Planner returned invalid action format"}

            except json.JSONDecodeError as json_err:
                logger.error(f"AI Planner failed: JSON Decode Error - {json_err}. Raw response: {response_text}")
                # Fallback khi không parse được JSON -> thử back
                return {"action": "back", "reason": "AI Planner response parsing failed"}

        except Exception as e:
            logger.error(f"An error occurred during AI Planning for screen {current_screen_id}: {e}", exc_info=True)
            traceback.print_exc()
            # Fallback an toàn khi có lỗi hệ thống
            return {"action": "back", "reason": f"AI Planner exception: {e}"}
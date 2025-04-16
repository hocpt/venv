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
from jinja2 import Environment, Template

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

# --- Helper Function: Get Timezone ---
def _get_configured_timezone():
    try: return pytz.timezone('Asia/Ho_Chi_Minh') # Hoặc đọc từ config nếu có
    except: return pytz.utc

# --- === HÀM HELPER MỚI: LẤY VÀ CẤU HÌNH KEY XOAY VÒNG === ---
__current_configured_key_id = None
__last_configure_time = None
def _get_active_key_and_configure(provider: str = 'google_gemini') -> int | None:
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
            key_id_used_for_this_attempt = _get_active_key_and_configure('google_gemini')
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


# === THÊM DÒNG PRINT DEBUG Ở CUỐI FILE ===
print("DEBUG: app/ai_service.py - Module loaded completely.")
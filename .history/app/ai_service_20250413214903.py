# app/ai_service.py
import os
import google.generativeai as genai
from flask import current_app # Import current_app để truy cập config
import re
import traceback
import random
from datetime import datetime, timezone # Thêm timezone
import pytz # Thêm pytz
import time # Thêm time
from google.api_core import exceptions as api_core_exceptions # Import exception cụ thể
import json
from jinja2 import Environment, Template

# --- Import Database Module ---
try:
    from . import database as db
except ImportError:
    try:
        import database as db
        print("WARNING (ai_service): Using fallback database import.")
    except ImportError:
        print("CRITICAL ERROR (ai_service): Cannot import database module.")
        db = None

# --- Constants for Retry Logic ---
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 5
BACKOFF_FACTOR = 2
MAX_JITTER_SECONDS = 1.5
MAX_RETRY_DELAY_SECONDS = 60.0

# --- DANH SÁCH INTENT ĐÃ ĐỊNH NGHĨA ---
# (Lấy từ config hoặc định nghĩa ở đây) - Đảm bảo khớp với DB/Logic khác
VALID_INTENTS = [
    'greeting', 'price_query', 'shipping_query', 'product_info_query',
    'compliment', 'complaint', 'connection_request', 'spam',
    'positive_generic', 'negative_generic', 'other', 'unknown', 'error',
    'start', 'simulated_turn' # Thêm các intent dùng nội bộ nếu cần
]

# --- Global Flag for Gemini Configuration ---
__gemini_configured = False

# --- Helper Functions (Should remain mostly unchanged) ---

def _get_api_key():
    """Hàm nội bộ để lấy API key từ config của Flask app."""
    # (Giữ nguyên code hàm này như trước)
    try:
        # Ưu tiên lấy key từ DB trước nếu sau này implément Key Rotation
        # key = db.get_an_active_api_key('google_gemini')
        # if key: return key
        # Nếu không có key từ DB hoặc chưa implement, lấy từ config
        key = current_app.config.get('GOOGLE_API_KEY')
        if not key:
            print("WARNING (ai_service): GOOGLE_API_KEY not found in app.config.")
        return key
    except RuntimeError: # Lỗi nếu gọi ngoài app context (khi không dùng key từ DB)
         # Nếu dùng key từ DB thì không cần current_app ở đây
         # print(f"ERROR (ai_service): Cannot access app context for API key.")
         # Thay vào đó, đọc trực tiếp từ os.environ nếu cần fallback
         key = os.environ.get('GOOGLE_API_KEY')
         if not key:
              print("ERROR (ai_service): GOOGLE_API_KEY not found in environment variables either.")
         return key
    except Exception as e:
        print(f"ERROR (ai_service): Unknown error getting API key: {e}")
        return None

def configure_gemini_if_needed():
    """Cấu hình API key cho thư viện Gemini nếu chưa làm."""
    # (Giữ nguyên code hàm này như trước)
    global __gemini_configured
    if __gemini_configured:
        return True
    api_key = _get_api_key()
    if api_key:
        try:
            genai.configure(api_key=api_key)
            print("INFO (ai_service): Google AI API Key configured successfully.")
            __gemini_configured = True
            return True
        except Exception as config_err:
            print(f"ERROR (ai_service): Failed to configure Google AI API Key: {config_err}")
            return False
    else:
        print("ERROR (ai_service): Cannot configure Gemini - API Key is missing.")
        return False

def _parse_generation_config(config_str_or_dict) -> genai.types.GenerationConfig | None:
    """ Chuyển đổi chuỗi JSON hoặc dict thành GenerationConfig object. """
    # (Giữ nguyên code hàm này như trước)
    if not config_str_or_dict: return None
    config_dict = None
    if isinstance(config_str_or_dict, str):
        try: config_dict = json.loads(config_str_or_dict)
        except json.JSONDecodeError: return None
    elif isinstance(config_str_or_dict, dict): config_dict = config_str_or_dict
    else: return None
    if config_dict and isinstance(config_dict, dict):
        try:
            valid_args = {k: v for k, v in config_dict.items() if hasattr(genai.types.GenerationConfig(), k)}
            if valid_args: return genai.types.GenerationConfig(**valid_args)
            else: return None
        except Exception: return None
    return None

def _get_configured_timezone():
    """ Lấy timezone đã cấu hình cho scheduler (hoặc default). """
    # Có thể lấy từ config nếu bạn định nghĩa ở đó, hoặc hardcode
    try:
         # Giả sử bạn có SCHEDULER_TIMEZONE trong config
         # tz_str = current_app.config.get('SCHEDULER_TIMEZONE', 'Asia/Ho_Chi_Minh')
         tz_str = 'Asia/Ho_Chi_Minh' # Hoặc hardcode nếu không có trong config
         return pytz.timezone(tz_str)
    except Exception:
         return pytz.utc # Fallback về UTC nếu lỗi

# === HÀM GỌI API GEMINI TỔNG QUÁT (CÓ RETRY) ===
def call_generative_model(prompt: str, persona_id: str | None = None) -> tuple[str | None, str]:
    """
    Hàm gọi API Gemini tổng quát với retry logic cho lỗi 429.
    Sử dụng persona_id để lấy model và generation config phù hợp.
    """
    print(f"DEBUG (call_generative_model): PersonaID='{persona_id or 'Default'}', Prompt='{prompt[:100]}...'")
    response_text = None
    status = "error_unknown"

    if not configure_gemini_if_needed(): # Đảm bảo API key được cấu hình
        return None, "error_ai_no_key_or_config_failed"
    if not prompt:
        return None, "error_input_prompt_empty"

    # --- Lấy cấu hình Model và Generation Config ---
    model_name = current_app.config.get('GEMINI_DEFAULT_MODEL', 'models/gemini-1.5-flash-latest')
    default_gen_config = genai.types.GenerationConfig(
        temperature=current_app.config.get('GEMINI_REPLY_TEMPERATURE', 0.7), # Lấy từ config
        max_output_tokens=current_app.config.get('GEMINI_REPLY_MAX_TOKENS', 1000) # Lấy từ config
    )
    generation_config = default_gen_config
    persona_config_used = False

    if persona_id:
        try:
            persona = db.get_persona_details(persona_id) if db else None # Kiểm tra db tồn tại
            if persona:
                model_name = persona.get('model_name') or model_name
                persona_gen_config_obj = _parse_generation_config(persona.get('generation_config'))
                if persona_gen_config_obj:
                     generation_config = persona_gen_config_obj
                     persona_config_used = True
                print(f"DEBUG (call_generative_model): Using Persona '{persona_id}'. Model: {model_name}, CustomGenCfg: {persona_config_used}")
            else: print(f"WARN (call_generative_model): Persona '{persona_id}' not found. Using defaults.")
        except Exception as db_err: print(f"ERROR (call_generative_model): DB error fetch persona '{persona_id}': {db_err}. Using defaults.")

    if not persona_config_used: print(f"DEBUG (call_generative_model): Using default config. Model: {model_name}")


    # --- Vòng lặp gọi API với Retry ---
    last_exception = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            model = genai.GenerativeModel(model_name)
            print(f"DEBUG (call_generative_model): Attempt {attempt + 1}/{MAX_RETRIES + 1} calling API...")
            response = model.generate_content(prompt, generation_config=generation_config)

            # --- Xử lý Response ---
            response_text = None; status = "error_unknown" # Reset
            if response.parts:
                try:
                    response_text = response.text.strip()
                    if response_text: status = 'success'
                    else: status = 'error_ai_empty'; print(f"WARN: Attempt {attempt + 1} received empty text.")
                except Exception as e_text:
                    status = "error_ai_text_access"; print(f"ERROR: Attempt {attempt + 1} access text failed: {e_text}")
            elif hasattr(response, 'prompt_feedback') and response.prompt_feedback.block_reason:
                status = "error_ai_blocked"; response_text = f"Blocked: {response.prompt_feedback.block_reason}"; print(f"WARN: Attempt {attempt + 1} blocked: {response_text}")
                break # Thoát retry nếu bị chặn
            else:
                status = "error_ai_invalid_response"; print(f"WARN: Attempt {attempt + 1} invalid response structure.")
                break # Thoát retry nếu response lạ

            # Thoát nếu thành công hoặc gặp lỗi không nên retry
            if status != 'error_unknown' and status != 'error_ai_text_access': # Chỉ retry lỗi truy cập text?
                 break

        except api_core_exceptions.ResourceExhausted as e:
            last_exception = e
            print(f"WARN (call_generative_model): Attempt {attempt + 1} failed: Resource Exhausted (429).")
            if attempt >= MAX_RETRIES:
                status = "error_ai_rate_limited"; response_text = f"API rate limit hit after {MAX_RETRIES + 1} attempts."
                break
            # Tính delay
            delay = INITIAL_BACKOFF_SECONDS * (BACKOFF_FACTOR ** attempt) + random.uniform(0, MAX_JITTER_SECONDS)
            # Kiểm tra retry-delay gợi ý từ API (nếu có)
            suggested_delay = None
            if hasattr(e, 'metadata') and isinstance(e.metadata, tuple):
                for item in e.metadata:
                     if isinstance(item, tuple) and len(item) == 2 and item[0] == 'retry-delay':
                          try: suggested_delay = float(item[1].split(':')[-1].strip())
                          except: suggested_delay = None
                          break
            if suggested_delay and suggested_delay > 0:
                 delay = suggested_delay + random.uniform(0, MAX_JITTER_SECONDS)
                 print(f"INFO: Using API suggested retry delay.")
            delay = min(delay, MAX_RETRY_DELAY_SECONDS) # Giới hạn delay tối đa
            print(f"INFO (call_generative_model): Retrying in {delay:.2f} seconds...")
            time.sleep(delay)
            # continue vòng lặp

        except Exception as e: # Lỗi không mong muốn khác
            print(f"ERROR (call_generative_model): Attempt {attempt + 1} failed: {type(e).__name__} - {e}")
            # print(traceback.format_exc()) # Bỏ comment nếu cần debug sâu
            last_exception = e; status = "error_ai_exception"; response_text = f"Unexpected error: {e}"
            break # Thoát vòng lặp

    # --- Kết thúc vòng lặp retry ---
    print(f"INFO (call_generative_model): Call completed. Final Status: {status}")
    return response_text, status


# === HÀM TẠO TRẢ LỜI (ĐÃ REFACTOR ĐỂ DÙNG call_generative_model) ===
def generate_reply_with_ai(prompt_data: dict, persona_id: str) -> tuple[str | None, str]:
    """
    Tạo câu trả lời, sử dụng call_generative_model (có retry) và xử lý fallback.
    """
    task_type = 'generate_reply'
    print(f"DEBUG (generate_reply): Bắt đầu. PersonaID='{persona_id}', Task='{task_type}'")
    final_reply_text = None
    status = "error_ai_unknown"
    final_prompt = "" # Khởi tạo prompt rỗng

    # --- 1. Lấy thông tin Persona và Prompt Template ---
    # (Code lấy persona, template_content như cũ)
    persona = None; template_content = None
    try:
        persona = db.get_persona_details(persona_id) if db else None
        template_content = db.get_prompt_template_by_task(task_type) if db else None
    except Exception as db_err:
        print(f"LỖI (generate_reply): DB error fetching Persona/Template: {db_err}")
        return None, "error_db_ai_config_fetch"
    if not persona: return None, "error_ai_persona_not_found"
    if not template_content: return None, "error_ai_prompt_template_not_found"


    # --- 2. Render Prompt cuối cùng ---
    try:
        # (Code render final_prompt như cũ)
        jinja_env = Environment(); jinja_template = jinja_env.from_string(template_content)
        render_context = {"base_prompt": persona.get('base_prompt', ''), **prompt_data}
        final_prompt = jinja_template.render(render_context)
    except Exception as render_err:
        print(f"LỖI (generate_reply): Render prompt template failed: {render_err}")
        return None, "error_ai_prompt_render_failed"


    # --- 3. Gọi Hàm Gọi API Tập Trung ---
    generated_text, status = call_generative_model(prompt=final_prompt, persona_id=persona_id)

    # --- 4. Xử lý hậu kỳ ---
    processed_reply = generated_text
    if status == 'success' or status == 'error_ai_empty':
        if not processed_reply: status = "error_ai_empty" # Đảm bảo status đúng
        else:
            # 4.1 Thay thế ngày tháng
            try:
                server_tz = _get_configured_timezone()
                now = datetime.now(server_tz)
                temp_reply = processed_reply
                temp_reply = temp_reply.replace("[Ngày hôm nay]", now.strftime("%d"))
                temp_reply = temp_reply.replace("[Tháng]", now.strftime("%m"))
                temp_reply = temp_reply.replace("[Năm]", now.strftime("%Y"))
                if temp_reply != processed_reply: processed_reply = temp_reply
            except Exception as date_err: print(f"WARN (generate_reply): Date replacement error: {date_err}")

        # 4.2 Kiểm tra unhelpful / fallback
        is_unhelpful = False
        unhelpful_patterns = ["tôi không biết", "tôi không chắc", "tôi không có thông tin", "tôi không thể trả lời", "nằm ngoài phạm vi", "không thể giúp"]
        if not processed_reply or any(pattern in processed_reply.lower() for pattern in unhelpful_patterns) or re.search(r'\[.*?\]', processed_reply):
            is_unhelpful = True
            if processed_reply: print(f"WARN: AI response unhelpful/placeholder/empty: '{processed_reply[:100]}...'")

        if is_unhelpful:
            fallback_ref = persona.get('fallback_template_ref') # Ưu tiên fallback từ persona
            if not fallback_ref:
                 account_goal = prompt_data.get('account_goal', 'default')
                 if account_goal == 'make_friend': fallback_ref = 'fallback_make_friend'
                 elif account_goal == 'product_sales': fallback_ref = 'fallback_product_sales'
                 else: fallback_ref = 'fallback_generic'
            print(f"DEBUG: Using fallback template ref: {fallback_ref}")
            variations = db.get_template_variations(fallback_ref) if db else None
            fallback_reply = None
            if variations: fallback_reply = random.choice(variations).get('variation_text')
            if fallback_reply:
                processed_reply = fallback_reply; status = "success_fallback_template"
                print(f"DEBUG: Used fallback template: '{processed_reply[:100]}...'")
            else:
                status = "error_ai_unhelpful_no_fallback"; processed_reply = None
                print(f"WARN: No fallback template found for ref {fallback_ref}.")
        # else: # Nếu không unhelpful và status là 'success'
            # status đã là 'success' từ call_generative_model

    elif status != 'success': # Nếu lỗi từ call_generative_model (blocked, rate_limited, exception)
         processed_reply = None # Đảm bảo không trả về text cũ

    final_reply_text = processed_reply
    print(f"DEBUG (generate_reply): Returning status: {status}, text (first 100): '{str(final_reply_text)[:100]}...'")
    return final_reply_text, status


# === HÀM PHÁT HIỆN Ý ĐỊNH (ĐÃ REFACTOR ĐỂ DÙNG call_generative_model) ===
def detect_user_intent_with_ai(text: str, persona_id: str | None = None) -> str:
    """
    Phân loại ý định của text, sử dụng call_generative_model (có retry).
    """
    task_type = 'detect_intent'
    print(f"DEBUG (detect_intent): Bắt đầu. PersonaID='{persona_id or 'Default'}', Task='{task_type}', Text='{text[:100]}...'")
    detected_intent = 'error' # Mặc định lỗi

    if not text or not text.strip(): return 'unknown'

    # --- Chuẩn bị Prompt, Model, Config ---
    final_prompt = ""
    # Persona và template sẽ được dùng bên trong call_generative_model nếu persona_id được cung cấp
    # Ở đây chỉ cần tạo prompt mặc định nếu không dùng persona/template riêng cho task này
    if not db: # Không thể lấy template nếu db lỗi
         print("ERROR (detect_intent): DB module not available, using default prompt.")
         persona_id = None # Force default prompt if DB unavailable

    template_content = None
    if persona_id: # Chỉ lấy template nếu có persona ID (để dùng chung model/config của persona đó)
         try: template_content = db.get_prompt_template_by_task(task_type)
         except Exception as e: print(f"WARN: Failed to get prompt template {task_type}: {e}")

    if persona_id and template_content:
         # Render prompt dùng template và base_prompt của persona (nếu có)
         try:
              persona_details = db.get_persona_details(persona_id)
              base_prompt_from_persona = persona_details.get('base_prompt', '') if persona_details else ''
              jinja_env = Environment(); jinja_template = jinja_env.from_string(template_content)
              # Pass thêm list intent hợp lệ vào context để template có thể dùng
              valid_intents_list_str = ", ".join([i for i in VALID_INTENTS if i not in ['unknown', 'error']])
              render_context = {"base_prompt": base_prompt_from_persona, "text": text, "valid_intents_list": valid_intents_list_str}
              final_prompt = jinja_template.render(render_context)
              print(f"DEBUG (detect_intent): Using persona/template based prompt.")
         except Exception as render_err:
              print(f"ERROR (detect_intent): Failed render template, fallback to default prompt: {render_err}")
              final_prompt = "" # Reset để dùng default bên dưới
    else:
         # Nếu không có persona_id hoặc không tìm thấy template, dùng prompt mặc định
         if persona_id: print(f"DEBUG (detect_intent): Template for '{task_type}' not found, using default prompt.")
         else: print(f"DEBUG (detect_intent): No Persona ID provided, using default prompt.")
         persona_id = None # Đảm bảo call_generative_model dùng default config

    if not final_prompt: # Tạo prompt mặc định nếu chưa có
        intent_list_str = ", ".join([i for i in VALID_INTENTS if i not in ['unknown', 'error']])
        final_prompt = f"""Phân loại ý định chính của tin nhắn tiếng Việt sau đây vào MỘT trong các loại sau: [{intent_list_str}].
Tin nhắn: "{text}"
Chỉ trả về DUY NHẤT nhãn ý định (viết thường, tiếng Anh, không dấu, không giải thích). Ví dụ: price_query"""


    # --- Gọi Hàm Gọi API Tập Trung ---
    # Truyền persona_id (có thể là None) để call_generative_model dùng đúng model/config
    response_text, status = call_generative_model(prompt=final_prompt, persona_id=persona_id)

    # --- Xử lý kết quả ---
    if status == 'success' and response_text:
        try:
            raw_intent = response_text.strip().lower().replace('.', '').replace(':', '').replace('"', '').replace("'", "")
            # Tìm intent hợp lệ trong kết quả trả về
            found_valid_intent = 'other' # Mặc định
            # Ưu tiên khớp chính xác
            if raw_intent in VALID_INTENTS:
                 found_valid_intent = raw_intent
            else: # Nếu không khớp chính xác, thử tìm chứa trong chuỗi (ít tin cậy hơn)
                 best_match_len = 0
                 for valid_intent in VALID_INTENTS:
                      if valid_intent not in ['other', 'unknown', 'error', 'start'] and valid_intent in raw_intent:
                           # Ưu tiên match dài hơn nếu có (vd: product_info_query vs info_query)
                           if len(valid_intent) > best_match_len:
                                best_match_len = len(valid_intent)
                                found_valid_intent = valid_intent

            detected_intent = found_valid_intent # Gán kết quả cuối cùng
            print(f"DEBUG (detect_intent): Raw='{raw_intent}', Parsed='{detected_intent}'")

        except Exception as parse_err:
            print(f"ERROR (detect_intent): Parsing intent response failed: {parse_err}")
            detected_intent = 'error'
    elif status == 'error_ai_empty':
         detected_intent = 'other' # Nếu AI trả rỗng, coi là other
         print(f"WARN (detect_intent): AI returned empty, classifying as 'other'.")
    else: # Các lỗi khác từ call_generative_model (blocked, rate_limited, exception)
        detected_intent = 'error'
        print(f"ERROR (detect_intent): Failed to get classification from AI. Status: {status}")

    print(f"DEBUG (detect_intent): Final detected intent: '{detected_intent}'")
    return detected_intent


# === HÀM ĐỀ XUẤT LUẬT (ĐÃ REFACTOR ĐỂ DÙNG call_generative_model) ===
def suggest_rule_from_interaction(interaction_data: dict, persona_id: str) -> tuple[str | None, str | None, str | None, str | None]:
    """
    Sử dụng AI để phân tích tương tác và đề xuất keywords, category, template_ref, template_text.
    Sử dụng call_generative_model (có retry).
    """
    task_type = 'suggest_rule'
    print(f"DEBUG (suggest_rule): Bắt đầu. PersonaID='{persona_id}', Task='{task_type}'")
    suggested_keywords = None; suggested_category = None
    suggested_template_ref = None; suggested_template = None
    status = "error_ai_suggestion_unknown" # Status nội bộ của hàm này

    if not interaction_data or not interaction_data.get('received_text') or not interaction_data.get('sent_text'):
        print("WARN (suggest_rule): Missing received_text or sent_text in interaction_data.")
        return None, None, None, None

    # --- 1. Lấy thông tin Persona và Prompt Template ---
    persona = None; template_content = None
    try:
        persona = db.get_persona_details(persona_id) if db else None
        template_content = db.get_prompt_template_by_task(task_type) if db else None
    except Exception as db_err:
        print(f"LỖI (suggest_rule): DB error fetching Persona/Template: {db_err}")
        return None, None, None, None # Lỗi thì trả về None hết
    if not persona: print(f"WARN (suggest_rule): Persona '{persona_id}' not found. Using default prompt guidance."); persona = {} # Dùng dict rỗng thay vì None
    if not template_content:
        print(f"LỖI (suggest_rule): Prompt Template for task '{task_type}' not found.")
        return None, None, None, None

    # --- 2. Render Prompt cuối cùng ---
    final_prompt = ""
    try:
        # Chuẩn bị context để render, thêm list category hợp lệ
        jinja_env = Environment(); jinja_template = jinja_env.from_string(template_content)
        valid_categories_for_prompt = [c for c in VALID_INTENTS if c not in ['unknown', 'error', 'start', 'simulated_turn', 'any']] # Loại bỏ các intent không nên làm category
        render_context = {
            "base_prompt": persona.get('base_prompt', ''),
            "valid_categories_list": valid_categories_for_prompt,
            **interaction_data
        }
        final_prompt = jinja_template.render(render_context)
        # print(f"DEBUG (suggest_rule): Final Prompt (first 500 chars):\n{final_prompt[:500]}...")
    except Exception as render_err:
        print(f"LỖI (suggest_rule): Render prompt template failed: {render_err}")
        return None, None, None, None

    # --- 3. Gọi Hàm Gọi API Tập Trung ---
    response_text, call_status = call_generative_model(prompt=final_prompt, persona_id=persona_id)

    # --- 4. Xử lý và Parse Kết quả ---
    if call_status == 'success' and response_text:
        print(f"DEBUG (suggest_rule): AI Raw Response Text:\n---\n{response_text}\n---")
        try:
            # Hàm helper để làm sạch text trích xuất
            def clean_extracted_text(text):
                if text:
                    text = text.split("Category:")[0].split("Template Ref:")[0].split("Template Text:")[0]
                    text = re.sub(r'^[\s*-]+|[\s*-]+$', '', text, flags=re.MULTILINE).strip()
                    return text if text else None
                return None

            # Parse bằng regex (giữ nguyên logic parse cũ)
            kw_match = re.search(r"^Keywords:(.*?)(\nCategory:|\nTemplate Ref:|\nTemplate Text:|\Z)", response_text, re.I | re.M | re.S)
            cat_match = re.search(r"^Category:(.*?)(\nTemplate Ref:|\nTemplate Text:|\Z)", response_text, re.I | re.M | re.S)
            ref_match = re.search(r"^Template Ref:(.*?)(\nTemplate Text:|\Z)", response_text, re.I | re.M | re.S)
            tpl_match = re.search(r"^Template Text:(.*)", response_text, re.I | re.M | re.S)

            suggested_keywords = clean_extracted_text(kw_match.group(1) if kw_match else None)
            suggested_category = clean_extracted_text(cat_match.group(1) if cat_match else None)
            suggested_template_ref = clean_extracted_text(ref_match.group(1) if ref_match else None)
            suggested_template = clean_extracted_text(tpl_match.group(1) if tpl_match else None)

            # Xử lý trường hợp "Cannot generalize"
            if suggested_template and "cannot generalize" in suggested_template.lower():
                suggested_template = None
                print("INFO (suggest_rule): AI indicated template cannot be generalized.")

            # Kiểm tra xem có lấy được ít nhất keywords hoặc template không
            if suggested_keywords or suggested_template:
                status = "success_ai_suggestion"
                print(f"DEBUG (suggest_rule): Parsed OK - KW: {suggested_keywords}, Cat: {suggested_category}, Ref: {suggested_template_ref}, Txt: {str(suggested_template)[:50]}...")
            else:
                status = "error_ai_suggestion_parsing"
                print("ERROR (suggest_rule): Failed to parse keywords or template from AI response.")
                # Reset hết nếu không parse được gì
                suggested_keywords = suggested_category = suggested_template_ref = suggested_template = None

        except Exception as parse_err:
            status = "error_ai_suggestion_parsing";
            print(f"ERROR (suggest_rule): Exception during parsing AI response: {parse_err}")
            suggested_keywords = suggested_category = suggested_template_ref = suggested_template = None

    elif call_status != 'success': # Xử lý các lỗi từ call_generative_model
         status = f"error_ai_suggestion_{call_status}" # Ghi lại lỗi gốc
         print(f"ERROR (suggest_rule): AI call failed with status: {call_status}. Response text (if any): {response_text}")
         # Đảm bảo trả về None hết
         suggested_keywords = suggested_category = suggested_template_ref = suggested_template = None

    print(f"INFO (suggest_rule): Suggestion generation completed with internal status: {status}")
    # Trả về 4 giá trị
    return suggested_keywords, suggested_category, suggested_template_ref, suggested_template


# === CÁC HÀM KHÁC NẾU CÓ ===
# Ví dụ: Hàm lấy template variations đã có sẵn trong database.py, không cần ở đây
# def get_template_variations(...):
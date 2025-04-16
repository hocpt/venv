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
__current_configured_key_id = None
__last_configure_time = None
# --- Helper Functions (Should remain mostly unchanged) ---
def _get_active_key_and_configure(provider: str = 'google_gemini') -> int | None:
    """
    Lấy một API key đang active, chưa bị rate limit từ DB, cấu hình genai và trả về key_id.
    Sử dụng chiến lược xoay vòng đơn giản dựa trên last_used_at.
    """
    global __current_configured_key_id, __last_configure_time
    if not db:
        print("ERROR (get_active_key): DB module not available.")
        return None

    print(f"DEBUG (get_active_key): Finding active key for provider '{provider}'...")
    try:
        # Hàm DB trả về list dict: [{'key_id': ..., 'decrypted_value': ..., 'last_used_at': ...}, ...]
        # Sắp xếp theo last_used_at ASC NULLS FIRST (ưu tiên key chưa dùng/dùng lâu nhất)
        active_keys = db.get_active_api_keys_by_provider(provider)

        if not active_keys:
            print(f"ERROR (get_active_key): No active and available keys found for provider '{provider}'.")
            return None

        # --- Chọn Key (Ví dụ: Round Robin đơn giản) ---
        # Chọn key đầu tiên trong danh sách (đã được sắp xếp bởi DB)
        selected_key = active_keys[0]
        selected_key_id = selected_key['key_id']
        selected_key_value = selected_key.get('decrypted_value') # Hàm DB phải trả về key đã giải mã

        if not selected_key_value:
             print(f"ERROR (get_active_key): Key ID {selected_key_id} has no decrypted value.")
             return None # Không thể dùng key này

        # --- Cấu hình genai (Vấn đề tiềm ẩn với global config) ---
        # Chỉ configure lại nếu key khác hoặc đã configure lâu rồi (vd > 1 phút) để giảm gọi configure
        now = time.time()
        if selected_key_id != __current_configured_key_id or \
           __last_configure_time is None or \
           (now - __last_configure_time > 60):
            try:
                print(f"DEBUG (get_active_key): Configuring genai with Key ID: {selected_key_id}")
                genai.configure(api_key=selected_key_value)
                __current_configured_key_id = selected_key_id # Lưu lại key ID vừa config
                __last_configure_time = now
                print(f"INFO (get_active_key): Successfully configured API Key ID: {selected_key_id}")
            except Exception as config_err:
                print(f"ERROR (get_active_key): Failed to configure Google AI API Key ID {selected_key_id}: {config_err}")
                return None # Không thể cấu hình -> không thể dùng
        # else:
            # print(f"DEBUG (get_active_key): Reusing already configured Key ID: {selected_key_id}")


        # --- Cập nhật last_used_at cho key vừa chọn ---
        db.update_key_last_used(selected_key_id) # Hàm này cần được tạo trong database.py

        return selected_key_id # Trả về ID của key đã được chọn và cấu hình

    except Exception as e:
        print(f"ERROR (get_active_key): Unexpected error finding/configuring key: {e}")
        print(traceback.format_exc())
        return None

# === HÀM GỌI API GEMINI TỔNG QUÁT (ĐÃ CẬP NHẬT ĐỂ DÙNG KEY XOAY VÒNG) ===
def call_generative_model(prompt: str, persona_id: str | None = None) -> tuple[str | None, str]:
    """
    Hàm gọi API Gemini tổng quát với retry logic và sử dụng key xoay vòng.
    """
    print(f"DEBUG (call_generative_model): PersonaID='{persona_id or 'Default'}', Prompt='{prompt[:100]}...'")
    response_text = None
    status = "error_unknown"
    key_id_used_for_this_call = None # Lưu lại ID key dùng cho lần gọi này

    if not prompt: return None, "error_input_prompt_empty"
    if not db: return None, "error_db_module_missing" # Thêm kiểm tra db

    # --- Lấy cấu hình Model và Generation Config (Như cũ) ---
    model_name = 'models/gemini-1.5-flash-latest' # Nên lấy từ config hoặc persona
    generation_config = genai.types.GenerationConfig(temperature=0.7, max_output_tokens=1000) # Nên lấy từ config hoặc persona
    if persona_id:
        try:
            persona = db.get_persona_details(persona_id)
            if persona:
                model_name = persona.get('model_name') or model_name
                persona_gen_config_obj = _parse_generation_config(persona.get('generation_config'))
                if persona_gen_config_obj: generation_config = persona_gen_config_obj
        except Exception as db_err: print(f"ERROR fetching persona {persona_id}: {db_err}")
    print(f"DEBUG (call_generative_model): Using model: {model_name}, Config: {generation_config}")


    # --- Vòng lặp gọi API với Retry Logic ---
    last_exception = None
    for attempt in range(MAX_RETRIES + 1):
        key_id_used_for_this_attempt = None # Key dùng cho lần thử này
        try:
            # --- LẤY VÀ CẤU HÌNH KEY TRƯỚC MỖI LẦN THỬ ---
            # (Có thể tối ưu chỉ lấy key 1 lần ngoài vòng lặp nếu không cần xoay vòng quá nhanh)
            key_id_used_for_this_attempt = _get_active_key_and_configure('google_gemini')
            if not key_id_used_for_this_attempt:
                status = "error_ai_no_active_key"
                print(f"ERROR ({status}): Không có API key khả dụng để thực hiện yêu cầu.")
                break # Không có key thì không thử lại được nữa

            key_id_used_for_this_call = key_id_used_for_this_attempt # Lưu lại key ID nếu gọi thành công

            # Khởi tạo model và gọi API
            model = genai.GenerativeModel(model_name)
            print(f"DEBUG (call_generative_model): Attempt {attempt + 1}/{MAX_RETRIES + 1} using KeyID {key_id_used_for_this_call}...")
            response = model.generate_content(prompt, generation_config=generation_config)

            # --- Xử lý Response thành công (như cũ) ---
            response_text, status = None, "error_unknown"
            if response.parts:
                try:
                    response_text = response.text.strip(); status = 'success' if response_text else 'error_ai_empty'
                except Exception as e_text: status = "error_ai_text_access"; print(f"ERROR access text: {e_text}")
            elif hasattr(response, 'prompt_feedback') and response.prompt_feedback.block_reason:
                status = "error_ai_blocked"; response_text = f"Blocked: {response.prompt_feedback.block_reason}"; print(f"WARN: Blocked.")
                break # Thoát retry
            else:
                status = "error_ai_invalid_response"; print(f"WARN: Invalid response.")
                break # Thoát retry

            # Thoát nếu thành công hoặc gặp lỗi không retry
            if status == 'success' or status == 'error_ai_empty' or status == 'error_ai_blocked' or status == 'error_ai_invalid_response':
                break

        except api_core_exceptions.ResourceExhausted as e:
            last_exception = e
            print(f"WARN (call_generative_model): Attempt {attempt + 1} with KeyID {key_id_used_for_this_attempt} failed: Resource Exhausted (429).")
            if attempt >= MAX_RETRIES:
                status = "error_ai_rate_limited"; response_text = f"API rate limit hit after {MAX_RETRIES + 1} attempts."
                # <<< ĐÁNH DẤU KEY BỊ RATE LIMIT >>>
                if key_id_used_for_this_attempt:
                     suggested_delay_seconds = 60 # Mặc định khóa 60s nếu không có gợi ý
                     # Cố gắng lấy retry_delay từ metadata lỗi
                     # Cách truy cập metadata có thể thay đổi - cần kiểm tra thực tế
                     try:
                         # Thử truy cập theo cấu trúc đã thấy trong log
                         metadata_dict = dict(getattr(e, 'metadata', []))
                         retry_info = metadata_dict.get('google.rpc.retryinfo-bin') # Hoặc tên tương tự
                         if retry_info:
                              # Cần giải mã protobuf hoặc tìm cách parse khác
                              # Tạm thời dùng giá trị mặc định hoặc giá trị cứng nếu thấy trong log lỗi
                              # Ví dụ log thấy "seconds: 32", ta dùng 32 + buffer
                              delay_match = re.search(r'seconds:\s*(\d+)', str(e))
                              if delay_match:
                                   suggested_delay_seconds = int(delay_match.group(1)) + random.randint(5, 15) # Thêm buffer
                         print(f"DEBUG: Rate limit hit. Suggested/Calculated delay: {suggested_delay_seconds}s")
                     except Exception as ex_parse:
                         print(f"WARN: Could not parse suggested retry delay: {ex_parse}")

                     expiry_time = datetime.now(timezone.utc) + timedelta(seconds=suggested_delay_seconds)
                     db.set_key_rate_limit_expiry(key_id_used_for_this_attempt, expiry_time)
                     print(f"INFO: Marked KeyID {key_id_used_for_this_attempt} as rate limited until {expiry_time.isoformat()}")
                # <<< HẾT PHẦN ĐÁNH DẤU >>>
                break # Thoát vòng lặp

            # Tính toán thời gian chờ (như cũ, dùng gợi ý nếu có)
            delay = INITIAL_BACKOFF_SECONDS * (BACKOFF_FACTOR ** attempt) + random.uniform(0, MAX_JITTER_SECONDS)
            suggested_delay = None
            try: # Thử lấy gợi ý từ exception (cách này có thể không chính xác)
                delay_match = re.search(r'seconds:\s*(\d+)', str(e))
                if delay_match: suggested_delay = float(delay_match.group(1))
            except: pass
            if suggested_delay is not None and suggested_delay > 0:
                delay = suggested_delay + random.uniform(0, MAX_JITTER_SECONDS)
                print(f"INFO (call_generative_model): Using API suggested retry delay.")
            delay = min(delay, MAX_RETRY_DELAY_SECONDS)
            print(f"INFO (call_generative_model): Retrying in {delay:.2f} seconds...")
            time.sleep(delay)
            # continue vòng lặp

        except Exception as e: # Lỗi không mong muốn khác
            print(f"ERROR (call_generative_model): Attempt {attempt + 1} failed: {type(e).__name__} - {e}")
            last_exception = e; status = "error_ai_exception"; response_text = f"Unexpected error: {e}"
            break # Thoát vòng lặp

    # --- Kết thúc vòng lặp retry ---
    print(f"INFO (call_generative_model): Call completed using KeyID {key_id_used_for_this_call}. Final Status: {status}")
    return response_text, status


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
    # ... (code hàm này giữ nguyên) ...
    if not config_str_or_dict: return None
    config_dict = None
    if isinstance(config_str_or_dict, str):
        try: config_dict = json.loads(config_str_or_dict)
        except json.JSONDecodeError: return None
    elif isinstance(config_str_or_dict, dict): config_dict = config_str_or_dict
    else: return None
    if config_dict and isinstance(config_dict, dict):
        try:
            # Lấy các key hợp lệ cho GenerationConfig
            valid_keys = {'temperature', 'top_p', 'top_k', 'candidate_count', 'max_output_tokens', 'stop_sequences'}
            valid_args = {k: v for k, v in config_dict.items() if k in valid_keys}
            if valid_args: return genai.types.GenerationConfig(**valid_args)
            else: return None
        except Exception as e: print(f"WARN: Error creating GenConfig: {e}"); return None
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
    Tạo câu trả lời, dùng call_generative_model (đã có retry) và xử lý fallback.
    """
    # ... (Code lấy template, render prompt như cũ) ...
    persona = db.get_persona_details(persona_id) if db else None
    template_content = db.get_prompt_template_by_task('generate_reply') if db else None
    # ... (xử lý lỗi nếu không có persona/template) ...
    if not persona: return None, "error_ai_persona_not_found"
    if not template_content: return None, "error_ai_prompt_template_not_found"
    # ... (render final_prompt) ...
    final_prompt = "" # Placeholder - Cần code render đúng
    try:
        jinja_env = Environment(); jinja_template = jinja_env.from_string(template_content)
        render_context = {"base_prompt": persona.get('base_prompt', ''), **prompt_data}
        final_prompt = jinja_template.render(render_context)
    except Exception as render_err: return None, "error_ai_prompt_render_failed"

    # Gọi hàm call_generative_model
    generated_text, call_status = call_generative_model(prompt=final_prompt, persona_id=persona_id)

    # Xử lý kết quả và fallback (như cũ)
    processed_reply = generated_text
    final_status = call_status # Bắt đầu với status từ API call

    if final_status == 'success' or final_status == 'error_ai_empty':
        if not processed_reply: final_status = "error_ai_empty"
        else:
            # ... (Thay thế ngày tháng) ...
            try:
                server_tz = _get_configured_timezone()
                now = datetime.now(server_tz)
                temp_reply = processed_reply
                temp_reply = temp_reply.replace("[Ngày hôm nay]", now.strftime("%d"))
                temp_reply = temp_reply.replace("[Tháng]", now.strftime("%m"))
                temp_reply = temp_reply.replace("[Năm]", now.strftime("%Y"))
                if temp_reply != processed_reply: processed_reply = temp_reply
            except Exception as date_err: print(f"WARN (generate_reply): Date replace error: {date_err}")

            # ... (Kiểm tra unhelpful và fallback) ...
            is_unhelpful = False
            unhelpful_patterns = ["tôi không biết", "tôi không chắc", "tôi không có thông tin", "tôi không thể trả lời", "nằm ngoài phạm vi"]
            if any(pattern in processed_reply.lower() for pattern in unhelpful_patterns) or re.search(r'\[.*?\]', processed_reply):
                is_unhelpful = True
                if processed_reply: print(f"WARN: AI response unhelpful: '{processed_reply[:100]}...'")

            if is_unhelpful:
                # ... (Logic tìm fallback_ref như cũ) ...
                fallback_ref = persona.get('fallback_template_ref')
                if not fallback_ref: # Logic fallback mặc định
                    account_goal = prompt_data.get('account_goal', 'default')
                    if account_goal == 'make_friend': fallback_ref = 'fallback_make_friend'
                    elif account_goal == 'product_sales': fallback_ref = 'fallback_product_sales'
                    else: fallback_ref = 'fallback_generic'

                variations = db.get_template_variations(fallback_ref) if db else None
                fallback_reply = None
                if variations: fallback_reply = random.choice(variations).get('variation_text')

                if fallback_reply:
                    processed_reply = fallback_reply; final_status = "success_fallback_template"
                else:
                    final_status = "error_ai_unhelpful_no_fallback"; processed_reply = None
            else:
                 final_status = "success_ai" # Nếu không unhelpful, giữ lại status success

    elif final_status != 'success': # Lỗi từ call_generative_model
         processed_reply = None

    print(f"DEBUG (generate_reply): Returning status: {final_status}, text: '{str(processed_reply)[:100]}...'")
    return processed_reply, final_status


def generate_reply_with_ai(prompt_data: dict, persona_id: str) -> tuple[str | None, str]:
    """
    Tạo câu trả lời, dùng call_generative_model (đã có retry) và xử lý fallback.
    """
    # ... (Code lấy template, render prompt như cũ) ...
    persona = db.get_persona_details(persona_id) if db else None
    template_content = db.get_prompt_template_by_task('generate_reply') if db else None
    # ... (xử lý lỗi nếu không có persona/template) ...
    if not persona: return None, "error_ai_persona_not_found"
    if not template_content: return None, "error_ai_prompt_template_not_found"
    # ... (render final_prompt) ...
    final_prompt = "" # Placeholder - Cần code render đúng
    try:
        jinja_env = Environment(); jinja_template = jinja_env.from_string(template_content)
        render_context = {"base_prompt": persona.get('base_prompt', ''), **prompt_data}
        final_prompt = jinja_template.render(render_context)
    except Exception as render_err: return None, "error_ai_prompt_render_failed"

    # Gọi hàm call_generative_model
    generated_text, call_status = call_generative_model(prompt=final_prompt, persona_id=persona_id)

    # Xử lý kết quả và fallback (như cũ)
    processed_reply = generated_text
    final_status = call_status # Bắt đầu với status từ API call

    if final_status == 'success' or final_status == 'error_ai_empty':
        if not processed_reply: final_status = "error_ai_empty"
        else:
            # ... (Thay thế ngày tháng) ...
            try:
                server_tz = _get_configured_timezone()
                now = datetime.now(server_tz)
                temp_reply = processed_reply
                temp_reply = temp_reply.replace("[Ngày hôm nay]", now.strftime("%d"))
                temp_reply = temp_reply.replace("[Tháng]", now.strftime("%m"))
                temp_reply = temp_reply.replace("[Năm]", now.strftime("%Y"))
                if temp_reply != processed_reply: processed_reply = temp_reply
            except Exception as date_err: print(f"WARN (generate_reply): Date replace error: {date_err}")

            # ... (Kiểm tra unhelpful và fallback) ...
            is_unhelpful = False
            unhelpful_patterns = ["tôi không biết", "tôi không chắc", "tôi không có thông tin", "tôi không thể trả lời", "nằm ngoài phạm vi"]
            if any(pattern in processed_reply.lower() for pattern in unhelpful_patterns) or re.search(r'\[.*?\]', processed_reply):
                is_unhelpful = True
                if processed_reply: print(f"WARN: AI response unhelpful: '{processed_reply[:100]}...'")

            if is_unhelpful:
                # ... (Logic tìm fallback_ref như cũ) ...
                fallback_ref = persona.get('fallback_template_ref')
                if not fallback_ref: # Logic fallback mặc định
                    account_goal = prompt_data.get('account_goal', 'default')
                    if account_goal == 'make_friend': fallback_ref = 'fallback_make_friend'
                    elif account_goal == 'product_sales': fallback_ref = 'fallback_product_sales'
                    else: fallback_ref = 'fallback_generic'

                variations = db.get_template_variations(fallback_ref) if db else None
                fallback_reply = None
                if variations: fallback_reply = random.choice(variations).get('variation_text')

                if fallback_reply:
                    processed_reply = fallback_reply; final_status = "success_fallback_template"
                else:
                    final_status = "error_ai_unhelpful_no_fallback"; processed_reply = None
            else:
                 final_status = "success_ai" # Nếu không unhelpful, giữ lại status success

    elif final_status != 'success': # Lỗi từ call_generative_model
         processed_reply = None

    print(f"DEBUG (generate_reply): Returning status: {final_status}, text: '{str(processed_reply)[:100]}...'")
    return processed_reply, final_status
# === HÀM PHÁT HIỆN Ý ĐỊNH (ĐÃ REFACTOR ĐỂ DÙNG call_generative_model) ===

# === CÁC HÀM KHÁC NẾU CÓ ===
# Ví dụ: Hàm lấy template variations đã có sẵn trong database.py, không cần ở đây
# def get_template_variations(...):
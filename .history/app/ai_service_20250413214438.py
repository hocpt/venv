# app/ai_service.py
import os
import google.generativeai as genai
from flask import current_app # Import current_app để truy cập config
import re
import traceback
import random
from datetime import datetime

import psycopg2 # <<< Đảm bảo có import này
from . import database as db
import json
from jinja2 import Environment, Template
import time # <<< Thêm import time để dùng sleep
from google.api_core import exceptions as api_core_exceptions
# --- Constants for Retry Logic (Consider moving to config.py later) ---
MAX_RETRIES = 3 # Số lần thử lại tối đa (tổng cộng sẽ thử 1 + 3 = 4 lần)
INITIAL_BACKOFF_SECONDS = 5 # Thời gian chờ ban đầu (giây)
BACKOFF_FACTOR = 2 # Hệ số nhân cho thời gian chờ (tăng gấp đôi mỗi lần)
MAX_JITTER_SECONDS = 1.5 # Thời gian ngẫu nhiên cộng thêm để tránh retry đồng loạt
# --- Import Database ---
try:
    # Giả định database.py cùng cấp với __init__.py trong package 'app'
    from . import database as db
except ImportError:
    # Fallback nếu cấu trúc khác hoặc chạy riêng lẻ (ít xảy ra)
    import database as db
    print("WARNING (ai_service): Using fallback database import.")

# --- DANH SÁCH INTENT ĐÃ ĐỊNH NGHĨA ---
VALID_INTENTS = [
    'greeting', 'price_query', 'shipping_query', 'product_info_query',
    'compliment', 'complaint', 'connection_request', 'spam',
    'positive_generic', 'negative_generic', 'other', 'unknown', 'error'
]
__gemini_configured = False
# --- Hàm lấy API Key ---
def _get_api_key():
    """Hàm nội bộ để lấy API key từ config của Flask app."""
    try:
        key = current_app.config.get('GOOGLE_API_KEY')
        if not key:
            print("CẢNH BÁO (ai_service): GOOGLE_API_KEY không có trong app.config.")
        return key
    except RuntimeError:
        print(f"LỖI (ai_service): Không thể truy cập app context để lấy API key.")
        return None
    except Exception as e:
        print(f"LỖI (ai_service): Lỗi không xác định khi lấy API key: {e}")
        return None

# --- Hàm Cấu hình Gemini ---
__gemini_configured = False
def configure_gemini_if_needed():
    """Cấu hình API key cho thư viện Gemini nếu chưa làm."""
    global __gemini_configured
    if __gemini_configured:
        return True
    api_key = _get_api_key()
    if api_key:
        try:
            genai.configure(api_key=api_key)
            print("INFO (ai_service): Đã cấu hình Google AI API Key thành công.")
            __gemini_configured = True
            return True
        except Exception as config_err:
            print(f"LỖI (ai_service): Không thể cấu hình Google AI API Key: {config_err}")
            return False
    else:
        return False

# === Thêm hàm này vào backup/app/ai_service.py ===

def call_generative_model(prompt: str, persona_id: str | None = None) -> tuple[str | None, str]:
    """
    Hàm gọi API Gemini tổng quát với một prompt và tùy chọn persona.

    Args:
        prompt: Chuỗi prompt đầy đủ cần gửi cho AI.
        persona_id: ID của Persona (tùy chọn) để lấy model và generation config.

    Returns:
        Tuple: (response_text: str | None, status: str)
               response_text là nội dung text trả về từ AI hoặc None nếu lỗi.
               status là chuỗi mô tả kết quả ('success', 'error_blocked', 'error_empty', 'error_exception', etc.)
    """
    print(f"DEBUG (call_generative_model): PersonaID='{persona_id or 'Default'}', Prompt='{prompt[:100]}...'")
    response_text = None
    status = "error_unknown"

    if not configure_gemini_if_needed():
        return None, "error_ai_no_key_or_config_failed"
    if not prompt:
        return None, "error_input_prompt_empty"

    # --- Lấy cấu hình từ Persona hoặc dùng Default ---
    model_name = current_app.config.get('GEMINI_DEFAULT_MODEL', 'models/gemini-1.5-flash-latest')
    # Tạo config mặc định cơ bản (có thể lấy từ app config nếu muốn)
    default_gen_config = genai.types.GenerationConfig(
        temperature=current_app.config.get('GEMINI_REPLY_TEMPERATURE', 0.7),
        max_output_tokens=current_app.config.get('GEMINI_REPLY_MAX_TOKENS', 1000)
    )
    generation_config = default_gen_config
    persona_config_used = False

    if persona_id:
        try:
            persona = db.get_persona_details(persona_id)
            if persona:
                model_name = persona.get('model_name') or model_name
                persona_gen_config_obj = _parse_generation_config(persona.get('generation_config'))
                if persona_gen_config_obj:
                     generation_config = persona_gen_config_obj
                     persona_config_used = True
                print(f"DEBUG (call_generative_model): Using config from Persona '{persona_id}'. Model: {model_name}, Custom GenConfig: {persona_config_used}")
            else:
                print(f"WARNING (call_generative_model): Persona ID '{persona_id}' not found. Using default config.")
        except Exception as db_err:
             print(f"ERROR (call_generative_model): DB error fetching persona '{persona_id}': {db_err}. Using default config.")

    if not persona_config_used:
         print(f"DEBUG (call_generative_model): Using default config. Model: {model_name}")


    # --- === VÒNG LẶP GỌI API VỚI RETRY LOGIC === ---
    last_exception = None # Lưu lỗi cuối cùng nếu tất cả retry thất bại

    for attempt in range(MAX_RETRIES + 1): # Thử lần đầu (attempt 0) + MAX_RETRIES lần thử lại
        try:
            # Khởi tạo model trong vòng lặp có thể cần thiết nếu configure thay đổi key (dù hiện tại chưa dùng)
            model = genai.GenerativeModel(model_name)

            print(f"DEBUG (call_generative_model): Attempt {attempt + 1}/{MAX_RETRIES + 1} calling API...")
            response = model.generate_content(prompt, generation_config=generation_config)
            # print(f"DEBUG (call_generative_model): Attempt {attempt + 1} - Received response.") # Có thể bỏ log này

            # --- Xử lý Response thành công (Logic giữ nguyên) ---
            response_text = None # Reset trước mỗi lần xử lý response
            status = "error_unknown" # Reset status
            if response.parts:
                try:
                    response_text = response.text.strip()
                    if response_text:
                         status = 'success'
                         # print(f"DEBUG (call_generative_model): Success! Response text (first 500): {response_text[:500]}...")
                    else:
                         status = 'error_ai_empty' # AI trả về nhưng text rỗng
                         print(f"WARNING (call_generative_model): Attempt {attempt + 1} received empty text response.")
                except (ValueError, AttributeError) as e_text:
                    print(f"WARNING/ERROR (call_generative_model): Attempt {attempt + 1} - Cannot access response.text: {e_text}")
                    status = "error_ai_no_text_value"
                except Exception as e_other_text:
                    print(f"ERROR (call_generative_model): Attempt {attempt + 1} - Unexpected error accessing response.text: {e_other_text}")
                    status = "error_ai_text_access"

            # Xử lý trường hợp bị chặn (không phải lỗi để retry)
            elif hasattr(response, 'prompt_feedback') and response.prompt_feedback.block_reason:
                block_reason = response.prompt_feedback.block_reason
                print(f"WARNING (call_generative_model): Attempt {attempt + 1} - Gemini prompt blocked. Reason: {block_reason}")
                status = "error_ai_blocked"
                response_text = f"Blocked by API: {block_reason}" # Trả về lý do chặn
                break # <<< Thoát vòng lặp retry ngay lập tức nếu bị chặn

            # Xử lý trường hợp response không hợp lệ khác
            else:
                print(f"WARNING (call_generative_model): Attempt {attempt + 1} - Invalid or empty AI response structure.")
                status = "error_ai_invalid_response"
                # Có thể quyết định retry lỗi này hoặc không. Tạm thời không retry.
                break # <<< Thoát vòng lặp nếu response không rõ ràng


            # Nếu thành công (có text hoặc empty) hoặc gặp lỗi không retry (blocked, invalid), thoát vòng lặp
            if status == 'success' or status == 'error_ai_empty' or status == 'error_ai_blocked' or status == 'error_ai_invalid_response':
                break # <<< Thoát vòng lặp khi có kết quả cuối cùng (thành công hoặc lỗi không retry)

        # --- === XỬ LÝ LỖI CÓ THỂ RETRY (429) === ---
        except api_core_exceptions.ResourceExhausted as e:
            last_exception = e
            print(f"WARNING (call_generative_model): Attempt {attempt + 1} failed: Resource Exhausted (429).")
            if attempt >= MAX_RETRIES:
                print(f"ERROR (call_generative_model): Max retries ({MAX_RETRIES}) reached for Resource Exhausted.")
                status = "error_ai_rate_limited" # Status lỗi cuối cùng
                response_text = f"API rate limit exceeded after {MAX_RETRIES + 1} attempts."
                break # Thoát vòng lặp

            # Tính toán thời gian chờ
            delay = INITIAL_BACKOFF_SECONDS * (BACKOFF_FACTOR ** attempt) + random.uniform(0, MAX_JITTER_SECONDS)

            # Kiểm tra xem API có gợi ý thời gian chờ không (cần kiểm tra cấu trúc exception 'e')
            suggested_delay = None
            # Thử truy cập metadata nếu có (cách truy cập có thể thay đổi tùy phiên bản thư viện)
            if hasattr(e, 'metadata') and isinstance(e.metadata, tuple):
                for item in e.metadata:
                     if isinstance(item, tuple) and len(item) == 2 and item[0] == 'retry-delay':
                          # Metadata có thể chứa tuple ('retry-delay', 'seconds: 57') hoặc tương tự
                          # Cần parse giá trị này cẩn thận
                          try:
                               delay_str = item[1].split(':')[-1].strip()
                               suggested_delay = float(delay_str)
                               print(f"DEBUG: API suggested retry delay: {suggested_delay} seconds.")
                          except (IndexError, ValueError, TypeError):
                               print(f"DEBUG: Could not parse suggested retry delay from metadata: {item}")
                               suggested_delay = None
                          break

            if suggested_delay is not None and suggested_delay > 0:
                delay = suggested_delay + random.uniform(0, MAX_JITTER_SECONDS) # Dùng gợi ý + jitter
                print(f"INFO (call_generative_model): Using API suggested retry delay.")

            # Đảm bảo delay không quá lớn (ví dụ: tối đa 60 giây)
            delay = min(delay, 60.0)

            print(f"INFO (call_generative_model): Retrying in {delay:.2f} seconds...")
            time.sleep(delay)
            # Vòng lặp sẽ tự động tiếp tục với attempt tiếp theo

        # --- Xử lý các lỗi Exception khác (không retry) ---
        except Exception as e:
            print(f"ERROR (call_generative_model): Attempt {attempt + 1} failed with unexpected exception: {type(e).__name__} - {e}")
            print(traceback.format_exc())
            last_exception = e
            status = "error_ai_exception" # Lỗi không mong muốn
            response_text = f"Unexpected error: {e}"
            break # Thoát vòng lặp retry ngay lập tức

    # --- Kết thúc vòng lặp retry ---
    print(f"INFO (call_generative_model): Call completed with final status: {status}")
    # Trả về response_text và status cuối cùng
    return response_text, status

# ... (Các hàm khác trong ai_service.py) ...
# === HÀM TẠO TRẢ LỜI (ĐÃ REFACTOR ĐỂ DÙNG call_generative_model) ===
def generate_reply_with_ai(prompt_data: dict, persona_id: str) -> tuple[str | None, str]:
    """
    Tạo câu trả lời bằng Gemini API, sử dụng Persona và Prompt Template,
    đồng thời tận dụng logic retry từ call_generative_model.

    Args:
        prompt_data: Dictionary chứa dữ liệu ngữ cảnh để render prompt.
        persona_id: ID của AI Persona cần sử dụng.

    Returns:
        Tuple (reply_text: str hoặc None nếu lỗi, status: str)
    """
    task_type = 'generate_reply' # Task type để lấy prompt template
    print(f"DEBUG (generate_reply): Bắt đầu. PersonaID='{persona_id}', Task='{task_type}'")
    final_reply_text = None
    status = "error_ai_unknown" # Status mặc định

    # --- 1. Lấy thông tin Persona và Prompt Template ---
    persona = None
    template_content = None
    try:
        persona = db.get_persona_details(persona_id)
        template_content = db.get_prompt_template_by_task(task_type)
    except Exception as db_err:
        print(f"LỖI (generate_reply): Không thể lấy Persona/Template từ DB: {db_err}")
        return None, "error_db_ai_config_fetch"

    if not persona:
        print(f"LỖI (generate_reply): Không tìm thấy Persona ID '{persona_id}'.")
        return None, "error_ai_persona_not_found"
    if not template_content:
        # Nếu không có template cho task này, có thể dùng prompt đơn giản hoặc báo lỗi
        print(f"LỖI (generate_reply): Không tìm thấy Prompt Template cho task '{task_type}'.")
        # Thay vì lỗi, thử tạo prompt đơn giản? Hoặc trả về lỗi để rõ ràng hơn?
        # Tạm thời trả về lỗi:
        return None, "error_ai_prompt_template_not_found"
        # Hoặc tạo prompt đơn giản:
        # final_prompt = f"{persona.get('base_prompt', '')}\n\nLịch sử:\n{prompt_data.get('formatted_history','')}\n\nNgười dùng: {prompt_data.get('received_text')}\n\nBạn:"

    # --- 2. Render Prompt cuối cùng (Nếu có template) ---
    final_prompt = ""
    try:
        jinja_env = Environment()
        jinja_template = jinja_env.from_string(template_content)
        render_context = {
            "base_prompt": persona.get('base_prompt', ''),
            **prompt_data # Giải nén các key từ prompt_data
        }
        final_prompt = jinja_template.render(render_context)
        # print(f"DEBUG (generate_reply): Final Prompt (first 500 chars):\n{final_prompt[:500]}...") # Bỏ comment nếu cần debug prompt
    except Exception as render_err:
        print(f"LỖI (generate_reply): Không thể render prompt template: {render_err}")
        return None, "error_ai_prompt_render_failed"

    # --- 3. Gọi Hàm Gọi API Tập Trung (call_generative_model) ---
    # Hàm này đã có sẵn logic retry
    generated_text, status = call_generative_model(
        prompt=final_prompt,
        persona_id=persona_id # Truyền persona_id để call_generative_model lấy config model/gen đúng
    )

    # --- 4. Xử lý hậu kỳ (Nếu gọi API thành công và có text) ---
    # Chỉ xử lý hậu kỳ nếu status là 'success' hoặc 'error_ai_empty' (vẫn cần check unhelpful)
    processed_reply = generated_text # Bắt đầu với text từ call_generative_model

    if status == 'success' or status == 'error_ai_empty': # Bao gồm cả trường hợp AI trả về rỗng nhưng không lỗi
        if not processed_reply: # Xử lý trường hợp empty text
             print(f"DEBUG (generate_reply): AI returned empty text (Status: {status}). Treating as unhelpful.")
             status = "error_ai_empty" # Đảm bảo status là empty
             # Logic fallback sẽ được kích hoạt bên dưới
        else:
             print(f"DEBUG (generate_reply): Text gốc từ AI call: '{processed_reply[:100]}...'")

        # 4.1 Thay thế ngày tháng (Giữ nguyên)
        try:
            now = datetime.now(SCHEDULER_TIMEZONE) # Dùng timezone đã định nghĩa
            temp_reply = processed_reply
            temp_reply = temp_reply.replace("[Ngày hôm nay]", now.strftime("%d"))
            temp_reply = temp_reply.replace("[Tháng]", now.strftime("%m"))
            temp_reply = temp_reply.replace("[Năm]", now.strftime("%Y"))
            if temp_reply != processed_reply:
                print(f"DEBUG (generate_reply): Đã thay thế placeholders ngày tháng.")
                processed_reply = temp_reply
        except Exception as date_err:
            print(f"WARNING (generate_reply): Lỗi thay thế ngày tháng: {date_err}")

        # 4.2 Kiểm tra unhelpful / fallback (Giữ nguyên logic tìm fallback)
        is_unhelpful = False
        unhelpful_patterns = ["tôi không biết", "tôi không chắc", "tôi không có thông tin", "tôi không thể trả lời", "nằm ngoài phạm vi", "không thể giúp", "không đủ khả năng"]
        # Kiểm tra cả khi text rỗng hoặc chứa mẫu không hữu ích hoặc còn placeholder
        if not processed_reply or any(pattern in processed_reply.lower() for pattern in unhelpful_patterns) or re.search(r'\[.*?\]', processed_reply):
            is_unhelpful = True
            if processed_reply: # Chỉ log nếu có text để log
                 print(f"WARNING (generate_reply): AI response unhelpful/placeholder/empty: '{processed_reply[:100]}...'")

        if is_unhelpful:
            fallback_ref = persona.get('fallback_template_ref') # Ưu tiên fallback từ persona
            if not fallback_ref:
                 account_goal = prompt_data.get('account_goal', 'default')
                 if account_goal == 'make_friend': fallback_ref = 'fallback_make_friend'
                 elif account_goal == 'product_sales': fallback_ref = 'fallback_product_sales'
                 else: fallback_ref = 'fallback_generic'

            print(f"DEBUG (generate_reply): Using fallback template ref: {fallback_ref}")
            variations = db.get_template_variations(fallback_ref)
            fallback_reply = None
            if variations: fallback_reply = random.choice(variations).get('variation_text')

            if fallback_reply:
                processed_reply = fallback_reply # Ghi đè bằng template fallback
                status = "success_fallback_template" # Cập nhật status thành công nhờ fallback
                print(f"DEBUG (generate_reply): Đã dùng fallback template: '{processed_reply[:100]}...'")
            else:
                print(f"WARNING (generate_reply): Không tìm thấy fallback template cho ref {fallback_ref}.")
                # Nếu AI không hữu ích VÀ không có fallback -> coi như lỗi
                status = "error_ai_unhelpful_no_fallback"
                processed_reply = None # Không có gì để trả lời
        # else: # Nếu không unhelpful và status là success
             # status giữ nguyên là 'success' từ call_generative_model
             # print(f"DEBUG (generate_reply): Phản hồi AI (đã xử lý) ok.")
             # processed_reply đã có giá trị từ AI

    # Nếu status từ call_generative_model không phải success/empty (vd: blocked, rate_limited, exception)
    # thì processed_reply sẽ là None (hoặc thông báo lỗi từ call_generative_model) và status giữ nguyên lỗi đó
    elif status != 'success':
         processed_reply = None # Đảm bảo không trả về text cũ nếu có lỗi

    final_reply_text = processed_reply
    print(f"DEBUG (generate_reply): Returning text (first 100): '{str(final_reply_text)[:100]}...', status: {status}")
    return final_reply_text, status



def get_template_variations(template_ref: str | None) -> list[dict] | None:
    """
    Lấy tất cả các biến thể text cho một template_ref từ CSDL.

    Args:
        template_ref: Mã tham chiếu của template cần lấy biến thể.

    Returns:
        List các dictionary (ví dụ: [{'variation_text': 'text1'}, ...]),
        hoặc list rỗng [] nếu không có biến thể,
        hoặc None nếu có lỗi CSDL.
    """
    if not template_ref:
        return [] # Trả về list rỗng nếu không có ref

    variations_list = None # Khởi tạo là None để phân biệt lỗi và không có dữ liệu
    conn = db.get_db_connection()
    if not conn:
        return None # Lỗi kết nối -> trả về None

    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        print(f"DEBUG (database.py): Truy vấn các biến thể cho template_ref: {template_ref}")
        cur.execute("""
            SELECT variation_text
            FROM template_variations
            WHERE template_ref = %s;
            """, (template_ref,))
        rows = cur.fetchall() # Lấy tất cả các dòng khớp

        if rows:
            variations_list = [dict(row) for row in rows] # Trả về list các dict
            print(f"DEBUG (database.py): Tìm thấy {len(variations_list)} biến thể cho {template_ref}")
        else:
            print(f"WARNING (database.py): Không tìm thấy biến thể nào cho template_ref {template_ref}")
            variations_list = [] # Trả về list rỗng nếu ref đúng nhưng chưa có biến thể

    except psycopg2.Error as db_err:
        print(f"LỖI (database.py - get_template_variations): Truy vấn thất bại: {db_err}")
        print(traceback.format_exc())
        # variations_list vẫn là None
    except Exception as e:
        print(f"LỖI (database.py - get_template_variations): Lỗi không xác định: {e}")
        print(traceback.format_exc())
        # variations_list vẫn là None
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return variations_list # Trả về list (có thể rỗng) hoặc None nếu lỗi


    """
    Sử dụng AI để phân tích tương tác và đề xuất keywords, template mới.
    Args:
        interaction_data: Dict chứa 'received_text', 'sent_text', 'user_intent', ...
    Returns:
        Tuple: (suggested_keywords: str | None, suggested_template: str | None)
    """
    print(f"DEBUG (suggest_rule): Bắt đầu phân tích tương tác...")
    received_text = interaction_data.get('received_text', '')
    sent_text = interaction_data.get('sent_text', '')
    user_intent = interaction_data.get('user_intent', 'unknown')

    if not received_text or not sent_text:
        print("WARNING (suggest_rule): Thiếu received_text hoặc sent_text.")
        return None, None

    if not configure_gemini_if_needed():
         print("LỖI (suggest_rule): Không thể cấu hình Gemini.")
         return None, None # Không thể chạy nếu thiếu key

    # --- Tạo Prompt cho AI ---
    # Đây là phần quan trọng cần thử nghiệm và tinh chỉnh
    prompt = f"""Analyze the following successful user interaction:
User Intent: {user_intent}
User Said: "{received_text}"
Assistant Replied: "{sent_text}"

Based on this, suggest:
1. Trigger Keywords: Concise, comma-separated keywords from the "User Said" text that likely triggered this type of reply. Focus on the core request/sentiment.
2. Reusable Template: A generalized version of the "Assistant Replied" text. Replace specific details (like names, times, specific numbers if appropriate) with generic placeholders if possible (e.g., [Name], [Time]), but keep the core message and tone. If the reply is very specific and cannot be generalized, say "Cannot generalize".

Format your response exactly like this:
Keywords: <suggested keywords here>
Template Text: <suggested template text here or "Cannot generalize">
"""

    print(f"DEBUG (suggest_rule): Prompt:\n{prompt[:500]}...") # Log một phần prompt

    suggested_keywords = None
    suggested_template = None
    status = "error_ai_suggestion_unknown"

    try:
        # --- Gọi API Gemini ---
        # Có thể dùng model khác hoặc cấu hình riêng cho tác vụ này
        model_name = current_app.config.get('GEMINI_SUGGEST_MODEL', 'models/gemini-1.5-flash-latest')
        model = genai.GenerativeModel(model_name)
        # Có thể điều chỉnh generation_config (vd: temperature thấp hơn để kết quả nhất quán)
        generation_config = genai.types.GenerationConfig(temperature=0.2, max_output_tokens=200)

        response = model.generate_content(prompt, generation_config=generation_config)

        # --- Xử lý kết quả ---
        if response.parts:
            ai_text = response.text.strip()
            print(f"DEBUG (suggest_rule): AI Raw Response:\n{ai_text}")
            # Phân tích text trả về để lấy keywords và template
            keywords_match = re.search(r"Keywords:(.*)", ai_text, re.IGNORECASE | re.DOTALL)
            template_match = re.search(r"Template Text:(.*)", ai_text, re.IGNORECASE | re.DOTALL)

            if keywords_match:
                suggested_keywords = keywords_match.group(1).strip()
                # Xóa luôn chữ "Template Text:" nếu nó nằm trong group 1 của keywords
                suggested_keywords = suggested_keywords.split("Template Text:")[0].strip()

            if template_match:
                suggested_template = template_match.group(1).strip()
                if "cannot generalize" in suggested_template.lower():
                     suggested_template = None # Không tạo template nếu AI nói không tổng quát được
                     print("DEBUG (suggest_rule): AI indicated template cannot be generalized.")


            if suggested_keywords and suggested_template:
                status = "success_ai_suggestion"
                print("INFO (suggest_rule): Phân tích thành công.")
            elif suggested_keywords and not suggested_template:
                 # Trường hợp chỉ có keywords (do template không generalize được)
                 # Tùy chọn: Có thể vẫn lưu keywords? Hoặc coi là không thành công hoàn toàn.
                 status = "warning_ai_suggestion_keywords_only"
                 print("WARNING (suggest_rule): Chỉ có keywords được đề xuất.")
                 # Đặt template là None để không lưu
                 suggested_template = None

            else:
                 status = "error_ai_suggestion_parsing"
                 print("LỖI (suggest_rule): Không thể phân tích keywords/template từ phản hồi AI.")
                 suggested_keywords = None
                 suggested_template = None


        elif hasattr(response, 'prompt_feedback') and response.prompt_feedback.block_reason:
             block_reason = response.prompt_feedback.block_reason
             print(f"CẢNH BÁO (suggest_rule): Gemini bị chặn. Lý do: {block_reason}")
             status = "error_ai_suggestion_blocked"
        else:
             print("CẢNH BÁO (suggest_rule): Phản hồi AI không có nội dung.")
             status = "error_ai_suggestion_empty"

    except Exception as e:
        print(f"LỖI (suggest_rule): Gọi Gemini API hoặc xử lý thất bại: {e}")
        print(traceback.format_exc())
        status = "error_ai_suggestion_call"
        suggested_keywords = None
        suggested_template = None

    print(f"DEBUG (suggest_rule): Status = {status}")
    return suggested_keywords, suggested_template
# === Cập nhật/Hoàn thiện hàm này trong backup/app/ai_service.py ===

# --- Helper function để parse Generation Config ---
def _parse_generation_config(config_str_or_dict) -> genai.types.GenerationConfig | None:
    """ Chuyển đổi chuỗi JSON hoặc dict thành GenerationConfig object. """
    if not config_str_or_dict:
        return None
    config_dict = None
    if isinstance(config_str_or_dict, str):
        try:
            config_dict = json.loads(config_str_or_dict)
        except json.JSONDecodeError:
            print(f"WARNING: generation_config string không phải JSON hợp lệ: {config_str_or_dict[:100]}...")
            return None
    elif isinstance(config_str_or_dict, dict):
        config_dict = config_str_or_dict
    else:
        return None

    if config_dict and isinstance(config_dict, dict):
        try:
            # Chỉ truyền các tham số hợp lệ vào GenerationConfig
            valid_args = {k: v for k, v in config_dict.items() if hasattr(genai.types.GenerationConfig(), k)}
            if valid_args:
                return genai.types.GenerationConfig(**valid_args)
            else:
                return None
        except Exception as e:
            print(f"WARNING: Lỗi khi tạo GenerationConfig từ dict: {e}")
            return None
    return None


# === CÁC HÀM AI CHÍNH ĐÃ ĐƯỢC REFACTOR ===

def generate_reply_with_ai(prompt_data: dict, persona_id: str) -> tuple[str | None, str]:
    """
    Tạo câu trả lời bằng Gemini API, sử dụng Persona và Prompt Template.

    Args:
        prompt_data: Dictionary chứa dữ liệu ngữ cảnh để render prompt, ví dụ:
                     {'received_text': '...', 'formatted_history': '...', 'account_goal': '...'}
        persona_id: ID của AI Persona cần sử dụng (từ bảng ai_personas).

    Returns:
        Tuple (reply_text: str hoặc None nếu lỗi, status: str)
    """
    task_type = 'generate_reply'
    print(f"DEBUG (generate_reply): Bắt đầu. PersonaID='{persona_id}', Task='{task_type}'")
    final_reply_text = None
    status = "error_ai_unknown"

    if not configure_gemini_if_needed():
        return None, "error_ai_no_key_or_config_failed"

    # --- 1. Lấy thông tin Persona và Prompt Template ---
    persona = None
    template_content = None
    try:
        persona = db.get_persona_details(persona_id)
        template_content = db.get_prompt_template_by_task(task_type)
    except Exception as db_err:
        print(f"LỖI (generate_reply): Không thể lấy Persona/Template từ DB: {db_err}")
        return None, "error_db_ai_config_fetch"

    if not persona:
        print(f"LỖI (generate_reply): Không tìm thấy Persona với ID '{persona_id}'.")
        return None, "error_ai_persona_not_found"
    if not template_content:
        print(f"LỖI (generate_reply): Không tìm thấy Prompt Template cho task_type '{task_type}'.")
        return None, "error_ai_prompt_template_not_found"

    # --- 2. Render Prompt cuối cùng ---
    final_prompt = ""
    try:
        jinja_env = Environment()
        jinja_template = jinja_env.from_string(template_content)
        # Tạo context để render, kết hợp base_prompt và dữ liệu từ prompt_data
        render_context = {
            "base_prompt": persona.get('base_prompt', ''),
            **prompt_data # Giải nén các key từ prompt_data vào context
        }
        final_prompt = jinja_template.render(render_context)
        print(f"DEBUG (generate_reply): Final Prompt (first 500 chars):\n{final_prompt[:500]}...")
    except Exception as render_err:
        print(f"LỖI (generate_reply): Không thể render prompt template: {render_err}")
        return None, "error_ai_prompt_render_failed"

    # --- 3. Lấy cấu hình và gọi API ---
    try:
        # Lấy model và config từ persona, hoặc dùng default từ app config
        model_name = persona.get('model_name') or current_app.config.get('GEMINI_REPLY_MODEL', 'models/gemini-1.5-flash-latest')
        # Parse generation_config từ persona (có thể là JSON string hoặc dict từ DB)
        persona_gen_config_obj = _parse_generation_config(persona.get('generation_config'))
        # Tạo config mặc định nếu persona không có hoặc parse lỗi
        default_gen_config = genai.types.GenerationConfig(
            temperature=current_app.config.get('GEMINI_REPLY_TEMPERATURE', 0.7), # Lấy từ app config hoặc default
            max_output_tokens=current_app.config.get('GEMINI_REPLY_MAX_TOKENS', 1000)
        )
        generation_config = persona_gen_config_obj or default_gen_config

        print(f"DEBUG (generate_reply): Using model: {model_name}, Config: {generation_config}")

        model = genai.GenerativeModel(model_name)
        response = model.generate_content(final_prompt, generation_config=generation_config)
        print(f"DEBUG (generate_reply): Received response from API.")

        # --- 4. Xử lý Response từ AI (Tương tự như trước) ---
        generated_text = None
        processed_reply = None
        is_blocked = False
        has_content = False

        # 4.1 Check blocked
        try:
            if not response.parts and hasattr(response, 'prompt_feedback') and response.prompt_feedback.block_reason:
                block_reason = response.prompt_feedback.block_reason
                print(f"CẢNH BÁO (generate_reply): Gemini bị chặn. Lý do: {block_reason}")
                status = "error_ai_blocked"
                is_blocked = True
        except Exception as block_check_err:
             print(f"LỖI (generate_reply): Khi kiểm tra block_reason: {block_check_err}")
             status = "error_ai_response_check_failed"
             is_blocked = True

        # 4.2 Get text if not blocked
        if not is_blocked:
            try:
                generated_text = response.text.strip()
                if generated_text:
                    has_content = True
                    processed_reply = generated_text
                    print(f"DEBUG (generate_reply): Text gốc từ AI: '{processed_reply[:100]}...'")
                else:
                    print(f"CẢNH BÁO (generate_reply): Gemini không trả về text.")
                    status = "error_ai_empty_response"
            except (ValueError, AttributeError) as e:
                print(f"CẢNH BÁO/LỖI (generate_reply): Không lấy được text từ response. Feedback: {getattr(response, 'prompt_feedback', 'N/A')}. Lỗi: {e}")
                status = "error_ai_no_text_content" if isinstance(e, ValueError) else "error_ai_bad_response_structure"

        # --- 5. Xử lý hậu kỳ (Tương tự như trước, có thể cần xem lại logic fallback) ---
        if has_content and processed_reply:
            # 5.1 Thay thế ngày tháng (Giữ nguyên)
            try:
                now = datetime.now()
                temp_reply = processed_reply
                temp_reply = temp_reply.replace("[Ngày hôm nay]", now.strftime("%d"))
                temp_reply = temp_reply.replace("[Tháng]", now.strftime("%m"))
                temp_reply = temp_reply.replace("[Năm]", now.strftime("%Y"))
                if temp_reply != processed_reply:
                    print(f"DEBUG (generate_reply): Đã thay thế placeholders ngày tháng.")
                    processed_reply = temp_reply
            except Exception as date_err:
                print(f"WARNING (generate_reply): Lỗi thay thế ngày tháng: {date_err}")

            # 5.2 Kiểm tra unhelpful / fallback (Xem xét lại logic fallback)
            # Có thể định nghĩa fallback template ref trong persona config?
            is_unhelpful = False
            unhelpful_patterns = ["tôi không biết", "tôi không chắc", "tôi không có thông tin", "tôi không thể trả lời", "nằm ngoài phạm vi"]
            if any(pattern in processed_reply.lower() for pattern in unhelpful_patterns) or re.search(r'\[.*?\]', processed_reply):
                is_unhelpful = True
                print(f"WARNING (generate_reply): AI trả lời không hữu ích/còn placeholder: '{processed_reply[:100]}...'")

            if is_unhelpful:
                # Lấy fallback template ref (ưu tiên từ persona, sau đó từ account_goal, cuối cùng là default)
                fallback_ref = persona.get('fallback_template_ref') # <<< Giả sử có cột này trong ai_personas
                if not fallback_ref:
                     account_goal = prompt_data.get('account_goal', 'default')
                     if account_goal == 'make_friend': fallback_ref = 'fallback_make_friend'
                     elif account_goal == 'product_sales': fallback_ref = 'fallback_product_sales'
                     else: fallback_ref = 'fallback_generic'

                print(f"DEBUG (generate_reply): Using fallback template ref: {fallback_ref}")
                variations = db.get_template_variations(fallback_ref) # Hàm này đã có
                fallback_reply = None
                if variations:
                    fallback_reply = random.choice(variations).get('variation_text')

                if fallback_reply:
                    processed_reply = fallback_reply
                    status = "success_fallback_template"
                    print(f"DEBUG (generate_reply): Đã dùng fallback template: '{processed_reply[:100]}...'")
                else:
                    print(f"WARNING (generate_reply): Không tìm thấy fallback template cho ref {fallback_ref}.")
                    status = "error_ai_unhelpful_no_fallback"
                    processed_reply = None
            else:
                 # Phản hồi AI được coi là ổn
                 status = "success_ai"
                 print(f"DEBUG (generate_reply): Phản hồi AI (đã xử lý) ok: '{processed_reply[:100]}...'")

        # Gán kết quả cuối cùng
        final_reply_text = processed_reply

    except Exception as e:
        print(f"LỖI (generate_reply): Ngoại lệ khi gọi Gemini API hoặc xử lý: {type(e).__name__} - {e}")
        print(traceback.format_exc())
        status = "error_ai_call_exception"
        final_reply_text = None

    return final_reply_text, status

def suggest_rule_from_interaction(interaction_data: dict, persona_id: str) -> tuple[str | None, str | None, str | None, str | None]:
    """
    Sử dụng AI để phân tích tương tác và đề xuất keywords, category, template_ref, template_text mới.

    Args:
        interaction_data: Dict chứa 'received_text', 'sent_text', 'user_intent', ...
        persona_id: ID của AI Persona dùng để thực hiện việc phân tích/đề xuất.

    Returns:
        Tuple: (keywords, category, template_ref, template_text) - Các giá trị có thể là None.
    """
    task_type = 'suggest_rule'
    print(f"DEBUG (suggest_rule): Bắt đầu. PersonaID='{persona_id}', Task='{task_type}'")
    suggested_keywords = None
    suggested_category = None # <<< Thêm biến
    suggested_template_ref = None # <<< Thêm biến
    suggested_template = None
    status = "error_ai_suggestion_unknown"

    # ... (Kiểm tra input, kiểm tra config API như cũ) ...
    if not configure_gemini_if_needed(): return None, None, None, None # Trả về 4 giá trị None

    # --- 1. Lấy thông tin Persona và Prompt Template ---
    # ... (Lấy persona, template_content như cũ, xử lý lỗi nếu không tìm thấy) ...
    persona = db.get_persona_details(persona_id)
    template_content = db.get_prompt_template_by_task(task_type)
    if not persona: persona = {'base_prompt': 'You are an AI analyzing conversations.'} # Fallback
    if not template_content:
        print(f"LỖI (suggest_rule): Không tìm thấy Prompt Template cho task_type '{task_type}'.")
        return None, None, None, None

    # --- 2. Render Prompt cuối cùng ---
    # ... (Render final_prompt như cũ) ...
    final_prompt = ""
    try:
        jinja_env = Environment()
        jinja_template = jinja_env.from_string(template_content)
        render_context = {"base_prompt": persona.get('base_prompt', ''), **interaction_data}
        final_prompt = jinja_template.render(render_context)
        print(f"DEBUG (suggest_rule): Final Prompt (first 500 chars):\n{final_prompt[:500]}...")
    except Exception as render_err:
        print(f"LỖI (suggest_rule): Không thể render prompt template: {render_err}")
        return None, None, None, None


    # --- 3. Lấy cấu hình và gọi API ---
    try:
        # ... (Lấy model_name, generation_config như cũ) ...
        model_name = persona.get('model_name') or current_app.config.get('GEMINI_SUGGEST_MODEL', 'models/gemini-1.5-flash-latest')
        persona_gen_config_obj = _parse_generation_config(persona.get('generation_config'))
        default_gen_config = genai.types.GenerationConfig(temperature=0.2, max_output_tokens=400) # Tăng token output chút
        generation_config = persona_gen_config_obj or default_gen_config

        model = genai.GenerativeModel(model_name)
        print(f"DEBUG (suggest_rule): Calling model '{model_name}'...")
        response = model.generate_content(final_prompt, generation_config=generation_config)
        print(f"DEBUG (suggest_rule): Received response from Gemini.")

        # --- 4. Xử lý Response từ AI ---
        ai_text = ""
        # ... (Kiểm tra response.parts, response.text, block_reason như cũ) ...
        if response.parts:
            try: ai_text = response.text.strip()
            except Exception: ai_text = "" # Xử lý lỗi lấy text

            if ai_text:
                print(f"DEBUG (suggest_rule): AI Raw Response Text:\n---\n{ai_text}\n---")
                # <<< SỬA LẠI PHẦN PARSING ĐỂ LẤY THÊM TRƯỜNG >>>
                keywords_match = re.search(r"^Keywords:(.*?)(\nCategory:|\nTemplate Ref:|\nTemplate Text:|\Z)", ai_text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
                category_match = re.search(r"^Category:(.*?)(\nTemplate Ref:|\nTemplate Text:|\Z)", ai_text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
                ref_match = re.search(r"^Template Ref:(.*?)(\nTemplate Text:|\Z)", ai_text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
                template_match = re.search(r"^Template Text:(.*)", ai_text, re.IGNORECASE | re.MULTILINE | re.DOTALL)

                # Hàm helper để làm sạch text
                def clean_extracted_text(text):
                    if text:
                        # Bỏ label của dòng tiếp theo nếu bị match vào group 1
                        text = text.split("Category:")[0].split("Template Ref:")[0].split("Template Text:")[0]
                        # Xóa khoảng trắng, *, - ở đầu/cuối
                        text = re.sub(r'^[\s*-]+|[\s*-]+$', '', text, flags=re.MULTILINE).strip()
                    return text if text else None

                suggested_keywords = clean_extracted_text(keywords_match.group(1) if keywords_match else None)
                suggested_category = clean_extracted_text(category_match.group(1) if category_match else None)
                suggested_template_ref = clean_extracted_text(ref_match.group(1) if ref_match else None)
                suggested_template = clean_extracted_text(template_match.group(1) if template_match else None)

                print(f"DEBUG (suggest_rule): Parsed Keywords: '{suggested_keywords}'")
                print(f"DEBUG (suggest_rule): Parsed Category: '{suggested_category}'")
                print(f"DEBUG (suggest_rule): Parsed Template Ref: '{suggested_template_ref}'")

                if suggested_template and "cannot generalize" in suggested_template.lower():
                    suggested_template = None # Vẫn giữ logic này
                    print("INFO (suggest_rule): AI indicated template cannot be generalized.")
                else:
                    print(f"DEBUG (suggest_rule): Parsed Template Text: '{str(suggested_template)[:200]}...'")

                # Xác định status dựa trên việc parse được ít nhất keywords hoặc template
                if suggested_keywords or suggested_template:
                    status = "success_ai_suggestion"
                else:
                    status = "error_ai_suggestion_parsing"
                    # Reset hết nếu không parse được gì cốt lõi
                    suggested_keywords = suggested_category = suggested_template_ref = suggested_template = None

            else: status = "error_ai_suggestion_empty"

        elif hasattr(response, 'prompt_feedback') and response.prompt_feedback.block_reason:
            status = "error_ai_suggestion_blocked"
            print(f"CẢNH BÁO (suggest_rule): Gemini prompt bị chặn. Lý do: {response.prompt_feedback.block_reason}")
        else:
            status = "error_ai_suggestion_invalid_response"
            print(f"CẢNH BÁO (suggest_rule): Phản hồi AI không hợp lệ hoặc rỗng.")

    except Exception as e:
        print(f"LỖI (suggest_rule): Gọi Gemini API hoặc xử lý thất bại nghiêm trọng: {type(e).__name__} - {e}")
        print(traceback.format_exc())
        status = "error_ai_suggestion_exception"
        suggested_keywords = suggested_category = suggested_template_ref = suggested_template = None

    print(f"INFO (suggest_rule): Suggestion generation completed with status: {status}")
    # <<< TRẢ VỀ 4 GIÁ TRỊ >>>
    return suggested_keywords, suggested_category, suggested_template_ref, suggested_template
# ... (Các hàm khác như generate_reply_with_ai, detect_user_intent_with_ai) ...

def detect_user_intent_with_ai(text: str, persona_id: str | None = None) -> str:
    """
    Phân loại ý định của đoạn text sử dụng Gemini API, có thể tùy chọn Persona/Prompt.

    Args:
        text: Đoạn text cần phân loại.
        persona_id: ID của Persona (tùy chọn). Nếu có, sẽ dùng prompt/model từ persona.

    Returns:
        Chuỗi string là nhãn ý định (từ VALID_INTENTS) hoặc 'error'.
    """
    task_type = 'detect_intent'
    print(f"DEBUG (detect_intent): Bắt đầu. PersonaID='{persona_id or 'Default'}', Task='{task_type}', Text='{text[:100]}...'")
    detected_intent = 'error' # Mặc định lỗi

    if not text or not text.strip():
        print("DEBUG (detect_intent): Input text rỗng.")
        return 'unknown'

    if not configure_gemini_if_needed():
        return 'error'

    # --- Chuẩn bị Prompt, Model, Config ---
    final_prompt = ""
    model_name = current_app.config.get('GEMINI_CLASSIFY_MODEL', 'models/gemini-1.5-flash-latest') # Default model
    default_gen_config = genai.types.GenerationConfig(temperature=0.1, max_output_tokens=50) # Default config
    generation_config = default_gen_config

    persona = None
    template_content = None

    if persona_id: # Nếu có persona_id được cung cấp
        try:
            persona = db.get_persona_details(persona_id)
            template_content = db.get_prompt_template_by_task(task_type)
            if not persona:
                 print(f"WARNING (detect_intent): Không tìm thấy Persona ID '{persona_id}'. Dùng cấu hình mặc định.")
            if not template_content:
                 print(f"WARNING (detect_intent): Không tìm thấy Prompt Template '{task_type}'. Dùng prompt mặc định.")

            # Chỉ sử dụng cấu hình từ persona nếu cả persona và template đều tồn tại
            if persona and template_content:
                 # Render prompt
                 jinja_env = Environment()
                 jinja_template = jinja_env.from_string(template_content)
                 render_context = {"base_prompt": persona.get('base_prompt', ''), "text": text}
                 final_prompt = jinja_template.render(render_context)

                 # Lấy model/config từ persona
                 model_name = persona.get('model_name') or model_name # Ưu tiên model từ persona
                 persona_gen_config_obj = _parse_generation_config(persona.get('generation_config'))
                 generation_config = persona_gen_config_obj or default_gen_config # Ưu tiên config từ persona
                 print(f"DEBUG (detect_intent): Sử dụng cấu hình từ Persona '{persona_id}'.")

            else: # Nếu persona hoặc template không tìm thấy, quay về dùng prompt mặc định
                 persona_id = None # Đặt lại để logic dưới dùng prompt mặc định

        except Exception as db_err:
             print(f"LỖI (detect_intent): Lỗi DB khi lấy Persona/Template: {db_err}. Dùng cấu hình mặc định.")
             persona_id = None # Quay về dùng prompt mặc định

    # Nếu không có persona_id hoặc lấy config lỗi, dùng prompt mặc định
    if not persona_id:
        intent_list_str = ", ".join(VALID_INTENTS[:-2]) # Lấy intents hợp lệ
        final_prompt = f"""Phân loại ý định chính của bình luận/tin nhắn tiếng Việt sau đây vào MỘT trong các loại sau: [{intent_list_str}].
             Bình luận/Tin nhắn: "{text}"
             Chỉ trả về DUY NHẤT nhãn ý định (viết thường, không giải thích). Ví dụ: price_query"""
        print(f"DEBUG (detect_intent): Sử dụng prompt mặc định.")


    print(f"DEBUG (detect_intent): Final Prompt (first 300 chars): {final_prompt[:300]}...")
    print(f"DEBUG (detect_intent): Using model: {model_name}, Config: {generation_config}")

    # --- Gọi API và xử lý kết quả (Giữ nguyên logic xử lý intent như trước) ---
    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(final_prompt, generation_config=generation_config)
        print(f"DEBUG (detect_intent): Nhận được response phân loại.")

        # Xử lý và chuẩn hóa kết quả
        if response.parts:
             try:
                 raw_intent = response.text.strip().lower()
                 print(f"DEBUG (detect_intent): Raw intent from AI: '{raw_intent}'")
                 # Tìm intent hợp lệ trong kết quả trả về
                 found_valid_intent = 'other' # Mặc định là 'other' nếu không khớp rõ ràng
                 # Ưu tiên khớp chính xác trước
                 for valid_intent in VALID_INTENTS:
                      if valid_intent == raw_intent:
                           found_valid_intent = valid_intent
                           break
                 # Nếu không khớp chính xác, thử tìm trong chuỗi (ít ưu tiên hơn)
                 if found_valid_intent == 'other':
                     for valid_intent in VALID_INTENTS[:-2]: # Bỏ qua other, unknown, error
                          if valid_intent in raw_intent:
                              # Có thể thêm logic kiểm tra word boundary nếu cần chính xác hơn
                              found_valid_intent = valid_intent
                              break

                 # Kiểm tra lại xem found_valid_intent có nằm trong danh sách hợp lệ không
                 if found_valid_intent in VALID_INTENTS:
                       detected_intent = found_valid_intent # Gán nếu hợp lệ
                 else: # Trường hợp rất hiếm khi logic trên sai
                      detected_intent = 'other'
                 print(f"DEBUG (detect_intent): Parsed valid intent: '{detected_intent}'")

             except (ValueError, AttributeError) as e_parse:
                 print(f"WARNING (detect_intent): Không lấy/phân tích được text từ AI response: {e_parse}. Đặt là 'other'.")
                 detected_intent = 'other'
             except Exception as parse_err:
                 print(f"LỖI (detect_intent): Xử lý response AI thất bại: {parse_err}")
                 detected_intent = 'error'
        elif hasattr(response, 'prompt_feedback') and response.prompt_feedback.block_reason:
            print(f"CẢNH BÁO (detect_intent): Gemini bị chặn khi phân loại intent. Reason: {response.prompt_feedback.block_reason}")
            detected_intent = 'error' # Coi là lỗi nếu bị chặn
        else:
             print(f"CẢNH BÁO (detect_intent): Response phân loại intent không có nội dung.")
             detected_intent = 'other' # Coi là 'other' nếu không có nội dung

    except Exception as e: # Lỗi khi gọi API
        print(f"LỖI (detect_intent): Gọi Gemini API thất bại: {e}")
        print(traceback.format_exc())
        detected_intent = 'error'

    print(f"DEBUG (detect_intent): Kết quả cuối cùng: '{detected_intent}'")
    return detected_intent


    """
    Sử dụng AI (Gemini) để phân tích tương tác và đề xuất keywords, template mới.

    Args:
        interaction_data: Dict chứa ít nhất 'received_text' và 'sent_text'.
                          Có thể chứa thêm 'user_intent', 'stage_id', 'strategy_id' để làm phong phú prompt.

    Returns:
        Tuple: (suggested_keywords: str | None, suggested_template: str | None)
               Trả về (None, None) nếu có lỗi hoặc AI không đề xuất được.
    """
    print(f"DEBUG (suggest_rule): Bắt đầu phân tích tương tác...")
    received_text = interaction_data.get('received_text', '')
    sent_text = interaction_data.get('sent_text', '') # Đây là phản hồi do AI tạo ra trước đó
    user_intent = interaction_data.get('user_intent', 'unknown')
    # Có thể lấy thêm stage_id, strategy_id nếu muốn đưa vào prompt
    # stage_id = interaction_data.get('stage_id')
    # strategy_id = interaction_data.get('strategy_id')

    if not received_text or not sent_text:
        print("WARNING (suggest_rule): Thiếu received_text hoặc sent_text để phân tích.")
        return None, None

    # --- Kiểm tra cấu hình API ---
    if not configure_gemini_if_needed():
         print("LỖI (suggest_rule): Không thể cấu hình Gemini API.")
         return None, None

    # --- Tạo Prompt chi tiết cho AI ---
    # Prompt này yêu cầu AI xác định từ khóa và tạo template tái sử dụng
    prompt = f"""Analyze the following successful user interaction where the assistant's reply was generated by an AI:

Context:
- User Intent Detected: {user_intent}
- Conversation Stage (Optional): {interaction_data.get('stage_id', 'N/A')}
- Overall Strategy (Optional): {interaction_data.get('strategy_id', 'N/A')}

Interaction:
- User Said: "{received_text}"
- Assistant (AI) Replied: "{sent_text}"

Your Task:
1.  **Identify Trigger Keywords:** Extract the most important and concise keywords or short phrases (comma-separated) from the "User Said" text that likely represent the core reason for the assistant's reply. Avoid overly generic words unless necessary for the context.
2.  **Create Reusable Template:** Generalize the "Assistant Replied" text into a reusable template. If the reply contains specific details (like names, exact times, unique IDs, very specific numbers), try to replace them with generic placeholders like [Name], [Time], [ID], [Number] IF AND ONLY IF it makes sense for reusability. If the reply is too specific and cannot be meaningfully generalized, output "Cannot generalize". Maintain the original tone and key message of the reply.

Output Format: Respond ONLY in the following format, without any introductory text or explanations:
Keywords: <suggested keywords here>
Template Text: <suggested template text here or "Cannot generalize">
"""

    print(f"DEBUG (suggest_rule): Prompting Gemini for suggestions...")
    # print(f"DEBUG (suggest_rule) Prompt (first 500 chars):\n{prompt[:500]}...") # Bỏ comment nếu cần xem prompt

    suggested_keywords = None
    suggested_template = None
    status = "error_ai_suggestion_unknown" # Trạng thái xử lý nội bộ

    try:
        # --- Gọi API Gemini ---
        # Sử dụng model cấu hình riêng hoặc model mặc định
        model_name = current_app.config.get('GEMINI_SUGGEST_MODEL', 'models/gemini-1.5-flash-latest')
        model = genai.GenerativeModel(model_name)
        # Giảm temperature để kết quả nhất quán hơn, giới hạn token output
        generation_config = genai.types.GenerationConfig(temperature=0.2, max_output_tokens=300)

        print(f"DEBUG (suggest_rule): Calling model '{model_name}'...")
        response = model.generate_content(prompt, generation_config=generation_config)
        print(f"DEBUG (suggest_rule): Received response from Gemini.")

        # --- Xử lý và Phân tích Kết quả từ AI ---
        ai_text = ""
        if response.parts:
            try:
                 ai_text = response.text.strip()
                 print(f"DEBUG (suggest_rule): AI Raw Response Text:\n---\n{ai_text}\n---")
            except ValueError as e:
                 # Lỗi này đôi khi xảy ra nếu response chỉ có feedback mà không có content
                 print(f"WARNING (suggest_rule): Cannot access response.text. Value Error: {e}. Feedback: {getattr(response, 'prompt_feedback', 'N/A')}")
                 status = "error_ai_suggestion_no_text_value"
                 ai_text = "" # Đảm bảo ai_text rỗng
            except Exception as e_text:
                 print(f"ERROR (suggest_rule): Unexpected error accessing response.text: {e_text}")
                 status = "error_ai_suggestion_text_access"
                 ai_text = ""

            if ai_text:
                # Sử dụng regex để tìm chính xác và lấy nội dung sau label (case-insensitive, multiline)
                keywords_match = re.search(r"^Keywords:(.*?)(\nTemplate Text:|\Z)", ai_text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
                template_match = re.search(r"^Template Text:(.*)", ai_text, re.IGNORECASE | re.MULTILINE | re.DOTALL)

                if keywords_match:
                    suggested_keywords = keywords_match.group(1).strip()
                    # Dọn dẹp thêm nếu cần (ví dụ loại bỏ dấu * nếu AI trả về markdown)
                    suggested_keywords = re.sub(r'^[\s*-]+|[\s*-]+$', '', suggested_keywords, flags=re.MULTILINE).strip()

                    print(f"DEBUG (suggest_rule): Extracted Keywords: '{suggested_keywords}'")
                else:
                     print("WARNING (suggest_rule): Could not find 'Keywords:' label in AI response.")

                if template_match:
                    suggested_template = template_match.group(1).strip()
                    # Dọn dẹp thêm nếu cần
                    suggested_template = re.sub(r'^[\s*-]+|[\s*-]+$', '', suggested_template, flags=re.MULTILINE).strip()

                    if "cannot generalize" in suggested_template.lower():
                        suggested_template = None # Đặt là None nếu không tổng quát hóa được
                        print("INFO (suggest_rule): AI indicated template cannot be generalized.")
                    else:
                         print(f"DEBUG (suggest_rule): Extracted Template Text: '{suggested_template[:200]}...'")

                else:
                     print("WARNING (suggest_rule): Could not find 'Template Text:' label in AI response.")
                     suggested_template = None # Đặt là None nếu không tìm thấy

                # Xác định status cuối cùng
                if suggested_keywords and suggested_template:
                    status = "success_ai_suggestion"
                elif suggested_keywords and not suggested_template:
                    status = "warning_ai_suggestion_keywords_only"
                    # Quyết định xem có nên trả về keywords không, hiện tại thì có
                elif not suggested_keywords and suggested_template:
                     status = "warning_ai_suggestion_template_only"
                     # Không có keywords thì đề xuất cũng không hữu ích lắm? Đặt keywords là None
                     suggested_keywords = None
                else:
                    # Không tìm thấy cả hai hoặc lỗi regex
                    status = "error_ai_suggestion_parsing"
                    suggested_keywords = None
                    suggested_template = None

            else:
                 # Trường hợp response.text truy cập được nhưng lại rỗng
                 print("WARNING (suggest_rule): AI response text is empty.")
                 status = "error_ai_suggestion_empty"


        elif hasattr(response, 'prompt_feedback') and response.prompt_feedback.block_reason:
             block_reason = response.prompt_feedback.block_reason
             print(f"CẢNH BÁO (suggest_rule): Gemini prompt bị chặn. Lý do: {block_reason}")
             status = "error_ai_suggestion_blocked"
        else:
             # Trường hợp response không có parts và cũng không bị chặn rõ ràng
             print(f"CẢNH BÁO (suggest_rule): Phản hồi AI không hợp lệ hoặc không có nội dung. Response: {response}")
             status = "error_ai_suggestion_invalid_response"

    except Exception as e:
        # Bắt các lỗi khác trong quá trình gọi API hoặc xử lý
        print(f"LỖI (suggest_rule): Gọi Gemini API hoặc xử lý thất bại nghiêm trọng: {type(e).__name__} - {e}")
        print(traceback.format_exc())
        status = "error_ai_suggestion_exception"
        suggested_keywords = None
        suggested_template = None

    print(f"INFO (suggest_rule): Suggestion generation completed with status: {status}")
    # Chỉ trả về keywords và template, status chỉ dùng để log/debug nội bộ
    return suggested_keywords, suggested_template



    """
    Phân loại ý định của đoạn text sử dụng Gemini API.
    Trả về: Chuỗi string là nhãn ý định hoặc 'error'.
    """
    print(f"DEBUG (detect_intent): Bắt đầu. Text(100): '{text[:100]}...'")

    
    if not text or not text.strip():
        print("DEBUG (detect_intent): Input text rỗng.")
        return 'unknown'

    # !!! KHỞI TẠO BIẾN Ở ĐÂY !!!
    detected_intent = 'error' # Khởi tạo giá trị mặc định/lỗi



    if not configure_gemini_if_needed():
        return 'error' # Trả về lỗi nếu không config được API

    intent_list_str = ", ".join(VALID_INTENTS[:-2])
    prompt = f"""Phân loại ý định chính của bình luận/tin nhắn tiếng Việt sau đây vào MỘT trong các loại sau: [{intent_list_str}].
             Bình luận/Tin nhắn: "{text}"
             Chỉ trả về DUY NHẤT nhãn ý định (viết thường, không giải thích). Ví dụ: price_query"""
    print(f"DEBUG (detect_intent): Prompt phân loại intent: {prompt}") # Log đúng biến prompt
    detected_intent = 'error'
    # Khối try chính bao gồm cả gọi API và xử lý response
    try:
        # ... (Lấy model_name, model = ..., generation_config = ...) ...
        model_name = current_app.config.get('GEMINI_CLASSIFY_MODEL', 'models/gemini-1.5-flash-latest')
        print(f"DEBUG (detect_intent): Sử dụng model phân loại: {model_name}") # Thêm log cho rõ
        model = genai.GenerativeModel(model_name) # <<< Khởi tạo model
        generation_config = genai.types.GenerationConfig(temperature=0.1, max_output_tokens=50)
        # Bây giờ mới gọi generate_content
        response = model.generate_content(prompt, generation_config=generation_config)
        print(f"DEBUG (detect_intent): Nhận được response phân loại.")

        # --- Xử lý và chuẩn hóa kết quả ---
        if response.parts:
             try:
                 raw_intent = response.text.strip().lower()
                 # ... (logic kiểm tra raw_intent và gán detected_intent = valid_intent hoặc 'other') ...
                 # Ví dụ:
                 found_valid_intent = None
                 for valid_intent in VALID_INTENTS:
                      if re.search(r'\b' + re.escape(valid_intent) + r'\b', raw_intent):
                          found_valid_intent = valid_intent
                          break
                 if found_valid_intent and found_valid_intent not in ['unknown', 'error']:
                      detected_intent = found_valid_intent # Gán nếu hợp lệ
                 else:
                      detected_intent = 'other' # Gán 'other' nếu không hợp lệ

             except ValueError as e:
                 print(f"WARNING (detect_intent): Không lấy được text... Đặt là 'other'.")
                 detected_intent = 'other' # Gán lại nếu lỗi parse
             except Exception as parse_err:
                 print(f"LỖI (detect_intent): Xử lý response AI thất bại: {parse_err}")
                 # Không gán lại, detected_intent vẫn là 'error' từ khởi tạo
        elif hasattr(response, 'prompt_feedback') and response.prompt_feedback.block_reason:
            print(f"CẢNH BÁO (detect_intent): Gemini bị chặn...")
            # detected_intent vẫn là 'error' từ khởi tạo
        else:
             print(f"CẢNH BÁO (detect_intent): Response không có nội dung...")
             # detected_intent vẫn là 'error' từ khởi tạo

    except Exception as e: # Lỗi khi gọi API
        print(f"LỖI (detect_intent): Gọi Gemini API thất bại: {e}")
        print(traceback.format_exc())
        # detected_intent vẫn là 'error' từ khởi tạo

    # Dòng return nằm ở cuối hàm, lúc này detected_intent chắc chắn đã có giá trị
    print(f"DEBUG (detect_intent): Kết quả cuối cùng: '{detected_intent}'")
    return detected_intent
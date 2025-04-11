# app/ai_service.py
import os
import google.generativeai as genai
from flask import current_app # Import current_app để truy cập config
import re
import traceback
import random
from datetime import datetime # <<< Đảm bảo có import này
# !!! Đảm bảo import database đúng cách !!!
# Nếu database.py cùng cấp __init__.py trong thư mục 'app' thì dùng:
from . import database as db
# Nếu cấu trúc khác, bạn cần điều chỉnh import này

# --- DANH SÁCH INTENT ĐÃ ĐỊNH NGHĨA ---
VALID_INTENTS = [
    'greeting', 'price_query', 'shipping_query', 'product_info_query',
    'compliment', 'complaint', 'connection_request', 'spam',
    'positive_generic', 'negative_generic', 'other', 'unknown', 'error'
]

# --- Hàm lấy API Key ---
def _get_api_key():
    """Hàm nội bộ để lấy API key từ config của Flask app."""
    try:
        # Truy cập config thông qua current_app
        key = current_app.config.get('GOOGLE_API_KEY')
        if not key:
            print("CẢNH BÁO (ai_service): GOOGLE_API_KEY không có trong app.config.")
        return key
    except RuntimeError:
        # Lỗi này có thể xảy ra nếu hàm được gọi ngoài application context
        # Trong cấu trúc hiện tại thì ít khả năng xảy ra nếu gọi từ route
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

# --- Hàm Tạo Trả lời (Đã chỉnh sửa cấu trúc) ---
def generate_reply_with_ai(prompt: str, account_goal: str) -> tuple[str | None, str]:
    """
    Tạo câu trả lời bằng Gemini API, xử lý fallback/redirect và thay thế placeholder.
    Trả về: Tuple (reply_text: str hoặc None nếu lỗi, status: str)
    """
    print(f"DEBUG (generate_reply): Bắt đầu. Goal='{account_goal}'. Prompt(100): '{prompt[:100]}...'")
    final_reply_text = None # Biến lưu kết quả cuối cùng
    status = "error_ai_unknown"

    if not configure_gemini_if_needed():
        return None, "error_ai_no_key_or_config_failed"

    try:
        # --- Bước 1: Gọi API Gemini ---
        model_name = current_app.config.get('GEMINI_REPLY_MODEL', 'models/gemini-1.5-flash-latest')
        model = genai.GenerativeModel(model_name)
        print(f"DEBUG (generate_reply): Sử dụng model: {model_name}")
        print(f"DEBUG (generate_reply): Đang gọi model.generate_content...")
        response = model.generate_content(prompt)
        print(f"DEBUG (generate_reply): Đã nhận response từ API.")

        # --- Bước 2: Xử lý Response từ AI ---
        generated_text = None
        processed_reply = None
        is_blocked = False
        has_content = False

        # 2.1 Kiểm tra xem có bị chặn không
        try:
            if not response.parts and hasattr(response, 'prompt_feedback') and response.prompt_feedback.block_reason:
                block_reason = response.prompt_feedback.block_reason
                print(f"CẢNH BÁO (generate_reply): Gemini bị chặn. Lý do: {block_reason}")
                status = "error_ai_blocked"
                is_blocked = True
        except Exception as block_check_err:
             print(f"LỖI (generate_reply): Khi kiểm tra block_reason: {block_check_err}")
             status = "error_ai_response_check_failed"
             is_blocked = True # Coi như bị chặn nếu không check được

        # 2.2 Nếu không bị chặn, thử lấy text
        if not is_blocked:
            try:
                generated_text = response.text.strip()
                if generated_text:
                    has_content = True
                    processed_reply = generated_text # Bắt đầu với text gốc
                    print(f"DEBUG (generate_reply): Text gốc từ AI: '{processed_reply[:100]}...'")
                else:
                    print(f"CẢNH BÁO (generate_reply): Gemini không trả về text.")
                    status = "error_ai_empty_response"
            except ValueError as e:
                print(f"CẢNH BÁO (generate_reply): Không lấy được text từ response. Feedback: {getattr(response, 'prompt_feedback', 'N/A')}. Lỗi: {e}")
                status = "error_ai_no_text_content"
            except AttributeError as ae:
                print(f"LỖI (generate_reply): Cấu trúc response không mong đợi: {ae}")
                status = "error_ai_bad_response_structure"

        # --- Bước 3: Xử lý hậu kỳ (Chỉ thực hiện nếu AI trả về nội dung) ---
        if has_content and processed_reply:
            # 3.1 Thay thế ngày tháng
            try:
                now = datetime.now()
                temp_reply = processed_reply
                temp_reply = temp_reply.replace("[Ngày hôm nay]", now.strftime("%d"))
                temp_reply = temp_reply.replace("[Tháng]", now.strftime("%m"))
                temp_reply = temp_reply.replace("[Năm]", now.strftime("%Y"))
                # Thêm replace khác nếu cần
                if temp_reply != processed_reply:
                    print(f"DEBUG (ai_service): Đã thay thế placeholders ngày tháng.")
                    processed_reply = temp_reply # Cập nhật
                # else: # Bỏ log này cho gọn
                #    print(f"DEBUG (ai_service): Không tìm thấy placeholder ngày tháng.")
            except Exception as date_err:
                print(f"WARNING (ai_service): Lỗi thay thế ngày tháng: {date_err}")
                # Giữ nguyên processed_reply nếu lỗi

            # 3.2 Kiểm tra nội dung AI có hữu ích không và dùng Fallback nếu cần
            is_unhelpful = False
            unhelpful_patterns = ["tôi không biết", "tôi không chắc", "tôi không có thông tin", "tôi không thể trả lời", "nằm ngoài phạm vi"]
            if any(pattern in processed_reply.lower() for pattern in unhelpful_patterns) or re.search(r'\[.*?\]', processed_reply): # Kiểm tra placeholder còn sót lại
                is_unhelpful = True
                print(f"WARNING: AI trả lời không hữu ích/còn placeholder: '{processed_reply[:100]}...'")

            if is_unhelpful:
                fallback_reply = None
                fallback_template_ref = None
                # Chọn fallback template dựa trên goal
                if account_goal == 'make_friend': fallback_template_ref = 'fallback_make_friend'
                elif account_goal == 'product_sales': fallback_template_ref = 'fallback_product_sales'
                else: fallback_template_ref = 'fallback_generic'

                if fallback_template_ref:
                    print(f"DEBUG: Sử dụng fallback template ref: {fallback_template_ref}")
                    variations = db.get_template_variations(fallback_template_ref)
                    if variations:
                        fallback_reply = random.choice(variations).get('variation_text')

                if fallback_reply:
                    processed_reply = fallback_reply # Ghi đè bằng template
                    status = "success_fallback_template"
                    print(f"DEBUG: Đã dùng fallback template: '{processed_reply[:100]}...'")
                else:
                    print(f"WARNING: Không tìm thấy fallback template cho ref {fallback_template_ref}.")
                    status = "error_ai_unhelpful_no_fallback"
                    processed_reply = None # Trả về None nếu không có fallback
            else:
                 # Phản hồi AI được coi là ổn
                 status = "success_ai"
                 print(f"DEBUG: Phản hồi AI (đã xử lý) ok: '{processed_reply[:100]}...'")

        # Nếu ban đầu AI không có content hoặc bị chặn, processed_reply vẫn là None
        # Gán kết quả cuối cùng cho biến sẽ return
        final_reply_text = processed_reply

    # Bắt lỗi trong quá trình gọi API hoặc khởi tạo model
    except Exception as e:
        print(f"LỖI (generate_reply): Ngoại lệ khi gọi Gemini API hoặc xử lý: {type(e).__name__} - {e}")
        print(traceback.format_exc())
        status = "error_ai_call"
        final_reply_text = None

    # Return giá trị cuối cùng
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
    conn = get_db_connection()
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

def suggest_rule_from_interaction(interaction_data: dict) -> tuple[str | None, str | None]:
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


# --- Hàm detect_user_intent_with_ai (Giữ nguyên như bản sửa lỗi trước) ---
# Trong app/ai_service.py
def detect_user_intent_with_ai(text: str) -> str:
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
# nlp_utils.py
from underthesea import word_tokenize
# import các thư viện NLP khác nếu cần

def tokenize_text(text):
    if not text:
        return []
    try:
        # Chuyển sang chữ thường trước khi tách từ
        return word_tokenize(text.lower())
    except Exception as e:
        print(f"Lỗi khi tách từ: {e}")
        return text.lower().split() # Fallback tách từ đơn giản

def check_rules_match(tokens, raw_text_lower, rules):
    # Input: list of tokens, lowercase raw text, list of rule dicts from DB
    # Output: matched_template_ref or None
    if not tokens and not raw_text_lower: return None

    for rule in rules:
        keywords = [kw.strip() for kw in rule['trigger_keywords'].lower().split(',')]
        rule_matched = False
        for keyword in keywords:
            # Kiểm tra keyword có trong token hoặc chuỗi gốc không
            if keyword in tokens or keyword in raw_text_lower:
                rule_matched = True
                print(f"DEBUG: Khớp từ khóa '{keyword}' của luật ref '{rule['response_template_ref']}'")
                break
        if rule_matched:
            return rule['response_template_ref'] # Trả về ref nếu khớp
    return None # Không khớp luật nào

# ... thêm hàm determine_topic, detect_user_intent ...
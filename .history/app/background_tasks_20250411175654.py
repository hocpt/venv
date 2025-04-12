# backup/app/background_tasks.py
from flask import current_app
# ... (các import khác nếu có ở trên hàm) ...
from datetime import datetime # Import datetime để dùng trong print
import time # Import time nếu bạn dùng time.strftime

# --- Các hằng số JOB_ID, STATUS_TO_ANALYZE etc. có thể giữ lại hoặc comment đi ---
JOB_ID = 'suggestion_job'
# ...

# === Sửa lại trong backup/app/background_tasks.py ===
# ... (Imports) ...

def analyze_interactions_and_suggest():
    # ... (Lấy app context, persona_id, last_processed_id như cũ) ...
    with app.app_context():
        # ...
        try:
            # ... (Lấy interactions như cũ) ...
            if not interactions:
                # ... (Xử lý khi không có interaction) ...
                return

            # ... (Lặp qua interactions) ...
            for interaction in interactions:
                # ... (Lấy history_id, interaction_data như cũ) ...

                # <<< NHẬN 4 GIÁ TRỊ TỪ AI SERVICE >>>
                suggested_keywords, suggested_category, suggested_template_ref, suggested_template = ai_service.suggest_rule_from_interaction(
                    interaction_data=interaction_data,
                    persona_id=persona_id_for_suggestion
                )

                # 4. Lưu đề xuất vào DB
                # <<< CHỈ CẦN KIỂM TRA keywords HOẶC template CÓ GIÁ TRỊ >>>
                if suggested_keywords or suggested_template:
                    print(f"INFO: (Task) AI đề xuất cho ID {history_id}: kw='{str(suggested_keywords)[:50]}...', cat='{suggested_category}', ref='{suggested_template_ref}', tpl='{str(suggested_template)[:50]}...'")
                    source_examples = {'history_ids': [history_id], 'run_type': 'background'} # Có thể thêm run_type
                    # <<< TRUYỀN ĐỦ 4 GIÁ TRỊ VÀO HÀM DB >>>
                    added = db.add_suggestion(
                        keywords=suggested_keywords,
                        category=suggested_category,
                        template_ref=suggested_template_ref,
                        template_text=suggested_template,
                        source_examples=source_examples
                    )
                    # ... (Log kết quả lưu như cũ) ...
                else:
                     print(f"DEBUG: (Task) AI không tạo ra đề xuất hợp lệ (thiếu cả keywords và template) cho interaction {history_id}.")

                # Luôn cập nhật ID lớn nhất đã xử lý
                max_processed_id_in_batch = max(max_processed_id_in_batch, history_id)

            # ... (Cập nhật task state như cũ) ...
        # ... (Except như cũ) ...
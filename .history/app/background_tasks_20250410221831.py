# backup/app/background_tasks.py
from flask import current_app
try:
    from . import database as db
    from . import ai_service
except ImportError:
    import database as db
    import ai_service
import time
from datetime import datetime, timedelta
import traceback

# ... (Các hằng số JOB_ID, STATUS_TO_ANALYZE, etc.) ...

def analyze_interactions_and_suggest():
    app = current_app._get_current_object()
    if not app:
        print(f"LỖI (Task {JOB_ID}): Không thể lấy Flask app instance.")
        return

    with app.app_context():
        print(f"\n--- Bắt đầu tác vụ nền: {JOB_ID} --- ({time.strftime('%Y-%m-%d %H:%M:%S')})")

        # <<< Lấy Persona ID cho việc phân tích từ config >>>
        persona_id_for_suggestion = current_app.config.get('SUGGESTION_ANALYSIS_PERSONA_ID', 'rule_suggester') # Dùng default nếu không có trong config
        print(f"DEBUG: (Task) Sử dụng Persona ID for suggestion: {persona_id_for_suggestion}")

        try:
            # 1. Xác định thời điểm bắt đầu quét
            min_timestamp = datetime.now() - timedelta(hours=LOOKBACK_HOURS)
            print(f"DEBUG: (Task) Quét các tương tác từ sau: {min_timestamp.strftime('%Y-%m-%d %H:%M:%S')}")

            # 2. Lấy các tương tác cần phân tích từ DB
            print(f"DEBUG: (Task) Lấy tối đa {PROCESSING_LIMIT} tương tác với status {STATUS_TO_ANALYZE} từ DB...")
            interactions = db.get_interactions_for_suggestion(
                min_timestamp=min_timestamp,
                status_filter=STATUS_TO_ANALYZE,
                limit=PROCESSING_LIMIT
            )
            # ... (Xử lý nếu interactions is None hoặc rỗng) ...
            if interactions is None:
                 print(f"LỖI: (Task {JOB_ID}) Không thể lấy tương tác từ DB.")
                 return
            if not interactions:
                 print(f"INFO: (Task {JOB_ID}) Không có tương tác mới phù hợp để phân tích.")
                 print(f"--- Kết thúc tác vụ nền: {JOB_ID} (Không có dữ liệu) ---")
                 return

            print(f"INFO: (Task {JOB_ID}) Tìm thấy {len(interactions)} tương tác để phân tích.")

            # 3. Lặp qua từng tương tác và xử lý
            suggestions_added = 0
            for interaction in interactions:
                history_id = interaction.get('history_id')
                print(f"DEBUG: (Task) Phân tích interaction ID: {history_id}")
                interaction_data = { # Dữ liệu cho AI service
                    'received_text': interaction.get('received_text'),
                    'sent_text': interaction.get('sent_text'),
                    'user_intent': interaction.get('detected_user_intent'),
                    'stage_id': interaction.get('stage_id'),
                    'strategy_id': interaction.get('strategy_id')
                }
                if not interaction_data['received_text'] or not interaction_data['sent_text']:
                    print(f"WARNING: (Task) Bỏ qua interaction {history_id} do thiếu text.")
                    continue

                # <<< Gọi hàm AI service VỚI persona_id >>>
                suggested_keywords, suggested_template = ai_service.suggest_rule_from_interaction(
                    interaction_data=interaction_data,
                    persona_id=persona_id_for_suggestion # Truyền persona ID đã lấy từ config
                )

                # 4. Lưu đề xuất vào DB (Giữ nguyên logic)
                if suggested_keywords and suggested_template:
                    # ... (code lưu suggestion) ...
                    source_examples = {'history_ids': [history_id]}
                    added = db.add_suggestion(suggested_keywords, suggested_template, source_examples)
                    # ... (log kết quả lưu) ...
                    if added: suggestions_added += 1
                else:
                     print(f"DEBUG: (Task) AI không tạo ra đề xuất hợp lệ cho interaction {history_id}.")

            print(f"INFO: (Task {JOB_ID}) Đã thêm {suggestions_added} đề xuất mới.")
            print(f"--- Kết thúc tác vụ nền: {JOB_ID} ---")

        except Exception as e:
             print(f"LỖI NGHIÊM TRỌNG trong background task {JOB_ID}: {e}")
             print(traceback.format_exc())
             print(f"--- Kết thúc tác vụ nền: {JOB_ID} (Gặp lỗi) ---")
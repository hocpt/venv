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
JOB_ID = 'suggestion_job'
STATUS_TO_ANALYZE = ['success_ai']
LOOKBACK_HOURS = 1 # Hoặc giá trị bạn muốn
PROCESSING_LIMIT = 50
# ... (Các hằng số JOB_ID, STATUS_TO_ANALYZE, etc.) ...

def analyze_interactions_and_suggest():
    """
    Tác vụ nền được lên lịch để phân tích các tương tác thành công gần đây
    và tạo đề xuất rule/template mới. Đã cập nhật quản lý trạng thái.
    """
    print(f"\n\n!!!!!! DEBUG: TASK {JOB_ID} EXECUTED AT {datetime.now()} !!!!!!\n\n")
    app = current_app._get_current_object()
    if not app:
        print(f"LỖI (Task {JOB_ID}): Không thể lấy Flask app instance.")
        return

    with app.app_context():
        print(f"\n--- Bắt đầu tác vụ nền: {JOB_ID} --- ({time.strftime('%Y-%m-%d %H:%M:%S')})")
        persona_id_for_suggestion = current_app.config.get('SUGGESTION_ANALYSIS_PERSONA_ID', 'rule_suggester')
        print(f"DEBUG: (Task) Sử dụng Persona ID for suggestion: {persona_id_for_suggestion}")

        last_processed_id = 0 # Khởi tạo
        max_processed_id_in_batch = 0 # Theo dõi ID lớn nhất trong batch này
        suggestions_added = 0

        try:
            # 1. Lấy trạng thái xử lý cuối cùng từ DB
            last_processed_id = db.get_task_state(JOB_ID) or 0 # Mặc định là 0 nếu chưa có
            print(f"DEBUG: (Task) Lấy last_processed_id = {last_processed_id}")

            # 2. Lấy các tương tác MỚI HƠN ID cuối cùng đã xử lý
            print(f"DEBUG: (Task) Lấy tối đa {PROCESSING_LIMIT} tương tác với status {STATUS_TO_ANALYZE} sau ID {last_processed_id}...")
            interactions = db.get_interactions_for_suggestion(
                min_history_id=last_processed_id, # <<< Dùng ID thay vì timestamp
                status_filter=STATUS_TO_ANALYZE,
                limit=PROCESSING_LIMIT
            )

            if interactions is None:
                 print(f"LỖI: (Task {JOB_ID}) Không thể lấy tương tác từ DB.")
                 return

            if not interactions:
                 print(f"INFO: (Task {JOB_ID}) Không có tương tác mới phù hợp để phân tích.")
                 # Không cần cập nhật trạng thái vì không xử lý gì
                 print(f"--- Kết thúc tác vụ nền: {JOB_ID} (Không có dữ liệu mới) ---")
                 return

            print(f"INFO: (Task {JOB_ID}) Tìm thấy {len(interactions)} tương tác để phân tích.")

            # 3. Lặp qua từng tương tác và xử lý
            for interaction in interactions:
                history_id = interaction.get('history_id')
                if history_id is None: continue # Bỏ qua nếu không có ID

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

                suggested_keywords, suggested_template = ai_service.suggest_rule_from_interaction(
                    interaction_data=interaction_data,
                    persona_id=persona_id_for_suggestion
                )

                # 4. Lưu đề xuất vào DB
                if suggested_keywords and suggested_template:
                    print(f"INFO: (Task) AI đề xuất cho ID {history_id}: keywords='{suggested_keywords[:50]}...', template='{suggested_template[:50]}...'")
                    source_examples = {'history_ids': [history_id]}
                    added = db.add_suggestion(suggested_keywords, suggested_template, source_examples)
                    if added:
                        suggestions_added += 1
                        # Cập nhật ID lớn nhất đã xử lý THÀNH CÔNG trong batch này
                        max_processed_id_in_batch = max(max_processed_id_in_batch, history_id)
                        print(f"INFO: (Task) Đã lưu đề xuất từ interaction {history_id}.")
                    else:
                        print(f"LỖI: (Task) Lưu đề xuất từ interaction {history_id} thất bại.")
                else:
                     print(f"DEBUG: (Task) AI không tạo ra đề xuất hợp lệ cho interaction {history_id}.")
                     # Vẫn coi như đã xử lý (dù không thành công) để cập nhật last_processed_id
                     max_processed_id_in_batch = max(max_processed_id_in_batch, history_id)


            # 5. Cập nhật trạng thái sau khi xử lý xong batch
            # Chỉ cập nhật nếu có interaction được xử lý trong batch này
            if max_processed_id_in_batch > last_processed_id:
                 print(f"DEBUG: (Task) Cập nhật last_processed_id thành {max_processed_id_in_batch} cho task {JOB_ID}")
                 update_success = db.update_task_state(JOB_ID, max_processed_id_in_batch)
                 if not update_success:
                      print(f"LỖI: (Task {JOB_ID}) Không thể cập nhật trạng thái last_processed_id!")
                 # Nếu cập nhật trạng thái lỗi thì lần chạy sau sẽ xử lý lại batch này!

            print(f"INFO: (Task {JOB_ID}) Đã thêm {suggestions_added} đề xuất mới.")
            print(f"--- Kết thúc tác vụ nền: {JOB_ID} ---")

        except Exception as e:
             print(f"LỖI NGHIÊM TRỌNG trong background task {JOB_ID}: {e}")
             print(traceback.format_exc())
             print(f"--- Kết thúc tác vụ nền: {JOB_ID} (Gặp lỗi) ---")
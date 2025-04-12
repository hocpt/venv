# backup/app/background_tasks.py
from flask import Flask, current_app # <<< Thêm Flask
import time
from datetime import datetime, timedelta
import traceback
from . import create_app
# Import db và ai_service (giữ nguyên)
try:
    from . import database as db
    from . import ai_service
except ImportError:
    import database as db
    import ai_service
    print("WARNING (background_tasks): Using fallback database/ai_service imports.")

# --- Constants ---
JOB_ID = 'suggestion_job' # Phải khớp với ID trong bảng scheduled_jobs
DEFAULT_STATUS_TO_ANALYZE = ['success_ai'] # Chỉ phân tích các tương tác AI trả lời thành công
DEFAULT_PROCESSING_LIMIT = 50 # Giới hạn số lượng xử lý mỗi lần chạy
STATUS_TO_ANALYZE = ['success_ai']
# =============================================
# === HÀM THỰC THI TÁC VỤ NỀN CHÍNH ===
# =============================================
def analyze_interactions_and_suggest():
    """
    Tác vụ nền... Tự tạo app instance và context khi chạy.
    """
    print(f"\n--- Starting background task: {JOB_ID} --- ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    # --- TẠO APP INSTANCE VÀ APP CONTEXT TẠM THỜI ---
    # Điều này đảm bảo job có môi trường Flask đầy đủ để chạy
    # mà không cần truyền app object (gây lỗi pickle)
    try:
        print("DEBUG: (Task) Creating temporary app instance for context...")
        # Sử dụng cấu hình mặc định hoặc bạn có thể chỉ định config class nếu cần
        # import config
        # temp_app = create_app(config_class=config.ProductionConfig) # Ví dụ nếu có config khác
        temp_app = create_app()
        if not temp_app:
             raise Exception("Failed to create temporary Flask app instance.")
        print("DEBUG: (Task) Temporary app instance created.")
    except Exception as creation_err:
        print(f"CRITICAL ERROR (Task {JOB_ID}): Cannot create temporary Flask app for context: {creation_err}")
        print(traceback.format_exc())
        return # Không thể chạy nếu không tạo được app

    # Chạy logic chính bên trong context của app tạm thời
    with temp_app.app_context():
        print("DEBUG: (Task) Entered temporary app context.")
        # Lấy Persona ID từ config thông qua current_app (trỏ đến temp_app)
        persona_id_for_suggestion = current_app.config.get('SUGGESTION_ANALYSIS_PERSONA_ID', 'rule_suggester')
        print(f"DEBUG: (Task) Using Persona ID: {persona_id_for_suggestion}")

        # Khởi tạo các biến theo dõi
        last_processed_id = 0
        max_processed_id_in_batch = 0
        suggestions_added = 0
        interactions_found_count = 0
        processed_count = 0

        try:
            # 1. Lấy trạng thái xử lý cuối cùng từ DB
            last_processed_id = db.get_task_state(JOB_ID) or 0
            max_processed_id_in_batch = last_processed_id
            print(f"DEBUG: (Task) Fetched last_processed_id = {last_processed_id}")

            # 2. Lấy các tương tác MỚI HƠN ID đó để phân tích
            status_filter = current_app.config.get('STATUS_TO_ANALYZE_SUGGEST', STATUS_TO_ANALYZE)
            limit = current_app.config.get('SUGGESTION_PROCESSING_LIMIT', PROCESSING_LIMIT)
            print(f"DEBUG: (Task) Fetching max {limit} interactions with status {status_filter} after ID {last_processed_id}...")

            interactions = db.get_interactions_for_suggestion(
                min_history_id=last_processed_id,
                status_filter=status_filter,
                limit=limit
            )

            if interactions is None:
                 print(f"ERROR: (Task {JOB_ID}) Could not fetch interactions from DB.")
                 return # Thoát nếu lỗi DB

            interactions_found_count = len(interactions)
            if not interactions:
                 print(f"INFO: (Task {JOB_ID}) No new interactions found matching criteria.")
                 print(f"--- Finishing background task: {JOB_ID} (No new data) ---")
                 # Vẫn nên cập nhật last_run_timestamp nếu cần theo dõi
                 db.update_task_state(JOB_ID, max_processed_id_in_batch) # Cập nhật timestamp chạy cuối
                 return # Thoát nếu không có tương tác mới

            print(f"INFO: (Task {JOB_ID}) Found {interactions_found_count} interactions to analyze.")

            # 3. Lặp qua các tương tác tìm được và xử lý
            for interaction in interactions:
                processed_count += 1
                history_id = interaction.get('history_id')
                if history_id is None: continue

                max_processed_id_in_batch = max(max_processed_id_in_batch, history_id)
                print(f"DEBUG: (Task) Analyzing interaction ID: {history_id}")
                interaction_data = {k: interaction.get(k) for k in ['received_text', 'sent_text', 'detected_user_intent', 'stage_id', 'strategy_id']}

                if not interaction_data['received_text'] or not interaction_data['sent_text']:
                    print(f"WARNING: (Task) Skipping interaction {history_id} due to missing text.")
                    continue

                # Gọi hàm AI service
                try:
                    suggested_keywords, suggested_category, suggested_template_ref, suggested_template = ai_service.suggest_rule_from_interaction(
                        interaction_data=interaction_data,
                        persona_id=persona_id_for_suggestion
                    )
                except Exception as ai_call_err:
                     print(f"ERROR: (Task) Exception calling ai_service for ID {history_id}: {ai_call_err}")
                     print(traceback.format_exc())
                     continue # Bỏ qua interaction này

                # 4. Lưu đề xuất hợp lệ vào database
                if suggested_keywords or suggested_template:
                    print(f"INFO: (Task) AI suggested for ID {history_id}: kw='{str(suggested_keywords)[:50]}...', cat='{suggested_category}', ref='{suggested_template_ref}', tpl='{str(suggested_template)[:50]}...'")
                    source_examples = {'history_ids': [history_id], 'run_type': 'background', 'persona_used': persona_id_for_suggestion, 'timestamp': datetime.now().isoformat()}
                    try:
                         added = db.add_suggestion(
                             keywords=suggested_keywords, category=suggested_category,
                             template_ref=suggested_template_ref, template_text=suggested_template,
                             source_examples=source_examples
                         )
                         if added:
                             suggestions_added += 1
                             print(f"INFO: (Task) Suggestion saved from interaction {history_id}.")
                         else:
                             print(f"ERROR: (Task) Failed to save suggestion from interaction {history_id}.")
                    except Exception as db_add_err:
                         print(f"ERROR: (Task) Exception calling db.add_suggestion for ID {history_id}: {db_add_err}")
                         print(traceback.format_exc())
                else:
                     print(f"DEBUG: (Task) AI did not generate valid suggestion for interaction {history_id}.")

            # --- Kết thúc vòng lặp ---

            # 5. Cập nhật trạng thái last_processed_id
            if max_processed_id_in_batch > last_processed_id:
                print(f"DEBUG: (Task) Updating last_processed_id from {last_processed_id} to {max_processed_id_in_batch} for task {JOB_ID}")
                update_success = db.update_task_state(JOB_ID, max_processed_id_in_batch)
                if not update_success:
                    print(f"CRITICAL ERROR: (Task {JOB_ID}) FAILED TO UPDATE last_processed_id to {max_processed_id_in_batch}!")
            else:
                print(f"DEBUG: (Task) No new interactions processed. State not updated.")

            end_time = time.time()
            print(f"INFO: (Task {JOB_ID}) Processed {processed_count}/{interactions_found_count}. Added {suggestions_added} new suggestions.")
            print(f"--- Finishing background task: {JOB_ID} --- (Duration: {end_time - start_time:.2f}s)")

        except Exception as e:
             print(f"CRITICAL ERROR during background task {JOB_ID}: {e}")
             print(traceback.format_exc())
             print(f"--- Finishing background task: {JOB_ID} (with CRITICAL ERROR) ---")
    # <<< Kết thúc with app.app_context() >>>

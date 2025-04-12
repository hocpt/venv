# backup/app/background_tasks.py
from flask import current_app # Để truy cập config và tạo app context
import time
from datetime import datetime, timedelta
import traceback # Để log lỗi chi tiết

# Import db và ai_service bằng relative import
try:
    from . import database as db
    from . import ai_service
except ImportError:
    # Fallback nếu chạy script này riêng lẻ (ít khả dụng)
    import database as db
    import ai_service
    print("WARNING (background_tasks): Using fallback database/ai_service imports.")

# --- Định nghĩa các hằng số/cấu hình cho tác vụ ---
JOB_ID = 'suggestion_job' # Phải khớp với ID trong bảng scheduled_jobs và khi đăng ký
STATUS_TO_ANALYZE = ['success_ai'] # Chỉ phân tích các tương tác thành công do AI tạo ra
PROCESSING_LIMIT = 50 # Giới hạn số lượng tương tác xử lý trong một lần chạy tác vụ

# Hàm chính thực thi tác vụ nền
def analyze_interactions_and_suggest():
    """
    Tác vụ nền được APScheduler lên lịch chạy định kỳ.
    Nó phân tích các tương tác thành công gần đây (trạng thái 'success_ai')
    để yêu cầu AI đề xuất keywords, category, template_ref, và template_text mới,
    sau đó lưu các đề xuất này vào bảng suggested_rules.
    Sử dụng cơ chế quản lý trạng thái dựa trên last_processed_id để tránh xử lý lại.
    """
    # Lấy app instance hiện tại để tạo app context
    # Cần thiết để các hàm db và ai_service (dùng current_app) hoạt động đúng
    app = current_app._get_current_object()
    if not app:
        # Lỗi này không nên xảy ra nếu job được chạy bởi Flask-APScheduler đúng cách
        print(f"CRITICAL ERROR (Task {JOB_ID}): Cannot get Flask app instance. Task cannot run.")
        return

    # Tạo app context để các hàm db.* và current_app.config hoạt động
    with app.app_context():
        print(f"\n--- Starting background task: {JOB_ID} --- ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")

        # Lấy Persona ID cấu hình cho việc phân tích từ config
        persona_id_for_suggestion = current_app.config.get('SUGGESTION_ANALYSIS_PERSONA_ID', 'rule_suggester')
        print(f"DEBUG: (Task) Using Persona ID for suggestion: {persona_id_for_suggestion}")

        # Khởi tạo các biến theo dõi
        last_processed_id = 0
        max_processed_id_in_batch = 0 # Theo dõi ID cao nhất đã xử lý trong lần chạy này
        suggestions_added = 0
        interactions_found_count = 0
        processed_count = 0

        try:
            # 1. Lấy trạng thái xử lý cuối cùng (ID của interaction cuối) từ DB
            last_processed_id = db.get_task_state(JOB_ID) or 0
            max_processed_id_in_batch = last_processed_id # Bắt đầu bằng ID cũ
            print(f"DEBUG: (Task) Fetched last_processed_id = {last_processed_id}")

            # 2. Lấy các tương tác MỚI HƠN ID đó để phân tích
            # Lấy các cấu hình khác từ app config nếu cần
            status_filter = current_app.config.get('STATUS_TO_ANALYZE_SUGGEST', STATUS_TO_ANALYZE)
            limit = current_app.config.get('SUGGESTION_PROCESSING_LIMIT', PROCESSING_LIMIT)
            print(f"DEBUG: (Task) Fetching max {limit} interactions with status {status_filter} after ID {last_processed_id}...")

            # Gọi hàm DB đã cập nhật (dùng min_history_id)
            interactions = db.get_interactions_for_suggestion(
                min_history_id=last_processed_id,
                status_filter=status_filter,
                limit=limit
            )

            # Xử lý kết quả trả về từ DB
            if interactions is None:
                 # Lỗi nghiêm trọng khi truy vấn DB
                 print(f"ERROR: (Task {JOB_ID}) Could not fetch interactions from DB. Aborting run.")
                 return # Thoát tác vụ nếu không lấy được dữ liệu

            interactions_found_count = len(interactions)
            if not interactions:
                 print(f"INFO: (Task {JOB_ID}) No new interactions found matching criteria (status={status_filter}, after ID={last_processed_id}).")
                 # Không cần cập nhật trạng thái vì không xử lý gì
                 print(f"--- Finishing background task: {JOB_ID} (No new data) ---")
                 return # Thoát nếu không có tương tác mới

            print(f"INFO: (Task {JOB_ID}) Found {interactions_found_count} interactions to analyze.")

            # 3. Lặp qua các tương tác tìm được và xử lý
            for interaction in interactions:
                processed_count += 1
                history_id = interaction.get('history_id')
                if history_id is None:
                    print("WARNING: (Task) Found interaction record with no history_id, skipping.")
                    continue

                # Luôn cập nhật ID cao nhất đã gặp trong batch này
                # ngay cả khi xử lý interaction đó bị lỗi sau đó, để đảm bảo tiến trình đi tiếp
                max_processed_id_in_batch = max(max_processed_id_in_batch, history_id)

                print(f"DEBUG: (Task) Analyzing interaction ID: {history_id}")

                # Chuẩn bị dữ liệu cho AI Service
                interaction_data = {
                    'received_text': interaction.get('received_text'),
                    'sent_text': interaction.get('sent_text'), # Phản hồi do AI tạo (status='success_ai')
                    'user_intent': interaction.get('detected_user_intent'),
                    'stage_id': interaction.get('stage_id'),
                    'strategy_id': interaction.get('strategy_id')
                    # Có thể thêm các trường khác từ interaction nếu prompt template cần
                }

                # Kiểm tra dữ liệu tối thiểu cần thiết
                if not interaction_data['received_text'] or not interaction_data['sent_text']:
                    print(f"WARNING: (Task) Skipping interaction {history_id} due to missing received_text or sent_text.")
                    continue # Chuyển sang interaction tiếp theo

                # Gọi hàm AI service để lấy đề xuất (mong đợi 4 giá trị trả về)
                try:
                    suggested_keywords, suggested_category, suggested_template_ref, suggested_template = ai_service.suggest_rule_from_interaction(
                        interaction_data=interaction_data,
                        persona_id=persona_id_for_suggestion
                    )
                except Exception as ai_call_err:
                     print(f"ERROR: (Task) Exception calling ai_service.suggest_rule_from_interaction for ID {history_id}: {ai_call_err}")
                     print(traceback.format_exc())
                     continue # Bỏ qua interaction này, xử lý cái tiếp theo

                # 4. Lưu đề xuất hợp lệ vào database
                # Chỉ lưu nếu AI trả về ít nhất keywords hoặc template text
                if suggested_keywords or suggested_template:
                    print(f"INFO: (Task) AI suggested for ID {history_id}: kw='{str(suggested_keywords)[:50]}...', cat='{suggested_category}', ref='{suggested_template_ref}', tpl='{str(suggested_template)[:50]}...'")
                    source_examples = {'history_ids': [history_id], 'run_type': 'background', 'persona_used': persona_id_for_suggestion}

                    # Gọi hàm DB đã cập nhật để lưu
                    try:
                         added = db.add_suggestion(
                             keywords=suggested_keywords,
                             category=suggested_category,
                             template_ref=suggested_template_ref,
                             template_text=suggested_template,
                             source_examples=source_examples
                         )
                         if added:
                             suggestions_added += 1
                             print(f"INFO: (Task) Suggestion saved successfully from interaction {history_id}.")
                         else:
                             # Lỗi logic bên trong add_suggestion hoặc lỗi DB không bắt được Exception
                             print(f"ERROR: (Task) Failed to save suggestion from interaction {history_id} (db.add_suggestion returned False).")
                    except Exception as db_add_err:
                         print(f"ERROR: (Task) Exception calling db.add_suggestion for ID {history_id}: {db_add_err}")
                         print(traceback.format_exc())
                         # Có thể dừng lại hoặc tiếp tục tùy chiến lược xử lý lỗi
                else:
                     print(f"DEBUG: (Task) AI did not generate a valid suggestion (keywords or template text) for interaction {history_id}.")
                     # Không có gì để lưu, nhưng interaction này đã được xử lý

            # --- Kết thúc vòng lặp ---

            # 5. Cập nhật trạng thái last_processed_id sau khi xử lý xong batch
            # Chỉ cập nhật nếu ID lớn nhất trong batch này lớn hơn ID đã xử lý trước đó
            if max_processed_id_in_batch > last_processed_id:
                print(f"DEBUG: (Task) Updating last_processed_id from {last_processed_id} to {max_processed_id_in_batch} for task {JOB_ID}")
                update_success = db.update_task_state(JOB_ID, max_processed_id_in_batch)
                if not update_success:
                    # Lỗi nghiêm trọng: Lần chạy sau sẽ xử lý lại batch này!
                    print(f"CRITICAL ERROR: (Task {JOB_ID}) FAILED TO UPDATE last_processed_id to {max_processed_id_in_batch}!")
                    # Cần có cơ chế cảnh báo hoặc retry ở đây trong hệ thống thực tế
            else:
                # Trường hợp này xảy ra nếu không có interaction mới nào được tìm thấy hoặc
                # tất cả interaction mới đều bị lỗi trước khi ID max được cập nhật
                print(f"DEBUG: (Task) No new interactions were fully processed beyond ID {last_processed_id}. State not updated.")


            print(f"INFO: (Task {JOB_ID}) Processed {processed_count}/{interactions_found_count} interactions found. Added {suggestions_added} new suggestions.")
            print(f"--- Finishing background task: {JOB_ID} ---")

        except Exception as e:
             # Bắt các lỗi không mong muốn xảy ra trong quá trình chạy tác vụ
             print(f"CRITICAL ERROR during background task {JOB_ID}: {e}")
             print(traceback.format_exc())
             print(f"--- Finishing background task: {JOB_ID} (with CRITICAL ERROR) ---")

    # Kết thúc khối app_context

# Có thể thêm các hàm tác vụ nền khác ở đây
# def another_background_task():
#     with current_app.app_context():
#        print("Another task running...")
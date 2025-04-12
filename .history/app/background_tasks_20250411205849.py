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

# === Thay thế hàm này trong backup/app/background_tasks.py ===
# (Nhớ giữ lại các import cần thiết: current_app, time, datetime, timedelta, traceback, ai_service)

# --- Hằng số JOB_ID vẫn cần ---
JOB_ID = 'suggestion_job'

def analyze_interactions_and_suggest():
    """
    [PHIÊN BẢN DEBUG] Chạy logic phân tích với dữ liệu giả lập, bỏ qua DB.
    """
    print(f"\n\n!!!!!! DEBUG: TASK {JOB_ID} EXECUTED AT {datetime.now()} !!!!!!\n\n")
    app = current_app._get_current_object()
    if not app:
        print(f"ERROR (Task {JOB_ID} - Debug): Cannot get Flask app instance.")
        return

    with app.app_context():
        print(f"\n--- Starting background task (DEBUG MODE - SIMULATED DATA): {JOB_ID} --- ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")

        # Lấy Persona ID từ config (vẫn cần)
        persona_id_for_suggestion = current_app.config.get('SUGGESTION_ANALYSIS_PERSONA_ID', 'rule_suggester')
        print(f"DEBUG: (Task - Debug) Using Persona ID for suggestion: {persona_id_for_suggestion}")

        # ----- Giả lập Dữ liệu -----
        last_processed_id = 0 # Giả sử bắt đầu từ 0
        print(f"DEBUG: (Task - Debug) Simulating last_processed_id = {last_processed_id}")

        # Tạo 1-2 interaction giả lập để test
        simulated_interactions = [
            {
                'history_id': 999991, # ID giả > last_processed_id
                'received_text': "Shop ơi giá sao ạ?",
                'sent_text': "Dạ sản phẩm này giá 100k bạn nhé.", # Phản hồi giả định do AI tạo
                'detected_user_intent': 'price_query',
                'stage_id': 'providing_info',
                'strategy_id': 'default_strategy'
            },
            # Thêm interaction khác nếu muốn test nhiều
            # {
            #    'history_id': 999992,
            #    'received_text': "Ship về Hà Nội mất bao lâu?",
            #    'sent_text': "Dạ thường mất 2-3 ngày ạ.",
            #    'detected_user_intent': 'shipping_query',
            #    'stage_id': 'providing_info',
            #    'strategy_id': 'default_strategy'
            # },
        ]
        interactions = simulated_interactions # Sử dụng dữ liệu giả lập
        interactions_found_count = len(interactions)
        print(f"INFO: (Task - Debug) Using {interactions_found_count} simulated interactions.")

        # Khởi tạo biến theo dõi
        suggestions_added = 0
        processed_count = 0
        max_processed_id_in_batch = last_processed_id # Khởi tạo

        try:
            # 3. Lặp qua các interaction giả lập và xử lý
            for interaction in interactions:
                processed_count += 1
                history_id = interaction.get('history_id')
                if history_id is None: continue

                max_processed_id_in_batch = max(max_processed_id_in_batch, history_id)
                print(f"DEBUG: (Task - Debug) Analyzing simulated interaction ID: {history_id}")

                # Dữ liệu cho AI Service (lấy từ interaction giả lập)
                interaction_data = {
                    'received_text': interaction.get('received_text'),
                    'sent_text': interaction.get('sent_text'),
                    'user_intent': interaction.get('detected_user_intent'),
                    'stage_id': interaction.get('stage_id'),
                    'strategy_id': interaction.get('strategy_id')
                }

                if not interaction_data['received_text'] or not interaction_data['sent_text']:
                    print(f"WARNING: (Task - Debug) Skipping interaction {history_id} due to missing text.")
                    continue

                # Gọi hàm AI service để lấy đề xuất (phần này vẫn chạy thật)
                try:
                    suggested_keywords, suggested_category, suggested_template_ref, suggested_template = ai_service.suggest_rule_from_interaction(
                        interaction_data=interaction_data,
                        persona_id=persona_id_for_suggestion
                    )
                except Exception as ai_call_err:
                     print(f"ERROR: (Task - Debug) Exception calling ai_service for ID {history_id}: {ai_call_err}")
                     print(traceback.format_exc())
                     continue # Bỏ qua interaction này nếu AI lỗi

                # 4. Chỉ In ra đề xuất (Không lưu vào DB)
                if suggested_keywords or suggested_template:
                    suggestions_added += 1
                    print(f"--- !!! AI SUGGESTION GENERATED (Not Saved) !!! ---")
                    print(f"Source History ID: {history_id}")
                    print(f"Keywords: {suggested_keywords}")
                    print(f"Category: {suggested_category}")
                    print(f"Template Ref: {suggested_template_ref}")
                    print(f"Template Text: {suggested_template}")
                    print(f"--- !!! END AI SUGGESTION !!! ---")
                else:
                     print(f"DEBUG: (Task - Debug) AI did not generate a valid suggestion for interaction {history_id}.")

            # 5. Chỉ In ra trạng thái sẽ được cập nhật (Không cập nhật DB)
            if max_processed_id_in_batch > last_processed_id:
                print(f"DEBUG: (Task - Debug) Would update last_processed_id to {max_processed_id_in_batch} for task {JOB_ID}")
            else:
                print(f"DEBUG: (Task - Debug) No new interactions processed. State would remain {last_processed_id}.")

            print(f"INFO: (Task - Debug) Processed {processed_count}/{interactions_found_count} simulated interactions. Generated {suggestions_added} suggestions (not saved).")
            print(f"--- Finishing background task (DEBUG MODE): {JOB_ID} ---")

        except Exception as e:
             print(f"CRITICAL ERROR during background task {JOB_ID} (DEBUG MODE): {e}")
             print(traceback.format_exc())
             print(f"--- Finishing background task (DEBUG MODE): {JOB_ID} (with CRITICAL ERROR) ---")
# Có thể thêm các hàm tác vụ nền khác ở đây
# def another_background_task():
#     with current_app.app_context():
#        print("Another task running...")
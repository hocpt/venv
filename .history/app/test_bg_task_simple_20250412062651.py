# test_bg_task_simple.py
# File để test APScheduler chạy job độc lập với Flask

import logging
import sys
import time
from datetime import datetime, timedelta
import traceback
from apscheduler.schedulers.background import BackgroundScheduler
import random # Để giả lập AI trả về hoặc không trả về kết quả

# --- Cấu hình Logging cơ bản ---
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG,
                    format='%(asctime)s %(levelname)-8s %(name)-15s : %(message)s')
log = logging.getLogger(__name__)
logging.getLogger('apscheduler').setLevel(logging.DEBUG)

# --- Các Hàm Giả lập (Mock Functions) ---
# Giả lập các hàm database mà tác vụ nền cần gọi

def mock_get_task_state(task_name: str) -> int:
    """Giả lập lấy trạng thái cuối cùng, luôn trả về 0 để test."""
    log.debug(f"[Mock DB] get_task_state called for '{task_name}'. Returning 0.")
    return 0

def mock_get_interactions_for_suggestion(min_history_id: int, status_filter: list = None, limit: int = 100) -> list[dict]:
    """Giả lập trả về một danh sách interaction mẫu."""
    log.debug(f"[Mock DB] get_interactions_for_suggestion called (min_id={min_history_id}, status={status_filter}, limit={limit}).")
    # Chỉ trả về data nếu min_history_id là 0 (lần chạy đầu) để test vòng lặp
    if min_history_id == 0:
        return [
            {
                'history_id': 101, # ID lớn hơn min_history_id
                'received_text': "Giá sao shop?",
                'sent_text': "Dạ giá 150k ạ",
                'detected_user_intent': 'price_query',
                'stage_id': 'providing_info',
                'strategy_id': 'default_strategy'
            },
            {
                'history_id': 102,
                'received_text': "Cảm ơn shop nhiều",
                'sent_text': "Không có gì ạ ^^",
                'detected_user_intent': 'compliment',
                'stage_id': 'closing',
                'strategy_id': 'default_strategy'
            }
        ]
    else:
        # Giả lập không có interaction mới ở các lần chạy sau
        log.debug("[Mock DB] No new interactions to return.")
        return []

def mock_add_suggestion(keywords: str | None, category: str | None, template_ref: str | None, template_text: str | None, source_examples: dict) -> bool:
    """Giả lập việc thêm suggestion thành công."""
    log.info(f"[Mock DB] add_suggestion called. SUCCESS. Data: kw='{keywords}', cat='{category}', ref='{template_ref}', tpl='{template_text}', src='{source_examples}'")
    return True

def mock_update_task_state(task_name: str, last_processed_id: int) -> bool:
    """Giả lập việc cập nhật trạng thái thành công."""
    log.info(f"[Mock DB] update_task_state called for '{task_name}'. SUCCESS. Setting last_processed_id to {last_processed_id}.")
    return True

def mock_suggest_rule_from_interaction(interaction_data: dict, persona_id: str) -> tuple[str | None, str | None, str | None, str | None]:
    """Giả lập hàm AI trả về kết quả."""
    log.debug(f"[Mock AI] suggest_rule_from_interaction called for persona '{persona_id}'.")
    # Giả lập AI đôi khi trả về kết quả, đôi khi không
    if random.choice([True, True, False]): # Tỷ lệ 2/3 thành công
        kw = f"kw_{interaction_data.get('detected_user_intent', 'unknown')}"
        cat = interaction_data.get('detected_user_intent', 'other')
        ref = f"ref_{cat}"
        txt = f"Suggested template for {interaction_data.get('received_text', '')}"
        log.debug(f"[Mock AI] Returning suggestion: ({kw}, {cat}, {ref}, {txt})")
        return kw, cat, ref, txt
    else:
        log.debug("[Mock AI] Returning NO suggestion.")
        return None, None, None, None

# === Hàm Logic Tác vụ (Copy từ background_tasks.py và sửa đổi để dùng mock) ===
# Chúng ta copy logic vào đây để không phụ thuộc vào Flask context (current_app)

JOB_ID_TEST = 'suggestion_job_test' # Dùng ID khác để test

def analyze_interactions_and_suggest_mocked():
    """Phiên bản tác vụ nền dùng hàm mock, không cần Flask app context."""
    print(f"\n--- Starting Mocked Task: {JOB_ID_TEST} --- ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")

    persona_id_for_suggestion = 'mock_rule_suggester' # Dùng ID giả lập
    print(f"DEBUG: (Mock Task) Using Persona ID: {persona_id_for_suggestion}")

    last_processed_id = 0
    max_processed_id_in_batch = 0
    suggestions_added = 0
    interactions_found_count = 0
    processed_count = 0

    try:
        # 1. Lấy trạng thái (dùng hàm mock)
        last_processed_id = mock_get_task_state(JOB_ID_TEST) or 0
        max_processed_id_in_batch = last_processed_id
        print(f"DEBUG: (Mock Task) Fetched last_processed_id = {last_processed_id}")

        # 2. Lấy interactions (dùng hàm mock)
        limit = 10 # Giả lập limit
        status_filter = ['success_ai'] # Giả lập status
        print(f"DEBUG: (Mock Task) Fetching max {limit} interactions with status {status_filter} after ID {last_processed_id}...")
        interactions = mock_get_interactions_for_suggestion(
            min_history_id=last_processed_id,
            status_filter=status_filter,
            limit=limit
        )

        if not interactions: # Kiểm tra list rỗng (hàm mock trả về [] thay vì None)
             print(f"INFO: (Mock Task) No new interactions found.")
             print(f"--- Finishing Mocked Task: {JOB_ID_TEST} (No new data) ---")
             return

        interactions_found_count = len(interactions)
        print(f"INFO: (Mock Task) Found {interactions_found_count} interactions to analyze.")

        # 3. Lặp và xử lý
        for interaction in interactions:
            processed_count += 1
            history_id = interaction.get('history_id')
            if history_id is None: continue

            max_processed_id_in_batch = max(max_processed_id_in_batch, history_id)
            print(f"DEBUG: (Mock Task) Analyzing interaction ID: {history_id}")
            interaction_data = {k: interaction.get(k) for k in ['received_text', 'sent_text', 'detected_user_intent', 'stage_id', 'strategy_id']}

            if not interaction_data['received_text'] or not interaction_data['sent_text']:
                print(f"WARNING: (Mock Task) Skipping interaction {history_id} due to missing text.")
                continue

            # Gọi hàm AI mock
            try:
                suggested_keywords, suggested_category, suggested_template_ref, suggested_template = mock_suggest_rule_from_interaction(
                    interaction_data=interaction_data,
                    persona_id=persona_id_for_suggestion
                )
            except Exception as ai_call_err:
                 print(f"ERROR: (Mock Task) Exception calling mock_suggest_rule: {ai_call_err}")
                 continue

            # 4. Lưu đề xuất (dùng hàm mock)
            if suggested_keywords or suggested_template:
                source_examples = {'history_ids': [history_id], 'run_type': 'mock_background'}
                try:
                    added = mock_add_suggestion(
                        keywords=suggested_keywords, category=suggested_category,
                        template_ref=suggested_template_ref, template_text=suggested_template,
                        source_examples=source_examples
                    )
                    if added: suggestions_added += 1
                except Exception as db_add_err:
                     print(f"ERROR: (Mock Task) Exception calling mock_add_suggestion: {db_add_err}")
            else:
                 print(f"DEBUG: (Mock Task) Mock AI did not generate suggestion for interaction {history_id}.")

        # 5. Cập nhật trạng thái (dùng hàm mock)
        if max_processed_id_in_batch > last_processed_id:
            print(f"DEBUG: (Mock Task) Updating last_processed_id to {max_processed_id_in_batch} for task {JOB_ID_TEST}")
            update_success = mock_update_task_state(JOB_ID_TEST, max_processed_id_in_batch)
            if not update_success: print(f"ERROR: (Mock Task) Failed to update task state!")

        print(f"INFO: (Mock Task) Processed {processed_count}/{interactions_found_count}. Generated {suggestions_added} suggestions (mocked).")
        print(f"--- Finishing Mocked Task: {JOB_ID_TEST} ---")

    except Exception as e:
         print(f"CRITICAL ERROR during background task {JOB_ID_TEST} (Mocked): {e}")
         print(traceback.format_exc())
         print(f"--- Finishing Mocked Task: {JOB_ID_TEST} (with CRITICAL ERROR) ---")

# === Phần Chính Chạy Scheduler Độc Lập ===
if __name__ == '__main__':
    log.info("--- Starting Standalone APScheduler Test with Mocked Task ---")
    scheduler = BackgroundScheduler(daemon=True) # Chạy nền
    log.info("--- Scheduler Initialized (BackgroundScheduler) ---")

    try:
        # Thêm job test chạy hàm logic đã được mock
        scheduler.add_job(
            id=JOB_ID_TEST,
            func=analyze_interactions_and_suggest_mocked, # <<< Gọi hàm đã mock
            trigger='interval',
            seconds=10, # Chạy mỗi 10 giây để test
            replace_existing=True
        )
        log.info("--- Test job added ---")

        # Bắt đầu scheduler
        scheduler.start()
        log.info("--- Scheduler started. Keeping main thread alive... (Press Ctrl+C to stop) ---")

        # Giữ script chạy
        while True:
            time.sleep(2)

    except (KeyboardInterrupt, SystemExit):
        log.info("\n--- Shutting down scheduler... ---")
        scheduler.shutdown()
        log.info("--- Scheduler shut down. Exiting. ---")
    except Exception as e:
        log.error(f"\n--- An error occurred: {e} ---")
        logging.exception("Error during scheduler setup or run:")
        if scheduler.running:
             scheduler.shutdown()
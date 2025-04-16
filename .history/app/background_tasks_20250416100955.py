# app/background_tasks.py
import time
import traceback
import random
from datetime import datetime, timedelta
from flask import Flask, current_app
import database as db
import ai_service
import importlib
from apscheduler.jobstores.base import JobLookupError
from dotenv import load_dotenv
# Cần cách để lấy create_app từ thư mục cha hoặc cấu trúc dự án
# Ví dụ: Giả sử run.py ở cùng cấp với thư mục app
import sys
import os
# Import các thành phần cần thiết từ Flask và ứng dụng
# --- Import các module của ứng dụng (Bỏ try...except) ---
print("DEBUG (scheduler_runner): Attempting application imports...")
from . import database as db
from .background_tasks import run_ai_conversation_simulation, analyze_interactions_and_suggest, approve_all_suggestions_task
from . import create_app
# Thêm lệnh kiểm tra ngay sau import
if db and run_ai_conversation_simulation and analyze_interactions_and_suggest and approve_all_suggestions_task and create_app:
    print("INFO (scheduler_runner): Application modules imported successfully.")
    _imports_successful = True
else:
    # Trường hợp này không nên xảy ra nếu import thành công, nhưng để phòng ngừa
    print("CRITICAL ERROR (scheduler_runner): One or more application modules seem invalid after import.")
    _imports_successful = False

# --- Constants cho Suggestion Job ---
SUGGESTION_JOB_ID = 'suggestion_job'
DEFAULT_STATUS_TO_ANALYZE = ['success_ai', 'success_ai_sim_A', 'success_ai_sim_B'] # <<< Bao gồm cả status mô phỏng
DEFAULT_PROCESSING_LIMIT = 50 # Giới hạn số lượng xử lý mỗi lần chạy suggestion

# =============================================
# === TÁC VỤ NỀN: PHÂN TÍCH VÀ ĐỀ XUẤT LUẬT ===
# =============================================
def analyze_interactions_and_suggest():
    """
    Tác vụ nền phân tích các tương tác thành công (thực tế và mô phỏng)
    để đề xuất keywords và template mới. Tự tạo app context khi chạy.
    """
    job_id_log = SUGGESTION_JOB_ID # Dùng constant
    print(f"\n--- Starting background task analyze: {job_id_log} --- ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    start_time = time.time()

    # --- Tạo App Context Tạm Thời ---
    if not create_app:
         print(f"CRITICAL ERROR ({job_id_log}): create_app function not available. Cannot create context.")
         return
    temp_app = None
    try:
        print(f"DEBUG ({job_id_log}): Creating temporary app instance...")
        temp_app = create_app()
        if not temp_app: raise Exception("Failed to create temporary Flask app instance.")
    except Exception as creation_err:
        print(f"CRITICAL ERROR ({job_id_log}): Cannot create Flask app context: {creation_err}")
        return

    # --- Chạy Logic Bên Trong Context ---
    with temp_app.app_context():
        print(f"DEBUG ({job_id_log}): Entered app context.")
        if not db or not ai_service:
            print(f"ERROR ({job_id_log}): DB or AI service module not available.")
            return

        # Lấy cấu hình từ current_app
        persona_id_for_suggestion = current_app.config.get('SUGGESTION_ANALYSIS_PERSONA_ID', 'rule_suggester')
        status_filter = current_app.config.get('STATUS_TO_ANALYZE_SUGGEST', ['success_ai', 'success_ai_sim_A', 'success_ai_sim_B']) # <<< Dùng list đã cập nhật
        limit = current_app.config.get('SUGGESTION_PROCESSING_LIMIT', DEFAULT_PROCESSING_LIMIT)

        print(f"DEBUG ({job_id_log}): Using Persona ID: {persona_id_for_suggestion}")
        print(f"DEBUG ({job_id_log}): Analyzing statuses: {status_filter}, Limit: {limit}")

        # Khởi tạo biến theo dõi
        last_processed_id = 0
        max_processed_id_in_batch = 0
        suggestions_added = 0
        interactions_found_count = 0
        processed_count = 0

        try:
            # 1. Lấy trạng thái xử lý cuối cùng từ DB
            last_processed_id = db.get_task_state(job_id_log) or 0
            max_processed_id_in_batch = last_processed_id
            print(f"DEBUG ({job_id_log}): Fetched last_processed_id = {last_processed_id}")

            # 2. Lấy các tương tác MỚI HƠN ID đó để phân tích
            print(f"DEBUG ({job_id_log}): Fetching max {limit} interactions with status {status_filter} after ID {last_processed_id}...")
            interactions = db.get_interactions_for_suggestion(
                min_history_id=last_processed_id,
                status_filter=status_filter,
                limit=limit
            )

            if interactions is None:
                 print(f"ERROR ({job_id_log}): Could not fetch interactions from DB.")
                 # Không cập nhật last_processed_id nếu lỗi DB
                 return

            interactions_found_count = len(interactions)
            if not interactions:
                 print(f"INFO ({job_id_log}): No new interactions found matching criteria.")
                 # Vẫn cập nhật last_run_timestamp nếu task chạy mà không có dữ liệu mới
                 db.update_task_state(job_id_log, max_processed_id_in_batch)
                 print(f"--- Finishing background task: {job_id_log} (No new data) ---")
                 return

            print(f"INFO ({job_id_log}): Found {interactions_found_count} interactions to analyze.")

            # 3. Lặp qua các tương tác tìm được và xử lý
            for interaction in interactions:
                processed_count += 1
                history_id = interaction.get('history_id')
                if history_id is None: continue

                # Luôn cập nhật ID lớn nhất đã thấy trong batch này
                max_processed_id_in_batch = max(max_processed_id_in_batch, history_id)

                print(f"DEBUG ({job_id_log}): Analyzing interaction ID: {history_id}")
                # Lấy đủ dữ liệu cần thiết cho prompt suggest_rule
                interaction_data = {
                    'received_text': interaction.get('received_text'),
                    'sent_text': interaction.get('sent_text'),
                    'user_intent': interaction.get('detected_user_intent'), # Intent của user trong lượt đó
                    'stage_id': interaction.get('stage_id'),
                    'strategy_id': interaction.get('strategy_id')
                    # Có thể thêm các trường khác nếu prompt cần
                }

                if not interaction_data['received_text'] or not interaction_data['sent_text']:
                    print(f"WARNING ({job_id_log}): Skipping interaction {history_id} due to missing text.")
                    continue

                # Gọi hàm AI service để đề xuất (đã được refactor)
                try:
                    # Hàm này trả về 4 giá trị
                    suggested_keywords, suggested_category, suggested_template_ref, suggested_template = ai_service.suggest_rule_from_interaction(
                        interaction_data=interaction_data,
                        persona_id=persona_id_for_suggestion # Dùng persona chuyên đề xuất
                    )
                except Exception as ai_call_err:
                     print(f"ERROR ({job_id_log}): AI call failed for ID {history_id}: {ai_call_err}")
                     continue # Bỏ qua interaction này

                # 4. Lưu đề xuất hợp lệ vào database
                # Chỉ cần keywords hoặc template là đủ để lưu
                if suggested_keywords or suggested_template:
                    print(f"INFO ({job_id_log}): Suggestion from ID {history_id}: kw='{str(suggested_keywords)[:50]}...', cat='{suggested_category}', ref='{suggested_template_ref}', tpl='{str(suggested_template)[:50]}...'")
                    source_examples = {
                        'history_ids': [history_id],
                        'run_type': 'background_suggestion_job',
                        'persona_used': persona_id_for_suggestion,
                        'timestamp': datetime.now().isoformat()
                    }
                    try:
                         # Hàm add_suggestion nhận đủ 4 tham số đề xuất
                         added = db.add_suggestion(
                             keywords=suggested_keywords,
                             category=suggested_category,
                             template_ref=suggested_template_ref,
                             template_text=suggested_template,
                             source_examples=source_examples
                         )
                         if added:
                             suggestions_added += 1
                             print(f"INFO ({job_id_log}): Suggestion saved from interaction {history_id}.")
                         else:
                             print(f"ERROR ({job_id_log}): Failed to save suggestion from interaction {history_id} (DB function returned False).")
                    except Exception as db_add_err:
                         print(f"ERROR ({job_id_log}): DB exception saving suggestion from {history_id}: {db_add_err}")
                         print(traceback.format_exc()) # In traceback để debug lỗi DB
                else:
                     print(f"DEBUG ({job_id_log}): AI did not generate valid suggestion for interaction {history_id}.")

            # --- Kết thúc vòng lặp ---

            # 5. Cập nhật trạng thái last_processed_id (ID lớn nhất đã xử lý trong batch này)
            # Chỉ cập nhật nếu thực sự có xử lý interaction mới
            if max_processed_id_in_batch > last_processed_id:
                print(f"DEBUG ({job_id_log}): Updating last_processed_id from {last_processed_id} to {max_processed_id_in_batch} for task {job_id_log}")
                update_success = db.update_task_state(job_id_log, max_processed_id_in_batch)
                if not update_success:
                    # Lỗi nghiêm trọng nếu không cập nhật được state, có thể dẫn đến xử lý lặp lại
                    print(f"CRITICAL ERROR ({job_id_log}): FAILED TO UPDATE last_processed_id to {max_processed_id_in_batch}! Next run might reprocess interactions.")
            else:
                # Nếu không có interaction mới nào có ID lớn hơn, chỉ cập nhật timestamp
                print(f"DEBUG ({job_id_log}): No interactions with higher ID processed. Updating last run time only.")
                db.update_task_state(job_id_log, last_processed_id) # Chỉ cập nhật timestamp

            end_time = time.time()
            print(f"INFO ({job_id_log}): Processed {processed_count}/{interactions_found_count}. Added {suggestions_added} new suggestions.")
            print(f"--- Finishing background task: {job_id_log} --- (Duration: {end_time - start_time:.2f}s)")

        except Exception as e:
             # Bắt lỗi tổng quát trong quá trình xử lý
             print(f"CRITICAL ERROR during background task {job_id_log}: {e}")
             print(traceback.format_exc())
             # Không cập nhật last_processed_id khi có lỗi nghiêm trọng để thử lại sau
             print(f"--- Finishing background task: {job_id_log} (with CRITICAL ERROR) ---")
    # <<< Kết thúc with temp_app.app_context() >>>

# =============================================
# === TÁC VỤ NỀN: DUYỆT TẤT CẢ ĐỀ XUẤT (ĐÃ SỬA) ===
# =============================================
def approve_all_suggestions_task():
    """
    Tác vụ nền để tự động phê duyệt tất cả suggestions đang ở trạng thái 'pending'.
    Tự tạo app context khi chạy.
    """
    task_id_log = f"approve_all_task_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    print(f"\n--- Starting background task approve_all: {task_id_log} --- ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    start_time = time.time()

    # --- Tạo App Context ---
    if not create_app:
        print(f"CRITICAL ERROR ({task_id_log}): create_app not available.")
        return
    temp_app = None
    try:
        print(f"DEBUG ({task_id_log}): Creating temporary app instance...")
        temp_app = create_app()
        if not temp_app: raise Exception("Failed to create Flask app instance.")
    except Exception as creation_err:
        print(f"CRITICAL ERROR ({task_id_log}): Cannot create app context: {creation_err}")
        return

    # Chạy logic bên trong context
    with temp_app.app_context():
        print(f"DEBUG ({task_id_log}): Entered app context.")
        if not db:
            print(f"ERROR ({task_id_log}): DB module not available.")
            return

        approved_count = 0
        failed_count = 0
        skipped_count = 0
        pending_suggestions = []

        try:
            # 1. Lấy tất cả pending suggestions
            print(f"DEBUG ({task_id_log}): Fetching all pending suggestions...")
            pending_suggestions = db.get_pending_suggestions()

            if pending_suggestions is None:
                print(f"ERROR ({task_id_log}): Failed to fetch pending suggestions from DB.")
                return
            if not pending_suggestions:
                print(f"INFO ({task_id_log}): No pending suggestions found to approve.")
                print(f"--- Finishing background task: {task_id_log} (No data) ---")
                return

            print(f"INFO ({task_id_log}): Found {len(pending_suggestions)} suggestions to process.")

            # 2. Lặp qua và phê duyệt từng cái
            for suggestion in pending_suggestions:
                suggestion_id = suggestion.get('suggestion_id')
                if suggestion_id is None: continue # Bỏ qua nếu không có ID

                print(f"DEBUG ({task_id_log}): Processing suggestion ID: {suggestion_id}")

                # Lấy dữ liệu đề xuất gốc
                keywords = suggestion.get('suggested_keywords')
                category = suggestion.get('suggested_category')
                template_ref = suggestion.get('suggested_template_ref')
                template_text = suggestion.get('suggested_template_text')
                priority = 0 # Priority mặc định khi duyệt hàng loạt
                notes = f"Bulk Approved from AI suggestion #{suggestion_id}."

                # Validate dữ liệu tối thiểu (cả 3 đều cần)
                if not keywords or not template_ref or not template_text:
                    print(f"WARNING ({task_id_log}): Skipping suggestion {suggestion_id} due to missing required fields (keywords, ref, text).")
                    skipped_count += 1
                    # Cập nhật status lỗi nếu muốn
                    try: db.update_suggestion_status(suggestion_id, 'error_missing_data')
                    except Exception as e: print(f"WARN ({task_id_log}): Failed to update status for skipped sugg {suggestion_id}: {e}")
                    continue

                # Thực hiện phê duyệt (trong try-except cho từng cái)
                try:
                    # a. Thêm Template + Variation (Hàm này đã xử lý ON CONFLICT)
                    added_template_ref = db.add_new_template(
                        template_ref=template_ref,
                        first_variation_text=template_text,
                        description=f"AI suggested, bulk approval #{suggestion_id}",
                        category=category if category else None
                    )
                    if not added_template_ref:
                         # Thường lỗi này ít xảy ra nếu hàm DB xử lý tốt, nhưng vẫn kiểm tra
                         raise Exception(f"Failed to add/ensure template/variation for ref '{template_ref}'")

                    # b. Thêm Rule
                    rule_added = db.add_new_rule(
                        keywords=keywords, category=category if category else None,
                        template_ref=added_template_ref, # Dùng ref trả về (có thể là cái cũ nếu ON CONFLICT)
                        priority=priority, notes=notes
                    )
                    if not rule_added:
                         # Có thể do lỗi DB khác?
                         raise Exception(f"Failed to add rule for template ref '{added_template_ref}'")

                    # c. Cập nhật Status suggestion thành approved
                    status_updated = db.update_suggestion_status(suggestion_id, 'approved')
                    if not status_updated:
                         # Không quá nghiêm trọng, ghi log warning
                         print(f"WARNING ({task_id_log}): Rule/Template created for suggestion {suggestion_id}, but failed to update suggestion status.")

                    print(f"INFO ({task_id_log}): Successfully approved suggestion {suggestion_id}.")
                    approved_count += 1

                except Exception as approve_err:
                     # Nếu có lỗi khi phê duyệt 1 suggestion -> ghi log lỗi và tiếp tục cái khác
                     print(f"ERROR ({task_id_log}): Failed to approve suggestion {suggestion_id}: {approve_err}")
                     # Cập nhật status thành error để không thử lại?
                     try: db.update_suggestion_status(suggestion_id, f'error_bulk_approve')
                     except Exception as e: print(f"WARN ({task_id_log}): Failed to update error status for sugg {suggestion_id}: {e}")
                     failed_count += 1
                     continue # Đi tiếp suggestion khác

            # 3. Ghi log tổng kết
            end_time = time.time()
            print(f"INFO ({task_id_log}): Processing complete. Approved: {approved_count}, Failed: {failed_count}, Skipped: {skipped_count}.")
            print(f"--- Finishing background task: {task_id_log} --- (Duration: {end_time - start_time:.2f}s)")

        except Exception as e:
            # Lỗi tổng quát khi chạy task (ví dụ lỗi khi get_pending_suggestions)
            print(f"CRITICAL ERROR during background task {task_id_log}: {e}")
            print(traceback.format_exc())
            print(f"--- Finishing background task: {task_id_log} (with CRITICAL ERROR) ---")
    # <<< Kết thúc with app.app_context() >>>


# =============================================
# === HÀM MÔ PHỎNG HỘI THOẠI AI (PHIÊN BẢN CẬP NHẬT) ===
# =============================================

# app/background_tasks.py
# ... (các import và các hàm khác giữ nguyên) ...

# =============================================
# === HÀM MÔ PHỎNG HỘI THOẠI AI (PHIÊN BẢN ĐẦY ĐỦ - SỬA LỖI NAMEERROR) ===
# =============================================
def run_ai_conversation_simulation(
        persona_a_id: str,           # Tham số 1
        persona_b_id: str,           # Tham số 2
        strategy_id: str,            # Tham số 3
        max_turns: int,              # Tham số 4
        starting_prompt: str | None, # Tham số 5
        log_account_id_a: str,       # Tham số 6 <<< Đảm bảo có ở đây
        log_account_id_b: str,       # Tham số 7 <<< Đảm bảo có ở đây
        sim_thread_id_base: str,     # Tham số 8
        sim_goal: str                # Tham số 9
    ):
    """
    Tác vụ nền để mô phỏng cuộc hội thoại giữa hai AI Persona với cấu hình động,
    có theo dõi Strategy và Stage. Tự tạo app context khi chạy.
    """
    task_id_log = f"{sim_thread_id_base}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    print(f"\n--- Starting AI Conversation Simulation: {task_id_log} ---")
    # In ra các tham số nhận được để kiểm tra
    print(f"    Received Params: PA={persona_a_id}, PB={persona_b_id}, Strat={strategy_id}, Turns={max_turns}")
    print(f"    Log Accounts: LogA={log_account_id_a}, LogB={log_account_id_b}") # <<< Log tham số account
    print(f"    StartPrompt='{starting_prompt[:50] if starting_prompt else '[Default]' }...', Goal={sim_goal}")
    start_time = time.time()

    # --- Tạo App Context Tạm Thời ---
    if not create_app:
         print(f"CRITICAL ERROR ({task_id_log}): create_app not available.")
         return
    temp_app = None
    try:
        print(f"DEBUG ({task_id_log}): Creating temporary app instance...")
        temp_app = create_app()
        if not temp_app: raise Exception("Failed to create temporary Flask app instance.")
    except Exception as creation_err:
        print(f"CRITICAL ERROR ({task_id_log}): Cannot create app context: {creation_err}")
        return

    # --- Chạy Logic Mô Phỏng Bên Trong Context ---
    with temp_app.app_context():
        print(f"DEBUG ({task_id_log}): Entered app context.")
        if not db or not ai_service:
             print(f"ERROR ({task_id_log}): DB or AI service module not available.")
             return

        # --- === Sử dụng Tham số Truyền vào === ---
        # Các tham số đã được truyền vào hàm, không cần gán lại vào biến viết hoa nữa
        SIM_THREAD_ID = f"sim_thread_{task_id_log}"
        SIM_APP_NAME = 'simulation'
        # Chuyển starting_prompt thành giá trị mặc định nếu None hoặc rỗng
        actual_starting_prompt = starting_prompt if starting_prompt else "Xin chào!"

        # --- Lấy thông tin Strategy và Stage ban đầu ---
        current_stage_id = None
        try:
            initial_stage_id = db.get_initial_stage(strategy_id)
            if not initial_stage_id:
                print(f"ERROR ({task_id_log}): Strategy '{strategy_id}' not found or has no initial stage. Aborting.")
                return
            current_stage_id = initial_stage_id
            print(f"DEBUG ({task_id_log}): Initial Stage set to '{current_stage_id}' for strategy '{strategy_id}'.")
        except Exception as db_err:
            print(f"ERROR ({task_id_log}): DB error fetching initial stage for strategy '{strategy_id}': {db_err}. Aborting.")
            return

        # --- Lấy thông tin chi tiết Personas ---
        try:
             persona_a_details = db.get_persona_details(persona_a_id)
             persona_b_details = db.get_persona_details(persona_b_id)
             if not persona_a_details or not persona_b_details:
                 print(f"ERROR ({task_id_log}): Could not find persona details for {persona_a_id} or {persona_b_id}. Aborting.")
                 return
        except Exception as db_err:
             print(f"ERROR ({task_id_log}): DB error fetching persona details: {db_err}. Aborting.")
             return

        # --- === Vòng Lặp Hội Thoại === ---
        conversation_history_text = ""
        last_message = actual_starting_prompt # Sử dụng câu chào đã xử lý
        current_speaker_persona_id = persona_a_id # A nói trước
        turns_taken = 0
        detected_intent_for_next_turn = "start"

        while turns_taken < max_turns * 2:
            # Xác định người nói và ID log tương ứng trong lượt này
            is_persona_a_turn = (current_speaker_persona_id == persona_a_id)
            persona_id_to_use = persona_a_id if is_persona_a_turn else persona_b_id
            opponent_persona_id = persona_b_id if is_persona_a_turn else persona_a_id
            turn_status_code = 'success_ai_sim_A' if is_persona_a_turn else 'success_ai_sim_B'
            speaker_label = "Persona A" if is_persona_a_turn else "Persona B"
            opponent_label = "Persona B" if is_persona_a_turn else "Persona A"
            # <<< SỬ DỤNG THAM SỐ ĐÚNG Ở ĐÂY >>>
            account_id_for_this_turn_log = log_account_id_a if is_persona_a_turn else log_account_id_b

            turns_taken += 1 # Tăng số lượt đã thực hiện
            print(f"\nDEBUG ({task_id_log}): --- Turn {(turns_taken + 1) // 2} / {max_turns} ({speaker_label} speaking) ---")
            print(f"    Current Stage: {current_stage_id}")
            print(f"    Input ('{last_message[:100]}...'), Prev Intent: {detected_intent_for_next_turn}")
            print(f"    Using Log Account: {account_id_for_this_turn_log}") # <<< Log thêm

            # 1. Chuẩn bị Prompt Data
            prompt_data = {
                "account_platform": SIM_APP_NAME,
                "account_notes": f"Simulated conversation ({sim_goal}) between {persona_a_id} and {persona_b_id}", # <<< Dùng tham số
                "account_goal": sim_goal, # <<< Dùng tham số
                "strategy_id": strategy_id, # <<< Dùng tham số
                "current_stage_id": current_stage_id,
                "user_intent": detected_intent_for_next_turn,
                "formatted_history": conversation_history_text,
                "received_text": last_message
            }

            # 2. Gọi AI Service
            ai_reply, ai_status = None, "error_ai_call_failed" # Khởi tạo
            try:
                ai_reply, ai_status = ai_service.generate_reply_with_ai(prompt_data=prompt_data, persona_id=persona_id_to_use)
            except Exception as ai_call_err:
                print(f"ERROR ({task_id_log}): AI call failed: {ai_call_err}")
                break # Dừng mô phỏng nếu AI lỗi

            # 3. Xử lý kết quả và Ghi Log
            if ai_status.startswith("success") and ai_reply:
                print(f"    {speaker_label} replied: '{ai_reply[:100]}...'")
                history_id = None
                try:
                    history_id = db.log_interaction_received(
                        account_id=account_id_for_this_turn_log, # <<< Dùng biến đã xác định
                        app_name=SIM_APP_NAME, thread_id=SIM_THREAD_ID,
                        received_text=last_message, strategy_id=strategy_id,
                        current_stage_id=current_stage_id, user_intent=detected_intent_for_next_turn
                    )
                    if history_id:
                        db.update_interaction_log(
                            history_id=history_id, sent_text=ai_reply,
                            status=turn_status_code, next_stage_id=current_stage_id
                        )
                    else: print(f"ERROR ({task_id_log}): Failed log received turn {turns_taken}.")
                except Exception as log_err: print(f"ERROR ({task_id_log}): Failed log interaction DB: {log_err}"); break

                # 4. Phát hiện Intent của lời nói VỪA TẠO RA
                detected_intent_for_next_turn = "error"
                try:
                    detected_intent_for_next_turn = ai_service.detect_user_intent_with_ai(text=ai_reply, persona_id=None)
                    print(f"    Intent detected in reply: {detected_intent_for_next_turn}")
                except Exception as intent_err: print(f"ERROR ({task_id_log}): Failed detect intent: {intent_err}")

                # 5. Tìm Transition và Cập nhật Stage
                next_stage_found = None
                try:
                    transition = db.find_transition(current_stage_id, detected_intent_for_next_turn)
                    if transition and transition.get('next_stage_id'): next_stage_found = transition['next_stage_id']
                except Exception as trans_err: print(f"ERROR ({task_id_log}): Error finding transition: {trans_err}")

                # 6. Cập nhật lịch sử, tin nhắn cuối, và stage
                conversation_history_text += f"{opponent_label}: {last_message}\n"
                conversation_history_text += f"{speaker_label}: {ai_reply}\n"
                last_message = ai_reply
                if next_stage_found and next_stage_found != current_stage_id:
                     print(f"    Transitioning Stage: '{current_stage_id}' -> '{next_stage_found}'")
                     current_stage_id = next_stage_found

            else:
                print(f"ERROR ({task_id_log}): {speaker_label} failed (Status: {ai_status}). Ending.")
                break # Dừng vòng lặp nếu AI lỗi

            # 7. Chuyển lượt
            current_speaker_persona_id = opponent_persona_id
            time.sleep(random.randint(1, 3))

        # --- Kết thúc vòng lặp ---
        end_time = time.time()
        print(f"INFO ({task_id_log}): Simulation finished. Total turns attempted: {turns_taken}.") # Sửa log kết thúc
        print(f"--- Finishing background task: {task_id_log} --- (Duration: {end_time - start_time:.2f}s)")
    # <<< Kết thúc with temp_app.app_context() >>>

# ... (Các hàm tác vụ nền khác nếu có) ...

    # <<< Kết thúc with temp_app.app_context() >>>
# app/background_tasks.py
import time
import traceback
import random
from datetime import datetime, timedelta, timezone # Thêm timezone
import pytz # Thêm pytz
import json
try:
    from app import database as db
    from app import ai_service
    print("DEBUG (background_tasks): Imported db and ai_service.")
except ImportError as e:
    print(f"CRITICAL ERROR (background_tasks): Cannot import db or ai_service: {e}")
    db = None
    ai_service = None
try:
    # Vẫn cần Flask và current_app NẾU bạn dùng logger trực tiếp trong các hàm helper CÙNG FILE
    # Nhưng KHÔNG import create_app ở đây
    from flask import Flask, current_app
    # Bỏ: from . import create_app
    # Bỏ: from . import database as db  (đã import ở trên)
    # Bỏ: from . import ai_service (đã import ở trên)
    # Check lại các import khác nếu có
    _imports_successful_bgt = True # Có thể bỏ biến này nếu không cần thiết nữa
except ImportError as e:
    print(f"CRITICAL ERROR (background_tasks): Failed basic Flask import?: {e}.")
    current_app = None # Đặt current_app thành None nếu import Flask lỗi
    _imports_successful_bgt = False
# --- Constants ---
SUGGESTION_JOB_ID = 'suggestion_job'
# Bao gồm cả status từ simulation để job đề xuất có thể học
DEFAULT_STATUS_TO_ANALYZE = ['success_ai', 'success_ai_sim_A', 'success_ai_sim_B']
DEFAULT_PROCESSING_LIMIT = 50

# =============================================
# === TÁC VỤ NỀN: PHÂN TÍCH VÀ ĐỀ XUẤT LUẬT ===
# =============================================
def analyze_interactions_and_suggest():
    """
    Tác vụ nền phân tích các tương tác thành công (thực tế và mô phỏng)
    để đề xuất keywords, category, template_ref, template_text mới.
    Tự tạo app context khi chạy.
    """
    # === Import create_app BÊN TRONG hàm ===
    try:
        from app import create_app
        from flask import current_app # Import current_app ở đây nếu cần logger
    except ImportError:
        print("CRITICAL ERROR (analyze_interactions_and_suggest): Cannot import create_app or current_app! Task cannot run.")
        return
    # ======================================

    job_id_log = SUGGESTION_JOB_ID
    # Dùng print tạm thời ở đây vì chưa có logger
    print(f"\n--- Starting background task: {job_id_log} --- ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    start_time = time.time()

    # --- Tạo App Context Tạm Thời ---
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
        # === Lấy logger SAU KHI có context ===
        logger = current_app.logger
        # ====================================
        logger.debug(f"DEBUG ({job_id_log}): Entered app context.")

        # Kiểm tra module db và ai_service (vẫn cần thiết)
        if not db or not ai_service:
            logger.error(f"ERROR ({job_id_log}): DB or AI service module not available inside context.")
            return

        # Lấy cấu hình từ current_app
        persona_id_for_suggestion = current_app.config.get('SUGGESTION_ANALYSIS_PERSONA_ID', 'rule_suggester')
        status_filter = current_app.config.get('STATUS_TO_ANALYZE_SUGGEST', DEFAULT_STATUS_TO_ANALYZE)
        limit = current_app.config.get('SUGGESTION_PROCESSING_LIMIT', DEFAULT_PROCESSING_LIMIT)
        logger.debug(f"DEBUG ({job_id_log}): Configs - Persona: {persona_id_for_suggestion}, StatusFilter: {status_filter}, Limit: {limit}")

        last_processed_id = 0
        max_processed_id_in_batch = 0
        suggestions_added = 0
        interactions_found_count = 0
        processed_count = 0

        try:
            # 1. Lấy trạng thái xử lý cuối cùng
            last_processed_id = db.get_task_state(job_id_log) or 0
            max_processed_id_in_batch = last_processed_id
            logger.debug(f"DEBUG ({job_id_log}): Last processed ID = {last_processed_id}")

            # 2. Lấy các tương tác mới cần phân tích
            interactions = db.get_interactions_for_suggestion(
                min_history_id=last_processed_id, status_filter=status_filter, limit=limit
            )

            if interactions is None:
                logger.error(f"ERROR ({job_id_log}): Could not fetch interactions from database.")
                return # Dừng nếu lỗi DB

            interactions_found_count = len(interactions)
            if not interactions:
                logger.info(f"INFO ({job_id_log}): No new interactions found to analyze after ID {last_processed_id}.")
                # Chỉ cập nhật timestamp nếu không có gì mới
                db.update_task_state(job_id_log, last_processed_id)
                logger.info(f"--- Finishing: {job_id_log} (No new data) ---")
                return # Kết thúc

            logger.info(f"INFO ({job_id_log}): Found {interactions_found_count} interactions to analyze.")

            # 3. Lặp và xử lý
            for interaction in interactions:
                processed_count += 1
                history_id = interaction.get('history_id')
                if history_id is None: continue

                # Cập nhật ID lớn nhất trong batch này
                max_processed_id_in_batch = max(max_processed_id_in_batch, history_id)
                logger.debug(f"DEBUG ({job_id_log}): Analyzing interaction ID: {history_id}")

                # Chuẩn bị dữ liệu cho AI
                interaction_data = {
                    'received_text': interaction.get('received_text'),
                    'sent_text': interaction.get('sent_text'),
                    'detected_user_intent': interaction.get('detected_user_intent'),
                    'stage_id': interaction.get('stage_id'),
                    'strategy_id': interaction.get('strategy_id')
                }
                if not interaction_data['received_text'] or not interaction_data['sent_text']:
                    logger.warning(f"WARN ({job_id_log}): Skipping interaction {history_id} - missing received or sent text.")
                    continue

                # Gọi AI service
                keywords, category, template_ref, template = None, None, None, None # Khởi tạo
                try:
                    # Hàm này cần trả về tuple 4 giá trị
                    keywords, category, template_ref, template = ai_service.suggest_rule_from_interaction(
                        interaction_data=interaction_data, persona_id=persona_id_for_suggestion
                    )
                except Exception as ai_call_err:
                    logger.error(f"ERROR ({job_id_log}): AI call failed for interaction ID {history_id}: {ai_call_err}", exc_info=True)
                    continue # Bỏ qua interaction này nếu gọi AI lỗi

                # 4. Lưu đề xuất hợp lệ
                if keywords or template: # Chỉ lưu nếu AI trả về ít nhất 1 trong 2
                    logger.info(f"INFO ({job_id_log}): Suggestion from ID {history_id}: kw='{str(keywords)[:50]}...', cat='{category}', ref='{template_ref}', tpl='{str(template)[:50]}...'")
                    source_examples = {
                        'history_ids': [history_id],
                        'run_type': job_id_log,
                        'persona_used': persona_id_for_suggestion,
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    }
                    try:
                        # Hàm add_suggestion cần được kiểm tra lại để đảm bảo hoạt động đúng
                        added = db.add_suggestion(
                            keywords=keywords,
                            category=category,
                            template_ref=template_ref,
                            template_text=template,
                            source_examples=source_examples
                        )
                        if added:
                            suggestions_added += 1
                            logger.info(f"INFO ({job_id_log}): Suggestion saved successfully from interaction {history_id}.")
                        else:
                            # Hàm add_suggestion trả về False (có thể do lỗi logic hoặc DB)
                            logger.error(f"ERROR ({job_id_log}): db.add_suggestion returned False for interaction {history_id}.")
                    except Exception as db_add_err:
                        logger.error(f"ERROR ({job_id_log}): DB exception while saving suggestion from interaction {history_id}: {db_add_err}", exc_info=True)
                else:
                    logger.debug(f"DEBUG ({job_id_log}): No valid suggestion content (keywords or template) returned by AI for interaction {history_id}.")

            # 5. Cập nhật trạng thái last_processed_id sau khi xử lý hết batch
            if max_processed_id_in_batch > last_processed_id:
                logger.info(f"INFO ({job_id_log}): Finished batch, updating last_processed_id for '{job_id_log}' to {max_processed_id_in_batch}")
                update_success = db.update_task_state(job_id_log, max_processed_id_in_batch)
                if not update_success:
                    logger.critical(f"CRITICAL ERROR ({job_id_log}): FAILED TO UPDATE last_processed_id to {max_processed_id_in_batch}!")
            else:
                 # Vẫn cập nhật timestamp nếu không có ID mới nào được xử lý
                 logger.info(f"INFO ({job_id_log}): No new interaction IDs processed, updating timestamp for '{job_id_log}'.")
                 db.update_task_state(job_id_log, last_processed_id)

            end_time = time.time()
            logger.info(f"INFO ({job_id_log}): Task finished. Processed {processed_count}/{interactions_found_count} interactions. Added {suggestions_added} new suggestions.")
            logger.info(f"--- Finishing background task: {job_id_log} --- (Duration: {end_time - start_time:.2f}s)")

        except Exception as e: # Bắt lỗi tổng quát trong quá trình xử lý chính
             # Ghi log lỗi nghiêm trọng kèm traceback
             logger.critical(f"CRITICAL ERROR during task {job_id_log}: {e}", exc_info=True)
             print(f"--- Finishing background task: {job_id_log} (with CRITICAL ERROR) ---")

def approve_all_suggestions_task():
    """
    Tác vụ nền để tự động phê duyệt tất cả suggestions đang 'pending'.
    Tự tạo app context khi chạy.
    """
    # === Import create_app BÊN TRONG hàm ===
    try:
        from app import create_app
        from flask import current_app
    except ImportError:
        print("CRITICAL ERROR (approve_all_suggestions_task): Cannot import create_app or current_app! Task cannot run.")
        return
    # ======================================

    job_id_log = f"approve_all_task_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    # Dùng print tạm thời
    print(f"\n--- Starting background task: {job_id_log} --- ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    start_time = time.time()

    # --- Tạo App Context ---
    temp_app = None
    try:
        temp_app = create_app()
        if not temp_app: raise Exception("Failed to create Flask app instance.")
    except Exception as creation_err:
        print(f"CRITICAL ERROR ({job_id_log}): Cannot create app context: {creation_err}"); return

    # Chạy logic bên trong context
    with temp_app.app_context():
        logger = current_app.logger # Lấy logger
        logger.debug(f"DEBUG ({job_id_log}): Entered app context.")
        if not db: logger.error(f"ERROR ({job_id_log}): DB module not available."); return

        approved_count = 0
        failed_count = 0
        skipped_count = 0
        pending_suggestions = []
        try:
            # 1. Lấy tất cả pending suggestions
            # Hàm này trả về list hoặc None nếu lỗi
            pending_suggestions = db.get_pending_suggestions()
            if pending_suggestions is None:
                logger.error(f"ERROR ({job_id_log}): Failed to fetch pending suggestions from database.")
                return # Dừng nếu lỗi DB
            if not pending_suggestions:
                logger.info(f"INFO ({job_id_log}): No pending suggestions found.")
                logger.info(f"--- Finishing: {job_id_log} (No data) ---")
                return # Kết thúc nếu không có suggestion

            logger.info(f"INFO ({job_id_log}): Found {len(pending_suggestions)} pending suggestions to process.")

            # 2. Lặp và phê duyệt
            for suggestion in pending_suggestions:
                suggestion_id = suggestion.get('suggestion_id')
                keywords = suggestion.get('suggested_keywords')
                category = suggestion.get('suggested_category') # Lấy category
                template_ref = suggestion.get('suggested_template_ref') # Lấy ref
                template_text = suggestion.get('suggested_template_text')

                if not suggestion_id:
                    logger.warning(f"WARN ({job_id_log}): Skipping suggestion with invalid data (missing ID): {suggestion}")
                    skipped_count += 1
                    continue

                logger.debug(f"DEBUG ({job_id_log}): Processing suggestion ID: {suggestion_id}")

                # Kiểm tra các trường bắt buộc cho rule và template
                if not keywords or not template_ref or not template_text:
                    logger.warning(f"WARN ({job_id_log}): Skipping suggestion {suggestion_id} - missing required fields (keywords, template_ref, template_text). Marking as error.")
                    skipped_count += 1
                    try:
                        # Cập nhật status thành lỗi để không xử lý lại
                        db.update_suggestion_status(suggestion_id, 'error_missing_data')
                    except Exception as update_err:
                         logger.error(f"ERROR ({job_id_log}): Failed to mark suggestion {suggestion_id} as error: {update_err}")
                    continue # Bỏ qua suggestion này

                # Bắt đầu xử lý phê duyệt
                try:
                    # a. Thêm Template + Variation (Hàm này cần trả về tuple (bool, message/ref))
                    template_added_success, template_msg_or_ref = db.add_new_template(
                        _template_ref=template_ref,
                        description=f"AI suggested from #{suggestion_id}",
                        category=category if category else None,
                        first_variation_text=template_text
                    )
                    # Hàm add_new_template trả về (True, template_ref) khi thành công
                    if not template_added_success:
                        # template_msg_or_ref lúc này là thông báo lỗi
                        raise Exception(f"Failed to add template/variation '{template_ref}': {template_msg_or_ref}")

                    # Lấy template_ref thực tế (có thể là cái cũ nếu đã tồn tại)
                    actual_template_ref = template_msg_or_ref

                    # b. Thêm Rule mới (Hàm này cần trả về bool)
                    # Hàm add_new_rule đã được sửa để không cần strategy_id
                    rule_added = db.add_new_rule(
                        keywords=keywords,
                        category=category if category else None,
                        template_ref=actual_template_ref, # Dùng ref thực tế
                        priority=0, # Hoặc priority khác nếu muốn
                        notes=f"Bulk Approved from AI suggestion #{suggestion_id}."
                    )
                    if not rule_added:
                        # Có thể đã tồn tại rule giống hệt (nếu có constraint) hoặc lỗi DB
                        # Nên kiểm tra lại constraint UNIQUE của bảng rules
                        logger.warning(f"WARN ({job_id_log}): Could not add rule for template '{actual_template_ref}' (suggestion {suggestion_id}). Rule might already exist or DB error.")
                        # Không raise Exception ở đây, vẫn coi như template đã xử lý, cập nhật status suggestion

                    # c. Cập nhật Status suggestion thành 'approved'
                    status_updated = db.update_suggestion_status(suggestion_id, 'approved')
                    if not status_updated:
                        # Lỗi không nghiêm trọng lắm, ghi log
                        logger.warning(f"WARN ({job_id_log}): Rule/Template created for suggestion {suggestion_id}, but failed to update suggestion status to 'approved'.")

                    logger.info(f"INFO ({job_id_log}): Successfully approved suggestion {suggestion_id}.")
                    approved_count += 1

                except Exception as approve_err:
                     # Bắt lỗi trong quá trình thêm template hoặc rule
                     logger.error(f"ERROR ({job_id_log}): Failed to approve suggestion {suggestion_id}: {approve_err}", exc_info=False) # Không cần traceback đầy đủ ở đây
                     failed_count += 1
                     try:
                         # Cập nhật status suggestion thành lỗi để không thử lại
                         db.update_suggestion_status(suggestion_id, 'error_bulk_approve')
                     except Exception as update_err:
                          logger.error(f"ERROR ({job_id_log}): Also failed to mark suggestion {suggestion_id} as error after approval failure: {update_err}")
                     continue # Chuyển sang suggestion tiếp theo

            # 3. Ghi log tổng kết
            end_time = time.time()
            logger.info(f"INFO ({job_id_log}): Task complete. Approved: {approved_count}, Failed: {failed_count}, Skipped: {skipped_count}.")
            logger.info(f"--- Finishing background task: {job_id_log} --- (Duration: {end_time - start_time:.2f}s)")

        except Exception as e: # Lỗi tổng quát (ví dụ: lỗi khi get_pending_suggestions)
            logger.critical(f"CRITICAL ERROR during task {job_id_log}: {e}", exc_info=True)
            print(f"--- Finishing background task: {job_id_log} (with CRITICAL ERROR) ---")
    # <<< Kết thúc with temp_app.app_context() >>>
# =============================================
# === HÀM MÔ PHỎNG HỘI THOẠI AI (PHIÊN BẢN ĐẦY ĐỦ) ===
# =============================================

def run_ai_conversation_simulation(
        persona_a_id: str, persona_b_id: str, strategy_id: str, max_turns: int,
        starting_prompt: str | None, log_account_id_a: str, log_account_id_b: str,
        sim_thread_id_base: str, sim_goal: str
    ):
    """
    Tác vụ nền mô phỏng hội thoại AI với cấu hình động, theo dõi Strategy/Stage.
    Tự tạo app context khi chạy.
    """
    try:
        from app import create_app
    except ImportError:
        print("CRITICAL ERROR (run_ai_conversation_simulation): Cannot import create_app! Task cannot run.")
        return
    task_id_log = f"{sim_thread_id_base}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    print(f"\n--- Starting AI Simulation: {task_id_log} ---")
    print(f"    Params: PA={persona_a_id}, PB={persona_b_id}, Strat={strategy_id}, Turns={max_turns}, LogA={log_account_id_a}, LogB={log_account_id_b}")
    start_time = time.time()

    # Kiểm tra import trước khi chạy
    

    # --- Tạo App Context ---
    temp_app = None
    try:
        temp_app = create_app()
        if not temp_app: raise Exception("Failed create Flask app instance.")
    except Exception as creation_err:
        print(f"CRITICAL ERROR ({task_id_log}): Cannot create app context: {creation_err}"); return

    # --- Chạy Logic Bên Trong Context ---
    with temp_app.app_context():
        print(f"DEBUG ({task_id_log}): Entered app context.")
        if not db or not ai_service:
             print(f"ERROR ({task_id_log}): DB or AI service module not available."); return

        # Khởi tạo biến và lấy thông tin ban đầu
        SIM_THREAD_ID = f"sim_thread_{task_id_log}"; SIM_APP_NAME = 'simulation'
        actual_starting_prompt = starting_prompt if starting_prompt else "Xin chào!"
        current_stage_id = None; persona_a_details = None; persona_b_details = None

        try:
            initial_stage_id = db.get_initial_stage(strategy_id)
            if not initial_stage_id: print(f"ERROR ({task_id_log}): Strategy/Initial Stage '{strategy_id}' not found."); return
            current_stage_id = initial_stage_id
            persona_a_details = db.get_persona_details(persona_a_id)
            persona_b_details = db.get_persona_details(persona_b_id)
            if not persona_a_details or not persona_b_details: print(f"ERROR ({task_id_log}): Persona details not found."); return
        except Exception as db_err: print(f"ERROR ({task_id_log}): DB error fetching initial data: {db_err}."); return

        # --- Vòng Lặp Hội Thoại ---
        conversation_history_text = ""; last_message = actual_starting_prompt
        current_speaker_persona_id = persona_a_id # A nói trước
        turns_taken = 0; detected_intent_for_next_turn = "start"

        while turns_taken < max_turns * 2:
            is_persona_a_turn = (current_speaker_persona_id == persona_a_id)
            persona_id_to_use = persona_a_id if is_persona_a_turn else persona_b_id
            opponent_persona_id = persona_b_id if is_persona_a_turn else persona_a_id
            turn_status_code = 'success_ai_sim_A' if is_persona_a_turn else 'success_ai_sim_B'
            speaker_label = "Persona A" if is_persona_a_turn else "Persona B"
            opponent_label = "Persona B" if is_persona_a_turn else "Persona A"
            account_id_for_this_turn_log = log_account_id_a if is_persona_a_turn else log_account_id_b

            turns_taken += 1
            print(f"\nDEBUG ({task_id_log}): --- Turn {(turns_taken + 1) // 2} / {max_turns} ({speaker_label} speaking) ---")
            print(f"    Stage: {current_stage_id}, Input: '{last_message[:100]}...', Prev Intent: {detected_intent_for_next_turn}, Log Acc: {account_id_for_this_turn_log}")

            # 1. Chuẩn bị Prompt Data
            prompt_data = { "account_platform": SIM_APP_NAME, "account_notes": f"Simulated ({sim_goal})", "account_goal": sim_goal, "strategy_id": strategy_id, "current_stage_id": current_stage_id, "user_intent": detected_intent_for_next_turn, "formatted_history": conversation_history_text, "received_text": last_message }

            # 2. Gọi AI Service (Hàm này đã gọi call_generative_model có retry)
            ai_reply, ai_status = ai_service.generate_reply_with_ai(prompt_data=prompt_data, persona_id=persona_id_to_use)

            # 3. Xử lý kết quả và Ghi Log
            if ai_status.startswith("success") and ai_reply: # Bao gồm cả success_fallback_template
                print(f"    {speaker_label} replied: '{ai_reply[:100]}...' (Status: {ai_status})")
                history_id = None
                try:
                    history_id = db.log_interaction_received(account_id=account_id_for_this_turn_log, app_name=SIM_APP_NAME, thread_id=SIM_THREAD_ID, received_text=last_message, strategy_id=strategy_id, current_stage_id=current_stage_id, user_intent=detected_intent_for_next_turn)
                    if history_id: db.update_interaction_log(history_id=history_id, sent_text=ai_reply, status=turn_status_code, next_stage_id=current_stage_id) # Lưu stage hiện tại trước khi chuyển
                    else: print(f"ERROR ({task_id_log}): Failed log received turn {turns_taken}.")
                except Exception as log_err: print(f"ERROR ({task_id_log}): Failed log interaction DB: {log_err}"); break

                # 4. Phát hiện Intent của lời nói VỪA TẠO RA
                detected_intent_for_next_turn = "error" # Mặc định nếu lỗi
                try:
                    # --- <<< GỌI HÀM DETECT ĐÚNG >>> ---
                    detected_intent_for_next_turn = ai_service.detect_user_intent_with_ai(text=ai_reply, persona_id=None)
                    print(f"    Intent detected in reply: {detected_intent_for_next_turn}")
                except AttributeError as ae:
                    print(f"FATAL ERROR ({task_id_log}): AttributeError calling detect_user_intent_with_ai. Is ai_service module loaded correctly? Error: {ae}")
                    break # Không thể tiếp tục nếu thiếu hàm
                except Exception as intent_err: print(f"ERROR ({task_id_log}): Failed detect intent: {intent_err}")

                # 5. Tìm Transition và Cập nhật Stage
                next_stage_found = None
                try:
                    transition = db.find_transition(current_stage_id, detected_intent_for_next_turn)
                    if transition and transition.get('next_stage_id'): next_stage_found = transition['next_stage_id']
                except Exception as trans_err: print(f"ERROR ({task_id_log}): Error finding transition: {trans_err}")

                # 6. Cập nhật lịch sử, tin nhắn cuối, và stage
                conversation_history_text += f"{opponent_label}: {last_message}\n"; conversation_history_text += f"{speaker_label}: {ai_reply}\n"
                last_message = ai_reply
                if next_stage_found and next_stage_found != current_stage_id:
                     print(f"    Transitioning Stage: '{current_stage_id}' -> '{next_stage_found}'")
                     current_stage_id = next_stage_found

            else: # AI không trả lời thành công (kể cả fallback) hoặc lỗi
                print(f"ERROR ({task_id_log}): {speaker_label} failed (Status: {ai_status}). Ending simulation.")
                # Ghi log lỗi vào history nếu muốn
                try:
                     history_id = db.log_interaction_received(account_id=account_id_for_this_turn_log, app_name=SIM_APP_NAME, thread_id=SIM_THREAD_ID, received_text=last_message, strategy_id=strategy_id, current_stage_id=current_stage_id, user_intent=detected_intent_for_next_turn)
                     if history_id: db.update_interaction_log(history_id=history_id, sent_text=None, status=ai_status, next_stage_id=current_stage_id)
                except Exception as log_err: print(f"ERROR ({task_id_log}): Failed log AI failure: {log_err}")
                break # Dừng vòng lặp

            # 7. Chuyển lượt và tạm dừng
            current_speaker_persona_id = opponent_persona_id
            time.sleep(random.randint(2, 4)) # Tăng nhẹ thời gian chờ

        # --- Kết thúc vòng lặp ---
        end_time = time.time()
        print(f"INFO ({task_id_log}): Simulation finished. Total turns attempted: {turns_taken}.")
        print(f"--- Finishing background task: {task_id_log} --- (Duration: {end_time - start_time:.2f}s)")

    # <<< Kết thúc with temp_app.app_context() >>>


# === HÀM BACKGROUND TASK: RUN SUGGESTION ENGINE ===
def run_suggestion_engine_task():
    """
    Tác vụ nền định kỳ để phân tích lịch sử tương tác gần đây
    và tạo ra các đề xuất luật/template mới dựa trên AI.
    """
    # --- Quan trọng: Tạo App Context ---
    # Background tasks chạy ngoài request context thông thường,
    # nên cần tạo app context để truy cập current_app (config, logger)
    # và các tiện ích mở rộng Flask (như SQLAlchemy, nếu dùng).
    # Đảm bảo biến 'app' đã được import đúng từ nơi khởi tạo Flask app.
    if not app:
         print("ERROR (run_suggestion_engine_task): Flask app instance not available.")
         return # Không chạy nếu không có app context

    with app.app_context():
        logger = current_app.logger
        logger.info("--- Starting Suggestion Engine Task ---")
        task_name = 'suggestion_job' # Tên task để lưu trạng thái

        # --- Lấy trạng thái lần chạy cuối ---
        # Lấy ID của interaction_history cuối cùng đã xử lý
        last_processed_id = db.get_task_state(task_name)
        if last_processed_id is None:
             logger.warning(f"Could not get last processed ID for task '{task_name}'. Starting from 0 (may re-process).")
             last_processed_id = 0 # Mặc định bắt đầu từ đầu nếu chưa có trạng thái

        logger.info(f"Last processed interaction ID for '{task_name}': {last_processed_id}")

        # --- Lấy các tương tác mới cần phân tích ---
        # Lấy các status cần phân tích từ config
        status_to_analyze = current_app.config.get(
            'STATUS_TO_ANALYZE_SUGGEST',
            ['success_ai', 'success_ai_sim_A', 'success_ai_sim_B'] # Giá trị mặc định
        )
        batch_limit = current_app.config.get('SUGGESTION_BATCH_LIMIT', 50) # Giới hạn số lượng mỗi lần chạy

        # Gọi hàm DB để lấy interactions mới (sau last_processed_id)
        try:
            interactions = db.get_interactions_for_suggestion(
                min_history_id=last_processed_id,
                status_filter=status_to_analyze,
                limit=batch_limit
            )
        except Exception as e_fetch:
            logger.error(f"Error fetching interactions for suggestion: {e_fetch}", exc_info=True)
            interactions = None

        if interactions is None:
            logger.error("Failed to fetch interactions from database. Task aborted.")
            return # Dừng nếu lỗi DB

        if not interactions:
            logger.info("No new interactions found to analyze for suggestions.")
            # Cập nhật thời gian chạy cuối dù không có gì xử lý (tùy chọn)
            db.update_task_state(task_name, last_processed_id)
            logger.info(f"--- Suggestion Engine Task Finished (No new data) ---")
            return # Kết thúc nếu không có interaction mới

        logger.info(f"Analyzing {len(interactions)} new interactions for suggestions...")

        # --- Xử lý từng interaction ---
        new_suggestions_added = 0
        max_processed_id_in_batch = last_processed_id # ID lớn nhất đã xử lý trong batch này

        for interaction in interactions:
            history_id = interaction.get('history_id')
            if not history_id: continue # Bỏ qua nếu không có ID

            # Cập nhật ID lớn nhất đã thấy
            if history_id > max_processed_id_in_batch:
                 max_processed_id_in_batch = history_id

            logger.debug(f"Analyzing interaction ID: {history_id}")
            received = interaction.get('received_text', '')
            sent = interaction.get('sent_text', '')
            intent = interaction.get('detected_user_intent')
            stage = interaction.get('stage_id')
            strategy = interaction.get('strategy_id')

            # Chỉ xử lý nếu có cả received và sent text
            if not received or not sent:
                 logger.warning(f"Skipping interaction {history_id} due to missing text.")
                 continue

            # --- Gọi AI Service để phân tích ---
            try:
                # Hàm này cần được định nghĩa trong ai_service.py
                # Nó sẽ trả về một dict chứa đề xuất (hoặc None)
                # Ví dụ: {'type': 'simple_rule', 'keywords': '...', 'template_ref': '...', 'category': '...'}
                # Hoặc: {'type': 'new_template', 'template_ref': '...', 'template_text': '...', 'category': '...'}
                suggestion_data = ai_service.analyze_interaction_for_suggestion(
                    received_text=received,
                    sent_text=sent,
                    current_intent=intent,
                    current_stage=stage,
                    current_strategy=strategy
                    # Có thể truyền thêm context khác nếu cần
                )

                if suggestion_data and isinstance(suggestion_data, dict):
                     logger.info(f"AI suggested data for interaction {history_id}: {suggestion_data}")
                     # Lưu đề xuất vào DB
                     added = db.add_suggestion(
                         keywords=suggestion_data.get('keywords'),
                         category=suggestion_data.get('category'),
                         template_ref=suggestion_data.get('template_ref'),
                         template_text=suggestion_data.get('template_text'),
                         source_examples={"interaction_id": history_id, "received": received, "sent": sent} # Lưu nguồn
                     )
                     if added:
                         new_suggestions_added += 1
                         logger.info(f"Successfully saved suggestion from interaction {history_id}.")
                     else:
                          logger.error(f"Failed to save suggestion from interaction {history_id} to database.")
                elif suggestion_data:
                     logger.warning(f"AI analysis for interaction {history_id} returned unexpected data type: {type(suggestion_data)}")
                # else: AI không có đề xuất gì cho interaction này

            except Exception as ai_err:
                logger.error(f"Error during AI analysis for interaction {history_id}: {ai_err}", exc_info=True)
                # Có thể đánh dấu interaction này là lỗi để không thử lại?

            # Delay nhỏ giữa các lần gọi AI để tránh rate limit (tùy chọn)
            # time.sleep(1)

        # --- Cập nhật trạng thái task ---
        # Lưu lại ID lớn nhất đã xử lý thành công trong batch này
        if max_processed_id_in_batch > last_processed_id:
            logger.info(f"Updating task '{task_name}' state. Last processed ID: {max_processed_id_in_batch}")
            update_success = db.update_task_state(task_name, max_processed_id_in_batch)
            if not update_success:
                 logger.error(f"CRITICAL: Failed to update task state for '{task_name}' to ID {max_processed_id_in_batch}!")
                 # Cần có cơ chế cảnh báo ở đây để tránh xử lý lặp lại vô hạn
        else:
             # Nếu không có interaction mới nào được xử lý (ví dụ tất cả bị skip), vẫn cập nhật timestamp
             logger.info(f"No new interaction IDs processed in this batch for '{task_name}'. Updating timestamp only.")
             db.update_task_state(task_name, last_processed_id) # Cập nhật timestamp

        logger.info(f"--- Suggestion Engine Task Finished. Added {new_suggestions_added} new suggestions. ---")





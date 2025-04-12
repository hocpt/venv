# backup/app/background_tasks.py
from flask import Flask, current_app # <<< Thêm Flask
import time
from datetime import datetime, timedelta
import traceback

# Import db và ai_service (giữ nguyên)
try:
    from . import database as db
    from . import ai_service
except ImportError:
    import database as db
    import ai_service
    print("WARNING (background_tasks): Using fallback database/ai_service imports.")

# --- Constants ---
JOB_ID = 'suggestion_job'
STATUS_TO_ANALYZE = ['success_ai']
PROCESSING_LIMIT = 50

# <<< SỬA CHỮ KÝ HÀM ĐỂ NHẬN 'app' >>>
def analyze_interactions_and_suggest():
    """
    Tác vụ nền... (lấy app context bằng current_app).
    """
    # <<< LẤY APP INSTANCE BẰNG current_app >>>
    # Cần chạy trong try...except vì current_app chỉ có khi context tồn tại
    # (Nhưng scheduler nên cung cấp context này khi chạy job)
    try:
        app = current_app._get_current_object()
        if not app:
            print(f"CRITICAL ERROR (Task {JOB_ID}): Cannot get Flask app instance via current_app.")
            return
    except RuntimeError:
         print(f"CRITICAL ERROR (Task {JOB_ID}): Not running within Flask application context.")
         return


    with app.app_context():
        start_time = time.time()
        print(f"\n--- Starting background task: {JOB_ID} --- ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        # Lấy Persona ID từ config thông qua current_app
        persona_id_for_suggestion = current_app.config.get('SUGGESTION_ANALYSIS_PERSONA_ID', 'rule_suggester')
        print(f"DEBUG: (Task) Using Persona ID: {persona_id_for_suggestion}")

        # ... (Toàn bộ logic còn lại của hàm: get state, get interactions, loop, call AI, add suggestion, update state) ...
        # ... (Giữ nguyên như phiên bản đầy đủ trước đó) ...
        try:
             # ...
             last_processed_id = db.get_task_state(JOB_ID) or 0
             # ...
             interactions = db.get_interactions_for_suggestion(...)
             # ...
             for interaction in interactions:
                 # ...
                 suggested_keywords, suggested_category, suggested_template_ref, suggested_template = ai_service.suggest_rule_from_interaction(...)
                 # ...
                 if suggested_keywords or suggested_template:
                     added = db.add_suggestion(...)
                 # ...
             # ... (Cập nhật task state) ...
             # ...
             print(f"--- Finishing background task: {JOB_ID} --- (Duration: {time.time() - start_time:.2f}s)")
        except Exception as e:
             # ... (Xử lý lỗi) ...
             print(f"--- Finishing background task: {JOB_ID} (with CRITICAL ERROR) ---")
    # <<< Kết thúc khối with app.app_context() >>>

# --- Hàm test context (nếu có ở file này thì cũng cần sửa tương tự) ---
# def simple_context_test_job_with_context(app: Flask):
#     with app.app_context():
#         print(...)
#         try:
#              print(current_app.name)
#         except ...
# backup/app/background_tasks.py
from flask import current_app
# Import db và ai_service bằng relative import nếu background_tasks.py
# nằm trong cùng package 'app' với __init__.py
try:
    from . import database as db
    from . import ai_service
except ImportError:
    # Fallback nếu chạy script này riêng lẻ (ít khả dụng khi dùng APScheduler với Flask)
    import database as db
    import ai_service

import time
from datetime import datetime, timedelta
import traceback # Để log lỗi chi tiết

# --- Định nghĩa các hằng số cho tác vụ ---
JOB_ID = 'suggestion_job'
# Trạng thái tương tác cần phân tích (chỉ lấy các phản hồi thành công từ AI)
STATUS_TO_ANALYZE = ['success_ai']
# Khoảng thời gian quét lùi (ví dụ: 1 giờ) - Cần cơ chế tốt hơn để tránh bỏ sót/trùng lặp
LOOKBACK_HOURS = 1
# Giới hạn số lượng tương tác xử lý mỗi lần chạy
PROCESSING_LIMIT = 50

def analyze_interactions_and_suggest():
    """
    Tác vụ nền được lên lịch để phân tích các tương tác thành công gần đây
    và tạo đề xuất rule/template mới.
    """
    # Lấy app context để truy cập config, db, etc.
    # current_app chỉ hoạt động trong request context hoặc app context.
    # APScheduler khi chạy job không tự có context này.
    app = current_app._get_current_object() # Lấy app instance thực tế
    if not app:
        print(f"LỖI (Task {JOB_ID}): Không thể lấy Flask app instance.")
        return

    with app.app_context(): # Tạo app context thủ công
        print(f"\n--- Bắt đầu tác vụ nền: {JOB_ID} --- ({time.strftime('%Y-%m-%d %H:%M:%S')})")

        try:
            # 1. Xác định thời điểm bắt đầu quét
            # --- CẢNH BÁO: Cơ chế đơn giản, có thể xử lý trùng lặp hoặc bỏ sót ---
            # TODO: Triển khai cơ chế lưu trữ trạng thái tốt hơn:
            # - Lưu timestamp/ID của bản ghi cuối cùng đã xử lý thành công vào DB/file.
            # - Lần chạy tiếp theo sẽ query các bản ghi MỚI HƠN timestamp/ID đó.
            min_timestamp = datetime.now() - timedelta(hours=LOOKBACK_HOURS)
            print(f"DEBUG: (Task) Quét các tương tác từ sau: {min_timestamp.strftime('%Y-%m-%d %H:%M:%S')}")

            # 2. Lấy các tương tác cần phân tích từ DB
            # Sử dụng hàm đã hoàn thiện ở bước trước
            print(f"DEBUG: (Task) Lấy tối đa {PROCESSING_LIMIT} tương tác với status {STATUS_TO_ANALYZE} từ DB...")
            interactions = db.get_interactions_for_suggestion(
                min_timestamp=min_timestamp,
                status_filter=STATUS_TO_ANALYZE,
                limit=PROCESSING_LIMIT
            )

            if interactions is None:
                 print(f"LỖI: (Task {JOB_ID}) Không thể lấy tương tác từ DB.")
                 return # Thoát nếu lỗi DB

            if not interactions:
                 print(f"INFO: (Task {JOB_ID}) Không có tương tác mới phù hợp để phân tích trong khoảng thời gian này.")
                 print(f"--- Kết thúc tác vụ nền: {JOB_ID} (Không có dữ liệu) ---")
                 return # Thoát nếu không có gì mới

            print(f"INFO: (Task {JOB_ID}) Tìm thấy {len(interactions)} tương tác để phân tích.")

            # 3. Lặp qua từng tương tác và xử lý
            suggestions_added = 0
            for interaction in interactions:
                history_id = interaction.get('history_id')
                print(f"DEBUG: (Task) Phân tích interaction ID: {history_id}")

                # Tạo dữ liệu đầu vào cho hàm AI
                interaction_data = {
                    'received_text': interaction.get('received_text'),
                    'sent_text': interaction.get('sent_text'), # Phản hồi do AI tạo
                    'user_intent': interaction.get('detected_user_intent'),
                    'stage_id': interaction.get('stage_id'),
                    'strategy_id': interaction.get('strategy_id')
                }

                # Kiểm tra dữ liệu cần thiết
                if not interaction_data['received_text'] or not interaction_data['sent_text']:
                    print(f"WARNING: (Task) Bỏ qua interaction {history_id} do thiếu received_text hoặc sent_text.")
                    continue

                # Gọi hàm AI service để đề xuất (đã hoàn thiện ở bước trước)
                suggested_keywords, suggested_template = ai_service.suggest_rule_from_interaction(interaction_data)

                # 4. Lưu đề xuất vào DB nếu AI trả về kết quả hợp lệ
                if suggested_keywords and suggested_template:
                    print(f"INFO: (Task) AI đề xuất cho ID {history_id}: keywords='{suggested_keywords[:100]}...', template='{suggested_template[:100]}...'")
                    # Lưu nguồn gốc đề xuất (ví dụ: history_id)
                    source_examples = {'history_ids': [history_id]}
                    # Gọi hàm DB để lưu (đã hoàn thiện ở bước trước)
                    added = db.add_suggestion(suggested_keywords, suggested_template, source_examples)
                    if added:
                        suggestions_added += 1
                        print(f"INFO: (Task) Đã lưu đề xuất từ interaction {history_id}.")
                    else:
                        print(f"LỖI: (Task) Lưu đề xuất từ interaction {history_id} thất bại.")
                else:
                     print(f"DEBUG: (Task) AI không tạo ra đề xuất hợp lệ cho interaction {history_id}.")

                # TODO: Cập nhật trạng thái đã xử lý cho interaction này (nếu dùng cơ chế cột cờ)
                # db.mark_interaction_processed(history_id)

            print(f"INFO: (Task {JOB_ID}) Đã thêm {suggestions_added} đề xuất mới.")
            print(f"--- Kết thúc tác vụ nền: {JOB_ID} ---")

        except Exception as e:
             # Ghi log lỗi nghiêm trọng khi chạy tác vụ nền
             print(f"LỖI NGHIÊM TRỌNG trong background task {JOB_ID}: {e}")
             print(traceback.format_exc())
             print(f"--- Kết thúc tác vụ nền: {JOB_ID} (Gặp lỗi) ---")
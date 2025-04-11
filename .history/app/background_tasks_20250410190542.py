# backup/app/background_tasks.py
from flask import current_app
from . import database as db
from . import ai_service
import time # Chỉ để ví dụ

# Hàm này sẽ được lên lịch chạy định kỳ bởi APScheduler
def analyze_interactions_and_suggest():
    # Lấy application context để có thể truy cập config, db,...
    # Sử dụng current_app._get_current_object() để lấy app instance thực sự
    app = current_app._get_current_object()
    with app.app_context():
        print(f"\n--- Chạy tác vụ nền: analyze_interactions_and_suggest --- ({time.strftime('%Y-%m-%d %H:%M:%S')})")

        try:
            # 1. Xác định khoảng thời gian cần quét (ví dụ: 1 giờ trước)
            # TODO: Lấy thời điểm quét cuối cùng từ DB hoặc config để tránh trùng lặp
            print("DEBUG: (Task) Xác định khoảng thời gian...")
            from datetime import datetime, timedelta
            # Ví dụ: Lấy các tương tác trong 1 giờ qua có status 'success_ai'
            one_hour_ago = datetime.now() - timedelta(hours=1)
            status_to_analyze = ['success_ai'] # Chỉ phân tích phản hồi từ AI

            # 2. Lấy các tương tác cần phân tích từ DB
            print("DEBUG: (Task) Lấy tương tác từ DB...")
            interactions = db.get_interactions_for_suggestion(min_timestamp=one_hour_ago, status_filter=status_to_analyze, limit=50) # Giới hạn số lượng mỗi lần chạy

            if interactions is None:
                 print("LỖI: (Task) Không thể lấy tương tác từ DB.")
                 return # Thoát nếu lỗi DB

            if not interactions:
                 print("INFO: (Task) Không có tương tác mới phù hợp để phân tích.")
                 return # Thoát nếu không có gì mới

            print(f"INFO: (Task) Tìm thấy {len(interactions)} tương tác để phân tích.")

            # 3. Lặp qua từng tương tác và gọi AI đề xuất
            for interaction in interactions:
                print(f"DEBUG: (Task) Phân tích interaction ID: {interaction.get('history_id')}")
                # Tạo dữ liệu đầu vào cho hàm AI
                interaction_data = {
                    'received_text': interaction.get('received_text'),
                    'sent_text': interaction.get('sent_text'), # Phản hồi do AI tạo ra
                    'user_intent': interaction.get('detected_user_intent'),
                    'stage_id': interaction.get('stage_id'),
                    'strategy_id': interaction.get('strategy_id')
                    # Thêm các context khác nếu cần
                }

                # Kiểm tra dữ liệu cần thiết
                if not interaction_data['received_text'] or not interaction_data['sent_text']:
                    print(f"WARNING: (Task) Bỏ qua interaction {interaction.get('history_id')} do thiếu text.")
                    continue

                # Gọi hàm AI service để đề xuất
                suggested_keywords, suggested_template = ai_service.suggest_rule_from_interaction(interaction_data)

                # 4. Lưu đề xuất vào DB nếu AI trả về kết quả
                if suggested_keywords and suggested_template:
                    print(f"INFO: (Task) AI đề xuất: keywords='{suggested_keywords[:100]}...', template='{suggested_template[:100]}...'")
                    # Lưu nguồn gốc đề xuất (ví dụ: history_id)
                    source_examples = {'history_ids': [interaction.get('history_id')]}
                    # Gọi hàm DB để lưu
                    added = db.add_suggestion(suggested_keywords, suggested_template, source_examples)
                    if added:
                        print(f"INFO: (Task) Đã lưu đề xuất từ interaction {interaction.get('history_id')}.")
                    else:
                        print(f"LỖI: (Task) Lưu đề xuất từ interaction {interaction.get('history_id')} thất bại.")
                else:
                     print(f"DEBUG: (Task) AI không tạo ra đề xuất cho interaction {interaction.get('history_id')}.")

                # TODO: Có thể đánh dấu interaction đã được xử lý để tránh quét lại

            print("--- Kết thúc tác vụ nền ---")

        except Exception as e:
             # Ghi log lỗi nghiêm trọng khi chạy tác vụ nền
             print(f"LỖI NGHIÊM TRỌNG trong background task: {e}")
             import traceback
             print(traceback.format_exc())
## Định hướng Phát triển: AI Điều khiển Điện thoại

Mục tiêu dài hạn là xây dựng khả năng cho hệ thống tự động tương tác với các ứng dụng trên điện thoại Android thực tế (đã root) để thu thập dữ liệu và thực thi các chiến lược phức tạp.

**Hướng tiếp cận đã thống nhất (Hybrid LLM Agent + Offline Strategy):**

1.  **Vai trò Điện thoại (Client - MacroDroid/AutoInput):**
    * **Thu thập:** Lấy dữ liệu cấu trúc UI màn hình hiện tại (dùng AutoInput UI Query là chủ yếu, thay vì `uiautomator dump` hay OCR).
    * **Đóng gói:** Tạo file JSON chứa danh sách các element UI quan trọng (ID, Text, Tọa độ, Clickable...).
    * **Giao tiếp:** Gửi JSON State lên Server (HTTP POST), nhận JSON Action từ Server.
    * **Thực thi:** Phân tích JSON Action và thực hiện hành động tương ứng (Tap, Swipe, Input...) bằng các action của MacroDroid/AutoInput/Shell.
    * **Báo cáo:** Gửi trạng thái thực thi (thành công/lỗi) về Server (trong lần gửi State tiếp theo).

2.  **Vai trò Server (PC - Flask/Python - Planner & Trainer):**
    * **"Bản đồ App" (CSDL + Admin UI):**
        * **Định nghĩa thủ công:** Người dùng định nghĩa cấu trúc ứng dụng mục tiêu thông qua Admin UI.
        * **Screens = Stages:** Các màn hình chính được định nghĩa là các `strategy_stages`. Cần có cách nhận diện stage từ dữ liệu UI.
        * **Actions = Transitions:** Các hành động (`stage_transitions`) mô tả việc tương tác với element trên màn hình hiện tại (`current_stage_id`) dẫn đến màn hình tiếp theo (`next_stage_id`). Trường `action_to_suggest` sẽ chứa **lệnh JSON chi tiết** cho MacroDroid.
    * **API Endpoint (`/phone/process_state`):** Nhận JSON State từ điện thoại.
    * **AI Service:**
        * **Phân tích State:** Dùng AI (Gemini) phân tích JSON State để xác định `current_stage_id` (vị trí trên "bản đồ").
        * **Quyết định Hành động:**
            * Tra cứu "Bản đồ" (Transitions) dựa trên `strategy_id`, `current_stage_id`, và mục tiêu con hiện tại. Nếu có Action JSON định sẵn -> Sử dụng.
            * Nếu cần suy luận phức tạp (vd: viết nội dung comment) hoặc xử lý tình huống lạ -> Gọi AI (Gemini) với đầy đủ ngữ cảnh (mục tiêu, stage, state màn hình, danh sách "tools" - các action JSON cơ bản) để AI **chọn/tạo ra Action JSON** tiếp theo.
    * **Gửi Lệnh:** Trả về Action JSON cho điện thoại.
    * **Logging:** Ghi lại chi tiết vào bảng `phone_action_log` (State -> Quyết định -> Action -> Kết quả).

3.  **"Học tập" / Tinh chỉnh (Chủ yếu Offline):**
    * Con người phân tích dữ liệu log từ `phone_action_log`.
    * **Cập nhật thủ công "Bản đồ App"** trong Admin UI (sửa Stages, Transitions, Action JSON).
    * **Tinh chỉnh Prompt** cho các lệnh gọi AI phân tích và quyết định.
    * (Nâng cao sau này) Sử dụng dữ liệu log để huấn luyện/fine-tune các mô hình AI chuyên biệt.

**Các bước triển khai tiếp theo cho tính năng này:**

1.  Thiết kế chi tiết và tạo bảng `phone_action_log`.
2.  Thiết kế cấu trúc JSON chuẩn cho State (Phone->Server) và Action (Server->Phone).
3.  Xây dựng API Endpoint `/phone/process_state` trên Flask.
4.  Xây dựng Macro trên điện thoại để thu thập UI (AutoInput), tạo JSON State, gửi/nhận HTTP, thực thi Action JSON cơ bản.
5.  Xây dựng logic AI cơ bản trên server để phân tích state và quyết định action đơn giản.
6.  Bắt đầu định nghĩa "Bản đồ" cho một ứng dụng cụ thể (vd: TikTok) qua Admin UI.
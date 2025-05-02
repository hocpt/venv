# README - Dự án HPT Automation
# Ngày cập nhật: 29/04/2025 (Tổng kết phiên làm việc)

## I. MỤC TIÊU TỔNG THỂ

Xây dựng hệ thống tự động hóa đa năng cho Android, bao gồm:
1.  **AI Ngôn ngữ:** Tự động trả lời/tương tác dựa trên văn bản (đã có nền tảng cơ bản).
2.  **AI Điều khiển:** Tự động hóa thao tác UI trên ứng dụng mục tiêu (TikTok, Facebook...).
3.  **AI Xây dựng Bản đồ App:** Tự động học và xây dựng cấu trúc, luồng hoạt động của ứng dụng mục tiêu.
4.  **AI Lập kế hoạch Chiến lược:** (Mục tiêu dài hạn) Tự động tạo ra các kịch bản (chiến lược JSON) từ mục tiêu cấp cao dựa trên bản đồ app đã học.
5.  **Admin UI:** Giao diện quản trị tập trung (Flask) để cấu hình, giám sát và quản lý toàn bộ hệ thống.
6.  **Hỗ trợ Đa nhiệm:** Quản lý nhiều thiết bị, tài khoản, clone app.

## II. KIẾN TRÚC & CÔNG NGHỆ

* **Backend:** Python, Flask (Application Factory), Waitress.
* **Database:**
    * **PostgreSQL:** Lưu trữ cấu hình (strategies, accounts, devices, tasks...), logs (interactions, actions), hàng đợi lệnh (scheduler_commands)... Schema chi tiết trong `automation_schema.sql`.
    * **Neo4j:** Lưu trữ **Bản đồ App (App Map)** dưới dạng đồ thị (Nodes=`Screen`, Edges=`TRANSITION`). Đã cài đặt qua Neo4j Desktop và kết nối thành công từ Flask.
* **Client:** MacroDroid + Plugin AutoInput (Chạy trên Android).
* **Giao tiếp:** REST API (JSON) giữa Server và Client.
* **AI:** Google Gemini (qua `ai_service.py`, có logic retry/key rotation).
* **Admin UI:** Jinja2 Templates, Bootstrap 5.
* **Thành phần khác:** APScheduler (tác vụ nền), Psycopg2, neo4j (Python drivers), python-dotenv, cryptography.

## III. TRẠNG THÁI HIỆN TẠI (Kết thúc phiên làm việc 29/04/2025)

* **Backend & Kết nối:**
    * Flask server chạy ổn định.
    * Kết nối PostgreSQL hoạt động.
    * **Kết nối Neo4j hoạt động**, module `graph_db.py` đã có các hàm core (`get_driver`, `close_driver`, `init_app`, `execute_read`, `execute_write`, `create_or_update_screen_node`, `create_or_update_transition_relationship`, `get_screen_properties`, `get_outgoing_transitions`).
    * `ai_service.py` hoạt động cho các tác vụ ngôn ngữ.
    * Scheduler (`scheduler_runner.py`) chạy, có thể xử lý command queue (`_process_pending_commands` đã sửa lỗi TypeError).
* **Luồng Mapping Tự động (Đang Xây dựng):**
    * **API `/phone/report_status`:** Đã sửa để chấp nhận `assignment_id` có thể là `None`, xử lý `current_ui_state` và `previous_action`, **enqueue thành công job `build_map`** vào `scheduler_commands`, và trả về ACK đơn giản cho client.
    * **Tác vụ Nền `build_app_map_task`:** Đã được tạo trong `background_tasks.py`. Có thể chạy, tạo app context, gọi các hàm `graph_db.py` để **tạo/cập nhật Node `Screen` và Edge `TRANSITION` trong Neo4j** (đã chạy thử thành công ít nhất lần đầu). Logic nhận diện `screenId` hiện tại còn đơn giản (dựa trên hash), cần cải thiện.
    * **API `/phone/get_next_exploration_action`:** Đã được **định nghĩa** trong `phone/routes.py`.
    * **Planner Placeholder (`plan_simple_exploration_action`):** Đã được **viết code** trong `phone/controller.py`, sử dụng các hàm `graph_db.py` để lấy thông tin màn hình/transition từ Neo4j và đề xuất hành động click đơn giản (cần client gửi 'clickable').
    * **Điểm nghẽn:** Cần Client gửi đúng dữ liệu và hoàn thiện logic Planner.
* **Admin UI:**
    * Hầu hết các trang CRUD cơ bản đã có.
    * Trang xem Log Assignment hiển thị được UI State qua Modal.
    * Trang API Docs động (list + modal fetch) hoạt động. CRUD API Docs cần hoàn thiện.
* **Client (MacroDroid):**
    * **Chưa hoàn thiện.** Cần triển khai logic **gửi `previous_action` context** và vòng lặp gọi API `/report_status` -> `/get_next_exploration_action` -> Thực thi -> Gửi báo cáo...

## IV. HƯỚNG XÂY DỰNG MAPPING TỰ ĐỘNG (Đã Thống Nhất)

* **Mục tiêu:** Tự động tạo đồ thị App Map trong Neo4j.
* **Mô hình Neo4j:**
    * Node `Screen`: Thuộc tính `screenId` (unique per app), `appName` (package_name), `activityName`, `structureHash`, `aiSummary` (tương lai), `rawStateSample` (JSON string), `lastSeen`, `createdAt`, `updatedAt`.
    * Relationship `TRANSITION`: Thuộc tính `actionType`, `onElementId`, `onElementText`, `onElementClass`, `count`, `lastTransitionTime`, `createdAt`, `updatedAt`.
* **Vòng lặp Mapping (Client <-> Server):**
    1.  **Client Gửi Report (`/report_status`):** Gửi `current_ui_state` (gồm `package_name`, `activity_name`, mảng ids/texts/coords, **clickable**...) và `previous_action` (gồm `source_screen_id` + `action_details`).
    2.  **Server Xử lý Báo cáo:**
        * API `report_status` nhận, xử lý UI state, đưa job `build_map` vào queue, trả về ACK.
        * BG Task `build_app_map_task` chạy:
            * Phân tích `current_ui_state` -> Nhận diện/Tạo `target_screen_id` & Node Neo4j.
            * Đọc `previous_action` -> Tạo/Cập nhật Edge `TRANSITION` trong Neo4j.
            * **Xác định `screenId`** của màn hình vừa xử lý.
    3.  **Client Yêu cầu Hành động (`/get_next_exploration_action`):** Gửi `current_screen_id` (ID client biết).
    4.  **Server Quyết định Hành động:**
        * API `get_next_exploration_action` nhận yêu cầu.
        * **Xác định `confirmedCurrentScreenId`** (ID thực sự ứng với state client vừa báo cáo).
        * Gọi Planner (`plan_simple_exploration_action` hiện tại): Truy vấn Neo4j về `confirmedCurrentScreenId` (nodes, edges) -> Đề xuất `nextAction` (ví dụ: click element chưa thử).
        * Trả về `{ confirmedCurrentScreenId, nextAction }` cho client.
    5.  **Client Nhận & Thực thi:** Cập nhật `v_current_screen_id` = `confirmedCurrentScreenId` -> Lưu `previous_action` mới (dùng `v_current_screen_id` làm nguồn) -> Thực thi `nextAction` -> Quay lại Bước 1 (Gửi Report).

## V. TẦM NHÌN DÀI HẠN

* Hoàn thiện AI Planner để thay thế `plan_simple_exploration_action`, có khả năng lập kế hoạch phức tạp hơn.
* Xây dựng AI Planner cấp cao hơn để tự động **tạo ra `action_sequence` JSON** từ mục tiêu (ví dụ: "tăng follow") dựa trên bản đồ Neo4j, **thay thế hoàn toàn việc tạo Strategy thủ công** trong Admin UI.
* Tích hợp AI sâu hơn vào Client để tự phục hồi lỗi.

## VI. BƯỚC TIẾP THEO ƯU TIÊN (Cho Phiên Làm Việc Mới)

1.  **Hoàn thiện Client (MacroDroid):**
    * **Quan trọng nhất:** Triển khai logic **gửi `previous_action` context** chính xác.
    * Triển khai **vòng lặp** gọi `/report_status` -> `/get_next_exploration_action` -> Thực thi -> Gửi báo cáo.
    * Đảm bảo gửi đủ thông tin element (`clickable`, `class_name`...) trong `current_ui_state`.
2.  **Hoàn thiện Server (API & Planner):**
    * Viết code **hoàn chỉnh** cho API `/phone/get_next_exploration_action` (bao gồm logic xác định `confirmedCurrentScreenId` và gọi planner).
    * **Kiểm thử và Tinh chỉnh:** Chạy client để gửi dữ liệu thật, kiểm tra kỹ log server và dữ liệu trong Neo4j Browser xem bản đồ có được xây dựng đúng luồng không. Sửa lỗi logic trong `build_app_map_task` hoặc `plan_simple_exploration_action` nếu cần.
3.  **Hoàn thiện Admin UI (Sau):** CRUD API Docs, Trực quan hóa Neo4j Map...
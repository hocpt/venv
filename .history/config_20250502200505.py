# README - Dự án HPT Automation
# Ngày cập nhật: 02/05/2025 (Tổng kết phiên làm việc)

## I. MỤC TIÊU TỔNG THỂ (Nhắc lại)

Xây dựng hệ thống tự động hóa Android đa năng bao gồm AI Ngôn ngữ, AI Điều khiển UI, AI Xây dựng Bản đồ App, và AI Lập kế hoạch Chiến lược, quản lý qua Admin UI tập trung, hỗ trợ đa thiết bị/tài khoản/clone.

## II. TRẠNG THÁI HIỆN TẠI (Đầu phiên làm việc mới)

* **Backend & Database:** Nền tảng Flask, PostgreSQL, Neo4j hoạt động. Các hàm CRUD cơ bản cho các bảng cấu hình (strategies, stages, transitions, macros, accounts, devices...) đã có. `ai_service` tích hợp Gemini cơ bản. Scheduler chạy nền.
* **Luồng Mapping/Khám phá:**
    * **API Gộp Đồng bộ (`/phone/explore_step`):** Đã thống nhất chuyển sang sử dụng API này **riêng cho luồng mapping** để đảm bảo tính đồng bộ giữa log SQL, cập nhật Neo4j và quyết định của planner, đồng thời đơn giản hóa client. **Đã cung cấp code Python** cho route và controller xử lý đồng bộ (process state -> log PG -> update Neo4j -> call planner -> return response).
    * **Logic Tạo Screen ID:** Đã xác định vấn đề **không nhất quán** giữa API và tác vụ nền. **Đã thống nhất** sử dụng hàm helper chung `determine_screen_id_from_state` (trong `controller.py`) cho cả hai nơi. **Đã cung cấp code** sửa đổi cho `build_app_map_task` để gọi hàm helper này.
    * **Planner (`plan_simple_exploration_action`):**
        * Phiên bản hiện tại đã trả về cấu trúc `nextAction` chuẩn hóa (`actionType: "run_macro"`, `macro_code`, `params` chứa `target` với `resource_id`, `text`, `coordinates`, và các trường `random_*` tùy chọn).
        * **Vấn đề:** Vẫn còn tình trạng bị **vòng lặp** (A->B->A hoặc S1->S1) do planner chưa đủ thông minh để xử lý tình huống state ID không đổi hoặc quay lại state cũ, và chỉ lọc theo trình tự đơn giản.
    * **Xử lý Clickability:** Đã xác nhận AutoInput không cung cấp `%aiclickable`, `%aiclasses` đáng tin cậy khi dùng "Only Visible". Thống nhất server sẽ dùng **heuristic đơn giản** (ví dụ: chỉ coi element có `resource_id` là clickable) và **bỏ qua `class_name`** trong logic planner và tạo cạnh Neo4j để đơn giản hóa client.
* **Client (MacroDroid):**
    * Đã xác nhận client cần **tự lấy `activity_name`** từ AutoInput (`%aiactivity`) sau mỗi hành động và gửi lên trong `current_ui_state`.
    * Client cần gửi mảng `class_names` (từ `%aiclasses`) nếu lấy được.
    * Client **không cần** gửi mảng `clickables` nữa (do server dùng heuristic).
    * Client cần tạo `previous_action.action_details` **ưu tiên `onElementId`**, nếu không có thì dùng `onElementText`, **bỏ qua `onElementClass`**.
    * Logic client cần được cập nhật để gọi API `/phone/explore_step` duy nhất cho luồng mapping.

## III. CÁC VẤN ĐỀ CHÍNH VÀ HƯỚNG GIẢI QUYẾT ĐÃ THỐNG NHẤT

1.  **Bất đồng bộ SQL/Neo4j & Phức tạp Client:**
    * **Vấn đề:** Luồng 2 API (`report_status` + `get_next_exploration_action`) với cập nhật Neo4j bất đồng bộ gây lỗi timing ("Node not found") và đòi hỏi client phải có logic retry phức tạp.
    * **Giải pháp (Đã thống nhất):** Sử dụng API gộp đồng bộ `POST /phone/explore_step` **riêng cho luồng mapping**. Server sẽ xử lý tuần tự: log PG -> cập nhật Neo4j -> gọi planner -> trả về kết quả. Client chỉ cần gọi 1 API và chờ. Luồng thực thi nhiệm vụ vẫn dùng API riêng (`/get_strategy`, `/report_status` async).

2.  **Không nhất quán Screen ID:**
    * **Vấn đề:** Logic tạo `screenId` khác nhau giữa API và background task dẫn đến ID không khớp (vd: API tính ra `1367...`, background task tạo node `4750...`).
    * **Giải pháp (Đã thống nhất):** **Thống nhất logic tạo ID** bằng cách sử dụng hàm helper chung `determine_screen_id_from_state` cho cả API (`handle_explore_step`) và tác vụ nền (`build_app_map_task`).

3.  **Planner bị vòng lặp (A->B->A hoặc S1->S1):**
    * **Vấn đề:** Planner hiện tại chỉ kiểm tra transition đã đi ra từ node hiện tại, chưa đủ thông minh để nhận biết và phá vỡ vòng lặp giữa các node hoặc lặp lại hành động trên cùng một node không hiệu quả. Nó cũng chỉ lọc element theo trình tự.
    * **Giải pháp Đề xuất (Cần thực hiện):**
        * **Nâng cấp `plan_simple_exploration_action`:**
            * **Ghi nhớ lịch sử:** Sử dụng `outgoing_transitions` từ Neo4j để biết các `actionType` và `onElementId` (cho click) đã được thử **từ màn hình hiện tại**.
            * **Ưu tiên Click Mới:** Luôn tìm element có `resource_id` (heuristic clickable) mà **chưa có** transition `click` tương ứng đi ra từ node hiện tại.
            * **Tránh Lặp Fallback:** Trước khi đề xuất `swipe_up` hoặc `NAV_GO_BACK`, kiểm tra xem các hành động này **đã có** transition đi ra từ node hiện tại chưa. Nếu có rồi thì không đề xuất lại.
            * **Trả về `no_action`:** Chỉ trả về khi tất cả các click khả thi (có ID) và các fallback chính (swipe, back) đều đã được thử từ màn hình này.
        * **(Tương lai) Mapping theo Chiến lược:** Bước tiếp theo sau khi giải quyết vòng lặp cơ bản là làm planner thông minh hơn bằng cách ưu tiên các hành động/element thuộc về "nhánh chính" của một chiến lược cụ thể.

4.  **Xử lý dữ liệu Client (Clickable, Class):**
    * **Vấn đề:** AutoInput không cung cấp `clickable`, `class_name` đáng tin cậy ở chế độ "Only Visible".
    * **Giải pháp (Đã thống nhất):**
        * Server dùng heuristic: Chỉ coi element có `resource_id` là clickable khi planner tìm hành động click.
        * Client **không cần** gửi `clickables`.
        * Client **không cần** lấy và gửi `class_names` (bỏ qua `%aiclasses`).
        * Client tạo `previous_action.action_details` chỉ cần `actionType` và `onElementId` (nếu có) hoặc `onElementText` (nếu không có ID). Bỏ qua `onElementClass`.

## IV. CÁC BƯỚC THỰC HIỆN TIẾP THEO (ƯU TIÊN)

1.  **Thống nhất Logic Tạo Screen ID (BẮT BUỘC LÀM TRƯỚC):**
    * **Action:** Áp dụng code sửa đổi cho hàm `build_app_map_task` trong `hpt4/app/background_tasks.py` để nó gọi hàm helper `determine_screen_id_from_state` (từ `controller.py`).
    * **Kiểm tra:** Đảm bảo import thành công và server khởi động không lỗi.
    * **Dọn dẹp:** Xóa dữ liệu cũ trong Neo4j cho app đang test (`MATCH (n:Screen {appName:'...'}) DETACH DELETE n`).

2.  **Implement API Gộp Đồng bộ `/phone/explore_step`:**
    * **Action:** Thêm route mới vào `routes.py` và hàm controller `handle_explore_step` vào `controller.py` với logic xử lý đồng bộ (Log PG -> Update Neo4j -> Call Planner) như code đã cung cấp ở phản hồi #45.
    * **Kiểm tra:** Đảm bảo API hoạt động, cập nhật Neo4j trước khi gọi planner.

3.  **Cập nhật Client MacroDroid (Cho Luồng Mapping):**
    * **Action:** Sửa logic client để gọi API `POST /phone/explore_step` duy nhất. Gửi đúng payload (bao gồm `current_screen_id` là ID server xác nhận lần trước hoặc `""` lần đầu, `current_ui_state` với `activity_name` từ `%aiactivity` và các mảng element, `previous_action` được tạo đúng cách - chỉ có `actionType` và `onElementId/Text`). Xử lý response (lưu `confirmedCurrentScreenId`, chuẩn bị `previous_action`, thực thi `nextAction`). Bỏ logic retry timing.
    * **Kiểm tra:** Đảm bảo client gọi đúng API và xử lý response mượt mà.

4.  **Nâng cấp Planner (`plan_simple_exploration_action`):**
    * **Action:** Áp dụng code sửa đổi cho hàm planner (phiên bản ở phản hồi #49) để triển khai heuristic clickable (chỉ dùng ID) và logic tránh lặp hành động (cả click và fallback) dựa trên `outgoing_transitions` trong Neo4j.
    * **Kiểm tra:** Chạy luồng mapping và quan sát xem planner có tránh được vòng lặp, có đề xuất click vào các ID khác nhau không, và có dùng fallback hợp lý không.

5.  **(Sau đó) Triển khai Mapping theo Chiến lược:** Bắt đầu thiết kế và implement các thay đổi CSDL, Admin UI, Planner để hỗ trợ mapping có định hướng.

6.  **(Song song/Sau đó) Xây dựng Tab Mapping Admin UI:** Phát triển giao diện trực quan hóa bản đồ Neo4j.

7.  **(Tương lai xa) Tích hợp CV/AI nâng cao.**

Hy vọng README này giúp bạn nắm bắt lại tổng thể và các bước chúng ta cần làm tiếp theo. Hãy bắt đầu với Bước 1: Thống nhất Logic Tạo ID.
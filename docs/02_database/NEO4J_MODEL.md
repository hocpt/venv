# Mô hình Dữ liệu Neo4j (App Mapping)

Neo4j được sử dụng để lưu trữ và quản lý đồ thị các màn hình (screens) và các hành động chuyển tiếp (transitions) giữa chúng trong các ứng dụng di động.

## 1. Nodes (Nút)

### :Screen
Đại diện cho một màn hình cụ thể trong một ứng dụng.

* **Properties (Thuộc tính):**
    * `screen_id` (String, PK): ID duy nhất của màn hình. Đây có thể là một hash của cấu trúc các element, hoặc kết hợp `app_name` + `activity_name` + một checksum nào đó. Đối với các node đã được "định nghĩa" (defined), `screen_id` này sẽ khớp với `defined_screen_id` trong bảng `screen_definitions` của PostgreSQL.
    * `app_name` (String): Tên package của ứng dụng (ví dụ: "com.example.app").
    * `activity_name` (String): Tên Activity của màn hình (nếu có, từ Android).
    * `screenshot_path` (String): Đường dẫn (tên file) đến ảnh chụp màn hình, lưu trên server.
    * `width` (Integer): Chiều rộng gốc của ảnh chụp màn hình.
    * `height` (Integer): Chiều cao gốc của ảnh chụp màn hình.
    * `element_count` (Integer): Số lượng phần tử UI được phát hiện trên màn hình.
    * `status` (String): Trạng thái của node màn hình:
        * `unknown`: Node mới được phát hiện, chưa được định nghĩa hoặc liên kết với PIE.
        * `defined`: Node đã được định nghĩa và liên kết với một `defined_screen_id` từ bảng `screen_definitions`.
        * `defined_from_unknown`: Node ban đầu là `unknown`, sau đó được admin định nghĩa và gán `defined_as_screen_id`.
        * `merged_to_defined`: Node `unknown` đã được merge vào một node `defined` và sẽ bị xóa hoặc đánh dấu không dùng.
        * `error_parsing`: Lỗi khi phân tích trạng thái UI của màn hình này.
    * `node_classification` (String, Optional): Phân loại tổng thể cho màn hình này do người dùng đặt (ví dụ: 'login_page', 'user_profile', 'settings_main').
    * `defined_as_screen_id` (String, Optional): Nếu status là `defined_from_unknown`, trường này lưu `defined_screen_id` mà nó được gán vào.
    * `logical_pie_name` (String, Optional): Tên logic của PIE tương ứng nếu node này có status `defined`.
    * `created_at` (DateTime): Thời điểm node được tạo.
    * `last_seen` (DateTime): Thời điểm cuối cùng màn hình này được hệ thống "nhìn thấy" hoặc cập nhật.
    * `updated_at` (DateTime): Thời điểm cuối cùng node này được cập nhật (ví dụ: status, screenshot).
    * `neo4j_db_id` (String, Internal): ID nội bộ của Neo4j, dùng để tham chiếu trong một số API.
* **Indexes:**
    * Tạo index trên `(:Screen {screen_id, app_name})` để tăng tốc độ truy vấn.
    * Tạo index trên `(:Screen {app_name})`.

## 2. Relationships (Quan hệ)

### :TRANSITION
Đại diện cho một hành động người dùng hoặc hệ thống dẫn đến việc chuyển từ một màn hình (`:Screen`) sang một màn hình khác.

* **Type:** `TRANSITION`
* **Direction:** `(source:Screen) -[:TRANSITION]-> (target:Screen)`
* **Properties (Thuộc tính):**
    * `actionType` (String): Loại hành động (ví dụ: "click", "input", "swipe_up", "nav_go_back", "run_macro").
    * `element_id` (String, Optional): `resource-id` (Android) hoặc một định danh khác của phần tử UI được tương tác.
    * `identifier_type` (String, Optional): Loại của `element_id` (ví dụ: 'resource_id', 'xpath', 'description').
    * `element_text` (String, Optional): Text của phần tử UI được tương tác (nếu có).
    * `macro_code` (String, Optional): Mã của macro được thực thi (nếu `actionType` là "run_macro").
    * `params_json_str` (String, Optional): Chuỗi JSON chứa các tham số cho hành động (ví dụ: text cho "input", params cho "run_macro").
    * `status` (String): Trạng thái của transition:
        * `provisional`: Mới được tạo, chưa được xác nhận.
        * `confirmed`: Đã được xác nhận bởi admin hoặc logic tự động.
        * `failed`: Hành động dẫn đến lỗi hoặc không chuyển màn hình như mong đợi.
        * `needs_review`: Cần admin xem xét.
        * `disabled`: Transition này bị vô hiệu hóa.
    * `attempt_count` (Integer): Số lần thử thực hiện transition này.
    * `success_count` (Integer): Số lần thực hiện thành công.
    * `created_at` (DateTime): Thời điểm transition được ghi nhận lần đầu.
    * `last_attempted_at` (DateTime): Thời điểm cuối cùng transition này được thử.
    * `updated_at` (DateTime): Thời điểm cuối cùng transition này được cập nhật.

## 3. Ví dụ Cypher Query

* **Tìm một Screen Node:**
    ```cypher
    MATCH (s:Screen {app_name: "com.example.app", screen_id: "example_screen_123"})
    RETURN s;
    ```
* **Tìm tất cả các transition đi ra từ một màn hình:**
    ```cypher
    MATCH (s1:Screen {screen_id: "start_screen_id", app_name: "app_name"})-[r:TRANSITION]->(s2:Screen)
    RETURN s1, r, s2;
    ```
* **Lấy tất cả Screen Nodes và Transitions cho một ứng dụng (dùng cho mapping viewer):**
    ```cypher
    MATCH (n:Screen {app_name: $app_name_param})
    OPTIONAL MATCH (n)-[r:TRANSITION]->(m:Screen {app_name: $app_name_param})
    RETURN n, r, m
    ```
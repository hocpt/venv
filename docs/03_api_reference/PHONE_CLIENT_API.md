# API cho Client Di động

Tài liệu này mô tả các API endpoints được thiết kế cho client di động (ví dụ: ứng dụng điện thoại) để tương tác với hệ thống HPT11.

## Mục lục

* [POST /phone/register_device](#post-phoneregister_device)
* [POST /phone/screen_data](#post-phonescreen_data)
* [POST /phone/task_assignment/request](#post-phonetask_assignmentrequest)
* [POST /phone/task_assignment/update](#post-phonetask_assignmentupdate)
* [POST /api/upload/screenshot](#post-apiuploadscreenshot)

---

## `POST /phone/register_device`

Đăng ký một thiết bị mới với hệ thống hoặc cập nhật thông tin thiết bị nếu đã tồn tại.

* **Mô tả:**
    Client di động gọi API này khi khởi động lần đầu hoặc khi cần cập nhật thông tin thiết bị. Hệ thống sẽ lưu hoặc cập nhật thông tin thiết bị vào bảng `devices` trong CSDL PostgreSQL.
* **Request Body (JSON):**
    ```json
    {
      "device_id": "string (required) - ID duy nhất của thiết bị",
      "device_name": "string (optional) - Tên gợi nhớ của thiết bị",
      "os_info": "string (optional) - Thông tin hệ điều hành (ví dụ: Android 11, API 30)",
      "macrodroid_version": "string (optional) - Phiên bản Macrodroid đang chạy trên thiết bị"
    }
    ```
* **Response Success (200 OK hoặc 201 Created):**
    ```json
    {
      "success": true,
      "message": "Device registered/updated successfully.", // Hoặc thông báo cụ thể hơn
      "device_id": "your_device_id"
    }
    ```
* **Response Error:**
    * **400 Bad Request:** Nếu thiếu `device_id` hoặc định dạng dữ liệu không hợp lệ.
        ```json
        {
          "success": false,
          "error": "Missing device_id or invalid data."
        }
        ```
    * **500 Internal Server Error:** Nếu có lỗi xảy ra ở phía server khi xử lý.
        ```json
        {
          "success": false,
          "error": "Internal server error while registering device."
        }
        ```
* **Ghi chú:**
    * Nếu `device_id` đã tồn tại, API sẽ cập nhật các thông tin khác (`device_name`, `os_info`, `macrodroid_version`, `last_seen_at`).
    * Trường `status` của thiết bị trong CSDL có thể được cập nhật thành 'online' khi API này được gọi.

---

## `POST /phone/screen_data`

Gửi dữ liệu về màn hình hiện tại của ứng dụng trên client, bao gồm thông tin activity, ảnh chụp màn hình (tên file), và danh sách các phần tử UI.

* **Mô tả:**
    API này được client gọi khi có sự thay đổi màn hình hoặc khi cần phân tích màn hình hiện tại. Dữ liệu được sử dụng để xây dựng đồ thị app mapping trong Neo4j và ghi log chi tiết vào PostgreSQL. Ảnh chụp màn hình thực tế sẽ được tải lên riêng qua endpoint `/api/upload/screenshot`.
* **Request Body (JSON):**
    ```json
    {
      "device_id": "string (required) - ID của thiết bị gửi dữ liệu",
      "app_name": "string (required) - Tên package của ứng dụng (ví dụ: com.example.app)",
      "screen_id": "string (required) - ID duy nhất của màn hình này (thường là activity_name + hash các element quan trọng)",
      "activity_name": "string (required) - Tên Activity hiện tại",
      "screenshot_filename": "string (required) - Tên file ảnh chụp màn hình (sẽ được upload riêng)",
      "elements": [ // Array of objects (required) - Danh sách các phần tử UI trên màn hình
        {
          "element_id": "string (required) - ID do client tạo, unique trong context của màn hình này",
          "text": "string (optional) - Nội dung text của element",
          "resource_id": "string (optional) - Resource ID của element",
          "class_name": "string (optional) - Class name của element (ví dụ: android.widget.Button)",
          "xpath": "string (optional) - XPath đến element",
          "bounds": "string (optional) - Tọa độ bao của element, ví dụ: \"[0,0][100,100]\"",
          "clickable": "boolean (optional)",
          "visible_to_user": "boolean (optional)",
          "is_password": "boolean (optional)",
          "parent_id": "string (optional) - element_id của node cha (nếu có)",
          "children_ids": ["string", ...] // (optional) - list element_id của các node con
          // Các thuộc tính khác do client trích xuất được
        }
      ],
      "window_width": "integer (optional) - Chiều rộng của cửa sổ/màn hình (pixel)",
      "window_height": "integer (optional) - Chiều cao của cửa sổ/màn hình (pixel)",
      "timestamp": "string (optional) - Thời gian ghi nhận dữ liệu, định dạng ISO 8601"
    }
    ```
* **Response Success (200 OK):**
    ```json
    {
      "success": true,
      "message": "Screen data received and processing queued/started.",
      "screen_id_processed": "actual_screen_id_from_server", // ID mà server sử dụng (có thể giống screen_id gửi lên)
      "neo4j_update_status": "success/pending/failed", // Trạng thái cập nhật Neo4j
      "log_status": "success/failed" // Trạng thái ghi log PostgreSQL
    }
    ```
* **Response Error:**
    * **400 Bad Request:** Nếu thiếu các trường bắt buộc hoặc định dạng dữ liệu không hợp lệ.
    * **500 Internal Server Error:** Lỗi xử lý ở server.
* **Ghi chú:**
    * Hàm `phone_controller.handle_screen_data` sẽ được gọi để xử lý logic.
    * Thông tin `screen_id`, `app_name`, `activity_name`, `screenshot_filename`, `elements` (cấu trúc rút gọn), `width`, `height` sẽ được lưu/cập nhật vào node `:Screen` trong Neo4j.
    * Toàn bộ `elements` chi tiết và `window_width`, `window_height` sẽ được ghi vào bảng `detailed_ui_interaction_logs` trong PostgreSQL.

---

## `POST /phone/task_assignment/request`

Client di động yêu cầu một nhiệm vụ (task assignment) mới từ server.

* **Mô tả:**
    Khi client sẵn sàng nhận nhiệm vụ mới, nó sẽ gọi API này. Server sẽ kiểm tra các task assignments đang chờ cho thiết bị đó, ưu tiên theo `priority` và `scheduled_start_time`, sau đó trả về thông tin nhiệm vụ và gói chiến lược (strategy package) tương ứng.
* **Request Body (JSON):**
    ```json
    {
      "device_id": "string (required) - ID của thiết bị yêu cầu nhiệm vụ",
      "available_accounts": [ // Array of objects (optional) - Danh sách các tài khoản đang có trên thiết bị
        {
          "account_id": "string (required) - ID của tài khoản trên thiết bị",
          "app_name": "string (required) - Tên package của ứng dụng mà tài khoản này thuộc về",
          "clone_context": "string (optional) - Thông tin clone (nếu có, ví dụ: 'clone_0', 'clone_1')",
          "status": "string (optional) - Trạng thái của tài khoản trên thiết bị (ví dụ: 'active_logged_in', 'login_required')"
        }
      ],
      "current_task_id": "integer (optional) - ID của task assignment đang thực hiện (nếu có, để server biết không giao lại task đó)"
    }
    ```
* **Response Success (200 OK):**
    * **Nếu có nhiệm vụ phù hợp:**
        ```json
        {
          "success": true,
          "assignment": {
            "task_assignment_id": 123, // ID của bản ghi task_assignments
            "device_account_id": 45,   // ID của bản ghi device_accounts (liên kết device và account)
            "account_id": "user_account_xyz", // ID của tài khoản sẽ thực hiện (từ bảng accounts)
            "app_name": "com.example.app",
            "clone_context": "clone_0",
            "strategy_id": "main_strategy_app_x", // ID của Control Strategy sẽ được thực thi
            "priority": 10,
            "target_data": { // Dữ liệu JSON cụ thể cho nhiệm vụ này
              "target_url": "[http://example.com/profile/abc](http://example.com/profile/abc)",
              "action_type": "like_post",
              "post_id": "post12345"
            },
            "notes": "Nhiệm vụ tương tác bài viết cụ thể"
          },
          "strategy_package": { // Gói JSON chứa các stage và transition của strategy_id trên
            "strategy_id": "main_strategy_app_x",
            "initial_stage_id": "start_interaction",
            "stages": [
              {
                "stage_id": "start_interaction",
                "description": "Bắt đầu tương tác",
                "identifying_elements": { /* PIE cho stage này nếu cần */ }
              }
              // ... các stages khác
            ],
            "transitions": [
              {
                "current_stage_id": "start_interaction",
                "user_intent": "on_stage_entry", // Hoặc trigger khác
                "priority": 0,
                "next_stage_id": "perform_action",
                "action_macro_code": "OPEN_URL",
                "action_params_str": "{\"url_variable_name\": \"target_data.target_url\"}"
              }
              // ... các transitions khác
            ]
          }
        }
        ```
    * **Nếu không có nhiệm vụ nào:**
        ```json
        {
          "success": true,
          "assignment": null,
          "strategy_package": null,
          "message": "No suitable tasks available at the moment."
        }
        ```
* **Response Error:**
    * **400 Bad Request:** Nếu thiếu `device_id`.
    * **500 Internal Server Error:** Lỗi server khi tìm kiếm nhiệm vụ hoặc biên dịch strategy.
* **Ghi chú:**
    * Server sẽ cập nhật bảng `device_accounts` dựa trên `available_accounts` từ client.
    * Logic chọn nhiệm vụ nằm trong `phone_controller.request_task_assignment`.
    * Hàm `compile_strategy_package` (hoặc tương đương là `assemble_mainloop_package_from_definition` cho mainloop, hoặc `compile_control_strategy_package` cho control) trong `phone_controller` được sử dụng để tạo `strategy_package`.

---

## `POST /phone/task_assignment/update`

Client di động cập nhật trạng thái của một nhiệm vụ đang thực hiện.

* **Mô tả:**
    Sau khi nhận một nhiệm vụ, client sẽ gọi API này để thông báo tiến trình, trạng thái hoàn thành, hoặc lỗi gặp phải. Thông tin này được ghi vào bảng `task_assignment_logs` và cập nhật trạng thái của `task_assignments`.
* **Request Body (JSON):**
    ```json
    {
      "device_id": "string (required) - ID của thiết bị",
      "task_assignment_id": "integer (required) - ID của nhiệm vụ đang được cập nhật",
      "status": "string (required) - Trạng thái mới của nhiệm vụ (ví dụ: 'running', 'completed', 'error', 'interrupted', 'retrying')",
      "current_stage": "string (optional) - Stage hiện tại trong chiến lược mà client đang thực thi",
      "message": "string (optional) - Thông báo chi tiết, đặc biệt khi có lỗi (ví dụ: 'Element not found', 'Login failed')",
      "result_data": { // object (optional) - Dữ liệu kết quả của nhiệm vụ (nếu có)
        "likes_count": 10,
        "comment_id": "cmt789"
      },
      "detailed_log_entry": { // object (optional) - Thông tin chi tiết về bước thực hiện cuối cùng hoặc trạng thái UI khi có sự kiện
        "action_taken": "click_element",
        "element_details": {"resource_id": "com.app:id/button_like", "text": "Like"},
        "timestamp": "2025-05-20T10:30:00Z",
        "current_ui_state_summary": { // Tóm tắt UI state nếu cần
            "activity_name": "com.example.PostViewActivity",
            "visible_elements_count": 15
        }
        // Có thể bao gồm cả full UI state nếu server yêu cầu hoặc cho mục đích gỡ lỗi
        // "full_ui_elements": [ { ... element_data ... } ]
      }
    }
    ```
* **Response Success (200 OK):**
    ```json
    {
      "success": true,
      "message": "Task update received and logged."
    }
    ```
* **Response Error:**
    * **400 Bad Request:** Nếu thiếu `device_id`, `task_assignment_id`, `status` hoặc định dạng không hợp lệ.
    * **404 Not Found:** Nếu `task_assignment_id` không tồn tại.
    * **500 Internal Server Error:** Lỗi server khi cập nhật CSDL.
* **Ghi chú:**
    * Hàm `phone_controller.update_task_assignment_status` xử lý logic.
    * Một bản ghi mới sẽ được thêm vào `task_assignment_logs`.
    * Bản ghi `task_assignments` tương ứng sẽ được cập nhật `status`, `last_updated_at`, và `completed_at` (nếu status là 'completed' hoặc 'error').

---

## `POST /api/upload/screenshot`

Client tải file ảnh chụp màn hình lên server.

* **Mô tả:**
    API này thường được gọi sau khi client đã gửi thông tin màn hình qua `/phone/screen_data` (trong đó có `screenshot_filename`). Server sẽ lưu file ảnh vào thư mục được cấu hình (`SCREENSHOT_STORAGE_PATH` / `app_name` / `filename`).
* **Request Body (Multipart Form Data):**
    * `file` (File, required): Dữ liệu file ảnh nhị phân.
    * `filename` (string, required): Tên file mà server sẽ sử dụng để lưu. Tên này phải khớp với `screenshot_filename` đã được thông báo trước đó.
    * `app_name` (string, required): Tên package của ứng dụng, dùng để tạo thư mục con lưu trữ ảnh cho ứng dụng đó.
* **Response Success (201 Created):**
    ```json
    {
      "success": true,
      "message": "Screenshot uploaded successfully.",
      "saved_server_path_debug": "/path/to/storage/app_name/filename.png" // Chỉ để debug
    }
    ```
* **Response Error:**
    * **400 Bad Request:** Nếu thiếu `file`, `filename`, hoặc `app_name` trong form data, hoặc file không hợp lệ.
    * **500 Internal Server Error:** Nếu server không thể lưu file (ví dụ: lỗi phân quyền, hết dung lượng, `SCREENSHOT_STORAGE_PATH` không được cấu hình).
* **Ghi chú:**
    * Hàm `upload_screenshot_from_client` trong `app/routes.py` xử lý việc này.
    * Sử dụng `secure_filename` để đảm bảo tên file và tên thư mục `app_name` an toàn.
    * Thư mục con cho `app_name` sẽ được tạo tự động nếu chưa tồn tại.
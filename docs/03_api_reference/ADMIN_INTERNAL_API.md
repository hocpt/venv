# API Nội bộ cho Giao diện Admin

Các API này được sử dụng bởi frontend của trang quản trị (Admin UI) để lấy dữ liệu động, thực hiện các hành động cập nhật mà không cần tải lại toàn bộ trang, hoặc hỗ trợ các chức năng tương tác phức tạp.

## Mục lục

* [GET /admin/_get_templates](#get-admin_get_templates)
* [GET /admin/_get_stages](#get-admin_get_stages)
* [GET /admin/_get_live_job_statuses](#get-admin_get_live_job_statuses)
* [GET /admin/_internal/accounts_for_device](#get-admin_internalaccounts_for_device)
* [GET /admin/_internal/api-doc-details/{doc_id}](#get-admin_internalapi-doc-detailsdoc_id)
* [GET /admin/api/mapping_data](#get-adminapimapping_data)
* [GET /admin/api/screen_elements_for_mapping/{screen_id}](#get-adminapiscreen_elements_for_mappingscreen_id)
* [POST /admin/api/element/classify](#post-adminapielementclassify)
* [POST /admin/api/element/mark_explored](#post-adminapielementmark_explored)
* [POST /admin/api/screen/{screen_id}/suggest_classifications](#post-adminapiscreenscreen_idsuggest_classifications)
* [GET /admin/api/mapping/screen-definitions](#get-adminapimappingscreen-definitions)
* [POST /admin/api/mapping/screen-definitions](#post-adminapimappingscreen-definitions)
* [GET /admin/api/mapping/screen-definitions/{def_id}](#get-adminapimappingscreen-definitionsdef_id)
* [PUT /admin/api/mapping/screen-definitions/{def_id}](#put-adminapimappingscreen-definitionsdef_id)
* [DELETE /admin/api/mapping/screen-definitions/{def_id}](#delete-adminapimappingscreen-definitionsdef_id)
* [GET /admin/api/pie_definition_conditions](#get-adminapipie_definition_conditions)
* [POST /admin/api/pie_definition/{defined_pie_id}/update_conditions](#post-adminapipie_definitiondefined_pie_idupdate_conditions)
* [POST /admin/api/mapping/management/nodes/define_new_pie_with_conditions](#post-adminapimappingmanagementnodesdefine_new_pie_with_conditions)
* [POST /admin/api/mapping/transition/update/{neo4j_edge_id}](#post-adminapimappingtransitionupdateneo4j_edge_id)
* [GET /admin/api/mapping/management/nodes](#get-adminapimappingmanagementnodes) (Mới cho Node Management Table)
* [POST /admin/api/mapping/management/nodes/{screen_id}/delete](#post-adminapimappingmanagementnodesscreen_iddelete) (Mới cho Node Management Table)
* [POST /admin/api/mapping/management/nodes/{screen_id}/classify](#post-adminapimappingmanagementnodesscreen_idclassify) (Mới cho Node Management Table)
* [POST /admin/api/mapping/management/nodes/merge-unknown-to-defined](#post-adminapimappingmanagementnodesmerge-unknown-to-defined) (Mới cho Node Management Table)


---

## `GET /admin/_get_templates`

Lấy danh sách tất cả các `template_ref` để điền vào các dropdown trong giao diện admin (ví dụ: khi thêm/sửa Simple Rule).

* **Tham số URL:** Không có.
* **Request Body:** Không có.
* **Response Success (200 OK):**
    ```json
    [
      {"template_ref": "greeting_general"},
      {"template_ref": "product_info_variation1"},
      // ...
    ]
    ```
    Trả về một mảng các object, mỗi object chứa `template_ref`. Trả về mảng rỗng `[]` nếu không có template nào.
* **Response Error:**
    * **500 Internal Server Error:** Nếu có lỗi khi truy vấn CSDL.

---

## `GET /admin/_get_stages`

Lấy danh sách tất cả các stage (`stage_id` và `name`) để điền vào các dropdown trong giao diện admin (ví dụ: khi thêm/sửa Strategy hoặc Transition).

* **Tham số URL:** Không có.
* **Request Body:** Không có.
* **Response Success (200 OK):**
    ```json
    [
      {"stage_id": "initial_greeting", "name": "Initial Greeting Stage"},
      {"stage_id": "product_query", "name": "Product Query Stage"},
      // ...
    ]
    ```
    Trả về một mảng các object, mỗi object chứa `stage_id` và `name`. Trả về mảng rỗng `[]` nếu không có stage nào.
* **Response Error:**
    * **500 Internal Server Error:** Nếu có lỗi khi truy vấn CSDL.

---

## `GET /admin/_get_live_job_statuses`

Lấy trạng thái hoạt động (thời gian chạy kế tiếp hoặc trạng thái 'Paused'/'Not Scheduled') của các tác vụ nền (scheduled jobs) để cập nhật động trên giao diện admin.

* **Tham số URL:** Không có.
* **Request Body:** Không có.
* **Response Success (200 OK):**
    ```json
    {
      "suggestion_job": "14:30:00 21/05/2025", // Thời gian chạy kế tiếp đã định dạng
      "another_job_id": "Paused",
      "sim_run_config_123": "Not Scheduled" // Nếu job có config nhưng không chạy
      // ...
    }
    ```
    Trả về một object với key là `job_id` và value là chuỗi mô tả trạng thái.
* **Response Error:**
    * **500 Internal Server Error:** Nếu có lỗi khi truy vấn CSDL `apscheduler_jobs` hoặc `scheduled_jobs`.

---

## `GET /admin/_internal/accounts_for_device`

Lấy danh sách các tài khoản đã được liên kết với một `device_id` cụ thể. Được sử dụng để điền dropdown Tài khoản một cách động khi admin chọn Thiết bị trong form Thêm Task Assignment.

* **Tham số URL:**
    * `device_id` (string, required): ID của thiết bị.
* **Request Body:** Không có.
* **Response Success (200 OK):**
    ```json
    [
      {
        "device_account_id": 1, // ID từ bảng device_accounts
        "account_id": "user_abc", // ID từ bảng accounts
        "username": "User ABC",
        "platform": "tiktok"
      },
      // ...
    ]
    ```
    Trả về một mảng các object, mỗi object chứa thông tin về một tài khoản liên kết. Trả về mảng rỗng `[]` nếu không có tài khoản nào liên kết hoặc `device_id` không hợp lệ.
* **Response Error:**
    * **400 Bad Request:** Nếu thiếu `device_id`.
    * **500 Internal Server Error:** Lỗi truy vấn CSDL.

---

## `GET /admin/_internal/api-doc-details/{doc_id}`

Lấy thông tin chi tiết của một bản ghi tài liệu API từ bảng `api_documentation` dựa trên `doc_id` của nó. Được sử dụng để hiển thị chi tiết khi người dùng nhấp vào một API trên trang danh sách `/admin/api-docs`.

* **Tham số URL:**
    * `doc_id` (integer, required): ID của tài liệu API cần lấy.
* **Request Body:** Không có.
* **Response Success (200 OK):**
    ```json
    {
      "doc_id": 1,
      "endpoint_path": "/phone/register_device",
      "http_method": "POST",
      "summary": "Đăng ký thiết bị mới",
      "description": "Client di động gọi API này...",
      "request_notes": "device_id là bắt buộc.",
      "request_example": "{\n  \"device_id\": \"unique_device_id_123\",\n  \"device_name\": \"My Test Phone\"\n}",
      "response_notes": "Trả về device_id đã đăng ký.",
      "success_response_example": "{\n  \"success\": true,\n  \"message\": \"Device registered successfully.\",\n  \"device_id\": \"unique_device_id_123\"\n}",
      "error_response_example": "{\n  \"success\": false,\n  \"error\": \"Missing device_id.\"\n}",
      "notes": "API này cũng cập nhật last_seen_at.",
      "is_active": true,
      "created_at": "2025-05-20T10:00:00Z",
      "updated_at": "2025-05-20T11:00:00Z"
    }
    ```
* **Response Error:**
    * **404 Not Found:** Nếu không tìm thấy `doc_id`.
        ```json
        {
          "error": "API Doc with ID 123 not found."
        }
        ```
    * **500 Internal Server Error:** Lỗi truy vấn CSDL.
        ```json
        {
          "error": "Internal server error"
        }
        ```

---

## `GET /admin/api/mapping_data`

Lấy dữ liệu nodes (Screens) và edges (Transitions) từ Neo4j cho một `app_name` cụ thể, dùng để vẽ đồ thị trong trang Admin Mapping Viewer.

* **Tham số URL:**
    * `app_name` (string, required): Tên package của ứng dụng cần lấy dữ liệu đồ thị.
* **Request Body:** Không có.
* **Response Success (200 OK):**
    ```json
    {
      "nodes": [
        {
          "data": {
            "id": "com.example.app_MainActivity_hash1", // screen_id
            "app_name": "com.example.app",
            "activity": "MainActivity",
            "status": "defined",
            "element_count": 10,
            "screenshot_url": "/screenshots/com.example.app/screenshot_main.png",
            "original_width": 1080,
            "original_height": 1920,
            "label": "MainActivi..." // Nhãn rút gọn cho node
          }
        }
        // ... các nodes khác
      ],
      "edges": [
        {
          "data": {
            "id": "edge_neo4jInternalId123", // ID của cạnh
            "source": "com.example.app_MainActivity_hash1", // screen_id nguồn
            "target": "com.example.app_LoginActivity_hash2", // screen_id đích
            "action_type": "click",
            "element_id": "btn_login_main",
            "status": "confirmed"
            // ... các thuộc tính khác của Transition
          }
        }
        // ... các edges khác
      ]
    }
    ```
* **Response Error:**
    * **400 Bad Request:** Nếu thiếu `app_name`.
    * **500 Internal Server Error:** Lỗi khi truy vấn Neo4j hoặc xử lý dữ liệu.
    * **503 Service Unavailable:** Nếu Neo4j không kết nối được.

---

## `GET /admin/api/screen_elements_for_mapping/{screen_id}`

Lấy danh sách các phần tử UI (elements) của một màn hình (Screen) cụ thể từ Neo4j. Dữ liệu này được sử dụng trong Admin Mapping Viewer khi người dùng chọn một node Screen để xem chi tiết các elements hoặc khi cần chọn element cho một Transition.

* **Tham số URL:**
    * `screen_id` (string, required): ID của màn hình cần lấy elements.
* **Request Body:** Không có.
* **Response Success (200 OK):**
    ```json
    {
      "success": true,
      "elements": [
        {
          "element_id": "element_uuid_1",
          "text": "Login Button",
          "resource_id": "com.example.app:id/btnLogin",
          "class_name": "android.widget.Button",
          "xpath": "/hierarchy/android.widget.FrameLayout[1]/...",
          "bounds": "[100,200][300,400]",
          "clickable": true,
          "visible_to_user": true,
          "classification": "button_login" // Nếu đã được phân loại
        }
        // ... các elements khác của screen_id này
      ]
    }
    ```
* **Response Error:**
    * **404 Not Found:** Nếu `screen_id` không tồn tại trong Neo4j hoặc không có elements nào.
    * **500 Internal Server Error:** Lỗi khi truy vấn Neo4j.
        ```json
        {
          "success": false,
          "error": "Không thể lấy dữ liệu elements từ CSDL. Chi tiết server: Error message from server"
        }
        ```

---

## `POST /admin/api/element/classify`

Cập nhật hoặc thêm mới thông tin phân loại (classification) cho một phần tử UI (element) cụ thể của một màn hình vào bảng `element_classifications` trong CSDL PostgreSQL.

* **Mô tả:**
    API này được gọi từ trang Admin Screen Elements khi người dùng chọn một classification cho element.
* **Request Body (JSON):**
    ```json
    {
      "screen_id": "string (required) - ID của màn hình chứa element",
      "element_id": "string (required) - ID của element cần phân loại",
      "identifier_type": "string (optional) - Loại định danh chính của element (ví dụ: 'resource_id', 'text', 'xpath')",
      "classification": "string (required) - Giá trị classification được chọn (phải nằm trong VALID_CLASSIFICATIONS của AI Service)"
    }
    ```
* **Response Success (200 OK):**
    ```json
    {
      "success": true,
      "message": "Element 'element_id_value' classified as 'classification_value'."
    }
    ```
* **Response Error:**
    * **400 Bad Request:** Nếu thiếu tham số, `classification` không hợp lệ.
    * **500 Internal Server Error:** Lỗi khi cập nhật CSDL PostgreSQL.
        ```json
        {
          "success": false,
          "error": "Mô tả lỗi từ server, ví dụ: Failed to update classification in database."
        }
        ```

---

## `POST /admin/api/element/mark_explored`

Cập nhật trạng thái `manual_explored_override` cho một phần tử UI trong bảng `element_classifications` (PostgreSQL).

* **Mô tả:**
    Cho phép admin ghi đè trạng thái "đã khám phá" của một element, bỏ qua logic tự động dựa trên transitions.
* **Request Body (JSON):**
    ```json
    {
      "screen_id": "string (required) - ID của màn hình",
      "element_id": "string (required) - ID của element",
      "override_status": "string (required) - Giá trị mới: 'force_explored', 'force_unexplored', hoặc 'auto'"
    }
    ```
* **Response Success (200 OK):**
    ```json
    {
      "success": true,
      "message": "Element 'element_id_value' override status updated."
    }
    ```
* **Response Error:**
    * **400 Bad Request:** Nếu thiếu tham số hoặc `override_status` không hợp lệ.
    * **500 Internal Server Error:** Lỗi khi cập nhật CSDL.

---

## `POST /admin/api/screen/{screen_id}/suggest_classifications`

Gửi một danh sách các phần tử UI của một màn hình đến AI Service để nhận gợi ý phân loại (classification) cho từng phần tử.

* **Mô tả:**
    API này được gọi từ trang Admin Screen Elements khi người dùng yêu cầu AI gợi ý classification cho các elements chưa được phân loại.
* **Tham số URL:**
    * `screen_id` (string, required): ID của màn hình chứa các elements.
* **Request Body (JSON):**
    ```json
    {
      "elements": [ // Array of element objects
        {
          "element_id": "element_uuid_1",
          "text": "Login Button",
          "resource_id": "com.example.app:id/btnLogin",
          "class_name": "android.widget.Button",
          // ... các thuộc tính khác của element mà AI cần
        },
        // ...
      ]
    }
    ```
* **Response Success (200 OK):**
    ```json
    {
      "success": true,
      "suggestions": [
        {
          "element_id": "element_uuid_1",
          "text": "Login Button",
          // ... các thuộc tính gốc của element
          "suggested_classification": "button_login" // Gợi ý từ AI
        }
        // ... các elements khác với gợi ý (nếu có)
      ]
    }
    ```
    Nếu AI không đưa ra gợi ý cho một số elements, trường `suggested_classification` có thể không có hoặc là `null`.
* **Response Error:**
    * **400 Bad Request:** Nếu request body không đúng định dạng hoặc danh sách `elements` rỗng/không hợp lệ.
    * **500 Internal Server Error:** Lỗi khi gọi AI Service hoặc xử lý lỗi không mong muốn.
    * **503 Service Unavailable:** Nếu AI Service không khả dụng.

---

## `GET /admin/api/mapping/screen-definitions`

Lấy danh sách các Định nghĩa Màn hình Nhận dạng (PIE Definitions) cho một `app_name` cụ thể từ CSDL PostgreSQL.

* **Tham số URL:**
    * `app_name` (string, required): Tên package của ứng dụng.
* **Request Body:** Không có.
* **Response Success (200 OK):**
    ```json
    [
      {
        "definition_id": 1,
        "app_name": "com.example.app",
        "activity_name": "MainActivity",
        "logical_screen_name": "Main Screen",
        "defined_screen_id": "com.example.app_MainActivity_v1",
        "description": "Màn hình chính của ứng dụng",
        "identifying_elements": [ // Đây là nội dung của cột identifying_elements_json
          {"attribute": "resource_id", "comparison": "equals", "value": "com.example.app:id/title"},
          {"attribute": "text", "comparison": "contains", "value": "Welcome"}
        ],
        "created_at": "2025-05-20T10:00:00Z",
        "updated_at": "2025-05-20T11:00:00Z"
      }
      // ... các PIE definitions khác cho app_name này
    ]
    ```
    Trả về một mảng các object PIE definition. Trả về mảng rỗng `[]` nếu không có định nghĩa nào cho app đó.
* **Response Error:**
    * **400 Bad Request:** Nếu thiếu `app_name`.
    * **500 Internal Server Error:** Lỗi khi truy vấn CSDL.

---

## `POST /admin/api/mapping/screen-definitions`

Thêm một Định nghĩa Màn hình Nhận dạng (PIE Definition) mới vào CSDL PostgreSQL.

* **Request Body (JSON):**
    ```json
    {
      "app_name": "string (required)",
      "activity_name": "string (optional)",
      "logical_screen_name": "string (required) - Tên logic cho màn hình",
      "defined_screen_id": "string (required) - ID định danh duy nhất cho màn hình này trong context của app_name",
      "identifying_elements_json": [ // Array of objects (required) - Danh sách các điều kiện PIE
        {"attribute": "resource_id", "comparison": "equals", "value": "com.example.app:id/some_id"},
        {"attribute": "text", "comparison": "contains", "value": "Some Text"}
      ],
      "description": "string (optional) - Mô tả thêm"
    }
    ```
* **Response Success (201 Created):**
    ```json
    {
      "success": true,
      "message": "Đã thêm định nghĩa màn hình thành công.",
      "definition_id": 123 // ID của bản ghi screen_definitions mới được tạo
    }
    ```
* **Response Error:**
    * **400 Bad Request:** Nếu thiếu trường bắt buộc hoặc `identifying_elements_json` không phải là mảng.
    * **409 Conflict:** Nếu `defined_screen_id` đã tồn tại cho `app_name` đó.
    * **500 Internal Server Error:** Lỗi khi ghi vào CSDL.

---

## `GET /admin/api/mapping/screen-definitions/{def_id}`

Lấy thông tin chi tiết của một Định nghĩa Màn hình Nhận dạng (PIE Definition) cụ thể dựa trên `definition_id` (ID của bảng `screen_definitions`).

* **Tham số URL:**
    * `def_id` (integer, required): ID của PIE definition.
* **Request Body:** Không có.
* **Response Success (200 OK):**
    ```json
    // Cấu trúc tương tự như một phần tử trong response của GET /admin/api/mapping/screen-definitions
    {
      "definition_id": 1,
      "app_name": "com.example.app",
      // ... các trường khác
      "identifying_elements": [ // Lưu ý: hàm DB get_screen_definition_by_id cần join để lấy cả elements
        {"element_def_id": 10, "attribute": "resource_id", "comparison": "equals", "value": "com.example.app:id/title"},
        {"element_def_id": 11, "attribute": "text", "comparison": "contains", "value": "Welcome"}
      ]
    }
    ```
* **Response Error:**
    * **404 Not Found:** Nếu không tìm thấy `def_id`.
    * **500 Internal Server Error:** Lỗi CSDL.

---

## `PUT /admin/api/mapping/screen-definitions/{def_id}`

Cập nhật thông tin của một Định nghĩa Màn hình Nhận dạng (PIE Definition) đã tồn tại.

* **Tham số URL:**
    * `def_id` (integer, required): ID của PIE definition cần cập nhật.
* **Request Body (JSON):** Tương tự như body của `POST /admin/api/mapping/screen-definitions`. Tất cả các trường (ngoại trừ `definition_id`) đều có thể được cập nhật.
    ```json
    {
      "app_name": "string (required)",
      "activity_name": "string (optional)",
      "logical_screen_name": "string (required)",
      "defined_screen_id": "string (required)", // Có thể cho phép sửa hoặc không tùy logic
      "identifying_elements_json": [ /* danh sách điều kiện PIE mới */ ],
      "description": "string (optional)"
    }
    ```
* **Response Success (200 OK):**
    ```json
    {
      "success": true,
      "message": "Cập nhật định nghĩa thành công."
    }
    ```
* **Response Error:**
    * **400 Bad Request:** Dữ liệu không hợp lệ.
    * **404 Not Found:** Nếu `def_id` không tồn tại.
    * **409 Conflict:** Nếu `defined_screen_id` mới (nếu cho phép sửa) bị trùng.
    * **500 Internal Server Error:** Lỗi CSDL.

---

## `DELETE /admin/api/mapping/screen-definitions/{def_id}`

Xóa một Định nghĩa Màn hình Nhận dạng (PIE Definition) và các `screen_definition_elements` liên quan của nó.

* **Tham số URL:**
    * `def_id` (integer, required): ID của PIE definition cần xóa.
* **Request Body:** Không có.
* **Response Success (200 OK):**
    ```json
    {
      "success": true,
      "message": "Đã xóa định nghĩa."
    }
    ```
* **Response Error:**
    * **404 Not Found:** Nếu `def_id` không tồn tại.
    * **500 Internal Server Error:** Lỗi CSDL.
* **Ghi chú:** Cần đảm bảo rằng việc xóa này cũng xử lý các `screen_definition_elements` liên quan (ví dụ: dùng `ON DELETE CASCADE` trong CSDL hoặc xóa tường minh trong code). Hàm `db.delete_screen_definition` có xử lý việc này.

---

## `GET /admin/api/pie_definition_conditions`

Lấy danh sách các điều kiện (PIE conditions/elements) của một Định nghĩa Màn hình Nhận dạng (PIE Definition) cụ thể.

* **Tham số URL:**
    * `defined_screen_id` (string, required): ID định danh của PIE.
    * `app_name` (string, required): Tên package của ứng dụng.
* **Request Body:** Không có.
* **Response Success (200 OK):**
    ```json
    {
      "success": true,
      "conditions": [
        {
          "element_def_id": 10, // ID của screen_definition_elements
          "screen_definition_id": 1, // FK đến screen_definitions
          "attribute": "resource_id",
          "comparison": "equals",
          "value": "com.example.app:id/title_text",
          // "weight": 1.0 (nếu có)
        },
        // ...
      ]
    }
    ```
    Trả về mảng rỗng nếu PIE definition không có conditions hoặc không tìm thấy PIE.
* **Response Error:**
    * **400 Bad Request:** Thiếu `defined_screen_id` hoặc `app_name`.
    * **404 Not Found:** Nếu không tìm thấy PIE definition tương ứng.
    * **500 Internal Server Error:** Lỗi CSDL.

---

## `POST /admin/api/pie_definition/{defined_pie_id}/update_conditions`

Cập nhật (ghi đè hoàn toàn) danh sách các điều kiện (PIE conditions/elements) cho một Định nghĩa Màn hình Nhận dạng (PIE Definition) đã tồn tại. `defined_pie_id` ở đây là `defined_screen_id` của PIE.

* **Tham số URL:**
    * `defined_pie_id` (string, required): ID định danh của PIE definition (`defined_screen_id`).
* **Request Body (JSON):**
    ```json
    {
      "app_name": "string (required) - Tên package của ứng dụng",
      "new_conditions_list": [ // Array of objects (required) - Danh sách ĐẦY ĐỦ các điều kiện mới
        // Mỗi object có cấu trúc: {"attribute": "...", "comparison": "...", "value": "..."}
        // Ví dụ:
        {"attribute": "text", "comparison": "starts_with", "value": "Profile of "},
        {"attribute": "element_id", "comparison": "exists", "value": null} // value có thể là null cho 'exists'
      ]
    }
    ```
* **Response Success (200 OK):**
    ```json
    {
      "success": true,
      "message": "Đã cập nhật các điều kiện PIE thành công."
    }
    ```
* **Response Error:**
    * **400 Bad Request:** Nếu thiếu `app_name`, `new_conditions_list`, hoặc định dạng `new_conditions_list` không hợp lệ.
    * **404 Not Found:** Nếu không tìm thấy PIE definition cho `defined_pie_id` và `app_name`.
    * **500 Internal Server Error:** Lỗi khi cập nhật CSDL.
* **Ghi chú:** API này sẽ xóa tất cả các conditions cũ của PIE đó và thêm các conditions mới từ `new_conditions_list`.

---

## `POST /admin/api/mapping/management/nodes/define_new_pie_with_conditions`

Tạo một Định nghĩa Màn hình Nhận dạng (PIE Definition) mới dựa trên thông tin từ một node "unknown" và các điều kiện do người dùng chọn, sau đó cập nhật node "unknown" đó trong Neo4j để nó trỏ đến hoặc trở thành node "defined" mới.

* **Mô tả:** API này được gọi từ modal "Define New PIE" trên trang Node Management.
* **Request Body (JSON):**
    ```json
    {
      "unknown_node_neo4j_id": "integer (required) - ID nội bộ của node unknown trong Neo4j (elementId(n))",
      "current_unknown_screen_id": "string (required) - screen_id hiện tại của node unknown",
      "app_name": "string (required)",
      "activity_name": "string (optional) - Activity name của node unknown",
      "logical_name": "string (required) - Tên logic cho PIE mới (ví dụ: User Login Screen)",
      "new_defined_screen_id": "string (required) - ID định danh mới cho PIE (ví dụ: com.app.login_v1)",
      "selected_conditions": [ // Array of objects (required, non-empty) - Các điều kiện PIE người dùng chọn
        {"attribute": "resource_id", "comparison": "equals", "value": "com.app:id/btnLogin"},
        {"attribute": "text", "comparison": "contains", "value": "Password"}
      ],
      "description": "string (optional) - Mô tả cho PIE mới"
    }
    ```
* **Response Success (201 Created):**
    ```json
    {
      "success": true,
      "message": "Đã tạo định nghĩa PIE 'User Login Screen' (com.app.login_v1) và cập nhật Node 'unknown_screen_id_value' thành công.",
      "new_pie_db_id": 42, // ID của bản ghi screen_definitions trong PostgreSQL
      "defined_screen_id": "com.app.login_v1" // ID định danh của PIE mới
    }
    ```
* **Response Error:**
    * **400 Bad Request:** Thiếu tham số, `selected_conditions` rỗng hoặc không hợp lệ.
    * **409 Conflict:** Nếu `new_defined_screen_id` đã tồn tại cho `app_name` đó.
    * **500 Internal Server Error:** Lỗi khi tạo PIE trong PostgreSQL hoặc cập nhật node trong Neo4j.
        * Nếu lỗi cập nhật Neo4j sau khi đã tạo PIE, message có thể chỉ rõ điều này.
* **Ghi chú:**
    * Hàm `db.create_new_pie_definition_from_node` được gọi để tạo PIE trong PostgreSQL.
    * Hàm `graph_db.convert_unknown_to_defined_node_wrapper` được gọi để cập nhật node trong Neo4j. Điều này bao gồm việc đổi `screen_id` của node từ `current_unknown_screen_id` thành `new_defined_screen_id`, cập nhật `status` thành 'defined', và có thể cập nhật `logical_name` và các thuộc tính khác. Quan trọng nhất là phải xử lý các cạnh (transitions) vào/ra node cũ để chúng trỏ đúng đến node mới (sau khi đổi ID).

---

## `POST /admin/api/mapping/transition/update/{neo4j_edge_id}`

Cập nhật các thuộc tính của một cạnh Transition trong Neo4j, dựa trên ID nội bộ của cạnh đó trong Neo4j (`elementId(r)`).

* **Mô tả:** API này được gọi từ modal "Edit Transition" trong trang Admin Mapping Viewer.
* **Tham số URL:**
    * `neo4j_edge_id` (string, required): ID nội bộ của cạnh Transition trong Neo4j (ví dụ: kết quả của `elementId(r)`).
* **Request Body (JSON):**
    Một object chứa các thuộc tính của Transition cần cập nhật. Chỉ các trường được cung cấp sẽ được cập nhật.
    ```json
    {
      "action_type": "string (optional) - Ví dụ: 'click', 'input', 'run_macro'",
      "element_id": "string (optional) - ID của element UI kích hoạt transition",
      "identifier_type": "string (optional) - Loại định danh của element (resource_id, text, xpath)",
      "element_text": "string (optional) - Text của element (nếu dùng để định danh)",
      "macro_code": "string (optional) - Mã macro nếu action_type là 'run_macro'",
      "params_json_str": "string (optional) - Chuỗi JSON chứa tham số cho macro",
      "status": "string (optional) - Ví dụ: 'provisional', 'confirmed', 'failed', 'disabled'",
      "attempt_count": "integer (optional)",
      "success_count": "integer (optional)"
    }
    ```
* **Response Success (200 OK):**
    ```json
    {
      "success": true,
      "message": "Cập nhật transition thành công." // Hoặc thông báo chi tiết hơn từ hàm graph_db
    }
    ```
* **Response Error:**
    * **400 Bad Request:** Dữ liệu không hợp lệ (ví dụ: `action_type` không được phép, `params_json_str` không phải JSON hợp lệ).
    * **404 Not Found:** Nếu không tìm thấy transition với `neo4j_edge_id` đó.
    * **500 Internal Server Error:** Lỗi khi cập nhật Neo4j.
* **Ghi chú:**
    * Hàm `graph_db.update_transition_by_neo4j_id_tx` sẽ được gọi để thực hiện việc cập nhật trong một transaction.
    * Cần cẩn thận validate các giá trị đầu vào, đặc biệt là `params_json_str`.
    * Thuộc tính `updated_at` của cạnh sẽ được tự động cập nhật.

---

## `GET /admin/api/mapping/management/nodes`

Lấy danh sách các Node (Screens) từ Neo4j cho trang Quản lý Node, hỗ trợ lọc theo `app_name`, `filter_status` và phân trang.

* **Tham số URL:**
    * `app_name_filter` (string, optional): Lọc theo tên package ứng dụng.
    * `filter_status` (string, optional, default: 'unknown'): Lọc theo trạng thái của node (ví dụ: 'unknown', 'defined', 'explored', 'error', 'all').
    * `page` (integer, optional, default: 1): Số trang.
* **Request Body:** Không có.
* **Response Success (200 OK):**
    ```json
    {
      "nodes": [
        {
          "screen_id": "com.example.app_SomeActivity_hash123",
          "app_name": "com.example.app",
          "activity_name": "SomeActivity",
          "status": "unknown",
          "element_count": 5,
          "screenshot_path": "screenshot_unknown1.png",
          "screenshot_full_url": "/screenshots/com.example.app/screenshot_unknown1.png",
          "width": 1080,
          "height": 1920,
          "node_classification": "general_interaction", // Phân loại node (nếu có)
          "created_at": "2025-05-20T10:00:00Z", // Đã chuyển sang ISO format
          "last_seen": "2025-05-21T14:30:00Z", // Đã chuyển sang ISO format
          "logical_pie_name": null, // Sẽ có giá trị nếu status là 'defined' và có PIE tương ứng
          "defined_as_screen_id": null, // Sẽ có giá trị nếu status là 'defined_from_unknown'
          "id_cho_data_attribute_html": "neo4j_internal_id_1" // ID nội bộ Neo4j
        }
        // ... các nodes khác
      ],
      "pagination": {
        "page": 1,
        "per_page": 15,
        "total_items": 50,
        "total_pages": 4,
        "has_prev": false,
        "has_next": true,
        "prev_num": null,
        "next_num": 2
      }
    }
    ```
* **Response Error:**
    * **500 Internal Server Error:** Lỗi khi truy vấn Neo4j.
* **Ghi chú:**
    * Hàm `graph_db.get_screen_nodes_for_management` được sử dụng.
    * Các trường datetime từ Neo4j được chuyển đổi sang chuỗi ISO 8601.
    * `screenshot_full_url` được tạo động.
    * `id_cho_data_attribute_html` là ID nội bộ của Neo4j (`elementId(n)`), dùng cho các thao tác trên dòng của bảng.

---

## `POST /admin/api/mapping/management/nodes/{screen_id}/delete`

Xóa một Node (Screen) khỏi Neo4j và file ảnh chụp màn hình liên quan của nó khỏi server.

* **Tham số URL:**
    * `screen_id` (string, required): ID của screen node cần xóa.
* **Request Body (JSON):**
    ```json
    {
      "app_name": "string (required) - Tên package của ứng dụng chứa node này"
    }
    ```
* **Response Success (200 OK):**
    ```json
    {
      "success": true,
      "message": "Đã xóa Node com.example.app_SomeActivity_hash123 và các dữ liệu liên quan thành công."
    }
    ```
    Hoặc có thể có thông báo lỗi phụ nếu xóa file ảnh thất bại nhưng xóa node Neo4j thành công.
* **Response Error:**
    * **400 Bad Request:** Thiếu `app_name` trong body.
    * **404 Not Found:** Nếu node không tìm thấy trong Neo4j.
    * **500 Internal Server Error:** Lỗi khi xóa node Neo4j hoặc xóa file.
* **Ghi chú:**
    * Hàm `graph_db.delete_screen_node_logic` được gọi để xóa node và các cạnh liên quan trong Neo4j.
    * Thông tin `app_name` và `screenshot_path` của node được lấy từ Neo4j TRƯỚC KHI xóa node để xác định đúng file ảnh cần xóa.
    * File ảnh vật lý được xóa từ đường dẫn `SCREENSHOT_STORAGE_PATH` / `app_name_of_node` / `screenshot_filename`.

---

## `POST /admin/api/mapping/management/nodes/{screen_id}/classify`

Cập nhật hoặc đặt thuộc tính `node_classification` cho một Screen Node trong Neo4j.

* **Tham số URL:**
    * `screen_id` (string, required): ID của screen node cần phân loại.
* **Request Body (JSON):**
    ```json
    {
      "app_name": "string (required) - Tên package của ứng dụng chứa node này",
      "node_classification": "string (optional) - Giá trị phân loại mới. Nếu là chuỗi rỗng hoặc null, thuộc tính classification sẽ bị xóa khỏi node."
    }
    ```
* **Response Success (200 OK):**
    ```json
    {
      "success": true,
      "message": "Đã cập nhật phân loại cho Node com.example.app_SomeActivity_hash123."
    }
    ```
* **Response Error:**
    * **400 Bad Request:** Thiếu `app_name`.
    * **500 Internal Server Error:** Lỗi khi cập nhật Neo4j.
* **Ghi chú:**
    * Hàm `graph_db.update_node_classification_in_neo4j` được gọi để thực hiện.

---

## `POST /admin/api/mapping/management/nodes/merge-unknown-to-defined`

Merge một Node "unknown" vào một Node "defined" đã tồn tại trong Neo4j. Node "unknown" (nguồn) sẽ bị xóa sau khi merge.

* **Mô tả:** Được sử dụng khi admin xác định một node "unknown" thực chất là một phiên bản của một node "defined" đã có PIE.
* **Request Body (JSON):**
    ```json
    {
      "unknown_screen_id": "string (required) - screen_id của node unknown cần merge",
      "target_defined_screen_id": "string (required) - screen_id của node defined đích",
      "app_name": "string (required) - Tên package của ứng dụng"
    }
    ```
* **Response Success (200 OK):**
    ```json
    {
      "success": true,
      "message": "Node Unknown 'unknown_id_value' đã được merge thành công vào 'defined_id_value'."
    }
    ```
* **Response Error:**
    * **400 Bad Request:** Thiếu tham số, hoặc `unknown_screen_id` trùng với `target_defined_screen_id`, hoặc `target_defined_screen_id` không phải là một PIE hợp lệ.
    * **500 Internal Server Error:** Lỗi khi thực hiện merge trong Neo4j.
* **Ghi chú:**
    * Hàm `graph_db.merge_neo4j_screen_nodes_and_delete_source` thực hiện logic này.
    * Logic merge bao gồm:
        * Chuyển tất cả các cạnh vào/ra của node nguồn sang node đích.
        * Kết hợp/cập nhật thuộc tính từ node nguồn sang node đích (nếu cần).
        * Xóa node nguồn.
    * Có thể có logic xóa file ảnh của node nguồn nếu nó khác với ảnh của node đích.
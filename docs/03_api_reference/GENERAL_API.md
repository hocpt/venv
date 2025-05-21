# API Chung

Các API này phục vụ các chức năng chung của hệ thống, không thuộc về client di động cụ thể hay các tác vụ nội bộ của admin.

## Mục lục

* [POST /receive_content_for_reply](#post-receive_content_for_reply)
* [GET /favicon.ico](#get-faviconico)
* [GET /screenshots/{app_name}/{filename}](#get-screenshotsapp_namefilename)

---

## `POST /receive_content_for_reply`

Endpoint chính để client (ví dụ: client di động hoặc một hệ thống khác) gửi nội dung văn bản đã nhận được từ người dùng và nhận lại một phản hồi từ hệ thống HPT11. Phản hồi này có thể được tạo ra dựa trên các luật (simple rules), template, hoặc bởi AI.

* **Mô tả:**
    API này xử lý một lượt tương tác. Nó sẽ:
    1.  Lấy thông tin tài khoản và persona mặc định (nếu có).
    2.  Xác định chiến lược (strategy) và giai đoạn (stage) hiện tại của hội thoại (dựa trên `thread_id`).
    3.  Phát hiện ý định (intent) của người dùng từ `received_text` bằng AI.
    4.  Ghi log tương tác ban đầu vào CSDL.
    5.  Tìm kiếm luật chuyển tiếp (transition) phù hợp. Nếu có và có template, sẽ sử dụng template đó để trả lời.
    6.  Nếu không có luật/template phù hợp, sẽ gọi AI (với persona đã xác định) để tạo phản hồi.
    7.  Cập nhật log tương tác với phản hồi và trạng thái cuối cùng.
    8.  Trả về phản hồi và trạng thái cho client.
* **Request Body (JSON):**
    ```json
    {
      "account_id": "string (required) - ID của tài khoản đang tương tác",
      "received_text": "string (required) - Nội dung văn bản người dùng gửi",
      "app": "string (optional, default: 'unknown') - Tên ứng dụng/nền tảng của client (ví dụ: 'tiktok', 'zalo')",
      "thread_id": "string (optional) - ID của luồng hội thoại để duy trì ngữ cảnh. Nếu không có, một luồng mới có thể được ngầm định tạo."
    }
    ```
* **Response Success (200 OK):**
    ```json
    {
      "reply_text": "Đây là nội dung phản hồi từ hệ thống.",
      "status": "success_ai", // Hoặc "success_strategy_template", "success_fallback_template", v.v.
      // "next_action": { // (Tùy chọn, nếu có gợi ý hành động tiếp theo từ luật)
      //   "type": "CLICK_BUTTON",
      //   "target_id": "button_confirm_id"
      // }
    }
    ```
    Giá trị của `status` cho biết nguồn gốc và kết quả của phản hồi:
    * `success_strategy_template`: Phản hồi từ template dựa trên luật thành công.
    * `success_ai`: Phản hồi từ AI thành công.
    * `success_fallback_template`: Phản hồi từ template dự phòng (nếu AI lỗi nhưng có fallback).
    * Các trạng thái lỗi khác như `error_no_json_data`, `error_missing_data`, `error_no_variation`, `error_ai_...`, `error_server_unexpected`.
* **Response Error:**
    * **400 Bad Request:** Nếu thiếu `account_id` hoặc `received_text`.
        ```json
        {
          "reply_text": "",
          "status": "error_missing_data"
        }
        ```
    * **500 Internal Server Error:** Nếu có lỗi nghiêm trọng ở server.
        ```json
        {
          "reply_text": "",
          "status": "error_server_unexpected"
        }
        ```
* **Ghi chú:**
    * Toàn bộ quá trình xử lý được ghi lại trong bảng `interaction_history`.
    * Logic chọn Persona được ưu tiên từ `default_persona_id` của `account_id`, nếu không có thì dùng `DEFAULT_REPLY_PERSONA_ID` từ config.

---

## `GET /favicon.ico`

Phục vụ file icon hiển thị trên tab trình duyệt.

* **Mô tả:** Trình duyệt tự động yêu cầu file này.
* **Tham số URL:** Không có.
* **Request Body:** Không có.
* **Response Success (200 OK):**
    * **Content-Type:** `image/vnd.microsoft.icon`
    * **Body:** Dữ liệu nhị phân của file `favicon.ico` (nằm trong thư mục `static`).
* **Response Error:**
    * **404 Not Found:** Nếu file `favicon.ico` không tồn tại trong thư mục `static`.

---

## `GET /screenshots/{app_name}/{filename}`

Phục vụ file ảnh chụp màn hình đã được lưu trữ trên server, dựa trên tên ứng dụng và tên file.

* **Mô tả:**
    API này được sử dụng bởi giao diện Admin Mapping Viewer để hiển thị ảnh chụp màn hình tương ứng với các Screen Node.
* **Tham số URL:**
    * `app_name` (string, required): Tên package của ứng dụng (được dùng làm tên thư mục con).
    * `filename` (string, required): Tên file ảnh chụp màn hình (ví dụ: `uuid_generated_by_client.png`).
* **Request Body:** Không có.
* **Response Success (200 OK):**
    * **Content-Type:** (Tự động xác định, thường là `image/png` hoặc `image/jpeg`).
    * **Body:** Dữ liệu nhị phân của file ảnh.
* **Response Error:**
    * **400 Bad Request:** Nếu `app_name` hoặc `filename` không hợp lệ sau khi được làm sạch (sanitize).
    * **404 Not Found:** Nếu thư mục ứng dụng hoặc file ảnh không tồn tại trên server tại đường dẫn `SCREENSHOT_STORAGE_PATH/{app_name}/{filename}`.
    * **500 Internal Server Error:** Nếu `SCREENSHOT_STORAGE_PATH` không được cấu hình hoặc có lỗi server khác.
* **Ghi chú:**
    * Đường dẫn `SCREENSHOT_STORAGE_PATH` được lấy từ `app.config`.
    * `app_name` và `filename` được "sanitize" để tránh các vấn đề bảo mật đường dẫn.
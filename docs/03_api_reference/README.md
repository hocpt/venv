# Tham chiếu API

Phần này cung cấp tài liệu chi tiết về các API của hệ thống HPT11. Các API này được sử dụng bởi client (ứng dụng di động), giao diện admin, hoặc các dịch vụ nội bộ khác.

## Tổ chức

Tài liệu API được chia thành các mục dựa trên nguồn gốc hoặc mục đích sử dụng của API:

* **[API cho Client Điện thoại (PHONE_CLIENT_API.md)](PHONE_CLIENT_API.md):** Các API mà ứng dụng di động sử dụng để tương tác với backend, ví dụ: đăng ký thiết bị, yêu cầu gói chiến lược, gửi trạng thái UI, upload file.
* **[API Nội bộ Trang Admin (ADMIN_INTERNAL_API.md)](ADMIN_INTERNAL_API.md):** Các API được sử dụng bởi frontend của trang admin để lấy dữ liệu cho các bảng, modal, hoặc thực hiện các hành động quản trị không đồng bộ.
* **[API Tổng quát (GENERAL_API.md)](GENERAL_API.md):** Các API khác không thuộc hai nhóm trên, ví dụ: API xử lý yêu cầu trả lời chung (`/receive_content_for_reply`).

## Quy ước Chung

* **Base URL:** Tất cả các API đều có thể truy cập qua base URL của ứng dụng (ví dụ: `http://localhost:5000`).
* **Định dạng Dữ liệu:** Hầu hết các API sử dụng JSON cho cả request body và response body. Header `Content-Type: application/json` nên được sử dụng.
* **Xác thực:** (***Cần làm rõ cơ chế xác thực cho từng nhóm API, ví dụ: API key, session-based, token-based***).
* **Mã Trạng thái HTTP:**
    * `200 OK`: Yêu cầu thành công.
    * `201 Created`: Tài nguyên mới được tạo thành công (thường dùng cho POST tạo mới).
    * `204 No Content`: Yêu cầu thành công nhưng không có nội dung trả về (thường dùng cho DELETE).
    * `400 Bad Request`: Yêu cầu không hợp lệ (thiếu tham số, sai định dạng).
    * `401 Unauthorized`: Chưa xác thực.
    * `403 Forbidden`: Đã xác thực nhưng không có quyền truy cập.
    * `404 Not Found`: Tài nguyên không tìm thấy.
    * `409 Conflict`: Xung đột dữ liệu (ví dụ: tạo tài nguyên đã tồn tại).
    * `500 Internal Server Error`: Lỗi máy chủ không xác định.

## Định dạng Tài liệu cho mỗi Endpoint

Mỗi endpoint sẽ được mô tả theo cấu trúc sau:

* **`METHOD /path/to/endpoint`**
    * **Mô tả:** Chức năng của endpoint.
    * **Tham số URL (URL Parameters):** Nếu có.
        * `param_name` (kiểu dữ liệu): Mô tả.
    * **Headers Đặc biệt:** Nếu có.
        * `Header-Name`: Mô tả.
    * **Request Body:** Mô tả các trường, kiểu dữ liệu, tính bắt buộc, ví dụ JSON.
    * **Response Success:** Mã trạng thái, mô tả, ví dụ JSON.
    * **Response Error:** Mã trạng thái, mô tả, ví dụ JSON.
    * **Ghi chú:** Các thông tin quan trọng khác.

Tham khảo các file Markdown con để biết chi tiết từng API.
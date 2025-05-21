# Các Quy trình Xử lý Nghiệp vụ (Workflows)

Thư mục này cung cấp mô tả chi tiết về các quy trình xử lý nghiệp vụ (workflows) chính trong hệ thống HPT11. Việc hiểu rõ các workflows này giúp làm sáng tỏ cách các thành phần khác nhau của hệ thống tương tác với nhau để đạt được một mục tiêu cụ thể hoặc xử lý một kịch bản người dùng nhất định.

Mỗi tệp Markdown trong đây sẽ tập trung vào một workflow cụ thể, phân tích từng bước trong quy trình, dữ liệu đầu vào, đầu ra và các thànhส่วน (components) liên quan.

## Danh sách các Workflows

* **[Quy trình Tương tác từ Điện thoại (`PHONE_INTERACTION.md`)](./PHONE_INTERACTION.md):** Mô tả chi tiết luồng xử lý khi client di động gửi một tin nhắn hoặc nội dung từ người dùng cuối đến server để nhận phản hồi.
* **[Quy trình Định nghĩa PIE từ Node Unknown (`PIE_DEFINITION.md`)](./PIE_DEFINITION.md):** Giải thích các bước mà quản trị viên thực hiện để định nghĩa một Màn hình Nhận dạng (PIE) mới từ một "Screen Node" chưa xác định (unknown) trong hệ thống App Mapping.

*(Các workflows khác có thể được thêm vào đây khi cần thiết, ví dụ: Luồng xử lý Task Assignment, Luồng chạy AI Simulation, Luồng phân tích và tạo AI Suggestion, v.v.)*
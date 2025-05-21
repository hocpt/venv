# Strategies (Chiến lược) và Stages (Giai đoạn)

Hệ thống Chiến lược và Giai đoạn là cốt lõi của việc điều khiển luồng tương tác và tự động hóa trong HPT11. Chúng cho phép định nghĩa các kịch bản phức tạp, từ việc trả lời tin nhắn đơn giản đến việc điều khiển các hành động trên ứng dụng di động.

## 1. Khái niệm Strategy (Chiến lược)

Một **Strategy** (Chiến lược) là một tập hợp các **Stages** (Giai đoạn) và **Transitions** (Chuyển tiếp) được thiết kế để thực hiện một mục tiêu hoặc một luồng công việc cụ thể. Mỗi tài khoản (Account) có thể được gán một chiến lược mặc định, hoặc chiến lược có thể được chọn dựa trên ngữ cảnh.

### 1.1. Các loại Strategy

Hệ thống HPT11 hỗ trợ ba loại Strategy chính, mỗi loại phục vụ một mục đích khác nhau:

* **`language` (Chiến lược Hội thoại):**
    * **Mục đích:** Được sử dụng chủ yếu để xử lý các tương tác dựa trên ngôn ngữ tự nhiên, ví dụ như trả lời tin nhắn của người dùng.
    * **Hoạt động:** Các transitions trong Language Strategy thường dẫn đến việc gửi một tin nhắn phản hồi (lấy từ `response_template_ref`) hoặc chuyển sang một stage khác trong hội thoại.
    * **Quản lý:** Thông qua trang "Quản lý Chiến lược Hội thoại" (`/admin/strategies/language`) trong giao diện admin.
* **`control` (Chiến lược Điều khiển):**
    * **Mục đích:** Được thiết kế để điều khiển các hành động trên client di động, ví dụ như nhấp vào nút, nhập văn bản, điều hướng màn hình.
    * **Hoạt động:** Các transitions trong Control Strategy thường kích hoạt việc thực thi một `action_macro_code` (Macro Code) với các tham số (`action_params_str`) cụ thể. Chúng cũng dựa vào việc nhận dạng màn hình (`identifying_elements` của Stage) và các điều kiện (`condition_type`, `condition_value`) để quyết định hành động.
    * **Quản lý:** Thông qua trang "Quản lý Chiến lược Điều khiển" (`/admin/strategies/control`) trong giao diện admin.
* **`mainloop` (Chiến lược Vòng lặp Chính):**
    * **Mục đích:** Đây là một loại chiến lược cấp cao, thường được gán cho một thiết bị (Device). MainLoop Strategy điều phối việc thực thi các Control Strategy khác dựa trên trạng thái của thiết bị hoặc các điều kiện cụ thể. Nó hoạt động như một vòng lặp liên tục kiểm tra và quyết định hành động.
    * **Hoạt động:** Các transitions trong MainLoop Strategy có thể gọi các Control Strategy khác, kiểm tra các điều kiện hệ thống, hoặc thực hiện các macro đặc biệt.
    * **Quản lý:** Thông qua trang "Quản lý Chiến lược Vòng lặp Chính" (`/admin/strategies/mainloop`) trong giao diện admin.

### 1.2. Thuộc tính của Strategy

Một Strategy được định nghĩa bởi các thuộc tính sau (lưu trong bảng `strategies`):

* `strategy_id` (VARCHAR(255), PRIMARY KEY): ID duy nhất của chiến lược.
* `name` (VARCHAR(255), NOT NULL): Tên gợi nhớ của chiến lược.
* `description` (TEXT): Mô tả chi tiết về mục đích và hoạt động của chiến lược.
* `initial_stage_id` (VARCHAR(255), REFERENCES stages(stage_id)): ID của Stage đầu tiên sẽ được thực thi khi chiến lược này bắt đầu.
* `strategy_type` (VARCHAR(50), NOT NULL): Loại chiến lược ('language', 'control', hoặc 'mainloop').
* `created_at`, `updated_at`: Dấu thời gian tạo và cập nhật.

## 2. Khái niệm Stage (Giai đoạn)

Một **Stage** (Giai đoạn) đại diện cho một bước, một trạng thái cụ thể, hoặc một màn hình cụ thể (trong Control Strategy) trong một Strategy.

### 2.1. Thuộc tính của Stage

Một Stage được định nghĩa bởi các thuộc tính sau (lưu trong bảng `stages`):

* `stage_id` (VARCHAR(255), PRIMARY KEY): ID duy nhất của giai đoạn.
* `strategy_id` (VARCHAR(255), NOT NULL, REFERENCES strategies(strategy_id)): ID của Strategy mà Stage này thuộc về.
* `description` (TEXT): Mô tả về mục đích hoặc trạng thái của Stage này.
* `stage_order` (INTEGER, DEFAULT 0): Thứ tự ưu tiên hoặc sắp xếp của Stage trong một Strategy (hiện tại chưa được sử dụng nhiều trong logic xử lý chính, nhưng có thể dùng để hiển thị).
* `identifying_elements` (JSONB, optional): **Chỉ dùng cho Control/MainLoop Stages.** Một cấu trúc JSON chứa các điều kiện để nhận dạng màn hình (PIE - Potentially Identifiable Elements) tương ứng với Stage này trên client di động. Nếu client báo cáo đang ở một màn hình khớp với `identifying_elements` này, thì Stage này được coi là đang hoạt động.
    * *Ví dụ:*
        ```json
        {
          "elements": [
            {"attribute": "resource_id", "comparison": "equals", "value": "com.example.app:id/login_button"},
            {"attribute": "text", "comparison": "contains", "value": "Welcome"}
          ],
          "logical_operator": "AND" // "AND" hoặc "OR"
        }
        ```
* `created_at`, `updated_at`: Dấu thời gian.

## 3. Khái niệm Transition (Chuyển tiếp)

Một **Transition** (Chuyển tiếp) định nghĩa logic để di chuyển từ một `current_stage_id` sang một `next_stage_id` khác, hoặc để thực hiện một hành động cụ thể tại Stage hiện tại. Việc kích hoạt một Transition phụ thuộc vào `user_intent` (cho Language Strategy) hoặc một `trigger` (cho Control/MainLoop Strategy), cùng với các điều kiện (`condition_type`, `condition_value`) và độ ưu tiên (`priority`).

### 3.1. Thuộc tính của Transition

Một Transition được định nghĩa bởi các thuộc tính sau (lưu trong bảng `stage_transitions`):

* `transition_id` (SERIAL, PRIMARY KEY): ID tự tăng của transition.
* `strategy_id` (VARCHAR(255), NOT NULL, REFERENCES strategies(strategy_id)): Strategy mà transition này thuộc về.
* `current_stage_id` (VARCHAR(255), NOT NULL, REFERENCES stages(stage_id)): Stage nguồn của transition.
* `user_intent` (VARCHAR(255), NOT NULL):
    * Đối với **Language Strategy**: Ý định của người dùng (ví dụ: 'greeting', 'price_query', 'any').
    * Đối với **Control/MainLoop Strategy**: Một trigger hoặc sự kiện (ví dụ: 'on_stage_entry', 'element_clicked', 'condition_met', 'any').
* `priority` (INTEGER, DEFAULT 0): Độ ưu tiên của transition. Nếu nhiều transition cùng khớp, transition có `priority` cao hơn sẽ được chọn.
* `condition_type` (VARCHAR(100), optional): Loại điều kiện để transition được kích hoạt. Ví dụ:
    * `current_stage_equals` (ít dùng, vì đã có `current_stage_id`)
    * `element_exists_text`: Kiểm tra sự tồn tại của element dựa trên text.
    * `element_exists_id`: Kiểm tra sự tồn tại của element dựa trên resource ID.
    * `variable_equals`: Kiểm tra một biến trong ngữ cảnh bằng một giá trị.
    * (Để trống nếu không có điều kiện cụ thể ngoài `user_intent`).
* `condition_value` (TEXT, optional): Giá trị cho `condition_type`.
* `next_stage_id` (VARCHAR(255), REFERENCES stages(stage_id), optional): Stage đích sẽ chuyển đến nếu transition được kích hoạt. Nếu `NULL`, sẽ ở lại Stage hiện tại (hữu ích khi chỉ thực hiện hành động).
* `response_template_ref` (VARCHAR(255), REFERENCES response_templates(template_ref), optional): **Chỉ dùng cho Language Strategy.** Tham chiếu đến một `template_ref` trong bảng `response_templates` để lấy nội dung phản hồi.
* `action_macro_code` (VARCHAR(255), REFERENCES macro_definitions(macro_code), optional): **Chỉ dùng cho Control/MainLoop Strategy.** Tham chiếu đến một `macro_code` trong bảng `macro_definitions` để client di động thực thi.
* `action_params_str` (TEXT, optional): **Chỉ dùng cho Control/MainLoop Strategy.** Một chuỗi JSON chứa các tham số cần thiết cho `action_macro_code`. Client sẽ parse chuỗi này. Ví dụ: `{"url": "https://example.com", "text_to_input": "Hello World"}`.
* `notes` (TEXT, optional): Ghi chú thêm về transition.
* `created_at`, `updated_at`: Dấu thời gian.

### 3.2. Thuộc tính Vòng lặp (Loop Properties) cho Control/MainLoop Transitions

Các transitions trong Control và MainLoop Strategies có thể bao gồm logic vòng lặp:

* `loop_type` (VARCHAR(50), optional): Loại vòng lặp. Các giá trị có thể:
    * `repeat_n`: Lặp lại hành động `N` lần.
    * `while_condition_met`: Lặp lại hành động chừng nào một điều kiện còn đúng.
    * `for_each`: Lặp qua một tập hợp các phần tử (ví dụ: các elements trên màn hình khớp với một selector).
* `loop_count` (INTEGER, optional): Số lần lặp, sử dụng khi `loop_type` là `repeat_n`.
* `loop_condition_type` (VARCHAR(100), optional): Loại điều kiện cho vòng lặp `while_condition_met` (tương tự `condition_type`).
* `loop_condition_value` (TEXT, optional): Giá trị cho `loop_condition_type`.
* `loop_target_selector_str` (TEXT, optional): Một chuỗi JSON hoặc một định dạng selector khác (ví dụ: XPath, CSS selector) để xác định tập hợp các mục tiêu cho vòng lặp `for_each`.
* `loop_variable_name` (VARCHAR(100), optional): Tên biến sẽ được sử dụng để lưu trữ phần tử hiện tại trong vòng lặp `for_each`, có thể được tham chiếu trong `action_params_str`.

## 4. Cách Hoạt động

1.  **Xác định Strategy và Stage Hiện tại:**
    * Dựa trên `account_id` (cho Language Strategy) hoặc `device_id` (cho MainLoop Strategy) và `thread_id` (cho hội thoại) hoặc `task_assignment` (cho Control Strategy), hệ thống xác định `strategy_id` đang hoạt động.
    * `current_stage_id` được lấy từ lần tương tác trước đó trong cùng `thread_id`/`task_assignment`, hoặc là `initial_stage_id` của Strategy nếu là lần đầu.

2.  **Thu thập Trigger/Intent:**
    * **Language Strategy:** `user_intent` được phát hiện từ `received_text` bằng AI.
    * **Control/MainLoop Strategy:** Trigger có thể là:
        * `on_stage_entry`: Kích hoạt ngay khi vào một Stage.
        * Kết quả của việc thực thi một `action_macro_code` trước đó (ví dụ: 'element_clicked', 'api_call_success').
        * Một điều kiện được kiểm tra định kỳ.

3.  **Tìm Transition Phù hợp:**
    * Hệ thống truy vấn bảng `stage_transitions` để tìm các transitions khớp với:
        * `strategy_id`
        * `current_stage_id`
        * `user_intent` (hoặc trigger)
    * Nếu có nhiều transition khớp, transition có `priority` cao nhất sẽ được ưu tiên.
    * Sau đó, `condition_type` và `condition_value` của transition được chọn sẽ được kiểm tra. Nếu điều kiện không đúng, transition đó sẽ bị bỏ qua và hệ thống có thể tìm transition khác có độ ưu tiên thấp hơn.

4.  **Thực thi Hành động và Chuyển Stage:**
    * **Language Strategy:** Nếu transition có `response_template_ref`, hệ thống lấy một variation từ template đó và gửi về làm phản hồi.
    * **Control/MainLoop Strategy:** Nếu transition có `action_macro_code`, lệnh thực thi macro cùng với `action_params_str` sẽ được gửi đến client di động.
    * **Chuyển Stage:** Nếu transition có `next_stage_id`, hệ thống sẽ cập nhật `current_stage_id` thành `next_stage_id` cho lần tương tác tiếp theo. Nếu không, Stage hiện tại được giữ nguyên.
    * **Xử lý Vòng lặp:** Nếu transition có định nghĩa vòng lặp, client di động (hoặc server, tùy thiết kế) sẽ quản lý việc lặp lại hành động và kiểm tra điều kiện dừng.

## 5. Quản lý qua Giao diện Admin

Hệ thống cung cấp các trang quản lý chi tiết cho Strategies, Stages, và Transitions:

* **Quản lý Strategies:**
    * Xem danh sách các strategies theo từng loại (`language`, `control`, `mainloop`).
    * Thêm mới Strategy: Chọn loại, nhập ID, tên, mô tả, chọn `initial_stage_id`.
    * Sửa thông tin Strategy.
    * Xóa Strategy (cần cẩn thận nếu có Stage hoặc Transition đang tham chiếu).

* **Quản lý Stages (trong trang chi tiết của từng Strategy):**
    * Xem danh sách các Stages thuộc một Strategy cụ thể.
    * Thêm mới Stage: Nhập ID, mô tả, thứ tự, và `identifying_elements` (JSON) cho Control/MainLoop Stages.
    * Sửa thông tin Stage.
    * Xóa Stage (cần cẩn thận nếu có Transition đang tham chiếu đến Stage này là `current_stage_id` hoặc `next_stage_id`).

* **Quản lý Transitions (trong trang chi tiết của từng Strategy, thường được hiển thị theo từng Stage):**
    * Xem danh sách các Transitions của một Stage cụ thể.
    * Thêm mới Transition: Chọn `current_stage_id`, `user_intent`/trigger, `priority`, điều kiện, `next_stage_id`.
        * Đối với Language: Chọn `response_template_ref`.
        * Đối với Control/MainLoop: Chọn `action_macro_code`, nhập `action_params_str` (JSON), cấu hình các thuộc tính vòng lặp.
    * Sửa thông tin Transition.
    * Xóa Transition.
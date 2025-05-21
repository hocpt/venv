# Bảng thuật ngữ (Glossary)

Tài liệu này định nghĩa các thuật ngữ, từ viết tắt và khái niệm chuyên ngành thường được sử dụng trong dự án HPT11.

---

## A

* **Account (Tài khoản):**
    Đại diện cho một tài khoản người dùng trên một nền tảng cụ thể (ví dụ: TikTok, Zalo) mà hệ thống HPT11 sẽ quản lý hoặc tương tác thay mặt. Được lưu trong bảng `accounts`.
* **Action (Hành động):**
    Một thao tác cụ thể được thực hiện bởi hệ thống hoặc client, ví dụ: 'click', 'input text', 'send_message', 'run_macro'.
* **Action Macro Code:**
    Một mã định danh cho một kịch bản hành động (macro) được định nghĩa trước, mà client di động có thể thực thi. Ví dụ: `UI_CLICK`, `UI_INPUT_TEXT`. Được lưu trong `macro_definitions`.
* **Action Params (Tham số Hành động):**
    Dữ liệu đầu vào (thường ở dạng JSON) được truyền cho một `Action Macro Code` để tùy chỉnh hành vi của nó. Ví dụ: `{"element_id": "btn_login", "text_to_input": "password123"}`.
* **Activity Name:**
    Trong Android, đây là tên của một Activity class, thường đại diện cho một màn hình của ứng dụng. Được sử dụng trong App Mapping.
* **Admin UI (Giao diện Quản trị):**
    Giao diện web dựa trên Flask mà quản trị viên sử dụng để cấu hình, quản lý và theo dõi hệ thống HPT11.
* **AI (Artificial Intelligence - Trí tuệ Nhân tạo):**
    Đề cập đến việc sử dụng các mô hình học máy (ví dụ: Google Gemini) để thực hiện các tác vụ thông minh như phát hiện ý định, tạo phản hồi, gợi ý, phân loại.
* **AI Persona:**
    Một cấu hình định nghĩa "tính cách" hoặc vai trò cho AI, bao gồm prompt cơ sở, model và các tham số sinh văn bản. Giúp AI phản hồi phù hợp với các ngữ cảnh khác nhau. Lưu trong `ai_personas`.
* **AI Playground (Sân chơi AI):**
    Một trang trong Admin UI cho phép người dùng tương tác trực tiếp với AI model để thử nghiệm prompt và Persona.
* **AI Suggestion (Gợi ý từ AI):**
    Đề xuất về luật (rule) hoặc mẫu phản hồi (template) mới do AI tạo ra dựa trên việc phân tích lịch sử tương tác. Lưu trong `ai_suggestions`.
* **API (Application Programming Interface - Giao diện Lập trình Ứng dụng):**
    Một tập hợp các quy tắc và giao thức cho phép các thành phần phần mềm khác nhau giao tiếp với nhau.
* **API Key:**
    Một mã bí mật được sử dụng để xác thực và ủy quyền truy cập vào một API hoặc dịch vụ (ví dụ: Google Gemini API key). Lưu trong `api_keys`.
* **App Mapping (Ánh xạ Ứng dụng):**
    Quá trình và tính năng xây dựng một mô hình đồ thị về các màn hình, phần tử UI và luồng chuyển tiếp của một ứng dụng di động.
* **APScheduler:**
    Thư viện Python dùng để lập lịch và thực thi các tác vụ nền (background tasks) theo thời gian.
* **Attribute (Thuộc tính - của UI Element):**
    Một đặc điểm của một phần tử UI, ví dụ: `resource_id`, `text`, `class_name`, `xpath`, `clickable`.

## B

* **Background Task (Tác vụ Nền):**
    Một công việc được thực thi ngầm, thường là theo lịch trình hoặc được kích hoạt bởi một sự kiện, không trực tiếp cản trở luồng tương tác chính của người dùng. Ví dụ: `analyze_interactions_and_suggest`.
* **Base Prompt (Prompt Nền tảng):**
    Một phần của AI Persona, là hướng dẫn chung về vai trò, giọng điệu, và kiến thức cơ bản mà AI nên sử dụng.
* **Blueprint (Flask):**
    Một cách để tổ chức một nhóm các route và view liên quan trong một ứng dụng Flask. Dự án sử dụng các blueprint cho `main`, `admin`, và `phone`.
* **Bounds (Tọa độ Bao):**
    Tọa độ (thường là top-left và bottom-right) xác định vị trí và kích thước của một UI Element trên màn hình.

## C

* **Category (Danh mục):**
    Một nhãn dùng để nhóm các Simple Rules hoặc Response Templates.
* **Classification (Phân loại - của UI Element):**
    Một nhãn gán cho UI Element để mô tả chức năng hoặc loại của nó (ví dụ: 'button_login', 'input_username'). Giúp AI và hệ thống hiểu rõ hơn về màn hình. Danh sách các classification hợp lệ được định nghĩa trong `ai_service.VALID_CLASSIFICATIONS`.
* **Clone Context:**
    Một chuỗi định danh (ví dụ: 'clone_0', 'clone_1') để phân biệt các phiên bản nhân bản (cloned instances) của cùng một ứng dụng trên một thiết bị. Được sử dụng trong `device_accounts`.
* **Command Queue (Hàng đợi Lệnh):**
    Bảng `scheduler_commands` hoạt động như một hàng đợi để truyền lệnh từ ứng dụng web đến tiến trình `scheduler_runner.py`.
* **Condition (Điều kiện - của Transition hoặc PIE):**
    Một quy tắc logic phải được thỏa mãn để một Transition được kích hoạt hoặc một màn hình được nhận dạng (PIE). Ví dụ: `element_exists_text`, `variable_equals`.
* **Control Strategy (Chiến lược Điều khiển):**
    Một loại Strategy được thiết kế để tự động hóa các hành động trên giao diện người dùng của ứng dụng di động, thường thông qua việc thực thi các Macro Code.
* **CSDL (Cơ sở dữ liệu):**
    Viết tắt của Cơ sở dữ liệu.
* **CSRF (Cross-Site Request Forgery):**
    Một loại tấn công web. Flask-WTF giúp bảo vệ chống lại nó.
* **Cytoscape.js:**
    Thư viện JavaScript dùng để trực quan hóa đồ thị, được sử dụng trong Admin Mapping Viewer.

## D

* **Dashboard (Bảng điều khiển):**
    Trang chính của Admin UI, hiển thị các thông tin thống kê tổng quan.
* **Defined Screen ID:**
    Một ID chuỗi duy nhất (trong context của `app_name`) do người dùng định nghĩa cho một màn hình đã được nhận dạng bằng PIE. Khác với `screen_id` có thể do client tự sinh ban đầu.
* **Device (Thiết bị):**
    Một thiết bị di động (ví dụ: điện thoại Android) đã được đăng ký với hệ thống HPT11. Thông tin lưu trong bảng `devices`.
* **Device Account Link (Liên kết Thiết bị - Tài khoản):**
    Một bản ghi trong bảng `device_accounts` thể hiện mối quan hệ giữa một `Device` và một `Account`, có thể bao gồm `clone_context` và `app_package_name`.

## E

* **Element (UI Element - Phần tử Giao diện Người dùng):**
    Một thành phần đơn lẻ trên màn hình ứng dụng, ví dụ: nút, ô nhập liệu, hình ảnh.
* **Element ID (Định danh Phần tử):**
    Một ID do client tạo ra để định danh duy nhất một UI Element trong context của một màn hình cụ thể.
* **Endpoint (Điểm cuối API):**
    Một URL cụ thể mà tại đó một API có thể được truy cập để thực hiện một chức năng.
* **Encryption Key (Khóa Mã hóa):**
    Một khóa bí mật được sử dụng để mã hóa và giải mã dữ liệu nhạy cảm.

## F

* **Flask:**
    Một micro web framework phổ biến viết bằng Python, được sử dụng làm nền tảng cho backend của HPT11.

## G

* **Gemini (Google Gemini):**
    Một dòng các mô hình AI đa phương thức của Google, được sử dụng trong dự án này cho các tác vụ như tạo phản hồi, phát hiện ý định, v.v.
* **Generation Config (Cấu hình Sinh văn bản):**
    Các tham số (ví dụ: `temperature`, `max_output_tokens`, `top_p`, `top_k`) điều khiển cách mô hình AI tạo ra văn bản. Được lưu trữ dạng JSONB trong `ai_personas`.
* **Goal (Mục tiêu - của Account):**
    Mục đích hoặc mục tiêu được gán cho một tài khoản (ví dụ: 'customer_support', 'lead_generation').

## H

* **HPT11:**
    Tên mã hoặc tên định danh của dự án này.

## I

* **Identifier Type (Loại Định danh - của UI Element):**
    Cách mà một UI Element được định danh (ví dụ: 'resource_id', 'text', 'xpath', 'element_id').
* **Identifying Elements (JSON - của Stage hoặc PIE Definition):**
    Một cấu trúc JSON mô tả các điều kiện dựa trên UI Elements để nhận dạng một màn hình hoặc một Stage.
* **Initial Stage ID (ID Giai đoạn Khởi đầu):**
    ID của Stage đầu tiên sẽ được kích hoạt khi một Strategy bắt đầu.
* **Intent (User Intent - Ý định Người dùng):**
    Mục đích hoặc ý nghĩa đằng sau một phát ngôn hoặc hành động của người dùng. AI được sử dụng để phát hiện intent từ `received_text`.
* **Interaction History (Lịch sử Tương tác):**
    Bảng `interaction_history` lưu trữ chi tiết về các lượt tương tác giữa hệ thống và người dùng cuối (hoặc AI trong mô phỏng).

## J

* **Jinja2:**
    Một template engine mạnh mẽ cho Python, được Flask sử dụng để render các trang HTML.
* **Job (Scheduled Job - Tác vụ Lập lịch):**
    Một hàm hoặc công việc được APScheduler lên lịch để thực thi. Cấu hình lưu trong `scheduled_jobs`, trạng thái live trong `apscheduler_jobs`.
* **JSON (JavaScript Object Notation):**
    Một định dạng trao đổi dữ liệu nhẹ, dễ đọc và viết, được sử dụng rộng rãi trong các API và lưu trữ cấu hình.

## K

* **Keyword (Từ khóa):**
    Các từ hoặc cụm từ được sử dụng trong `simple_rules` để kích hoạt một phản hồi dựa trên template.

## L

* **Language Strategy (Chiến lược Hội thoại):**
    Một loại Strategy tập trung vào việc xử lý và phản hồi các tương tác ngôn ngữ.
* **Log (Bản ghi):**
    Thông tin được ghi lại về các sự kiện, hành động, hoặc lỗi xảy ra trong hệ thống. Ví dụ: `interaction_history`, `task_assignment_logs`.
* **Logical Screen Name (Tên Logic của Màn hình):**
    Một tên mô tả, thân thiện với người dùng cho một PIE Definition (ví dụ: "Màn hình đăng nhập chính").

* **Loop (Vòng lặp - trong Transition):**
    Khả năng của một Control/MainLoop Transition để lặp lại hành động của nó nhiều lần hoặc cho đến khi một điều kiện được thỏa mãn. Các loại loop: `repeat_n`, `while_condition_met`, `for_each`.

## M

* **Macro Code (Mã Macro):** Xem "Action Macro Code".
* **MainLoop Strategy (Chiến lược Vòng lặp Chính):**
    Một loại Strategy cấp cao, thường được gán cho Device, điều phối các Control Strategy khác và quản lý luồng hoạt động tổng thể của thiết bị.
* **Manual Explored Override (Ghi đè Khám phá Thủ công):**
    Một cờ trong bảng `element_classifications` cho phép admin đánh dấu một element là "đã khám phá" hoặc "chưa khám phá", ghi đè lên logic tự động.
* **Markdown:**
    Ngôn ngữ đánh dấu nhẹ được sử dụng để viết tài liệu này.
* **Merge Nodes (Hợp nhất Node):**
    Trong App Mapping, hành động hợp nhất một `Screen Node` "unknown" vào một `Screen Node` "defined" đã tồn tại, khi admin xác định chúng là cùng một màn hình.

## N

* **Neo4j:**
    Một hệ quản trị cơ sở dữ liệu đồ thị, được sử dụng trong HPT11 để lưu trữ và quản lý dữ liệu App Mapping.
* **Next Action Suggestion (Gợi ý Hành động Tiếp theo):**
    Một gợi ý từ hệ thống (thường từ một Simple Rule hoặc Transition) về hành động mà client nên thực hiện tiếp theo.
* **Next Stage ID (ID Giai đoạn Kế tiếp):**
    ID của Stage mà hệ thống sẽ chuyển đến sau khi một Transition được kích hoạt thành công.
* **Node (Neo4j Node - Nút Đồ thị):**
    Thực thể cơ bản trong cơ sở dữ liệu đồ thị Neo4j. Trong HPT11, `Screen Node` là một ví dụ.

## O

* **ORM (Object Relational Mapper):**
    Một kỹ thuật lập trình cho phép chuyển đổi dữ liệu giữa các hệ thống kiểu không tương thích (ví dụ: database quan hệ và ngôn ngữ lập trình hướng đối tượng). SQLAlchemy là một ORM.

## P

* **Payload (Dữ liệu Gửi kèm):**
    Dữ liệu được gửi trong body của một HTTP request (thường là JSON) hoặc trong một `scheduler_command`.
* **PIE (Potentially Identifiable Elements / Page Identifying Elements - Phần tử Nhận dạng Tiềm năng/Trang):**
    Một tập hợp các điều kiện dựa trên thuộc tính của UI Elements, được sử dụng để nhận dạng một màn hình một cách duy nhất. Định nghĩa PIE được lưu trong `screen_definitions` và `screen_definition_elements`.
* **Platform (Nền tảng):**
    Nền tảng ứng dụng mà một tài khoản thuộc về (ví dụ: 'tiktok', 'zalo').
* **PostgreSQL:**
    Một hệ quản trị cơ sở dữ liệu quan hệ đối tượng mạnh mẽ, được sử dụng làm CSDL chính cho dữ liệu có cấu trúc trong HPT11.
* **Priority (Độ ưu tiên):**
    Một giá trị số được sử dụng để xác định thứ tự ưu tiên xử lý, ví dụ cho Simple Rules hoặc Stage Transitions.
* **Prompt (AI Prompt - Câu lệnh AI):**
    Đầu vào dạng văn bản được cung cấp cho một mô hình AI để nó tạo ra một phản hồi hoặc thực hiện một tác vụ.
* **Prompt Template (Mẫu Prompt):**
    Một mẫu văn bản chuẩn hóa, có thể chứa các placeholder, được sử dụng để xây dựng các prompt hoàn chỉnh gửi đến AI. Lưu trong `prompt_templates`.
* **Pygments:**
    Thư viện Python dùng để tô sáng cú pháp mã nguồn.

## R

* **Received Text (Văn bản Nhận được):**
    Nội dung văn bản mà người dùng cuối gửi đến, được client di động chuyển tiếp cho server.
* **Relationship (Neo4j Relationship - Quan hệ Đồ thị):**
    Kết nối giữa các Node trong cơ sở dữ liệu đồ thị Neo4j. Trong HPT11, `:TRANSITION` là một loại quan hệ quan trọng.
* **Reply Text (Văn bản Phản hồi):**
    Nội dung văn bản mà hệ thống HPT11 tạo ra để trả lời người dùng cuối.
* **Resource ID (Định danh Tài nguyên - của UI Element):**
    Trong Android, đây là một ID duy nhất được gán cho một UI Element trong layout XML (ví dụ: `com.example.app:id/button_login`).
* **Response Template (Mẫu Phản hồi):**
    Xem "Template".
* **Route (Flask Route - Tuyến đường Flask):**
    Một ánh xạ giữa một URL và một hàm Python (view function) trong ứng dụng Flask, xử lý các HTTP request đến URL đó.
* **Rule (Simple Rule - Luật Đơn giản):**
    Một luật dựa trên từ khóa (`trigger_keywords`) để kích hoạt một `template_ref` cụ thể. Lưu trong `simple_rules`.

## S

* **Scheduler (Bộ lập lịch):**
    Đề cập đến APScheduler, chịu trách nhiệm thực thi các tác vụ nền theo lịch trình.
* **Scheduler Command (Lệnh cho Bộ lập lịch):**
    Một yêu cầu được gửi đến `scheduler_runner.py` thông qua bảng `scheduler_commands` để điều khiển scheduler.
* **Schema (Lược đồ CSDL):**
    Cấu trúc của cơ sở dữ liệu, bao gồm các bảng, cột, kiểu dữ liệu, và các ràng buộc. File `automation_schema.sql` định nghĩa lược đồ cho PostgreSQL.
* **Screen ID (Định danh Màn hình):**
    ID duy nhất của một `Screen Node` trong Neo4j.
* **Screen Node (Nút Màn hình):**
    Một Node trong Neo4j đại diện cho một màn hình hoặc một trạng thái UI của ứng dụng.
* **Screenshot (Ảnh chụp Màn hình):**
    Hình ảnh của màn hình ứng dụng tại một thời điểm, được client gửi lên và lưu trên server.
* **Seed Data (Dữ liệu Mẫu/Khởi tạo):**
    Dữ liệu ban đầu được chèn vào CSDL khi thiết lập hệ thống.
* **SQLAlchemy:**
    Một bộ công cụ SQL và ORM cho Python. Được APScheduler sử dụng cho `SQLAlchemyJobStore`.
* **Stage (Giai đoạn):**
    Một bước hoặc trạng thái cụ thể trong một Strategy. Lưu trong `stages`.
* **Status (Trạng thái):**
    Một giá trị chỉ định tình trạng hiện tại của một thực thể, ví dụ: status của `Screen Node` ('unknown', 'defined'), status của `Transition` ('provisional', 'confirmed'), status của `Task Assignment` ('pending', 'running', 'completed').
* **Strategy (Chiến lược):**
    Một tập hợp các Stages và Transitions định nghĩa một kịch bản hoặc luồng công việc. Có các loại: 'language', 'control', 'mainloop'. Lưu trong `strategies`.
* **Strategy Package (Gói Chiến lược):**
    Một cấu trúc dữ liệu (thường là JSON) chứa thông tin đầy đủ về một Strategy (initial stage, stages, transitions) được biên dịch và gửi cho client di động để thực thi.

## T

* **Target Data (Dữ liệu Mục tiêu - của Task Assignment):**
    Một đối tượng JSON chứa thông tin cụ thể mà một Task Assignment cần để thực hiện nhiệm vụ của nó (ví dụ: URL của bài viết cần tương tác, ID người dùng cần gửi tin nhắn). Lưu trong `task_assignments`.
* **Task Assignment (Giao việc):**
    Một nhiệm vụ cụ thể được gán cho một `Device Account` (liên kết giữa thiết bị và tài khoản) để thực thi một `Strategy`. Lưu trong `task_assignments`.
* **Task State (Trạng thái Tác vụ):**
    Bảng `task_states` lưu trữ trạng thái hoặc tiến trình của các tác vụ nền dài hạn (ví dụ: ID của bản ghi cuối cùng đã được `suggestion_job` xử lý).
* **Template (Response Template - Mẫu Phản hồi):**
    Một mẫu văn bản được định nghĩa trước, có thể có nhiều biến thể (variations), được sử dụng để tạo ra các phản hồi nhanh chóng và nhất quán. Thông tin template chính lưu trong `response_templates`, các biến thể trong `template_variations`.
* **Template Ref (Tham chiếu Mẫu):**
    Một ID chuỗi duy nhất tham chiếu đến một `Response Template` trong bảng `response_templates`.
* **Thread ID (ID Luồng hội thoại):**
    Một ID được sử dụng để nhóm các lượt tương tác (turns) thuộc về cùng một cuộc hội thoại, giúp duy trì ngữ cảnh.
* **Transaction (Giao dịch CSDL):**
    Một đơn vị công việc được thực hiện trên cơ sở dữ liệu, đảm bảo tính toàn vẹn dữ liệu (ACID).
* **Transition (Chuyển tiếp):**
    Một quy tắc hoặc hành động trong một Strategy, xác định cách di chuyển từ Stage này sang Stage khác hoặc thực hiện một hành động dựa trên điều kiện. Lưu trong `stage_transitions`.
* **Trigger (Kích hoạt - của Transition hoặc Scheduled Job):**
    Một sự kiện hoặc điều kiện khiến một Transition hoặc một Scheduled Job được thực thi. Ví dụ trigger cho job: 'interval', 'cron', 'date'. Ví dụ trigger cho Control Transition: 'on_stage_entry', 'element_clicked'.

## U

* **UI (User Interface - Giao diện Người dùng):**
    Cách mà người dùng tương tác với một ứng dụng hoặc hệ thống.
* **Unknown Node (Nút Chưa xác định):**
    Một `Screen Node` trong Neo4j có status là 'unknown', nghĩa là nó chưa được liên kết với một PIE Definition chính thức.

## V

* **Variation (Template Variation - Biến thể Mẫu):**
    Một phiên bản văn bản cụ thể của một `Response Template`. Một template có thể có nhiều variations để tạo sự đa dạng trong phản hồi. Lưu trong `template_variations`.

## X

* **XPath (XML Path Language):**
    Một ngôn ngữ truy vấn để chọn các node từ một tài liệu XML (hoặc HTML, UI tree). Có thể được sử dụng để định danh UI Elements.
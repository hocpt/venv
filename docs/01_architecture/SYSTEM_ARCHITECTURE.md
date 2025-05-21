# Kiến trúc Hệ thống

## 1. Tổng quan

Hệ thống HPT11 được xây dựng dựa trên kiến trúc microservices (hoặc monolithic với các module rõ ràng - ***cần làm rõ***), bao gồm các thành phần chính sau:

* **Ứng dụng Flask (Backend):**
    * Xử lý các yêu cầu API từ client (điện thoại, trang admin).
    * Tương tác với các cơ sở dữ liệu (PostgreSQL, Neo4j).
    * Tích hợp với các dịch vụ AI.
    * Quản lý và thực thi các tác vụ nền.
    * Cung cấp giao diện quản trị (Admin UI).
* **Cơ sở dữ liệu PostgreSQL:** Lưu trữ dữ liệu có cấu trúc của hệ thống như:
    * Thông tin người dùng, tài khoản, thiết bị.
    * Luật đơn giản, template trả lời, AI suggestions.
    * Lịch sử tương tác, log tác vụ.
    * Cấu hình AI Personas, API Keys.
    * Định nghĩa màn hình (PIE Definitions) và các điều kiện nhận dạng.
    * Chiến lược (Language, Control, MainLoop) và các giai đoạn (Stages), chuyển tiếp (Transitions) của chúng.
    * Cấu hình và trạng thái các tác vụ nền.
* **Cơ sở dữ liệu Neo4j:** Lưu trữ dữ liệu đồ thị cho chức năng App Mapping:
    * Các Screen Node (đại diện cho các màn hình ứng dụng).
    * Các Transition Edge (đại diện cho các hành động chuyển màn hình).
    * Thuộc tính của nodes và edges (ví dụ: app_name, activity_name, element_id, actionType).
* **AI Service (Module `ai_service.py`):**
    * Đóng gói logic tương tác với các mô hình ngôn ngữ lớn (LLMs) như Gemini.
    * Cung cấp các chức năng:
        * Phát hiện ý định người dùng.
        * Sinh nội dung trả lời.
        * Đề xuất luật mới.
        * Phân loại phần tử UI.
    * Quản lý AI Personas và Prompt Templates.
* **Scheduler (APScheduler):**
    * Quản lý và thực thi các tác vụ nền theo lịch trình (ví dụ: `analyze_interactions_and_suggest`, `approve_all_suggestions_task`, `run_ai_conversation_simulation`).
    * Sử dụng SQLAlchemyJobStore để lưu trữ thông tin job trong PostgreSQL.
* **Client (Ứng dụng Điện thoại):**
    * Gửi yêu cầu và nhận phản hồi từ backend.
    * Thực thi các hành động điều khiển dựa trên gói chiến lược (strategy package) nhận được từ backend (đối với Control/MainLoop Strategies).
    * Upload ảnh chụp màn hình và dữ liệu UI.
* **Giao diện Admin (Flask Admin):**
    * Cung cấp các trang quản lý cho Rules, Templates, Accounts, Devices, Strategies, AI Personas, API Keys, Scheduled Jobs, AI Simulations, App Mapping, PIE Definitions, và hệ thống tài liệu này.

## 2. Sơ đồ Kiến trúc (Đề xuất)

(***Nhúng sơ đồ kiến trúc ở đây nếu có, ví dụ sử dụng Mermaid hoặc ảnh. Ví dụ:***)

```mermaid
graph TD
    A[Client (Mobile App)] -->|HTTP API Request| B(Flask Backend App);
    B -->|SQL Queries| C(PostgreSQL Database);
    B -->|Cypher Queries| D(Neo4j Database);
    B -->|API Calls| E(AI Service / LLM);
    B -->|Job Scheduling| F(APScheduler);
    F -->|Job Store| C;
    G[Admin UI (Flask)] -->|HTTP API Request| B;

    subgraph "Flask Backend App (app/)"
        H(Routes: main, admin, phone)
        I(Controllers/Logic)
        J(Database Modules: database.py, graph_db.py)
        K(AI Service Module: ai_service.py)
        L(Background Tasks)
    end

Dưới đây là nội dung dự kiến cho các tệp Markdown chính trong thư mục docs/, được tổng hợp từ các tệp dự án.

docs/README.md
Markdown

# Tài liệu Dự án HPT11

Chào mừng bạn đến với tài liệu tập trung của dự án HPT11. Hệ thống tài liệu này được thiết kế để cung cấp cái nhìn tổng quan và chi tiết về các khía cạnh khác nhau của dự án, từ kiến trúc tổng thể đến các API cụ thể và luồng xử lý nghiệp vụ.

## Mục tiêu

* **Nguồn thông tin tập trung:** Cung cấp một nơi duy nhất để tìm kiếm thông tin về dự án cho tất cả các thành viên trong nhóm, bao gồm cả AI hỗ trợ.
* **Dễ dàng cập nhật và bảo trì:** Tài liệu được viết dưới dạng Markdown và lưu trữ trên GitHub cùng với mã nguồn, giúp việc theo dõi thay đổi và đồng bộ hóa trở nên đơn giản.
* **Hỗ trợ AI:** Giúp AI nhanh chóng nắm bắt bối cảnh và các chi tiết của dự án trong các phiên làm việc mới.

## Cách sử dụng

Tài liệu được tổ chức thành các thư mục con theo chủ đề. Bạn có thể duyệt qua các mục trong thanh điều hướng bên trái (khi xem trên trang admin) để tìm thông tin cụ thể.

* **[00 Tổng quan Dự án (PROJECT OVERVIEW)](#00_PROJECT_OVERVIEW/PROJECT_SUMMARY.md):** Mục tiêu, chức năng chính, công nghệ sử dụng.
* **[01 Kiến trúc (ARCHITECTURE)](#01_ARCHITECTURE/SYSTEM_ARCHITECTURE.md):** Kiến trúc tổng thể, các thành phần và luồng dữ liệu.
* **[02 Cơ sở dữ liệu (DATABASE)](#02_DATABASE/POSTGRESQL_SCHEMA.md):** Schema của PostgreSQL và mô hình dữ liệu Neo4j.
* **[03 Tham chiếu API (API REFERENCE)](#03_API_REFERENCE/README.md):** Chi tiết về các API của hệ thống, thay thế cho trang `/admin/api-docs` cũ.
* **[04 Chức năng (FEATURES)](#04_FEATURES/README.md):** Mô tả chi tiết các chức năng chính của dự án.
* **[05 Luồng xử lý (WORKFLOWS)](#05_WORKFLOWS/README.md):** Các quy trình nghiệp vụ và luồng xử lý quan trọng.
* **[06 Cài đặt và Cấu hình (SETUP AND CONFIG)](#06_SETUP_AND_CONFIG/REQUIREMENTS.md):** Hướng dẫn cài đặt và các biến môi trường.
* **[07 Bảng thuật ngữ (GLOSSARY)](#07_GLOSSARY.md):** Giải thích các thuật ngữ và từ viết tắt sử dụng trong dự án.

## Đóng góp

Các nhà phát triển chịu trách nhiệm duy trì và cập nhật tài liệu này trên GitHub. Khi có thay đổi về mã nguồn hoặc chức năng, vui lòng cập nhật các tệp Markdown tương ứng.

docs/00_PROJECT_OVERVIEW/PROJECT_SUMMARY.md
Markdown

# Tổng quan Dự án HPT11

## 1. Mục tiêu Dự án

Dự án HPT11 (tên mã nội bộ) được xây dựng nhằm mục đích [***Người dùng cần bổ sung mục tiêu chính của dự án***]. Hệ thống tập trung vào việc [***Người dùng cần bổ sung mô tả ngắn gọn về giải pháp/sản phẩm***].

Các mục tiêu phụ bao gồm:

* Cải thiện khả năng nắm bắt thông tin dự án cho AI (Gemini) để giảm thời gian giải thích lặp lại trong các phiên làm việc mới.
* Tạo nguồn tài liệu tham khảo tập trung, dễ truy cập và cập nhật cho các thành viên trong nhóm.
* Quản lý phiên bản tài liệu đồng bộ với mã nguồn trên GitHub.

## 2. Chức năng Chính

Hệ thống bao gồm các nhóm chức năng chính sau:

* **Quản lý Tài khoản và Thiết bị:** Cho phép quản lý thông tin các tài khoản người dùng và các thiết bị liên kết.
* **Hệ thống Trả lời Tự động:**
    * Xử lý yêu cầu từ client (ví dụ: điện thoại) và tạo phản hồi dựa trên luật hoặc AI.
    * Quản lý luật đơn giản (Simple Rules) và các mẫu trả lời (Templates & Variations).
    * Tích hợp AI (ví dụ: Gemini) để phát hiện ý định người dùng và tạo phản hồi thông minh.
    * Hỗ trợ chiến lược hội thoại (Language Strategies) và chiến lược điều khiển (Control Strategies, MainLoop Strategies) để quản lý luồng tương tác.
* **Quản lý Tác vụ Nền:** Lên lịch và thực thi các tác vụ nền như phân tích và đề xuất AI, duyệt đề xuất tự động, chạy mô phỏng hội thoại.
* **Mapping Ứng dụng (App Mapping):**
    * Trực quan hóa cấu trúc màn hình và luồng chuyển tiếp của các ứng dụng di động.
    * Quản lý các Screen Node và Transition trong cơ sở dữ liệu đồ thị Neo4j.
    * Định nghĩa các Phần tử Nhận diện Chính (PIE - Primary Identifying Elements) cho các màn hình.
* **Tích hợp AI Nâng cao:**
    * AI Personas để tùy chỉnh hành vi của AI.
    * AI Playground để thử nghiệm tương tác trực tiếp với AI.
    * Mô phỏng hội thoại AI (AI Conversation Simulations) để kiểm thử và đánh giá các kịch bản.
* **Giao diện Admin:** Cung cấp các công cụ để quản lý tất cả các khía cạnh trên, bao gồm cả hệ thống tài liệu này.

## 3. Công nghệ Sử dụng

* **Backend:** Python, Flask
* **Cơ sở dữ liệu:**
    * PostgreSQL (cho dữ liệu có cấu trúc như rules, templates, accounts, logs, PIE definitions, etc.)
    * Neo4j (cho dữ liệu đồ thị như app mapping, screen nodes, transitions)
* **AI:** Google Gemini (và các mô hình khác nếu có)
* **Frontend (Admin):** HTML, CSS, JavaScript (có thể sử dụng Bootstrap và các thư viện JS khác như Cytoscape.js cho mapping)
* **Quản lý Tác vụ Nền:** APScheduler
* **Hiển thị Tài liệu:** Thư viện Markdown, Pygments (cho syntax highlighting)

docs/01_ARCHITECTURE/SYSTEM_ARCHITECTURE.md
Markdown

# Kiến trúc Hệ thống

## 1. Tổng quan

Hệ thống HPT11 được xây dựng dựa trên kiến trúc microservices (hoặc monolithic với các module rõ ràng - ***cần làm rõ***), bao gồm các thành phần chính sau:

* **Ứng dụng Flask (Backend):**
    * Xử lý các yêu cầu API từ client (điện thoại, trang admin).
    * Tương tác với các cơ sở dữ liệu (PostgreSQL, Neo4j).
    * Tích hợp với các dịch vụ AI.
    * Quản lý và thực thi các tác vụ nền.
    * Cung cấp giao diện quản trị (Admin UI).
* **Cơ sở dữ liệu PostgreSQL:** Lưu trữ dữ liệu có cấu trúc của hệ thống như:
    * Thông tin người dùng, tài khoản, thiết bị.
    * Luật đơn giản, template trả lời, AI suggestions.
    * Lịch sử tương tác, log tác vụ.
    * Cấu hình AI Personas, API Keys.
    * Định nghĩa màn hình (PIE Definitions) và các điều kiện nhận dạng.
    * Chiến lược (Language, Control, MainLoop) và các giai đoạn (Stages), chuyển tiếp (Transitions) của chúng.
    * Cấu hình và trạng thái các tác vụ nền.
* **Cơ sở dữ liệu Neo4j:** Lưu trữ dữ liệu đồ thị cho chức năng App Mapping:
    * Các Screen Node (đại diện cho các màn hình ứng dụng).
    * Các Transition Edge (đại diện cho các hành động chuyển màn hình).
    * Thuộc tính của nodes và edges (ví dụ: app_name, activity_name, element_id, actionType).
* **AI Service (Module `ai_service.py`):**
    * Đóng gói logic tương tác với các mô hình ngôn ngữ lớn (LLMs) như Gemini.
    * Cung cấp các chức năng:
        * Phát hiện ý định người dùng.
        * Sinh nội dung trả lời.
        * Đề xuất luật mới.
        * Phân loại phần tử UI.
    * Quản lý AI Personas và Prompt Templates.
* **Scheduler (APScheduler):**
    * Quản lý và thực thi các tác vụ nền theo lịch trình (ví dụ: `analyze_interactions_and_suggest`, `approve_all_suggestions_task`, `run_ai_conversation_simulation`).
    * Sử dụng SQLAlchemyJobStore để lưu trữ thông tin job trong PostgreSQL.
* **Client (Ứng dụng Điện thoại):**
    * Gửi yêu cầu và nhận phản hồi từ backend.
    * Thực thi các hành động điều khiển dựa trên gói chiến lược (strategy package) nhận được từ backend (đối với Control/MainLoop Strategies).
    * Upload ảnh chụp màn hình và dữ liệu UI.
* **Giao diện Admin (Flask Admin):**
    * Cung cấp các trang quản lý cho Rules, Templates, Accounts, Devices, Strategies, AI Personas, API Keys, Scheduled Jobs, AI Simulations, App Mapping, PIE Definitions, và hệ thống tài liệu này.

## 2. Sơ đồ Kiến trúc (Đề xuất)

(***Nhúng sơ đồ kiến trúc ở đây nếu có, ví dụ sử dụng Mermaid hoặc ảnh. Ví dụ:***)

```mermaid
graph TD
    A[Client (Mobile App)] -->|HTTP API Request| B(Flask Backend App);
    B -->|SQL Queries| C(PostgreSQL Database);
    B -->|Cypher Queries| D(Neo4j Database);
    B -->|API Calls| E(AI Service / LLM);
    B -->|Job Scheduling| F(APScheduler);
    F -->|Job Store| C;
    G[Admin UI (Flask)] -->|HTTP API Request| B;

    subgraph "Flask Backend App (app/)"
        H(Routes: main, admin, phone)
        I(Controllers/Logic)
        J(Database Modules: database.py, graph_db.py)
        K(AI Service Module: ai_service.py)
        L(Background Tasks)
    end
3. Các Module Chính trong Code (app/)
__init__.py: Khởi tạo ứng dụng Flask, đăng ký blueprints, cấu hình.
routes.py: Chứa các API endpoint chính cho client (ví dụ: /receive_content_for_reply).
admin_routes.py: Chứa các route cho giao diện admin, bao gồm cả trang tài liệu này.
phone/ (package):
phone/routes.py: Các API endpoint dành riêng cho tương tác với thiết bị điện thoại (ví dụ: đăng ký thiết bị, nhận gói chiến lược, upload trạng thái UI).
phone/controller.py: Logic xử lý các yêu cầu từ điện thoại, biên dịch gói chiến lược.
phone/utils.py: Các hàm tiện ích cho package phone.
database.py: Module tương tác với PostgreSQL, chứa các hàm CRUD cho các bảng dữ liệu.
graph_db.py: Module tương tác với Neo4j, chứa các hàm truy vấn Cypher.
ai_service.py: Module xử lý logic liên quan đến AI, bao gồm gọi LLM, quản lý persona, prompt.
background_tasks.py: Định nghĩa các hàm chạy nền được quản lý bởi APScheduler.
scheduler_runner.py: Khởi tạo và chạy APScheduler.
config.py: Chứa các lớp cấu hình cho ứng dụng (biến môi trường, API keys, etc.).
encryption.py: Module xử lý mã hóa (ví dụ: cho API keys).
nlp_utils.py: (Nếu có) Các tiện ích xử lý ngôn ngữ tự nhiên.
<!
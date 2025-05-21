# Quy trình Tương tác từ Điện thoại (Phone Interaction Workflow)

Quy trình này mô tả chi tiết các bước xử lý khi hệ thống HPT11 nhận được một yêu cầu tương tác từ client di động, thường là nội dung tin nhắn do người dùng cuối gửi, và cần đưa ra một phản hồi.

## 1. Tổng quan

Mục tiêu của workflow này là tiếp nhận thông tin từ client, phân tích ngữ cảnh và nội dung, sau đó quyết định và tạo ra một phản hồi phù hợp, có thể dựa trên luật định sẵn, template, hoặc do AI tạo ra.

**Điểm kích hoạt:** Client di động gửi một HTTP POST request đến endpoint `/receive_content_for_reply`.

**Các thành phần chính liên quan:**

* `app/routes.py` (cụ thể là hàm `handle_receive_content`)
* `app/database.py` (các hàm truy vấn và ghi CSDL PostgreSQL)
* `app/ai_service.py` (các hàm liên quan đến AI như phát hiện intent, tạo phản hồi)
* CSDL PostgreSQL: Các bảng `accounts`, `interaction_history`, `strategies`, `stages`, `stage_transitions`, `response_templates`, `template_variations`, `ai_personas`.
* File cấu hình `config.py` (để lấy các giá trị mặc định như `DEFAULT_REPLY_PERSONA_ID`).

## 2. Các Bước Xử lý Chi tiết

Sơ đồ luồng xử lý có thể được minh họa như sau:

```mermaid
graph TD
    A[Client Di động Gửi Request POST /receive_content_for_reply] --> B{Server Nhận Dữ liệu};
    B -- Dữ liệu JSON (account_id, received_text, app, thread_id) --> C[Xác thực & Validate Input];
    C -- OK --> D[Lấy Thông tin Ngữ cảnh];
    D -- account_id --> E[DB: Lấy Account Details (default_persona_id, default_strategy_id, goal, notes)];
    D -- thread_id --> F[DB: Lấy Last Stage từ interaction_history];
    F --> G[Xác định Current Stage ID];
    E --> G;
    G -- current_stage_id, persona_id (từ E hoặc config) --> H[AI Service: Phát hiện User Intent];
    H -- user_intent --> I[DB: Ghi Log Ban đầu (log_interaction_received)];
    I -- history_id, current_stage_id, user_intent --> J[DB: Tìm Transition Khớp];
    J -- Tìm thấy Transition & Có Template Ref --> K[DB: Lấy Template Variations];
    K -- Có Variations --> L[Chọn Ngẫu nhiên 1 Variation làm Reply Text];
    L --> M[Status: success_strategy_template];
    J -- Không tìm thấy Transition / Không có Template Ref / K lỗi --> N[Gọi AI Service Tạo Phản hồi];
    N -- prompt_data (bao gồm history, account_info, stage, intent, text), persona_id --> O[AI Service: generate_reply_with_ai];
    O -- AI trả lời thành công --> P[Lấy Reply Text từ AI];
    P --> Q[Status: success_ai / success_fallback_template];
    O -- AI lỗi / không trả lời --> R[Reply Text rỗng];
    R --> S[Status: error_ai_*];
    M --> T[Xác định Next Stage ID (từ Transition hoặc giữ nguyên)];
    Q --> T;
    S --> T;
    T -- reply_text, status, next_stage_id --> U[DB: Cập nhật Log Cuối cùng (update_interaction_log)];
    U --> V[Chuẩn bị JSON Response];
    V -- reply_text, status, next_action (nếu có) --> W[Trả Response về Client Di động];
    C -- Lỗi Validate --> X[Status: error_missing_data/error_no_json_data, Reply rỗng];
    X --> U;
# app/admin_routes.py
import os
import traceback
from typing import Counter
from flask import Blueprint, Flask, config, render_template, request, redirect, url_for, flash,current_app ,jsonify
from datetime import datetime, timedelta, timezone 
import psycopg2
import math
import json
import uuid 
import importlib # Để kiểm tra function path (tùy chọn)
import pytz
from . import graph_db 
from flask import flash
from collections import Counter
from app import graph_db # Module tương tác Neo4j
from app import ai_service
from PIL import Image
from flask import send_from_directory, current_app 
#from app.auth import admin_required 
from flask import jsonify
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, current_app
)
from .graph_db import convert_unknown_to_defined_node_wrapper
from .database import get_pie_conditions_from_db,update_pie_conditions_in_db ,create_new_pie_definition_from_node
from math import ceil # <<< Thêm import ceil
from app.database import get_device_details, get_accounts_linked_to_device, get_all_accounts_for_select, link_device_account
PER_PAGE_RULES = 30
PER_PAGE_TEMPLATES = 30
PER_PAGE_ACCOUNTS = 30
PER_PAGE_PERSONAS = 30
PER_PAGE_PROMPT_TEMPLATES = 30
PER_PAGE_SAVED_SIM_CONFIGS = 30
PER_PAGE_MACROS = 30
PER_PAGE = 30
PER_PAGE_ASSIGNMENTS = 30
PER_PAGE_DEVICES = 30
PER_PAGE_LOGS = 50

try:
    from app.scheduler_runner import live_scheduler
except ImportError:
    print("CRITICAL WARNING (admin_routes): Could not import live_scheduler from app.scheduler_runner! Live control will fail.")
    live_scheduler = None
try:
    from . import ai_service
except ImportError:
    import ai_service
    print("WARNING (admin_routes): Using fallback ai_service import.")
# Import db và scheduler (đã chuyển sang SQLAlchemyJobStore và import trực tiếp)
try:
    from . import database as db
except ImportError:
    import database as db
    print("WARNING (admin_routes): Using fallback database import.")

try: from .background_tasks import approve_all_suggestions_task
except ImportError: approve_all_suggestions_task = None
# Import hàm tác vụ nền
try:
    from .background_tasks import run_ai_conversation_simulation # <<< Import hàm mô phỏng
except ImportError:
     print("CRITICAL WARNING (admin_routes): Could not import background tasks!")
     run_ai_conversation_simulation = None # Đặt là None nếu import lỗi
# --- Định nghĩa các loại trigger hợp lệ ---
try:
    from .phone import controller as phone_controller
except ImportError:
    # Fallback nếu cấu trúc hơi khác hoặc để test độc lập
    try:
        import phone.controller as phone_controller
        print("WARN (admin_routes): Using fallback import for phone.controller")
    except ImportError:
        print("CRITICAL ERROR (admin_routes): Cannot import phone controller!")
        phone_controller = None
TRIGGER_TYPES = ['interval', 'cron', 'date']
# === ĐỊNH NGHĨA CÁC TÁC VỤ NỀN CÓ THỂ LÊN LỊCH TỪ UI ===
# Key: Tên hiển thị trên UI
# Value: Đường dẫn Python đầy đủ đến hàm thực thi
AVAILABLE_SCHEDULED_TASKS = {
    'Phân tích & Đề xuất AI': 'app.background_tasks.analyze_interactions_and_suggest',
    'Tự động Duyệt Tất Cả Đề Xuất': 'app.background_tasks.approve_all_suggestions_task',
    'Chạy Mô phỏng Hội thoại AI': 'app.background_tasks.run_ai_conversation_simulation', # <<< Thêm hàm này
    # Thêm các tác vụ khác nếu có...
}
AVAILABLE_SCHEDULED_TASKS_LIST = sorted(AVAILABLE_SCHEDULED_TASKS.items())
SIMULATION_FUNCTION_PATH = 'app.background_tasks.run_ai_conversation_simulation'
VALID_CONDITION_TYPES = [
    '', # Lựa chọn mặc định: Luôn chạy (Không có điều kiện)
    'current_stage_equals', # Điều kiện: Stage hiện tại bằng giá trị
    'element_exists_text', # Điều kiện: Element có text này tồn tại
    'element_exists_id', # Điều kiện: Element có ID này tồn tại
    # Thêm các loại điều kiện khác bạn muốn hỗ trợ ở đây
    # Ví dụ: 'variable_equals', 'element_not_exists_text', ...
]
admin_bp = Blueprint(
    'admin',
    __name__,
    template_folder='../templates',
    url_prefix='/admin'
)
VALID_INTENTS_FOR_TRANSITION = [
    'greeting', 'price_query', 'shipping_query', 'product_info_query',
    'compliment', 'complaint', 'connection_request', 'spam',
    'positive_generic', 'negative_generic', 'other', 'any' # Thêm 'any'
]
 # Đặt số lượng item mỗi trang ở đây
VALID_CONDITION_TYPES = ['', 'current_stage_equals', 'element_exists_text', 'element_exists_id']
# --- Danh sách status có thể lọc (Tùy chọn) ---
# Lấy từ các status bạn dùng trong routes.py và ai_service.py
POSSIBLE_HISTORY_STATUS = [
    'received', 'success_strategy_template', 'success_ai', 'success_fallback_template',
    'error_no_json_data', 'error_missing_data', 'error_no_variation',
    'error_ai_no_key_or_config_failed', 'error_ai_blocked', 'error_ai_empty_response',
    'error_ai_no_text_content', 'error_ai_bad_response_structure',
    'error_ai_unhelpful_no_fallback', 'error_ai_call', 'error_server_unexpected'
    # Thêm các status khác nếu có
]
PROMPT_TASK_TYPES = ['generate_reply', 'suggest_rule', 'detect_intent', 'other'] # Có thể mở rộng sau
VALID_STRATEGY_TYPES = ['language', 'control']
# === Dashboard ===
@admin_bp.route('/')
def index():
    stats_data = None # Khởi tạo là None
    try:
        stats_data = db.get_dashboard_stats()
    except Exception as e:
        print(f"Lỗi khi lấy dashboard stats trong route: {e}")
        flash("Không thể tải dữ liệu thống kê cho dashboard.", "error")

    # Nếu stats_data là None (do lỗi DB), truyền vào dict rỗng để template không bị lỗi
    return render_template('admin_index_content.html',
                           title="Admin Dashboard",
                           stats=stats_data if stats_data is not None else {})

def _get_configured_timezone():
    try:
         # Cố gắng lấy từ config nếu có, nếu không dùng default
         # tz_str = current_app.config.get('SCHEDULER_TIMEZONE', 'Asia/Ho_Chi_Minh')
         tz_str = 'Asia/Ho_Chi_Minh' # Hoặc dùng giá trị mặc định trực tiếp
         return pytz.timezone(tz_str)
    except Exception:
         print("WARN: Could not get configured timezone, falling back to UTC.")
         return pytz.utc
# === Quản lý Luật (Đã có từ trước - Bổ sung endpoint cho edit) ===


@admin_bp.route('/rules')
def view_rules():
    title = "Quản lý Luật (Simple Rules)"
    rules = []
    duplicate_keyword_rule_ids = set()
    distinct_categories = []
    distinct_template_refs = []
    active_filters = {}
    pagination = None # <<< Biến lưu thông tin phân trang

    if not db:
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
    else:
        try:
            # Lấy page từ URL, mặc định là 1
            page = request.args.get('page', 1, type=int)
            if page < 1: page = 1

            # Lấy các tham số filter (như cũ)
            filter_keywords = request.args.get('filter_keywords', '').strip()
            filter_category = request.args.get('filter_category', '').strip()
            filter_template_ref = request.args.get('filter_template_ref', '').strip()
            active_filters = {k.replace('filter_', ''): v for k, v in request.args.items() if v and k.startswith('filter_')}
            print(f"DEBUG (view_rules): Page={page}, Active Filters = {active_filters}")

            # Gọi hàm lấy luật đã lọc VÀ tổng số mục
            rules, total_items = db.get_filtered_rules(
                filters=active_filters,
                page=page,
                per_page=PER_PAGE_RULES
            ) # <<< Gọi hàm đã sửa

            if rules is None or total_items is None:
                 flash("Lỗi khi tải danh sách luật từ CSDL.", "error"); rules = []; total_items = 0

            print(f"DEBUG (view_rules): Fetched {len(rules)} rules for page {page}. Total matching: {total_items}")

            # --- Tính toán thông tin phân trang ---
            if total_items > 0:
                 total_pages = ceil(total_items / PER_PAGE_RULES)
                 if page > total_pages: page = total_pages # Tránh page ảo
                 pagination = {
                    'page': page, 'per_page': PER_PAGE_RULES, 'total_items': total_items,
                    'total_pages': total_pages, 'has_prev': page > 1, 'has_next': page < total_pages,
                    'prev_num': page - 1 if page > 1 else None,
                    'next_num': page + 1 if page < total_pages else None
                 }
            else: # Nếu không có mục nào
                 pagination = {'page': 1, 'per_page': PER_PAGE_RULES, 'total_items': 0, 'total_pages': 0, 'has_prev': False, 'has_next': False}

            # Lấy danh sách cho dropdown filter (như cũ)
            distinct_categories = db.get_distinct_rule_categories() or []
            distinct_template_refs = db.get_distinct_rule_template_refs() or []

            # --- Logic tìm keywords trùng lặp (chỉ chạy trên rules của trang hiện tại) ---
            if rules:
                # ... (Code tìm duplicate_keyword_rule_ids như cũ) ...
                keyword_counts = Counter()
                for rule in rules:
                    normalized_keywords=tuple(sorted([k.strip().lower() for k in rule.get('trigger_keywords','').split(',') if k.strip()]))
                    if normalized_keywords: keyword_counts[normalized_keywords] += 1
                duplicate_keywords = {kw for kw, count in keyword_counts.items() if count > 1}
                for rule in rules:
                    normalized_keywords=tuple(sorted([k.strip().lower() for k in rule.get('trigger_keywords','').split(',') if k.strip()]))
                    if normalized_keywords in duplicate_keywords: duplicate_keyword_rule_ids.add(rule.get('rule_id'))


        except Exception as e:
            print(f"Lỗi nghiêm trọng khi load rules: {e}")
            flash("Đã xảy ra lỗi không mong muốn khi tải danh sách luật.", "error")
            rules = []; duplicate_keyword_rule_ids = set(); distinct_categories = []; distinct_template_refs = []; pagination = None

    # Truyền tất cả dữ liệu cần thiết vào template
    return render_template('admin_rules.html',
                           title=title,
                           rules=rules, # <<< Chỉ chứa dữ liệu trang hiện tại
                           duplicate_rule_ids=duplicate_keyword_rule_ids,
                           distinct_categories=distinct_categories,
                           distinct_template_refs=distinct_template_refs,
                           filters=active_filters,
                           pagination=pagination) # <<< Truyền pagination

# Sửa lỗi thiếu endpoint='add_rule_form' trong route GET
@admin_bp.route('/rules/add', methods=['GET', 'POST'])
def add_rule(): # Đổi tên hàm thành add_rule thay vì add_rule_form cho nhất quán
    if request.method == 'POST':
        try:
            # --- Lấy dữ liệu từ form ---
            keywords = request.form.get('keywords')
            category = request.form.get('category') # Có thể None nếu không nhập
            template_ref = request.form.get('template_ref')
            priority_str = request.form.get('priority', '0') # Lấy dạng string, mặc định '0'
            notes = request.form.get('notes') # Có thể None

            # --- Validate dữ liệu ---
            if not keywords or not template_ref:
                 flash("Keywords và Template Ref là bắt buộc.", "warning")
                 # Trả về lại form với dữ liệu cũ (nếu cần) hoặc chỉ báo lỗi
                 # Cần lấy lại danh sách template cho form GET
                 templates = db.get_all_template_refs() or []
                 return render_template('admin_add_rule.html', title="Thêm Luật Mới", templates=templates, current_data=request.form), 400 # Bad request

            try:
                 priority = int(priority_str) # Chuyển đổi priority
            except ValueError:
                 flash("Priority phải là một số nguyên.", "warning")
                 templates = db.get_all_template_refs() or []
                 return render_template('admin_add_rule.html', title="Thêm Luật Mới", templates=templates, current_data=request.form), 400

            # --- Gọi hàm DB ---
            # Giả sử hàm add_new_rule trả về True/False
            success = db.add_new_rule(
                keywords=keywords,
                category=category,
                template_ref=template_ref,
                priority=priority,
                notes=notes
            )

            # --- Phản hồi ---
            if success:
                flash('Thêm luật thành công!', 'success')
                return redirect(url_for('admin.view_rules'))
            else:
                flash('Thêm luật thất bại! (Lỗi CSDL hoặc dữ liệu không hợp lệ)', 'error')
                # Ở lại trang add, cần lấy lại template list
                templates = db.get_all_template_refs() or []
                return render_template('admin_add_rule.html', title="Thêm Luật Mới", templates=templates, current_data=request.form)
        except psycopg2.IntegrityError as e:
            # Bắt lỗi nếu vi phạm ràng buộc UNIQUE mới thêm
            db.get_db_connection().rollback() # Rollback transaction
            print(f"IntegrityError while adding rule: {e}")
            flash("Thêm luật thất bại! Có vẻ luật với Keywords, Category, và Template Ref này đã tồn tại.", "error")
        except Exception as e:
            print(f"Lỗi nghiêm trọng khi thêm luật: {e}")
            flash(f"Đã xảy ra lỗi không mong muốn khi thêm luật: {e}", "error")
            # Ở lại trang add, cần lấy lại template list
            templates = db.get_all_template_refs() or []
            return render_template('admin_add_rule.html', title="Thêm Luật Mới", templates=templates, current_data=request.form)

    # GET request
    try:
        # Giả sử hàm này lấy list các dict [{'template_ref': 'ref1'}, ...]
        templates = db.get_all_template_refs() or []
        if templates is None:
             flash("Không thể tải danh sách template từ CSDL.", "error")
             templates = []
    except Exception as e:
        print(f"Lỗi nghiêm trọng load templates cho add rule: {e}")
        flash("Lỗi không mong muốn khi tải danh sách template.", "error")
        templates = []

    # Truyền templates vào template admin_add_rule.html
    return render_template('admin_add_rule.html', title="Thêm Luật Mới", templates=templates)


@admin_bp.route('/rules/<int:rule_id>/edit', methods=['GET', 'POST'])
def edit_rule(rule_id):
    if request.method == 'POST':
        try:
            # Lấy dữ liệu từ form
            keywords = request.form.get('keywords')
            category = request.form.get('category')
            template_ref = request.form.get('template_ref')
            priority_str = request.form.get('priority', '0')
            notes = request.form.get('notes')

            # Validate
            if not keywords: # Chỉ cần keywords là đủ ở đây, template có thể để trống
                 flash("Keywords là bắt buộc.", "warning")
                 # Cần lấy lại rule và templates để render lại form
                 rule = db.get_rule_by_id(rule_id)
                 templates = db.get_all_template_refs() or []
                 if not rule: return redirect(url_for('admin.view_rules')) # Không tìm thấy rule để sửa
                 return render_template('admin_edit_rule.html', title="Sửa Luật", rule=rule, templates=templates), 400

            try:
                 priority = int(priority_str)
            except ValueError:
                 flash("Priority phải là một số nguyên.", "warning")
                 rule = db.get_rule_by_id(rule_id)
                 templates = db.get_all_template_refs() or []
                 if not rule: return redirect(url_for('admin.view_rules'))
                 return render_template('admin_edit_rule.html', title="Sửa Luật", rule=rule, templates=templates), 400

            # Gọi hàm DB để cập nhật (giả sử có hàm update_rule)
            success = db.update_rule(
                rule_id=rule_id,
                keywords=keywords,
                category=category,
                template_ref=template_ref if template_ref else None, # Cho phép bỏ trống template
                priority=priority,
                notes=notes
            )

            if success:
                flash('Cập nhật luật thành công!', 'success')
                return redirect(url_for('admin.view_rules'))
            else:
                flash('Cập nhật luật thất bại!', 'error')
                # Ở lại trang edit, cần lấy lại rule và templates
                rule = db.get_rule_by_id(rule_id) # Lấy lại dữ liệu mới nhất (hoặc giữ nguyên form)
                templates = db.get_all_template_refs() or []
                if not rule: return redirect(url_for('admin.view_rules'))
                return render_template('admin_edit_rule.html', title="Sửa Luật", rule=rule, templates=templates)

        except Exception as e:
            print(f"Lỗi nghiêm trọng khi cập nhật luật: {e}")
            flash(f"Đã xảy ra lỗi không mong muốn khi cập nhật luật: {e}", "error")
            # Ở lại trang edit, lấy lại dữ liệu
            rule = db.get_rule_by_id(rule_id)
            templates = db.get_all_template_refs() or []
            if not rule: return redirect(url_for('admin.view_rules'))
            return render_template('admin_edit_rule.html', title="Sửa Luật", rule=rule, templates=templates)

    # GET request
    try:
        rule = db.get_rule_by_id(rule_id) # Giả sử hàm này lấy dict thông tin rule
        templates = db.get_all_template_refs() # Giả sử hàm này lấy list template ref
        if templates is None: templates = []
        if rule is None:
             flash(f"Không tìm thấy luật có ID {rule_id}.", "error")
             return redirect(url_for('admin.view_rules'))
    except psycopg2.IntegrityError as e:
         db.get_db_connection().rollback() # Rollback transaction
         print(f"IntegrityError while updating rule {rule_id}: {e}")
         flash("Cập nhật luật thất bại! Có vẻ bạn đang tạo ra một luật trùng lặp với luật khác (Keywords, Category, Template Ref).", "error")
    except Exception as e:
        print(f"Lỗi nghiêm trọng khi tải dữ liệu sửa luật: {e}")
        flash("Không thể tải dữ liệu để sửa luật.", "error")
        return redirect(url_for('admin.view_rules'))
    rule = db.get_rule_by_id(rule_id)
    templates = db.get_all_template_refs() or []
    if not rule: return redirect(url_for('admin.view_rules'))
    return render_template('admin_edit_rule.html', title="Sửa Luật", rule=rule, templates=templates)


@admin_bp.route('/rules/<int:rule_id>/delete', methods=['POST'])
def delete_rule(rule_id):
    try:
        # Giả sử có hàm db.delete_rule(rule_id) trả về True/False
        success = db.delete_rule(rule_id)
        if success:
            flash(f"Đã xóa luật #{rule_id}.", 'success')
        else:
            flash(f"Xóa luật #{rule_id} thất bại (có thể do ID không tồn tại hoặc lỗi CSDL).", 'error')
    except Exception as e:
        print(f"Lỗi nghiêm trọng khi xóa luật: {e}")
        flash(f"Đã xảy ra lỗi không mong muốn khi xóa luật: {e}", "error")
    # Luôn redirect về trang danh sách luật sau khi xử lý
    return redirect(url_for('admin.view_rules'))


# === Đề xuất AI ===
@admin_bp.route('/suggestions')
def view_suggestions():
    title = "Đề xuất từ AI"
    suggestions = []
    suggestion_job_status = {'status': 'Unknown', 'next_run_time_str': 'N/A'} # <<< Khởi tạo dict trạng thái

    if not db:
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
    else:
        try:
            # Lấy danh sách suggestions đang chờ (như cũ)
            suggestions = db.get_pending_suggestions()
            if suggestions is None:
                 flash("Không thể tải đề xuất từ CSDL.", "error")
                 suggestions = []

            # --- <<< THÊM LOGIC LẤY TRẠNG THÁI LIVE CỦA suggestion_job >>> ---
            try:
                live_run_times = _get_live_next_run_times() or {}
                job_id_to_check = 'suggestion_job'
                server_tz = _get_configured_timezone()

                if job_id_to_check in live_run_times:
                    next_run_timestamp = live_run_times[job_id_to_check]
                    if next_run_timestamp is not None:
                        try:
                            utc_dt = datetime.fromtimestamp(next_run_timestamp, tz=timezone.utc)
                            local_dt = utc_dt.astimezone(server_tz)
                            suggestion_job_status['next_run_time_str'] = local_dt.strftime('%Y-%m-%d %H:%M:%S %z')
                            suggestion_job_status['status'] = 'Scheduled'
                        except Exception as fmt_err:
                            print(f"Error formatting suggestion_job time: {fmt_err}")
                            suggestion_job_status['next_run_time_str'] = 'Lỗi Format'
                            suggestion_job_status['status'] = 'Error Formatting'
                    else:
                        # Timestamp là None -> Job đang Paused
                        suggestion_job_status['next_run_time_str'] = '---'
                        suggestion_job_status['status'] = 'Paused'
                else:
                    # Không tìm thấy job_id trong apscheduler_jobs
                    # Kiểm tra xem nó có đang được enable trong config không
                    job_config = db.get_job_config_details(job_id_to_check)
                    if job_config and job_config.get('is_enabled'):
                         suggestion_job_status['status'] = 'Error/Not Found in Scheduler' # Lẽ ra phải có nếu enabled
                    else:
                         suggestion_job_status['status'] = 'Disabled' # Bị tắt trong config

            except Exception as live_err:
                print(f"Error getting live status for suggestion_job: {live_err}")
                suggestion_job_status['status'] = 'Error Fetching Status'
            # --- <<< KẾT THÚC LOGIC LẤY TRẠNG THÁI LIVE >>> ---

        except Exception as e:
            print(f"Lỗi nghiêm trọng load suggestions page data: {e}")
            suggestions = []
            flash("Lỗi không mong muốn khi tải dữ liệu.", "error")

    # Truyền thêm suggestion_job_status vào template
    return render_template('admin_suggestions.html',
                           title=title,
                           suggestions=suggestions,
                           suggestion_job_status=suggestion_job_status)

@admin_bp.route('/suggestions/<int:suggestion_id>/edit', methods=['GET', 'POST'])
def edit_suggestion(suggestion_id):
    """ Hiển thị form để sửa và phê duyệt suggestion từ AI """
    if not db: # Kiểm tra db
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
        return redirect(url_for('admin.view_suggestions'))

    # Lấy thông tin suggestion gốc cho cả GET và POST (nếu lỗi validation)
    suggestion = db.get_suggestion_by_id(suggestion_id)
    if not suggestion:
        flash(f"Không tìm thấy đề xuất ID {suggestion_id}.", "error")
        return redirect(url_for('admin.view_suggestions'))
    if suggestion.get('status') != 'pending':
        flash(f"Đề xuất ID {suggestion_id} không ở trạng thái 'pending'.", "warning")
        return redirect(url_for('admin.view_suggestions'))

    if request.method == 'POST':
        # Lấy dữ liệu đã chỉnh sửa từ form
        keywords = request.form.get('keywords', '').strip()
        category = request.form.get('category', '').strip()
        template_ref = request.form.get('template_ref', '').strip()
        template_text = request.form.get('template_text', '').strip()
        priority = request.form.get('priority', type=int, default=0)
        notes = f"Approved from AI suggestion #{suggestion_id}. Original keywords: {suggestion.get('suggested_keywords', '')}" # Giữ note gốc

        # Validate dữ liệu nhập (quan trọng!)
        error = False
        if not keywords:
            flash("Keywords là bắt buộc.", "warning"); error = True
        if not template_ref:
            flash("Template Ref là bắt buộc.", "warning"); error = True
        if not template_text:
             flash("Template Text (Variation) là bắt buộc.", "warning"); error = True

        if error:
             # Truyền lại dữ liệu vừa nhập vào form để người dùng sửa tiếp
             return render_template('admin_edit_suggestion.html',
                                    title=f"Sửa & Phê duyệt Đề xuất #{suggestion_id}",
                                    suggestion=suggestion, # Dùng suggestion gốc để hiển thị phần không sửa được
                                    current_data=request.form), 400 # current_data chứa giá trị vừa nhập

        # ----- Thực hiện logic phê duyệt với dữ liệu đã sửa -----
        approval_error = None
        try:
            # 1. Thêm Template và Variation mới (dùng dữ liệu đã sửa)
            # Hàm add_new_template sẽ tự xử lý ON CONFLICT nếu template_ref đã tồn tại
            # nhưng nên khuyến khích người dùng đặt ref mới nếu sửa đổi nhiều
            added_template_ref = db.add_new_template(
                template_ref=template_ref,
                first_variation_text=template_text,
                description=f"AI suggested, approved from #{suggestion_id}", # Hoặc để trống
                category=category if category else None
            )

            if added_template_ref:
                # 2. Thêm Rule mới (dùng dữ liệu đã sửa)
                rule_added = db.add_new_rule(
                    keywords=keywords,
                    category=category if category else None,
                    template_ref=added_template_ref, # Dùng ref trả về (có thể là cái cũ nếu đã tồn tại)
                    priority=priority,
                    notes=notes
                )

                if rule_added:
                    # 3. Cập nhật trạng thái suggestion thành 'approved'
                    status_updated = db.update_suggestion_status(suggestion_id, 'approved')
                    if status_updated:
                        flash(f"Đã phê duyệt thành công đề xuất #{suggestion_id} và tạo rule/template.", "success")
                    else:
                        # Vẫn thành công về mặt thêm rule/template nhưng lỗi cập nhật status suggestion
                        flash(f"Đã tạo rule/template cho đề xuất #{suggestion_id}, nhưng không thể cập nhật trạng thái đề xuất.", "warning")
                    # Redirect về trang suggestions sau khi thành công
                    return redirect(url_for('admin.view_suggestions'))
                else:
                    # Lỗi khi thêm rule (sau khi đã thêm template/variation)
                    approval_error = "Đã thêm template/variation nhưng thêm rule thất bại."
            else:
                # Lỗi ngay từ bước thêm template/variation
                approval_error = "Thêm template/variation mới thất bại (Template Ref có thể bị lỗi?)."

        except Exception as e:
            approval_error = f"Lỗi không mong muốn trong quá trình phê duyệt: {e}"
            print(f"Lỗi nghiêm trọng khi phê duyệt suggestion {suggestion_id}: {e}")
            print(traceback.format_exc())

        # Nếu có lỗi trong quá trình phê duyệt
        if approval_error:
            flash(f"Phê duyệt thất bại: {approval_error}", "error")
            # Hiển thị lại form với dữ liệu người dùng vừa nhập
            return render_template('admin_edit_suggestion.html',
                                   title=f"Sửa & Phê duyệt Đề xuất #{suggestion_id}",
                                   suggestion=suggestion,
                                   current_data=request.form)

    # --- Xử lý GET Request ---
    # Truyền suggestion gốc vào template để hiển thị giá trị AI đề xuất ban đầu
    return render_template('admin_edit_suggestion.html',
                           title=f"Sửa & Phê duyệt Đề xuất #{suggestion_id}",
                           suggestion=suggestion)

@admin_bp.route('/suggestions/<int:suggestion_id>/approve', methods=['POST'])
def approve_suggestion(suggestion_id):
    try:
        suggestion = db.get_suggestion_by_id(suggestion_id)
        if not suggestion or suggestion.get('status') != 'pending':
            flash("Đề xuất không hợp lệ hoặc đã được xử lý.", "warning")
            return redirect(url_for('admin.view_suggestions'))

        # Lấy dữ liệu từ form phê duyệt
        template_ref = request.form.get('template_ref')
        category = request.form.get('category', 'ai_suggested') # Mặc định category
        priority_str = request.form.get('priority', '0')

        # Validate
        if not template_ref:
             flash("Cần cung cấp Template Ref khi phê duyệt.", "warning")
             # Cần render lại trang suggestions hoặc trang chi tiết suggestion nếu có
             return redirect(url_for('admin.view_suggestions')) # Redirect đơn giản

        try:
            priority = int(priority_str)
        except ValueError:
            flash("Priority phải là số nguyên.", "warning")
            return redirect(url_for('admin.view_suggestions'))

        # Bắt đầu transaction hoặc xử lý tuần tự
        # 1. Thêm template mới (nếu chưa có) VÀ variation đầu tiên
        # Giả sử add_new_template trả về template_ref nếu thành công, None nếu lỗi
        added_template_ref = db.add_new_template(
            template_ref=template_ref,
            first_variation_text=suggestion['suggested_template_text'],
            description=f"AI suggested template from suggestion {suggestion_id}",
            category=category # Sử dụng category từ form
        )

        if added_template_ref:
            # 2. Thêm rule mới trỏ đến template vừa tạo
            rule_added = db.add_new_rule(
                keywords=suggestion['suggested_keywords'],
                category=category, # Sử dụng category từ form
                template_ref=added_template_ref, # Dùng ref trả về từ hàm add_new_template
                priority=priority,
                notes=f"Approved from AI suggestion #{suggestion_id}. Original keywords: {suggestion['suggested_keywords']}"
            )

            if rule_added:
                # 3. Cập nhật trạng thái suggestion thành 'approved'
                status_updated = db.update_suggestion_status(suggestion_id, 'approved')
                if status_updated:
                    flash("Đã phê duyệt và thêm luật/template thành công!", "success")
                else:
                    # Vẫn thành công về mặt thêm luật/template nhưng lỗi cập nhật status suggestion
                    flash("Đã thêm luật/template, nhưng không thể cập nhật trạng thái đề xuất.", "warning")
                return redirect(url_for('admin.view_suggestions'))
            else:
                # Lỗi khi thêm rule (sau khi đã thêm template/variation)
                # Cần xử lý rollback hoặc báo lỗi rõ ràng
                flash("Đã thêm template/variation nhưng thêm rule thất bại.", "error")
                # Cân nhắc xóa template/variation vừa thêm nếu logic yêu cầu
        else:
            # Lỗi ngay từ bước thêm template/variation
            flash("Thêm template/variation mới thất bại.", "error")

    except Exception as e:
        print(f"Lỗi nghiêm trọng khi phê duyệt: {e}")
        flash(f"Đã xảy ra lỗi không mong muốn khi phê duyệt: {e}", "error")

    # Nếu có lỗi xảy ra, quay lại trang suggestions
    return redirect(url_for('admin.view_suggestions'))


@admin_bp.route('/suggestions/<int:suggestion_id>/reject', methods=['POST'])
def reject_suggestion(suggestion_id):
    try:
        # Giả sử hàm update_suggestion_status trả về True/False
        success = db.update_suggestion_status(suggestion_id, 'rejected')
        if success:
            flash(f"Đã từ chối đề xuất #{suggestion_id}.", 'info')
        else:
            flash("Từ chối đề xuất thất bại (ID không tồn tại hoặc lỗi CSDL).", 'error')
    except Exception as e:
        print(f"Lỗi nghiêm trọng khi từ chối đề xuất: {e}")
        flash(f"Đã xảy ra lỗi không mong muốn khi từ chối: {e}", "error")
    return redirect(url_for('admin.view_suggestions'))

@admin_bp.route('/suggestions/<int:suggestion_id>/approve-direct', methods=['POST'])
def approve_suggestion_direct(suggestion_id):
    """Xử lý phê duyệt trực tiếp suggestion mà không cần sửa đổi."""
    if not db:
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
        return redirect(url_for('admin.view_suggestions'))

    # 1. Lấy thông tin suggestion gốc từ DB
    suggestion = db.get_suggestion_by_id(suggestion_id)
    if not suggestion:
        flash(f"Không tìm thấy đề xuất ID {suggestion_id}.", "error")
        return redirect(url_for('admin.view_suggestions'))
    if suggestion.get('status') != 'pending':
        flash(f"Đề xuất ID {suggestion_id} không ở trạng thái 'pending'.", "warning")
        return redirect(url_for('admin.view_suggestions'))

    # 2. Lấy các giá trị AI đã đề xuất (KHÔNG lấy từ form)
    keywords = suggestion.get('suggested_keywords')
    category = suggestion.get('suggested_category') # Lấy category AI đề xuất
    template_ref = suggestion.get('suggested_template_ref') # Lấy ref AI đề xuất
    template_text = suggestion.get('suggested_template_text')
    priority = 0 # Hoặc bạn có thể đặt một priority mặc định khác
    notes = f"Approved directly from AI suggestion #{suggestion_id}."

    # Validate dữ liệu đề xuất tối thiểu
    if not keywords or not template_ref or not template_text:
        flash(f"Đề xuất ID {suggestion_id} thiếu thông tin Keywords, Template Ref hoặc Template Text. Không thể phê duyệt trực tiếp.", "error")
        # Có thể nên chuyển suggestion này sang status 'error' hoặc 'needs_edit'
        # db.update_suggestion_status(suggestion_id, 'error_missing_data')
        return redirect(url_for('admin.view_suggestions'))

    # ----- Thực hiện logic phê duyệt -----
    approval_error = None
    try:
        # 1. Thêm Template và Variation mới
        added_template_ref = db.add_new_template(
            template_ref=template_ref,
            first_variation_text=template_text,
            description=f"AI suggested, direct approval #{suggestion_id}", # Mô tả tự động
            category=category if category else None # Dùng category AI đề xuất
        )

        if added_template_ref:
            # 2. Thêm Rule mới
            rule_added = db.add_new_rule(
                keywords=keywords,
                category=category if category else None,
                template_ref=added_template_ref, # Dùng ref có thể đã tồn tại hoặc mới tạo
                priority=priority,
                notes=notes
            )

            if rule_added:
                # 3. Cập nhật trạng thái suggestion thành 'approved'
                status_updated = db.update_suggestion_status(suggestion_id, 'approved')
                if status_updated:
                    flash(f"Đã phê duyệt trực tiếp đề xuất #{suggestion_id} và tạo rule/template.", "success")
                else:
                    flash(f"Đã tạo rule/template cho đề xuất #{suggestion_id}, nhưng lỗi cập nhật trạng thái đề xuất.", "warning")
                return redirect(url_for('admin.view_suggestions'))
            else:
                approval_error = "Đã thêm template/variation nhưng thêm rule thất bại."
        else:
            approval_error = "Thêm template/variation mới thất bại (Template Ref có thể bị lỗi?)."

    except Exception as e:
        approval_error = f"Lỗi không mong muốn khi phê duyệt trực tiếp: {e}"
        print(f"Lỗi nghiêm trọng khi phê duyệt trực tiếp suggestion {suggestion_id}: {e}")
        print(traceback.format_exc())

    # Nếu có lỗi trong quá trình phê duyệt
    if approval_error:
        flash(f"Phê duyệt trực tiếp thất bại: {approval_error}", "error")

    return redirect(url_for('admin.view_suggestions'))

# --- === ROUTE DUYỆT TẤT CẢ ĐỀ XUẤT (SỬ DỤNG COMMAND QUEUE) === ---
@admin_bp.route('/suggestions/approve-all-start-job', methods=['POST'])
def start_approve_all_job():
    """Thêm lệnh yêu cầu chạy tác vụ duyệt tất cả suggestions vào queue."""
    command_type_to_add = 'approve_all_suggestions' # <<< Định nghĩa loại lệnh mới
    print(f"INFO: Received request to start task '{command_type_to_add}'.")

    if not db:
         flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
         return redirect(url_for('admin.view_suggestions'))
    # Tùy chọn: Kiểm tra xem hàm tác vụ có tồn tại không
    if not approve_all_suggestions_task:
         flash("Lỗi: Không tìm thấy hàm tác vụ nền 'approve_all_suggestions_task'.", "error")
         return redirect(url_for('admin.view_suggestions'))

    try:
        # Payload có thể rỗng vì tác vụ này không cần tham số cụ thể từ UI
        payload = {'source': 'approve_all_button'}

        # Thêm lệnh vào hàng đợi
        command_id = db.add_scheduler_command(
            command_type=command_type_to_add,
            payload=payload
        )

        if command_id:
            flash(f"Đã yêu cầu chạy tác vụ duyệt tất cả đề xuất. Scheduler sẽ xử lý (Command ID: {command_id}).", 'success')
        else:
             flash("Lỗi khi thêm yêu cầu vào hàng đợi CSDL.", "error")

    # Bỏ phần gọi live_scheduler.add_job trực tiếp và các except liên quan đến nó
    # except (ImportError, AttributeError) as ie: ...
    except Exception as e:
        print(f"Lỗi nghiêm trọng khi yêu cầu duyệt tất cả: {e}")
        print(traceback.format_exc())
        flash(f"Đã xảy ra lỗi không mong muốn: {e}", "error")

    return redirect(url_for('admin.view_suggestions'))



# =============================================
# === CÁC ROUTE MỚI THÊM VÀO ===
# =============================================

# === Quản lý Tài khoản ===
@admin_bp.route('/accounts', methods=['GET'])
def view_accounts():
    """Xem danh sách các tài khoản với tìm kiếm và phân trang."""
    page = request.args.get('page', 1, type=int)
    if page < 1: page = 1 # Đảm bảo trang không âm
    per_page = current_app.config.get('ADMIN_ITEMS_PER_PAGE', 10)
    search_query = request.args.get('search', '', type=str).strip() # Lấy và làm sạch query tìm kiếm

    accounts_list = []      # Mặc định là list rỗng
    total_items = 0         # Mặc định tổng số là 0
    pagination_details = None # Dùng dict để chứa thông tin phân trang cho template

    try:
        # Gọi hàm CSDL MỚI, nhận về tuple (list, total)
        accounts_result, total_result = db.get_all_accounts_paginated(
            page=page,
            per_page=per_page,
            search_query=search_query if search_query else None # Truyền None nếu không tìm kiếm
        )

        # Kiểm tra kết quả từ CSDL
        if accounts_result is not None and total_result is not None:
            accounts_list = accounts_result
            total_items = total_result

            if total_items > 0:
                # Tính toán thông tin phân trang
                total_pages = math.ceil(total_items / per_page)

                # Kiểm tra nếu trang yêu cầu vượt quá tổng số trang
                if page > total_pages:
                     flash(f'Trang {page} không tồn tại. Hiển thị trang cuối ({total_pages}).', 'warning')
                     return redirect(url_for('.view_accounts', page=total_pages, search=search_query))

                # Tạo dictionary chứa thông tin phân trang để truyền cho template
                pagination_details = {
                    'page': page,
                    'per_page': per_page,
                    'total_items': total_items,
                    'total_pages': total_pages,
                    'has_prev': page > 1,
                    'has_next': page < total_pages,
                    'prev_num': page - 1 if page > 1 else None,
                    'next_num': page + 1 if page < total_pages else None,
                    # Không cần 'items' ở đây vì đã có biến accounts_list riêng
                }
            # else: Nếu total_items là 0, pagination_details vẫn là None, template sẽ không hiển thị phân trang
        else:
            # Hàm CSDL trả về (None, None) -> Lỗi CSDL
            current_app.logger.error("get_all_accounts_paginated trả về (None, None) trong view_accounts.")
            flash('Có lỗi xảy ra khi tải danh sách tài khoản. Vui lòng kiểm tra log server.', 'error')
            # accounts_list và total_items giữ giá trị mặc định ([], 0)

    except Exception as e:
        # Bắt lỗi không mong muốn khác
        current_app.logger.error(f"Lỗi trong view_accounts khi gọi DB: {e}", exc_info=True) # Log traceback
        flash('Có lỗi nghiêm trọng xảy ra khi tải danh sách tài khoản.', 'error')
        # accounts_list và total_items giữ giá trị mặc định ([], 0)

    # Render template với dữ liệu
    return render_template('admin_accounts.html',
                           title="Quản lý Tài khoản",     # Tiêu đề trang
                           accounts=accounts_list,       # Danh sách tài khoản (luôn là list)
                           pagination_details=pagination_details, # Dict thông tin phân trang hoặc None
                           search_query=search_query) 


@admin_bp.route('/accounts/add', methods=['GET', 'POST'])
def add_account():
    # --- Xử lý POST Request ---
    if request.method == 'POST':
        try:
            # Lấy dữ liệu từ form
            account_id = request.form.get('account_id')
            platform = request.form.get('platform')
            username = request.form.get('username')
            notes = request.form.get('notes')
            goal = request.form.get('goal')
            strategy_id = request.form.get('default_strategy_id')
            status = request.form.get('status', 'active')

            # Validate dữ liệu
            if not account_id or not platform or not username:
                 flash("Account ID, Platform và Username là bắt buộc.", "warning")
                 # --- Nếu validation lỗi, cần lấy lại dữ liệu để hiển thị form ---
                 strategies = db.get_all_strategies() or []
                 valid_platforms = current_app.config.get('VALID_PLATFORMS', [])
                 valid_goals = current_app.config.get('VALID_GOALS', [])
                 return render_template('admin_add_account.html',
                                        title="Thêm Tài khoản Mới",
                                        strategies=strategies,
                                        valid_platforms=valid_platforms,
                                        valid_goals=valid_goals,
                                        current_data=request.form), 400 # Trả về form với dữ liệu đã nhập

            # Gọi hàm DB để thêm mới
            success = db.add_new_account(account_id, platform, username, status, notes, goal, strategy_id if strategy_id else None)

            # Xử lý kết quả
            if success:
                flash('Thêm tài khoản thành công!', 'success')
                return redirect(url_for('admin.view_accounts')) # Redirect nếu thành công
            else:
                flash('Thêm tài khoản thất bại! (ID có thể đã tồn tại?)', 'error')
                # --- Nếu thêm thất bại, lấy lại dữ liệu để hiển thị form ---
                strategies = db.get_all_strategies() or []
                valid_platforms = current_app.config.get('VALID_PLATFORMS', [])
                valid_goals = current_app.config.get('VALID_GOALS', [])
                return render_template('admin_add_account.html',
                                       title="Thêm Tài khoản Mới",
                                       strategies=strategies,
                                       valid_platforms=valid_platforms,
                                       valid_goals=valid_goals,
                                       current_data=request.form) # Ở lại form với dữ liệu đã nhập

        except Exception as e:
             print(f"Lỗi nghiêm trọng khi thêm account: {e}")
             flash(f"Lỗi không mong muốn khi thêm tài khoản: {e}", "error")
             # --- Nếu có lỗi Exception, lấy lại dữ liệu để hiển thị form ---
             strategies = db.get_all_strategies() or []
             valid_platforms = current_app.config.get('VALID_PLATFORMS', [])
             valid_goals = current_app.config.get('VALID_GOALS', [])
             return render_template('admin_add_account.html',
                                    title="Thêm Tài khoản Mới",
                                    strategies=strategies,
                                    valid_platforms=valid_platforms,
                                    valid_goals=valid_goals,
                                    current_data=request.form) # Ở lại form với dữ liệu đã nhập

    # --- Xử lý GET Request ---
    # Chỉ thực hiện khi request.method là 'GET'
    strategies = []
    valid_platforms = []
    valid_goals = []
    try:
        # Lấy danh sách strategies, platforms, goals để hiển thị form
        strategies = db.get_all_strategies()
        if strategies is None:
             flash("Lỗi tải danh sách chiến lược.", "error")
             strategies = []
        valid_platforms = current_app.config.get('VALID_PLATFORMS', [])
        valid_goals = current_app.config.get('VALID_GOALS', [])

    except Exception as e:
        print(f"Lỗi nghiêm trọng load data for add account form: {e}")
        flash("Lỗi không mong muốn khi tải dữ liệu form.", "error")
        # strategies, valid_platforms, valid_goals sẽ là list rỗng đã khởi tạo

    # Render template cho GET request
    return render_template('admin_add_account.html',
                           title="Thêm Tài khoản Mới",
                           strategies=strategies,
                           valid_platforms=valid_platforms,
                           valid_goals=valid_goals)


@admin_bp.route('/accounts/<account_id>/edit', methods=['GET', 'POST'])
def edit_account(account_id):
    # --- Xử lý POST Request ---
    if request.method == 'POST':
        try:
            # Lấy dữ liệu từ form
            platform = request.form.get('platform')
            username = request.form.get('username')
            status = request.form.get('status')
            notes = request.form.get('notes')
            goal = request.form.get('goal')
            strategy_id = request.form.get('default_strategy_id')

            # Validate dữ liệu
            if not platform or not username:
                 flash("Platform và Username là bắt buộc.", "warning")
                 # --- Nếu validation lỗi, cần lấy lại dữ liệu để hiển thị form ---
                 account = db.get_account_details(account_id) # Lấy lại account data
                 strategies = db.get_all_strategies() or []
                 valid_platforms = current_app.config.get('VALID_PLATFORMS', [])
                 valid_goals = current_app.config.get('VALID_GOALS', [])
                 if not account: # Kiểm tra lại account tồn tại
                      flash(f"Không tìm thấy tài khoản ID {account_id} để sửa.", "error")
                      return redirect(url_for('admin.view_accounts'))
                 # Truyền account vào lại để giữ giá trị cũ trên form
                 return render_template('admin_edit_account.html',
                                        title=f"Sửa Tài khoản {account_id}",
                                        account=account, # Dùng account data cũ
                                        strategies=strategies,
                                        valid_platforms=valid_platforms,
                                        valid_goals=valid_goals), 400 # Trả về form

            # Gọi hàm DB để cập nhật
            success = db.update_account(
                account_id=account_id, platform=platform, username=username, status=status,
                notes=notes, goal=goal, default_strategy_id=strategy_id if strategy_id else None
            )

            # Xử lý kết quả
            if success:
                flash('Cập nhật tài khoản thành công!', 'success')
                return redirect(url_for('admin.view_accounts')) # Redirect nếu thành công
            else:
                flash('Cập nhật tài khoản thất bại (ID không tồn tại hoặc lỗi CSDL).', 'error')
                # --- Nếu update thất bại, lấy lại dữ liệu để hiển thị form ---
                account = db.get_account_details(account_id) # Lấy lại account data
                strategies = db.get_all_strategies() or []
                valid_platforms = current_app.config.get('VALID_PLATFORMS', [])
                valid_goals = current_app.config.get('VALID_GOALS', [])
                if not account: return redirect(url_for('admin.view_accounts'))
                # Truyền account vào lại để giữ giá trị cũ trên form
                return render_template('admin_edit_account.html',
                                       title=f"Sửa Tài khoản {account_id}",
                                       account=account, # Dùng account data cũ
                                       strategies=strategies,
                                       valid_platforms=valid_platforms,
                                       valid_goals=valid_goals)

        except Exception as e:
            print(f"Lỗi nghiêm trọng khi cập nhật account {account_id}: {e}")
            flash(f"Lỗi không mong muốn khi cập nhật tài khoản: {e}", "error")
            # --- Nếu có lỗi Exception, lấy lại dữ liệu để hiển thị form ---
            account = db.get_account_details(account_id) # Lấy lại account data
            strategies = db.get_all_strategies() or []
            valid_platforms = current_app.config.get('VALID_PLATFORMS', [])
            valid_goals = current_app.config.get('VALID_GOALS', [])
            if not account: return redirect(url_for('admin.view_accounts'))
            # Truyền account vào lại để giữ giá trị cũ trên form
            return render_template('admin_edit_account.html',
                                   title=f"Sửa Tài khoản {account_id}",
                                   account=account, # Dùng account data cũ
                                   strategies=strategies,
                                   valid_platforms=valid_platforms,
                                   valid_goals=valid_goals)

    # --- Xử lý GET Request ---
    # Chỉ thực hiện khi request.method là 'GET'
    account = None
    strategies = []
    valid_platforms = []
    valid_goals = []
    try:
        # Lấy dữ liệu account cần sửa và các list để hiển thị form
        account = db.get_account_details(account_id)
        strategies = db.get_all_strategies() or []

        if account is None:
            flash(f"Không tìm thấy tài khoản có ID {account_id}.", "error")
            return redirect(url_for('admin.view_accounts'))

        valid_platforms = current_app.config.get('VALID_PLATFORMS', [])
        valid_goals = current_app.config.get('VALID_GOALS', [])

    except Exception as e:
        print(f"Lỗi nghiêm trọng khi tải dữ liệu sửa account {account_id}: {e}")
        flash("Không thể tải dữ liệu để sửa tài khoản.", "error")
        return redirect(url_for('admin.view_accounts'))

    # Render template cho GET request
    return render_template('admin_edit_account.html',
                           title=f"Sửa Tài khoản {account_id}",
                           account=account,
                           strategies=strategies,
                           valid_platforms=valid_platforms,
                           valid_goals=valid_goals)

@admin_bp.route('/accounts/<account_id>/delete', methods=['POST'])
def delete_account(account_id):
    """Xử lý xóa tài khoản."""
    try:
        # Gọi hàm delete_account từ database.py (đã tạo skeleton trước đó)
        success = db.delete_account(account_id)
        if success:
            flash(f"Đã xóa tài khoản ID {account_id}.", 'success')
        else:
            flash(f"Xóa tài khoản ID {account_id} thất bại (ID không tồn tại hoặc lỗi CSDL).", 'error')
    except Exception as e:
        print(f"Lỗi nghiêm trọng khi xóa account {account_id}: {e}")
        flash(f"Đã xảy ra lỗi không mong muốn khi xóa tài khoản: {e}", "error")

    # Luôn redirect về trang danh sách tài khoản sau khi xử lý
    return redirect(url_for('admin.view_accounts'))

# === Quản lý Templates ===
@admin_bp.route('/templates')
def view_templates():
    """Hiển thị danh sách Templates & Variations có bộ lọc và phân trang."""
    title="Quản lý Templates & Variations"
    templates_data = [] # Danh sách template cho trang hiện tại
    distinct_categories = [] # Danh sách category cho dropdown lọc
    active_filters = {} # Lưu các filter đang áp dụng
    pagination = None # Thông tin phân trang

    if not db:
         flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
    else:
        try:
            # 1. Lấy tham số trang và bộ lọc từ URL
            page = request.args.get('page', 1, type=int)
            if page < 1: page = 1

            filter_ref = request.args.get('filter_ref', '').strip()
            filter_category = request.args.get('filter_category', '').strip()
            # Lưu lại các filter đang được dùng để truyền về template
            active_filters = {k.replace('filter_', ''): v for k, v in request.args.items() if v and k.startswith('filter_')}
            print(f"DEBUG (view_templates): Page={page}, Active Filters = {active_filters}")

            # 2. Gọi hàm DB để lấy dữ liệu đã lọc và phân trang
            # Hàm này trả về (list_items_page, total_items)
            templates_data, total_items = db.get_filtered_templates_with_details(
                filter_ref=filter_ref if filter_ref else None,
                filter_category=filter_category if filter_category else None,
                page=page,
                per_page=PER_PAGE_TEMPLATES
            )

            if templates_data is None or total_items is None:
                 flash("Lỗi khi tải danh sách template từ CSDL.", "error")
                 templates_data = []; total_items = 0
                 pagination = None # Lỗi DB -> không có phân trang
                 print("DEBUG (view_templates): DB query failed, pagination set to None.")
            else:
                 # 3. Tính toán thông tin phân trang
                 if total_items > 0:
                     total_pages = ceil(total_items / PER_PAGE_TEMPLATES)
                     if page > total_pages and total_pages > 0: page = total_pages # Đảm bảo page hợp lệ
                     pagination = {
                        'page': page, 'per_page': PER_PAGE_TEMPLATES, 'total_items': total_items,
                        'total_pages': total_pages, 'has_prev': page > 1, 'has_next': page < total_pages,
                        'prev_num': page - 1 if page > 1 else None,
                        'next_num': page + 1 if page < total_pages else None
                     }
                 else: # total_items = 0
                     pagination = {'page': 1, 'per_page': PER_PAGE_TEMPLATES, 'total_items': 0, 'total_pages': 0, 'has_prev': False, 'has_next': False}
                 print(f"DEBUG (view_templates): Calculated pagination = {pagination}")

            # 4. Lấy danh sách category duy nhất cho dropdown lọc
            distinct_categories = db.get_distinct_template_categories() or []
            print(f"DEBUG (view_templates): Fetched {len(distinct_categories)} distinct categories.")

        except Exception as e:
            print(f"Lỗi nghiêm trọng load templates page data: {e}")
            flash("Lỗi không mong muốn khi tải danh sách template.", "error")
            templates_data = []; distinct_categories = []; pagination = None
            print(f"DEBUG (view_templates): Exception occurred, pagination set to None.")

    # 5. Render template với đầy đủ dữ liệu
    print(f"DEBUG (view_templates): Final pagination object being passed = {pagination}")
    return render_template('admin_templates.html',
                           title=title,
                           templates=templates_data,              # <<< Danh sách template của trang này
                           distinct_categories=distinct_categories, # <<< Danh sách category cho filter
                           filters=active_filters,                # <<< Filter đang áp dụng
                           pagination=pagination) 


@admin_bp.route('/templates/add', methods=['GET', 'POST'])
def add_template(): 
    if request.method == 'POST':
        try:
            template_ref = request.form.get('template_ref')
            description = request.form.get('description')
            category = request.form.get('category')
            variation_text = request.form.get('variation_text') # Biến thể đầu tiên

            if not template_ref or not variation_text:
                 flash("Template Ref và ít nhất một Variation Text là bắt buộc.", "warning")
                 return render_template('admin_add_template.html', title="Thêm Template Mới", current_data=request.form), 400

            # Giả sử db.add_new_template đã được cập nhật để xử lý cả ref và variation đầu tiên
            added_ref = db.add_new_template(template_ref, variation_text, description, category)
            if added_ref:
                flash(f'Thêm template "{added_ref}" thành công!', 'success')
                # Chuyển đến trang xem chi tiết variations của template vừa thêm
                return redirect(url_for('admin.view_template_variations', template_ref=added_ref))
            else:
                flash('Thêm template thất bại!', 'error')
                return render_template('admin_add_template.html', title="Thêm Template Mới", current_data=request.form)
        except Exception as e:
             print(f"Lỗi nghiêm trọng khi thêm template: {e}")
             flash(f"Lỗi không mong muốn khi thêm template: {e}", "error")
             return render_template('admin_add_template.html', title="Thêm Template Mới", current_data=request.form)

    # GET request
    return render_template('admin_add_template.html', title="Thêm Template Mới")

@admin_bp.route('/templates/<template_ref>/variations')
def view_template_variations(template_ref):
    try:
        # Sử dụng hàm db.get_template_variations đã có
        variations = db.get_template_variations(template_ref)
        template_details = db.get_template_ref_details(template_ref) # Cần thêm hàm này để lấy description/category

        if variations is None:
            flash(f"Lỗi khi tải variations cho template '{template_ref}'.", "error")
            # Có thể redirect về trang view_templates hoặc hiển thị trang lỗi riêng
            return redirect(url_for('admin.view_templates'))
        if template_details is None:
             # Không tìm thấy template ref này
             flash(f"Không tìm thấy template ref '{template_ref}'.", "warning")
             return redirect(url_for('admin.view_templates'))

    except Exception as e:
        print(f"Lỗi nghiêm trọng load variations for {template_ref}: {e}")
        flash("Lỗi không mong muốn khi tải variations.", "error")
        return redirect(url_for('admin.view_templates'))

    return render_template('admin_template_variations.html',
                           title=f"Variations cho '{template_ref}'",
                           template_ref=template_ref,
                           template_details=template_details,
                           variations=variations)


@admin_bp.route('/templates/<template_ref>/variations/add', methods=['GET', 'POST'])
def add_template_variation(template_ref):
     # Kiểm tra xem template_ref có tồn tại không
     template_details = db.get_template_ref_details(template_ref)
     if not template_details:
          flash(f"Template ref '{template_ref}' không tồn tại.", "error")
          return redirect(url_for('admin.view_templates'))

     if request.method == 'POST':
          variation_text = request.form.get('variation_text')
          if not variation_text:
               flash("Nội dung variation không được để trống.", "warning")
               # Render lại form GET (cần truyền template_details ở đây nữa)
               return render_template('admin_add_template_variation.html',
                                      title=f"Thêm Variation cho '{template_ref}'",
                                      template_ref=template_ref,
                                      template_details=template_details) # <<< Thêm nếu hàm GET cần

          try:
               success = db.add_single_variation(template_ref, variation_text)
               if success:
                    # ... (xử lý thành công) ...
                    return redirect(url_for('admin.view_template_variations', template_ref=template_ref))

               else:
                    flash("Thêm variation thất bại.", "error")
                    # Ở lại trang add, truyền template_details
                    return render_template('admin_add_template_variation.html',
                                           title=f"Thêm Variation cho '{template_ref}'",
                                           template_ref=template_ref,
                                           template_details=template_details, # <<< Thêm
                                           current_text=variation_text)
          except Exception as e:
               print(f"Lỗi nghiêm trọng khi thêm variation: {e}") # <<< Lỗi xảy ra ở đây
               flash(f"Lỗi không mong muốn khi thêm variation: {e}", "error")
               # === SỬA LẠI RETURN TRONG EXCEPT NÀY ===
               return render_template('admin_add_template_variation.html',
                                      title=f"Thêm Variation cho '{template_ref}' (Lỗi Exception)",
                                      template_ref=template_ref,
                                      template_details=template_details, # <<< TRUYỀN LẠI template_details
                                      current_text=variation_text)
               # === KẾT THÚC SỬA ===

     # GET request (cũng nên truyền template_details)
     return render_template('admin_add_template_variation.html',
                            title=f"Thêm Variation cho '{template_ref}'",
                            template_ref=template_ref,
                            template_details=template_details)

@admin_bp.route('/templates/<template_ref>/delete', methods=['POST'])
def delete_template(template_ref):
    """Xử lý xóa Template Ref và các variations liên quan."""
    try:
        # Gọi hàm xóa từ database.py (cần tạo hàm này)
        success = db.delete_template_ref(template_ref)
        if success:
            flash(f"Đã xóa Template Ref '{template_ref}' và các variations của nó.", 'success')
        else:
            # Trường hợp này ít xảy ra nếu không có lỗi FK, có thể do ref không tồn tại
            flash(f"Xóa Template Ref '{template_ref}' thất bại (Ref không tồn tại?).", 'error')

    except psycopg2.errors.ForeignKeyViolation:
         # Bắt lỗi cụ thể khi template đang được tham chiếu bởi bảng khác (rules, transitions)
         flash(f"Không thể xóa Template Ref '{template_ref}' vì nó đang được sử dụng bởi Rules hoặc Transitions.", 'error')
         print(f"INFO: Ngăn chặn xóa template '{template_ref}' do vi phạm khóa ngoại.")

    except Exception as e:
        print(f"Lỗi nghiêm trọng khi xóa template {template_ref}: {e}")
        flash(f"Đã xảy ra lỗi không mong muốn khi xóa Template Ref: {e}", "error")

    # Luôn redirect về trang danh sách templates
    return redirect(url_for('admin.view_templates'))

def delete_template_ref(template_ref: str) -> bool:
    """Xóa một template_ref khỏi response_templates.
       Do có ràng buộc ON DELETE CASCADE trong DB, các variations liên quan
       trong template_variations cũng sẽ tự động bị xóa.
       Hàm sẽ thất bại (ném ForeignKeyViolation) nếu template_ref đang được
       tham chiếu bởi simple_rules hoặc stage_transitions (do không có ON DELETE).
    """
    if not template_ref: return False
    conn = db.get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        print(f"DEBUG (database.py): Xóa template_ref='{template_ref}'...")
        # Chỉ cần xóa từ response_templates, variations sẽ tự xóa theo CASCADE
        sql = "DELETE FROM response_templates WHERE template_ref = %s;"
        cur.execute(sql, (template_ref,))
        conn.commit()
        # Kiểm tra xem có dòng nào thực sự bị xóa không
        success = cur.rowcount > 0
        if not success:
            print(f"WARNING (database.py - delete_template_ref): Không tìm thấy template_ref '{template_ref}' để xóa.")

    except psycopg2.Error as db_err:
         # Không bắt lỗi ForeignKeyViolation ở đây, để route xử lý
         print(f"LỖI (database.py - delete_template_ref): DELETE thất bại: {db_err}")
         if conn: conn.rollback()
         # Ném lại lỗi để route có thể bắt cụ thể lỗi FK
         raise db_err
    except Exception as e:
        print(f"LỖI (database.py - delete_template_ref): Lỗi không xác định: {e}")
        if conn: conn.rollback()
        raise e # Ném lại lỗi để route bắt
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success # Chỉ trả về True nếu không có Exception và rowcount > 0

@admin_bp.route('/templates/variations/<int:variation_id>/delete', methods=['POST'])
def delete_template_variation(variation_id):
    """Xử lý xóa một variation cụ thể."""
    # Lấy template_ref từ form ẩn để redirect về đúng trang
    template_ref_redirect = request.form.get('template_ref_redirect')

    if not template_ref_redirect:
         # Nếu không có template_ref để redirect, thì về trang template list chung
         flash("Lỗi: Không xác định được template gốc để quay lại.", "error")
         return redirect(url_for('admin.view_templates'))

    try:
        # Gọi hàm xóa variation từ database.py (cần tạo hàm này)
        success = db.delete_single_variation(variation_id)
        if success:
            flash(f"Đã xóa variation ID {variation_id}.", 'success')
        else:
            flash(f"Xóa variation ID {variation_id} thất bại (ID không tồn tại?).", 'error')
    except Exception as e:
        print(f"Lỗi nghiêm trọng khi xóa variation {variation_id}: {e}")
        flash(f"Đã xảy ra lỗi không mong muốn khi xóa variation: {e}", "error")

    # Redirect về trang xem variations của template gốc
    return redirect(url_for('admin.view_template_variations', template_ref=template_ref_redirect))


    
@admin_bp.route('/templates/<template_ref>/edit', methods=['GET', 'POST'])
def edit_template_details(template_ref):
    """Sửa description và category của Template Ref."""
    if not db:
         flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
         return redirect(url_for('admin.view_templates'))

    # Lấy details cho GET và để kiểm tra sự tồn tại cho POST
    template_details = db.get_template_ref_details(template_ref)
    if not template_details:
        flash(f"Không tìm thấy template ref '{template_ref}'.", "error")
        return redirect(url_for('admin.view_templates'))

    # --- Xử lý POST Request ---
    if request.method == 'POST':
        try:
            # Lấy dữ liệu mới từ form
            new_description = request.form.get('description', '').strip()
            new_category = request.form.get('category', '').strip()

            # Validate đơn giản (ví dụ: category không nên quá dài)
            if len(new_category) > 50:
                 flash("Tên Category quá dài (tối đa 50 ký tự).", "warning")
                 # Cần lấy lại distinct_categories để render lại form lỗi
                 distinct_categories = db.get_distinct_template_categories() or []
                 return render_template('admin_edit_template_details.html',
                                        title=f"Sửa Chi tiết Template '{template_ref}' (Lỗi)",
                                        template=template_details,
                                        distinct_categories=distinct_categories,
                                        current_data=request.form), 400 # Giữ lại dữ liệu đã nhập

            # Gọi hàm DB để cập nhật
            success = db.update_template_details(
                template_ref=template_ref,
                description=new_description or None, # Chuyển rỗng thành None nếu DB cho phép NULL
                category=new_category or None      # Chuyển rỗng thành None nếu DB cho phép NULL
            )

            if success:
                flash(f"Đã cập nhật chi tiết cho template '{template_ref}' thành công!", 'success')
                return redirect(url_for('admin.view_templates')) # <<< Redirect về trang danh sách
            else:
                # Lỗi này ít xảy ra nếu template_ref tồn tại
                flash(f"Cập nhật chi tiết cho template '{template_ref}' thất bại.", 'error')
                # Render lại form với dữ liệu người dùng vừa nhập
                distinct_categories = db.get_distinct_template_categories() or []
                return render_template('admin_edit_template_details.html',
                                       title=f"Sửa Chi tiết Template '{template_ref}'",
                                       template=template_details,
                                       distinct_categories=distinct_categories,
                                       current_data=request.form) # Hiển thị lại lỗi

        except Exception as e:
            print(f"Lỗi nghiêm trọng khi cập nhật template details {template_ref}: {e}")
            flash(f"Lỗi không mong muốn khi cập nhật: {e}", "error")
            # Render lại form với dữ liệu gốc ban đầu khi có lỗi nghiêm trọng
            distinct_categories = db.get_distinct_template_categories() or []
            return render_template('admin_edit_template_details.html',
                                   title=f"Sửa Chi tiết Template '{template_ref}'",
                                   template=template_details, # Dùng data gốc
                                   distinct_categories=distinct_categories)


    # --- Xử lý GET Request ---
    # Chỉ cần lấy dữ liệu và hiển thị form
    distinct_categories = []
    try:
        # Lấy danh sách category cho datalist/dropdown
        distinct_categories = db.get_distinct_template_categories() or []
    except Exception as e:
         flash("Lỗi khi tải danh sách category cho form.", "warning")

    # template_details đã được lấy ở đầu hàm
    return render_template('admin_edit_template_details.html',
                           title=f"Sửa Chi tiết Template '{template_ref}'",
                           template=template_details, # Dữ liệu hiện tại của template
                           distinct_categories=distinct_categories)


@admin_bp.route('/templates/variations/<int:variation_id>/edit', methods=['GET', 'POST'])
def edit_template_variation(variation_id):
    """Sửa nội dung text của một variation."""
    # Lấy thông tin variation hiện tại cho cả GET và POST (nếu có lỗi)
    variation = db.get_variation_details(variation_id)
    if not variation:
        flash(f"Không tìm thấy variation ID {variation_id}.", "error")
        # Không biết redirect về template ref nào, quay về trang template list chung
        return redirect(url_for('admin.view_templates'))
    # Lấy template_ref để dùng cho redirect và link Hủy
    template_ref_redirect = variation.get('template_ref')

    if request.method == 'POST':
        new_variation_text = request.form.get('variation_text')

        if not new_variation_text: # Kiểm tra text không rỗng
             flash("Nội dung variation không được để trống.", "warning")
             # Render lại form với lỗi và dữ liệu cũ (variation)
             return render_template('admin_edit_template_variation.html',
                                    title=f"Sửa Variation {variation_id}",
                                    variation=variation), 400
        try:
            success = db.update_variation(variation_id, new_variation_text)
            if success:
                flash(f"Cập nhật variation ID {variation_id} thành công!", 'success')
                # Redirect về trang xem variations của template gốc
                return redirect(url_for('admin.view_template_variations', template_ref=template_ref_redirect))
            else:
                 # Ít xảy ra nếu variation tồn tại
                flash(f"Cập nhật variation ID {variation_id} thất bại.", 'error')
                # Render lại form với dữ liệu cũ
                return render_template('admin_edit_template_variation.html',
                                        title=f"Sửa Variation {variation_id}",
                                        variation=variation)
        except Exception as e:
             print(f"Lỗi nghiêm trọng khi cập nhật variation {variation_id}: {e}")
             flash(f"Lỗi không mong muốn khi cập nhật variation: {e}", "error")
             # Render lại form với dữ liệu cũ
             return render_template('admin_edit_template_variation.html',
                                     title=f"Sửa Variation {variation_id}",
                                     variation=variation)

    # GET request: Hiển thị form với dữ liệu hiện tại
    return render_template('admin_edit_template_variation.html',
                           title=f"Sửa Variation {variation_id}",
                           variation=variation) # Truyền variation details vào template

# === Quản lý Chiến lược ===

@admin_bp.route('/strategies/control') # <<< Đổi URL
def view_strategies_control(): # <<< Đổi tên hàm
    """Hiển thị danh sách các chiến lược loại 'control'."""
    title = "Quản lý Chiến lược Điều khiển" # <<< Đổi Title
    control_strategies = []
    if not db:
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
    else:
        try:
            # Gọi hàm DB với bộ lọc type='control'
            control_strategies = db.get_all_strategies(strategy_type_filter='control')
            if control_strategies is None:
                flash("Lỗi khi tải danh sách chiến lược điều khiển.", "error")
                control_strategies = []
        except Exception as e:
            print(f"Lỗi load control strategies: {e}")
            flash("Lỗi không mong muốn khi tải dữ liệu.", "error")
            control_strategies = []
    # Render template đã ĐỔI TÊN
    return render_template('admin_strategies_control.html',
                           title=title,
                           strategies=control_strategies)



@admin_bp.route('/strategies/<strategy_id>/stages-language')
def view_strategy_stages_language(strategy_id):
    """Hiển thị stages và language transitions cho một Language Strategy."""
    strategy = None
    strategy_stages_list = []
    transitions_list = []
    all_templates = [] # Cần cho nút Add Transition

    if not db:
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
    else:
        try:
            strategy = db.get_strategy_details(strategy_id)
            print(f"DEBUG (view_strategy_stages_language): Fetched strategy details for '{strategy_id}': {strategy}")
            # <<< Kiểm tra strategy tồn tại và đúng type 'language' >>>
            if strategy is None or strategy.get('strategy_type') != 'language':
                flash(f"Không tìm thấy Language Strategy ID {strategy_id} hoặc loại không đúng.", "warning")
                return redirect(url_for('admin.view_strategies_language')) # Redirect về list language

            strategy_stages_list = db.get_stages_for_strategy(strategy_id) or []
            # Hàm này lấy tất cả transition thô, template sẽ lọc ra cái cần hiển thị
            transitions_list = db.get_strategy_action_sequence(strategy_id) or []
            all_templates = db.get_all_template_refs() or [] # Lấy templates cho nút Add

        except Exception as e:
            print(f"Lỗi tải stages/transitions cho language strategy {strategy_id}: {e}")
            flash("Lỗi tải chi tiết chiến lược hội thoại.", "error")
            # Reset về list rỗng khi lỗi
            strategy = strategy or {'strategy_id': strategy_id, 'name': 'Lỗi tải tên'} # Để tránh lỗi template
            strategy_stages_list = []
            transitions_list = []
            all_templates = []

    # <<< Render template MỚI: admin_strategy_stages_language.html >>>
    return render_template('admin_strategy_stages_language.html',
                           title=f"Language Stages & Transitions cho '{strategy.get('name', strategy_id)}'",
                           strategy=strategy,
                           strategy_stages=strategy_stages_list,
                           transitions=transitions_list, # Truyền list transitions thô
                           all_templates=all_templates) # Truyền cho nút Add

# --- Đảm bảo route cho CONTROL đã được đổi tên đúng ---
@admin_bp.route('/strategies/<strategy_id>/stages-control')
def view_strategy_stages_control(strategy_id):
    # ... (Code của hàm này giữ nguyên như đã cung cấp trước đó) ...
    strategy = None
    strategy_stages_list = []
    transitions_list = []
    all_macros = []
    if not db: flash("Lỗi DB.", "error")
    else:
        try:
            strategy = db.get_strategy_details(strategy_id)
            if strategy is None or strategy.get('strategy_type') != 'control':
                flash(f"Không tìm thấy Control Strategy ID {strategy_id} hoặc loại không đúng.", "warning")
                return redirect(url_for('admin.view_strategies_control'))
            strategy_stages_list = db.get_stages_for_strategy(strategy_id) or []
            transitions_list = db.get_strategy_action_sequence(strategy_id) or []
            all_macros = db.get_all_macro_definitions() or []
        except Exception as e:
            print(f"Lỗi tải stages/transitions cho control strategy {strategy_id}: {e}")
            flash("Lỗi tải chi tiết chiến lược điều khiển.", "error")
            strategy = strategy or {'strategy_id': strategy_id, 'name': 'Lỗi tải tên'}
            strategy_stages_list = []; transitions_list = []; all_macros = []
    print(f"DEBUG Route (view_strategy_stages_control): Passing transitions to template: {transitions_list}")
    return render_template('admin_strategy_stages_control.html', # <<< Đảm bảo tên đúng
                           title=f"Control Stages & Transitions cho '{strategy.get('name', strategy_id)}'",
                           strategy=strategy,
                           strategy_stages=strategy_stages_list,
                           transitions=transitions_list,
                           all_macros=all_macros)

@admin_bp.route('/stages/add-language', methods=['GET', 'POST'])
def add_stage_language():
    strategy_id = request.args.get('strategy_id') or request.form.get('strategy_id')
    if not strategy_id:
        flash("Cần cung cấp strategy_id.", "error")
        return redirect(url_for('admin.view_strategies_language')) # Về trang list language

    # Kiểm tra strategy tồn tại và đúng loại
    strategy_details = db.get_strategy_details(strategy_id)
    if not strategy_details or strategy_details.get('strategy_type') != 'language':
        flash("Strategy không hợp lệ hoặc không phải loại 'language'.", "error")
        return redirect(url_for('admin.view_strategies_language'))

    cancel_url = url_for('admin.view_strategy_stages_language', strategy_id=strategy_id)
    title = f"Thêm Stage cho Language Strategy {strategy_id}"

    if request.method == 'POST':
        stage_id = request.form.get('stage_id', '').strip()
        description = request.form.get('description', '').strip()
        order_str = request.form.get('stage_order', '0').strip()

        # Validate dữ liệu cơ bản
        errors = []
        if not stage_id: errors.append("Stage ID là bắt buộc.")
        try: order = int(order_str)
        except ValueError: errors.append("Stage Order phải là số nguyên.")

        if errors:
            for error in errors: flash(error, "warning")
            return render_template('admin_add_stage_language.html', title=title + " (Lỗi)",
                                   strategy_id=strategy_id, cancel_url=cancel_url,
                                   current_data=request.form), 400

        # Gọi hàm DB, identifying_elements là None cho language
        success, error_msg = db.add_new_stage(stage_id, strategy_id, description, order, None)

        if success:
            flash(f"Thêm stage '{stage_id}' thành công!", 'success')
            return redirect(cancel_url) # Redirect về trang chi tiết language
        else:
            flash(f"Thêm stage '{stage_id}' thất bại: {error_msg or 'Lỗi không xác định.'}", 'error')
            return render_template('admin_add_stage_language.html', title=title + " (Lỗi DB)",
                                   strategy_id=strategy_id, cancel_url=cancel_url,
                                   current_data=request.form)

    # GET request
    return render_template('admin_add_stage_language.html', title=title,
                           strategy_id=strategy_id, cancel_url=cancel_url)

@admin_bp.route('/stages/add-control', methods=['GET', 'POST'])
def add_stage_control():
    strategy_id = request.args.get('strategy_id') or request.form.get('strategy_id')
    if not strategy_id:
        flash("Cần cung cấp strategy_id.", "error")
        return redirect(url_for('admin.view_strategies_control')) # Về trang list control

    # Kiểm tra strategy tồn tại và đúng loại
    strategy_details = db.get_strategy_details(strategy_id)
    if not strategy_details or strategy_details.get('strategy_type') != 'control':
        flash("Strategy không hợp lệ hoặc không phải loại 'control'.", "error")
        return redirect(url_for('admin.view_strategies_control'))

    cancel_url = url_for('admin.view_strategy_stages_control', strategy_id=strategy_id)
    title = f"Thêm Stage cho Control Strategy {strategy_id}"

    if request.method == 'POST':
        stage_id = request.form.get('stage_id', '').strip()
        description = request.form.get('description', '').strip()
        order_str = request.form.get('stage_order', '0').strip()
        identifying_elements_str = request.form.get('identifying_elements', '{}').strip() # <<< Lấy trường này

        # Validate dữ liệu cơ bản và identifying_elements
        errors = []
        validated_identifying_elements_str = None # Để lưu JSON hợp lệ hoặc None
        if not stage_id: errors.append("Stage ID là bắt buộc.")
        try: order = int(order_str)
        except ValueError: errors.append("Stage Order phải là số nguyên.")
        # Validate JSON nếu có nhập (khác '{}' và không rỗng)
        if identifying_elements_str and identifying_elements_str.strip() != '{}':
            try:
                json.loads(identifying_elements_str) # Chỉ validate
                validated_identifying_elements_str = identifying_elements_str # Giữ lại nếu hợp lệ
            except json.JSONDecodeError:
                errors.append("Identifying Elements không phải là định dạng JSON hợp lệ.")
        # Nếu rỗng hoặc chỉ có '{}', validated_identifying_elements_str sẽ là None

        if errors:
            for error in errors: flash(error, "warning")
            return render_template('admin_add_stage_control.html', title=title + " (Lỗi)",
                                   strategy_id=strategy_id, cancel_url=cancel_url,
                                   current_data=request.form), 400

        # Gọi hàm DB, truyền identifying_elements
        success, error_msg = db.add_new_stage(stage_id, strategy_id, description, order, validated_identifying_elements_str)

        if success:
            flash(f"Thêm stage '{stage_id}' thành công!", 'success')
            return redirect(cancel_url) # Redirect về trang chi tiết control
        else:
            flash(f"Thêm stage '{stage_id}' thất bại: {error_msg or 'Lỗi không xác định.'}", 'error')
            return render_template('admin_add_stage_control.html', title=title + " (Lỗi DB)",
                                   strategy_id=strategy_id, cancel_url=cancel_url,
                                   current_data=request.form)

    # GET request
    return render_template('admin_add_stage_control.html', title=title,
                           strategy_id=strategy_id, cancel_url=cancel_url)

@admin_bp.route('/stages/<stage_id>/edit', methods=['GET', 'POST'])
def edit_stage(stage_id):
    """Sửa description, order, và identifying_elements của stage."""
    if not db:
        flash("Lỗi DB.", "error")
        return redirect(url_for('admin.index')) # Về Dashboard nếu lỗi DB

    # --- Lấy thông tin stage và strategy ngay từ đầu ---
    stage = None
    strategy_id_redirect = None
    strategy_details = None
    strategy_type = 'language' # Default
    redirect_endpoint = 'admin.view_strategy_stages_language' # Default
    # <<< Đặt giá trị mặc định an toàn cho cancel_url >>>
    cancel_url = url_for('admin.index') # Default về Dashboard nếu có lỗi nghiêm trọng

    try:
        stage = db.get_stage_details(stage_id) # Hàm này cần trả về dict có strategy_id
        if not stage:
            flash(f"Không tìm thấy stage ID {stage_id}.", "error")
            return redirect(url_for('admin.index')) # Về Dashboard nếu không tìm thấy stage

        strategy_id_redirect = stage.get('strategy_id')
        if strategy_id_redirect:
            strategy_details = db.get_strategy_details(strategy_id_redirect)
            if strategy_details:
                strategy_type = strategy_details.get('strategy_type', 'language')
                redirect_endpoint = 'admin.view_strategy_stages_language' if strategy_type == 'language' else 'admin.view_strategy_stages_control'
                # <<< TÍNH TOÁN cancel_url CHÍNH XÁC Ở ĐÂY >>>
                cancel_url = url_for(redirect_endpoint, strategy_id=strategy_id_redirect)
            else:
                # Không tìm thấy strategy gốc, đặt cancel về list chung
                flash(f"Cảnh báo: Không tìm thấy strategy gốc ID '{strategy_id_redirect}' của stage này.", "warning")
                cancel_url = url_for('admin.view_strategies_control') if strategy_type=='control' else url_for('admin.view_strategies_language')
        else:
            # Stage không có strategy_id? (Lỗi dữ liệu) - Đặt cancel về list chung
             flash(f"Cảnh báo: Stage '{stage_id}' không có strategy_id liên kết.", "warning")
             cancel_url = url_for('admin.view_strategies_language') # Tạm về language list

    except Exception as e:
        print(f"Lỗi nghiêm trọng khi lấy thông tin stage/strategy: {e}")
        flash("Lỗi khi đọc thông tin stage/strategy gốc.", "error")
        return redirect(url_for('admin.index')) # Redirect về index khi có lỗi nghiêm trọng

    # --- Đã có stage và cancel_url hợp lệ ở đây ---
    title = f"Sửa Stage '{stage_id}'"

    if request.method == 'POST':
        # Lấy dữ liệu từ form
        description = request.form.get('description')
        order_str = request.form.get('stage_order', '0')
        identifying_elements_str = request.form.get('identifying_elements', '{}')

        # --- Validate dữ liệu ---
        errors = []
        try:
            order = int(order_str)
        except ValueError:
            errors.append("Stage Order phải là số nguyên.")

        # Validate JSON Identifying Elements
        validated_identifying_elements_str = '{}' # Default
        if identifying_elements_str and identifying_elements_str.strip() and identifying_elements_str != '{}':
            try:
                json.loads(identifying_elements_str) # Chỉ validate
                validated_identifying_elements_str = identifying_elements_str # Giữ lại nếu hợp lệ
            except json.JSONDecodeError:
                errors.append("Identifying Elements không phải là định dạng JSON hợp lệ. Vui lòng nhập đúng định dạng hoặc để trống/ {}.")
        elif identifying_elements_str is not None and (not identifying_elements_str.strip() or identifying_elements_str == '{}'):
             validated_identifying_elements_str = None # Lưu NULL nếu rỗng hoặc chỉ {}

        # Nếu có lỗi validation
        if errors:
            for error in errors: flash(error, "warning")
            # <<< Luôn truyền cancel_url khi render lại >>>
            return render_template('admin_edit_stage.html', title=title + " (Lỗi)",
                                   stage=stage, # stage gốc đã lấy ở trên
                                   cancel_url=cancel_url,
                                   current_data=request.form), 400

        # --- Gọi hàm DB để cập nhật ---
        try:
            # Hàm update_stage nhận identifying_elements_str (có thể là None)
            success, error_msg = db.update_stage(stage_id, description, order, validated_identifying_elements_str)

            if success:
                flash(f"Cập nhật stage '{stage_id}' thành công!", 'success')
                # Redirect về trang chi tiết strategy gốc dùng cancel_url đã tính
                return redirect(cancel_url)
            else:
                flash(f"Cập nhật stage '{stage_id}' thất bại: {error_msg or 'Không có gì thay đổi?'}", 'error')
                # <<< Luôn truyền cancel_url khi render lại >>>
                return render_template('admin_edit_stage.html', title=title + " (Lỗi DB)",
                                       stage=stage, # stage gốc
                                       cancel_url=cancel_url,
                                       current_data=request.form)
        except Exception as e:
            print(f"Lỗi nghiêm trọng khi sửa stage {stage_id}: {e}")
            flash(f"Lỗi không mong muốn khi sửa stage: {e}", "error")
            # <<< Luôn truyền cancel_url khi render lại >>>
            return render_template('admin_edit_stage.html', title=title,
                                   stage=stage, # stage gốc
                                   cancel_url=cancel_url,
                                   current_data=request.form)

    # --- Xử lý GET request ---
    # Hiển thị form lần đầu
    # <<< Luôn truyền cancel_url vào template >>>
    return render_template('admin_edit_stage.html', title=title, stage=stage, cancel_url=cancel_url)

@admin_bp.route('/stages/<stage_id>/delete', methods=['POST'])
def delete_stage(stage_id):
    """Xóa một stage và redirect về trang chi tiết strategy phù hợp."""
    logger = current_app.logger if current_app else print
    logger.info(f"--- DEBUG (delete_stage): Received request for stage ID: {stage_id} ---")
    strategy_id_redirect = None
    strategy_type_redirect = 'unknown' # Khởi tạo là unknown
    redirect_endpoint = None # Endpoint trang chi tiết
    list_redirect_endpoint = 'admin.view_strategies_language' # Default fallback list

    # --- Cố gắng lấy thông tin STRATEGY GỐC TRƯỚC KHI XÓA ---
    try:
        # Hàm get_stage_details trả về dict có strategy_id
        stage_details = db.get_stage_details(stage_id)
        logger.debug(f"DEBUG (delete_stage): Fetched stage_details: {stage_details}")

        if stage_details:
            strategy_id_redirect = stage_details.get('strategy_id')
            logger.debug(f"DEBUG (delete_stage): Found parent strategy_id: {strategy_id_redirect}")
            if strategy_id_redirect:
                 # Lấy thêm thông tin strategy để biết type
                 strategy_info = db.get_strategy_details(strategy_id_redirect)
                 logger.debug(f"DEBUG (delete_stage): Fetched strategy_info: {strategy_info}")
                 if strategy_info:
                      strategy_type_redirect = strategy_info.get('strategy_type', 'unknown') # Lấy type
                      logger.debug(f"DEBUG (delete_stage): Determined strategy_type: {strategy_type_redirect}")

                      # === SỬA LẠI LOGIC XÁC ĐỊNH ENDPOINT (Như đã làm cho delete_transition) ===
                      if strategy_type_redirect == 'control':
                           redirect_endpoint = 'admin.view_strategy_stages_control'
                           list_redirect_endpoint = 'admin.view_strategies_control'
                      elif strategy_type_redirect == 'language':
                           redirect_endpoint = 'admin.view_strategy_stages_language'
                           list_redirect_endpoint = 'admin.view_strategies_language'
                      elif strategy_type_redirect == 'mainloop': # <<< THÊM CHECK MAINLOOP
                           redirect_endpoint = 'admin.view_strategy_stages_mainloop' # <<< Endpoint chi tiết mainloop
                           list_redirect_endpoint = 'admin.view_strategies_mainloop' # <<< Endpoint list mainloop
                      else: # Type không xác định
                           logger.warning(f"WARN (delete_stage): Unknown strategy type '{strategy_type_redirect}'. Cannot redirect to detail.")
                           redirect_endpoint = None
                           # Giữ list_redirect_endpoint là default (language)
                      # === KẾT THÚC SỬA LOGIC ===

                 else: # Không tìm thấy strategy details
                      logger.warning(f"WARN (delete_stage): Could not find strategy details for ID '{strategy_id_redirect}'. Cannot redirect to detail.")
                      strategy_id_redirect = None
            else: # Stage không có strategy_id
                 logger.warning(f"WARN (delete_stage): Stage '{stage_id}' has no associated strategy_id.")
                 strategy_id_redirect = None
        else: # Không tìm thấy stage
            logger.error(f"ERROR (delete_stage): Could not find stage details for ID {stage_id}. Cannot determine redirect target.")
            strategy_id_redirect = None

    except Exception as e_fetch:
        logger.error(f"ERROR (delete_stage): Exception while fetching details before delete: {e_fetch}", exc_info=True)
        strategy_id_redirect = None # Reset nếu có lỗi khi fetch

    # --- Thực hiện Xóa ---
    delete_success = False
    error_msg_delete = None
    try:
        # Hàm db.delete_stage trả về bool
        delete_success = db.delete_stage(stage_id)
        if delete_success:
            flash(f"Đã xóa stage '{stage_id}'.", 'success')
            logger.info(f"INFO (delete_stage): Successfully deleted stage {stage_id}.")
        else:
            flash(f"Xóa stage '{stage_id}' thất bại (ID không tồn tại?).", 'error')
            logger.error(f"ERROR (delete_stage): Failed to delete stage {stage_id}.")
    except psycopg2.Error as db_err: # Bắt lỗi DB cụ thể hơn nếu cần
         logger.error(f"Lỗi DB khi xóa stage {stage_id}: {db_err}", exc_info=True)
         flash(f"Lỗi CSDL khi xóa stage '{stage_id}'. Kiểm tra xem có thành phần nào khác còn phụ thuộc vào nó không.", "error")
    except Exception as e_delete:
        logger.error(f"Lỗi nghiêm trọng khi xóa stage {stage_id}: {e_delete}", exc_info=True)
        flash(f"Lỗi không mong muốn khi xóa stage: {e_delete}", "error")

    # --- Logic Chuyển hướng (Đã sửa) ---
    # Ưu tiên redirect về trang chi tiết nếu có đủ thông tin
    if strategy_id_redirect and redirect_endpoint:
        logger.info(f"INFO (delete_stage): Redirecting to detail page: {redirect_endpoint} for strategy {strategy_id_redirect}")
        return redirect(url_for(redirect_endpoint, strategy_id=strategy_id_redirect))
    else:
        # Nếu không đủ thông tin về trang chi tiết, fallback về trang danh sách PHÙ HỢP
        logger.warning(f"WARN (delete_stage): Fallback redirect needed. strategy_id={strategy_id_redirect}, type={strategy_type_redirect}, detail_endpoint={redirect_endpoint}")
        flash("Đã xóa stage. Không thể xác định chính xác trang chi tiết để quay lại, chuyển về trang danh sách.", "info")
        logger.info(f"INFO (delete_stage): Fallback redirecting to list page: {list_redirect_endpoint}")
        # <<< SỬA LẠI FALLBACK: Dùng list_redirect_endpoint đã xác định ở trên >>>
        return redirect(url_for(list_redirect_endpoint))

# --- Quản lý Transitions (Các route riêng biệt) ---

@admin_bp.route('/strategies/add', methods=['GET', 'POST'])
def add_strategy():
    """Hiển thị form và xử lý việc thêm Chiến lược mới (Language, Control, hoặc Mainloop)."""

    # Xác định strategy_type dựa trên URL (GET) hoặc form (POST)
    # Mặc định là 'language' nếu không có gì được chỉ định
    # Ưu tiên lấy từ form nếu là POST, fallback về URL args nếu GET
    if request.method == 'POST':
        strategy_type_resolved = request.form.get('strategy_type')
        # Fallback nếu type không có trong form POST (ít xảy ra)
        if not strategy_type_resolved or strategy_type_resolved not in ['language', 'control', 'mainloop']:
             strategy_type_resolved = request.args.get('type', 'language')
    else: # GET request
        strategy_type_resolved = request.args.get('type', 'language')

    # Đảm bảo strategy_type cuối cùng hợp lệ
    if strategy_type_resolved not in ['language', 'control', 'mainloop']:
        strategy_type_resolved = 'language' # Mặc định an toàn

    title = f"Thêm {strategy_type_resolved.capitalize()} Strategy Mới"

    # Lấy danh sách stages cho dropdown (cần cho cả GET và POST lỗi)
    stages = []
    try:
        # Giả sử hàm này trả về list các dict stage hoặc None nếu lỗi
        stages_result = db.get_all_stages()
        if stages_result is None:
             flash("Lỗi khi tải danh sách Stages từ CSDL.", "error")
             stages = []
        else:
            stages = stages_result
    except Exception as e:
        current_app.logger.error(f"Lỗi tải stages cho add_strategy form: {e}", exc_info=True)
        flash("Lỗi không mong muốn khi tải dữ liệu Stages.", "error")
        stages = [] # Đảm bảo stages là list rỗng nếu lỗi

    # --- Xử lý POST request ---
    if request.method == 'POST':
        # Xác định strategy_type trước tiên
        strategy_type_resolved = request.form.get('strategy_type')
        if not strategy_type_resolved or strategy_type_resolved not in ['language', 'control', 'mainloop']:
             strategy_type_resolved = request.args.get('type', 'language') # Fallback
        if strategy_type_resolved not in ['language', 'control', 'mainloop']:
             strategy_type_resolved = 'language' # Default an toàn

        title = f"Thêm {strategy_type_resolved.capitalize()} Strategy Mới" # Cập nhật title theo type đã giải quyết

        # Lấy dữ liệu từ form
        strategy_id = request.form.get('strategy_id', '').strip()
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        initial_stage_id = request.form.get('initial_stage_id') # Vẫn lấy giá trị

        # === THÊM LOG DEBUG Ở ĐÂY ===
        print(f"--- DEBUG add_strategy POST ---")
        print(f"Received strategy_id: '{strategy_id}' (Type: {type(strategy_id)})")
        print(f"Received name: '{name}' (Type: {type(name)})")
        print(f"Received initial_stage_id: '{initial_stage_id}' (Type: {type(initial_stage_id)})")
        print(f"Resolved strategy_type: '{strategy_type_resolved}' (Type: {type(strategy_type_resolved)})")
        print(f"--- End DEBUG ---")
        # === KẾT THÚC THÊM LOG DEBUG ===

        # Validate dữ liệu
        errors = []
        # Dòng kiểm tra KHÔNG có initial_stage_id
        if not strategy_id or not name or not strategy_type_resolved:
            errors.append("Strategy ID, Name, và Strategy Type (ẩn) là bắt buộc.") # Thông báo lỗi này KHÔNG bao gồm Initial Stage ID
        # Kiểm tra lại strategy_type_resolved
        if strategy_type_resolved not in ['language', 'control', 'mainloop']:
            errors.append("Strategy Type không hợp lệ.")

        # Nếu có lỗi validation
        if errors:
            # In ra lỗi để xem có khớp không
            print(f"DEBUG: Validation failed with errors: {errors}")
            for error in errors: flash(error, "warning")
            # Lấy lại stages để render form lỗi
            stages = []
            try: stages = db.get_all_stages() or []
            except Exception as e_stages: print(f"Error getting stages for error render: {e_stages}"); stages = []
            return render_template('admin_add_strategy.html',
                                   title=title + " (Lỗi)",
                                   stages=stages,
                                   strategy_type=strategy_type_resolved,
                                   current_data=request.form), 400

        # ... (Phần gọi db.add_new_strategy và xử lý kết quả giữ nguyên như phiên bản trước) ...
        try:
            success, error_msg = db.add_new_strategy(
                strategy_id=strategy_id,
                name=name,
                description=description or None,
                initial_stage_id=initial_stage_id if initial_stage_id else None,
                strategy_type=strategy_type_resolved
            )
            # ... (Xử lý success/error và redirect/render) ...
            if success:
                flash(f'Thêm chiến lược ({strategy_type_resolved}) "{name}" thành công!', 'success')
                if strategy_type_resolved == 'control': redirect_url = url_for('admin.view_strategies_control')
                elif strategy_type_resolved == 'mainloop': redirect_url = url_for('admin.view_strategies_mainloop')
                else: redirect_url = url_for('admin.view_strategies_language')
                return redirect(redirect_url)
            else:
                flash(f'Thêm chiến lược thất bại: {error_msg or "Lỗi không xác định."}', 'error')
                stages = db.get_all_stages() or []
                return render_template('admin_add_strategy.html',
                                       title=title + " (Lỗi DB)",
                                       stages=stages,
                                       strategy_type=strategy_type_resolved,
                                       current_data=request.form)
        except Exception as e:
            current_app.logger.error(f"Lỗi nghiêm trọng khi gọi db.add_new_strategy: {e}", exc_info=True)
            flash(f"Lỗi không mong muốn khi thêm chiến lược: {e}", "error")
            stages = db.get_all_stages() or []
            return render_template('admin_add_strategy.html',
                                   title=title + " (Lỗi Exception)",
                                   stages=stages,
                                   strategy_type=strategy_type_resolved,
                                   current_data=request.form)

    # --- Xử lý GET request (giữ nguyên) ---
    else: # GET request
        stages = []
        try: stages = db.get_all_stages() or []
        except Exception: flash("Lỗi tải stages", "error"); stages = []
        return render_template('admin_add_strategy.html',
                               title=title,
                               stages=stages,
                               strategy_type=strategy_type_resolved)

@admin_bp.route('/strategies/<strategy_id>/edit', methods=['GET', 'POST'])
def edit_strategy(strategy_id):
    # Lấy strategy details (bao gồm cả strategy_type)
    strategy = db.get_strategy_details(strategy_id)
    if not strategy:
        flash(f"Không tìm thấy strategy ID {strategy_id}.", "error")
        # Fallback redirect thông minh hơn dựa trên type nếu có thể, tạm thời về language list
        # (Logic redirect này có thể cần xem lại nếu strategy không tồn tại)
        strategy_type_guess = request.args.get('type', 'language') # Đoán type từ URL nếu có
        list_redirect_endpoint = 'admin.view_strategies_control' if strategy_type_guess == 'control' else \
                                 'admin.view_strategies_mainloop' if strategy_type_guess == 'mainloop' else \
                                 'admin.view_strategies_language'
        return redirect(url_for(list_redirect_endpoint))

    # === THAY ĐỔI CÁCH LẤY STAGES ===
    # Lấy các stage chỉ thuộc về strategy này
    strategy_specific_stages = [] # Khởi tạo list rỗng
    try:
        # Gọi hàm lấy stage theo strategy_id
        strategy_specific_stages = db.get_stages_for_strategy(strategy_id) or []
        if strategy_specific_stages is None: # Phân biệt lỗi DB và list rỗng
             flash(f"Lỗi khi tải danh sách Stages cho strategy {strategy_id}.", "error")
             strategy_specific_stages = []
    except Exception as e_stages:
        current_app.logger.error(f"Lỗi tải stages cho edit_strategy {strategy_id}: {e_stages}", exc_info=True)
        flash("Lỗi không mong muốn khi tải dữ liệu Stages.", "error")
        # strategy_specific_stages vẫn là list rỗng

    current_strategy_type = strategy.get('strategy_type', 'language') # Lấy type để redirect sau POST

    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        initial_stage_id = request.form.get('initial_stage_id') # Lấy stage ID đã chọn

        # Validate
        if not name: # Chỉ cần Name là bắt buộc khi sửa (Initial Stage có thể để trống)
             flash("Name là bắt buộc.", "warning")
             # Render lại form lỗi, truyền lại strategy_specific_stages
             return render_template('admin_edit_strategy.html', title=f"Sửa Chiến lược {strategy_id} (Lỗi)",
                                    strategy=strategy,
                                    stages=strategy_specific_stages, # <<< Truyền list stage đúng
                                    current_data=request.form), 400

        # Gọi hàm db.update_strategy
        # Đảm bảo hàm update xử lý initial_stage_id rỗng thành NULL
        success, error_msg = db.update_strategy(
            strategy_id,
            name,
            description or None,
            initial_stage_id if initial_stage_id else None # Chuyển rỗng thành None
        )

        if success:
            flash('Cập nhật chiến lược thành công!', 'success')
            # Redirect đúng trang danh sách dựa trên type
            list_redirect_endpoint = 'admin.view_strategies_control' if current_strategy_type == 'control' else \
                                     'admin.view_strategies_mainloop' if current_strategy_type == 'mainloop' else \
                                     'admin.view_strategies_language'
            return redirect(url_for(list_redirect_endpoint))
        else:
            flash(f'Cập nhật chiến lược thất bại: {error_msg or "Lỗi."}', 'error')
            # Render lại form lỗi, truyền lại strategy_specific_stages
            return render_template('admin_edit_strategy.html', title=f"Sửa Chiến lược {strategy_id} (Lỗi DB)",
                                   strategy=strategy,
                                   stages=strategy_specific_stages, # <<< Truyền list stage đúng
                                   current_data=request.form)

    # --- Xử lý GET request ---
    # strategy và strategy_specific_stages đã được lấy ở trên
    return render_template('admin_edit_strategy.html',
                           title=f"Sửa Chiến lược {strategy_id}",
                           strategy=strategy,
                           stages=strategy_specific_stages)

# --- Sửa Route Xóa Strategy ---
@admin_bp.route('/strategies/<strategy_id>/delete', methods=['POST'])
def delete_strategy(strategy_id):
    """Xử lý xóa chiến lược và redirect về đúng trang danh sách."""
    logger = current_app.logger if current_app else print
    strategy_type_redirect = 'language' # Default redirect về language nếu không lấy được type

    # Lấy type TRƯỚC KHI XÓA để redirect đúng
    try:
        strategy_details = db.get_strategy_details(strategy_id)
        if strategy_details and strategy_details.get('strategy_type'):
            strategy_type_redirect = strategy_details.get('strategy_type')
        else:
            logger.warning(f"Could not get details or type for strategy {strategy_id} before deleting. Defaulting redirect type to '{strategy_type_redirect}'.")
    except Exception as e_fetch:
         logger.error(f"Error fetching strategy details before delete for {strategy_id}: {e_fetch}", exc_info=True)
         # Giữ nguyên default redirect type

    logger.info(f"Attempting to delete strategy {strategy_id} (Type determined as: {strategy_type_redirect})")

    # Thực hiện xóa
    try:
        # Hàm delete_strategy nên trả về tuple (success, error_msg)
        success, error_msg = db.delete_strategy(strategy_id)
        if success:
            flash(f"Đã xóa chiến lược ID '{strategy_id}'.", 'success')
            logger.info(f"Successfully deleted strategy {strategy_id}.")
        else:
            flash(f"Xóa chiến lược ID '{strategy_id}' thất bại: {error_msg or 'ID không tồn tại?'}", 'error')
            logger.error(f"Failed to delete strategy {strategy_id}: {error_msg}")
    except Exception as e_delete:
        logger.error(f"Lỗi nghiêm trọng khi xóa strategy {strategy_id}: {e_delete}", exc_info=True)
        flash(f"Đã xảy ra lỗi không mong muốn khi xóa chiến lược: {e_delete}", "error")

    # === SỬA LẠI LOGIC REDIRECT ===
    # Redirect về trang danh sách tương ứng dựa trên type đã lấy được TRƯỚC KHI XÓA
    if strategy_type_redirect == 'control':
         redirect_url = url_for('admin.view_strategies_control')
    elif strategy_type_redirect == 'mainloop': # <<< THÊM CHECK MAINLOOP
         redirect_url = url_for('admin.view_strategies_mainloop')
    else: # Default là language (hoặc unknown)
         redirect_url = url_for('admin.view_strategies_language')

    logger.info(f"Redirecting to {redirect_url} after deleting strategy {strategy_id}")
    return redirect(redirect_url)

# --- Route MỚI cho Danh sách Chiến lược Hội thoại ---
@admin_bp.route('/strategies/language')
def view_strategies_language():
    """Hiển thị danh sách các chiến lược loại 'language'."""
    title = "Quản lý Chiến lược Hội thoại"
    language_strategies = []
    if not db:
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
    else:
        try:
            # Gọi hàm DB với bộ lọc type='language'
            language_strategies = db.get_all_strategies(strategy_type_filter='language')
            if language_strategies is None:
                flash("Lỗi khi tải danh sách chiến lược hội thoại.", "error")
                language_strategies = []
        except Exception as e:
            print(f"Lỗi load language strategies: {e}")
            flash("Lỗi không mong muốn khi tải dữ liệu.", "error")
            language_strategies = []
    # Render template MỚI
    return render_template('admin_strategies_language.html',
                           title=title,
                           strategies=language_strategies) # Đổi tên biến truyền vào thành 'strategies'

# --- ĐỔI TÊN Route và Hàm cho Danh sách Chiến lược Điều khiển ---

@admin_bp.route('/ai-playground', methods=['GET', 'POST'])
def ai_playground():
    """Trang tiện ích để chat trực tiếp với AI."""
    personas = []
    ai_response = None
    user_prompt = ""
    selected_persona_id = ""
    error_message = None

    # Luôn lấy danh sách persona cho dropdown
    try:
        personas = db.get_all_personas() or []
    except Exception as e:
        print(f"Lỗi khi lấy danh sách personas cho playground: {e}")
        flash("Không thể tải danh sách AI Personas.", "error")
        personas = []

    if request.method == 'POST':
        user_prompt = request.form.get('user_prompt', '').strip()
        selected_persona_id = request.form.get('persona_id', '').strip()
        persona_id_to_use = selected_persona_id if selected_persona_id else None # Dùng None nếu chọn default

        if not user_prompt:
            flash("Vui lòng nhập yêu cầu/prompt.", "warning")
        else:
            try:
                # Gọi hàm AI service tổng quát
                ai_response_text, status = ai_service.call_generative_model(
                    prompt=user_prompt,
                    persona_id=persona_id_to_use
                )
                if status == 'success':
                    ai_response = ai_response_text
                else:
                    error_message = f"AI Error: {status}"
                    if ai_response_text: error_message += f"\nDetails: {ai_response_text}"
                    ai_response = None
                    flash(f"AI không thể xử lý yêu cầu (Status: {status}).", "error")

            except Exception as e:
                print(f"Lỗi nghiêm trọng khi gọi AI trong playground: {e}")
                flash(f"Lỗi không mong muốn khi gọi AI: {e}", "error")
                error_message = f"Server Error: {e}"
                ai_response = None

    # Render template cho cả GET và POST
    return render_template('admin_ai_playground.html',
                           title="AI Playground",
                           personas=personas,
                           user_prompt=user_prompt,
                           ai_response=ai_response,
                           error_message=error_message,
                           selected_persona_id=selected_persona_id)

@admin_bp.route('/history')
def view_history():
    """Hiển thị lịch sử tương tác với phân trang."""
    logger = current_app.logger # Lấy logger
    page = request.args.get('page', 1, type=int)
    per_page = 30 # Hoặc lấy từ config
    history_entries = None
    pagination = None

    if not db:
        flash("Lỗi DB.", "error")
    else:
        try:
            # Gọi hàm DB để lấy dữ liệu
            history_entries, pagination = db.get_interaction_history(page=page, per_page=per_page)

            # === THÊM LOG DEBUG Ở ĐÂY ===
            logger.debug(f"DEBUG (view_history): Called db.get_interaction_history for page {page}.")
            logger.debug(f"DEBUG (view_history): Fetched history_entries type: {type(history_entries)}, length: {len(history_entries) if history_entries is not None else 'None'}")
            # In ra một vài entry đầu tiên để kiểm tra nội dung (nếu có)
            if history_entries:
                 logger.debug(f"DEBUG (view_history): First history entry (sample): {history_entries[0]}")
            logger.debug(f"DEBUG (view_history): Fetched pagination data: {pagination}")
            # ===========================

        except Exception as e:
            logger.error(f"Lỗi khi lấy lịch sử tương tác: {e}", exc_info=True)
            flash(f"Lỗi khi tải lịch sử: {e}", "error")
            history_entries = None # Đảm bảo là None nếu lỗi
            pagination = None
    logger.debug(f"--- DEBUG History Data Check (After SQL Fix) ---") # Thêm chữ để phân biệt
    logger.debug(f"Fetched history_entries type: {type(history_entries)}")
    if history_entries is not None:
        logger.debug(f"Fetched history_entries length: {len(history_entries)}")
        if history_entries: # Log bản ghi đầu tiên nếu list không rỗng
            logger.debug(f"First history entry data: {history_entries[0]}")
        else:
            logger.debug("history_entries list is empty.")
    else:
        logger.debug("history_entries is None")
    logger.debug(f"Fetched pagination data: {pagination}")
    logger.debug(f"--- END DEBUG History Data Check (After SQL Fix) ---")
    # Truyền dữ liệu vào template
    return render_template('admin_history.html',
                           title="Lịch sử Tương tác",
                           history_entries=history_entries, # Có thể là None hoặc list
                           pagination=pagination)

@admin_bp.route('/_get_templates') # Route nội bộ (ví dụ)
def get_templates_for_select():
     # Hàm này có thể được gọi bằng AJAX để cập nhật dropdown
     templates = db.get_all_template_refs()
     # Trả về JSON
     from flask import jsonify
     return jsonify(templates or [])

@admin_bp.route('/_get_stages')
def get_stages_for_select():
     
     stages = db.get_all_stages() # Giả sử trả về list of dicts [{stage_id, name}]
     from flask import jsonify
     return jsonify(stages or [])

# =============================================
# === QUẢN LÝ AI PERSONAS ===
# =============================================
@admin_bp.route('/ai-personas')
def view_personas():
    """Hiển thị danh sách các AI Personas với phân trang."""
    title = "Quản lý AI Personas"
    personas = []
    pagination = None # <<< Biến phân trang

    if not db:
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
    else:
        try:
            # Lấy page từ URL
            page = request.args.get('page', 1, type=int)
            if page < 1: page = 1
            print(f"DEBUG (view_personas): Requesting page {page}")

            # Gọi hàm DB mới để lấy dữ liệu trang và tổng số
            personas, total_items = db.get_all_personas(page=page, per_page=PER_PAGE_PERSONAS)

            if personas is None or total_items is None:
                 flash("Lỗi khi tải danh sách AI Personas từ CSDL.", "error")
                 personas = []; total_items = 0
                 pagination = None
            else:
                 # Tính toán thông tin phân trang
                 if total_items > 0:
                     total_pages = ceil(total_items / PER_PAGE_PERSONAS)
                     if page > total_pages and total_pages > 0: page = total_pages
                     pagination = {
                        'page': page, 'per_page': PER_PAGE_PERSONAS, 'total_items': total_items,
                        'total_pages': total_pages, 'has_prev': page > 1, 'has_next': page < total_pages,
                        'prev_num': page - 1 if page > 1 else None,
                        'next_num': page + 1 if page < total_pages else None
                     }
                 else:
                     pagination = {'page': 1, 'per_page': PER_PAGE_PERSONAS, 'total_items': 0, 'total_pages': 0, 'has_prev': False, 'has_next': False}
                 print(f"DEBUG (view_personas): Calculated pagination = {pagination}")

        except Exception as e:
            print(f"Lỗi nghiêm trọng khi load personas: {e}")
            flash("Lỗi không mong muốn khi tải AI Personas.", "error")
            personas = []; pagination = None

    # Truyền personas (của trang hiện tại) và pagination vào template
    return render_template('admin_personas.html',
                           title=title,
                           personas=personas,
                           pagination=pagination) 


@admin_bp.route('/ai-personas/add', methods=['GET', 'POST'])
def add_persona():
    """Thêm AI Persona mới."""
    if request.method == 'POST':
        persona_id = request.form.get('persona_id', '').strip()
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        base_prompt = request.form.get('base_prompt', '').strip()
        model_name = request.form.get('model_name', '').strip()
        generation_config_str = request.form.get('generation_config', '').strip()

        if not persona_id or not name or not base_prompt:
             flash("Persona ID, Name, và Base Prompt là bắt buộc.", "warning")
             return render_template('admin_add_ai_persona.html', title="Thêm AI Persona", current_data=request.form), 400

        # Validate JSON cơ bản (nếu người dùng nhập)
        gen_config_json = None
        if generation_config_str:
            try:
                gen_config_json = json.loads(generation_config_str)
            except json.JSONDecodeError:
                flash("Generation Config không phải là JSON hợp lệ. Vui lòng nhập đúng định dạng hoặc để trống.", "warning")
                return render_template('admin_add_ai_persona.html', title="Thêm AI Persona", current_data=request.form), 400

        try:
            success = db.add_new_persona(persona_id, name, description, base_prompt,
                                         model_name or None, # Chuyển chuỗi rỗng thành None
                                         generation_config_str or None) # Truyền chuỗi JSON (hoặc None) vào hàm DB
            if success:
                flash(f"Thêm persona '{persona_id}' thành công!", 'success')
                return redirect(url_for('admin.view_personas'))
            else:
                flash(f"Thêm persona '{persona_id}' thất bại (ID hoặc Name đã tồn tại?).", 'error')
                return render_template('admin_add_ai_persona.html', title="Thêm AI Persona", current_data=request.form)
        except Exception as e:
            print(f"Lỗi nghiêm trọng khi thêm persona: {e}")
            flash(f"Lỗi không mong muốn khi thêm persona: {e}", "error")
            return render_template('admin_add_ai_persona.html', title="Thêm AI Persona", current_data=request.form)

    # GET request
    return render_template('admin_add_ai_persona.html', title="Thêm AI Persona")


@admin_bp.route('/ai-personas/<persona_id>/edit', methods=['GET', 'POST'])
def edit_persona(persona_id):
    """Sửa AI Persona."""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        base_prompt = request.form.get('base_prompt', '').strip()
        model_name = request.form.get('model_name', '').strip()
        generation_config_str = request.form.get('generation_config', '').strip()

        if not name or not base_prompt: # ID không đổi, chỉ cần name và base_prompt
             flash("Name và Base Prompt là bắt buộc.", "warning")
             # Lấy lại persona cũ để hiển thị form
             persona = db.get_persona_details(persona_id)
             if not persona: return redirect(url_for('admin.view_personas')) # Should not happen if GET worked
             # Truyền lại request.form để giữ giá trị người dùng vừa nhập sai
             return render_template('admin_edit_ai_persona.html', title=f"Sửa AI Persona '{persona_id}'", persona=persona, current_data=request.form), 400

        # Validate JSON
        gen_config_json = None
        if generation_config_str:
            try:
                gen_config_json = json.loads(generation_config_str)
            except json.JSONDecodeError:
                flash("Generation Config không phải là JSON hợp lệ. Vui lòng nhập đúng định dạng hoặc để trống.", "warning")
                persona = db.get_persona_details(persona_id)
                if not persona: return redirect(url_for('admin.view_personas'))
                return render_template('admin_edit_ai_persona.html', title=f"Sửa AI Persona '{persona_id}'", persona=persona, current_data=request.form), 400

        try:
            success = db.update_persona(persona_id, name, description, base_prompt,
                                        model_name or None, generation_config_str or None)
            if success:
                flash(f"Cập nhật persona '{persona_id}' thành công!", 'success')
                return redirect(url_for('admin.view_personas'))
            else:
                flash(f"Cập nhật persona '{persona_id}' thất bại (Name đã tồn tại?).", 'error')
                # Lấy lại persona cũ và hiển thị lỗi
                persona = db.get_persona_details(persona_id)
                if not persona: return redirect(url_for('admin.view_personas'))
                return render_template('admin_edit_ai_persona.html', title=f"Sửa AI Persona '{persona_id}'", persona=persona, current_data=request.form)
        except Exception as e:
            print(f"Lỗi nghiêm trọng khi cập nhật persona {persona_id}: {e}")
            flash(f"Lỗi không mong muốn khi cập nhật persona: {e}", "error")
            persona = db.get_persona_details(persona_id)
            if not persona: return redirect(url_for('admin.view_personas'))
            return render_template('admin_edit_ai_persona.html', title=f"Sửa AI Persona '{persona_id}'", persona=persona, current_data=request.form)


    # GET request
    persona = db.get_persona_details(persona_id)
    if not persona:
        flash(f"Không tìm thấy persona ID '{persona_id}'.", "error")
        return redirect(url_for('admin.view_personas'))
    return render_template('admin_edit_ai_persona.html', title=f"Sửa AI Persona '{persona_id}'", persona=persona)


@admin_bp.route('/ai-personas/<persona_id>/delete', methods=['POST'])
def delete_persona(persona_id):
    """Xóa AI Persona."""
    try:
        success = db.delete_persona(persona_id)
        if success:
            flash(f"Đã xóa persona '{persona_id}'.", 'success')
        else:
            flash(f"Xóa persona '{persona_id}' thất bại (ID không tồn tại?).", 'error')
    except Exception as e:
         print(f"Lỗi nghiêm trọng khi xóa persona {persona_id}: {e}")
         flash(f"Lỗi không mong muốn khi xóa persona: {e}", "error")
    return redirect(url_for('admin.view_personas'))


# =============================================
# === QUẢN LÝ PROMPT TEMPLATES ===
# =============================================
@admin_bp.route('/prompt-templates')
def view_prompt_templates():
    """Hiển thị danh sách các Prompt Templates với phân trang."""
    title = "Quản lý Prompt Templates"
    templates = []
    pagination = None # <<< Biến phân trang

    if not db:
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
    else:
        try:
            # Lấy page từ URL
            page = request.args.get('page', 1, type=int)
            if page < 1: page = 1
            print(f"DEBUG (view_prompt_templates): Requesting page {page}")

            # Gọi hàm DB mới để lấy dữ liệu trang và tổng số
            templates, total_items = db.get_all_prompt_templates(page=page, per_page=PER_PAGE_PROMPT_TEMPLATES)

            if templates is None or total_items is None:
                 flash("Lỗi khi tải danh sách Prompt Templates từ CSDL.", "error")
                 templates = []; total_items = 0
                 pagination = None
            else:
                 # Tính toán thông tin phân trang
                 if total_items > 0:
                     total_pages = ceil(total_items / PER_PAGE_PROMPT_TEMPLATES)
                     if page > total_pages and total_pages > 0: page = total_pages
                     pagination = {
                        'page': page, 'per_page': PER_PAGE_PROMPT_TEMPLATES, 'total_items': total_items,
                        'total_pages': total_pages, 'has_prev': page > 1, 'has_next': page < total_pages,
                        'prev_num': page - 1 if page > 1 else None,
                        'next_num': page + 1 if page < total_pages else None
                     }
                 else:
                     pagination = {'page': 1, 'per_page': PER_PAGE_PROMPT_TEMPLATES, 'total_items': 0, 'total_pages': 0, 'has_prev': False, 'has_next': False}
                 print(f"DEBUG (view_prompt_templates): Calculated pagination = {pagination}")

        except Exception as e:
            print(f"Lỗi nghiêm trọng khi load prompt templates: {e}")
            flash("Lỗi không mong muốn khi tải Prompt Templates.", "error")
            templates = []; pagination = None

    # Truyền templates (của trang hiện tại) và pagination vào template
    return render_template('admin_prompt_templates.html',
                           title=title,
                           templates=templates,
                           pagination=pagination) # <<< Truyền pagination


@admin_bp.route('/prompt-templates/add', methods=['GET', 'POST'])
def add_prompt_template():
    """Thêm Prompt Template mới."""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        task_type = request.form.get('task_type', '').strip()
        template_content = request.form.get('template_content', '').strip()

        if not name or not task_type or not template_content:
             flash("Name, Task Type, và Template Content là bắt buộc.", "warning")
             return render_template('admin_add_prompt_template.html', title="Thêm Prompt Template",
                                    task_types=PROMPT_TASK_TYPES, current_data=request.form), 400
        if task_type not in PROMPT_TASK_TYPES:
             flash("Task Type không hợp lệ.", "warning")
             return render_template('admin_add_prompt_template.html', title="Thêm Prompt Template",
                                    task_types=PROMPT_TASK_TYPES, current_data=request.form), 400

        try:
            success = db.add_new_prompt_template(name, task_type, template_content)
            if success:
                flash(f"Thêm prompt template '{name}' thành công!", 'success')
                return redirect(url_for('admin.view_prompt_templates'))
            else:
                flash(f"Thêm prompt template '{name}' thất bại (Name đã tồn tại?).", 'error')
                return render_template('admin_add_prompt_template.html', title="Thêm Prompt Template",
                                       task_types=PROMPT_TASK_TYPES, current_data=request.form)
        except Exception as e:
            print(f"Lỗi nghiêm trọng khi thêm prompt template: {e}")
            flash(f"Lỗi không mong muốn khi thêm prompt template: {e}", "error")
            return render_template('admin_add_prompt_template.html', title="Thêm Prompt Template",
                                   task_types=PROMPT_TASK_TYPES, current_data=request.form)

    # GET request
    return render_template('admin_add_prompt_template.html', title="Thêm Prompt Template", task_types=PROMPT_TASK_TYPES)


@admin_bp.route('/prompt-templates/<int:prompt_template_id>/edit', methods=['GET', 'POST'])
def edit_prompt_template(prompt_template_id):
    """Sửa Prompt Template."""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        task_type = request.form.get('task_type', '').strip()
        template_content = request.form.get('template_content', '').strip()

        if not name or not task_type or not template_content:
             flash("Name, Task Type, và Template Content là bắt buộc.", "warning")
             template = db.get_prompt_template_details(prompt_template_id) # Lấy lại để hiển thị form
             if not template: return redirect(url_for('admin.view_prompt_templates'))
             return render_template('admin_edit_prompt_template.html', title=f"Sửa Prompt Template {prompt_template_id}",
                                    template=template, task_types=PROMPT_TASK_TYPES, current_data=request.form), 400
        if task_type not in PROMPT_TASK_TYPES:
             flash("Task Type không hợp lệ.", "warning")
             template = db.get_prompt_template_details(prompt_template_id)
             if not template: return redirect(url_for('admin.view_prompt_templates'))
             return render_template('admin_edit_prompt_template.html', title=f"Sửa Prompt Template {prompt_template_id}",
                                    template=template, task_types=PROMPT_TASK_TYPES, current_data=request.form), 400

        try:
            success = db.update_prompt_template(prompt_template_id, name, task_type, template_content)
            if success:
                flash(f"Cập nhật prompt template '{name}' thành công!", 'success')
                return redirect(url_for('admin.view_prompt_templates'))
            else:
                 flash(f"Cập nhật prompt template '{name}' thất bại (Name đã tồn tại?).", 'error')
                 template = db.get_prompt_template_details(prompt_template_id) # Lấy lại để hiển thị form
                 if not template: return redirect(url_for('admin.view_prompt_templates'))
                 return render_template('admin_edit_prompt_template.html', title=f"Sửa Prompt Template {prompt_template_id}",
                                        template=template, task_types=PROMPT_TASK_TYPES, current_data=request.form)
        except Exception as e:
            print(f"Lỗi nghiêm trọng khi cập nhật prompt template {prompt_template_id}: {e}")
            flash(f"Lỗi không mong muốn khi cập nhật prompt template: {e}", "error")
            template = db.get_prompt_template_details(prompt_template_id)
            if not template: return redirect(url_for('admin.view_prompt_templates'))
            return render_template('admin_edit_prompt_template.html', title=f"Sửa Prompt Template {prompt_template_id}",
                                   template=template, task_types=PROMPT_TASK_TYPES, current_data=request.form)


    # GET request
    template = db.get_prompt_template_details(prompt_template_id)
    if not template:
        flash(f"Không tìm thấy prompt template ID {prompt_template_id}.", "error")
        return redirect(url_for('admin.view_prompt_templates'))
    return render_template('admin_edit_prompt_template.html', title=f"Sửa Prompt Template {prompt_template_id}",
                           template=template, task_types=PROMPT_TASK_TYPES)


@admin_bp.route('/prompt-templates/<int:prompt_template_id>/delete', methods=['POST'])
def delete_prompt_template(prompt_template_id):


    """Xóa Prompt Template."""
    try:
        success = db.delete_prompt_template(prompt_template_id)
        if success:
            flash(f"Đã xóa prompt template ID {prompt_template_id}.", 'success')
        else:
            flash(f"Xóa prompt template ID {prompt_template_id} thất bại (ID không tồn tại?).", 'error')
    except Exception as e:
         print(f"Lỗi nghiêm trọng khi xóa prompt template {prompt_template_id}: {e}")
         flash(f"Lỗi không mong muốn khi xóa prompt template: {e}", "error")
    return redirect(url_for('admin.view_prompt_templates'))



@admin_bp.route('/scheduled-jobs')
def view_scheduled_jobs():
    """
    Hiển thị trang quản lý cấu hình job định kỳ và trạng thái live của chúng.
    """
    title = "Quản lý Cấu hình Tác vụ Định Kỳ"
    db_jobs_config = []   # Danh sách cấu hình từ DB
    live_job_statuses = [] # Danh sách trạng thái live để hiển thị ở bảng 2
    pending_counts = {}   # Đếm pending cho suggestion_job

    if not db:
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
    else:
        try:
            # 1. Lấy danh sách cấu hình từ bảng scheduled_jobs
            db_jobs_config = db.get_all_job_configs() or []
            if db_jobs_config is None: # Phân biệt lỗi DB và không có job
                 flash("Lỗi khi tải danh sách cấu hình jobs từ Database.", "error")
                 db_jobs_config = [] # Gán list rỗng nếu lỗi

            # 2. Lấy thời gian chạy thực tế từ bảng apscheduler_jobs
            live_run_times = _get_live_next_run_times() # Dùng lại hàm helper đã có

            # 3. Tạo danh sách trạng thái live cho Bảng 2
            server_tz = _get_configured_timezone() # Dùng hàm helper lấy timezone

            # Chỉ xử lý trạng thái live cho các job có trong cấu hình
            configured_job_ids = {job['job_id'] for job in db_jobs_config}

            for job_id, next_run_timestamp in live_run_times.items():
                # Chỉ quan tâm đến job ID có trong cấu hình
                if job_id in configured_job_ids:
                    status_info = {'id': job_id, 'next_run_time_str': 'N/A', 'status': 'Unknown'}
                    if next_run_timestamp is not None:
                        try:
                            utc_dt = datetime.fromtimestamp(next_run_timestamp, tz=timezone.utc)
                            local_dt = utc_dt.astimezone(server_tz)
                            status_info['next_run_time_str'] = local_dt.strftime('%Y-%m-%d %H:%M:%S %z')
                            status_info['status'] = 'Scheduled' # Hoặc 'Running' nếu có thể xác định
                        except Exception as fmt_err:
                            print(f"Error formatting live timestamp for {job_id}: {fmt_err}")
                            status_info['next_run_time_str'] = 'Lỗi Format'
                    else:
                        # Timestamp là None có nghĩa là job đang PAUSED trong scheduler
                        status_info['next_run_time_str'] = '---'
                        status_info['status'] = 'Paused'
                    live_job_statuses.append(status_info)

            # Thêm các job có config nhưng không có trong apscheduler_jobs (Not Scheduled)
            live_job_ids_found = {s['id'] for s in live_job_statuses}
            for cfg_job in db_jobs_config:
                 cfg_job_id = cfg_job['job_id']
                 if cfg_job_id not in live_job_ids_found:
                      live_job_statuses.append({
                           'id': cfg_job_id,
                           'next_run_time_str': '---',
                           'status': 'Not Scheduled' if not cfg_job.get('is_enabled') else 'Error/Not Found'
                      })

            # Sắp xếp danh sách trạng thái live theo ID (tùy chọn)
            live_job_statuses.sort(key=lambda x: x['id'])


            # 4. Logic đếm pending cho suggestion_job (giữ nguyên và đảm bảo đúng)
            for job_conf in db_jobs_config:
                if job_conf.get('job_id') == 'suggestion_job':
                    try:
                        last_id = db.get_task_state('suggestion_job') or 0
                        # Đảm bảo dùng đúng filter bao gồm cả sim status
                        status_filter = current_app.config.get(
                            'STATUS_TO_ANALYZE_SUGGEST',
                            ['success_ai', 'success_ai_sim_A', 'success_ai_sim_B'] # Default đúng
                        )
                        count = db.get_pending_suggestion_interaction_count(last_id, status_filter)
                        pending_counts['suggestion_job'] = count if count is not None else 'Lỗi'
                    except Exception as count_err:
                        print(f"Lỗi khi đếm pending items cho suggestion_job: {count_err}")
                        pending_counts['suggestion_job'] = 'Lỗi'
                    break # Chỉ cần đếm 1 lần

        except Exception as e:
            print(f"Lỗi nghiêm trọng khi tải dữ liệu jobs: {e}")
            flash("Lỗi không mong muốn khi tải dữ liệu trang.", "error")
            db_jobs_config, live_job_statuses = [], [] # Reset về rỗng khi lỗi

    # Render template, truyền cả hai danh sách
    return render_template('admin_scheduled_jobs.html',
                           title=title,
                           jobs_config=db_jobs_config,       # <<< Danh sách cấu hình
                           live_statuses=live_job_statuses, # <<< Danh sách trạng thái live
                           pending_counts=pending_counts)   # <<< Số lượng chờ xử lý

# Trong file: hpt2/app/admin_routes.py
# ... (import ...)

# Biến hằng số chứa đường dẫn hàm mô phỏng (Đảm bảo đã định nghĩa)
SIMULATION_FUNCTION_PATH = 'app.background_tasks.run_ai_conversation_simulation'
# Danh sách các tác vụ nền (Đảm bảo đã định nghĩa)
AVAILABLE_SCHEDULED_TASKS = {
    'Phân tích & Đề xuất AI': 'app.background_tasks.analyze_interactions_and_suggest',
    'Tự động Duyệt Tất Cả Đề Xuất': 'app.background_tasks.approve_all_suggestions_task',
    'Chạy Mô phỏng Hội thoại AI': 'app.background_tasks.run_ai_conversation_simulation',
}
AVAILABLE_SCHEDULED_TASKS_LIST = sorted(AVAILABLE_SCHEDULED_TASKS.items())

@admin_bp.route('/scheduled-jobs/add', methods=['GET', 'POST'])
def add_scheduled_job():
    title = "Thêm Scheduled Job Mới"
    cancel_url = url_for('admin.view_scheduled_jobs')
    logger = current_app.logger

    # --- Lấy dữ liệu cho các Dropdown (cho cả GET và POST lỗi) ---
    valid_trigger_types = ['interval', 'date', 'cron']
    saved_simulation_configs = []
    try:
        configs_from_db, _ = db.get_all_simulation_configs(page=1, per_page=10000)
        if configs_from_db:
            saved_simulation_configs = sorted(configs_from_db, key=lambda x: x.get('config_name', ''))
    except Exception as e:
        logger.error(f"Lỗi tải dropdown data cho add_scheduled_job: {e}", exc_info=True)
        flash("Lỗi tải dữ liệu Cấu hình Mô phỏng cho form.", "error")
        # Không cần gán lại [], vì đã khởi tạo ở trên

    if request.method == 'POST':
        current_data = request.form.to_dict()
        # === BẮT ĐẦU KHỐI TRY LỚN ===
        try:
            # Lấy các trường form cơ bản
            job_id = request.form.get('job_id', '').strip()
            job_function_path = request.form.get('job_function_path')
            trigger_type = request.form.get('trigger_type')
            trigger_args_str = request.form.get('trigger_args_str', '{}').strip()
            description = request.form.get('description', '').strip()
            is_enabled = request.form.get('enabled') == 'on' # <<< Đã sửa ở bước trước

            # Validate cơ bản
            errors = []
            if not job_id: errors.append("Job ID là bắt buộc.")
            if not job_function_path: errors.append("Function Path là bắt buộc.")
            if not trigger_type: errors.append("Trigger Type là bắt buộc.")
            if not trigger_args_str: errors.append("Trigger Args là bắt buộc.")
            try:
                trigger_args_dict = json.loads(trigger_args_str); assert isinstance(trigger_args_dict, dict)
            except: errors.append("Trigger Args JSON không hợp lệ.")

            job_args_str_final = None

            # KIỂM TRA FUNCTION PATH ĐỂ XỬ LÝ JOB ARGS
            if job_function_path == SIMULATION_FUNCTION_PATH:
                config_id_str = request.form.get('simulation_config_id')
                if not config_id_str:
                    errors.append("Vui lòng chọn một Cấu hình Mô phỏng đã lưu.")
                else:
                    try:
                        config_id = int(config_id_str)
                        config_details = db.get_simulation_config(config_id)
                        if not config_details:
                            errors.append(f"Không tìm thấy Cấu hình Mô phỏng ID {config_id}.")
                        else:
                            job_args = {
                                'persona_a_id': config_details.get('persona_a_id'),
                                'persona_b_id': config_details.get('persona_b_id'),
                                'log_account_id_a': config_details.get('log_account_id_a'),
                                'log_account_id_b': config_details.get('log_account_id_b'),
                                'strategy_id': config_details.get('strategy_id'),
                                'max_turns': config_details.get('max_turns', 5),
                                'starting_prompt': config_details.get('starting_prompt'),
                                'sim_thread_id_base': f"scheduled_sim_{config_id}",
                                'sim_goal': config_details.get('simulation_goal') or f"scheduled_run_{config_id}"
                            }
                            if not all(job_args[k] for k in ['persona_a_id', 'persona_b_id', 'log_account_id_a', 'log_account_id_b', 'strategy_id']):
                                errors.append(f"Cấu hình Mô phỏng ID {config_id} thiếu thông tin.")
                            else:
                                job_args_str_final = json.dumps(job_args)
                    except ValueError:
                        errors.append("Lỗi định dạng ID Cấu hình Mô phỏng.")
                    except Exception as e_fetch:
                        errors.append(f"Lỗi khi lấy chi tiết Cấu hình Mô phỏng: {e_fetch}")
                        logger.error(f"Lỗi khi lấy chi tiết Cấu hình Mô phỏng: {e_fetch}", exc_info=True) # Ghi log lỗi chi tiết
            else: # Nếu không phải hàm simulation
                job_args_str_textarea = request.form.get('job_args_str', '{}').strip()
                if job_args_str_textarea and job_args_str_textarea.strip() != '{}':
                    try:
                        job_args_dict = json.loads(job_args_str_textarea); assert isinstance(job_args_dict, dict)
                        job_args_str_final = job_args_str_textarea
                    except: errors.append("Job Args JSON không hợp lệ.")

            # Nếu có lỗi validation
            if errors:
                for error in errors: flash(error, "warning")
                return render_template('admin_add_scheduled_job.html',
                                       title=title + " (Lỗi)", cancel_url=cancel_url,
                                       available_tasks=AVAILABLE_SCHEDULED_TASKS_LIST, # <<< Sửa lại tên biến
                                       valid_trigger_types=valid_trigger_types,
                                       saved_simulation_configs=saved_simulation_configs,
                                       current_data=current_data), 400

            # Gọi hàm DB add_job_config (Bên trong khối try riêng)
            # === KHỐI TRY NHỎ CHO DB CALL ===
            try:
                success, error_msg = db.add_job_config(
                    job_id=job_id, function_path=job_function_path,
                    trigger_type=trigger_type, trigger_args_str=trigger_args_str,
                    is_enabled=is_enabled, description=description or None,
                    job_args_str=job_args_str_final
                )
                if success:
                    flash(f"Đã thêm job '{job_id}' thành công.", "success")
                    # if db: db.add_scheduler_command('reload_jobs', {}) # Cân nhắc reload
                    return redirect(cancel_url)
                else:
                    flash(f"Thêm job '{job_id}' thất bại: {error_msg}", "error")
                    # Render lại form nếu lỗi DB
                    return render_template('admin_add_scheduled_job.html',
                                        title=title + " (Lỗi DB)", cancel_url=cancel_url,
                                        available_tasks=AVAILABLE_SCHEDULED_TASKS_LIST,
                                        valid_trigger_types=valid_trigger_types,
                                        saved_simulation_configs=saved_simulation_configs,
                                        current_data=current_data)
            except Exception as e_db: # Bắt lỗi cụ thể khi gọi DB
                logger.error(f"Lỗi khi gọi db.add_job_config: {e_db}", exc_info=True)
                flash(f"Lỗi CSDL nghiêm trọng khi thêm job: {e_db}", "error")
                # Render lại form
                return render_template('admin_add_scheduled_job.html',
                                       title=title + " (Lỗi DB Exception)", cancel_url=cancel_url,
                                       available_tasks=AVAILABLE_SCHEDULED_TASKS_LIST,
                                       valid_trigger_types=valid_trigger_types,
                                       saved_simulation_configs=saved_simulation_configs,
                                       current_data=current_data)
            # === KẾT THÚC KHỐI TRY NHỎ CHO DB CALL ===

        # === THÊM KHỐI EXCEPT CHO KHỐI TRY LỚN BÊN NGOÀI ===
        except Exception as e:
            logger.error(f"Lỗi không xác định trong quá trình xử lý POST add_scheduled_job: {e}", exc_info=True)
            flash(f"Lỗi không mong muốn trong quá trình xử lý form: {e}", "error")
            # Render lại form với lỗi chung
            return render_template('admin_add_scheduled_job.html',
                                   title=title + " (Lỗi Exception Chung)", cancel_url=cancel_url,
                                   available_tasks=AVAILABLE_SCHEDULED_TASKS_LIST,
                                   valid_trigger_types=valid_trigger_types,
                                   saved_simulation_configs=saved_simulation_configs,
                                   current_data=current_data)
        # === KẾT THÚC KHỐI EXCEPT ===

    # --- GET request ---
    return render_template('admin_add_scheduled_job.html',
                           title=title, cancel_url=cancel_url,
                           available_tasks=AVAILABLE_SCHEDULED_TASKS_LIST,
                           valid_trigger_types=valid_trigger_types,
                           saved_simulation_configs=saved_simulation_configs)

@admin_bp.route('/scheduled-jobs/<job_id>/edit', methods=['GET', 'POST'])
def edit_scheduled_job(job_id):
    logger = current_app.logger
    if not db: flash("Lỗi DB.", "error"); return redirect(url_for('admin.view_scheduled_jobs'))

    job_details = db.get_job_config_details(job_id) # Hàm này đã lấy job_args_str
    if not job_details:
        flash(f"Không tìm thấy job ID '{job_id}'.", "error")
        return redirect(url_for('admin.view_scheduled_jobs'))

    title = f"Sửa Tác vụ '{job_id}'"
    cancel_url = url_for('admin.view_scheduled_jobs')
    available_tasks = list(AVAILABLE_SCHEDULED_TASKS.items())
    available_tasks.sort()
    valid_trigger_types = ['interval', 'date', 'cron']

    # <<< THÊM: Lấy danh sách config sim đã lưu (cho cả GET và POST lỗi) >>>
    saved_simulation_configs = []
    try:
        configs_from_db, _ = db.get_all_simulation_configs(page=1, per_page=10000)
        if configs_from_db:
            saved_simulation_configs = sorted(configs_from_db, key=lambda x: x.get('config_name', ''))
    except Exception as e:
        logger.error(f"Lỗi tải dropdown simulation configs cho edit_scheduled_job: {e}", exc_info=True)
        flash("Lỗi tải danh sách Cấu hình Mô phỏng.", "warning")
    # ===================================================================

    if request.method == 'POST':
        current_data = request.form.to_dict() # Giữ lại data nếu lỗi
        try:
            # Lấy các trường form cơ bản
            trigger_type = request.form.get('trigger_type', '').strip()
            trigger_args_str = request.form.get('trigger_args_str', '{}').strip()
            is_enabled = request.form.get('is_enabled') == 'on'
            description = request.form.get('description', '').strip()
            # Function path không cho sửa, lấy từ job_details
            job_function_path = job_details.get('job_function_path')

            # Validate cơ bản
            errors = []
            # ... (validate trigger_type, trigger_args) ...
            if not trigger_type or trigger_type not in valid_trigger_types: errors.append("Trigger Type không hợp lệ.")
            try:
                trigger_args_dict = json.loads(trigger_args_str); assert isinstance(trigger_args_dict, dict)
            except: errors.append("Trigger Args JSON không hợp lệ.")


            job_args_str_final = None # Biến lưu job_args cuối cùng

            # === KIỂM TRA FUNCTION PATH ĐỂ XỬ LÝ JOB ARGS ===
            if job_function_path == SIMULATION_FUNCTION_PATH:
                config_id_str = request.form.get('simulation_config_id')
                if not config_id_str:
                    errors.append("Vui lòng chọn một Cấu hình Mô phỏng đã lưu.")
                else:
                    try:
                        config_id = int(config_id_str)
                        config_details = db.get_simulation_config(config_id)
                        if not config_details:
                            errors.append(f"Không tìm thấy Cấu hình Mô phỏng ID {config_id}.")
                        else:
                            job_args = { # Tạo job_args từ config đã chọn
                                'persona_a_id': config_details.get('persona_a_id'),
                                'persona_b_id': config_details.get('persona_b_id'),
                                # ... (các trường khác như trong hàm add) ...
                                'log_account_id_a': config_details.get('log_account_id_a'),
                                'log_account_id_b': config_details.get('log_account_id_b'),
                                'strategy_id': config_details.get('strategy_id'),
                                'max_turns': config_details.get('max_turns', 5),
                                'starting_prompt': config_details.get('starting_prompt'),
                                'sim_thread_id_base': f"scheduled_sim_{config_id}",
                                'sim_goal': config_details.get('simulation_goal') or f"scheduled_run_{config_id}"
                            }
                            if not all(job_args[k] for k in ['persona_a_id', 'persona_b_id', 'log_account_id_a', 'log_account_id_b', 'strategy_id']):
                                errors.append(f"Cấu hình Mô phỏng ID {config_id} thiếu thông tin.")
                            else:
                                job_args_str_final = json.dumps(job_args)
                    except ValueError:
                        errors.append("Lỗi định dạng ID Cấu hình Mô phỏng.")
                    except Exception as e_fetch:
                        errors.append(f"Lỗi khi lấy chi tiết Cấu hình Mô phỏng: {e_fetch}")
            else: # Function path khác
                job_args_str_textarea = request.form.get('job_args_str', '{}').strip()
                if job_args_str_textarea and job_args_str_textarea.strip() != '{}':
                    try:
                        job_args_dict = json.loads(job_args_str_textarea); assert isinstance(job_args_dict, dict)
                        job_args_str_final = job_args_str_textarea
                    except: errors.append("Job Args JSON không hợp lệ.")
            # ==============================================

            if errors:
                for msg in errors: flash(msg, "warning")
                # <<< Truyền đủ dữ liệu khi render lỗi >>>
                return render_template('admin_edit_scheduled_job.html',
                                       title=title + " (Lỗi)", cancel_url=cancel_url,
                                       job=job_details, # Job gốc
                                       available_tasks=available_tasks,
                                       valid_trigger_types=valid_trigger_types,
                                       saved_simulation_configs=saved_simulation_configs, # <<< Thêm
                                       current_data=current_data), 400

            # === Gọi hàm DB update_job_config với job_args_str_final ===
            db_success, db_error = db.update_job_config(
                job_id, trigger_type, trigger_args_str, is_enabled, description,
                job_args_str=job_args_str_final # <<< Truyền job_args cuối cùng
            )
            # ... (Xử lý success/error và redirect/render như cũ) ...
            if db_success:
                flash(f"Cập nhật cấu hình tác vụ '{job_id}' thành công!", 'success')
                # if db: db.add_scheduler_command('reload_jobs', {}) # Cân nhắc reload
                return redirect(cancel_url)
            else:
                flash(f"Lỗi cập nhật DB: {db_error or 'Unknown DB error'}", "error")
                # <<< Truyền đủ dữ liệu khi render lỗi DB >>>
                return render_template('admin_edit_scheduled_job.html',
                                       title=title + " (Lỗi DB)", cancel_url=cancel_url,
                                       job=job_details, # Job gốc
                                       available_tasks=available_tasks,
                                       valid_trigger_types=valid_trigger_types,
                                       saved_simulation_configs=saved_simulation_configs, # <<< Thêm
                                       current_data=current_data)
        except Exception as e:
            logger.error(f"Lỗi nghiêm trọng khi sửa scheduled job {job_id}: {e}", exc_info=True)
            flash(f"Lỗi không mong muốn khi cập nhật job: {e}", "error")
            # <<< Truyền đủ dữ liệu khi render lỗi Exception >>>
            return render_template('admin_edit_scheduled_job.html',
                                   title=title + " (Lỗi Exception)", cancel_url=cancel_url,
                                   job=job_details, # Job gốc
                                   available_tasks=available_tasks,
                                   valid_trigger_types=valid_trigger_types,
                                   saved_simulation_configs=saved_simulation_configs, # <<< Thêm
                                   current_data=current_data)


    # --- Xử lý GET Request ---
    # <<< Truyền thêm saved_simulation_configs >>>
    return render_template('admin_edit_scheduled_job.html',
                           title=title, cancel_url=cancel_url,
                           job=job_details, # Đã chứa job_args_str
                           available_tasks=available_tasks,
                           valid_trigger_types=valid_trigger_types,
                           saved_simulation_configs=saved_simulation_configs) 

@admin_bp.route('/scheduled-jobs/<job_id>/delete', methods=['POST'])
def delete_scheduled_job(job_id):
    """Chỉ xóa cấu hình Job khỏi DB."""
    if not db:
         flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
         return redirect(url_for('admin.view_scheduled_jobs'))

    # <<< KHÔNG CÒN PHẦN XÓA KHỎI SCHEDULER LIVE >>>

    # --- Chỉ Xóa khỏi DB ---
    db_success, db_error = db.delete_job_config(job_id)
    if db_success:
        flash(f"Đã xóa cấu hình job '{job_id}' khỏi DB. Thay đổi sẽ có hiệu lực sau khi khởi động lại server.", 'success')
    else:
        flash(f"Lỗi xóa cấu hình job '{job_id}' khỏi DB: {db_error or 'Unknown DB error'}.", "error")

    return redirect(url_for('admin.view_scheduled_jobs'))


@admin_bp.route('/scheduled-jobs/<job_id>/toggle', methods=['POST'])
def toggle_scheduled_job(job_id):
    """Chỉ Bật/Tắt cấu hình is_enabled trong DB."""
    if not db:
         flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
         return redirect(url_for('admin.view_scheduled_jobs'))

    job_details = db.get_job_config_details(job_id)
    if not job_details:
        flash(f"Không tìm thấy job '{job_id}' để thay đổi trạng thái.", "error")
        return redirect(url_for('admin.view_scheduled_jobs'))

    current_enabled_state = job_details.get('is_enabled', False)
    new_enabled_state = not current_enabled_state

    # --- Chỉ Cập nhật trạng thái trong DB ---
    db_success, db_error = db.update_job_enabled_status(job_id, new_enabled_state)

    if db_success:
        action_text = "bật" if new_enabled_state else "tắt"
        flash(f"Đã đặt trạng thái '{action_text}' cho job '{job_id}' trong cấu hình DB. Khởi động lại server để áp dụng.", 'success')
    else:
        flash(f"Lỗi cập nhật trạng thái DB cho job '{job_id}': {db_error or 'Unknown DB error'}", "error")

    # <<< KHÔNG CÒN PHẦN TƯƠNG TÁC VỚI SCHEDULER LIVE >>>
    return redirect(url_for('admin.view_scheduled_jobs'))



@admin_bp.route('/scheduled-jobs/suggestion_job/run-now', methods=['POST'])
def run_suggestion_job_now():
    """Yêu cầu chạy suggestion_job ngay lập tức thông qua command queue."""
    job_name_to_run = 'suggestion_job' # Tên job cần chạy ngay
    print(f"INFO: Received request to run job '{job_name_to_run}' now.")

    if not db:
         flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
         return redirect(url_for('admin.view_scheduled_jobs'))

    try:
        # Tạo một payload đơn giản (có thể trống hoặc chứa thông tin nguồn gốc)
        payload = {'source': 'manual_run_now_button'}
        # Thêm lệnh vào hàng đợi CSDL với một command_type riêng
        command_id = db.add_scheduler_command(
            command_type='run_suggestion_job_now', # <<< Loại lệnh mới
            payload=payload
        )

        if command_id:
            flash(f"Đã yêu cầu chạy tác vụ '{job_name_to_run}' ngay lập tức. Scheduler sẽ xử lý (Command ID: {command_id}).", 'success')
        else:
             flash(f"Lỗi khi thêm yêu cầu chạy tác vụ '{job_name_to_run}' vào hàng đợi CSDL.", "error")

    except Exception as e:
        print(f"Lỗi nghiêm trọng khi yêu cầu chạy '{job_name_to_run}' ngay: {e}")
        print(traceback.format_exc())
        flash(f"Đã xảy ra lỗi không mong muốn khi yêu cầu chạy tác vụ: {e}", "error")

    # <<< QUAN TRỌNG: Luôn trả về một response hợp lệ >>>
    return redirect(url_for('admin.view_scheduled_jobs'))

def _get_live_next_run_times():
    live_times = {}
    conn = None
    cur = None
    # !!! Sử dụng lại hàm get_db_connection từ module database !!!
    # Đảm bảo bạn đã import: from . import database as db
    if not db:
        print("ERROR (_get_live_next_run_times): Database module 'db' not available.")
        return {} # Trả về dict rỗng nếu không import được db

    try:
        conn = db.get_db_connection() # Dùng hàm kết nối từ database.py
        if not conn:
            print("ERROR (_get_live_next_run_times): Failed to get DB connection.")
            return {}

        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor) # Dùng DictCursor
        # Lấy id (là job_id) và next_run_time (là Unix timestamp float)
        cur.execute("SELECT id, next_run_time FROM public.apscheduler_jobs;")
        rows = cur.fetchall()
        live_times = {row['id']: row['next_run_time'] for row in rows} if rows else {}
        # print(f"DEBUG: Fetched live run times: {live_times}") # Log nếu cần debug

    except psycopg2.Error as db_err:
        print(f"ERROR (_get_live_next_run_times): DB Error querying apscheduler_jobs: {db_err}")
        # Không nên flash ở đây vì đây là hàm helper
    except Exception as e:
        print(f"ERROR (_get_live_next_run_times): Unexpected error querying apscheduler_jobs: {e}")
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return live_times

@admin_bp.route('/_get_live_job_statuses')
def get_live_job_statuses_for_ajax():
    """Trả về trạng thái next_run_time của các job dưới dạng JSON cho AJAX."""
    live_times_raw = _get_live_next_run_times() # Gọi hàm helper đã tạo
    live_statuses = {}
    server_tz_str = 'Asia/Ho_Chi_Minh' # Cần nhất quán với cấu hình scheduler
    try:
        server_tz = pytz.timezone(server_tz_str)
    except pytz.UnknownTimeZoneError:
        server_tz = pytz.utc

    for job_id, timestamp in live_times_raw.items():
        status_str = 'N/A'
        if timestamp is not None:
            try:
                utc_dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                local_dt = utc_dt.astimezone(server_tz)
                # Dùng định dạng đơn giản hơn cho AJAX nếu muốn
                status_str = local_dt.strftime('%H:%M:%S %d/%m/%Y')
                if job_id == 'suggestion_job':
                 print(f"AJAX DEBUG: Formatted time for {job_id} = {status_str}")
                # Hoặc giữ định dạng cũ:
                # status_str = local_dt.strftime('%Y-%m-%d %H:%M:%S %z')
            except Exception:
                status_str = 'Lỗi Format'
        else:
            status_str = 'Paused'
        live_statuses[job_id] = status_str

    # Cũng cần trả về trạng thái cho những job có config nhưng không chạy
    try:
        all_config_jobs = db.get_all_job_configs() or []
        for cfg_job in all_config_jobs:
            job_id = cfg_job.get('job_id')
            if job_id and job_id not in live_statuses:
                live_statuses[job_id] = 'Not Scheduled' # Hoặc dựa vào cfg_job['is_enabled']
    except Exception as e:
         print(f"Error fetching all configs for AJAX status: {e}")


    return jsonify(live_statuses)

# =============================================================
# === QUẢN LÝ MÔ PHỎNG HỘI THOẠI AI ===
# =============================================================


@admin_bp.route('/ai-simulations', methods=['GET'])
def view_ai_simulations():
    """
    Hiển thị trang quản lý mô phỏng AI:
    - Danh sách cấu hình đã lưu (có phân trang)
    - Danh sách các lần chạy/lệnh gần đây (từ commands và live jobs)
    """
    title = "Quản lý Mô phỏng AI"
    # Khởi tạo các list và dict cần thiết
    personas, strategies, accounts, saved_configs = [], [], [], []
    simulations_display_list = []
    saved_configs_pagination = None

    if not db:
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
    else:
        try:
            # --- 1. Lấy dữ liệu cho các Dropdown (cần cho form Thêm/Sửa sau này) ---
            personas = db.get_all_personas() or []
            strategies = db.get_all_strategies() or []
            accounts = db.get_all_accounts() or [] # Hàm này cần hỗ trợ phân trang nếu danh sách quá lớn

            # --- 2. Lấy danh sách Cấu hình Đã Lưu (có phân trang) ---
            page_saved = request.args.get('page_saved', 1, type=int) # Dùng param riêng cho pagination này
            if page_saved < 1: page_saved = 1

            saved_configs, total_saved_configs = db.get_all_simulation_configs(
                page=page_saved, per_page=PER_PAGE_SAVED_SIM_CONFIGS
            )


            if saved_configs is None or total_saved_configs is None:
                 flash("Lỗi khi tải danh sách cấu hình đã lưu.", "error")
                 saved_configs = []; total_saved_configs = 0
                 saved_configs_pagination = None

            else:
                 # Tính toán pagination cho cấu hình đã lưu
                 if total_saved_configs > 0:
                     total_pages_saved = ceil(total_saved_configs / PER_PAGE_SAVED_SIM_CONFIGS)
                     if page_saved > total_pages_saved and total_pages_saved > 0: page_saved = total_pages_saved
                     saved_configs_pagination = {
                        'page': page_saved, 'per_page': PER_PAGE_SAVED_SIM_CONFIGS, 'total_items': total_saved_configs,
                        'total_pages': total_pages_saved, 'has_prev': page_saved > 1, 'has_next': page_saved < total_pages_saved,
                        'prev_num': page_saved - 1 if page_saved > 1 else None,
                        'next_num': page_saved + 1 if page_saved < total_pages_saved else None,
                        'page_param': 'page_saved' # Thêm tên tham số page để dùng trong url_for
                     }
                 else:
                     saved_configs_pagination = {'page': 1, 'per_page': PER_PAGE_SAVED_SIM_CONFIGS, 'total_items': 0, 'total_pages': 0, 'has_prev': False, 'has_next': False, 'page_param': 'page_saved'}
                 print(f"DEBUG (view_ai_simulations): Calculated Saved Configs pagination = {saved_configs_pagination}")


            # === 3. TẠO DANH SÁCH HIỂN THỊ CÁC LẦN CHẠY/LỆNH GẦN ĐÂY ===
            server_tz = _get_configured_timezone()

            # 3.1 Lấy các Lệnh mô phỏng gần đây (pending, processing, error, done)
            recent_commands = db.get_recent_simulation_commands(
                status_list=['pending', 'processing', 'error', 'done'],
                command_type='run_simulation', limit=30
            ) or []
            command_map = {cmd['command_id']: cmd for cmd in recent_commands}
            print(f"DEBUG: Fetched {len(recent_commands)} recent simulation commands (incl. done).")

            # 3.2 Lấy các Job mô phỏng đang được lên lịch
            live_job_times = _get_live_next_run_times() or {} # dict {job_id: timestamp}
            live_sim_jobs_dict = {job_id: ts for job_id, ts in live_job_times.items() if job_id.startswith('sim_run_')}
            print(f"DEBUG: Found {len(live_sim_jobs_dict)} live simulation jobs.")

            processed_command_ids = set() # Theo dõi command ID đã được liên kết

            # 3.3 Tạo danh sách hiển thị - Ưu tiên xử lý các Job Live trước
            for job_id, next_run_timestamp in live_sim_jobs_dict.items():
                sim_info = {'id': job_id, 'type': 'job', 'command_id': None, 'config_info': '(Live Job - Config N/A)', 'status_text': 'Unknown', 'created_at': None, 'next_run_time_str': 'N/A', 'error_message': None}
                config_info_str = sim_info['config_info'] # Default

                # Trích xuất command_id từ job_id
                command_id_from_job = None
                parts = job_id.split('_')
                if len(parts) >= 3 and parts[0] == 'sim' and parts[1] == 'run':
                     try: command_id_from_job = int(parts[2]); sim_info['command_id'] = command_id_from_job
                     except ValueError: pass

                # Nếu tìm được command_id, lấy thông tin config từ command_map
                if command_id_from_job and command_id_from_job in command_map:
                    command_data = command_map[command_id_from_job]
                    payload = command_data.get('payload', {})
                    cfg_pa = payload.get('persona_a_id','?'); cfg_pb = payload.get('persona_b_id','?')
                    cfg_stra = payload.get('strategy_id','?'); cfg_turns = payload.get('max_turns','?')
                    cfg_goal = payload.get('sim_goal','?')
                    config_info_str = f"A: {cfg_pa} <-> B: {cfg_pb}<br>" \
                                      f"<small>Strat: {cfg_stra} | Goal: {cfg_goal} | Turns: {cfg_turns}</small>"
                    sim_info['created_at'] = command_data.get('created_at')
                    processed_command_ids.add(command_id_from_job)

                sim_info['config_info'] = config_info_str

                # Format thời gian và status
                if next_run_timestamp is not None:
                    try:
                        utc_dt = datetime.fromtimestamp(next_run_timestamp, tz=timezone.utc)
                        local_dt = utc_dt.astimezone(server_tz)
                        sim_info['next_run_time_str'] = local_dt.strftime('%Y-%m-%d %H:%M:%S %z')
                        sim_info['status_text'] = 'Scheduled'
                    except Exception: sim_info['next_run_time_str'] = 'Lỗi Format'
                else:
                    sim_info['next_run_time_str'] = '---'; sim_info['status_text'] = 'Paused/Finished?'

                simulations_display_list.append(sim_info)

            # 3.4 Xử lý các Command chưa được liên kết hoặc có trạng thái cuối cùng
            for cmd_id, command_data in command_map.items():
                if cmd_id not in processed_command_ids:
                    payload = command_data.get('payload', {})
                    status = command_data.get('status', 'unknown')
                    status_text = status.capitalize()
                    if status == 'pending': status_text = 'Pending Queue'
                    elif status == 'processing': status_text = 'Processing Cmd'
                    elif status == 'done': status_text = 'Command Done'
                    elif status == 'error': status_text = f"Command Error: {command_data.get('error_message', '')[:100]}" if command_data.get('error_message') else 'Command Error'

                    cfg_pa=payload.get('persona_a_id','?'); cfg_pb=payload.get('persona_b_id','?')
                    cfg_stra=payload.get('strategy_id','?'); cfg_turns=payload.get('max_turns','?')
                    cfg_goal=payload.get('sim_goal','?')
                    config_info_str = f"A: {cfg_pa} <-> B: {cfg_pb}<br>" \
                                      f"<small>Strat: {cfg_stra} | Goal: {cfg_goal} | Turns: {cfg_turns}</small>"

                    sim_info = {
                        'id': f"cmd_{cmd_id}", 'type': 'command', 'command_id': cmd_id,
                        'job_id': None, 'config_info': config_info_str,
                        'status_text': status_text, 'created_at': command_data.get('created_at'),
                        'next_run_time_str': '---', 'error_message': command_data.get('error_message')
                    }
                    simulations_display_list.append(sim_info)

            # 3.5 Sắp xếp danh sách hiển thị cuối cùng (theo thời gian tạo lệnh giảm dần)
            def get_sort_key(item):
                 if item.get('created_at'): return item['created_at']
                 return datetime.now(timezone.utc) # Fallback để sort
            simulations_display_list.sort(key=get_sort_key, reverse=True)

        except Exception as e:
            print(f"Lỗi khi tải dữ liệu trang mô phỏng AI: {e}")
            print(traceback.format_exc()) # In traceback để dễ debug
            flash("Lỗi không mong muốn khi tải dữ liệu.", "error")
            personas, strategies, accounts, saved_configs, simulations_display_list, saved_configs_pagination = [], [], [], [], [], None


    # Render template với tất cả dữ liệu cần thiết
    return render_template('admin_ai_simulations.html',
                           title=title,
                           personas=personas,
                           strategies=strategies,
                           accounts=accounts,
                           saved_configs=saved_configs,                 # Danh sách config trang hiện tại
                           saved_configs_pagination=saved_configs_pagination, # Pagination cho config
                           simulations_display=simulations_display_list) 


@admin_bp.route('/ai-simulations/run-adhoc', methods=['POST'])
def run_adhoc_simulation():
    """Xử lý yêu cầu chạy mô phỏng ad-hoc bằng cách thêm lệnh vào DB queue."""
    # Bây giờ không cần kiểm tra live_scheduler ở đây nữa
    # Chỉ cần kiểm tra module db có sẵn không
    if not db:
         flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
         return redirect(url_for('admin.view_ai_simulations'))

    try:
        # --- Lấy dữ liệu từ form ---
        persona_a_id = request.form.get('persona_a_id')
        persona_b_id = request.form.get('persona_b_id')
        log_account_id_a = request.form.get('log_account_id_a') # <<< Lấy account log A
        log_account_id_b = request.form.get('log_account_id_b') # <<< Lấy account log B
        strategy_id = request.form.get('strategy_id')
        max_turns_str = request.form.get('max_turns', '5')
        starting_prompt = request.form.get('starting_prompt', '').strip()
        sim_goal = request.form.get('sim_goal', 'simulation').strip()
        # sim_thread_id_base không cần lấy từ form nữa

        # --- Validate dữ liệu ---
        errors = []
        if not persona_a_id: errors.append("Vui lòng chọn Persona A.")
        if not persona_b_id: errors.append("Vui lòng chọn Persona B.")
        if persona_a_id == persona_b_id: errors.append("Persona A và Persona B phải khác nhau.")
        if not log_account_id_a: errors.append("Vui lòng chọn Account ID cho Log Persona A.") # <<< Validate A
        if not log_account_id_b: errors.append("Vui lòng chọn Account ID cho Log Persona B.") # <<< Validate B
        # Tùy chọn: Kiểm tra log_account_id_a != log_account_id_b nếu muốn
        # if log_account_id_a == log_account_id_b: errors.append("Account ID cho Log A và B nên khác nhau.")
        if not strategy_id: errors.append("Vui lòng chọn Chiến lược.")

        max_turns = 5 # Giá trị mặc định
        try:
            max_turns = int(max_turns_str)
            if not (1 <= max_turns <= 20):
                 raise ValueError("Số lượt phải từ 1 đến 20.")
        except ValueError as e:
            errors.append(f"Số lượt nói tối đa không hợp lệ: {e}")

        if errors:
            for error in errors: flash(error, 'warning')
            # Cần lấy lại danh sách để render lại form
            personas = db.get_all_personas() or []
            strategies = db.get_all_strategies() or []
            accounts = db.get_all_accounts() or [] # <<< Lấy lại accounts
            return render_template('admin_ai_simulations.html',
                                   title="Chạy Mô phỏng (Lỗi)",
                                   personas=personas, strategies=strategies, accounts=accounts, # <<< Truyền lại accounts
                                   current_data=request.form), 400

        # --- Chuẩn bị Payload cho Lệnh ---
        # Tạo tiền tố thread dựa trên account ID
        sim_thread_id_base = f"sim_{log_account_id_a[:5]}_vs_{log_account_id_b[:5]}"

        command_payload = {
            'persona_a_id': persona_a_id,
            'persona_b_id': persona_b_id,
            'log_account_id_a': log_account_id_a, # <<< Thêm
            'log_account_id_b': log_account_id_b, # <<< Thêm
            'strategy_id': strategy_id,
            'max_turns': max_turns,
            'starting_prompt': starting_prompt if starting_prompt else "Xin chào!",
            'sim_thread_id_base': sim_thread_id_base, # <<< Dùng tiền tố mới
            'sim_goal': sim_goal
            # 'sim_account_id' không cần nữa
        }

        print(f"INFO: Adding 'run_simulation' command with payload: {command_payload}")

        # --- Thêm Lệnh vào Hàng Đợi DB ---
        command_id = db.add_scheduler_command(
            command_type='run_simulation',
            payload=command_payload
        )

        if command_id:
            flash(f"Đã yêu cầu chạy mô phỏng '{sim_goal}' giữa {persona_a_id} và {persona_b_id}. Tác vụ sẽ được xử lý (Command ID: {command_id}).", 'success')
        else:
             flash("Lỗi khi thêm yêu cầu chạy mô phỏng vào hàng đợi CSDL.", "error")

    except Exception as e:
        print(f"Lỗi nghiêm trọng khi yêu cầu mô phỏng: {e}")
        print(traceback.format_exc())
        flash(f"Đã xảy ra lỗi không mong muốn khi yêu cầu chạy mô phỏng: {e}", "error")

    # Luôn redirect về trang quản lý sau khi xử lý
    return redirect(url_for('admin.view_ai_simulations'))


# --- === ROUTE HỦY BỎ MỘT LẦN CHẠY MÔ PHỎNG === ---
@admin_bp.route('/simulations/<job_id>/cancel', methods=['POST'])
def cancel_simulation_job(job_id):
    """Thêm lệnh 'cancel_job' vào queue để yêu cầu scheduler hủy job."""
    print(f"INFO: Received request to cancel simulation job ID: {job_id}")
    if not db:
         flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
         return redirect(url_for('admin.view_ai_simulations'))
    if not job_id:
         flash("Lỗi: Cần cung cấp Job ID để hủy bỏ.", "warning")
         return redirect(url_for('admin.view_ai_simulations'))

    # --- Tạo Payload cho lệnh Hủy ---
    # Payload chỉ cần chứa job_id cần hủy
    command_payload = {
        'job_id_to_cancel': job_id
    }

    try:
        # --- Thêm Lệnh 'cancel_job' vào Hàng Đợi DB ---
        command_id = db.add_scheduler_command(
            command_type='cancel_job', # <<< Loại lệnh mới
            payload=command_payload
        )

        if command_id:
            flash(f"Đã yêu cầu hủy bỏ job '{job_id}'. Scheduler sẽ xử lý (Command ID: {command_id}).", 'success')
        else:
             flash(f"Lỗi khi thêm yêu cầu hủy job '{job_id}' vào hàng đợi CSDL.", "error")

    except Exception as e:
        print(f"Lỗi nghiêm trọng khi yêu cầu hủy job {job_id}: {e}")
        print(traceback.format_exc())
        flash(f"Đã xảy ra lỗi không mong muốn khi yêu cầu hủy job: {e}", "error")

    # Luôn redirect về trang quản lý mô phỏng
    return redirect(url_for('admin.view_ai_simulations'))

# --- === ROUTE CHẠY MÔ PHỎNG TỪ CẤU HÌNH ĐÃ LƯU === ---
@admin_bp.route('/ai-simulations/configs/<int:config_id>/run', methods=['POST'])
def run_saved_simulation(config_id):
    """Đọc cấu hình đã lưu và thêm lệnh chạy mô phỏng vào queue."""
    print(f"INFO: Received request to run saved simulation config ID: {config_id}")
    if not db:
         flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
         return redirect(url_for('admin.view_ai_simulations'))

    try:
        # 1. Lấy chi tiết cấu hình từ CSDL
        config_details = db.get_simulation_config(config_id)

        if not config_details:
            flash(f"Lỗi: Không tìm thấy cấu hình mô phỏng có ID {config_id}.", "error")
            return redirect(url_for('admin.view_ai_simulations'))

        # Kiểm tra xem config có được enable không (tùy chọn)
        if not config_details.get('is_enabled', True):
             flash(f"Cấu hình mô phỏng '{config_details.get('config_name')}' đang bị tắt (disabled).", "warning")
             return redirect(url_for('admin.view_ai_simulations'))

        # 2. Trích xuất tham số từ cấu hình đã lưu
        # Đảm bảo tên key khớp với các cột trong bảng ai_simulation_configs
        # và khớp với các tham số mà run_ai_conversation_simulation mong đợi
        command_payload = {
            'persona_a_id': config_details.get('persona_a_id'),
            'persona_b_id': config_details.get('persona_b_id'),
            'log_account_id_a': config_details.get('log_account_id_a'),
            'log_account_id_b': config_details.get('log_account_id_b'),
            'strategy_id': config_details.get('strategy_id'),
            'max_turns': config_details.get('max_turns', 5), # Lấy giá trị từ DB hoặc default
            'starting_prompt': config_details.get('starting_prompt'), # Có thể là None
            # Tạo tiền tố thread ID dựa trên tên config để dễ nhận biết
            'sim_thread_id_base': f"sim_{config_details.get('config_name', str(config_id)).replace(' ', '_')[:15]}",
            'sim_goal': config_details.get('simulation_goal') or 'saved_config_run'
        }

        # Kiểm tra lại các giá trị bắt buộc
        if not all([command_payload['persona_a_id'], command_payload['persona_b_id'],
                    command_payload['log_account_id_a'], command_payload['log_account_id_b'],
                    command_payload['strategy_id']]):
            flash(f"Lỗi: Cấu hình ID {config_id} thiếu thông tin Persona, Account Log hoặc Strategy.", "error")
            return redirect(url_for('admin.view_ai_simulations'))


        print(f"INFO: Adding 'run_simulation' command from saved config '{config_details.get('config_name')}' with payload: {command_payload}")

        # 3. Thêm Lệnh vào Hàng Đợi DB
        command_id = db.add_scheduler_command(
            command_type='run_simulation',
            payload=command_payload
        )

        if command_id:
            flash(f"Đã yêu cầu chạy mô phỏng theo cấu hình '{config_details.get('config_name')}'. Tác vụ sẽ được xử lý (Command ID: {command_id}).", 'success')
        else:
             flash(f"Lỗi khi thêm yêu cầu chạy cấu hình '{config_details.get('config_name')}' vào hàng đợi CSDL.", "error")

    except Exception as e:
        print(f"Lỗi nghiêm trọng khi yêu cầu chạy cấu hình đã lưu ID {config_id}: {e}")
        print(traceback.format_exc())
        flash(f"Đã xảy ra lỗi không mong muốn: {e}", "error")

    # Luôn redirect về trang quản lý mô phỏng
    return redirect(url_for('admin.view_ai_simulations'))

# --- === ROUTE THÊM CẤU HÌNH MÔ PHỎNG MỚI === ---
@admin_bp.route('/ai-simulations/configs/add', methods=['GET', 'POST'])
def add_simulation_config_view():
    # ... (Code xử lý GET và lấy data dropdown như cũ) ...
    all_personas, all_accounts, all_language_strategies = [], [], []
    # ... (try/except để lấy data) ...
    try:
        # Lấy dữ liệu dropdown (ví dụ)
        personas_list_from_db, _ = db.get_all_personas(page=1, per_page=10000)
        all_personas = sorted(personas_list_from_db, key=lambda x: x.get('name', '').lower()) if personas_list_from_db else []
        accounts_list_from_db, _ = db.get_all_accounts(page=1, per_page=10000)
        all_accounts = sorted(accounts_list_from_db, key=lambda x: x.get('username', x.get('account_id', '')).lower()) if accounts_list_from_db else []
        raw_lang_strategies = db.get_all_strategies(strategy_type_filter='language')
        all_language_strategies = sorted(raw_lang_strategies, key=lambda x: x.get('strategy_id', '')) if raw_lang_strategies else []
    except Exception as e:
        current_app.logger.error(f"Lỗi tải dữ liệu cho form add_simulation_config_view: {e}", exc_info=True)
        flash("Lỗi tải dữ liệu cho form.", "error")


    if request.method == 'POST':
        current_data = request.form.to_dict()
        try:
            # --- Lấy dữ liệu form (giữ nguyên) ---
            config_name = request.form.get('config_name', '').strip()
            description = request.form.get('description', '').strip()
            persona_a_id = request.form.get('persona_a_id')
            persona_b_id = request.form.get('persona_b_id')
            account_log_a_id = request.form.get('account_log_a_id')
            account_log_b_id = request.form.get('account_log_b_id')
            strategy_id = request.form.get('strategy_id')
            max_turns_str = request.form.get('max_turns', '5').strip()
            starting_prompt = request.form.get('starting_prompt', '').strip()
            simulation_goal = request.form.get('simulation_goal', '').strip()

            # === SỬA CÁCH LẤY is_enabled ===
            is_enabled = request.form.get('enabled') == 'on'
            # ============================

            # --- Validate (giữ nguyên) ---
            errors = []
            # ... (phần validate giữ nguyên) ...
            if not config_name: errors.append("Tên cấu hình là bắt buộc.")
            # ... (các validate khác) ...
            max_turns = 5
            try:
                max_turns = int(max_turns_str)
                if not (1 <= max_turns <= 50): raise ValueError("Số lượt phải từ 1 đến 50.")
            except ValueError as e: errors.append(f"Số lượt nói tối đa không hợp lệ: {e}")

            if errors:
                for error in errors: flash(error, "warning")
                # Truyền lại các list dropdown khi render lỗi
                return render_template('admin_add_simulation_config.html',
                                       title="Thêm Cấu hình Mô phỏng AI (Lỗi)", cancel_url=url_for('admin.view_ai_simulations'),
                                       personas=all_personas, accounts=all_accounts, strategies=all_language_strategies,
                                       current_data=current_data), 400

            # --- Gọi hàm DB (Đảm bảo truyền biến boolean is_enabled) ---
            success, error_msg_db = db.add_simulation_config(
                config_name=config_name, description=description or None,
                persona_a_id=persona_a_id, persona_b_id=persona_b_id,
                log_account_id_a=account_log_a_id, log_account_id_b=account_log_b_id,
                strategy_id=strategy_id, max_turns=max_turns,
                starting_prompt=starting_prompt or None,
                simulation_goal=simulation_goal or None,
                is_enabled=is_enabled # <<< Truyền biến boolean đã xử lý
            )

            # ... (Xử lý success/error và redirect/render như cũ) ...
            if success:
                flash(f"Thêm cấu hình mô phỏng '{config_name}' thành công!", "success")
                return redirect(url_for('admin.view_ai_simulations'))
            else:
                flash(f"Thêm cấu hình mô phỏng thất bại: {error_msg_db or 'Lỗi không xác định.'}", "error")
                return render_template('admin_add_simulation_config.html',
                                       title="Thêm Cấu hình Mô phỏng AI (Lỗi DB)", cancel_url=url_for('admin.view_ai_simulations'),
                                       personas=all_personas, accounts=all_accounts, strategies=all_language_strategies,
                                       current_data=current_data)
        except Exception as e:
            current_app.logger.error(f"Lỗi nghiêm trọng khi thêm simulation config: {e}", exc_info=True)
            flash(f"Lỗi không mong muốn khi thêm cấu hình: {e}", "error")
            return render_template('admin_add_simulation_config.html',
                                   title="Thêm Cấu hình Mô phỏng AI (Lỗi Exception)", cancel_url=url_for('admin.view_ai_simulations'),
                                   personas=all_personas, accounts=all_accounts, strategies=all_language_strategies,
                                   current_data=current_data)

    # --- GET request (Giữ nguyên) ---
    return render_template('admin_add_simulation_config.html',
                           title="Thêm Cấu hình Mô phỏng AI", cancel_url=url_for('admin.view_ai_simulations'),
                           personas=all_personas,
                           accounts=all_accounts,
                           strategies=all_language_strategies)

@admin_bp.route('/ai-simulations/configs/<int:config_id>/edit', methods=['GET', 'POST'])
def edit_simulation_config_view(config_id): # <<< Đã sửa tên hàm route ở phản hồi trước
    """Hiển thị form và xử lý cập nhật cấu hình mô phỏng đã lưu."""
    logger = current_app.logger
    if not db:
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
        return redirect(url_for('admin.view_ai_simulations'))

    # Lấy chi tiết config hiện tại (cho cả GET và POST lỗi)
    config = db.get_simulation_config(config_id)
    if not config:
        flash(f"Không tìm thấy cấu hình mô phỏng có ID {config_id}.", "error")
        return redirect(url_for('admin.view_ai_simulations'))

    title = f"Sửa Cấu hình Mô phỏng '{config.get('config_name', config_id)}'"
    cancel_url = url_for('admin.view_ai_simulations')

    # === LẤY DỮ LIỆU DROPDOWN (CHO CẢ GET VÀ POST LỖI) ===
    all_personas, all_accounts, all_language_strategies = [], [], []
    try:
        personas_list_from_db, _ = db.get_all_personas(page=1, per_page=10000)
        all_personas = sorted(personas_list_from_db, key=lambda x: x.get('name', '').lower()) if personas_list_from_db else []
        accounts_list_from_db, _ = db.get_all_accounts(page=1, per_page=10000)
        all_accounts = sorted(accounts_list_from_db, key=lambda x: x.get('username', x.get('account_id', '')).lower()) if accounts_list_from_db else []
        raw_lang_strategies = db.get_all_strategies(strategy_type_filter='language')
        all_language_strategies = sorted(raw_lang_strategies, key=lambda x: x.get('strategy_id', '')) if raw_lang_strategies else []
    except Exception as e:
        logger.error(f"Lỗi tải dữ liệu dropdown cho form edit_simulation_config: {e}", exc_info=True)
        flash("Lỗi tải dữ liệu cần thiết cho form.", "error")
    # ======================================================

    if request.method == 'POST':
        current_data = request.form.to_dict() # Giữ lại dữ liệu form nếu lỗi
        try:
            # --- Lấy dữ liệu form (Giữ nguyên) ---
            config_name = request.form.get('config_name', '').strip()
            description = request.form.get('description', '').strip()
            persona_a_id = request.form.get('persona_a_id')
            persona_b_id = request.form.get('persona_b_id')
            log_account_id_a = request.form.get('log_account_id_a')
            log_account_id_b = request.form.get('log_account_id_b')
            strategy_id = request.form.get('strategy_id')
            max_turns_str = request.form.get('max_turns', '5').strip()
            starting_prompt = request.form.get('starting_prompt', '').strip()
            simulation_goal = request.form.get('simulation_goal', '').strip()
            is_enabled = request.form.get('is_enabled') == 'on' # Xử lý checkbox

            # --- Validate (Giữ nguyên) ---
            errors = []
            # ... (validate như trong hàm add) ...
            if not config_name: errors.append("Tên cấu hình là bắt buộc.")
            # ... (các validate khác) ...
            max_turns = 5
            try:
                max_turns = int(max_turns_str)
                if not (1 <= max_turns <= 50): raise ValueError("Số lượt phải từ 1 đến 50.")
            except ValueError as e: errors.append(f"Số lượt nói tối đa không hợp lệ: {e}")


            if errors:
                for error in errors: flash(error, 'warning')
                # <<< Truyền ĐỦ dữ liệu dropdown khi render lại form lỗi >>>
                return render_template('admin_edit_simulation_config.html',
                                       title=title + " (Lỗi)", cancel_url=cancel_url,
                                       config=config, # Truyền config gốc
                                       personas=all_personas, accounts=all_accounts, strategies=all_language_strategies,
                                       current_data=current_data), 400

            # --- Gọi hàm DB để cập nhật ---
            success, error_msg_db = db.update_simulation_config(
                config_id=config_id,
                config_name=config_name, description=description or None,
                persona_a_id=persona_a_id, persona_b_id=persona_b_id,
                log_account_id_a=log_account_id_a, log_account_id_b=log_account_id_b,
                strategy_id=strategy_id, max_turns=max_turns,
                starting_prompt=starting_prompt or None,
                simulation_goal=simulation_goal or None,
                is_enabled=is_enabled
            )

            if success:
                flash(f"Đã cập nhật cấu hình mô phỏng '{config_name}' thành công!", 'success')
                return redirect(cancel_url)
            else:
                flash(f"Cập nhật cấu hình '{config_name}' thất bại: {error_msg_db or 'Lỗi không xác định.'}", 'error')
                 # <<< Truyền ĐỦ dữ liệu dropdown khi render lại form lỗi DB >>>
                return render_template('admin_edit_simulation_config.html',
                                       title=title + " (Lỗi DB)", cancel_url=cancel_url,
                                       config=config, # Truyền config gốc
                                       personas=all_personas, accounts=all_accounts, strategies=all_language_strategies,
                                       current_data=current_data)
        except Exception as e:
            logger.error(f"Lỗi nghiêm trọng khi cập nhật simulation config ID {config_id}: {e}", exc_info=True)
            flash(f"Lỗi không mong muốn khi cập nhật cấu hình: {e}", "error")
             # <<< Truyền ĐỦ dữ liệu dropdown khi render lại form lỗi Exception >>>
            return render_template('admin_edit_simulation_config.html',
                                   title=title + " (Lỗi Exception)", cancel_url=cancel_url,
                                   config=config, # Truyền config gốc
                                   personas=all_personas, accounts=all_accounts, strategies=all_language_strategies,
                                   current_data=current_data)

    # --- Xử lý GET request ---
    # Render template, truyền cả config gốc và dữ liệu dropdown đã lấy
    return render_template('admin_edit_simulation_config.html',
                           title=title, cancel_url=cancel_url,
                           config=config, # <<< Dữ liệu cấu hình cần sửa
                           personas=all_personas,
                           accounts=all_accounts,
                           strategies=all_language_strategies)

@admin_bp.route('/ai-simulations/configs/<int:config_id>/toggle', methods=['POST'])
def toggle_simulation_config(config_id):
    """Bật hoặc tắt một simulation config."""
    logger = current_app.logger
    if not db:
        flash("Lỗi DB.", "error")
        return redirect(url_for('admin.view_ai_simulations'))

    # Xác định hành động mong muốn từ form
    action = request.form.get('action')
    new_enabled_state = (action == 'enable') # True nếu action là 'enable'

    logger.info(f"Request to {action} simulation config ID: {config_id}. Setting is_enabled to: {new_enabled_state}")

    try:
        # Gọi hàm DB mới để cập nhật trạng thái
        success, error_msg = db.update_simulation_config_enabled(config_id, new_enabled_state)

        if success:
            action_text = "bật" if new_enabled_state else "tắt"
            flash(f"Đã {action_text} cấu hình mô phỏng ID {config_id}.", 'success')
        else:
            flash(f"Lỗi khi cập nhật trạng thái cấu hình ID {config_id}: {error_msg or 'Không tìm thấy ID?'}", "error")

    except Exception as e:
        logger.error(f"Lỗi nghiêm trọng khi toggle simulation config {config_id}: {e}", exc_info=True)
        flash(f"Lỗi không mong muốn: {e}", "error")

    return redirect(url_for('admin.view_ai_simulations'))

@admin_bp.route('/ai-simulations/configs/<int:config_id>/delete', methods=['POST'])
def delete_simulation_config_view(config_id):
    """Xử lý xóa một cấu hình mô phỏng đã lưu."""
    print(f"INFO: Received request to delete simulation config ID: {config_id}")
    if not db:
         flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
         return redirect(url_for('admin.view_ai_simulations'))

    try:
        # Gọi hàm xóa trong database.py
        success = db.delete_simulation_config(config_id)

        if success:
            flash(f"Đã xóa thành công cấu hình mô phỏng ID {config_id}.", 'success')
        else:
            # Có thể do ID không tồn tại
            flash(f"Xóa cấu hình mô phỏng ID {config_id} thất bại (ID không tồn tại?).", 'warning')

    except Exception as e:
        print(f"Lỗi nghiêm trọng khi xóa cấu hình mô phỏng ID {config_id}: {e}")
        print(traceback.format_exc())
        flash(f"Đã xảy ra lỗi không mong muốn khi xóa cấu hình: {e}", "error")

    # Luôn redirect về trang quản lý chính
    return redirect(url_for('admin.view_ai_simulations'))

# --- === ROUTE XÓA MỘT LỆNH SCHEDULER KHỎI HÀNG ĐỢI/LỊCH SỬ LỆNH === ---
@admin_bp.route('/commands/<int:command_id>/delete', methods=['POST'])
def delete_scheduler_command_view(command_id):
    """Xử lý xóa một command khỏi bảng scheduler_commands."""
    print(f"INFO: Received request to delete scheduler command ID: {command_id}")
    if not db:
         flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
         return redirect(url_for('admin.view_ai_simulations')) # Hoặc trang thích hợp khác

    try:
        # Gọi hàm xóa trong database.py
        success = db.delete_scheduler_command(command_id)

        if success:
            flash(f"Đã xóa thành công lệnh ID {command_id}.", 'success')
        else:
            flash(f"Xóa lệnh ID {command_id} thất bại (ID không tồn tại?).", 'warning')

    except Exception as e:
        print(f"Lỗi nghiêm trọng khi xóa lệnh ID {command_id}: {e}")
        print(traceback.format_exc())
        flash(f"Đã xảy ra lỗi không mong muốn khi xóa lệnh: {e}", "error")

    # Luôn redirect về trang quản lý mô phỏng (nơi hiển thị danh sách lệnh/job)
    return redirect(url_for('admin.view_ai_simulations'))

@admin_bp.route('/ai-simulations/commands/clear-finished', methods=['POST'])
def clear_finished_simulation_commands():
    """Xóa các lệnh run_simulation có status 'done' hoặc 'error'."""
    print("INFO: Received request to clear finished simulation commands.")
    if not db:
         flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
         return redirect(url_for('admin.view_ai_simulations'))

    try:
        # Gọi hàm xóa hàng loạt trong database.py
        success, deleted_count, error_msg = db.delete_completed_or_errored_commands(
            command_type='run_simulation' # Chỉ xóa lệnh loại run_simulation
        )

        if success:
            flash(f"Đã xóa thành công {deleted_count or 0} lệnh mô phỏng đã hoàn thành hoặc bị lỗi.", 'success')
        else:
            flash(f"Xóa lệnh thất bại: {error_msg or 'Lỗi không xác định'}.", "error")

    except Exception as e:
        print(f"Lỗi nghiêm trọng khi xóa hàng loạt lệnh: {e}")
        print(traceback.format_exc())
        flash(f"Đã xảy ra lỗi không mong muốn khi xóa lệnh: {e}", "error")

    # Luôn redirect về trang quản lý mô phỏng
    return redirect(url_for('admin.view_ai_simulations'))

# --- === ROUTE XEM CHI TIẾT KẾT QUẢ MÔ PHỎNG === ---
@admin_bp.route('/simulations/results/<int:command_id>')
def view_simulation_results(command_id):
    """Hiển thị chi tiết cuộc hội thoại của một lần chạy mô phỏng."""
    if not db:
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
        return redirect(url_for('admin.view_ai_simulations'))

    command_details = None
    conversation_turns = []
    title = f"Kết quả Mô phỏng (Lệnh #{command_id})"

    try:
        # 1. Lấy thông tin lệnh gốc để biết cấu hình và thread_id_base
        command_details = db.get_command_details(command_id)
        if not command_details or command_details.get('command_type') != 'run_simulation':
            flash(f"Không tìm thấy lệnh chạy mô phỏng hợp lệ với ID {command_id}.", "error")
            return redirect(url_for('admin.view_ai_simulations'))

        payload = command_details.get('payload', {})
        thread_id_base = payload.get('sim_thread_id_base')
        # Hoặc lấy từ trường 'run_details' nếu bạn đã implement lưu thread_id đầy đủ

        if not thread_id_base:
            flash(f"Không thể xác định Thread ID gốc cho lệnh {command_id}.", "error")
            # Vẫn render trang nhưng không có hội thoại
        else:
            # Tạo pattern để tìm kiếm (cần khớp với cách tạo trong background_tasks)
            thread_id_pattern = f"sim_thread_{thread_id_base}_%"
            print(f"DEBUG: Finding conversation with thread_id LIKE '{thread_id_pattern}'")
            conversation_turns = db.get_simulation_conversation(thread_id_pattern) or []
            if conversation_turns is None: # Phân biệt lỗi DB và không có dữ liệu
                 flash("Lỗi khi tải dữ liệu hội thoại từ CSDL.", "error")
                 conversation_turns = []
            print(f"DEBUG: Found {len(conversation_turns)} turns.")

        title = f"Kết quả: {payload.get('persona_a_id','?')} vs {payload.get('persona_b_id','?')}"

    except Exception as e:
        print(f"Lỗi nghiêm trọng khi tải kết quả mô phỏng {command_id}: {e}")
        flash(f"Lỗi không mong muốn khi tải kết quả: {e}", "error")
        conversation_turns = [] # Đảm bảo list rỗng khi lỗi

    # Render template mới (sẽ tạo ở bước sau)
    return render_template('admin_simulation_results.html',
                           title=title,
                           command=command_details, # Truyền thông tin lệnh gốc
                           conversation=conversation_turns) # Truyền các lượt hội thoại

# =============================================
# === QUẢN LÝ API KEYS ===
# =============================================

@admin_bp.route('/api-keys', methods=['GET'])
def view_api_keys():
    """Hiển thị danh sách các API Keys đã lưu."""
    title = "Quản lý API Keys"
    api_keys_list = []
    if not db:
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
    else:
        try:
            # Lấy danh sách keys (hàm này không trả về giá trị key thực tế)
            api_keys_list = db.get_all_api_keys()
            if api_keys_list is None:
                 flash("Lỗi khi tải danh sách API keys từ CSDL.", "error")
                 api_keys_list = []
        except Exception as e:
            print(f"Lỗi nghiêm trọng khi load API keys: {e}")
            flash("Lỗi không mong muốn khi tải danh sách API Keys.", "error")
            api_keys_list = []

    return render_template('admin_api_keys.html',
                           title=title,
                           api_keys=api_keys_list)

# --- === ROUTE THÊM API KEY MỚI === ---
@admin_bp.route('/api-keys/add', methods=['GET', 'POST'])
def add_api_key_view():
    """Hiển thị form và xử lý thêm API Key mới."""
    title="Thêm API Key Mới"
    # Danh sách provider có thể lấy từ config hoặc định nghĩa cứng ở đây
    providers = ['google_gemini'] # Mở rộng sau

    if request.method == 'POST':
        if not db:
            flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error");
            return render_template('admin_add_api_key.html', title=title, providers=providers, current_data=request.form), 500

        key_name = request.form.get('key_name', '').strip()
        provider = request.form.get('provider', '').strip()
        api_key_value = request.form.get('api_key_value', '').strip() # Lấy giá trị key gốc
        status = request.form.get('status', 'active').strip()
        notes = request.form.get('notes', '').strip()

        # Validate
        errors = []
        if not key_name: errors.append("Tên Key là bắt buộc.")
        if not provider: errors.append("Nhà cung cấp là bắt buộc.")
        if provider not in providers: errors.append("Nhà cung cấp không hợp lệ.")
        if not api_key_value: errors.append("Giá trị API Key là bắt buộc.")
        if status not in ['active', 'inactive']: errors.append("Trạng thái không hợp lệ.")

        if errors:
            for error in errors: flash(error, 'warning')
            return render_template('admin_add_api_key.html', title=title + " (Lỗi)",
                                   providers=providers, current_data=request.form), 400

        try:
            # Gọi hàm DB để thêm (hàm này đã bao gồm mã hóa)
            success = db.add_api_key(key_name, provider, api_key_value, status, notes or None)
            if success:
                flash(f"Đã thêm API Key '{key_name}' thành công!", 'success')
                return redirect(url_for('admin.view_api_keys'))
            else:
                # Lỗi có thể do tên key trùng hoặc lỗi DB khác
                flash(f"Thêm API Key '{key_name}' thất bại! (Tên Key có thể đã tồn tại?)", 'error')
                return render_template('admin_add_api_key.html', title=title,
                                       providers=providers, current_data=request.form)
        except Exception as e:
            print(f"Lỗi nghiêm trọng khi thêm API Key: {e}")
            flash(f"Lỗi không mong muốn khi thêm key: {e}", "error")
            return render_template('admin_add_api_key.html', title=title,
                                   providers=providers, current_data=request.form)

    # GET request
    return render_template('admin_add_api_key.html', title=title, providers=providers)

# --- === ROUTE SỬA THÔNG TIN API KEY === ---
@admin_bp.route('/api-keys/<int:key_id>/edit', methods=['GET', 'POST'])
def edit_api_key_view(key_id):
    """Hiển thị form và xử lý cập nhật thông tin API Key (không bao gồm giá trị key)."""
    title = f"Sửa API Key #{key_id}"
    valid_statuses = ['active', 'inactive', 'rate_limited']

    if not db:
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
        return redirect(url_for('admin.view_api_keys'))

    # Lấy chi tiết key cho cả GET và POST lỗi
    key_details = db.get_api_key_details(key_id)
    if not key_details:
        flash(f"Không tìm thấy API Key có ID {key_id}.", "error")
        return redirect(url_for('admin.view_api_keys'))

    if request.method == 'POST':
        try:
            key_name = request.form.get('key_name', '').strip()
            status = request.form.get('status', '').strip()
            notes = request.form.get('notes', '').strip()

            # Validate
            errors = []
            if not key_name: errors.append("Tên Key là bắt buộc.")
            if status not in valid_statuses: errors.append("Trạng thái không hợp lệ.")

            if errors:
                for error in errors: flash(error, 'warning')
                # Render lại form với lỗi, giữ lại dữ liệu nhập
                return render_template('admin_edit_api_key.html', title=title + " (Lỗi)",
                                       key_details=key_details, # Truyền key gốc để lấy ID, provider
                                       current_data=request.form), 400 # Truyền dữ liệu lỗi

            # Gọi hàm DB để cập nhật (không cập nhật giá trị key)
            success = db.update_api_key(key_id, key_name, status, notes or None)

            if success:
                flash(f"Đã cập nhật thông tin cho API Key '{key_name}' (ID: {key_id}).", 'success')
                return redirect(url_for('admin.view_api_keys'))
            else:
                # Lỗi có thể do tên key trùng hoặc lỗi DB khác
                flash(f"Cập nhật API Key '{key_name}' thất bại! (Tên Key mới có thể đã tồn tại?)", 'error')
                return render_template('admin_edit_api_key.html', title=title,
                                       key_details=key_details, current_data=request.form)

        except Exception as e:
            print(f"Lỗi nghiêm trọng khi cập nhật API Key {key_id}: {e}")
            flash(f"Lỗi không mong muốn khi cập nhật key: {e}", "error")
            return render_template('admin_edit_api_key.html', title=title,
                                   key_details=key_details, current_data=request.form)

    # GET request: Hiển thị form với dữ liệu hiện tại
    return render_template('admin_edit_api_key.html', title=title, key_details=key_details)

# --- === ROUTE XÓA API KEY === ---
@admin_bp.route('/api-keys/<int:key_id>/delete', methods=['POST'])
def delete_api_key_view(key_id):
    """Xử lý xóa một API Key."""
    print(f"INFO: Received request to delete API Key ID: {key_id}")
    if not db:
         flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
         return redirect(url_for('admin.view_api_keys'))

    try:
        # Lấy tên key trước khi xóa để hiển thị thông báo (tùy chọn)
        key_details = db.get_api_key_details(key_id)
        key_name = key_details.get('key_name', f'ID {key_id}') if key_details else f'ID {key_id}'

        # Gọi hàm xóa trong database.py
        success = db.delete_api_key(key_id)

        if success:
            flash(f"Đã xóa thành công API Key '{key_name}'.", 'success')
        else:
            flash(f"Xóa API Key '{key_name}' thất bại (ID không tồn tại?).", 'warning')

    except Exception as e:
        print(f"Lỗi nghiêm trọng khi xóa API Key {key_id}: {e}")
        flash(f"Đã xảy ra lỗi không mong muốn khi xóa key: {e}", "error")

    # Luôn redirect về trang quản lý API Key
    return redirect(url_for('admin.view_api_keys'))

# =============================================
# === QUẢN LÝ MACRO DEFINITIONS ===
# =============================================
@admin_bp.route('/macro-definitions')
def view_macro_definitions():
    """Hiển thị danh sách Macro Definitions với filter và pagination."""
    title = "Quản lý Định nghĩa Macro Code"
    macros_page = []
    pagination = None
    # Danh sách các target có thể có cho dropdown lọc
    app_targets = ['system', 'generic', 'tiktok', 'zalo', 'facebook'] # Hoặc lấy động từ DB
    active_filters = {}

    if not db:
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
    else:
        try:
            # 1. Lấy tham số trang và bộ lọc từ URL
            page = request.args.get('page', 1, type=int)
            if page < 1: page = 1

            # Lấy giá trị filter từ request.args
            filter_code = request.args.get('filter_code', '').strip()
            filter_desc = request.args.get('filter_desc', '').strip()
            filter_target = request.args.get('filter_target', '__all__').strip() # Dùng '__all__' làm giá trị mặc định (không lọc)

            # Lưu lại các filter đang áp dụng để điền lại form
            active_filters = {
                'filter_code': filter_code,
                'filter_desc': filter_desc,
                'filter_target': filter_target
            }
            # Tạo dict filters để truyền vào hàm DB (chỉ chứa filter có giá trị và loại bỏ giá trị default '__all__')
            db_filters = {k.replace('filter_', ''): v for k, v in active_filters.items() if v and (k != 'filter_target' or v != '__all__')}

            # 2. Gọi hàm DB mới để lấy dữ liệu trang và tổng số
            macros_page, total_items = db.get_all_macro_definitions(
                filters=db_filters,
                page=page,
                per_page=PER_PAGE_MACROS
            )

            if macros_page is None or total_items is None:
                 flash("Lỗi khi tải danh sách định nghĩa macro từ CSDL.", "error")
                 macros_page = []; total_items = 0
                 pagination = None
            else:
                 # 3. Tính toán thông tin phân trang
                 if total_items > 0:
                     total_pages = ceil(total_items / PER_PAGE_MACROS)
                     if page > total_pages and total_pages > 0: page = total_pages # Đảm bảo page hợp lệ
                     pagination = {
                        'page': page, 'per_page': PER_PAGE_MACROS, 'total_items': total_items,
                        'total_pages': total_pages, 'has_prev': page > 1, 'has_next': page < total_pages,
                        'prev_num': page - 1 if page > 1 else None,
                        'next_num': page + 1 if page < total_pages else None
                     }
                 else: # total_items = 0
                     pagination = {'page': 1, 'per_page': PER_PAGE_MACROS, 'total_items': 0, 'total_pages': 0, 'has_prev': False, 'has_next': False}

            # 4. Lấy danh sách app_targets cho dropdown (đã định nghĩa ở trên)

        except Exception as e:
            print(f"Lỗi nghiêm trọng load macro definitions: {e}")
            flash("Lỗi không mong muốn khi tải dữ liệu.", "error")
            macros_page = []; pagination = None; app_targets = []

    # 5. Render template với đầy đủ dữ liệu
    return render_template('admin_macro_definitions.html',
                           title=title,
                           macros=macros_page,       # Danh sách macro của trang này
                           pagination=pagination,    # Thông tin phân trang
                           filters=active_filters,   # Filter đang áp dụng để điền lại form
                           app_targets=app_targets)


@admin_bp.route('/macro-definitions/add', methods=['GET', 'POST'])
def add_macro_definition_view():
    """Thêm định nghĩa Macro Code mới."""
    # ... (Code đã cung cấp ở lần trước) ...
    title="Thêm Định nghĩa Macro Mới"
    app_targets = ['system', 'generic', 'tiktok', 'zalo', 'facebook'] # Hoặc lấy động từ DB
    if request.method == 'POST':
        if not db: flash("Lỗi DB.", "error"); return redirect(url_for('admin.view_macro_definitions'))
        macro_code = request.form.get('macro_code', '').strip()
        description = request.form.get('description', '').strip()
        app_target = request.form.get('app_target', '').strip()
        params_schema_str = request.form.get('params_schema', '').strip()
        notes = request.form.get('notes', '').strip()
        if not macro_code:
            flash("Macro Code là bắt buộc.", "warning")
            return render_template('admin_add_macro_definition.html', title=title, app_targets=app_targets, current_data=request.form), 400
        success, error_msg = db.add_macro_definition(macro_code, description, app_target, params_schema_str, notes)
        if success:
            flash(f"Thêm định nghĩa macro '{macro_code}' thành công!", 'success')
            return redirect(url_for('admin.view_macro_definitions'))
        else:
            flash(f"Thêm thất bại: {error_msg}", 'error')
            return render_template('admin_add_macro_definition.html', title=title, app_targets=app_targets, current_data=request.form)
    return render_template('admin_add_macro_definition.html', title=title, app_targets=app_targets)


@admin_bp.route('/macro-definitions/<path:macro_code>/edit', methods=['GET', 'POST']) # Dùng <path:> để xử lý '/' trong macro code nếu có
def edit_macro_definition_view(macro_code):
    """Sửa định nghĩa Macro Code."""
    # ... (Code đã cung cấp ở lần trước, nhớ dùng current_data khi POST lỗi) ...
    if not db: flash("Lỗi DB.", "error"); return redirect(url_for('admin.view_macro_definitions'))
    macro_def = db.get_macro_definition(macro_code)
    if not macro_def:
        flash(f"Không tìm thấy Macro Code '{macro_code}'.", "error")
        return redirect(url_for('admin.view_macro_definitions'))
    title = f"Sửa Định nghĩa Macro '{macro_code}'"
    app_targets = ['system', 'generic', 'tiktok', 'zalo', 'facebook']
    if request.method == 'POST':
        description = request.form.get('description', '').strip()
        app_target = request.form.get('app_target', '').strip()
        params_schema_str = request.form.get('params_schema', '').strip()
        notes = request.form.get('notes', '').strip()
        success, error_msg = db.update_macro_definition(macro_code, description, app_target, params_schema_str, notes)
        if success:
            flash(f"Cập nhật định nghĩa macro '{macro_code}' thành công!", 'success')
            return redirect(url_for('admin.view_macro_definitions'))
        else:
            flash(f"Cập nhật thất bại: {error_msg}", 'error')
            current_data = request.form.copy()
            current_data['macro_code'] = macro_code
            return render_template('admin_edit_macro_definition.html', title=title, macro_def=macro_def, app_targets=app_targets, current_data=current_data)
    return render_template('admin_edit_macro_definition.html', title=title, macro_def=macro_def, app_targets=app_targets)


@admin_bp.route('/macro-definitions/<path:macro_code>/delete', methods=['POST'])
def delete_macro_definition_view(macro_code):
    """Xóa định nghĩa Macro Code."""
    # ... (Code đã cung cấp ở lần trước) ...
    if not db: flash("Lỗi DB.", "error"); return redirect(url_for('admin.view_macro_definitions'))
    success, error_msg = db.delete_macro_definition(macro_code)
    if success: flash(f"Đã xóa định nghĩa macro '{macro_code}'.", 'success')
    else: flash(f"Xóa thất bại: {error_msg}", 'error')
    return redirect(url_for('admin.view_macro_definitions'))


# --- Sửa Route Thêm/Sửa Transition ---


@admin_bp.route('/transitions/<int:transition_id>/edit', methods=['GET', 'POST'])
def edit_transition(transition_id):
    # ... (Phần lấy transition details và strategy_id_redirect giữ nguyên) ...
    VALID_CONDITION_TYPES = [
        '', # Luôn chạy (mặc định)
        'current_stage_equals',
        'element_exists_text',
        'element_exists_id',
        'variable_equals' # Ví dụ
        # Thêm các loại điều kiện khác client có thể kiểm tra
    ]
    if not db: flash("Lỗi DB.", "error"); return redirect(url_for('admin.view_strategies'))
    transition = db.get_transition_details(transition_id) # Hàm này đã sửa
    if not transition: flash(f"Ko tìm thấy transition ID {transition_id}.", "error"); return redirect(url_for('admin.view_strategies'))
    strategy_id_redirect = transition.get('strategy_id')
    if not strategy_id_redirect: flash(f"Ko tìm thấy strategy gốc cho transition {transition_id}.", "error"); return redirect(url_for('admin.view_strategies'))

    # --- Lấy dữ liệu dropdown (cho cả GET và POST lỗi) ---
    strategy_stages = db.get_stages_for_strategy(strategy_id_redirect) or []
    all_stages = db.get_all_stages() or []
    all_macros = db.get_all_macro_definitions() or [] # <<< Lấy macros

    if request.method == 'POST':
        # ... (Lấy current_stage_id, user_intent, condition_logic, next_stage_id, priority_str như cũ) ...
        current_stage_id = request.form.get('current_stage_id')
        user_intent = request.form.get('user_intent')
        condition_logic = request.form.get('condition_logic')
        next_stage_id = request.form.get('next_stage_id')
        priority_str = request.form.get('priority', '0')
        # <<< Lấy macro_code và params_str >>>
        action_macro_code = request.form.get('action_macro_code')
        action_params_str = request.form.get('action_params_str', '{}')

        # <<< Validate >>>
        if not current_stage_id or not user_intent:
             flash("Current Stage và User Intent là bắt buộc.", "warning")
             return render_template('admin_edit_transition.html', title=f"Sửa Transition {transition_id} (Lỗi)",
                                    transition=transition, strategy_stages=strategy_stages, all_stages=all_stages,
                                    all_macros=all_macros, # <<< Truyền macros
                                    valid_intents=VALID_INTENTS_FOR_TRANSITION, current_data=request.form), 400
        try: priority = int(priority_str)
        except ValueError:
             flash("Priority phải là số nguyên.", "warning")
             return render_template('admin_edit_transition.html', title=f"Sửa Transition {transition_id} (Lỗi)",
                                    transition=transition, strategy_stages=strategy_stages, all_stages=all_stages,
                                    all_macros=all_macros, valid_intents=VALID_INTENTS_FOR_TRANSITION, current_data=request.form), 400

        # <<< Gọi hàm db.update_transition đã sửa >>>
        success, error_msg = db.update_transition(
            transition_id, current_stage_id, user_intent, condition_logic, next_stage_id, priority,
            action_macro_code, action_params_str
        )

        if success:
            flash('Cập nhật transition thành công!', 'success')
            return redirect(url_for('admin.view_strategy_stages', strategy_id=strategy_id_redirect))
        else:
            flash(f'Cập nhật transition thất bại: {error_msg}', 'error')
            # <<< Render lại form với lỗi, truyền đủ dữ liệu dropdown và current_data >>>
            return render_template('admin_edit_transition.html', title=f"Sửa Transition {transition_id} (Lỗi DB)",
                                   transition=transition, strategy_stages=strategy_stages, all_stages=all_stages,
                                   all_macros=all_macros, valid_intents=VALID_INTENTS_FOR_TRANSITION, current_data=request.form)

    # <<< GET request: Truyền đủ dữ liệu dropdown >>>
    return render_template('admin_edit_transition.html', title=f"Sửa Transition {transition_id}",
                           transition=transition, # Đã chứa action_macro_code và action_params_str
                           strategy_stages=strategy_stages,
                           all_stages=all_stages,
                           all_macros=all_macros, # <<< Truyền macros
                           valid_intents=VALID_INTENTS_FOR_TRANSITION)


@admin_bp.route('/transitions/add-control', methods=['GET', 'POST'])
def add_transition_control():
    """Hiển thị form và xử lý thêm Transition mới cho Control Strategy."""
    # Lấy strategy_id từ URL args hoặc form
    strategy_id = request.args.get('strategy_id') or request.form.get('strategy_id')
    current_stage_id_prefill = request.args.get('current_stage_id')

    if not strategy_id: # Kiểm tra strategy_id
        flash("Cần cung cấp strategy_id.", "error")
        return redirect(url_for('admin.view_strategies_control'))
    if not db: # Kiểm tra db
         flash("Lỗi DB.", "error")
         return redirect(url_for('admin.view_strategies_control'))

    # --- Lấy dữ liệu cần thiết cho form (cho cả GET và POST lỗi) ---
    strategy_details = None
    strategy_stages_for_dropdowns = [] # List stages của strategy này
    all_macros = []
    all_templates = []
    cancel_url = url_for('admin.view_strategies_control') # Fallback

    try:
        strategy_details = db.get_strategy_details(strategy_id)
        if not strategy_details or strategy_details.get('strategy_type') != 'control':
            flash("Strategy không hợp lệ hoặc không phải loại 'control'.", "error")
            return redirect(url_for('admin.view_strategies_control'))
        cancel_url = url_for('admin.view_strategy_stages_control', strategy_id=strategy_id)

        # Lấy stages của strategy này
        raw_strategy_stages = db.get_stages_for_strategy(strategy_id)
        if raw_strategy_stages is None:
            flash(f"Lỗi khi tải danh sách Stages cho strategy {strategy_id}.", "error")
            strategy_stages_for_dropdowns = []
        elif isinstance(raw_strategy_stages, list):
            # === SẮP XẾP STAGES Ở ĐÂY BẰNG PYTHON ===
            try:
                 # Sắp xếp list các dictionary theo key 'stage_id'
                 strategy_stages_for_dropdowns = sorted(raw_strategy_stages, key=lambda x: x.get('stage_id', ''))
                 print(f"DEBUG: Sorted stages for dropdowns: {[s.get('stage_id') for s in strategy_stages_for_dropdowns]}") # Log thứ tự sau sort
            except Exception as sort_err:
                 current_app.logger.error(f"Error sorting strategy stages: {sort_err}", exc_info=True)
                 strategy_stages_for_dropdowns = raw_strategy_stages # Dùng list chưa sort nếu lỗi
        else:
             strategy_stages_for_dropdowns = []

        # Lấy macro definitions
        temp_macros, _ = db.get_all_macro_definitions(page=1, per_page=1000)
        all_macros = temp_macros or []

        # Lấy response templates
        all_templates = db.get_all_template_refs_with_details()
        if all_templates is None:
            flash("Lỗi khi tải danh sách Response Templates.", "warning")
            all_templates = []

    except Exception as e:
        current_app.logger.error(f"ERROR (add_transition_control): Lỗi tải dữ liệu cho form: {e}", exc_info=True)
        flash(f"Lỗi tải dữ liệu cho form: {e}", "error")
        
        # Các list sẽ là list rỗng

    # Lấy hằng số từ config (Đảm bảo đã import config)
    valid_intents = getattr(config, 'VALID_INTENTS_FOR_TRANSITION', ['any', 'on_stage_entry']) # Thêm giá trị mặc định an toàn
    valid_condition_types = getattr(config, 'VALID_CONDITION_TYPES', []) # Thêm giá trị mặc định an toàn

    title = f"Thêm Control Transition cho Strategy {strategy_id}"

    # --- Xử lý POST ---
    if request.method == 'POST':
        # === KHỞI TẠO BIẾN errors ===
        errors = []

        # Lấy dữ liệu từ form (lấy cả current_stage_id ở đây)
        current_stage_id = request.form.get('current_stage_id') # <<< Lấy ở đây
        user_intent = request.form.get('user_intent')
        condition_type = request.form.get('condition_type', '').strip()
        condition_value = request.form.get('condition_value', '').strip()
        next_stage_id = request.form.get('next_stage_id', '').strip()
        priority_str = request.form.get('priority', '0').strip()
        action_macro_code = request.form.get('action_macro_code', '').strip()
        action_params_str = request.form.get('action_params_str', '{}').strip()
        response_template_ref = request.form.get('response_template_ref', '').strip() # Lấy response template
        form_strategy_id = request.form.get('strategy_id') # Lấy từ hidden input
        notes = request.form.get('notes', '').strip()
        # Lấy dữ liệu LOOP
        loop_type = request.form.get('loop_type', '').strip()
        loop_count_str = request.form.get('loop_count', '').strip()
        loop_condition_type = request.form.get('loop_condition_type', '').strip()
        loop_condition_value = request.form.get('loop_condition_value', '').strip()
        loop_target_selector_str = request.form.get('loop_target_selector_str', '').strip()
        loop_variable_name = request.form.get('loop_variable_name', '').strip()


        # --- Validate ---
        if not current_stage_id: errors.append("Current Stage là bắt buộc.") # <<< Giờ biến này đã được định nghĩa
        if not user_intent: errors.append("User Intent/Trigger là bắt buộc.")
        if not form_strategy_id or form_strategy_id != strategy_id: errors.append("Lỗi Strategy ID.")
        priority = 0
        try: priority = int(priority_str)
        except ValueError: errors.append("Priority phải là số nguyên.")

        # Validate JSON Params
        params_dict = {}
        if action_macro_code and action_params_str and action_params_str.strip() and action_params_str != '{}':
             try:
                  params_dict = json.loads(action_params_str)
                  if not isinstance(params_dict, dict): errors.append("Action Params phải là JSON object.")
             except json.JSONDecodeError: errors.append("Action Params JSON không hợp lệ.")

        # Validate Loop Target Selector JSON
        loop_selector_dict = None
        if loop_target_selector_str and loop_target_selector_str.strip() and loop_target_selector_str != '{}':
            try:
                loop_selector_dict = json.loads(loop_target_selector_str)
            except json.JSONDecodeError: errors.append("Loop Target Selector JSON không hợp lệ.")

        # Validate dữ liệu Loop khác
        loop_count = None
        if loop_type == 'repeat_n':
            if not loop_count_str: errors.append("Cần nhập Số lần lặp.")
            else:
                try: loop_count = int(loop_count_str); assert loop_count >= 1
                except (ValueError, AssertionError): errors.append("Số lần lặp phải là số nguyên > 0.")
        elif loop_type == 'while_condition_met':
            if not loop_condition_type: errors.append('Cần chọn Điều kiện Lặp.')
        elif loop_type == 'for_each':
             if not loop_target_selector_str or not loop_selector_dict: errors.append("Cần nhập Selector Mục tiêu Lặp hợp lệ cho For Each.")
             if not loop_variable_name: errors.append("Cần nhập Tên biến lưu phần tử lặp cho For Each.")
        elif loop_type: errors.append(f"Loại vòng lặp '{loop_type}' chưa được hỗ trợ.")


        # Nếu có lỗi validation
        if errors:
            for error in errors: flash(error, "warning")
            # Render lại template mới: admin_add_transition_control.html
            return render_template('admin_add_transition_control.html',
                                   title=title + " (Lỗi)", strategy_id=strategy_id, cancel_url=cancel_url,
                                   current_stage_id_prefill=current_stage_id, # <<< Truyền current_stage_id đã lấy từ form
                                   strategy_stages=strategy_stages_for_dropdowns, # Dùng list của strategy này
                                   all_stages=strategy_stages_for_dropdowns,      # Dùng list control stages
                                   all_macros=all_macros, all_templates=all_templates,
                                   valid_intents=valid_intents, valid_condition_types=valid_condition_types,
                                   current_data=request.form), 400 # Truyền request.form để giữ lại các giá trị khác

        # --- Gọi hàm DB add_new_transition ---
        try:
            success, error_msg = db.add_new_transition(
                strategy_id=strategy_id, # Đã thêm strategy_id vào hàm DB
                current_stage_id=current_stage_id,
                user_intent=user_intent,
                priority=priority,
                condition_type=condition_type if condition_type else None,
                condition_value=condition_value if condition_value else None,
                next_stage_id=next_stage_id if next_stage_id else None,
                action_macro_code=action_macro_code if action_macro_code else None,
                action_params_str=action_params_str if (action_params_str and action_params_str.strip() and action_params_str != '{}') else None,
                response_template_ref=response_template_ref if response_template_ref else None, # Thêm response template
                loop_type=loop_type if loop_type else None,
                loop_count=loop_count, # int hoặc None
                loop_condition_type=loop_condition_type if loop_condition_type else None,
                loop_condition_value=loop_condition_value if loop_condition_value else None,
                loop_target_selector_str=loop_target_selector_str if loop_target_selector_str and loop_target_selector_str.strip() and loop_target_selector_str != '{}' else None,
                loop_variable_name=loop_variable_name if loop_variable_name else None,
                notes=notes if notes else None
            )

            if success:
                flash('Thêm control transition thành công!', 'success')
                return redirect(cancel_url) # Redirect về trang chi tiết control
            else:
                flash(f'Thêm control transition thất bại: {error_msg or "Lỗi không xác định."}', 'error')
                # Render lại template mới: admin_add_transition_control.html
                return render_template('admin_add_transition_control.html',
                                       title=title + " (Lỗi DB)", strategy_id=strategy_id, cancel_url=cancel_url,
                                       current_stage_id_prefill=current_stage_id,
                                       strategy_stages=strategy_stages_for_dropdowns, # <<< List đã sắp xếp
                                       all_stages=strategy_stages_for_dropdowns,      # <<< List đã sắp xếp
                                       all_macros=all_macros, all_templates=all_templates,
                                       valid_intents=valid_intents, valid_condition_types=valid_condition_types,
                                       current_data=request.form)
        except Exception as e:
             current_app.logger.error(f"Lỗi nghiêm trọng khi thêm control transition: {e}", exc_info=True)
             flash(f"Lỗi không mong muốn: {e}", "error")
             # Render lại template mới: admin_add_transition_control.html
             return render_template('admin_add_transition_control.html',
                                    title=title + " (Lỗi Exception)", strategy_id=strategy_id, cancel_url=cancel_url,
                                    current_stage_id_prefill=current_stage_id,
                                    strategy_stages=strategy_stages_for_dropdowns, # <<< List đã sắp xếp
                                    all_stages=strategy_stages_for_dropdowns,      # <<< List đã sắp xếp
                                    all_macros=all_macros, all_templates=all_templates,
                                    valid_intents=valid_intents, valid_condition_types=valid_condition_types,
                                    current_data=request.form)

    # --- GET request ---
    # Render template, truyền các list đã lấy cho dropdowns
    return render_template('admin_add_transition_control.html',
                           title=title, strategy_id=strategy_id, cancel_url=cancel_url,
                           current_stage_id_prefill=current_stage_id_prefill, # Cho GET request
                           strategy_stages=strategy_stages_for_dropdowns, # <<< List đã sắp xếp
                           all_stages=strategy_stages_for_dropdowns,      # <<< List đã sắp xếp
                           all_macros=all_macros, all_templates=all_templates,
                           valid_intents=valid_intents, valid_condition_types=valid_condition_types)

@admin_bp.route('/transitions/<int:transition_id>/edit-control', methods=['GET', 'POST'])
def edit_transition_control(transition_id):
    """Hiển thị form và xử lý sửa Control Transition.
       Đã sửa lỗi AttributeError và đảm bảo truyền đúng stage list.
    """
    if not db: flash("Lỗi DB.", "error"); return redirect(url_for('admin.view_strategies_control'))

    # --- Lấy dữ liệu gốc của transition ---
    transition = db.get_transition_details(transition_id)
    if not transition:
        flash(f"Không tìm thấy transition ID {transition_id}.", "error")
        return redirect(url_for('admin.view_strategies_control'))

    strategy_id = transition.get('strategy_id')
    if not strategy_id:
        flash("Lỗi: Transition không có strategy_id liên kết.", "error")
        return redirect(url_for('admin.view_strategies_control'))

    # --- Lấy dữ liệu cần thiết cho form ---
    strategy_details = None
    strategy_stages_for_dropdowns = [] # <<< Dùng list này cho CẢ HAI dropdown
    all_macros = []
    all_templates = []
    cancel_url = url_for('admin.view_strategies_control') # Fallback

    try:
        strategy_details = db.get_strategy_details(strategy_id)
        if not strategy_details or strategy_details.get('strategy_type') != 'control':
            flash("Transition này không thuộc về một Control Strategy hợp lệ.", "error")
            return redirect(url_for('admin.view_strategies_control'))
        cancel_url = url_for('admin.view_strategy_stages_control', strategy_id=strategy_id)

        # === LẤY STAGES CHỈ CỦA STRATEGY NÀY ===
        strategy_stages_for_dropdowns = db.get_stages_for_strategy(strategy_id) or []
        if strategy_stages_for_dropdowns is None:
            flash(f"Lỗi khi tải danh sách Stages cho strategy {strategy_id}.", "error")
            strategy_stages_for_dropdowns = []
        # === KẾT THÚC LẤY STAGES ===

        # Lấy macro definitions
        temp_macros, _ = db.get_all_macro_definitions(page=1, per_page=1000)
        all_macros = temp_macros or []

        # Lấy response templates
        all_templates = db.get_all_template_refs_with_details() # Đảm bảo hàm này tồn tại
        if all_templates is None:
            flash("Lỗi khi tải danh sách Response Templates.", "warning")
            all_templates = []

    except Exception as e:
        current_app.logger.error(f"ERROR (edit_transition_control): Lỗi tải dữ liệu cho form: {e}", exc_info=True)
        flash(f"Lỗi tải dữ liệu cho form: {e}", "error")
        # Các list sẽ là list rỗng

    # === ĐỊNH NGHĨA LIST VALID Ở ĐÂY (Thay vì dùng config) ===
    valid_intents=['any', 'on_stage_entry', 'element_clicked', 'element_not_found', 'user_input_match:*', 'api_call_success', 'api_call_error'] # Ví dụ
    valid_condition_types=['element_visible', 'element_not_visible', 'variable_check'] # Ví dụ

    title = f"Sửa Control Transition #{transition_id}"

    # --- Xử lý POST (logic validate và gọi DB update_transition giữ nguyên) ---
    if request.method == 'POST':
        # Khởi tạo errors
        errors = []

        # Lấy dữ liệu từ form
        current_stage_id = request.form.get('current_stage_id')
        user_intent = request.form.get('user_intent')
        condition_type = request.form.get('condition_type', '').strip()
        condition_value = request.form.get('condition_value', '').strip()
        next_stage_id = request.form.get('next_stage_id', '').strip()
        priority_str = request.form.get('priority', '0').strip()
        action_macro_code = request.form.get('action_macro_code', '').strip()
        action_params_str = request.form.get('action_params_str', '{}').strip()
        response_template_ref = request.form.get('response_template_ref', '').strip() # Lấy response template
        notes = request.form.get('notes', '').strip()
        # Lấy dữ liệu LOOP
        loop_type = request.form.get('loop_type', '').strip()
        loop_count_str = request.form.get('loop_count', '').strip()
        loop_condition_type = request.form.get('loop_condition_type', '').strip()
        loop_condition_value = request.form.get('loop_condition_value', '').strip()
        loop_target_selector_str = request.form.get('loop_target_selector_str', '').strip()
        loop_variable_name = request.form.get('loop_variable_name', '').strip()

        # --- Validate ---
        if not current_stage_id: errors.append("Current Stage là bắt buộc.")
        if not user_intent: errors.append("User Intent/Trigger là bắt buộc.")
        priority = 0
        try: priority = int(priority_str)
        except ValueError: errors.append("Priority phải là số nguyên.")
        # ... (Validate JSON Params, Loop JSON, Loop Count như cũ) ...
        params_dict = {} # Validate JSON Params
        if action_macro_code and action_params_str and action_params_str.strip() and action_params_str != '{}':
             try: params_dict = json.loads(action_params_str); assert isinstance(params_dict, dict)
             except: errors.append("Action Params JSON không hợp lệ.")
        loop_selector_dict = None # Validate Loop Selector JSON
        if loop_target_selector_str and loop_target_selector_str.strip() and loop_target_selector_str != '{}':
             try: loop_selector_dict = json.loads(loop_target_selector_str)
             except: errors.append("Loop Target Selector JSON không hợp lệ.")
        loop_count = None # Validate Loop Count
        if loop_type == 'repeat_n':
             if not loop_count_str: errors.append("Cần nhập Số lần lặp.")
             else:
                 try: loop_count = int(loop_count_str); assert loop_count >= 1
                 except: errors.append("Số lần lặp phải là số nguyên > 0.")
        # ... (Validate loop fields khác nếu cần) ...


        # Nếu có lỗi validation
        if errors:
            for error in errors: flash(error, "warning")
            # Render lại template edit, truyền đúng list stages cho cả hai dropdown
            return render_template('admin_edit_transition_control.html',
                                   title=title + " (Lỗi)", transition=transition, # Dữ liệu gốc
                                   strategy_id=strategy_id, cancel_url=cancel_url,
                                   strategy_stages=strategy_stages_for_dropdowns, # <<< Dùng list này
                                   all_stages=strategy_stages_for_dropdowns,      # <<< Dùng list này
                                   all_macros=all_macros, all_templates=all_templates,
                                   valid_intents=valid_intents, valid_condition_types=valid_condition_types,
                                   current_data=request.form), 400

        # --- Gọi hàm DB Update (truyền đủ các trường) ---
        try:
            success, error_msg = db.update_transition(
                transition_id=transition_id,
                current_stage_id=current_stage_id,
                user_intent=user_intent,
                next_stage_id=next_stage_id if next_stage_id else None,
                priority=priority,
                response_template_ref=response_template_ref if response_template_ref else None,
                action_macro_code=action_macro_code if action_macro_code else None,
                action_params_str=action_params_str if (action_params_str and action_params_str.strip() and action_params_str != '{}') else None,
                condition_type=condition_type if condition_type else None,
                condition_value=condition_value if condition_value else None,
                loop_type=loop_type if loop_type else None,
                loop_count=loop_count,
                loop_condition_type=loop_condition_type if loop_condition_type else None,
                loop_condition_value=loop_condition_value if loop_condition_value else None,
                loop_target_selector_str=loop_target_selector_str if loop_target_selector_str and loop_target_selector_str.strip() and loop_target_selector_str != '{}' else None,
                loop_variable_name=loop_variable_name if loop_variable_name else None
                # notes=notes if notes else None # Cần sửa hàm db.update_transition nếu muốn lưu notes
            )

            if success:
                flash(f'Cập nhật control transition #{transition_id} thành công!', 'success')
                return redirect(cancel_url) # Redirect về trang chi tiết control
            else:
                flash(f'Cập nhật control transition thất bại: {error_msg or "Lỗi không xác định."}', 'error')
                 # Render lại template edit
                return render_template('admin_edit_transition_control.html',
                                       title=title + " (Lỗi DB)", transition=transition, # Dữ liệu gốc
                                       strategy_id=strategy_id, cancel_url=cancel_url,
                                       strategy_stages=strategy_stages_for_dropdowns, # <<< Dùng list này
                                       all_stages=strategy_stages_for_dropdowns,      # <<< Dùng list này
                                       all_macros=all_macros, all_templates=all_templates,
                                       valid_intents=valid_intents, valid_condition_types=valid_condition_types,
                                       current_data=request.form)
        except Exception as e:
             current_app.logger.error(f"Lỗi nghiêm trọng khi sửa control transition {transition_id}: {e}", exc_info=True)
             flash(f"Lỗi không mong muốn: {e}", "error")
             # Render lại template edit
             return render_template('admin_edit_transition_control.html',
                                    title=title + " (Lỗi Exception)", transition=transition, # Dữ liệu gốc
                                    strategy_id=strategy_id, cancel_url=cancel_url,
                                    strategy_stages=strategy_stages_for_dropdowns, # <<< Dùng list này
                                    all_stages=strategy_stages_for_dropdowns,      # <<< Dùng list này
                                    all_macros=all_macros, all_templates=all_templates,
                                    valid_intents=valid_intents, valid_condition_types=valid_condition_types,
                                    current_data=request.form)

    # --- GET request ---
    # Render template, truyền cùng list stages cho cả hai dropdown
    return render_template('admin_edit_transition_control.html',
                           title=title, transition=transition, strategy_id=strategy_id, cancel_url=cancel_url,
                           strategy_stages=strategy_stages_for_dropdowns, # <<< Dùng list này
                           all_stages=strategy_stages_for_dropdowns,      # <<< Dùng list này
                           all_macros=all_macros, all_templates=all_templates,
                           valid_intents=valid_intents, valid_condition_types=valid_condition_types)


@admin_bp.route('/transitions/add-language', methods=['GET', 'POST'])
def add_transition_language():
    """Hiển thị form và xử lý thêm Transition mới cho Language Strategy."""
    # === LẤY strategy_id TỪ GET (khi bấm nút) HOẶC POST (khi submit form) ===
    strategy_id = request.args.get('strategy_id', request.form.get('strategy_id'))
    # Lấy current_stage_id nếu có từ GET để điền sẵn
    current_stage_id_prefill = request.args.get('current_stage_id')

    # --- Kiểm tra strategy_id ---
    if not strategy_id:
        flash("Cần strategy_id.", "error") # <<< LỖI BẠN GẶP PHẢI
        return redirect(url_for('admin.view_strategies_language')) # Redirect về list language
    if not db:
         flash("Lỗi DB.", "error")
         return redirect(url_for('admin.view_strategies_language'))

    # --- Lấy dữ liệu cần thiết cho form ---
    strategy_details = None
    strategy_stages_for_dropdowns = [] # Stages của strategy này
    all_templates = [] # Templates cho dropdown Response Ref
    cancel_url = url_for('admin.view_strategies_language') # Fallback

    try:
        strategy_details = db.get_strategy_details(strategy_id)
        if not strategy_details or strategy_details.get('strategy_type') != 'language':
            flash("Strategy không hợp lệ hoặc không phải loại 'language'.", "error")
            return redirect(url_for('admin.view_strategies_language'))
        cancel_url = url_for('admin.view_strategy_stages_language', strategy_id=strategy_id)

        # Lấy stages của strategy này (và sắp xếp)
        raw_strategy_stages = db.get_stages_for_strategy(strategy_id)
        if raw_strategy_stages is None:
            flash(f"Lỗi khi tải danh sách Stages cho strategy {strategy_id}.", "error")
            strategy_stages_for_dropdowns = []
        elif isinstance(raw_strategy_stages, list):
            try:
                 strategy_stages_for_dropdowns = sorted(raw_strategy_stages, key=lambda x: x.get('stage_id', ''))
            except Exception as sort_err:
                 current_app.logger.error(f"Error sorting language strategy stages: {sort_err}", exc_info=True)
                 strategy_stages_for_dropdowns = raw_strategy_stages
        else:
             strategy_stages_for_dropdowns = []

        # Lấy response templates
        all_templates = db.get_all_template_refs_with_details()
        if all_templates is None:
            flash("Lỗi khi tải danh sách Response Templates.", "warning")
            all_templates = []

    except Exception as e:
        current_app.logger.error(f"ERROR (add_transition_language): Lỗi tải dữ liệu cho form: {e}", exc_info=True)
        flash(f"Lỗi tải dữ liệu cho form: {e}", "error")
        strategy_stages_for_dropdowns = []
        all_templates = []

    # Định nghĩa list valid intents/conditions cho language
    valid_intents = ['any', 'on_stage_entry', 'keyword_match:*', 'sentiment_positive', 'sentiment_negative'] # Ví dụ
    valid_condition_types = ['intent_confidence_above', 'entity_detected', 'variable_check'] # Ví dụ

    title = f"Thêm Language Transition cho Strategy {strategy_id}"

    # --- Xử lý POST ---
    if request.method == 'POST':
        errors = []
        # Lấy dữ liệu từ form
        current_stage_id = request.form.get('current_stage_id')
        user_intent = request.form.get('user_intent')
        condition_type = request.form.get('condition_type', '').strip()
        condition_value = request.form.get('condition_value', '').strip()
        next_stage_id = request.form.get('next_stage_id', '').strip()
        priority_str = request.form.get('priority', '0').strip()
        response_template_ref = request.form.get('response_template_ref', '').strip()
        notes = request.form.get('notes', '').strip()
        # strategy_id đã được lấy ở đầu hàm

        # --- Validate ---
        if not current_stage_id: errors.append("Current Stage là bắt buộc.")
        if not user_intent: errors.append("User Intent/Trigger là bắt buộc.")
        if not response_template_ref: errors.append("Response Template Ref là bắt buộc cho Language Transition.") # Bắt buộc cho language
        priority = 0
        try: priority = int(priority_str)
        except ValueError: errors.append("Priority phải là số nguyên.")

        if errors:
            for error in errors: flash(error, "warning")
            # Render lại form add language transition
            return render_template('admin_add_transition_language.html',
                                   title=title + " (Lỗi)", strategy_id=strategy_id, cancel_url=cancel_url,
                                   current_stage_id_prefill=current_stage_id,
                                   strategy_stages=strategy_stages_for_dropdowns, # List đã sắp xếp
                                   all_stages=strategy_stages_for_dropdowns,      # List đã sắp xếp
                                   all_templates=all_templates,
                                   valid_intents=valid_intents, valid_condition_types=valid_condition_types,
                                   current_data=request.form), 400

        # --- Gọi hàm DB add_new_transition ---
        # Đặt các tham số không dùng (action, loop) là None
        try:
            success, error_msg = db.add_new_transition(
                strategy_id=strategy_id,
                current_stage_id=current_stage_id,
                user_intent=user_intent,
                priority=priority,
                condition_type=condition_type if condition_type else None,
                condition_value=condition_value if condition_value else None,
                next_stage_id=next_stage_id if next_stage_id else None,
                action_macro_code=None, # Không dùng cho language
                action_params_str=None, # Không dùng cho language
                response_template_ref=response_template_ref, # Dùng cho language
                loop_type=None, # Không dùng cho language
                loop_count=None, loop_condition_type=None, loop_condition_value=None,
                loop_target_selector_str=None, loop_variable_name=None,
                notes=notes if notes else None
            )

            if success:
                flash('Thêm language transition thành công!', 'success')
                return redirect(cancel_url) # Redirect về trang chi tiết language
            else:
                flash(f'Thêm language transition thất bại: {error_msg or "Lỗi không xác định."}', 'error')
                # Render lại form add language transition
                return render_template('admin_add_transition_language.html',
                                       title=title + " (Lỗi DB)", strategy_id=strategy_id, cancel_url=cancel_url,
                                       current_stage_id_prefill=current_stage_id,
                                       strategy_stages=strategy_stages_for_dropdowns,
                                       all_stages=strategy_stages_for_dropdowns,
                                       all_templates=all_templates,
                                       valid_intents=valid_intents, valid_condition_types=valid_condition_types,
                                       current_data=request.form)
        except Exception as e:
             current_app.logger.error(f"Lỗi nghiêm trọng khi thêm language transition: {e}", exc_info=True)
             flash(f"Lỗi không mong muốn: {e}", "error")
             # Render lại form add language transition
             return render_template('admin_add_transition_language.html',
                                    title=title + " (Lỗi Exception)", strategy_id=strategy_id, cancel_url=cancel_url,
                                    current_stage_id_prefill=current_stage_id,
                                    strategy_stages=strategy_stages_for_dropdowns,
                                    all_stages=strategy_stages_for_dropdowns,
                                    all_templates=all_templates,
                                    valid_intents=valid_intents, valid_condition_types=valid_condition_types,
                                    current_data=request.form)

    # --- GET request ---
    # Render template, truyền các list đã lấy và sắp xếp
    return render_template('admin_add_transition_language.html',
                           title=title, strategy_id=strategy_id, cancel_url=cancel_url,
                           current_stage_id_prefill=current_stage_id_prefill, # Cho GET request
                           strategy_stages=strategy_stages_for_dropdowns, # List đã sắp xếp
                           all_stages=strategy_stages_for_dropdowns,      # List đã sắp xếp
                           all_templates=all_templates,
                           valid_intents=valid_intents, valid_condition_types=valid_condition_types)

@admin_bp.route('/transitions/<int:transition_id>/edit-language', methods=['GET', 'POST'])
def edit_transition_language(transition_id):
    """Sửa transition cho Language Strategy."""
    transition = db.get_transition_details(transition_id) # Hàm này đã lấy cả template_ref
    if not transition: flash(f"Ko tìm thấy transition ID {transition_id}.", "error"); return redirect(url_for('admin.view_strategies_language'))
    strategy_id_redirect = transition.get('strategy_id')
    strategy_details = db.get_strategy_details(strategy_id_redirect)
    if not strategy_details or strategy_details.get('strategy_type') != 'language':
         flash("Transition này không thuộc về Language Strategy.", "error")
         return redirect(url_for('admin.view_strategies_language'))

    # Lấy dữ liệu dropdown
    strategy_stages = db.get_stages_for_strategy(strategy_id_redirect) or []
    all_stages = db.get_all_stages() or []
    all_templates = db.get_all_template_refs() or []

    if request.method == 'POST':
        current_stage_id = request.form.get('current_stage_id')
        user_intent = request.form.get('user_intent')
        next_stage_id = request.form.get('next_stage_id')
        priority_str = request.form.get('priority', '0')
        response_template_ref = request.form.get('response_template_ref') # <<< Lấy template ref

        # Validate
        if not current_stage_id or not user_intent: flash("Current Stage, Intent bắt buộc.", "warning"); #... return render_template ...
        try: priority = int(priority_str)
        except ValueError: flash("Priority phải là số.", "warning"); #... return render_template ...

        # Gọi hàm update DB (truyền None cho các trường control)
        success, error_msg = db.update_transition(
            transition_id, current_stage_id, user_intent, next_stage_id, priority,
            response_template_ref if response_template_ref else None, # <<< Truyền template ref
            None, None, None, None # action_macro_code, params, condition = None
        )

        if success:
            flash('Cập nhật language transition thành công!', 'success')
            return redirect(url_for('admin.view_strategy_stages_language', strategy_id=strategy_id_redirect))
        else:
            flash(f'Cập nhật language transition thất bại: {error_msg or "Lỗi."}', 'error')
            # Render lại form language edit
            return render_template('admin_edit_transition_language.html', title=f"Sửa Language Transition {transition_id} (Lỗi DB)",
                                   transition=transition, strategy_stages=strategy_stages, all_stages=all_stages, all_templates=all_templates,
                                   valid_intents=VALID_INTENTS_FOR_TRANSITION, current_data=request.form)

    # GET request
    return render_template('admin_edit_transition_language.html', title=f"Sửa Language Transition {transition_id}",
                           transition=transition, # Đã chứa response_template_ref
                           strategy_stages=strategy_stages, all_stages=all_stages, all_templates=all_templates,
                           valid_intents=VALID_INTENTS_FOR_TRANSITION)


# --- Route Xóa Transition (Có thể dùng chung) ---
# app/admin_routes.py
@admin_bp.route('/transitions/<int:transition_id>/delete', methods=['POST'])
def delete_transition(transition_id):
    """Xóa một transition và redirect về trang chi tiết strategy phù hợp."""
    logger = current_app.logger if current_app else print # Lấy logger
    logger.info(f"--- DEBUG (delete_transition): Received request for transition ID: {transition_id} ---")
    strategy_id_redirect = None
    strategy_type_redirect = 'unknown' # Khởi tạo là unknown
    redirect_endpoint = None # Khởi tạo endpoint để chuyển về trang chi tiết
    list_redirect_endpoint = 'admin.view_strategies_language' # Default fallback về list language

    # --- Cố gắng lấy thông tin STRATEGY GỐC TRƯỚC KHI XÓA ---
    try:
        # Hàm get_transition_details cần trả về dict có strategy_id
        transition_details = db.get_transition_details(transition_id)
        logger.debug(f"DEBUG (delete_transition): Fetched transition_details: {transition_details}")

        if transition_details:
            strategy_id_redirect = transition_details.get('strategy_id')
            logger.debug(f"DEBUG (delete_transition): Found parent strategy_id: {strategy_id_redirect}")
            if strategy_id_redirect:
                 # Lấy thêm thông tin strategy để biết type
                 strategy_info = db.get_strategy_details(strategy_id_redirect)
                 logger.debug(f"DEBUG (delete_transition): Fetched strategy_info: {strategy_info}")
                 if strategy_info:
                      strategy_type_redirect = strategy_info.get('strategy_type', 'unknown') # Lấy type
                      logger.debug(f"DEBUG (delete_transition): Determined strategy_type: {strategy_type_redirect}")

                      # === SỬA LẠI LOGIC XÁC ĐỊNH ENDPOINT ===
                      # Xác định endpoint trang chi tiết VÀ trang danh sách dựa trên type
                      if strategy_type_redirect == 'control':
                           redirect_endpoint = 'admin.view_strategy_stages_control'
                           list_redirect_endpoint = 'admin.view_strategies_control'
                      elif strategy_type_redirect == 'language':
                           redirect_endpoint = 'admin.view_strategy_stages_language'
                           list_redirect_endpoint = 'admin.view_strategies_language'
                      elif strategy_type_redirect == 'mainloop': # <<< THÊM CHECK MAINLOOP
                           redirect_endpoint = 'admin.view_strategy_stages_mainloop' # <<< Endpoint chi tiết mainloop
                           list_redirect_endpoint = 'admin.view_strategies_mainloop' # <<< Endpoint list mainloop
                      else: # Nếu strategy_type không xác định
                           logger.warning(f"WARN (delete_transition): Unknown strategy type '{strategy_type_redirect}'. Cannot redirect to detail.")
                           redirect_endpoint = None # Không có trang chi tiết cụ thể
                           # Giữ list_redirect_endpoint là default (language) hoặc thay đổi nếu muốn
                      # === KẾT THÚC SỬA LOGIC ===

                 else: # Không tìm thấy strategy details
                      logger.warning(f"WARN (delete_transition): Could not find strategy details for ID '{strategy_id_redirect}'. Cannot redirect to detail.")
                      strategy_id_redirect = None # Đặt lại ID nếu strategy không tồn tại
            else: # Transition không có strategy_id
                 logger.warning(f"WARN (delete_transition): Transition {transition_id} has no associated strategy_id.")
                 strategy_id_redirect = None
        else: # Không tìm thấy transition
            logger.error(f"ERROR (delete_transition): Could not find transition details for ID {transition_id}. Cannot determine redirect target.")
            strategy_id_redirect = None

    except Exception as e_fetch:
        logger.error(f"ERROR (delete_transition): Exception while fetching details before delete: {e_fetch}", exc_info=True)
        strategy_id_redirect = None # Reset nếu có lỗi khi fetch

    # --- Thực hiện Xóa ---
    delete_success = False
    error_msg_delete = None
    try:
        # Hàm db.delete_transition trả về tuple (success, error_msg)
        delete_success, error_msg_delete = db.delete_transition(transition_id)
        if delete_success:
            flash(f"Đã xóa transition ID {transition_id}.", 'success')
            logger.info(f"INFO (delete_transition): Successfully deleted transition {transition_id}.")
        else:
            flash(f"Xóa transition ID {transition_id} thất bại: {error_msg_delete or 'ID không tồn tại?'}", 'error')
            logger.error(f"ERROR (delete_transition): Failed to delete transition {transition_id}: {error_msg_delete}")
    except Exception as e_delete:
        logger.error(f"Lỗi nghiêm trọng khi xóa transition {transition_id}: {e_delete}", exc_info=True)
        flash(f"Lỗi không mong muốn khi xóa transition: {e_delete}", "error")

    # --- Logic Chuyển hướng (Đã sửa) ---
    # Ưu tiên redirect về trang chi tiết nếu có đủ thông tin
    if strategy_id_redirect and redirect_endpoint:
        logger.info(f"INFO (delete_transition): Redirecting to detail page: {redirect_endpoint} for strategy {strategy_id_redirect}")
        return redirect(url_for(redirect_endpoint, strategy_id=strategy_id_redirect))
    else:
        # Nếu không đủ thông tin về trang chi tiết, fallback về trang danh sách PHÙ HỢP
        logger.warning(f"WARN (delete_transition): Fallback redirect needed. strategy_id={strategy_id_redirect}, type={strategy_type_redirect}, detail_endpoint={redirect_endpoint}")
        flash("Đã xóa transition. Không thể xác định trang chi tiết để quay lại, chuyển về trang danh sách.", "info")
        logger.info(f"INFO (delete_transition): Fallback redirecting to list page: {list_redirect_endpoint}")
        # <<< SỬA LẠI FALLBACK: Dùng list_redirect_endpoint đã xác định ở trên >>>
        return redirect(url_for(list_redirect_endpoint))

# --- ROUTE MỚI ĐỂ XEM JSON PACKAGE ---
@admin_bp.route('/strategies/<strategy_id>/package-json')
def view_strategy_package_json(strategy_id):
    """
    Biên dịch và trả về gói JSON thực thi cho client của một Control Strategy.
    Đã sửa lỗi TypeError khi gọi compile_strategy_package.
    """
    logger = current_app.logger if current_app else print
    if not db:
        return jsonify({"error": "Database module not available"}), 500
    if not phone_controller:
         logger.error("Phone controller is not available!")
         return jsonify({"error": "Server internal error (controller)."}), 500

    try:
        # Kiểm tra strategy tồn tại và là loại control
        strategy_details = db.get_strategy_details(strategy_id)
        if not strategy_details:
            return jsonify({"error": f"Strategy ID '{strategy_id}' not found."}), 404
        # Bạn có thể bỏ qua kiểm tra type nếu muốn xem package cho mọi loại
        # if strategy_details.get('strategy_type') != 'control':
        #      return jsonify({"error": f"Strategy '{strategy_id}' is not a Control strategy."}), 400

        # === SỬA LẠI CÁCH GỌI HÀM BIÊN DỊCH ===
        # Gọi hàm compile_strategy_package chỉ với strategy_id
        # theo đúng định nghĩa trong phone/controller.py
        logger.info(f"Attempting to compile package for strategy: {strategy_id}")
        package_data = phone_controller.compile_strategy_package(
            strategy_id=strategy_id
            # <<< BỎ CÁC THAM SỐ KHÔNG MONG MUỐN: account_context, device_info, assignment_id >>>
        )
        # === KẾT THÚC SỬA ĐỔI ===

        if package_data is None:
             logger.warning(f"compile_strategy_package returned None for strategy {strategy_id}")
             return jsonify({"error": f"Could not compile package for strategy '{strategy_id}'. It might be incomplete or have issues."}), 500

        # Xử lý datetime nếu cần (hàm convert_datetimes_to_iso nên có sẵn)
        serializable_package = convert_datetimes_to_iso(package_data)

        # Trả về JSON format đẹp
        response = current_app.response_class(
            response=json.dumps(serializable_package, indent=2, ensure_ascii=False),
            status=200,
            mimetype='application/json; charset=utf-8'
        )
        return response

    except Exception as e:
        # Bắt lỗi TypeError nếu hàm compile thay đổi signature trong tương lai
        if isinstance(e, TypeError) and 'unexpected keyword argument' in str(e):
             logger.error(f"ERROR generating package for {strategy_id}: Mismatch calling compile_strategy_package - {e}", exc_info=True)
             return jsonify({"error": f"Lỗi nội bộ: Tham số gọi hàm biên dịch không đúng. {e}"}), 500
        else:
             logger.error(f"ERROR generating strategy package JSON for {strategy_id}: {e}", exc_info=True)
             return jsonify({"error": f"Internal server error during package compilation: {e}"}), 500
# === QUẢN LÝ TASK ASSIGNMENTS ===

@admin_bp.route('/task-assignments', methods=['GET'])
def view_task_assignments():
    """Hiển thị danh sách Task Assignments với filter và phân trang."""
    page = request.args.get('page', 1, type=int)
    if page < 1: page = 1
    per_page = current_app.config.get('ADMIN_ITEMS_PER_PAGE', 15) # Có thể đặt số lượng khác

    # Lấy các tham số filter từ query string
    filters = {
        'status': request.args.get('status', '', type=str).strip(),
        'strategy_id': request.args.get('strategy_id', '', type=str).strip(),
        'device_id': request.args.get('device_id', '', type=str).strip(),
        'account_id': request.args.get('account_id', '', type=str).strip(),
        'search': request.args.get('search', '', type=str).strip() # Thêm filter tìm kiếm chung nếu cần
    }
    # Loại bỏ các filter rỗng
    active_filters = {k: v for k, v in filters.items() if v}

    assignments_list = []
    total_items = 0
    pagination_details = None

    try:
        # Gọi hàm CSDL get_all_task_assignments (đã có sẵn và trả về tuple)
        assignments_result, total_result = db.get_all_task_assignments(
            filters=active_filters, # Truyền các filter đang active
            page=page,
            per_page=per_page
        )

        if assignments_result is not None and total_result is not None:
            assignments_list = assignments_result
            total_items = total_result

            if total_items > 0:
                total_pages = math.ceil(total_items / per_page)
                if page > total_pages:
                     flash(f'Trang {page} không tồn tại. Hiển thị trang cuối ({total_pages}).', 'warning')
                     # Giữ lại các filter khi redirect
                     redirect_args = active_filters.copy()
                     redirect_args['page'] = total_pages
                     return redirect(url_for('.view_task_assignments', **redirect_args))

                pagination_details = {
                    'page': page, 'per_page': per_page, 'total_items': total_items,
                    'total_pages': total_pages, 'has_prev': page > 1, 'has_next': page < total_pages,
                    'prev_num': page - 1 if page > 1 else None,
                    'next_num': page + 1 if page < total_pages else None
                }
        else:
            current_app.logger.error("get_all_task_assignments trả về (None, None) trong view_task_assignments.")
            flash('Có lỗi xảy ra khi tải danh sách nhiệm vụ. Vui lòng kiểm tra log server.', 'error')

    except Exception as e:
        current_app.logger.error(f"Lỗi trong view_task_assignments khi gọi DB: {e}", exc_info=True)
        flash('Có lỗi nghiêm trọng xảy ra khi tải danh sách nhiệm vụ.', 'error')

    # Lấy thêm dữ liệu cho các dropdown filter (nếu cần)
    # strategies_for_select = db.get_all_strategies(strategy_type_filter='control') # Ví dụ
    # devices_for_select = db.get_all_devices_for_select() # Ví dụ

    return render_template('admin_task_assignments.html',
                           title="Quản lý Giao việc",
                           assignments=assignments_list,
                           pagination_details=pagination_details,
                           filters=filters # Truyền lại filters để hiển thị trạng thái đang lọc
                           # strategies_for_select=strategies_for_select, # Truyền dữ liệu dropdown
                           # devices_for_select=devices_for_select
                           )
# === THÊM TASK ASSIGNMENT MỚI ===

@admin_bp.route('/task-assignments/add', methods=['GET', 'POST'])
def add_task_assignment():
    """Hiển thị form và xử lý thêm Task Assignment mới."""
    title = "Thêm Task Assignment Mới"

    # --- Dữ liệu cần thiết cho form (cho cả GET và POST lỗi) ---
    devices = []
    control_strategies = []
    initial_accounts = [] # Để xử lý khi POST lỗi và đã chọn device
    current_data = {} # Để giữ lại dữ liệu form khi có lỗi
    error_occurred = False # Cờ báo lỗi để không lấy initial_accounts khi GET thành công

    try:
        devices = db.get_all_devices_for_select() or []
        control_strategies = db.get_all_strategies(strategy_type_filter='control') or []
    except Exception as e:
        current_app.logger.error(f"Lỗi tải dữ liệu dropdown cho form Add Assignment: {e}", exc_info=True)
        flash("Lỗi tải dữ liệu cần thiết cho form.", "error")
        # Có thể redirect hoặc hiển thị form rỗng

    # --- Xử lý POST ---
    if request.method == 'POST':
        current_data = request.form.to_dict() # Lấy dữ liệu form để hiển thị lại nếu lỗi
        error_occurred = True # Đánh dấu có khả năng lỗi để lấy initial_accounts
        try:
            device_id = request.form.get('device_id')
            device_account_id_str = request.form.get('device_account_id') # Value từ select là device_account_id
            strategy_id = request.form.get('strategy_id')
            priority_str = request.form.get('priority', '0')
            target_data_str = request.form.get('target_data', '{}').strip()
            notes = request.form.get('notes')
            schedule_start_str = request.form.get('schedule_start_time')
            schedule_end_str = request.form.get('schedule_end_time')

            # --- Validate dữ liệu ---
            errors = []
            device_account_id = None
            if not device_id: errors.append("Vui lòng chọn Thiết bị.")
            if not device_account_id_str: errors.append("Vui lòng chọn Tài khoản.")
            else:
                try: device_account_id = int(device_account_id_str)
                except ValueError: errors.append("Lỗi định dạng ID Tài khoản Thiết bị.")
            if not strategy_id: errors.append("Vui lòng chọn Chiến lược.")
            priority = 0
            try: priority = int(priority_str)
            except ValueError: errors.append("Độ ưu tiên phải là số nguyên.")

            # Validate JSON Target Data
            target_data_dict = None
            if target_data_str and target_data_str.strip() != '{}':
                try:
                    target_data_dict = json.loads(target_data_str)
                    if not isinstance(target_data_dict, dict): raise ValueError()
                except: errors.append("Target Data phải là JSON object hợp lệ hoặc {}.")

            # Validate và chuyển đổi thời gian (cần xử lý timezone cẩn thận hơn nếu cần)
            schedule_start_time = None
            if schedule_start_str:
                try: schedule_start_time = datetime.fromisoformat(schedule_start_str)
                except ValueError: errors.append("Định dạng thời gian bắt đầu không hợp lệ.")
            schedule_end_time = None
            if schedule_end_str:
                try: schedule_end_time = datetime.fromisoformat(schedule_end_str)
                except ValueError: errors.append("Định dạng thời gian kết thúc không hợp lệ.")
            if schedule_start_time and schedule_end_time and schedule_start_time >= schedule_end_time:
                 errors.append("Thời gian kết thúc phải sau thời gian bắt đầu.")

            # Nếu có lỗi validation
            if errors:
                for error in errors: flash(error, 'warning')
                # --- Lấy lại danh sách account cho device đã chọn để hiển thị lại form ---
                if device_id:
                    try: initial_accounts = db.get_accounts_for_device_select(device_id) or []
                    except Exception: pass # Bỏ qua nếu lỗi lấy account
                return render_template('admin_add_task_assignment.html', title=title + " (Lỗi)",
                                       devices=devices, control_strategies=control_strategies,
                                       initial_accounts=initial_accounts, # Truyền danh sách account ban đầu
                                       current_data=current_data), 400

            # --- Nếu không có lỗi validation, gọi hàm DB ---
            success, error_msg = db.add_task_assignment(
                device_account_id=device_account_id,
                strategy_id=strategy_id,
                priority=priority,
                target_data_str=target_data_str if target_data_dict is not None else None, # Chỉ truyền nếu hợp lệ và không rỗng
                notes=notes,
                schedule_start_time=schedule_start_time,
                schedule_end_time=schedule_end_time
            )

            if success:
                flash("Thêm Task Assignment thành công!", "success")
                return redirect(url_for('admin.view_task_assignments'))
            else:
                flash(f"Thêm Task Assignment thất bại: {error_msg or 'Lỗi không xác định.'}", "error")
                error_occurred = True # Đánh dấu lỗi DB

        except Exception as e:
            current_app.logger.error(f"Lỗi nghiêm trọng khi thêm task assignment: {e}", exc_info=True)
            flash(f"Lỗi không mong muốn: {e}", "error")
            error_occurred = True # Đánh dấu lỗi Exception

        # Nếu POST lỗi (validation hoặc DB), cần render lại form với dữ liệu
        if error_occurred and current_data.get('device_id'):
             try: initial_accounts = db.get_accounts_for_device_select(current_data['device_id']) or []
             except Exception: pass
        return render_template('admin_add_task_assignment.html', title=title + " (Lỗi)",
                               devices=devices, control_strategies=control_strategies,
                               initial_accounts=initial_accounts,
                               current_data=current_data)

    # --- Xử lý GET ---
    # Chỉ cần render form với dropdowns
    return render_template('admin_add_task_assignment.html', title=title,
                           devices=devices, control_strategies=control_strategies,
                           initial_accounts=initial_accounts, # Sẽ là [] khi GET thành công
                           current_data=current_data) # Sẽ là {} khi GET thành công


# --- API nội bộ cho Dropdown động ---
@admin_bp.route('/_internal/accounts_for_device', methods=['GET'])
def internal_get_accounts_for_device():
    """
    API nội bộ trả về danh sách account (dạng JSON) cho một device_id cụ thể.
    Được gọi bằng AJAX từ form Add Task Assignment.
    Endpoint này thuộc admin_bp vì nó phục vụ form admin.
    """
    device_id = request.args.get('device_id')
    current_app.logger.debug(f"AJAX request for accounts on device: {device_id}") # Thêm log debug
    if not device_id:
        return jsonify({"error": "Missing device_id parameter"}), 400

    accounts_list = [] # Khởi tạo list rỗng
    try:
        # Gọi hàm DB để lấy accounts (ID, Username, Platform, device_account_id)
        accounts_list = db.get_accounts_for_device_select(device_id)
        if accounts_list is None: # Phân biệt lỗi DB và không có account
             current_app.logger.error(f"DB Error getting accounts for device {device_id}")
             return jsonify({"error": "Database error fetching accounts"}), 500
        # Nếu device_id không tồn tại, hàm DB sẽ trả về list rỗng [] là đúng
        current_app.logger.debug(f"Found {len(accounts_list)} accounts for device {device_id}")

    except Exception as e:
        current_app.logger.error(f"Unexpected error in internal_get_accounts_for_device for {device_id}: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

    # Trả về danh sách account (có thể rỗng)
    return jsonify(accounts_list)

# =============================================
# === HÀM MỚI CHO QUẢN LÝ DEVICES (ADMIN) ===
# =============================================

def add_device(device_id: str, device_name: str | None, notes: str | None) -> tuple[bool, str | None]:
    """Thêm một thiết bị mới thủ công từ Admin.

    Args:
        device_id: ID duy nhất cho thiết bị (Admin nhập).
        device_name: Tên gợi nhớ (Admin nhập).
        notes: Ghi chú (Admin nhập).

    Returns:
        Tuple (bool, str | None): (True, None) nếu thành công, (False, error_message) nếu thất bại.
    """
    if not device_id:
        return False, "Device ID là bắt buộc."

    conn = db.get_db_connection()
    if not conn: return False, "Không thể kết nối CSDL."
    cur = None
    success = False
    error_msg = None
    try:
        cur = conn.cursor()
        # Chỉ insert các trường do Admin nhập, status có thể mặc định 'offline' hoặc 'pending_config'
        # registered_at dùng default NOW()
        sql = """
            INSERT INTO public.devices (device_id, device_name, notes, status, registered_at)
            VALUES (%s, %s, %s, %s, NOW());
        """
        # Status ban đầu có thể là 'pending_config' hoặc 'offline'
        params = (device_id.strip(), device_name.strip() if device_name else None, notes.strip() if notes else None, 'offline')
        cur.execute(sql, params)
        conn.commit()
        success = True
        current_app.logger.info(f"Admin added device: {device_id}")
    except psycopg2.IntegrityError:
        error_msg = f"Device ID '{device_id}' đã tồn tại."
        if conn: conn.rollback()
    except psycopg2.Error as e:
        error_msg = f"Lỗi CSDL khi thêm device: {e}"
        current_app.logger.error(error_msg, exc_info=True)
        if conn: conn.rollback()
    except Exception as e:
        error_msg = f"Lỗi không xác định khi thêm device: {e}"
        current_app.logger.error(error_msg, exc_info=True)
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success, error_msg


def get_all_devices(page: int = 1, per_page: int = 30) -> tuple[list[dict] | None, int | None]:
    """Lấy danh sách tất cả các thiết bị với phân trang."""
    devices = None
    total_items = None
    conn = db.get_db_connection()
    if not conn: return None, None
    cur = None
    try:
        # Query đếm tổng số
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM public.devices;")
        total_items = cur.fetchone()[0]
        cur.close()

        # Query lấy dữ liệu trang
        devices = []
        if total_items > 0:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            offset = (page - 1) * per_page
            sql = """
                SELECT device_id, device_name, os_info, macrodroid_version, status, last_seen_at, registered_at, notes
                FROM public.devices
                ORDER BY registered_at DESC, device_id
                LIMIT %s OFFSET %s;
            """
            cur.execute(sql, (per_page, offset))
            rows = cur.fetchall()
            devices = [dict(row) for row in rows] if rows else []

    except psycopg2.Error as db_err:
        current_app.logger.error(f"DB Error fetching all devices: {db_err}", exc_info=True)
        devices = None; total_items = None
    except Exception as e:
        current_app.logger.error(f"Unexpected Error fetching all devices: {e}", exc_info=True)
        devices = None; total_items = None
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return devices, total_items


def get_device_details(device_id: str) -> dict | None:
    """Lấy chi tiết một thiết bị bằng device_id."""
    if not device_id: return None
    details = None
    conn = db.get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        sql = """
            SELECT device_id, device_name, os_info, macrodroid_version, status, last_seen_at, registered_at, notes
            FROM public.devices WHERE device_id = %s;
            """
        cur.execute(sql, (device_id,))
        row = cur.fetchone()
        if row:
            details = dict(row)
    except Exception as e:
        current_app.logger.error(f"Error getting device details for {device_id}: {e}", exc_info=True)
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return details


def update_device_admin(device_id: str, device_name: str | None, notes: str | None, status: str | None) -> tuple[bool, str | None]:
    """Cập nhật thông tin device từ Admin (chủ yếu là name, notes, status)."""
    if not device_id: return False, "Device ID là bắt buộc."

    conn = db.get_db_connection()
    if not conn: return False, "Không thể kết nối CSDL."
    cur = None
    success = False
    error_msg = None
    try:
        cur = conn.cursor()
        # Chỉ cập nhật các trường Admin có thể sửa
        sql = """
            UPDATE public.devices
            SET device_name = %s, notes = %s, status = COALESCE(%s, status) -- Chỉ cập nhật status nếu được cung cấp
            WHERE device_id = %s;
        """
        # Trạng thái (status) có thể được cập nhật bởi admin (vd: disable) hoặc client (online/offline)
        # Nên cẩn thận khi cho admin sửa status
        params = (device_name.strip() if device_name else None,
                  notes.strip() if notes else None,
                  status.strip() if status else None, # Chỉ cập nhật status nếu admin nhập
                  device_id)
        cur.execute(sql, params)
        conn.commit()
        success = cur.rowcount > 0
        if not success:
            error_msg = f"Không tìm thấy Device ID '{device_id}' để cập nhật."
    except psycopg2.Error as e:
        error_msg = f"Lỗi CSDL khi cập nhật device: {e}"
        current_app.logger.error(error_msg, exc_info=True)
        if conn: conn.rollback()
    except Exception as e:
        error_msg = f"Lỗi không xác định khi cập nhật device: {e}"
        current_app.logger.error(error_msg, exc_info=True)
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success, error_msg


def delete_device(device_id: str) -> tuple[bool, str | None]:
    """Xóa một thiết bị (và các liên kết device_accounts, task_assignments liên quan do CASCADE)."""
    if not device_id: return False, "Device ID là bắt buộc."

    conn = db.get_db_connection()
    if not conn: return False, "Không thể kết nối CSDL."
    cur = None
    success = False
    error_msg = None
    try:
        cur = conn.cursor()
        # Do có ON DELETE CASCADE ở device_accounts và task_assignments,
        # chỉ cần xóa khỏi bảng devices
        sql = "DELETE FROM public.devices WHERE device_id = %s;"
        cur.execute(sql, (device_id,))
        conn.commit()
        success = cur.rowcount > 0
        if not success:
            error_msg = f"Không tìm thấy Device ID '{device_id}' để xóa."
        else:
            current_app.logger.info(f"Deleted device {device_id} and associated data via CASCADE.")
    except psycopg2.Error as e:
        error_msg = f"Lỗi CSDL khi xóa device: {e}"
        current_app.logger.error(error_msg, exc_info=True)
        if conn: conn.rollback()
    except Exception as e:
        error_msg = f"Lỗi không xác định khi xóa device: {e}"
        current_app.logger.error(error_msg, exc_info=True)
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success, error_msg


# --- Hàm lấy tài khoản cho Device (Đã tạo trước đó, giữ lại) ---
# def get_accounts_for_device_select(device_id: str) -> list[dict] | None: ...

# --- Thêm hàm lấy tất cả tài khoản cho dropdown ---
def get_all_accounts_for_select() -> list[dict] | None:
    """Lấy danh sách account (ID, Username, Platform) cho dropdown."""
    accounts = None
    conn = db.get_db_connection()
    if not conn: return None
    cur = None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        # Lấy các cột cần thiết, sắp xếp
        cur.execute("""
            SELECT account_id, username, platform
            FROM public.accounts
            ORDER BY platform, username, account_id;
        """)
        rows = cur.fetchall()
        accounts = [dict(row) for row in rows] if rows else []
    except Exception as e:
        current_app.logger.error(f"Error getting all accounts for select: {e}", exc_info=True)
        accounts = None
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return accounts

# =============================================
# === QUẢN LÝ THIẾT BỊ (DEVICES) ===
# =============================================

@admin_bp.route('/devices')
def view_devices():
    """Hiển thị danh sách các thiết bị đã đăng ký/thêm."""
    title = "Quản lý Thiết bị"
    devices = []
    pagination = None

    if not db:
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
    else:
        try:
            page = request.args.get('page', 1, type=int)
            if page < 1: page = 1

            devices, total_items = db.get_all_devices(page=page, per_page=PER_PAGE_DEVICES)

            if devices is None or total_items is None:
                flash("Lỗi khi tải danh sách thiết bị từ CSDL.", "error")
                devices = []; total_items = 0
            else:
                if total_items > 0:
                    total_pages = ceil(total_items / PER_PAGE_DEVICES)
                    if page > total_pages and total_pages > 0: page = total_pages
                    pagination = {
                        'page': page, 'per_page': PER_PAGE_DEVICES, 'total_items': total_items,
                        'total_pages': total_pages, 'has_prev': page > 1, 'has_next': page < total_pages,
                        'prev_num': page - 1, 'next_num': page + 1,
                        'page_param': 'page'
                    }
                else:
                    pagination = {'page': 1, 'per_page': PER_PAGE_DEVICES, 'total_items': 0, 'total_pages': 0, 'has_prev': False, 'has_next': False, 'page_param': 'page'}

        except Exception as e:
            current_app.logger.error(f"Lỗi nghiêm trọng load devices: {e}", exc_info=True)
            flash("Lỗi không mong muốn khi tải danh sách thiết bị.", "error")
            devices = []; pagination = None

    # Template này cần được tạo ở bước sau
    return render_template('admin_devices.html',
                           title=title,
                           devices=devices,
                           pagination=pagination)

@admin_bp.route('/devices/add', methods=['GET', 'POST'])
def add_device():
    """Hiển thị form và xử lý thêm thiết bị mới thủ công."""
    title = "Thêm Thiết bị Mới (Thủ công)"

    if request.method == 'POST':
        # ... (code xử lý lỗi DB) ...

        device_id = request.form.get('device_id', '').strip()
        device_name = request.form.get('device_name', '').strip()
        notes = request.form.get('notes', '').strip()
        os_info = request.form.get('os_info', '').strip() # <<< Lấy os_info
        macrodroid_version = request.form.get('macrodroid_version', '').strip() # <<< Lấy version

        if not device_id or not device_name: # <<< Kiểm tra cả device_name
            flash("Device ID và Tên Thiết bị là bắt buộc.", "warning") # <<< Sửa thông báo lỗi
            return render_template('admin_add_device.html', title="Thêm Thiết bị Mới (Lỗi)", current_data=request.form), 400

        try:
            # <<< Truyền thêm os_info, macrodroid_version vào hàm DB >>>
            success, error_msg = db.add_device(
                device_id=device_id,
                device_name=device_name or None,
                notes=notes or None,
                os_info=os_info or None, # <<< Thêm
                macrodroid_version=macrodroid_version or None # <<< Thêm
            )
            if success:
                flash(f"Thêm thiết bị '{device_id}' thành công!", 'success')
                return redirect(url_for('admin.view_devices'))
            else:
                flash(f"Thêm thiết bị thất bại: {error_msg or 'Lỗi không xác định.'}", 'error')
                return render_template('admin_add_device.html', title=title + " (Lỗi DB)", current_data=request.form)
        except Exception as e:
            current_app.logger.error(f"Lỗi nghiêm trọng khi thêm device: {e}", exc_info=True)
            flash(f"Lỗi không mong muốn khi thêm thiết bị: {e}", "error")
            return render_template('admin_add_device.html', title=title + " (Lỗi Exception)", current_data=request.form)

    # GET Request
    return render_template('admin_add_device.html', title=title)

@admin_bp.route('/devices/<device_id>/edit', methods=['GET', 'POST'])
def edit_device(device_id):
    """Hiển thị form và xử lý sửa thông tin thiết bị, bao gồm gán Main Loop Strategy."""
    if not db: flash("Lỗi DB.", "error"); return redirect(url_for('admin.view_devices'))

    # Lấy chi tiết device cho cả GET và POST lỗi
    device = db.get_device_details(device_id)
    if not device: flash(f"Không tìm thấy thiết bị ID '{device_id}'.", "error"); return redirect(url_for('admin.view_devices'))

    title = f"Sửa Thiết bị '{device.get('device_name', device_id)}'"
    editable_statuses = ['online', 'offline', 'disabled', 'error']

    # <<< LẤY DANH SÁCH MAIN LOOP STRATEGIES CHO DROPDOWN >>>
    mainloop_strategies_list = []
    try:
        mainloop_strategies_list = db.get_all_strategies(strategy_type_filter='mainloop') or []
    except Exception as e:
        current_app.logger.error(f"Lỗi tải danh sách Main Loop Strategies cho form edit device: {e}", exc_info=True)
        flash("Lỗi tải danh sách chiến lược Main Loop.", "warning") # Warning vì form vẫn có thể dùng

    # --- Xử lý POST ---
    if request.method == 'POST':
        device_name = request.form.get('device_name', '').strip()
        notes = request.form.get('notes', '').strip()
        status = request.form.get('status', '').strip()
        os_info = request.form.get('os_info', '').strip()
        macrodroid_version = request.form.get('macrodroid_version', '').strip()
        # <<< LẤY MAIN LOOP STRATEGY ID TỪ FORM >>>
        selected_mainloop_strategy_id = request.form.get('mainloop_strategy_id') # Value là strategy_id hoặc chuỗi rỗng

        # Validate status nếu admin được phép sửa
        if status and status not in editable_statuses:
             flash(f"Trạng thái '{status}' không hợp lệ.", "warning")
             return render_template('admin_edit_device.html', title=title + " (Lỗi)",
                                    device=device, editable_statuses=editable_statuses,
                                    mainloop_strategies=mainloop_strategies_list, # <<< Truyền lại list
                                    current_data=request.form), 400

        # --- Cập nhật thông tin device cơ bản ---
        update_success = False
        update_error = None
        try:
            update_success, update_error = db.update_device_admin(
                device_id=device_id,
                device_name=device_name or None,
                notes=notes or None,
                status=status if status else None,
                os_info=os_info or None,
                macrodroid_version=macrodroid_version or None
            )
            if not update_success:
                # Giữ lỗi từ hàm update_device_admin để hiển thị
                 flash(f"Cập nhật thông tin thiết bị thất bại: {update_error or 'Lỗi không xác định.'}", 'error')
                 # Không return ngay, tiếp tục xử lý mainloop strategy nếu có
            else:
                 flash(f"Cập nhật thông tin cơ bản cho thiết bị '{device_id}' thành công.", 'info') # Dùng info thay vì success ngay

        except Exception as e:
            current_app.logger.error(f"Lỗi nghiêm trọng khi sửa device {device_id}: {e}", exc_info=True)
            flash(f"Lỗi không mong muốn khi sửa thiết bị: {e}", "error")
            # Render lại form lỗi, không tiếp tục xử lý mainloop
            return render_template('admin_edit_device.html', title=title + " (Lỗi Exception)",
                                   device=device, editable_statuses=editable_statuses,
                                   mainloop_strategies=mainloop_strategies_list,
                                   current_data=request.form)

        # --- Cập nhật Main Loop Strategy (chỉ thực hiện nếu bước trên không lỗi nghiêm trọng) ---
        # So sánh giá trị mới chọn với giá trị hiện tại trong DB để xem có cần update không
        current_mainloop_id_in_db = device.get('mainloop_strategy_id') # Lấy từ dict device đã fetch
        strategy_id_to_set = selected_mainloop_strategy_id if selected_mainloop_strategy_id else None

        if strategy_id_to_set != current_mainloop_id_in_db:
             current_app.logger.info(f"Updating mainloop strategy for device {device_id} from '{current_mainloop_id_in_db}' to '{strategy_id_to_set}'")
             try:
                 # Gọi hàm DB mới để cập nhật mainloop_strategy_id
                 mainloop_success, mainloop_error = db.update_device_mainloop_strategy(device_id, strategy_id_to_set)

                 if mainloop_success:
                     flash(f"Đã cập nhật Main Loop Strategy cho thiết bị '{device_id}'.", 'success')
                     # Nếu cả hai update thành công, có thể redirect ngay
                     if update_success: # Kiểm tra KQ của update đầu tiên
                          return redirect(url_for('admin.view_devices'))
                 else:
                     flash(f"Cập nhật Main Loop Strategy thất bại: {mainloop_error or 'Lỗi không xác định.'}", 'error')
                     # Không redirect, hiển thị lại form với lỗi
                     error_occurred_mainloop = True # Đánh dấu lỗi

             except Exception as e_ml:
                 current_app.logger.error(f"Lỗi nghiêm trọng khi cập nhật mainloop strategy cho device {device_id}: {e_ml}", exc_info=True)
                 flash(f"Lỗi không mong muốn khi cập nhật Main Loop Strategy: {e_ml}", "error")
                 error_occurred_mainloop = True # Đánh dấu lỗi

             # Nếu có lỗi khi cập nhật mainloop, render lại form
             if error_occurred_mainloop:
                  return render_template('admin_edit_device.html', title=title + " (Lỗi Main Loop)",
                                         device=device, editable_statuses=editable_statuses,
                                         mainloop_strategies=mainloop_strategies_list,
                                         current_data=request.form)
        else:
            current_app.logger.info(f"Mainloop strategy for device {device_id} unchanged ('{current_mainloop_id_in_db}').")

        # Nếu không có lỗi nào xảy ra (hoặc chỉ có lỗi từ bước 1 nhưng không nghiêm trọng),
        # và không có thay đổi mainloop hoặc update mainloop thành công, thì redirect
        if update_success and (strategy_id_to_set == current_mainloop_id_in_db or mainloop_success):
             return redirect(url_for('admin.view_devices'))
        else:
             # Nếu bước 1 lỗi nhưng không exception, hoặc bước 2 lỗi -> render lại form
             return render_template('admin_edit_device.html', title=title + " (Lỗi)",
                                    device=device, editable_statuses=editable_statuses,
                                    mainloop_strategies=mainloop_strategies_list,
                                    current_data=request.form)


    # --- Xử lý GET Request ---
    # device và mainloop_strategies_list đã được lấy ở trên
    return render_template('admin_edit_device.html',
                           title=title,
                           device=device, # Chứa mainloop_strategy_id hiện tại
                           editable_statuses=editable_statuses,
                           mainloop_strategies=mainloop_strategies_list) 


@admin_bp.route('/devices/<device_id>/delete', methods=['POST'])
def delete_device(device_id):
    """Xử lý xóa thiết bị."""
    if not db:
        flash("Lỗi DB.", "error")
    else:
        try:
            success, error_msg = db.delete_device(device_id)
            if success:
                flash(f"Đã xóa thiết bị ID '{device_id}' và các dữ liệu liên quan (Device Accounts, Task Assignments).", 'success')
            else:
                flash(f"Xóa thiết bị thất bại: {error_msg or 'ID không tồn tại?'}", 'error')
        except Exception as e:
            current_app.logger.error(f"Lỗi nghiêm trọng khi xóa device {device_id}: {e}", exc_info=True)
            flash(f"Lỗi không mong muốn khi xóa thiết bị: {e}", "error")

    return redirect(url_for('admin.view_devices'))

# ======================================================
# === CHI TIẾT THIẾT BỊ & LIÊN KẾT TÀI KHOẢN ===
# ======================================================

@admin_bp.route('/devices/<device_id>')
def view_device_detail(device_id):
    """Hiển thị trang chi tiết thiết bị và các tài khoản liên kết."""
    title = f"Chi tiết Thiết bị {device_id}"
    device = None
    linked_accounts = []
    all_accounts_for_select = [] # Cho dropdown liên kết mới

    if not db:
        flash("Lỗi DB.", "error")
        # Không thể làm gì nếu lỗi DB, quay về trang trước đó hoặc index
        return redirect(request.referrer or url_for('admin.view_devices'))

    try:
        device = db.get_device_details(device_id)
        if not device:
            flash(f"Không tìm thấy thiết bị ID '{device_id}'.", "error")
            return redirect(url_for('admin.view_devices'))

        linked_accounts = db.get_accounts_linked_to_device(device_id) or []
        # Lấy danh sách tất cả tài khoản để người dùng chọn liên kết mới
        all_accounts_for_select = db.get_all_accounts_for_select() or []

    except Exception as e:
        current_app.logger.error(f"Lỗi khi tải chi tiết thiết bị {device_id}: {e}", exc_info=True)
        flash(f"Lỗi không mong muốn khi tải chi tiết thiết bị: {e}", "error")
        if device is None: return redirect(url_for('admin.view_devices'))

    title = f"Chi tiết Thiết bị: {device.get('device_name', device_id)}"
    # Template này cần được tạo ở bước sau
    return render_template('admin_device_detail.html',
                           title=title,
                           device=device,
                           linked_accounts=linked_accounts,
                           all_accounts=all_accounts_for_select) # Truyền danh sách account cho dropdown

@admin_bp.route('/devices/<device_id>/link-account', methods=['POST'])
def link_account_to_device_route(device_id): # Đổi tên hàm route để tránh trùng lặp
    """Xử lý việc liên kết một tài khoản với thiết bị từ form."""
    if not db:
        flash("Lỗi DB.", "error")
        return redirect(url_for('admin.view_device_detail', device_id=device_id)) # Quay lại trang chi tiết

    # Lấy dữ liệu từ form
    account_id = request.form.get('account_id')
    clone_context = request.form.get('clone_context', '').strip()
    app_package_name = request.form.get('app_package_name', '').strip()
    status = request.form.get('status', 'unknown').strip() # Trạng thái ban đầu của liên kết

    # Validate cơ bản
    if not account_id:
         flash("Bạn phải chọn một Tài khoản để liên kết.", "warning")
         return redirect(url_for('admin.view_device_detail', device_id=device_id))
    if not status: # Status cho liên kết là cần thiết
        flash("Cần chọn trạng thái cho liên kết (ví dụ: active_logged_in, login_required).", "warning")
        return redirect(url_for('admin.view_device_detail', device_id=device_id))


    try:
        # Gọi hàm DB để tạo liên kết
        success, error_msg = db.link_device_account(
            device_id=device_id,
            account_id=account_id,
            clone_context=clone_context if clone_context else None,
            app_package_name=app_package_name if app_package_name else None,
            status=status
        )

        if success:
            flash(f"Đã liên kết tài khoản '{account_id}' với thiết bị '{device_id}' thành công.", "success")
        else:
            flash(f"Liên kết thất bại: {error_msg or 'Lỗi không xác định.'}", "error")

    except Exception as e:
        current_app.logger.error(f"Lỗi nghiêm trọng khi liên kết account {account_id} với device {device_id}: {e}", exc_info=True)
        flash(f"Lỗi không mong muốn khi thực hiện liên kết: {e}", "error")

    # Luôn redirect về trang chi tiết thiết bị
    return redirect(url_for('admin.view_device_detail', device_id=device_id))

# ==============================================================
# === SỬA / HỦY LIÊN KẾT DEVICE-ACCOUNT ===
# ==============================================================

@admin_bp.route('/device-accounts/<int:link_id>/edit', methods=['GET', 'POST'])
def edit_device_account_link(link_id):
    """Hiển thị form và xử lý sửa thông tin liên kết Device-Account."""
    if not db:
        flash("Lỗi DB.", "error")
        # Không biết redirect về đâu nếu không có link details, tạm về device list
        return redirect(url_for('admin.view_devices'))

    # Lấy chi tiết liên kết hiện tại (bao gồm device_id, account_id để hiển thị và redirect)
    link_details = db.get_device_account_link_details(link_id)
    if not link_details:
        flash(f"Không tìm thấy liên kết Device-Account ID {link_id}.", "error")
        return redirect(url_for('admin.view_devices')) # Hoặc trang phù hợp hơn

    # Lấy device_id để dùng cho việc redirect và tạo link Cancel
    device_id_redirect = link_details.get('device_id')
    cancel_url = url_for('admin.view_device_detail', device_id=device_id_redirect) if device_id_redirect else url_for('admin.view_devices')
    title = f"Sửa Liên kết: Account '{link_details.get('account_id')}' trên Device '{device_id_redirect}'"

    # Các trạng thái hợp lệ cho liên kết
    valid_link_statuses = ['active_logged_in', 'login_required', 'unknown', 'error', 'inactive']

    if request.method == 'POST':
        # Lấy dữ liệu từ form
        clone_context = request.form.get('clone_context', '').strip()
        app_package_name = request.form.get('app_package_name', '').strip()
        status = request.form.get('status', '').strip()
        notes = request.form.get('notes', '').strip()

        # Validate status
        if not status or status not in valid_link_statuses:
             flash(f"Trạng thái liên kết '{status}' không hợp lệ.", "warning")
             # Render lại form với lỗi, giữ giá trị nhập
             return render_template('admin_edit_device_account_link.html',
                                    title=title + " (Lỗi)",
                                    link=link_details, # Dùng link gốc để lấy ID,...
                                    valid_statuses=valid_link_statuses,
                                    cancel_url=cancel_url,
                                    current_data=request.form), 400

        try:
            # Gọi hàm DB để cập nhật
            success, error_msg = db.update_device_account_link(
                device_account_id=link_id,
                clone_context=clone_context if clone_context else None,
                app_package_name=app_package_name if app_package_name else None,
                status=status,
                notes=notes if notes else None
            )

            if success:
                flash(f"Cập nhật liên kết ID {link_id} thành công!", 'success')
                return redirect(cancel_url) # Redirect về trang chi tiết device
            else:
                flash(f"Cập nhật liên kết thất bại: {error_msg or 'Lỗi không xác định.'}", 'error')
                # Render lại form với lỗi DB
                return render_template('admin_edit_device_account_link.html',
                                       title=title + " (Lỗi DB)",
                                       link=link_details,
                                       valid_statuses=valid_link_statuses,
                                       cancel_url=cancel_url,
                                       current_data=request.form)
        except Exception as e:
            current_app.logger.error(f"Lỗi nghiêm trọng khi sửa liên kết {link_id}: {e}", exc_info=True)
            flash(f"Lỗi không mong muốn khi sửa liên kết: {e}", "error")
            # Render lại form với lỗi Exception
            return render_template('admin_edit_device_account_link.html',
                                   title=title + " (Lỗi Exception)",
                                   link=link_details,
                                   valid_statuses=valid_link_statuses,
                                   cancel_url=cancel_url,
                                   current_data=request.form)

    # GET Request: Hiển thị form với dữ liệu hiện tại của liên kết
    return render_template('admin_edit_device_account_link.html',
                           title=title,
                           link=link_details, # Truyền chi tiết liên kết vào template
                           valid_statuses=valid_link_statuses,
                           cancel_url=cancel_url)


@admin_bp.route('/device-accounts/<int:link_id>/unlink', methods=['POST'])
def unlink_device_account_route(link_id): # Đổi tên hàm route
    """Xử lý việc hủy liên kết Device-Account."""
    if not db:
        flash("Lỗi DB.", "error");
        # Cố gắng lấy device_id từ form để redirect về đúng trang nếu có thể
        device_id_redirect = request.form.get('device_id_redirect')
        return redirect(url_for('admin.view_device_detail', device_id=device_id_redirect) if device_id_redirect else url_for('admin.view_devices'))

    # Lấy device_id TRƯỚC KHI XÓA để redirect về đúng trang chi tiết
    link_details = db.get_device_account_link_details(link_id)
    device_id_redirect = link_details.get('device_id') if link_details else None
    redirect_url = url_for('admin.view_device_detail', device_id=device_id_redirect) if device_id_redirect else url_for('admin.view_devices')

    try:
        success, error_msg = db.unlink_device_account(link_id)
        if success:
            flash(f"Đã hủy liên kết ID {link_id}.", 'success')
        else:
            flash(f"Hủy liên kết thất bại: {error_msg or 'ID không tồn tại?'}", 'error')
    except Exception as e:
        current_app.logger.error(f"Lỗi nghiêm trọng khi hủy liên kết {link_id}: {e}", exc_info=True)
        flash(f"Lỗi không mong muốn khi hủy liên kết: {e}", "error")

    return redirect(redirect_url) 

# ==============================================================
# === HỦY / XÓA / SỬA TASK ASSIGNMENT ===
# ==============================================================

@admin_bp.route('/task-assignments/<int:assignment_id>/cancel', methods=['POST'])
def cancel_task_assignment(assignment_id):
    """Xử lý yêu cầu hủy một Task Assignment đang chờ hoặc đang chạy."""
    if not db:
        flash("Lỗi DB.", "error")
        return redirect(url_for('admin.view_task_assignments'))

    current_app.logger.info(f"Attempting to cancel task assignment ID: {assignment_id}")
    try:
        # Lấy trạng thái hiện tại để kiểm tra (tùy chọn)
        # current_status = db.get_task_assignment_status(assignment_id)
        # if current_status not in ['pending', 'assigned', 'running']:
        #     flash(f"Không thể hủy assignment ID {assignment_id} vì trạng thái là '{current_status}'.", "warning")
        #     return redirect(url_for('admin.view_task_assignments'))

        # Gọi hàm DB để cập nhật status thành 'cancelled' và ghi thời gian hoàn thành
        success = db.update_assignment_status(
                    assignment_id=assignment_id,
                    new_status='cancelled',
                    completed_at=datetime.now(timezone.utc)
                    # result_data={'reason': 'Cancelled by admin'} # Có thể vẫn thêm lý do nếu hàm DB hỗ trợ
                )

        if success:
            flash(f"Đã hủy Task Assignment ID {assignment_id}.", 'success')
        else:
            flash(f"Hủy Task Assignment thất bại: {e or 'ID không tồn tại hoặc lỗi CSDL.'}", 'error')

    except Exception as e:
        current_app.logger.error(f"Lỗi nghiêm trọng khi hủy assignment {assignment_id}: {e}", exc_info=True)
        flash(f"Lỗi không mong muốn khi hủy assignment: {e}", "error")

    # Luôn redirect về trang danh sách assignment
    return redirect(url_for('admin.view_task_assignments'))

# ==============================================================
# === HỦY / XÓA / SỬA TASK ASSIGNMENT ===
# ==============================================================

@admin_bp.route('/task-assignments/<int:assignment_id>/delete', methods=['POST'])
def delete_task_assignment(assignment_id):
    """Xử lý yêu cầu xóa một Task Assignment."""
    if not db:
        flash("Lỗi DB.", "error")
        return redirect(url_for('admin.view_task_assignments'))

    current_app.logger.info(f"Attempting to delete task assignment ID: {assignment_id}")
    # (Tùy chọn) Có thể kiểm tra trạng thái trước khi xóa, ví dụ chỉ cho xóa khi đã completed/error/cancelled
    # assignment_details = db.get_task_assignment_details(assignment_id)
    # if assignment_details and assignment_details['status'] not in ['completed', 'error', 'cancelled']:
    #      flash(f"Không thể xóa assignment đang hoạt động hoặc đang chờ (ID: {assignment_id}). Hãy hủy trước.", "warning")
    #      return redirect(url_for('admin.view_task_assignments'))

    try:
        success, error_msg = db.delete_task_assignment(assignment_id)
        if success:
            flash(f"Đã xóa Task Assignment ID {assignment_id}.", 'success')
        else:
            flash(f"Xóa Task Assignment thất bại: {error_msg or 'ID không tồn tại?'}", 'error')
    except Exception as e:
        current_app.logger.error(f"Lỗi nghiêm trọng khi xóa assignment {assignment_id}: {e}", exc_info=True)
        flash(f"Lỗi không mong muốn khi xóa assignment: {e}", "error")

    return redirect(url_for('admin.view_task_assignments'))

@admin_bp.route('/assignments/<int:assignment_id>/logs', methods=['GET'])
def view_assignment_logs(assignment_id):
    """Hiển thị trang xem chi tiết log cho một Task Assignment."""
    page = request.args.get('page', 1, type=int)
    if page < 1: page = 1
    # Lấy số lượng item mỗi trang từ config, ví dụ 50 log/trang
    per_page = current_app.config.get('ADMIN_LOGS_PER_PAGE', 50)

    # Lấy thông tin cơ bản của assignment để hiển thị
    assignment = db.get_task_assignment_details(assignment_id)
    if not assignment:
        flash(f'Không tìm thấy Task Assignment với ID {assignment_id}.', 'error')
        return redirect(url_for('admin.view_task_assignments')) # Chuyển về trang danh sách assignments

    logs_list = []
    total_items = 0
    pagination_details = None

    try:
        # Gọi hàm CSDL đã cập nhật để lấy logs (bao gồm received_state_json)
        logs_result, total_result = db.get_assignment_logs(assignment_id, page=page, per_page=per_page)

        if logs_result is not None and total_result is not None:
            logs_list = logs_result
            total_items = total_result

            if total_items > 0:
                total_pages = math.ceil(total_items / per_page)
                # Kiểm tra trang có hợp lệ không
                if page > total_pages:
                     flash(f'Trang log {page} không tồn tại. Hiển thị trang cuối ({total_pages}).', 'warning')
                     return redirect(url_for('.view_assignment_logs', assignment_id=assignment_id, page=total_pages))

                # Tạo dict thông tin phân trang
                pagination_details = {
                    'page': page, 'per_page': per_page, 'total_items': total_items,
                    'total_pages': total_pages, 'has_prev': page > 1, 'has_next': page < total_pages,
                    'prev_num': page - 1 if page > 1 else None,
                    'next_num': page + 1 if page < total_pages else None
                }
        else:
            # Lỗi đã được log bên trong hàm get_assignment_logs
            flash('Có lỗi xảy ra khi tải danh sách logs.', 'error')

    except Exception as e:
        current_app.logger.error(f"Lỗi trong view_assignment_logs cho ID {assignment_id}: {e}", exc_info=True)
        flash('Có lỗi nghiêm trọng xảy ra khi tải danh sách logs.', 'error')

    # Render template, truyền cả thông tin assignment và logs
    return render_template('admin_assignment_logs.html',
                           title=f"Logs cho Assignment #{assignment_id}",
                           assignment=assignment, # Thông tin assignment cơ bản
                           logs=logs_list,         # Danh sách logs (có thể chứa received_state_json)
                           pagination_details=pagination_details)


@admin_bp.route('/task-assignments/<int:assignment_id>/edit', methods=['GET', 'POST'])
def edit_task_assignment(assignment_id):
    """Hiển thị form và xử lý việc sửa một Task Assignment."""
    if not db:
        flash("Lỗi DB.", "error")
        return redirect(url_for('admin.view_task_assignments'))

    # Lấy chi tiết assignment hiện tại để hiển thị và kiểm tra
    # Cần hàm get_task_assignment_details đã tạo ở bước Xem Log
    assignment = db.get_task_assignment_details(assignment_id)
    if not assignment:
        flash(f"Không tìm thấy Task Assignment ID {assignment_id}.", "error")
        return redirect(url_for('admin.view_task_assignments'))

    title = f"Sửa Task Assignment #{assignment_id}"
    # Các trạng thái admin có thể đặt (ví dụ: chỉ cho phép pause/resume từ đây?)
    # Tạm thời chưa cho sửa status ở form này, dùng action riêng (Cancel)
    # editable_statuses = ['pending', 'paused']

    if request.method == 'POST':
        current_data = request.form.to_dict() # Giữ lại dữ liệu form nếu lỗi
        try:
            # --- Lấy dữ liệu từ form ---
            priority_str = request.form.get('priority', '0')
            target_data_str = request.form.get('target_data', '{}').strip()
            notes = request.form.get('notes', '').strip()
            schedule_start_str = request.form.get('schedule_start_time')
            schedule_end_str = request.form.get('schedule_end_time')
            # status = request.form.get('status') # Tạm thời không cho sửa status ở đây

            # --- Validate dữ liệu ---
            errors = []
            update_data = {} # Dict chứa các thay đổi hợp lệ

            # Priority
            try:
                update_data['priority'] = int(priority_str)
            except (ValueError, TypeError):
                errors.append("Độ ưu tiên phải là số nguyên.")

            # Target Data (Validate JSON)
            target_data_parsed = None
            if target_data_str and target_data_str.strip() != '{}':
                try:
                    target_data_parsed = json.loads(target_data_str)
                    if not isinstance(target_data_parsed, dict): raise ValueError()
                    update_data['target_data'] = target_data_parsed # Lưu dạng dict để hàm DB xử lý
                except:
                    errors.append("Target Data phải là JSON object hợp lệ hoặc {}.")
            else: # Nếu người dùng nhập {} hoặc rỗng, coi như muốn xóa target data
                 if assignment.get('target_data') is not None:
                      update_data['target_data'] = None

            # Notes
            update_data['notes'] = notes if notes else None

            # Schedule Times
            schedule_start_time = None
            if schedule_start_str:
                try: schedule_start_time = datetime.fromisoformat(schedule_start_str).astimezone(timezone.utc)
                except ValueError: errors.append("Định dạng thời gian bắt đầu không hợp lệ.")
            update_data['schedule_start_time'] = schedule_start_time

            schedule_end_time = None
            if schedule_end_str:
                try: schedule_end_time = datetime.fromisoformat(schedule_end_str).astimezone(timezone.utc)
                except ValueError: errors.append("Định dạng thời gian kết thúc không hợp lệ.")
            update_data['schedule_end_time'] = schedule_end_time

            if schedule_start_time and schedule_end_time and schedule_start_time >= schedule_end_time:
                 errors.append("Thời gian kết thúc phải sau thời gian bắt đầu.")

            # --- Xử lý kết quả validate ---
            if errors:
                for error in errors: flash(error, 'warning')
                # Render lại form với lỗi và dữ liệu đã nhập
                return render_template('admin_edit_task_assignment.html',
                                       title=title + " (Lỗi)",
                                       assignment=assignment, # Dữ liệu gốc
                                       current_data=current_data), 400
            # --- Nếu không có lỗi validation, gọi hàm DB để cập nhật ---
            if update_data:
                 current_app.logger.debug(f"Updating assignment {assignment_id} with data: {update_data}")
                 # Cần hàm update_task_assignment đã tạo ở bước trước
                 success, error_msg = db.update_task_assignment(assignment_id, update_data)
                 if success:
                     flash(f"Cập nhật Task Assignment ID {assignment_id} thành công!", "success")
                     # Redirect về trang danh sách hoặc trang chi tiết nếu muốn
                     return redirect(url_for('admin.view_task_assignments'))
                 else:
                     flash(f"Cập nhật Task Assignment thất bại: {error_msg or 'Lỗi không xác định hoặc không có thay đổi.'}", "error")
                     # Render lại form với lỗi DB
                     return render_template('admin_edit_task_assignment.html',
                                           title=title + " (Lỗi DB)", assignment=assignment,
                                           current_data=current_data)
            else:
                 flash("Không có thay đổi nào được thực hiện.", "info")
                 return redirect(url_for('admin.view_task_assignments')) # Quay về nếu không có gì update

        except Exception as e:
            current_app.logger.error(f"Lỗi nghiêm trọng khi sửa assignment {assignment_id}: {e}", exc_info=True)
            flash(f"Lỗi không mong muốn khi sửa assignment: {e}", "error")
            # Render lại form với lỗi Exception
            return render_template('admin_edit_task_assignment.html',
                                   title=title + " (Lỗi Exception)", assignment=assignment,
                                   current_data=current_data)

    # --- Xử lý GET ---
    # Chỉ cần render form với dữ liệu assignment hiện tại
    return render_template('admin_edit_task_assignment.html',
                           title=title,
                           assignment=assignment) 

# --- API Documentation Routes ---

# Route xem danh sách (đã có skeleton, giờ hoàn thiện)
@admin_bp.route('/api-docs') # Giữ nguyên URL
def view_api_documentation(): # Tên hàm giữ nguyên
    """Hiển thị trang danh sách tài liệu API động từ CSDL."""
    title = "Tài liệu API Client (Database)"
    page = request.args.get('page', 1, type=int)
    if page < 1: page = 1
    per_page = current_app.config.get('ADMIN_ITEMS_PER_PAGE', 15)

    all_docs_details = [] # Dữ liệu gốc từ DB
    total_items = 0
    pagination_details = None
    all_docs_details_json_string = '[]' # <<< Chuỗi JSON để truyền vào template

    if not db:
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
    else:
        try:
            docs_result, total_result = db.get_all_api_docs_paginated(page=page, per_page=per_page)

            if docs_result is not None and total_result is not None:
                all_docs_details = docs_result
                total_items = total_result

                # <<< CHUYỂN ĐỔI DỮ LIỆU SANG CHUỖI JSON NGAY TẠI ĐÂY >>>
                try:
                    # Chuyển đổi datetime trước khi dump JSON
                    serializable_docs = convert_datetimes_to_iso(all_docs_details)
                    # Dump thành chuỗi JSON (không cần indent vì JS sẽ parse)
                    all_docs_details_json_string = json.dumps(serializable_docs, ensure_ascii=False)
                except Exception as json_e:
                    current_app.logger.error(f"Lỗi khi chuyển all_docs_details thành JSON: {json_e}", exc_info=True)
                    flash("Lỗi xử lý dữ liệu chi tiết API.", "error")
                    all_docs_details_json_string = '[]' # Trả về mảng rỗng nếu lỗi

                # --- Tính toán phân trang (giữ nguyên) ---
                if total_items > 0:
                    total_pages = math.ceil(total_items / per_page)
                    if page > total_pages and total_pages > 0: page = total_pages
                    pagination_details = {
                        'page': page, 'per_page': per_page, 'total_items': total_items,
                        'total_pages': total_pages, 'has_prev': page > 1, 'has_next': page < total_pages,
                        'prev_num': page - 1 if page > 1 else None,
                        'next_num': page + 1 if page < total_pages else None,
                        'page_param': 'page'
                    }
            else:
                flash("Lỗi khi tải tài liệu API từ CSDL.", "error")

        except Exception as e:
            current_app.logger.error(f"Lỗi trong view_api_documentation: {e}", exc_info=True)
            flash("Lỗi không mong muốn khi tải tài liệu API.", "error")
            all_docs_details = [] # Vẫn truyền list rỗng cho bảng

    # Render template list
    return render_template('admin_api_docs_list.html',
                           title=title,
                           api_docs=all_docs_details, # <<< Vẫn dùng list Python cho bảng HTML
                           all_docs_details_json_string=all_docs_details_json_string, # <<< Truyền chuỗi JSON
                           pagination_details=pagination_details)

# Route thêm mới (đã có skeleton, giờ hoàn thiện)
@admin_bp.route('/api-docs/add', methods=['GET', 'POST'])
def add_api_doc():
    title = "Thêm Tài liệu API Mới"
    valid_methods = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH'] # Các method hợp lệ

    if request.method == 'POST':
        if not db:
            flash("Lỗi DB.", "error"); return redirect(url_for('.view_api_documentation'))

        # Lấy dữ liệu từ form
        endpoint_path = request.form.get('endpoint_path', '').strip()
        http_method = request.form.get('http_method', '').strip().upper()
        summary = request.form.get('summary', '').strip()
        description = request.form.get('description', '').strip()
        request_notes = request.form.get('request_notes', '').strip()
        request_example = request.form.get('request_example', '').strip()
        response_notes = request.form.get('response_notes', '').strip()
        success_response_example = request.form.get('success_response_example', '').strip()
        error_response_example = request.form.get('error_response_example', '').strip()
        notes = request.form.get('notes', '').strip()
        is_active = request.form.get('is_active') == 'on'

        # Validate
        errors = []
        if not endpoint_path: errors.append("Endpoint Path là bắt buộc.")
        if not http_method: errors.append("HTTP Method là bắt buộc.")
        elif http_method not in valid_methods: errors.append("HTTP Method không hợp lệ.")
        if not summary: errors.append("Summary là bắt buộc.")

        if errors:
            for error in errors: flash(error, 'warning')
            return render_template('admin_add_api_doc.html', title=title + " (Lỗi)",
                                   valid_methods=valid_methods, current_data=request.form), 400

        # Gọi hàm DB
        success, error_msg = db.add_api_doc(
            endpoint_path, http_method, summary, description or None, request_notes or None,
            request_example or None, response_notes or None, success_response_example or None,
            error_response_example or None, notes or None, is_active
        )

        if success:
            flash(f"Đã thêm tài liệu cho API: {http_method} {endpoint_path}", 'success')
            return redirect(url_for('.view_api_documentation'))
        else:
            flash(f"Thêm tài liệu API thất bại: {error_msg or 'Lỗi không xác định.'}", 'error')
            return render_template('admin_add_api_doc.html', title=title + " (Lỗi DB)",
                                   valid_methods=valid_methods, current_data=request.form)

    # GET Request
    return render_template('admin_add_api_doc.html', title=title, valid_methods=valid_methods)

# Route sửa (đã có skeleton, giờ hoàn thiện)
@admin_bp.route('/api-docs/<int:doc_id>/edit', methods=['GET', 'POST'])
def edit_api_doc(doc_id):
    title = f"Sửa Tài liệu API #{doc_id}"
    valid_methods = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']

    if not db:
        flash("Lỗi DB.", "error"); return redirect(url_for('.view_api_documentation'))

    doc = db.get_api_doc_by_id(doc_id)
    if not doc:
        flash(f"Không tìm thấy tài liệu API với ID {doc_id}.", 'error')
        return redirect(url_for('.view_api_documentation'))

    if request.method == 'POST':
        # Lấy dữ liệu từ form
        endpoint_path = request.form.get('endpoint_path', '').strip()
        http_method = request.form.get('http_method', '').strip().upper()
        summary = request.form.get('summary', '').strip()
        description = request.form.get('description', '').strip()
        request_notes = request.form.get('request_notes', '').strip()
        request_example = request.form.get('request_example', '').strip()
        response_notes = request.form.get('response_notes', '').strip()
        success_response_example = request.form.get('success_response_example', '').strip()
        error_response_example = request.form.get('error_response_example', '').strip()
        notes = request.form.get('notes', '').strip()
        is_active = request.form.get('is_active') == 'on'

        # Validate
        errors = []
        if not endpoint_path: errors.append("Endpoint Path là bắt buộc.")
        if not http_method: errors.append("HTTP Method là bắt buộc.")
        elif http_method not in valid_methods: errors.append("HTTP Method không hợp lệ.")
        if not summary: errors.append("Summary là bắt buộc.")

        if errors:
            for error in errors: flash(error, 'warning')
            # Truyền lại doc gốc và dữ liệu lỗi
            return render_template('admin_edit_api_doc.html', title=title + " (Lỗi)",
                                   doc=doc, valid_methods=valid_methods, current_data=request.form), 400

        # Gọi hàm DB update
        success, error_msg = db.update_api_doc(
            doc_id, endpoint_path, http_method, summary, description or None, request_notes or None,
            request_example or None, response_notes or None, success_response_example or None,
            error_response_example or None, notes or None, is_active
        )

        if success:
            flash(f"Đã cập nhật tài liệu cho API: {http_method} {endpoint_path}", 'success')
            return redirect(url_for('.view_api_documentation'))
        else:
            flash(f"Cập nhật tài liệu API thất bại: {error_msg or 'Lỗi không xác định.'}", 'error')
            # Truyền lại doc gốc và dữ liệu lỗi
            return render_template('admin_edit_api_doc.html', title=title + " (Lỗi DB)",
                                   doc=doc, valid_methods=valid_methods, current_data=request.form)

    # GET Request
    return render_template('admin_edit_api_doc.html', title=title, doc=doc, valid_methods=valid_methods)

# Route xóa (cần tạo hàm này)
@admin_bp.route('/api-docs/<int:doc_id>/delete', methods=['POST'])
def delete_api_doc(doc_id):
    if not db:
        flash("Lỗi DB.", "error")
    else:
        try:
            # Lấy endpoint trước khi xóa để hiển thị flash message
            doc = db.get_api_doc_by_id(doc_id)
            endpoint_info = f"ID {doc_id}"
            if doc: endpoint_info = f"{doc.get('http_method','?')} {doc.get('endpoint_path','?')}"

            success, error_msg = db.delete_api_doc(doc_id)
            if success:
                flash(f"Đã xóa tài liệu API cho '{endpoint_info}'.", 'success')
            else:
                flash(f"Xóa tài liệu API '{endpoint_info}' thất bại: {error_msg or 'ID không tồn tại?'}", 'error')
        except Exception as e:
            current_app.logger.error(f"Lỗi nghiêm trọng khi xóa API doc {doc_id}: {e}", exc_info=True)
            flash(f"Lỗi không mong muốn khi xóa API doc: {e}", "error")

    return redirect(url_for('.view_api_documentation'))

@admin_bp.route('/_internal/api-doc-details/<int:doc_id>', methods=['GET'])
def get_api_doc_details_json(doc_id):
    """Trả về chi tiết của một API Doc dưới dạng JSON."""
    if not db:
        return jsonify({"error": "Database module not available"}), 503 # Service Unavailable

    try:
        details = db.get_api_doc_by_id(doc_id) # Dùng hàm DB đã có
        if details:
            # Chuyển đổi datetime thành string ISO nếu cần để JSON serialize được
            if details.get('created_at'):
                details['created_at'] = details['created_at'].isoformat()
            if details.get('updated_at'):
                details['updated_at'] = details['updated_at'].isoformat()
            return jsonify(details)
        else:
            return jsonify({"error": f"API Doc with ID {doc_id} not found."}), 404
    except Exception as e:
        current_app.logger.error(f"Error fetching API doc details JSON for ID {doc_id}: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

# --- === ROUTE MỚI CHO DANH SÁCH CHIẾN LƯỢC MAIN LOOP === ---

@admin_bp.route('/strategies/mainloop')
def view_strategies_mainloop():
    """Hiển thị danh sách các chiến lược loại 'mainloop' với phân trang."""
    title = "Quản lý Chiến lược Vòng lặp Chính (Main Loop)"
    mainloop_strategies_page = [] # Danh sách cho trang hiện tại
    pagination_details = None   # Thông tin phân trang

    if not db:
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
    else:
        try:
            # Lấy trang hiện tại từ URL
            page = request.args.get('page', 1, type=int)
            if page < 1: page = 1
            per_page = current_app.config.get('ADMIN_ITEMS_PER_PAGE', 15) # Lấy số lượng mỗi trang

            # --- Gọi hàm DB để lấy TẤT CẢ strategies loại 'mainloop' ---
            # Hàm get_all_strategies đã có filter này
            all_mainloop_strategies = db.get_all_strategies(strategy_type_filter='mainloop')

            if all_mainloop_strategies is None:
                flash("Lỗi khi tải danh sách chiến lược Main Loop.", "error")
                all_mainloop_strategies = [] # Đảm bảo là list rỗng nếu lỗi
                total_items = 0
            else:
                total_items = len(all_mainloop_strategies)

            # --- Thực hiện phân trang phía Python (Tạm thời) ---
            # Cách tốt hơn là sửa hàm DB để hỗ trợ LIMIT/OFFSET
            if total_items > 0:
                total_pages = ceil(total_items / per_page)
                # Đảm bảo trang không vượt quá giới hạn
                if page > total_pages:
                     page = total_pages

                start_index = (page - 1) * per_page
                end_index = start_index + per_page
                # Lấy các mục cho trang hiện tại từ list đầy đủ
                mainloop_strategies_page = all_mainloop_strategies[start_index:end_index]

                # Tạo thông tin pagination
                pagination_details = {
                    'page': page, 'per_page': per_page, 'total_items': total_items,
                    'total_pages': total_pages, 'has_prev': page > 1, 'has_next': page < total_pages,
                    'prev_num': page - 1 if page > 1 else None,
                    'next_num': page + 1 if page < total_pages else None,
                    'page_param': 'page' # Tên param dùng trong link phân trang
                }
            else:
                # Không có mục nào
                mainloop_strategies_page = []
                pagination_details = {'page': 1, 'per_page': per_page, 'total_items': 0, 'total_pages': 0, 'has_prev': False, 'has_next': False, 'page_param': 'page'}

        except Exception as e:
            current_app.logger.error(f"Lỗi load mainloop strategies: {e}", exc_info=True)
            flash("Lỗi không mong muốn khi tải dữ liệu.", "error")
            mainloop_strategies_page = []
            pagination_details = None

    # Render template, truyền danh sách của trang hiện tại và thông tin phân trang
    return render_template('admin_strategies_mainloop.html',
                           title=title,
                           strategies=mainloop_strategies_page, # <<< Chỉ truyền dữ liệu của trang này
                           pagination=pagination_details)   


# --- === ROUTE MỚI ĐỂ XEM CHI TIẾT STAGES/TRANSITIONS MAIN LOOP === ---
@admin_bp.route('/strategies/<strategy_id>/stages-mainloop')
def view_strategy_stages_mainloop(strategy_id):
    """Hiển thị stages và transitions cho một Main Loop Strategy."""
    strategy = None
    strategy_stages_list = []
    transitions_list = []
    # Dữ liệu cho dropdowns khi Thêm/Sửa transition (macros, stages...)
    all_stages = []
    all_macros = []

    if not db: flash("Lỗi DB.", "error")
    else:
        try:
            strategy = db.get_strategy_details(strategy_id)
            if strategy is None or strategy.get('strategy_type') != 'mainloop':
                flash(f"Không tìm thấy Main Loop Strategy ID {strategy_id} hoặc loại không đúng.", "warning")
                return redirect(url_for('admin.view_strategies_mainloop')) # Redirect về list mainloop

            strategy_stages_list = db.get_stages_for_strategy(strategy_id) or []
            transitions_list = db.get_strategy_action_sequence(strategy_id) or [] # Lấy transition thô
            # === THÊM LOG DEBUG Ở ĐÂY ===
            print(f"--- DEBUG view_strategy_stages_mainloop ---")
            print(f"Strategy ID: {strategy_id}")
            print(f"Fetched {len(transitions_list)} transitions from DB:")
            # In ra một vài transition đầu tiên để kiểm tra
            for i, trans in enumerate(transitions_list[:5]): # In tối đa 5 cái đầu
                print(f"  Transition {i}: ID={trans.get('transition_id')}, CurrentStage={trans.get('current_stage_id')}, Intent={trans.get('user_intent')}, Macro={trans.get('action_macro_code')}")
            if len(transitions_list) > 5: print("  ...")
            print(f"--- End DEBUG ---")
            # === KẾT THÚC LOG DEBUG ===
            # Lấy dữ liệu cho các dropdown trên trang này (nếu cần nút Add/Edit transition)
            all_stages = db.get_all_stages() or []
            # Lấy danh sách macro, có thể lọc theo type nếu bạn muốn tạo macro riêng cho mainloop
            temp_macros, _ = db.get_all_macro_definitions(page=1, per_page=1000) # Lấy nhiều
            all_macros = temp_macros or []

        except Exception as e:
            current_app.logger.error(f"Lỗi tải stages/transitions cho mainloop strategy {strategy_id}: {e}", exc_info=True)
            flash("Lỗi tải chi tiết chiến lược Main Loop.", "error")
            strategy = strategy or {'strategy_id': strategy_id, 'name': 'Lỗi tải tên'}
            strategy_stages_list, transitions_list, all_stages, all_macros = [], [], [], []

    # Render template MỚI (sẽ tạo ở bước sau)
    return render_template('admin_strategy_stages_mainloop.html',
                           title=f"Main Loop Stages & Transitions cho '{strategy.get('name', strategy_id)}'",
                           strategy=strategy,
                           strategy_stages=strategy_stages_list,
                           transitions=transitions_list,
                           all_stages=all_stages,
                           all_macros=all_macros) 

@admin_bp.route('/stages/add-mainloop', methods=['GET', 'POST'])
def add_stage_mainloop():
    """Hiển thị form và xử lý thêm Stage mới cho Mainloop Strategy."""
    strategy_id = request.args.get('strategy_id') or request.form.get('strategy_id')
    if not strategy_id:
        flash("Cần cung cấp strategy_id.", "error")
        return redirect(url_for('admin.view_strategies_mainloop')) # Về trang list mainloop

    # Kiểm tra strategy tồn tại và đúng loại
    if db:
        strategy_details = db.get_strategy_details(strategy_id)
        if not strategy_details or strategy_details.get('strategy_type') != 'mainloop':
            flash("Strategy không hợp lệ hoặc không phải loại 'mainloop'.", "error")
            return redirect(url_for('admin.view_strategies_mainloop'))
    else:
        flash("Lỗi DB.", "error")
        return redirect(url_for('admin.view_strategies_mainloop'))

    # URL để quay lại trang chi tiết mainloop strategy
    cancel_url = url_for('admin.view_strategy_stages_mainloop', strategy_id=strategy_id)
    title = f"Thêm Stage cho Mainloop Strategy {strategy_id}"

    if request.method == 'POST':
        stage_id = request.form.get('stage_id', '').strip()
        description = request.form.get('description', '').strip()
        order_str = request.form.get('stage_order', '0').strip()
        # <<< KHÔNG lấy identifying_elements nữa >>>

        # Validate dữ liệu cơ bản
        errors = []
        if not stage_id: errors.append("Stage ID là bắt buộc.")
        try: order = int(order_str)
        except ValueError: errors.append("Stage Order phải là số nguyên.")

        if errors:
            for error in errors: flash(error, "warning")
            # <<< Render template mới: admin_add_stage_mainloop.html >>>
            return render_template('admin_add_stage_mainloop.html', title=title + " (Lỗi)",
                                   strategy_id=strategy_id, cancel_url=cancel_url,
                                   current_data=request.form), 400

        # Gọi hàm DB, truyền None cho identifying_elements
        success, error_msg = db.add_new_stage(stage_id, strategy_id, description, order, None)

        if success:
            flash(f"Thêm stage '{stage_id}' thành công!", 'success')
            return redirect(cancel_url) # Redirect về trang chi tiết mainloop
        else:
            flash(f"Thêm stage '{stage_id}' thất bại: {error_msg or 'Lỗi không xác định.'}", 'error')
            # <<< Render template mới: admin_add_stage_mainloop.html >>>
            return render_template('admin_add_stage_mainloop.html', title=title + " (Lỗi DB)",
                                   strategy_id=strategy_id, cancel_url=cancel_url,
                                   current_data=request.form)

    # GET request
    # <<< Render template mới: admin_add_stage_mainloop.html >>>
    return render_template('admin_add_stage_mainloop.html', title=title,
                           strategy_id=strategy_id, cancel_url=cancel_url)

# Thêm vào file app/admin_routes.py

# --- === ROUTE MỚI ĐỂ THÊM TRANSITION CHO MAINLOOP === ---
@admin_bp.route('/transitions/add-mainloop', methods=['GET', 'POST'])
def add_transition_mainloop():
    """Hiển thị form và xử lý thêm Transition mới cho Mainloop Strategy."""
    # Lấy strategy_id từ URL args hoặc form
    strategy_id = request.args.get('strategy_id') or request.form.get('strategy_id')
    # Lấy current_stage_id để điền sẵn nếu có
    current_stage_id_prefill = request.args.get('current_stage_id')

    # --- Kiểm tra ban đầu ---
    if not strategy_id:
        flash("Cần cung cấp strategy_id.", "error")
        return redirect(url_for('admin.view_strategies_mainloop')) # Về trang list mainloop
    if not db:
         flash("Lỗi DB.", "error")
         return redirect(url_for('admin.view_strategies_mainloop'))

    # --- Lấy dữ liệu cần thiết cho form (cho cả GET và POST lỗi) ---
    strategy_details = None
    strategy_stages = [] # Stages thuộc strategy này
    all_stages = [] # Tất cả stages (cho next_stage dropdown)
    all_macros = [] # Tất cả các macro đã định nghĩa
    cancel_url = url_for('admin.view_strategies_mainloop') # Fallback cancel URL

    try:
        strategy_details = db.get_strategy_details(strategy_id)
        if not strategy_details or strategy_details.get('strategy_type') != 'mainloop':
            flash("Strategy không hợp lệ hoặc không phải loại 'mainloop'.", "error")
            return redirect(url_for('admin.view_strategies_mainloop'))
        # Đặt cancel_url chính xác về trang chi tiết mainloop
        cancel_url = url_for('admin.view_strategy_stages_mainloop', strategy_id=strategy_id)

        strategy_stages = db.get_stages_for_strategy(strategy_id) or []
        all_stages = db.get_all_stages() or []
        # Lấy danh sách macro (hiện tại lấy tất cả, có thể lọc sau nếu cần)
        temp_macros, _ = db.get_all_macro_definitions(page=1, per_page=1000)
        all_macros = temp_macros or []
    except Exception as e:
        current_app.logger.error(f"ERROR (add_transition_mainloop): Lỗi tải dữ liệu cho form: {e}", exc_info=True)
        flash(f"Lỗi tải dữ liệu cho form: {e}", "error")
        # Vẫn tiếp tục để render form rỗng nếu có thể

    title=f"Thêm Mainloop Transition cho Strategy {strategy_id}"

    # --- Xử lý POST ---
    if request.method == 'POST':
        # --- Lấy dữ liệu cơ bản ---
        current_stage_id = request.form.get('current_stage_id')
        user_intent = request.form.get('user_intent')
        condition_type = request.form.get('condition_type', '').strip()
        condition_value = request.form.get('condition_value', '').strip()
        next_stage_id = request.form.get('next_stage_id', '').strip()
        priority_str = request.form.get('priority', '0').strip()
        action_macro_code = request.form.get('action_macro_code', '').strip()
        action_params_str = request.form.get('action_params_str', '{}').strip()
        form_strategy_id = request.form.get('strategy_id') # Lấy từ hidden input
        notes = request.form.get('notes', '').strip() # Lấy thêm ghi chú

        # Lấy dữ liệu LOOP
        loop_type = request.form.get('loop_type', '').strip()
        loop_count_str = request.form.get('loop_count', '').strip()
        loop_condition_type = request.form.get('loop_condition_type', '').strip()
        loop_condition_value = request.form.get('loop_condition_value', '').strip()
        # Hiện tại chưa có loop_target_selector và loop_variable_name trong form đơn giản này

        # --- Validate ---
        errors = []
        if not current_stage_id: errors.append("Current Stage là bắt buộc.")
        if not user_intent: errors.append("User Intent/Trigger là bắt buộc.")
        if not form_strategy_id or form_strategy_id != strategy_id: errors.append("Lỗi Strategy ID.")
        priority = 0
        try: priority = int(priority_str)
        except ValueError: errors.append("Priority phải là số nguyên.")

        # Validate JSON Params nếu có nhập macro
        params_dict = {}
        if action_macro_code and action_params_str and action_params_str.strip() and action_params_str != '{}':
             try:
                  params_dict = json.loads(action_params_str)
                  if not isinstance(params_dict, dict): errors.append("Action Params phải là JSON object.")
             except json.JSONDecodeError: errors.append("Action Params JSON không hợp lệ.")

        # Validate dữ liệu Loop
        loop_count = None
        if loop_type == 'repeat_n':
            if not loop_count_str: errors.append("Cần nhập Số lần lặp khi chọn loại 'Repeat N'.")
            else:
                try: loop_count = int(loop_count_str); assert loop_count >= 1
                except (ValueError, AssertionError): errors.append("Số lần lặp phải là số nguyên lớn hơn 0.")
        elif loop_type == 'while_condition_met':
            if not loop_condition_type: errors.append('Cần chọn Điều kiện Lặp khi chọn loại \'While\'.')
        elif loop_type: errors.append(f"Loại vòng lặp '{loop_type}' chưa được hỗ trợ.")


        # Nếu có lỗi validation
        if errors:
            for error in errors: flash(error, "warning")
            # Render lại template mới: admin_add_transition_mainloop.html
            return render_template('admin_add_transition_mainloop.html',
                                   title=title + " (Lỗi)",
                                   strategy_id=strategy_id,
                                   cancel_url=cancel_url,
                                   current_stage_id_prefill=current_stage_id, # Giữ lại stage đã chọn
                                   strategy_stages=strategy_stages,
                                   all_stages=all_stages,
                                   all_macros=all_macros,
                                   valid_intents=VALID_INTENTS_FOR_TRANSITION, # Có thể tạo list riêng cho mainloop nếu cần
                                   valid_condition_types=VALID_CONDITION_TYPES, # Có thể tạo list riêng cho mainloop nếu cần
                                   current_data=request.form), 400

        # --- Gọi hàm DB add_new_transition ---
        # Hàm này đã được thiết kế để nhận các trường và xử lý NULL/JSON phù hợp
        try:
            success, error_msg = db.add_new_transition(
                strategy_id=strategy_id,
                current_stage_id=current_stage_id,
                user_intent=user_intent,
                priority=priority,
                condition_type=condition_type if condition_type else None,
                condition_value=condition_value if condition_value else None,
                next_stage_id=next_stage_id if next_stage_id else None,
                action_macro_code=action_macro_code if action_macro_code else None,
                action_params_str=action_params_str if (action_params_str and action_params_str.strip() and action_params_str != '{}') else None,
                response_template_ref=None, # Mainloop không dùng
                loop_type=loop_type if loop_type else None,
                loop_count=loop_count, # int hoặc None
                loop_condition_type=loop_condition_type if loop_condition_type else None,
                loop_condition_value=loop_condition_value if loop_condition_value else None,
                loop_target_selector_str=None, # Tạm thời None
                loop_variable_name=None, # Tạm thời None
                notes=notes if notes else None # Thêm notes
            )

            if success:
                flash('Thêm mainloop transition thành công!', 'success')
                return redirect(cancel_url) # Redirect về trang chi tiết mainloop
            else:
                flash(f'Thêm mainloop transition thất bại: {error_msg or "Lỗi không xác định."}', 'error')
                # Render lại template mới: admin_add_transition_mainloop.html
                return render_template('admin_add_transition_mainloop.html',
                                       title=title + " (Lỗi DB)",
                                       strategy_id=strategy_id,
                                       cancel_url=cancel_url,
                                       current_stage_id_prefill=current_stage_id,
                                       strategy_stages=strategy_stages,
                                       all_stages=all_stages,
                                       all_macros=all_macros,
                                       valid_intents=VALID_INTENTS_FOR_TRANSITION,
                                       valid_condition_types=VALID_CONDITION_TYPES,
                                       current_data=request.form)
        except Exception as e:
             current_app.logger.error(f"Lỗi nghiêm trọng khi thêm mainloop transition: {e}", exc_info=True)
             flash(f"Lỗi không mong muốn: {e}", "error")
             # Render lại template mới: admin_add_transition_mainloop.html
             return render_template('admin_add_transition_mainloop.html',
                                    title=title + " (Lỗi Exception)",
                                    strategy_id=strategy_id,
                                    cancel_url=cancel_url,
                                    current_stage_id_prefill=current_stage_id,
                                    strategy_stages=strategy_stages,
                                    all_stages=all_stages,
                                    all_macros=all_macros,
                                    valid_intents=VALID_INTENTS_FOR_TRANSITION,
                                    valid_condition_types=VALID_CONDITION_TYPES,
                                    current_data=request.form)

    # --- GET request ---
    # Render template mới: admin_add_transition_mainloop.html
    return render_template('admin_add_transition_mainloop.html',
                           title=title,
                           strategy_id=strategy_id,
                           cancel_url=cancel_url,
                           current_stage_id_prefill=current_stage_id_prefill,
                           strategy_stages=strategy_stages,
                           all_stages=all_stages,
                           all_macros=all_macros,
                           valid_intents=VALID_INTENTS_FOR_TRANSITION, # Có thể tạo list riêng
                           valid_condition_types=VALID_CONDITION_TYPES) # Có thể tạo list riêng

# Thêm vào file app/admin_routes.py

# --- === ROUTE MỚI ĐỂ SỬA TRANSITION CHO MAINLOOP === ---
@admin_bp.route('/transitions/<int:transition_id>/edit-mainloop', methods=['GET', 'POST'])
def edit_transition_mainloop(transition_id):
    """Hiển thị form và xử lý sửa Mainloop Transition."""
    if not db: flash("Lỗi DB.", "error"); return redirect(url_for('admin.view_strategies_mainloop'))

    # --- Lấy dữ liệu gốc của transition (cho cả GET và POST lỗi) ---
    # Hàm get_transition_details đã được sửa để lấy cả strategy_id và loop_* fields
    transition = db.get_transition_details(transition_id)
    if not transition:
        flash(f"Không tìm thấy transition ID {transition_id}.", "error")
        return redirect(url_for('admin.view_strategies_mainloop'))

    strategy_id = transition.get('strategy_id')
    if not strategy_id:
        flash("Lỗi: Transition không có strategy_id liên kết.", "error")
        return redirect(url_for('admin.view_strategies_mainloop'))

    # Kiểm tra lại type cho chắc chắn
    strategy_details = db.get_strategy_details(strategy_id)
    if not strategy_details or strategy_details.get('strategy_type') != 'mainloop':
         flash("Transition này không thuộc về một Mainloop Strategy hợp lệ.", "error")
         return redirect(url_for('admin.view_strategies_mainloop'))

    # --- Lấy dữ liệu cho các dropdown (cho cả GET và POST lỗi) ---
    strategy_stages = []
    all_stages = []
    all_macros = []
    try:
        strategy_stages = db.get_stages_for_strategy(strategy_id) or []
        all_stages = db.get_all_stages() or []
        temp_macros, _ = db.get_all_macro_definitions(page=1, per_page=1000)
        all_macros = temp_macros or []
    except Exception as e:
        current_app.logger.error(f"ERROR (edit_transition_mainloop): Lỗi tải dữ liệu cho form: {e}", exc_info=True)
        flash(f"Lỗi tải dữ liệu cho form: {e}", "error")

    title = f"Sửa Mainloop Transition #{transition_id}"
    cancel_url = url_for('admin.view_strategy_stages_mainloop', strategy_id=strategy_id)

    # --- Xử lý POST ---
    if request.method == 'POST':
        # --- Lấy dữ liệu cơ bản ---
        current_stage_id = request.form.get('current_stage_id')
        user_intent = request.form.get('user_intent')
        condition_type = request.form.get('condition_type', '').strip()
        condition_value = request.form.get('condition_value', '').strip()
        next_stage_id = request.form.get('next_stage_id', '').strip()
        priority_str = request.form.get('priority', '0').strip()
        action_macro_code = request.form.get('action_macro_code', '').strip()
        action_params_str = request.form.get('action_params_str', '{}').strip()
        notes = request.form.get('notes', '').strip() # Lấy notes

        # Lấy dữ liệu LOOP
        loop_type = request.form.get('loop_type', '').strip()
        loop_count_str = request.form.get('loop_count', '').strip()
        loop_condition_type = request.form.get('loop_condition_type', '').strip()
        loop_condition_value = request.form.get('loop_condition_value', '').strip()
        # Hiện tại chưa có loop_target_selector và loop_variable_name

        # --- Validate (tương tự như add) ---
        errors = []
        if not current_stage_id: errors.append("Current Stage là bắt buộc.")
        if not user_intent: errors.append("User Intent/Trigger là bắt buộc.")
        priority = 0
        try: priority = int(priority_str)
        except ValueError: errors.append("Priority phải là số nguyên.")
        # Validate JSON Params nếu có nhập macro
        params_dict = {}
        if action_macro_code and action_params_str and action_params_str.strip() and action_params_str != '{}':
             try:
                  params_dict = json.loads(action_params_str)
                  if not isinstance(params_dict, dict): errors.append("Action Params phải là JSON object.")
             except json.JSONDecodeError: errors.append("Action Params JSON không hợp lệ.")
        # Validate dữ liệu Loop
        loop_count = None
        if loop_type == 'repeat_n':
            if not loop_count_str: errors.append("Cần nhập Số lần lặp khi chọn loại 'Repeat N'.")
            else:
                try: loop_count = int(loop_count_str); assert loop_count >= 1
                except (ValueError, AssertionError): errors.append("Số lần lặp phải là số nguyên lớn hơn 0.")
        elif loop_type == 'while_condition_met':
            if not loop_condition_type: errors.append('Cần chọn Điều kiện Lặp khi chọn loại \'While\'.')
        elif loop_type: errors.append(f"Loại vòng lặp '{loop_type}' chưa được hỗ trợ.")

        # Nếu có lỗi validation
        if errors:
            for error in errors: flash(error, "warning")
            # Render lại template mới: admin_edit_transition_mainloop.html
            return render_template('admin_edit_transition_mainloop.html',
                                   title=title + " (Lỗi)",
                                   transition=transition, # Dữ liệu gốc để lấy ID
                                   strategy_id=strategy_id,
                                   cancel_url=cancel_url,
                                   strategy_stages=strategy_stages,
                                   all_stages=all_stages,
                                   all_macros=all_macros,
                                   valid_intents=VALID_INTENTS_FOR_TRANSITION,
                                   valid_condition_types=VALID_CONDITION_TYPES,
                                   current_data=request.form), 400

        # --- Gọi hàm DB Update ---
        # Hàm update_transition đã được thiết kế để nhận các trường loop và xử lý NULL/JSON
        try:
            success, error_msg = db.update_transition(
                transition_id=transition_id, # ID của transition đang sửa
                current_stage_id=current_stage_id,
                user_intent=user_intent,
                next_stage_id=next_stage_id if next_stage_id else None,
                priority=priority,
                response_template_ref=None, # Mainloop không dùng
                action_macro_code=action_macro_code if action_macro_code else None,
                action_params_str=action_params_str if (action_params_str and action_params_str.strip() and action_params_str != '{}') else None,
                condition_type=condition_type if condition_type else None,
                condition_value=condition_value if condition_value else None,
                loop_type=loop_type if loop_type else None,
                loop_count=loop_count, # int hoặc None
                loop_condition_type=loop_condition_type if loop_condition_type else None,
                loop_condition_value=loop_condition_value if loop_condition_value else None,
                loop_target_selector_str=None, # Tạm thời None
                loop_variable_name=None, # Tạm thời None
                # Lưu ý: Hàm db.update_transition hiện tại có thể chưa có tham số 'notes'. Nếu cần lưu notes, bạn cần sửa hàm DB đó.
            )

            if success:
                flash(f'Cập nhật mainloop transition #{transition_id} thành công!', 'success')
                return redirect(cancel_url) # Redirect về trang chi tiết mainloop
            else:
                flash(f'Cập nhật mainloop transition thất bại: {error_msg or "Lỗi không xác định."}', 'error')
                 # Render lại template mới: admin_edit_transition_mainloop.html
                return render_template('admin_edit_transition_mainloop.html',
                                       title=title + " (Lỗi DB)",
                                       transition=transition, # Dữ liệu gốc
                                       strategy_id=strategy_id,
                                       cancel_url=cancel_url,
                                       strategy_stages=strategy_stages,
                                       all_stages=all_stages,
                                       all_macros=all_macros,
                                       valid_intents=VALID_INTENTS_FOR_TRANSITION,
                                       valid_condition_types=VALID_CONDITION_TYPES,
                                       current_data=request.form)
        except Exception as e:
             current_app.logger.error(f"Lỗi nghiêm trọng khi sửa mainloop transition {transition_id}: {e}", exc_info=True)
             flash(f"Lỗi không mong muốn: {e}", "error")
             # Render lại template mới: admin_edit_transition_mainloop.html
             return render_template('admin_edit_transition_mainloop.html',
                                    title=title + " (Lỗi Exception)",
                                    transition=transition, # Dữ liệu gốc
                                    strategy_id=strategy_id,
                                    cancel_url=cancel_url,
                                    strategy_stages=strategy_stages,
                                    all_stages=all_stages,
                                    all_macros=all_macros,
                                    valid_intents=VALID_INTENTS_FOR_TRANSITION,
                                    valid_condition_types=VALID_CONDITION_TYPES,
                                    current_data=request.form)

    # --- GET request ---
    # Render template mới: admin_edit_transition_mainloop.html
    # transition, strategy_stages, all_stages, all_macros đã lấy ở trên
    return render_template('admin_edit_transition_mainloop.html',
                           title=title,
                           transition=transition, # Đã chứa các giá trị loop_* từ db
                           strategy_id=strategy_id,
                           cancel_url=cancel_url,
                           strategy_stages=strategy_stages,
                           all_stages=all_stages,
                           all_macros=all_macros,
                           valid_intents=VALID_INTENTS_FOR_TRANSITION,
                           valid_condition_types=VALID_CONDITION_TYPES)

# --- === ROUTE MỚI ĐỂ XEM ĐỊNH NGHĨA STRATEGY DẠNG JSON === ---
def convert_datetimes_to_iso(data):
    """
    Hàm đệ quy hoặc lặp qua cấu trúc dữ liệu (dict, list)
    và chuyển đổi các đối tượng datetime thành chuỗi ISO 8601.
    """
    if isinstance(data, dict):
        # Tạo dict mới để tránh thay đổi dict gốc khi lặp
        new_dict = {}
        for k, v in data.items():
            new_dict[k] = convert_datetimes_to_iso(v) # Đệ quy cho value
        return new_dict
    elif isinstance(data, list):
        # Tạo list mới
        new_list = []
        for item in data:
            new_list.append(convert_datetimes_to_iso(item)) # Đệ quy cho từng item
        return new_list
    elif isinstance(data, datetime):
        # Chuyển đổi datetime thành chuỗi ISO format
        try:
            return data.isoformat()
        except Exception:
             # Fallback nếu có lỗi khi gọi isoformat
             return str(data)
    else:
        # Giữ nguyên các kiểu dữ liệu khác
        return data

# --- ROUTE XEM JSON ĐỊNH NGHĨA STRATEGY (ĐÃ SỬA LỖI DATETIME) ---
@admin_bp.route('/strategies/<strategy_id>/definition-json')
def view_strategy_definition_json(strategy_id):
    """
    Trả về định nghĩa thô VÀ ví dụ gói JSON cho client của một strategy.
    """
    logger = current_app.logger if current_app else print
    if not db:
        return jsonify({"error": "Database module not available"}), 500

    strategy_definition = {} # Nơi chứa kết quả cuối cùng

    try:
        # 1. Lấy thông tin chi tiết strategy gốc
        strategy_details_raw = db.get_strategy_details(strategy_id)
        if not strategy_details_raw:
            return jsonify({"error": f"Strategy ID '{strategy_id}' not found."}), 404

        # 2. Lấy stages và transitions gốc
        strategy_stages_raw = db.get_stages_for_strategy(strategy_id) or []
        strategy_transitions_raw = db.get_strategy_action_sequence(strategy_id) or []

        # 3. Chuyển đổi datetime thành chuỗi ISO cho phần định nghĩa thô
        strategy_details_serializable = convert_datetimes_to_iso(strategy_details_raw)
        strategy_stages_serializable = convert_datetimes_to_iso(strategy_stages_raw)
        strategy_transitions_serializable = convert_datetimes_to_iso(strategy_transitions_raw)

        # 4. Thêm định nghĩa thô vào kết quả
        strategy_definition['raw_definition'] = {
            "strategy_info": strategy_details_serializable,
            "stages": strategy_stages_serializable,
            "transitions": strategy_transitions_serializable
        }

        # 5. Nếu là strategy 'mainloop', tạo thêm ví dụ gói JSON cho client
        strategy_definition['client_package_example'] = None # Khởi tạo là None
        if strategy_details_raw.get('strategy_type') == 'mainloop':
            if phone_controller:
                # Gọi hàm helper mới trong controller
                client_package = phone_controller.assemble_mainloop_package_from_definition(strategy_id)
                if client_package:
                    # Chuyển đổi datetime trong gói client (nếu có) trước khi gán
                    strategy_definition['client_package_example'] = convert_datetimes_to_iso(client_package)
                else:
                     logger.warning(f"Could not assemble client package example for mainloop strategy {strategy_id}")
            else:
                 logger.error("Phone controller not available to assemble client package example.")


        # 6. Trả về JSON cuối cùng (chứa cả raw_definition và client_package_example)
        response = current_app.response_class(
            response=json.dumps(strategy_definition, indent=2, ensure_ascii=False),
            status=200,
            mimetype='application/json; charset=utf-8'
        )
        return response

    except Exception as e:
        logger.error(f"ERROR generating strategy definition JSON for {strategy_id}: {e}", exc_info=True)
        return jsonify({"error": f"Internal server error: {e}"}), 500

@admin_bp.route('/history/delete-all', methods=['POST'])
def delete_all_history_view():
    """Xử lý yêu cầu xóa toàn bộ lịch sử tương tác."""
    logger = current_app.logger
    logger.warning("Attempting to delete ALL interaction history!") # Ghi log cảnh báo

    if not db:
        flash("Lỗi kết nối CSDL.", "error")
        return redirect(url_for('admin.view_history'))

    try:
        # Gọi hàm DB mới để xóa
        success, error_msg = db.delete_all_interaction_history()
        if success:
            flash("Đã xóa toàn bộ lịch sử tương tác thành công!", "success")
            logger.info("Successfully deleted all interaction history.")
        else:
            flash(f"Xóa lịch sử tương tác thất bại: {error_msg or 'Lỗi không xác định.'}", "error")
            logger.error(f"Failed to delete interaction history: {error_msg}")
    except Exception as e:
        logger.critical(f"Lỗi nghiêm trọng khi xóa lịch sử tương tác: {e}", exc_info=True)
        flash(f"Lỗi không mong muốn khi xóa lịch sử: {e}", "error")

    return redirect(url_for('admin.view_history'))

@admin_bp.route('/test-neo4j')
def test_neo4j_connection():
    """Route để kiểm tra kết nối Neo4j."""
    result_data = None
    error_msg = None
    try:
        # Thử chạy một truy vấn Cypher đơn giản
        cypher_query = "RETURN 1 as result"
        results = graph_db.execute_read(cypher_query)

        if results is not None and len(results) > 0:
            result_data = results[0] # Lấy bản ghi đầu tiên
            return jsonify({"status": "success", "message": "Neo4j connection successful!", "data": result_data})
        elif results == []: # Truy vấn chạy nhưng không trả về gì (ít xảy ra với RETURN 1)
             return jsonify({"status": "success", "message": "Neo4j query executed, no data returned."})
        else: # Hàm execute_read trả về None -> Lỗi
            error_msg = "graph_db.execute_read returned None (Check server logs for Neo4j driver/query errors)."
            return jsonify({"status": "error", "message": error_msg}), 500

    except Exception as e:
        # Lỗi xảy ra trong chính route test
        error_msg = f"Unexpected error in test route: {e}"
        current_app.logger.error(error_msg, exc_info=True)
        return jsonify({"status": "error", "message": error_msg}), 500




@admin_bp.route('/screen/<path:screen_id>/elements')
#@admin_required
def admin_screen_elements(screen_id):
    """
    Hiển thị trang chi tiết các phần tử của một màn hình (Screen).
    Đã cập nhật để lấy và truyền kích thước màn hình gốc.
    """
    logger = current_app.logger if current_app else print
    logger.info(f"Đang tải trang phần tử cho screen_id: {screen_id}")

    screen_data_from_neo4j = None
    elements_list = []
    screenshot_url = None
    valid_classifications = []
    original_width = None  # <<< Khởi tạo biến kích thước
    original_height = None # <<< Khởi tạo biến kích thước

    if not graph_db or not db or not ai_service:
        flash("Lỗi nghiêm trọng: Database, GraphDB hoặc AI module chưa sẵn sàng.", "error")
        return redirect(url_for('admin.index'))

    try:
        # 1. Lấy thông tin Screen từ Neo4j
        screen_data_from_neo4j = graph_db.get_screen_with_elements(screen_id)
        if not screen_data_from_neo4j:
            flash(f"Không tìm thấy Screen node với ID '{screen_id}' trong Neo4j.", 'warning')
            return redirect(url_for('admin.admin_mapping_viewer'))

        app_name = screen_data_from_neo4j.get('app_name')
        filename_from_neo4j = screen_data_from_neo4j.get('screenshot_path')
        logger.debug(f"Dữ liệu Screen từ Neo4j (trong admin_screen_elements): {screen_data_from_neo4j}") # <<< Log này rất quan trọng

        fetched_width_neo4j = screen_data_from_neo4j.get('width')  # Lấy từ dict Neo4j
        fetched_height_neo4j = screen_data_from_neo4j.get('height') 
        logger.debug(f"Giá trị width/height lấy trực tiếp từ Neo4j node props: W='{fetched_width_neo4j}', H='{fetched_height_neo4j}'")

        # 2. Tạo URL Ảnh chụp (logic giữ nguyên)
        filename_from_neo4j = screen_data_from_neo4j.get('screenshot_path')
        if filename_from_neo4j and app_name:
            # Tạo URL để hiển thị (như cũ)
            try:
                screenshot_url = url_for('serve_app_specific_screenshot', filename=filename_from_neo4j, _external=False)
                logger.info(f"[admin_screen_elements] Đã tạo URL screenshot: '{screenshot_url}'")
            except Exception as url_err:
                logger.error(f"[admin_screen_elements] Lỗi tạo URL screenshot: {url_err}", exc_info=True)
                screenshot_url = None

            # Đọc kích thước từ file ảnh trên server
            try:
                # Lấy đường dẫn gốc từ config
                base_path = current_app.config.get('SCREENSHOT_STORAGE_PATH')
                if not base_path:
                     logger.error("SCREENSHOT_STORAGE_PATH không được cấu hình trong Flask config!")
                     raise ValueError("Missing screenshot storage path configuration.")

                # Giả sử cấu trúc lưu trữ là base_path/app_name/filename.png
                # *** ĐIỀU CHỈNH ĐƯỜNG DẪN NÀY CHO PHÙ HỢP VỚI CẤU TRÚC THỰC TẾ CỦA BẠN ***
                full_image_path = os.path.join(base_path, app_name, filename_from_neo4j)
                logger.debug(f"Attempting to read dimensions from image file: {full_image_path}")

                if os.path.exists(full_image_path):
                    with Image.open(full_image_path) as img:
                        img_width, img_height = img.size
                        original_width = img_width
                        original_height = img_height
                        logger.info(f"Đọc kích thước từ file ảnh thành công: W={original_width}, H={original_height}")
                else:
                    logger.warning(f"File ảnh không tồn tại tại đường dẫn: {full_image_path}")

            except FileNotFoundError:
                 logger.warning(f"File ảnh không tồn tại (FileNotFoundError): {full_image_path}")
            except Exception as img_err:
                 logger.error(f"Lỗi khi đọc kích thước từ file ảnh '{filename_from_neo4j}': {img_err}", exc_info=True)
                 # Giữ nguyên original_width/height là None

        elif not filename_from_neo4j:
             logger.info(f"Không có screenshot_path cho screen {screen_id}, không thể lấy kích thước từ ảnh.")
        elif not app_name:
             logger.warning(f"Không có app_name cho screen {screen_id}, không thể xây dựng đường dẫn ảnh.")

        # 3. Lấy trạng thái khám phá tự động (logic giữ nguyên)
        tried_element_ids = set()
        if app_name:
            outgoing_transitions = graph_db.get_outgoing_transitions(screen_id, app_name) or []
            for trans_props in outgoing_transitions:
                 if isinstance(trans_props, dict):
                     el_id = trans_props.get('element_id')
                     action_type = trans_props.get('actionType')
                     macro_code = trans_props.get('macro_code')
                     is_interaction = (action_type in ['click', 'input']) or \
                                      (action_type == 'run_macro' and macro_code in ['UI_CLICK', 'UI_INPUT_TEXT', 'UI_TAP_XY'])
                     if el_id and is_interaction: tried_element_ids.add(el_id)
        else: logger.warning(f"app_name không có cho screen {screen_id}, không thể lấy outgoing transitions.")

        # 4. Lấy chi tiết elements và KÍCH THƯỚC MÀN HÌNH từ log PostgreSQL
        detailed_ui_state = db.get_last_detailed_ui_state_for_screen(screen_id) # <<< Hàm này trả về dict JSON

        # === LOGIC LẤY KÍCH THƯỚC MÀN HÌNH ===
        if detailed_ui_state and isinstance(detailed_ui_state, dict):
            logger.debug("Tìm thấy detailed_ui_state từ log.")
            # *** QUAN TRỌNG: Kiểm tra và thay thế 'width', 'height' bằng tên key đúng trong JSON log của bạn ***
            fetched_width = detailed_ui_state.get('width')  # <<< THAY KEY NẾU CẦN
            fetched_height = detailed_ui_state.get('height') # <<< THAY KEY NẾU CẦN
            logger.debug(f"Giá trị width/height gốc từ log: W='{fetched_width}', H='{fetched_height}'")

            # Chuyển đổi thành số nguyên, nếu không hợp lệ thì để None
            try:
                original_width = int(fetched_width_neo4j) if fetched_width_neo4j is not None else None
            except (ValueError, TypeError):
                logger.warning(f"Giá trị width ('{fetched_width_neo4j}') từ Neo4j không phải là số nguyên hợp lệ.")
                original_width = None
            try:
                original_height = int(fetched_height_neo4j) if fetched_height_neo4j is not None else None
            except (ValueError, TypeError):
                logger.warning(f"Giá trị height ('{fetched_height_neo4j}') từ Neo4j không phải là số nguyên hợp lệ.")
                original_height = None
        else:
             logger.warning(f"Không tìm thấy detailed_ui_state hoặc 'elements' không phải list cho screen {screen_id}.")

        # =======================================

        # 5. Xử lý danh sách elements từ log (logic giữ nguyên, chỉ cần detailed_ui_state)
        if detailed_ui_state and isinstance(detailed_ui_state.get('elements'), list):
            elements_list_from_log = detailed_ui_state.get('elements', [])
            logger.debug(f"Tìm thấy {len(elements_list_from_log)} elements trong detailed_ui_state log.")
            saved_data = db.get_element_classifications_for_screen(screen_id) or {}
            for el_from_log in elements_list_from_log:
                el_id = el_from_log.get('element_id')
                if el_id:
                    element_saved_data = saved_data.get(el_id, {})
                    classification = element_saved_data.get('classification', 'unclassified')
                    manual_override = element_saved_data.get('manual_explored_override')
                    auto_explored_status = el_id in tried_element_ids
                    override_active = 'auto'; display_explored_status = auto_explored_status
                    if manual_override is True: display_explored_status = True; override_active = 'force_explored'
                    elif manual_override is False: display_explored_status = False; override_active = 'force_unexplored'
                    el_from_log['classification'] = classification
                    el_from_log['display_explored_status'] = display_explored_status
                    el_from_log['override_active'] = override_active
                    elements_list.append(el_from_log)
                else: logger.warning(f"Bỏ qua element thiếu element_id trong log: {el_from_log}")
        else:
             logger.warning(f"Không có list 'elements' trong detailed_ui_state log.")


        # 6. Lấy danh sách phân loại hợp lệ (logic giữ nguyên)
        if hasattr(ai_service, 'VALID_CLASSIFICATIONS'):
            valid_classifications = ai_service.VALID_CLASSIFICATIONS
        else:
            logger.error("VALID_CLASSIFICATIONS not found in ai_service module!")
            flash("Lỗi cấu hình: Không tìm thấy danh sách phân loại hợp lệ.", "error")

    except Exception as e:
        logger.error(f"Lỗi tải trang phần tử màn hình cho {screen_id}: {e}", exc_info=True)
        flash(f"Lỗi không mong muốn khi tải dữ liệu trang: {e}", "error")
        if screen_data_from_neo4j is None: return redirect(url_for('admin.admin_mapping_viewer'))
        elements_list = []
        # Đảm bảo original_width/height vẫn là None nếu có lỗi xảy ra trước khi lấy được chúng
        original_width = original_width if 'original_width' in locals() else None
        original_height = original_height if 'original_height' in locals() else None


    # Render template, truyền thêm original_screen_width và original_screen_height
    return render_template('admin_screen_elements.html',
                           screen=screen_data_from_neo4j,   # Dữ liệu Screen node
                           elements=elements_list,          # List elements đã xử lý
                           valid_classifications=valid_classifications,
                           screenshot_url=screenshot_url,   # URL ảnh
                           original_screen_width=original_width,   # <<< Truyền chiều rộng gốc
                           original_screen_height=original_height)

# === API MỚI ĐỂ CẬP NHẬT MANUAL EXPLORED OVERRIDE ===
@admin_bp.route('/api/element/mark_explored', methods=['POST'])
#@admin_required
def api_mark_element_explored():
    """API Endpoint để cập nhật manual_explored_override trong PostgreSQL."""
    logger = current_app.logger if current_app else print
    if not request.is_json:
        return jsonify({"success": False, "error": "Request must be JSON"}), 400

    data = request.get_json()
    screen_id = data.get('screen_id')
    element_id = data.get('element_id')
    # Nhận trạng thái mới: 'force_explored', 'force_unexplored', hoặc 'auto'
    new_status_str = data.get('override_status')

    logger.debug(f"API Request mark_explored: screen={screen_id}, element={element_id}, status_str={new_status_str}")

    if not screen_id or not element_id or new_status_str not in ['force_explored', 'force_unexplored', 'auto']:
        return jsonify({"success": False, "error": "Missing or invalid parameters (screen_id, element_id, override_status)"}), 400

    # Chuyển đổi chuỗi trạng thái thành giá trị boolean hoặc None cho DB
    override_value: bool | None
    if new_status_str == 'force_explored':
        override_value = True
    elif new_status_str == 'force_unexplored':
        override_value = False
    else: # 'auto'
        override_value = None # Đặt là NULL trong DB để xóa ghi đè

    if not db:
         logger.error("Database module 'db' not available in api_mark_element_explored.")
         return jsonify({"success": False, "error": "Server configuration error (DB)."}), 500

    try:
        # Gọi hàm DB mới để cập nhật override status
        success, error_msg = db.update_manual_explored_override(
            screen_id=screen_id,
            element_id=element_id,
            override_status=override_value
        )
        if success:
            logger.info(f"Successfully set manual_explored_override for '{element_id}' on screen '{screen_id}' to '{override_value}'.")
            return jsonify({"success": True, "message": f"Element '{element_id}' override status updated."})
        else:
            logger.error(f"Failed to update override status for {screen_id}/{element_id}: {error_msg}")
            return jsonify({"success": False, "error": error_msg or "Failed to update override status in database."}), 500
    except Exception as e:
        logger.error(f"Exception in api_mark_element_explored: {e}", exc_info=True)
        return jsonify({"success": False, "error": "An internal server error occurred."}), 500

@admin_bp.route('/api/screen/<path:screen_id>/classify_element', methods=['POST'])
#@admin_required
def api_classify_element(screen_id):
    """API Endpoint để cập nhật classification cho một element."""
    if not request.is_json:
        return jsonify({"success": False, "error": "Request must be JSON"}), 400

    data = request.get_json()
    element_id = data.get('element_id')
    classification = data.get('classification')

    if not element_id or not classification:
        return jsonify({"success": False, "error": "Missing element_id or classification"}), 400

    if classification not in ai_service.VALID_CLASSIFICATIONS:
         return jsonify({"success": False, "error": f"Invalid classification value: {classification}"}), 400

    try:
        success = graph_db.update_element_classification(screen_id, element_id, classification)
        if success:
            return jsonify({"success": True, "message": f"Element '{element_id}' classified as '{classification}'."})
        else:
            return jsonify({"success": False, "error": "Failed to update classification in database."}), 500
    except Exception as e:
        print(f"Error updating element classification: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": "An internal server error occurred."}), 500

@admin_bp.route('/api/screen/<path:screen_id>/suggest_classifications', methods=['POST']) # <<< ĐỔI SANG POST
#@admin_required
def api_suggest_classifications(screen_id):
    """
    API Endpoint để lấy gợi ý phân loại từ AI, nhận danh sách element từ request body.
    """
    logger = current_app.logger if current_app else print
    logger.info(f"Received AI suggestion request for screen: {screen_id}")

    # Kiểm tra request có phải JSON không
    if not request.is_json:
        logger.warning("Suggest classifications request is not JSON.")
        return jsonify({"success": False, "error": "Request must be JSON"}), 400

    data = request.get_json()
    # === LẤY DANH SÁCH ELEMENT TỪ REQUEST BODY ===
    elements_to_classify = data.get('elements') # Mong đợi payload dạng {"elements": [...]}

    # Validate input
    if not isinstance(elements_to_classify, list):
        logger.warning(f"Invalid 'elements' data received for screen {screen_id}. Expected a list.")
        return jsonify({"success": False, "error": "Invalid payload format: 'elements' key must be a list."}), 400

    if not elements_to_classify:
         logger.info(f"No elements provided in the request for screen {screen_id} to suggest classifications.")
         return jsonify({"success": True, "suggestions": [], "message": "No elements provided to classify."})

    # Kiểm tra module AI Service
    if not ai_service:
        logger.error("AI Service module is not available.")
        return jsonify({"success": False, "error": "AI Service is unavailable."}), 503

    logger.debug(f"Requesting AI suggestions for {len(elements_to_classify)} elements from screen {screen_id}.")
    # Log thử vài element đầu tiên nhận được
    # logger.debug(f"Sample elements received: {elements_to_classify[:2]}")

    try:
        # === GỌI HÀM AI SERVICE VỚI DỮ LIỆU NHẬN ĐƯỢC ===
        # Hàm suggest_element_classifications chỉ cần các trường cơ bản
        # (Đảm bảo hàm AI không cần screen_id hay thông tin khác nữa)
        suggestions = ai_service.suggest_element_classifications(elements_to_classify)
        # Hàm này nên trả về list các element đã được bổ sung 'suggested_classification'

        # Kiểm tra kết quả trả về từ AI service (có thể nó trả về None nếu lỗi)
        if suggestions is None:
             logger.error(f"ai_service.suggest_element_classifications returned None for screen {screen_id}.")
             # Không nên trả lỗi 500 ngay, có thể AI không đưa ra gợi ý
             return jsonify({"success": True, "suggestions": [], "message": "AI service did not return suggestions."})

        logger.info(f"AI suggestions generated successfully for {len(suggestions)} elements on screen {screen_id}.")
        return jsonify({"success": True, "suggestions": suggestions}) # Trả về list đã có gợi ý

    except Exception as e:
        logger.error(f"Error getting AI classification suggestions for screen {screen_id}: {e}", exc_info=True)
        # traceback.print_exc() # In traceback ra console nếu cần debug sâu
        return jsonify({"success": False, "error": f"Failed to get AI suggestions: {type(e).__name__}"}), 500


@admin_bp.route('/api/task_assignment/<int:assignment_id>/update_status', methods=['POST'])
# @admin_required # Tạm thời comment out để kiểm tra
def api_update_task_status(assignment_id):
    # Kiểm tra xem request có phải JSON không
    if not request.is_json:
        return jsonify({"success": False, "error": "Request body must be JSON"}), 400

    data = request.get_json()
    new_status = data.get('new_status')

    # Validate input status
    if new_status not in ['active', 'paused']:
        return jsonify({"success": False, "error": "Invalid status value. Must be 'active' or 'paused'."}), 400

    # Kiểm tra module DB
    if not db:
         current_app.logger.error("Database module 'db' not available in api_update_task_status.")
         return jsonify({"success": False, "error": "Server configuration error (DB)."}), 500

    try:
        # Gọi hàm DB để cập nhật status (đã tạo ở bước trước)
        success, error_msg = db.update_task_mapping_status(assignment_id, new_status)

        if success:
             return jsonify({"success": True, "message": f"Task assignment {assignment_id} mapping status set to {new_status}"})
        else:
             status_code = 404 if "Không tìm thấy" in (error_msg or "") else 500
             return jsonify({"success": False, "error": error_msg or "Failed to update status in database."}), status_code

    except Exception as e:
        current_app.logger.error(f"Exception in api_update_task_status for ID {assignment_id}: {e}", exc_info=True)
        traceback.print_exc()
        return jsonify({"success": False, "error": f"Internal server error: {type(e).__name__}"}), 500

# Thêm/Sửa trong file app/admin_routes.py

from flask import Blueprint, request, jsonify, current_app, url_for # Đảm bảo có url_for
# ... (các import khác của bạn) ...
from . import graph_db # Hoặc from app import graph_db tùy cấu trúc

# ... (Blueprint definition admin_bp = Blueprint(...) ) ...

@admin_bp.route('/api/mapping_data', methods=['GET'])
# @admin_required # Bỏ comment nếu bạn dùng xác thực
def api_get_app_graph_data():
    """
    API Endpoint để lấy dữ liệu đồ thị (nodes và edges) cho một ứng dụng cụ thể.
    Dữ liệu này được sử dụng bởi Cytoscape.js để vẽ bản đồ.
    Đã cập nhật để bao gồm original_width và original_height cho mỗi node Screen.
    """
    logger = current_app.logger if current_app else print
    app_name = request.args.get('app_name')
    logger.info(f"API Mapping: Yêu cầu dữ liệu đồ thị cho app: '{app_name}'")

    if not app_name:
        logger.warning("API Mapping: Thiếu tham số 'app_name' trong query.")
        return jsonify({"error": "Thiếu tham số app_name"}), 400

    if not graph_db: # Kiểm tra module graph_db
         logger.error("API Mapping: GraphDB module chưa sẵn sàng.")
         return jsonify({"error": "Lỗi cấu hình server (GraphDB)"}), 500

    nodes_list_for_cytoscape = []
    edges_list_for_cytoscape = []
    node_ids_found_in_query = set() # Dùng để kiểm tra cạnh hợp lệ

    try:
        # --- LẤY DỮ LIỆU TỪ NEO4J TRỰC TIẾP TRONG ROUTE ---
        driver = graph_db.get_driver() # Cần có hàm get_driver() trong graph_db.py
        if not driver:
            logger.error("API Mapping: Neo4j driver không khả dụng.")
            return jsonify({"error": "Lỗi kết nối cơ sở dữ liệu đồ thị"}), 500

        # Lấy tên database từ config nếu có, nếu không dùng default 'neo4j'
        db_name_neo4j = current_app.config.get('NEO4J_DATABASE', 'neo4j')

        with driver.session(database=db_name_neo4j) as session:
            # 1. Query lấy các Node Screen
            # Bao gồm các thuộc tính cần thiết: id, activity, status, element_count,
            # screenshot_path (để tạo URL), và quan trọng là width, height.
            node_query = """
                MATCH (n:Screen {app_name: $app_name})
                WHERE n.screen_id IS NOT NULL
                RETURN n.screen_id AS id,
                       n.activity_name AS activity,
                       n.status AS status,
                       n.element_count AS element_count,
                       n.screenshot_path AS screenshot_path,
                       n.width AS width,          // <<< LẤY THUỘC TÍNH width TỪ NEO4J
                       n.height AS height        // <<< LẤY THUỘC TÍNH height TỪ NEO4J
                ORDER BY n.screen_id
            """
            logger.debug(f"API Mapping: Executing Node Query for app '{app_name}':\n{node_query}")
            nodes_result = session.run(node_query, app_name=app_name)

            for record in nodes_result:
                node_id = record["id"]
                if not node_id: # Bỏ qua nếu không có screen_id (dù query đã có WHERE)
                    continue

                element_count = record["element_count"] if record["element_count"] is not None else 0
                screenshot_filename = record["screenshot_path"]
                generated_screenshot_url = None

                # Tạo URL cho ảnh chụp màn hình
                if screenshot_filename:
                    try:
                        # Sử dụng endpoint 'serve_app_specific_screenshot'
                        generated_screenshot_url = url_for('serve_app_specific_screenshot', filename=screenshot_filename, _external=False)
                    except Exception as url_e:
                        logger.error(f"API Mapping: Lỗi tạo URL cho ảnh '{screenshot_filename}' của node {node_id}: {url_e}")

                # Tạo dictionary dữ liệu cho node Cytoscape
                node_data = {
                    "id": node_id,
                    "activity": record["activity"],
                    "status": record["status"],
                    "element_count": element_count,
                    "screenshot_url": generated_screenshot_url, # URL đã tạo
                    "original_width": record["width"],      # <<< TRẢ VỀ CHO FRONTEND
                    "original_height": record["height"],    # <<< TRẢ VỀ CHO FRONTEND
                    "label": node_id[:12] + '...' if node_id and len(node_id) > 12 else node_id # Nhãn ngắn gọn
                }
                # Loại bỏ các key có giá trị None để JSON response gọn hơn (tùy chọn)
                node_data_clean = {k: v for k, v in node_data.items() if v is not None}
                nodes_list_for_cytoscape.append({"data": node_data_clean})
                node_ids_found_in_query.add(node_id)

            logger.info(f"API Mapping: Processed {len(nodes_list_for_cytoscape)} nodes for app '{app_name}'.")

            # 2. Query lấy các Edges (TRANSITION)
            # Đảm bảo các thuộc tính trả về khớp với những gì frontend cần
            edge_query = """
                MATCH (a:Screen {app_name: $app_name})-[r:TRANSITION]->(b:Screen {app_name: $app_name})
                WHERE a.screen_id IS NOT NULL AND b.screen_id IS NOT NULL
                RETURN a.screen_id AS source,
                       b.screen_id AS target,
                       r.actionType AS action_type,      // Giữ tên key nhất quán
                       r.macro_code AS macro_code,
                       r.element_id AS element_id,        // Thuộc tính element_id trên cạnh
                       r.identifier_type AS identifier_type,
                       r.element_text AS element_text,
                       r.status AS status,
                       r.attempt_count AS attempt_count,
                       r.success_count AS success_count,
                       r.params_json_str AS params_json, // Đảm bảo đây là tên cột/thuộc tính đúng
                       elementId(r) AS neo4j_edge_id    // ID nội bộ của Neo4j cho cạnh
            """
            logger.debug(f"API Mapping: Executing Edge Query for app '{app_name}'")
            edges_result = session.run(edge_query, app_name=app_name)

            edge_counter_for_id = 0 # Dùng nếu neo4j_edge_id bị null
            for record in edges_result:
                edge_counter_for_id += 1
                source_id = record["source"]
                target_id = record["target"]

                # Chỉ thêm cạnh nếu cả node nguồn và đích đều hợp lệ và đã được lấy ở bước trước
                if source_id not in node_ids_found_in_query or target_id not in node_ids_found_in_query:
                    logger.warning(f"API Mapping: Bỏ qua cạnh có ID Neo4j '{record['neo4j_edge_id']}' vì node nguồn '{source_id}' hoặc đích '{target_id}' không hợp lệ/không được tìm thấy.")
                    continue

                # Tạo ID cho cạnh Cytoscape
                edge_id = f"edge_{record['neo4j_edge_id']}" if record['neo4j_edge_id'] else f"edge_auto_{source_id}_{target_id}_{edge_counter_for_id}"

                # Tạo dictionary dữ liệu cho cạnh
                edge_data = {
                    "id": edge_id,
                    "source": source_id,
                    "target": target_id
                }
                # Thêm các thuộc tính khác của cạnh nếu chúng tồn tại
                for key in record.keys():
                    if key not in ["source", "target", "neo4j_edge_id"] and record[key] is not None:
                        edge_data[key] = record[key]

                edges_list_for_cytoscape.append({"data": edge_data})

            logger.info(f"API Mapping: Processed {len(edges_list_for_cytoscape)} valid edges for app '{app_name}'.")

        # Kết thúc session with driver.session...

    except graph_db.ServiceUnavailable as su_err: # Bắt lỗi ServiceUnavailable từ graph_db
        logger.error(f"API Mapping: Lỗi kết nối Neo4j khi lấy dữ liệu cho app '{app_name}': {su_err}", exc_info=True)
        return jsonify({"error": "Lỗi dịch vụ cơ sở dữ liệu đồ thị."}), 503
    except Exception as e:
        logger.error(f"API Mapping: Lỗi không mong muốn khi lấy dữ liệu đồ thị cho app '{app_name}': {e}", exc_info=True)
        return jsonify({"error": "Lỗi server nội bộ khi xử lý yêu cầu."}), 500

    # Tạo dict kết quả cuối cùng
    final_graph_data = {"nodes": nodes_list_for_cytoscape, "edges": edges_list_for_cytoscape}
    logger.info(f"API Mapping: Trả về dữ liệu đồ thị thành công cho app '{app_name}'.")
    return jsonify(final_graph_data)


@admin_bp.route('/mapping/')
@admin_bp.route('/mapping/<path:app_name>')
# @admin_required
def admin_mapping_viewer(app_name=None):
    """Hiển thị trang xem đồ thị mapping."""
    title = "App Mapping Viewer"
    available_apps = [] # Danh sách các app đã được map

    # (Tùy chọn) Lấy danh sách các app_name đã có trong Neo4j để tạo dropdown chọn app
    if graph_db:
        try:
            available_apps = graph_db.get_distinct_app_names() or [] # Cần tạo hàm này trong graph_db.py
        except Exception as e:
             current_app.logger.warning(f"Could not fetch distinct app names: {e}")

    if app_name:
        title = f"Mapping for: {app_name}"

    # Render template mới, truyền app_name và danh sách app vào
    return render_template('admin_mapping_viewer.html',
                           title=title,
                           selected_app_name=app_name, # App đang được chọn (có thể None)
                           available_apps=available_apps)


# === API MỚI ĐỂ LƯU CLASSIFICATION VÀO POSTGRESQL ===
@admin_bp.route('/api/element/classify', methods=['POST'])
#@admin_required
def api_classify_element_postgres():
    """API Endpoint để cập nhật classification vào PostgreSQL."""
    logger = current_app.logger if current_app else print
    if not request.is_json:
        return jsonify({"success": False, "error": "Request must be JSON"}), 400

    data = request.get_json()
    screen_id = data.get('screen_id')
    element_id = data.get('element_id')
    identifier_type = data.get('identifier_type') # Lấy thêm identifier_type
    classification = data.get('classification')

    logger.debug(f"API Request classify: screen={screen_id}, element={element_id}, type={identifier_type}, class={classification}")

    if not screen_id or not element_id or not classification:
        return jsonify({"success": False, "error": "Missing screen_id, element_id, or classification"}), 400

    # Validate classification value
    if not ai_service or not hasattr(ai_service, 'VALID_CLASSIFICATIONS') or classification not in ai_service.VALID_CLASSIFICATIONS:
            logger.warning(f"Invalid classification value received: {classification}")
            return jsonify({"success": False, "error": f"Invalid classification value: {classification}"}), 400

    if not db:
            logger.error("Database module 'db' not available in api_classify_element_postgres.")
            return jsonify({"success": False, "error": "Server configuration error (DB)."}), 500

    try:
        # Gọi hàm DB mới để UPSERT vào PostgreSQL
        success, error_msg = db.upsert_element_classification(
            screen_id=screen_id,
            element_id=element_id,
            identifier_type=identifier_type, # Truyền identifier_type
            classification=classification,
            source='manual' # Đánh dấu là do người dùng sửa
        )
        if success:
            logger.info(f"Successfully classified element '{element_id}' on screen '{screen_id}' as '{classification}'.")
            return jsonify({"success": True, "message": f"Element '{element_id}' classified as '{classification}'."})
        else:
            logger.error(f"Failed to upsert classification for {screen_id}/{element_id}: {error_msg}")
            return jsonify({"success": False, "error": error_msg or "Failed to update classification in database."}), 500
    except Exception as e:
        logger.error(f"Exception in api_classify_element_postgres: {e}", exc_info=True)
        return jsonify({"success": False, "error": "An internal server error occurred."}), 500

# Trong app/admin_routes.py

@admin_bp.route('/api/screen_elements_for_mapping/<string:screen_id>', methods=['GET'])
def api_get_screen_elements_for_mapping(screen_id):
    driver = None
    try:
        # current_app.logger.debug(f"API call: screen_elements_for_mapping for {screen_id}")
        driver = graph_db.get_driver() # Giả sử bạn có hàm này
        # Đảm bảo bạn đang sử dụng database đúng nếu có cấu hình
        db_name = current_app.config.get("NEO4J_DATABASE", "neo4j") 
        with driver.session(database=db_name) as session:
            # Sử dụng execute_read cho các transaction chỉ đọc
            elements = session.execute_read(graph_db.get_elements_for_screen, screen_id)
        
        if elements is None: 
            # Điều này không nên xảy ra nếu query đúng và screen_id tồn tại, 
            # nhưng get_elements_for_screen có thể trả về None nếu có lỗi không mong muốn bên trong nó.
            current_app.logger.warning(f"get_elements_for_screen trả về None cho screen_id: {screen_id}")
            elements = []

        # current_app.logger.debug(f"API success: Returning {len(elements)} elements for screen {screen_id}")
        return jsonify(success=True, elements=elements)

    except AttributeError as ae: 
        # Bắt lỗi AttributeError cụ thể có thể đến từ get_elements_for_screen
        current_app.logger.error(f"Neo4j AttributeError trong API (screen_elements_for_mapping cho {screen_id}): {str(ae)}", exc_info=True)
        return jsonify(success=False, error=f"Lỗi thuộc tính Neo4j khi xử lý dữ liệu: {str(ae)}"), 500
    except Exception as e:
        # Bắt tất cả các lỗi khác
        current_app.logger.error(f"API (screen_elements_for_mapping): Lỗi khi lấy elements cho screen '{screen_id}'. Error: {str(e)}", exc_info=True)
        # Trả về thông báo lỗi chi tiết hơn cho frontend để dễ gỡ lỗi
        return jsonify(success=False, error=f"Không thể lấy dữ liệu elements từ CSDL. Chi tiết server: {str(e)}"), 500

# Trong app/admin_routes.py
import math # Đảm bảo import math ở đầu file nếu chưa có
from flask import Blueprint, render_template, request, flash, current_app, jsonify # Đảm bảo các import
# ... (các import khác của bạn: db, graph_db, psycopg2, json) ...
from . import database as db # Hoặc from app import database as db
import psycopg2 # Để bắt lỗi cụ thể
import psycopg2.extras # Để dùng DictCursor

# ... (admin_bp = Blueprint(...) đã được định nghĩa) ...

@admin_bp.route('/mapping/screen-definitions')
# @admin_required # Nếu bạn có decorator xác thực
def view_screen_definitions():
    title = "Quản lý Định nghĩa Màn hình (PIE)"
    logger = current_app.logger # Sử dụng logger của Flask app

    # 1. Lấy danh sách các app_name duy nhất cho dropdown filter
    distinct_app_names_for_filter = []
    try:
        conn = db.get_db_connection()
        if conn:
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                    cur.execute("SELECT DISTINCT app_name FROM screen_definitions WHERE app_name IS NOT NULL ORDER BY app_name;")
                    distinct_app_names_for_filter = [row['app_name'] for row in cur.fetchall()]
            except Exception as e_distinct_app:
                logger.error(f"Lỗi khi lấy distinct app_names cho screen_definitions filter: {e_distinct_app}", exc_info=True)
                flash("Lỗi tải danh sách app cho bộ lọc.", "warning") # Chỉ warning, trang vẫn có thể hoạt động
            finally:
                conn.close()
        else:
            flash("Không thể kết nối CSDL để lấy danh sách app cho bộ lọc.", "error")
    except Exception as e_conn:
        logger.error(f"Lỗi kết nối CSDL ban đầu khi lấy distinct_app_names: {e_conn}", exc_info=True)
        flash("Lỗi kết nối CSDL nghiêm trọng.", "error")
        # Có thể redirect hoặc render với list rỗng tùy theo mức độ nghiêm trọng bạn muốn xử lý

    # 2. Lấy các tham số filter và phân trang từ request
    selected_app_filter = request.args.get('app_name_filter', '').strip() # Chuỗi rỗng nếu "-- Tất cả Apps --"
    page = request.args.get('page', 1, type=int)
    if page < 1: 
        page = 1
    
    # PER_PAGE_PIE_DEFINITIONS nên được định nghĩa ở đầu file hoặc lấy từ config
    PER_PAGE_PIE_DEFINITIONS = current_app.config.get('PER_PAGE_PIE_DEFINITIONS', 15) 

    definitions_list = []
    pagination_details = None
    total_items_for_display = 0

    # 3. Lấy dữ liệu định nghĩa PIE từ CSDL
    try:
        if selected_app_filter: 
            # Lọc theo một app_name cụ thể
            logger.info(f"VIEW_SCREEN_DEFS: Lọc định nghĩa PIE cho app_name = '{selected_app_filter}'")
            # Hàm get_screen_definitions_for_app hiện tại không hỗ trợ phân trang.
            # Nếu số lượng định nghĩa cho một app có thể rất lớn, bạn cần sửa hàm này
            # để hỗ trợ LIMIT/OFFSET hoặc thực hiện phân trang ở Python.
            # Tạm thời, giả sử số lượng cho một app không quá lớn để cần phân trang ở DB.
            all_defs_for_app = db.get_screen_definitions_for_app(selected_app_filter, activity_name=None)
            
            if all_defs_for_app is None: # Lỗi DB khi gọi hàm
                flash(f"Lỗi khi tải danh sách định nghĩa cho app '{selected_app_filter}'.", "error")
                definitions_list = []
                total_items_for_display = 0
            else:
                # Phân trang thủ công ở Python nếu cần
                total_items_for_display = len(all_defs_for_app)
                if total_items_for_display > 0:
                    start_index = (page - 1) * PER_PAGE_PIE_DEFINITIONS
                    end_index = start_index + PER_PAGE_PIE_DEFINITIONS
                    definitions_list = all_defs_for_app[start_index:end_index]
                else: # Không có định nghĩa nào cho app này
                    definitions_list = [] 
                    # Không cần flash ở đây, template sẽ tự hiển thị "Không tìm thấy..."
        
        else: # selected_app_filter là rỗng, nghĩa là xem "Tất cả Apps"
            logger.info(f"VIEW_SCREEN_DEFS: Lấy tất cả định nghĩa PIE, page {page}")
            # Gọi hàm lấy tất cả có phân trang
            defs_page, total_db_items = db.get_all_screen_definitions(page=page, per_page=PER_PAGE_PIE_DEFINITIONS)
            
            if defs_page is None: # Lỗi DB khi gọi hàm
                flash("Lỗi khi tải danh sách tất cả định nghĩa màn hình.", "error")
                definitions_list = []
                total_items_for_display = 0
            else:
                definitions_list = defs_page
                total_items_for_display = total_db_items if total_db_items is not None else 0
                if total_items_for_display == 0 and not distinct_app_names_for_filter:
                    # Chỉ flash nếu thực sự không có định nghĩa nào trong toàn bộ hệ thống
                    flash("Chưa có định nghĩa màn hình nào được tạo. Hãy bắt đầu bằng cách thêm mới.", "info")

    except Exception as e_data_fetch:
        logger.error(f"Lỗi nghiêm trọng khi lấy dữ liệu screen_definitions: {e_data_fetch}", exc_info=True)
        flash("Lỗi không mong muốn khi tải dữ liệu định nghĩa màn hình.", "error")
        definitions_list = [] # Đảm bảo là list rỗng
        total_items_for_display = 0


    # 4. Tạo thông tin phân trang (nếu có dữ liệu)
    if total_items_for_display > 0:
        total_pages = math.ceil(total_items_for_display / PER_PAGE_PIE_DEFINITIONS)
        
        # Xử lý trường hợp page yêu cầu vượt quá số trang thực tế
        if page > total_pages and total_pages > 0: 
            # Trong trường hợp này, definitions_list có thể rỗng nếu phân trang ở DB
            # Hoặc nếu phân trang ở Python, nó đã được cắt đúng ở trên
            # Chỉ cần đảm bảo `page` trong `pagination_details` là hợp lệ
            page = total_pages 
        
        extra_params_for_pagination = {}
        if selected_app_filter: # Giữ lại filter app_name khi chuyển trang
            extra_params_for_pagination['app_name_filter'] = selected_app_filter

        pagination_details = {
            'page': page, 
            'per_page': PER_PAGE_PIE_DEFINITIONS, 
            'total_items': total_items_for_display,
            'total_pages': total_pages, 
            'has_prev': page > 1, 
            'has_next': page < total_pages,
            'prev_num': page - 1 if page > 1 else None,
            'next_num': page + 1 if page < total_pages else None,
            'page_param': 'page', # Tên query param cho phân trang
            'extra_params': extra_params_for_pagination 
        }
    
    logger.debug(f"Rendering admin_screen_definitions.html with {len(definitions_list)} definitions. Filter: '{selected_app_filter}'. Pagination: {pagination_details}")
    
    # 5. Render template
    return render_template('admin_screen_definitions.html', 
                           title=title, 
                           definitions=definitions_list, # Sẽ là list rỗng nếu không có dữ liệu/lỗi
                           distinct_app_names=distinct_app_names_for_filter, 
                           selected_app_filter=selected_app_filter,
                           pagination=pagination_details) # Sẽ là None nếu không có dữ liệu/lỗi

@admin_bp.route('/api/mapping/screen-definitions', methods=['GET'])
# @admin_required
def api_get_screen_definitions():
    app_name_filter = request.args.get('app_name')
    if not app_name_filter:
        return jsonify({"error": "Cần cung cấp tham số app_name"}), 400

    definitions = db.get_screen_definitions_for_app(app_name_filter)
    if definitions is None:
        return jsonify({"error": "Lỗi máy chủ khi lấy dữ liệu"}), 500
    return jsonify(definitions)

# API để tạo mới
@admin_bp.route('/api/mapping/screen-definitions', methods=['POST'])
# @admin_required
def api_add_screen_definition():
    if not request.is_json:
        return jsonify({"success": False, "error": "Yêu cầu phải là JSON"}), 400
    data = request.get_json()

    # Validate dữ liệu đầu vào data
    app_name = data.get('app_name')
    logical_name = data.get('logical_screen_name')
    defined_id = data.get('defined_screen_id')
    pies_json = data.get('identifying_elements_json') # Đây nên là list các dict

    if not all([app_name, logical_name, defined_id, isinstance(pies_json, list)]):
        return jsonify({"success": False, "error": "Thiếu các trường bắt buộc hoặc định dạng PIEs không đúng."}), 400

    success, error_msg, new_id = db.add_screen_definition(
        app_name,
        data.get('activity_name'),
        logical_name,
        defined_id,
        pies_json,
        data.get('description')
    )
    if success:
        return jsonify({"success": True, "message": "Đã thêm định nghĩa màn hình thành công.", "definition_id": new_id}), 201
    else:
        return jsonify({"success": False, "error": error_msg or "Thêm định nghĩa thất bại."}), 400 # Hoặc 500 nếu lỗi server

# API để lấy chi tiết (dùng cho form sửa)
@admin_bp.route('/api/mapping/screen-definitions/<int:def_id>', methods=['GET'])
# @admin_required
def api_get_screen_definition_detail(def_id):
    definition = db.get_screen_definition_by_id(def_id)
    if definition:
        # Chuyển đổi datetime thành string nếu cần cho JSON
        return jsonify(definition)
    return jsonify({"error": "Không tìm thấy định nghĩa"}), 404

# API để cập nhật
@admin_bp.route('/api/mapping/screen-definitions/<int:def_id>', methods=['PUT'])
# @admin_required
def api_update_screen_definition(def_id):
    if not request.is_json:
        return jsonify({"success": False, "error": "Yêu cầu phải là JSON"}), 400
    data = request.get_json()

    # Validate tương tự như add
    app_name = data.get('app_name')
    logical_name = data.get('logical_screen_name')
    defined_id = data.get('defined_screen_id')
    pies_json = data.get('identifying_elements_json')

    if not all([app_name, logical_name, defined_id, isinstance(pies_json, list)]):
        return jsonify({"success": False, "error": "Thiếu các trường bắt buộc hoặc định dạng PIEs không đúng."}), 400

    success, error_msg = db.update_screen_definition(
        def_id, app_name, data.get('activity_name'),
        logical_name, defined_id, pies_json, data.get('description')
    )
    if success:
        return jsonify({"success": True, "message": "Cập nhật định nghĩa thành công."})
    else:
        status_code = 404 if "Không tìm thấy" in (error_msg or "") else 400 # hoặc 500
        return jsonify({"success": False, "error": error_msg or "Cập nhật thất bại."}), status_code

# API để xóa
@admin_bp.route('/api/mapping/screen-definitions/<int:def_id>', methods=['DELETE'])
# @admin_required
def api_delete_screen_definition(def_id):
    success, error_msg = db.delete_screen_definition(def_id)
    if success:
        return jsonify({"success": True, "message": "Đã xóa định nghĩa."})
    else:
        status_code = 404 if "Không tìm thấy" in (error_msg or "") else 500
        return jsonify({"success": False, "error": error_msg or "Xóa thất bại."}), status_code

# Trong admin_routes.py, hàm view_node_management
@admin_bp.route('/mapping/node-management')
# @admin_required
def view_node_management():
    title = "Quản lý Vấn đề Node (Screens)"
    logger = current_app.logger # Sử dụng logger của Flask

    # ... (lấy distinct_app_names_for_filter như cũ) ...
    distinct_app_names_for_filter = [] 
    try:
        conn = db.get_db_connection() # Sử dụng module db (database.py)
        if conn:
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                    cur.execute("SELECT DISTINCT app_name FROM screen_definitions WHERE app_name IS NOT NULL ORDER BY app_name;")
                    distinct_app_names_for_filter = [row['app_name'] for row in cur.fetchall()]
            finally:
                conn.close()
    except Exception as e:
        logger.error(f"Lỗi khi lấy distinct app_names cho node management filter: {e}", exc_info=True)


    selected_app_filter = request.args.get('app_name_filter', '').strip()
    filter_status = request.args.get('filter_status', 'unknown') 
    page = request.args.get('page', 1, type=int)
    if page < 1: page = 1
    # PER_PAGE_NODE_ISSUES = 15 # Hoặc lấy từ config
    per_page_nodes = current_app.config.get('PER_PAGE_NODE_ISSUES', 15)


    nodes_for_template = [] # Danh sách node cuối cùng để truyền vào template
    pagination_info_for_template = None

    app_name_query_param = selected_app_filter if selected_app_filter else None

    # Gọi graph_db để lấy dữ liệu thô và total_items
    raw_nodes_page_data, total_items_from_db = graph_db.get_screen_nodes_for_management(
        app_name=app_name_query_param,
        filter_status=filter_status,
        page=page,
        per_page=per_page_nodes
    )

    if raw_nodes_page_data is None: # Lỗi từ graph_db
        flash("Lỗi khi tải dữ liệu Node từ Neo4j.", "error")
    else:
        # **QUAN TRỌNG: Xử lý tạo screenshot_full_url ở đây cho lần render đầu**
        for node_neo4j_data in raw_nodes_page_data:
            node_processed_data = dict(node_neo4j_data) # Tạo bản sao

            raw_screenshot_file = node_processed_data.get('screenshot_path') # CHỈ TÊN FILE
            node_app_name = node_processed_data.get('app_name')

            logger.debug(f"VIEW: Processing node for template: ID={node_processed_data.get('screen_id')}, App={node_app_name}, RawFile={raw_screenshot_file}")

            if raw_screenshot_file and node_app_name:
                # filename_for_url là "APP_NAME/TEN_FILE.png"
                filename_for_url = f"{node_app_name}/{raw_screenshot_file}"
                try:
                    node_processed_data['screenshot_full_url'] = url_for(
                        'serve_app_specific_screenshot', # Tên endpoint
                        filename=raw_screenshot_file,
                        _external=False
                    )
                    logger.debug(f"VIEW: Generated URL for {filename_for_url}: {node_processed_data['screenshot_full_url']}")
                except Exception as url_e:
                    logger.error(f"VIEW: Lỗi tạo URL ảnh cho node {node_processed_data.get('screen_id')} file {filename_for_url}: {url_e}", exc_info=True)
                    node_processed_data['screenshot_full_url'] = None
            else:
                node_processed_data['screenshot_full_url'] = None

            nodes_for_template.append(node_processed_data)

        # Tính toán pagination (giữ nguyên logic cũ của bạn)
        if total_items_from_db is not None and total_items_from_db > 0:
            total_pages_calc = math.ceil(total_items_from_db / per_page_nodes)
            if page > total_pages_calc and total_pages_calc > 0: page = total_pages_calc

            extra_params_for_pagination = {}
            if selected_app_filter: extra_params_for_pagination['app_name_filter'] = selected_app_filter
            if filter_status: extra_params_for_pagination['filter_status'] = filter_status

            pagination_info_for_template = {
                'page': page, 'per_page': per_page_nodes, 
                'total_items': total_items_from_db, 'total_pages': total_pages_calc, 
                'has_prev': page > 1, 'has_next': page < total_pages_calc,
                'prev_num': page - 1 if page > 1 else None,
                'next_num': page + 1 if page < total_pages_calc else None,
                'page_param': 'page', # Tên query param cho phân trang
                'extra_params': extra_params_for_pagination 
            }

    if not nodes_for_template and (selected_app_filter or filter_status != 'unknown'):
        flash(f"Không tìm thấy node nào khớp với bộ lọc.", "info")
    elif not nodes_for_template and not selected_app_filter and filter_status == 'unknown':
         flash(f"Không có node 'unknown' nào trong hệ thống.", "info")


    return render_template('admin_node_management.html', 
                           title=title,
                           nodes=nodes_for_template, # Truyền danh sách đã xử lý
                           distinct_app_names=distinct_app_names_for_filter,
                           selected_app_filter=selected_app_filter,
                           current_filter_status=filter_status,
                           pagination=pagination_info_for_template,
                           # screenshots_subdir không còn cần thiết nếu URL đã đầy đủ
                           # config=current_app.config # Truyền config nếu template JS cần đọc trực tiếp
                          )



@admin_bp.route('/api/mapping/management/nodes/<path:screen_id>/delete', methods=['POST'])
# @admin_required
def api_delete_managed_node(screen_id):
    logger = current_app.logger
    if not request.is_json:
        return jsonify({"success": False, "error": "Yêu cầu phải là JSON"}), 400

    data = request.get_json()
    app_name = data.get('app_name')

    if not app_name:
        logger.warning(f"API delete_managed_node: Thiếu app_name cho screen_id {screen_id}")
        return jsonify({"success": False, "error": "Thiếu tham số app_name."}), 400

    logger.info(f"API: Yêu cầu xóa Node '{screen_id}' của app '{app_name}'")

    # Bước 1: Lấy screenshot_path TRƯỚC KHI xóa node khỏi Neo4j
    node_details_before_delete = graph_db.get_screen_properties(screen_id, app_name) # Dùng hàm đã có
    screenshot_to_delete = None
    if node_details_before_delete:
        screenshot_to_delete = node_details_before_delete.get('screenshot_path')

    # Bước 2: Xóa Node khỏi Neo4j
    success_neo4j, error_msg_neo4j = graph_db.delete_screen_node_logic(screen_id, app_name)

    if success_neo4j:
        # Bước 3: Xóa file screenshot nếu có và xóa node Neo4j thành công
        if screenshot_to_delete: # screenshot_to_delete bây giờ chỉ là filename
            from app.phone.utils import delete_screenshot_file_on_server 

        # base_screenshot_path_for_delete sẽ là current_app.config['SCREENSHOT_STORAGE_PATH']
        # SCREENSHOT_STORAGE_PATH này trỏ đến app/static/screenshots
            base_screenshot_path_for_delete = current_app.config.get('SCREENSHOT_STORAGE_PATH')

            if base_screenshot_path_for_delete:
                # Hàm delete_screenshot_file_on_server giờ chỉ cần base_path và filename
                deleted_file, error_file = delete_screenshot_file_on_server(
                    base_static_screenshots_path=base_screenshot_path_for_delete, 
                    filename=screenshot_to_delete,  # Không cần app_name ở đây nữa
                    logger=current_app.logger # Truyền logger vào
                )
                if deleted_file:
                    logger.info(f"Đã xóa file screenshot: {screenshot_to_delete}")
                else:
                    logger.warning(f"Không thể xóa file screenshot {screenshot_to_delete}: {error_file}")
            else:
                logger.error("SCREENSHOT_STORAGE_PATH không được cấu hình, không thể xóa file ảnh.")

                return jsonify({"success": True, "message": f"Đã xóa Node {screen_id} và các dữ liệu liên quan."})
        else:
            logger.error(f"API delete_managed_node: Lỗi từ graph_db.delete_screen_node_logic - {error_msg_neo4j}")
        # Xác định status code dựa trên lỗi (ví dụ: 404 nếu không tìm thấy)
        status_code = 404 if "không tìm thấy" in (error_msg_neo4j or "").lower() else 500
        return jsonify({"success": False, "error": error_msg_neo4j or "Xóa Node thất bại."}), status_code


@admin_bp.route('/api/mapping/management/nodes/<path:screen_id>/classify', methods=['POST'], endpoint='api_classify_managed_node')
# @admin_required
def api_classify_managed_node(screen_id):
    logger = current_app.logger
    if not request.is_json:
        return jsonify({"success": False, "error": "Yêu cầu phải là JSON"}), 400

    data = request.get_json()
    app_name = data.get('app_name')
    node_classification = data.get('node_classification') 

    if not app_name: # app_name rất quan trọng để query đúng Node
        logger.warning(f"API classify_node: Thiếu app_name cho screen_id {screen_id}")
        return jsonify({"success": False, "error": "Thiếu tham số app_name."}), 400

    # node_classification có thể là chuỗi rỗng (để xóa phân loại) hoặc None
    classification_to_set = node_classification if node_classification and node_classification.strip() else None

    logger.info(f"API: Yêu cầu phân loại Node '{screen_id}' của app '{app_name}' thành '{classification_to_set}'")

    # Gọi hàm graph_db để cập nhật
    success = graph_db.update_node_classification_in_neo4j(screen_id, app_name, classification_to_set)

    if success:
        return jsonify({"success": True, "message": f"Đã cập nhật phân loại cho Node {screen_id}."})
    else:
        logger.error(f"API classify_node: Lỗi từ graph_db.update_node_classification_in_neo4j cho {app_name}/{screen_id}")
        return jsonify({"success": False, "error": "Cập nhật phân loại Node thất bại trong Neo4j."}), 500

@admin_bp.route('/api/mapping/management/nodes', methods=['GET'], endpoint='api_get_managed_nodes')
def api_get_managed_nodes():
    logger = current_app.logger
    try:
        app_name_filter_from_req = request.args.get('app_name_filter')
        filter_status_from_req = request.args.get('filter_status', 'unknown')
        page = request.args.get('page', 1, type=int)
        if page < 1: page = 1
        per_page_val = 15 # Hoặc current_app.config.get('PER_PAGE_NODE_ISSUES', 15)

        app_name_for_db_query = app_name_filter_from_req if app_name_filter_from_req and app_name_filter_from_req.strip() else None

        logger.debug(f"API get_managed_nodes: app_filter='{app_name_for_db_query}', status_filter='{filter_status_from_req}', page={page}")

        nodes_page_data, total_items = graph_db.get_screen_nodes_for_management(
            app_name=app_name_for_db_query,
            filter_status=filter_status_from_req,
            page=page,
            per_page=per_page_val
        )

        if nodes_page_data is None:
            logger.error("API get_managed_nodes: graph_db.get_screen_nodes_for_management trả về None.")
            return jsonify({"nodes": [], "pagination": {}, "error": "Lỗi tải dữ liệu Node."}), 500

        final_nodes_list_for_response = []
        if nodes_page_data:
            for node_data_from_neo4j in nodes_page_data:
                node_render_data = dict(node_data_from_neo4j)
                raw_screenshot_filename = node_render_data.get('screenshot_path') # CHỈ LÀ TÊN FILE
                # node_app_name = node_render_data.get('app_name') # Không dùng để tạo URL ảnh nữa

                logger.debug(f"Node processing for API: ID={node_render_data.get('screen_id')}, App={node_render_data.get('app_name')}, RawScreenshotFile={raw_screenshot_filename}")

                if raw_screenshot_filename: # Chỉ cần tên file
                    try:
                        # **SỬA Ở ĐÂY: filename TRUYỀN VÀO url_for LÀ CHỈ TÊN FILE**
                        node_render_data['screenshot_full_url'] = url_for(
                            'serve_app_specific_screenshot', 
                            filename=raw_screenshot_filename, # TRUYỀN TRỰC TIẾP TÊN FILE TỪ NEO4J
                            _external=False
                        )
                        logger.info(f"Generated screenshot_full_url for '{raw_screenshot_filename}': {node_render_data['screenshot_full_url']}")
                    except Exception as url_exc:
                        logger.error(f"Lỗi tạo URL ảnh cho file {raw_screenshot_filename}: {url_exc}", exc_info=True)
                        node_render_data['screenshot_full_url'] = None
                else:
                    node_render_data['screenshot_full_url'] = None
                
                final_nodes_list_for_response.append(node_render_data)
        
        # ... (logic pagination giữ nguyên) ...
        total_pages_val = 0
        current_total_items = total_items if total_items is not None else 0
        if current_total_items > 0 and per_page_val > 0:
            total_pages_val = math.ceil(current_total_items / per_page_val)

        pagination_details = {
            "page": page, "per_page": per_page_val, "total_items": current_total_items,
            "total_pages": total_pages_val, 'has_prev': page > 1, 'has_next': page < total_pages_val,
            'prev_num': page - 1 if page > 1 else None,
            'next_num': page + 1 if page < total_pages_val else None
        }
        
        return jsonify({
            "nodes": final_nodes_list_for_response,
            "pagination": pagination_details
        })

    except Exception as e:
        logger.error(f"Lỗi không mong muốn trong api_get_managed_nodes: {e}", exc_info=True)
        return jsonify({"nodes": [], "pagination": {}, "error": "Lỗi server."}), 500


@admin_bp.route('/api/mapping/management/nodes/define-from-unknown', methods=['POST'], endpoint='api_define_node_from_unknown')
# @admin_required
def api_define_node_from_unknown():
    logger = current_app.logger
    if not request.is_json:
        return jsonify({"success": False, "error": "Yêu cầu phải là JSON"}), 400

    data = request.get_json()
    logger.info(f"API define_from_unknown: Received data: {data}")

    unknown_screen_id = data.get('unknown_screen_id')
    app_name = data.get('app_name')
    # activity_name có thể là null, nhưng app_name thì không nên
    activity_name = data.get('activity_name') # Có thể là None nếu client không gửi hoặc PIE áp dụng chung
    
    new_logical_name = data.get('new_logical_screen_name')
    new_defined_id = data.get('new_defined_screen_id')
    new_pies_json_list = data.get('new_identifying_elements_json') # Đây là list các dict từ JS
    new_description = data.get('new_description')

    # --- Validate dữ liệu đầu vào ---
    if not all([unknown_screen_id, app_name, new_logical_name, new_defined_id, 
                isinstance(new_pies_json_list, list), len(new_pies_json_list) > 0]):
        logger.warning(f"API define_from_unknown: Thiếu tham số bắt buộc hoặc PIEs không hợp lệ. UnknownSID: {unknown_screen_id}, App: {app_name}, NewLogical: {new_logical_name}, NewDefinedID: {new_defined_id}, PIEs: {new_pies_json_list}")
        return jsonify({"success": False, "error": "Thiếu tham số bắt buộc hoặc PIEs rỗng/không hợp lệ."}), 400

    # --- Bước 1: Thêm định nghĩa PIE mới vào PostgreSQL ---
    success_db, error_msg_db, new_pie_definition_id = db.add_screen_definition(
        app_name=app_name,
        activity_name=activity_name, # Truyền activity_name (có thể None)
        logical_screen_name=new_logical_name,
        defined_screen_id=new_defined_id,
        identifying_elements_json=new_pies_json_list, # Truyền list Python
        description=new_description
    )

    if not success_db:
        logger.error(f"API define_from_unknown: Không thể thêm PIE definition vào DB cho '{new_logical_name}': {error_msg_db}")
        return jsonify({"success": False, "error": f"Lỗi lưu định nghĩa PIE: {error_msg_db}"}), 500 # Lỗi server

    logger.info(f"API define_from_unknown: Đã thêm PIE definition ID {new_pie_definition_id} cho defined_screen_id '{new_defined_id}'")
    existing_pie_def = db.get_screen_definition_by_defined_id(new_defined_id, app_name)
    if existing_pie_def:
        logger.warning(f"API define_from_unknown: new_defined_screen_id '{new_defined_id}' đã tồn tại cho app '{app_name}'.")
        return jsonify({"success": False, "error": f"Defined Screen ID '{new_defined_id}' đã được sử dụng cho app này. Vui lòng chọn ID khác."}), 400
    # --- Bước 2: Cập nhật Node "unknown" trong Neo4j thành Node "defined" ---
    # Bạn cần một hàm trong graph_db.py để làm việc này
    # Ví dụ: update_node_id_and_status(old_screen_id, new_screen_id, app_name, new_status)
    # Hàm này cũng cần xử lý việc cập nhật các transitions liên quan.
    
    # Tạm thời, chúng ta chỉ cập nhật screen_id và status của chính node đó.
    # Việc cập nhật transitions là phức tạp và cần làm cẩn thận.
    
    # Tạo hàm mới trong graph_db.py:
    # def rename_screen_node_and_set_status(old_screen_id, new_screen_id, app_name, new_status='defined'):
    #     // Logic:
    #     // 1. MATCH (s:Screen {screen_id: old_screen_id, app_name: app_name})
    #     // 2. REMOVE s.screen_id // Nếu screen_id là một thuộc tính có thể xóa và đặt lại
    #     // 3. SET s.screen_id = new_screen_id, s.status = new_status, s.updated_at = datetime()
    #     // 4. XỬ LÝ CẠNH: Đây là phần khó.
    #     //    - Tìm tất cả cạnh vào/ra của node cũ.
    #     //    - Tạo lại các cạnh đó với node mới (đã đổi ID).
    #     //    - Xóa node cũ nếu bạn tạo node mới hoàn toàn thay vì chỉ đổi ID.
    #     //    Cách đơn giản hơn có thể là chỉ cập nhật `status` và thêm một thuộc tính `defined_as: new_defined_screen_id`
    #     //    và để logic query sau này xử lý việc map từ unknown_id sang defined_id.
    #     //    Tuy nhiên, lý tưởng là đổi screen_id trực tiếp.

    # Giả sử bạn có hàm graph_db.convert_unknown_node_to_defined:
    # success_neo4j, error_msg_neo4j = graph_db.convert_unknown_node_to_defined(
    #     unknown_screen_id,
    #     new_defined_id, # screen_id mới sẽ là cái này
    #     app_name,
    #     # Có thể truyền thêm các thuộc tính khác của PIE definition để cập nhật vào node Neo4j nếu muốn
    # )

    # Vì việc cập nhật Neo4j (đặc biệt là transitions) phức tạp,
    # TẠM THỜI chúng ta chỉ cập nhật status của node unknown và ghi nhận defined_id.
    # Admin sẽ cần cơ chế merge/clean up sau.
    # Hoặc, đơn giản là Node Unknown này sẽ không được dùng nữa, và các lần khám phá sau sẽ khớp với PIE mới.

    # Cách tiếp cận đơn giản hơn: Chỉ cập nhật status của node unknown và có thể thêm 1 property
    # cho biết nó đã được định nghĩa thành defined_id nào.
    updated_node_props = {
        "status": "defined_from_unknown", # Một status mới để biết nó được định nghĩa từ unknown
        "defined_as_screen_id": new_defined_id, # Lưu lại defined_id nó được gán
        "node_classification": data.get("new_node_classification") # Nếu admin có gán luôn
    }
    success_neo4j_update, error_msg_neo4j_update = graph_db.update_screen_node_properties_by_id(
        screen_id_to_update=unknown_screen_id,
        app_name=app_name,
        properties_to_set=updated_node_props
    )
    # Bạn cần hàm graph_db.update_screen_node_properties_by_id(screen_id, app_name, properties_to_set)
    if success_db:
        logger.info(f"API define_from_unknown: Đã thêm PIE definition ID {new_pie_definition_id} cho defined_screen_id '{new_defined_id}'")
    
        # Bây giờ cập nhật Node trong Neo4j
        # Truyền cả new_logical_name để có thể lưu vào Neo4j nếu muốn
        success_neo4j, error_msg_neo4j = graph_db.convert_unknown_to_defined_node(
            unknown_screen_id=unknown_screen_id,
            app_name=app_name,
            new_defined_screen_id=new_defined_id, # Dùng new_defined_id đã được validate
            new_status='defined',
            # Tùy chọn: truyền thêm new_logical_name để lưu vào Neo4j node
            # new_logical_name_for_neo4j=new_logical_name 
        )
    
    if not success_neo4j_update:
        logger.error(f"API define_from_unknown: Không thể cập nhật Node Neo4j '{unknown_screen_id}' sau khi tạo PIE def: {error_msg_neo4j_update}")
        # Có thể cân nhắc xóa PIE definition vừa tạo nếu không cập nhật được Neo4j, hoặc để admin xử lý thủ công
        return jsonify({"success": False, "error": f"Lỗi cập nhật Node Neo4j: {error_msg_neo4j_update}. PIE definition đã được tạo (ID: {new_pie_definition_id})."}), 500

    logger.info(f"API define_from_unknown: Node Neo4j '{unknown_screen_id}' đã được cập nhật status/defined_as '{new_defined_id}'.")
    return jsonify({
        "success": True, 
        "message": f"Đã tạo định nghĩa PIE '{new_logical_name}' ({new_defined_id}) và cập nhật Node Unknown '{unknown_screen_id}'.",
        "new_pie_definition_id": new_pie_definition_id,
        "updated_neo4j_screen_id": unknown_screen_id, # Vẫn là unknown_id, nhưng status và defined_as đã đổi
        "now_defined_as": new_defined_id
    })


@admin_bp.route('/api/mapping/management/nodes/merge-selected', methods=['POST'], endpoint='api_merge_selected_nodes')
# @admin_required
def api_merge_selected_nodes():
    logger = current_app.logger
    logger.info("API: Placeholder for /api/mapping/management/nodes/merge-selected called.")
    # Logic merge thực sự sẽ được implement ở đây sau.
    # Tạm thời trả về lỗi hoặc một thông báo chưa implement.
    return jsonify({
        "success": False, 
        "error": "Chức năng Merge Selected Nodes chưa được triển khai đầy đủ ở backend."
    }), 501 # 501 Not Implemented

@admin_bp.route('/api/mapping/management/nodes/merge-unknown-to-defined', methods=['POST'], endpoint='api_merge_unknown_to_defined')
# @admin_required
def api_merge_unknown_to_defined_route(): # Đổi tên hàm để tránh trùng lặp nếu có
    logger = current_app.logger
    if not request.is_json:
        return jsonify({"success": False, "error": "Yêu cầu phải là JSON"}), 400

    data = request.get_json()
    logger.info(f"API merge_unknown_to_defined: Received data: {data}")

    unknown_screen_id = data.get('unknown_screen_id')
    target_defined_screen_id = data.get('target_defined_screen_id')
    app_name = data.get('app_name')

    if not all([unknown_screen_id, target_defined_screen_id, app_name]):
        return jsonify({"success": False, "error": "Thiếu tham số bắt buộc."}), 400

    if unknown_screen_id == target_defined_screen_id:
        return jsonify({"success": False, "error": "Node nguồn và Node đích không thể giống nhau."}), 400

    # 1. Kiểm tra target_defined_screen_id có hợp lệ không (tức là có trong screen_definitions)
    pie_def = db.get_screen_definition_by_defined_id(target_defined_screen_id, app_name)
    if not pie_def:
        msg = f"Target Defined Screen ID '{target_defined_screen_id}' không phải là một định nghĩa PIE hợp lệ cho app '{app_name}'."
        logger.warning(f"API merge_unknown_to_defined: {msg}")
        return jsonify({"success": False, "error": msg}), 400

    # 2. Gọi hàm GraphDB để thực hiện merge
    # Hàm này cần được implement cẩn thận trong graph_db.py
    success_neo4j, error_msg_neo4j = graph_db.merge_neo4j_screen_nodes_and_delete_source(
        source_screen_id=unknown_screen_id,
        target_screen_id=target_defined_screen_id,
        app_name=app_name
    )

    if success_neo4j:
        # (Tùy chọn) Xóa file ảnh của node unknown nếu nó khác với ảnh của node target
        unknown_node_details = graph_db.get_screen_properties(unknown_screen_id, app_name, fetch_elements=False) # Lấy nhanh props
        if unknown_node_details and unknown_node_details.get('screenshot_path'):
            target_node_details = graph_db.get_screen_properties(target_defined_screen_id, app_name, fetch_elements=False)
            if not target_node_details or unknown_node_details.get('screenshot_path') != target_node_details.get('screenshot_path'):
                from app.phone.utils import delete_screenshot_file_on_server
                storage_path = current_app.config.get('SCREENSHOT_STORAGE_PATH')
                if storage_path:
                    delete_screenshot_file_on_server(storage_path, unknown_node_details.get('screenshot_path'), logger)


        msg = f"Node Unknown '{unknown_screen_id}' đã được merge thành công vào '{target_defined_screen_id}'."
        logger.info(f"API merge_unknown_to_defined: {msg}")
        return jsonify({"success": True, "message": msg})
    else:
        logger.error(f"API merge_unknown_to_defined: Lỗi khi merge node Neo4j: {error_msg_neo4j}")
        return jsonify({"success": False, "error": error_msg_neo4j or "Lỗi merge Node trong Neo4j."}), 500

@admin_bp.route('/api/pie_definition_conditions', methods=['GET'])
# @admin_required # Nếu bạn có và muốn sử dụng decorator xác thực cho API
def api_get_pie_definition_conditions():
    defined_screen_id = request.args.get('defined_screen_id')
    app_name = request.args.get('app_name')

    current_app.logger.debug(f"API Request: /api/pie_definition_conditions with app_name='{app_name}', defined_screen_id='{defined_screen_id}'")

    if not defined_screen_id or not app_name:
        return jsonify({"success": False, "message": "Thiếu tham số 'defined_screen_id' hoặc 'app_name'."}), 400

    try:
        # Gọi hàm từ database.py để lấy conditions
        conditions = get_pie_conditions_from_db(app_name, defined_screen_id)

        if conditions is None:
            # Trường hợp PIE definition không được tìm thấy
            current_app.logger.warning(f"PIE Definition not found for app '{app_name}' and screen_id '{defined_screen_id}'.")
            return jsonify({
                "success": False,
                "message": f"Không tìm thấy Định nghĩa PIE cho ứng dụng '{app_name}' và ID màn hình '{defined_screen_id}'."
            }), 404
        
        # Nếu PIE definition được tìm thấy, conditions sẽ là một list (có thể rỗng)
        current_app.logger.debug(f"Successfully fetched {len(conditions)} conditions for PIE {app_name}/{defined_screen_id}.")
        return jsonify({"success": True, "conditions": conditions}), 200

    except Exception as e:
        current_app.logger.error(f"Lỗi trong api_get_pie_definition_conditions: {e}", exc_info=True)
        return jsonify({"success": False, "message": "Đã xảy ra lỗi máy chủ nội bộ."}), 500

@admin_bp.route('/api/pie_definition/<string:defined_pie_id>/update_conditions', methods=['POST'])
# @admin_required
def api_update_pie_definition_conditions(defined_pie_id):
    current_app.logger.debug(f"API Request: POST /api/pie_definition/{defined_pie_id}/update_conditions")
    
    if not request.is_json:
        return jsonify({"success": False, "message": "Yêu cầu phải là JSON."}), 400

    data = request.get_json()
    app_name = data.get('app_name')
    new_conditions_list = data.get('new_conditions_list')

    if not app_name:
        return jsonify({"success": False, "message": "Thiếu tham số 'app_name' trong body."}), 400
    
    if not isinstance(new_conditions_list, list):
        # new_conditions_list có thể là list rỗng [] nếu muốn xóa hết conditions
        return jsonify({"success": False, "message": "'new_conditions_list' phải là một danh sách (array)."}), 400

    # Validate cấu trúc của từng condition trong list (tùy chọn, nhưng nên có)
    for condition_item in new_conditions_list:
        if not isinstance(condition_item, dict) or \
           'attribute' not in condition_item or \
           'comparison' not in condition_item or \
           'value' not in condition_item: # 'value' có thể là None, nhưng key nên có
            return jsonify({"success": False, "message": "Mỗi condition trong danh sách phải có đủ 'attribute', 'comparison', và 'value'."}), 400

    try:
        success, error_msg = update_pie_conditions_in_db(app_name, defined_pie_id, new_conditions_list)

        if success:
            current_app.logger.info(f"Conditions updated for PIE: app='{app_name}', defined_id='{defined_pie_id}'.")
            return jsonify({"success": True, "message": "Đã cập nhật các điều kiện PIE thành công."}), 200
        else:
            current_app.logger.warning(f"Failed to update conditions for PIE {app_name}/{defined_pie_id}: {error_msg}")
            # Phân biệt lỗi do không tìm thấy PIE (404) hay lỗi khác (500)
            if "Không tìm thấy Định nghĩa PIE" in (error_msg or ""):
                 return jsonify({"success": False, "message": error_msg}), 404
            return jsonify({"success": False, "message": error_msg or "Lỗi cập nhật điều kiện PIE."}), 500

    except Exception as e:
        current_app.logger.error(f"Lỗi trong api_update_pie_definition_conditions cho PIE {app_name}/{defined_pie_id}: {e}", exc_info=True)
        return jsonify({"success": False, "message": "Đã xảy ra lỗi máy chủ nội bộ."}), 500

@admin_bp.route('/api/mapping/management/nodes/define_new_pie_with_conditions', methods=['POST'])
# @admin_required
def api_define_new_pie_and_update_node():
    current_app.logger.debug(f"API Request: POST /api/mapping/management/nodes/define_new_pie_with_conditions")
    if not request.is_json:
        return jsonify({"success": False, "message": "Yêu cầu phải là JSON."}), 400

    data = request.get_json()
    current_app.logger.info(f"API define_new_pie_with_conditions: Dữ liệu nhận được: {data}")

    unknown_node_neo4j_id = data.get('unknown_node_neo4j_id') # ID này dùng để tìm node trong Neo4j
    current_unknown_screen_id = data.get('current_unknown_screen_id') # screen_id hiện tại của node unknown
    app_name = data.get('app_name')
    activity_name = data.get('activity_name') # Có thể None
    
    new_logical_name = data.get('logical_name') # Tên logic mới cho PIE
    new_defined_screen_id = data.get('new_defined_screen_id') # ID định danh mới cho PIE
    selected_conditions = data.get('selected_conditions') # Danh sách conditions từ frontend
    description = data.get('description') # Mô tả cho PIE (tùy chọn)

    # --- Validate dữ liệu đầu vào ---
    required_fields = {
        "unknown_node_neo4j_id": unknown_node_neo4j_id, # Cần để xác định node Neo4j
        "current_unknown_screen_id": current_unknown_screen_id, # Để cập nhật node Neo4j
        "app_name": app_name,
        "logical_name": new_logical_name,
        "new_defined_screen_id": new_defined_screen_id,
        "selected_conditions": selected_conditions
    }
    missing_fields = [key for key, value in required_fields.items() if value is None or (isinstance(value, (str, list)) and not value)] # check cả list rỗng cho conditions
    
    if missing_fields:
        msg = f"Thiếu các tham số bắt buộc: {', '.join(missing_fields)}."
        current_app.logger.warning(f"API define_new_pie_with_conditions: {msg} Data: {data}")
        return jsonify({"success": False, "message": msg}), 400

    if not isinstance(selected_conditions, list) or not selected_conditions: # Phải là list và không rỗng
        msg = "'selected_conditions' phải là một danh sách các điều kiện và không được rỗng."
        current_app.logger.warning(f"API define_new_pie_with_conditions: {msg} Data: {data}")
        return jsonify({"success": False, "message": msg}), 400
    
    # Validate từng condition (tùy chọn, nhưng nên có)
    for cond in selected_conditions:
        if not isinstance(cond, dict) or not all(k in cond for k in ['attribute', 'comparison', 'value']):
            msg = "Mỗi condition trong 'selected_conditions' phải là một dictionary chứa 'attribute', 'comparison', 'value'."
            current_app.logger.warning(f"API define_new_pie_with_conditions: {msg} Invalid condition: {cond}")
            return jsonify({"success": False, "message": msg}), 400

    # --- Bước 1: Tạo PIE Definition mới trong PostgreSQL ---
    try:
        success_db, error_msg_db, new_pie_db_id = create_new_pie_definition_from_node(
            app_name=app_name,
            activity_name=activity_name,
            logical_name=new_logical_name,
            new_defined_screen_id=new_defined_screen_id,
            conditions=selected_conditions,
            description=description
        )

        if not success_db:
            current_app.logger.error(f"Không thể tạo PIE definition trong DB cho '{new_logical_name}': {error_msg_db}")
            # Nếu lỗi là do ID đã tồn tại, trả về 409 (Conflict) hoặc 400
            if "đã tồn tại" in (error_msg_db or "").lower():
                 return jsonify({"success": False, "message": error_msg_db}), 409
            return jsonify({"success": False, "message": f"Lỗi lưu định nghĩa PIE: {error_msg_db}"}), 500

        current_app.logger.info(f"Đã tạo PIE definition ID (DB): {new_pie_db_id} cho defined_screen_id '{new_defined_screen_id}'")

        # --- Bước 2: Cập nhật Node "unknown" trong Neo4j ---
        # Sử dụng current_unknown_screen_id để tìm node và đổi nó thành new_defined_screen_id
        success_neo4j, error_msg_neo4j = convert_unknown_to_defined_node_wrapper(
            unknown_screen_id=current_unknown_screen_id, # ID cũ của node trong Neo4j
            app_name=app_name,
            new_defined_screen_id=new_defined_screen_id, # ID mới mà node sẽ mang
            new_status='defined',
            new_logical_name=new_logical_name # Cập nhật cả logical_name cho node Neo4j
        )

        if not success_neo4j:
            current_app.logger.error(f"Không thể cập nhật Node Neo4j '{current_unknown_screen_id}' sau khi tạo PIE def '{new_defined_screen_id}': {error_msg_neo4j}")
            # QUAN TRỌNG: Cân nhắc việc rollback/xóa PIE definition vừa tạo trong PostgreSQL nếu Neo4j thất bại.
            # Hoặc, thông báo cho người dùng rằng PIE đã được tạo nhưng Node chưa được cập nhật, cần xử lý thủ công.
            # Tạm thời, chúng ta sẽ báo lỗi và PIE vẫn tồn tại.
            return jsonify({
                "success": False, 
                "message": f"Lỗi cập nhật Node Neo4j: {error_msg_neo4j}. PIE definition đã được tạo (ID DB: {new_pie_db_id}). Vui lòng kiểm tra thủ công."
            }), 500

        current_app.logger.info(f"Node Neo4j '{current_unknown_screen_id}' đã được cập nhật thành '{new_defined_screen_id}'.")
        
        return jsonify({
            "success": True, 
            "message": f"Đã tạo định nghĩa PIE '{new_logical_name}' ({new_defined_screen_id}) và cập nhật Node '{current_unknown_screen_id}' thành công.",
            "new_pie_db_id": new_pie_db_id,
            "defined_screen_id": new_defined_screen_id
        }), 201 # 201 Created

    except Exception as e:
        current_app.logger.error(f"Lỗi không mong muốn trong api_define_new_pie_and_update_node: {e}", exc_info=True)
        return jsonify({"success": False, "message": "Đã xảy ra lỗi máy chủ nội bộ."}), 500


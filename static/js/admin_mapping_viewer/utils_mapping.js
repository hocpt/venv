// static/js/admin_mapping_viewer/utils_mapping.js
import { APP_CONFIG } from './config_mapping.js';

/**
 * Gửi yêu cầu API đến server.
 * @param {string} url - URL của API.
 * @param {string} method - Phương thức HTTP (GET, POST, PUT, DELETE).
 * @param {object|null} body - Dữ liệu gửi đi (cho POST, PUT).
 * @param {object} headers - Các header tùy chỉnh.
 * @returns {Promise<object>} - Promise chứa dữ liệu JSON trả về từ server.
 * @throws {Error} - Nếu có lỗi mạng hoặc server trả về lỗi.
 */
export async function sendApiRequest(url, method = 'GET', body = null, headers = {}) {
    const defaultHeaders = {
        'Content-Type': 'application/json',
    };
    if (APP_CONFIG.CSRF_TOKEN) { // Thêm CSRF token nếu có
        defaultHeaders['X-CSRFToken'] = APP_CONFIG.CSRF_TOKEN;
    }

    const config = {
        method: method.toUpperCase(),
        headers: { ...defaultHeaders, ...headers }
    };

    if (body && (method.toUpperCase() === 'POST' || method.toUpperCase() === 'PUT' || method.toUpperCase() === 'DELETE')) {
        config.body = JSON.stringify(body);
    }

    console.log(`UTILS_MAPPING: Sending API request. URL: ${url}, Method: ${config.method}, Body:`, body);

    try {
        const response = await fetch(url, config);
        const responseData = await response.json(); // Luôn cố gắng parse JSON

        if (!response.ok) {
            // responseData có thể chứa thông tin lỗi từ server
            const errorMessage = responseData.message || responseData.error || `Lỗi HTTP ${response.status}: ${response.statusText}`;
            console.error(`UTILS_MAPPING: API request error to ${url}. Status: ${response.status}. Message: ${errorMessage}. ResponseData:`, responseData);
            const error = new Error(errorMessage);
            error.response = response; // Gắn response vào lỗi để có thể truy cập status code
            error.data = responseData; // Gắn data lỗi vào
            throw error;
        }
        console.log(`UTILS_MAPPING: API request successful to ${url}. ResponseData:`, responseData);
        return responseData;
    } catch (error) {
        // Bắt cả lỗi parse JSON nếu response không phải JSON (ví dụ server trả về HTML lỗi)
        if (error instanceof SyntaxError) {
            console.error(`UTILS_MAPPING: API request to ${url} returned non-JSON response. Error:`, error);
            throw new Error(`Lỗi phân tích phản hồi từ server (không phải JSON hợp lệ). URL: ${url}`);
        }
        // Ném lại lỗi đã được tạo ở trên hoặc lỗi mạng
        console.error(`UTILS_MAPPING: API request failed for ${url}. Error:`, error.message, error.data || '');
        throw error;
    }
}

/**
 * Escape HTML để tránh XSS.
 * @param {string} unsafe - Chuỗi cần escape.
 * @returns {string} - Chuỗi đã được escape.
 */
export function escapeHtml(unsafe) {
    if (unsafe === null || unsafe === undefined) return '';
    const str = typeof unsafe !== 'string' ? String(unsafe) : unsafe;
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

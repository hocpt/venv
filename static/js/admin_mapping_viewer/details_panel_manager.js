// static/js/admin_mapping_viewer/details_panel_manager.js
import { APP_CONFIG } from './config_mapping.js'; // Giả sử escapeHtml ở utils
import { openEditTransitionModal } from './modal_edit_transition.js'; // Import hàm mở modal
import { escapeHtml, sendApiRequest } from './utils_mapping.js';
// DOM Elements của Panel Chi Tiết
let panelTextContentDiv, panelActionsAreaDiv, panelScreenshotAreaDiv,
    panelScreenshotContainer, panelScreenshotImage;

// Hàm lấy các DOM element một lần
function getAndCheckDetailsPanelDOMElements() {
    const IDS = APP_CONFIG.DOM_ELEMENT_IDS;
    let allFound = true;

    panelTextContentDiv = document.getElementById(IDS.detailsPanelTextContent);
    if (!panelTextContentDiv) { console.warn(`DETAILS_PANEL: Element '${IDS.detailsPanelTextContent}' not found.`); allFound = false; }

    panelActionsAreaDiv = document.getElementById(IDS.detailsPanelActionsArea);
    if (!panelActionsAreaDiv) { console.warn(`DETAILS_PANEL: Element '${IDS.detailsPanelActionsArea}' not found.`); allFound = false; }

    panelScreenshotAreaDiv = document.getElementById(IDS.detailsPanelScreenshotArea);
    if (!panelScreenshotAreaDiv) { console.warn(`DETAILS_PANEL: Element '${IDS.detailsPanelScreenshotArea}' not found.`); allFound = false; }

    panelScreenshotContainer = document.getElementById(IDS.detailsPanelScreenshotContainer);
    if (!panelScreenshotContainer) { console.warn(`DETAILS_PANEL: Element '${IDS.detailsPanelScreenshotContainer}' not found.`); allFound = false; }

    panelScreenshotImage = document.getElementById(IDS.detailsPanelScreenshotImage);
    if (!panelScreenshotImage) { console.warn(`DETAILS_PANEL: Element '${IDS.detailsPanelScreenshotImage}' not found.`); allFound = false; }

    return allFound;
}

/**
 * Khởi tạo Details Panel Manager.
 */
export function initDetailsPanelManager() {
    console.log("DETAILS_PANEL: initDetailsPanelManager called.");
    getAndCheckDetailsPanelDOMElements();
    if (!panelTextContentDiv || !panelActionsAreaDiv || !panelScreenshotAreaDiv || !panelScreenshotContainer || !panelScreenshotImage) {
        console.error("DETAILS_PANEL: Một hoặc nhiều DOM elements của panel chi tiết không tìm thấy. Kiểm tra ID trong HTML và config_mapping.js DOM_ELEMENT_IDS.");
    } else {
        console.log("DETAILS_PANEL: All required DOM elements for details panel found.");
    }
    console.log("DETAILS_PANEL: Initialized.");
}

/**
 * Hiển thị thông báo mặc định khi không có gì được chọn.
 */
export function showDefaultDetailsMessage() {
    if (!panelTextContentDiv && !getAndCheckDetailsPanelDOMElements()) return; // Thử lấy lại nếu chưa có

    if (panelTextContentDiv) panelTextContentDiv.innerHTML = '<p class="text-muted fst-italic">Nhấp vào một node (màn hình) hoặc cạnh (chuyển tiếp) để xem chi tiết.</p>';
    if (panelActionsAreaDiv) panelActionsAreaDiv.innerHTML = '';
    if (panelScreenshotAreaDiv) panelScreenshotAreaDiv.style.display = 'none';
}


export function displayNodeDetails(nodeData) {
    if (!panelTextContentDiv && !getAndCheckDetailsPanelDOMElements()) {
        console.error("DETAILS_PANEL: displayNodeDetails - Không thể hiển thị chi tiết Node, thiếu DOM elements chính.");
        return;
    }
    if (!panelTextContentDiv || !panelActionsAreaDiv || !panelScreenshotAreaDiv || !panelScreenshotImage || !panelScreenshotContainer) {
        console.error("DETAILS_PANEL: displayNodeDetails - Vẫn thiếu một số DOM elements cần thiết.");
        return;
    } else {
        panelActionsAreaDiv.innerHTML = ''; // Xóa tất cả các nút hành động cũ trước khi thêm mới
        console.log("DETAILS_PANEL: panelActionsAreaDiv được xóa nội dung."); // Log để kiểm tra
    }

    console.log("DETAILS_PANEL: Displaying Node Details for nodeData:", JSON.parse(JSON.stringify(nodeData)));

    panelActionsAreaDiv.innerHTML = '';


    panelScreenshotAreaDiv.style.display = 'none';
    panelScreenshotImage.src = '';
    panelScreenshotImage.style.display = 'none';
    panelScreenshotContainer.innerHTML = '';
    const createTransitionButton = document.createElement('button');
    createTransitionButton.type = 'button';
    createTransitionButton.className = 'btn btn-sm btn-success mt-2 ms-2'; // ms-2 để cách nút Xem Elements
    createTransitionButton.innerHTML = '<i class="fas fa-plus-circle me-1"></i> Tạo Transition Mới';

    const deleteNodeButton = document.createElement('button');
    deleteNodeButton.type = 'button';
    deleteNodeButton.className = 'btn btn-sm btn-danger mt-2 ms-2'; // Hoặc màu khác
    deleteNodeButton.innerHTML = '<i class="fas fa-trash-alt me-1"></i> Xóa Node Này';

    deleteNodeButton.addEventListener('click', async function () {
        if (confirm(`BẠN CÓ CHẮC CHẮN MUỐN XÓA NODE "${nodeData.id}" (App: ${nodeData.app_name}) KHÔNG? \nHành động này sẽ xóa node, tất cả elements và các transitions liên quan đến nó. KHÔNG THỂ HOÀN TÁC!`)) {
            deleteNodeButton.disabled = true;
            deleteNodeButton.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Đang xóa node...';
            try {
                // API URL để xóa node
                // Cần app_name để đảm bảo xóa đúng node nếu screen_id không phải là duy nhất toàn cục
                const apiUrl = `/admin/api/mapping/management/nodes/${encodeURIComponent(nodeData.id)}/delete`;

                const payload = { app_name: nodeData.app_name }; // Gửi app_name trong body

                console.log(`DETAILS_PANEL: Gửi yêu cầu DELETE đến: ${apiUrl} với payload:`, payload);
                const response = await sendApiRequest(apiUrl, 'POST', payload); // Dùng POST và gửi app_name trong body để khớp với route Flask đã có

                if (response.success) {
                    console.log("DETAILS_PANEL: Xóa node thành công!", response.message || '');
                    // Xóa node khỏi đồ thị Cytoscape hoặc tải lại toàn bộ đồ thị
                    if (typeof window.removeNodeFromCytoscapeGraph === 'function') {
                        window.removeNodeFromCytoscapeGraph(nodeData.id); // nodeData.id là ID của Cytoscape node
                    } else {
                        console.warn("DETAILS_PANEL: Hàm removeNodeFromCytoscapeGraph không tìm thấy. Cần tải lại đồ thị thủ công.");
                        if (typeof window.refreshCytoscapeGraph === 'function') {
                            window.refreshCytoscapeGraph();
                        } else {
                            alert("Node đã được xóa. Vui lòng làm mới đồ thị.");
                        }
                    }
                    showDefaultDetailsMessage();
                } else {
                    console.error("DETAILS_PANEL: Lỗi khi xóa node từ server:", response.message || 'Lỗi không xác định.');
                    alert(`Lỗi khi xóa node: ${response.message || 'Lỗi không xác định.'}`);
                    deleteNodeButton.disabled = false;
                    deleteNodeButton.innerHTML = '<i class="fas fa-trash-alt me-1"></i> Xóa Node Này';
                }
            } catch (error) {
                console.error("DETAILS_PANEL: Lỗi client khi gửi yêu cầu xóa node:", error);
                alert(`Lỗi client khi xóa node: ${error.message || String(error)}`);
                deleteNodeButton.disabled = false;
                deleteNodeButton.innerHTML = '<i class="fas fa-trash-alt me-1"></i> Xóa Node Này';
            }
        }
    });
    createTransitionButton.addEventListener('click', function () {
        console.log("DETAILS_PANEL: Nút 'Tạo Transition Mới' được click cho Node:", JSON.parse(JSON.stringify(nodeData)));
        // Dữ liệu cơ bản cho một transition mới
        const newTransitionData = {
            source: nodeData.id, // Source node là node đang được chọn
            target: '', // Target sẽ được chọn trong modal
            action_type: '', // Sẽ được chọn trong modal
            element_id: '', // Sẽ được chọn trong modal (nếu cần)
            identifier_type: '',
            element_text: '',
            macro_code: '',
            params_json: '{}', // Mặc định là JSON rỗng
            status: 'provisional', // Trạng thái mặc định cho transition mới
            attempt_count: 0,
            success_count: 0,
            // Không có neo4j_edge_id vì đây là transition mới
        };

        // Mở modal (có thể là modal Sửa Transition hiện tại, nhưng với dữ liệu mới và ở chế độ "thêm mới")
        // Bạn cần điều chỉnh openEditTransitionModal để nó biết đang ở chế độ "thêm" hay "sửa"
        // Hoặc tạo một hàm/modal riêng cho việc thêm mới.
        // Tạm thời, chúng ta sẽ giả định openEditTransitionModal có thể xử lý việc này.
        openEditTransitionModal(newTransitionData, true); // Tham số thứ hai (isCreating = true) để báo hiệu là tạo mới
    });
    let textDetailsHtml = `<h5>Chi tiết Node (Màn hình)</h5> <ul class="list-group list-group-flush"> <li class="list-group-item"><strong>ID (Screen):</strong> <code>${escapeHtml(nodeData.id)}</code></li> <li class="list-group-item"><strong>Nhãn (Label):</strong> ${escapeHtml(nodeData.label || nodeData.id)}</li> <li class="list-group-item"><strong>App Name:</strong> <code>${escapeHtml(nodeData.app_name || 'N/A')}</code></li> <li class="list-group-item"><strong>Activity:</strong> ${escapeHtml(nodeData.activity || 'N/A')}</li> <li class="list-group-item"><strong>Trạng thái:</strong> <span class="badge bg-info">${escapeHtml(nodeData.status || 'N/A')}</span></li> <li class="list-group-item"><strong>Số Element (ước tính):</strong> ${nodeData.element_count !== undefined ? nodeData.element_count : 'N/A'}</li> <li class="list-group-item"><strong>Kích thước gốc (W x H):</strong> ${escapeHtml(nodeData.original_width || '?')} x ${escapeHtml(nodeData.original_height || '?')}</li> </ul>`;

    panelTextContentDiv.innerHTML = textDetailsHtml;

    // Thêm nút này vào panelActionsAreaDiv, có thể cần sắp xếp lại vị trí các nút
    if (panelActionsAreaDiv) {
        console.log("DETAILS_PANEL: Đã thêm nút hoc");


        // Nút 1: "Xem/Phân loại Elements"
        const screenIdForLink = nodeData.id;
        if (screenIdForLink && APP_CONFIG.URL_FOR_ADMIN_SCREEN_ELEMENTS && APP_CONFIG.URL_FOR_ADMIN_SCREEN_ELEMENTS.includes('__SCREEN_ID_PLACEHOLDER__')) {
            const elementPageUrl = APP_CONFIG.URL_FOR_ADMIN_SCREEN_ELEMENTS.replace('__SCREEN_ID_PLACEHOLDER__', encodeURIComponent(screenIdForLink));

            const viewElementsContainer = document.createElement('div'); // Tạo div bọc ngoài nếu muốn các nút cách đều nhau
            viewElementsContainer.className = 'd-inline-block me-2'; // Thêm class Bootstrap để cách nút bên phải

            const viewElementsLink = document.createElement('a');
            viewElementsLink.href = elementPageUrl;
            viewElementsLink.className = 'btn btn-sm btn-outline-primary mt-2';
            viewElementsLink.target = '_blank';
            viewElementsLink.innerHTML = '<i class="fas fa-search me-1"></i> Xem Elements';

            viewElementsContainer.appendChild(viewElementsLink);
            panelActionsAreaDiv.appendChild(viewElementsContainer);
            console.log("DETAILS_PANEL: Đã thêm nút 'Xem Elements'.");
        } else {
            console.warn("DETAILS_PANEL: Không thể tạo link 'Xem Elements'. Kiểm tra URL_FOR_ADMIN_SCREEN_ELEMENTS và screenIdForLink.");
        }

        // Nút 2: "Tạo Transition Mới"
        if (nodeData.id) { // Chỉ thêm nếu có nodeData.id
            const createTransitionButton = document.createElement('button');
            createTransitionButton.type = 'button';
            createTransitionButton.className = 'btn btn-sm btn-success mt-2 me-2'; // Thêm me-2
            createTransitionButton.innerHTML = '<i class="fas fa-plus-circle me-1"></i> Tạo Transition';

            createTransitionButton.addEventListener('click', function () {
                console.log("DETAILS_PANEL: Nút 'Tạo Transition Mới' được click cho Node:", JSON.parse(JSON.stringify(nodeData)));
                const newTransitionData = {
                    source: nodeData.id,
                    target: '',
                    action_type: '',
                    element_id: '',
                    identifier_type: '',
                    element_text: '',
                    macro_code: '',
                    params_json: '{}',
                    status: 'provisional',
                    attempt_count: 0,
                    success_count: 0,
                    app_name: nodeData.app_name
                };
                openEditTransitionModal(newTransitionData, true); // true = isCreating
            });
            panelActionsAreaDiv.appendChild(createTransitionButton);
            console.log("DETAILS_PANEL: Đã thêm nút 'Tạo Transition'.");
            console.log("DETAILS_PANEL: Đã appendChild createTransitionButton. Children của panelActionsAreaDiv:", panelActionsAreaDiv.children.length, panelActionsAreaDiv.innerHTML);
        } else { console.warn("DETAILS_PANEL: nodeData.id không tồn tại, không thêm nút 'Tạo Transition'."); }

        // Nút 3: "Xóa Node"
        if (nodeData.id && nodeData.app_name) { // Cần cả id và app_name để xóa
            const deleteNodeButton = document.createElement('button');
            deleteNodeButton.type = 'button';
            deleteNodeButton.className = 'btn btn-sm btn-danger mt-2'; // Bỏ me-2 nếu đây là nút cuối cùng hoặc thêm nếu còn nút khác
            deleteNodeButton.innerHTML = '<i class="fas fa-trash-alt me-1"></i> Xóa Node';

            deleteNodeButton.addEventListener('click', async function () {
                if (confirm(`BẠN CÓ CHẮC CHẮN MUỐN XÓA NODE "${nodeData.id}" (App: ${nodeData.app_name}) KHÔNG? \nHành động này sẽ xóa node, tất cả elements và các transitions liên quan đến nó. KHÔNG THỂ HOÀN TÁC!`)) {
                    deleteNodeButton.disabled = true;
                    deleteNodeButton.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Đang xóa...';
                    try {
                        const apiUrl = `/admin/api/mapping/management/nodes/${encodeURIComponent(nodeData.id)}/delete`;
                        const payload = { app_name: nodeData.app_name };

                        const response = await sendApiRequest(apiUrl, 'POST', payload);

                        if (response.success) {
                            console.log("DETAILS_PANEL: Xóa node thành công!", response.message || '');
                            if (typeof window.removeNodeFromCytoscapeGraph === 'function') {
                                window.removeNodeFromCytoscapeGraph(nodeData.id);
                            } else if (typeof window.refreshCytoscapeGraph === 'function') {
                                window.refreshCytoscapeGraph();
                            } else {
                                alert("Node đã được xóa. Vui lòng làm mới đồ thị.");
                            }
                            showDefaultDetailsMessage();
                        } else {
                            alert(`Lỗi khi xóa node: ${response.message || response.error || 'Lỗi không xác định.'}`);
                            deleteNodeButton.disabled = false;
                            deleteNodeButton.innerHTML = '<i class="fas fa-trash-alt me-1"></i> Xóa Node';
                        }
                    } catch (error) {
                        console.error("DETAILS_PANEL: Lỗi client khi gửi yêu cầu xóa node:", error);
                        alert(`Lỗi client khi xóa node: ${error.message || String(error)}`);
                        deleteNodeButton.disabled = false;
                        deleteNodeButton.innerHTML = '<i class="fas fa-trash-alt me-1"></i> Xóa Node';
                    }
                }
            });
            panelActionsAreaDiv.appendChild(deleteNodeButton);
            console.log("DETAILS_PANEL: Đã thêm nút 'Xóa Node'.");
        } else {
            console.warn("DETAILS_PANEL: nodeData.id hoặc nodeData.app_name không tồn tại, không thêm nút 'Xóa Node'.");
        }
        console.log("DETAILS_PANEL: Đã hoàn tất việc thêm các nút vào panelActionsAreaDiv.");

        console.log("DETAILS_PANEL: panelActionsAreaDiv object:", panelActionsAreaDiv);
    } else {
        console.error("DETAILS_PANEL: panelActionsAreaDiv không tồn tại ở thời điểm thêm nút, các nút sẽ không xuất hiện.");
    }
    console.log("DETAILS_PANEL: Nội dung cuối cùng của panelActionsAreaDiv.innerHTML:", panelActionsAreaDiv.innerHTML);







    console.log("DETAILS_PANEL: Bắt đầu xử lý ảnh. URL ảnh:", nodeData.screenshot_url,
        "Original Width:", nodeData.original_width,
        "Original Height:", nodeData.original_height);

    if (nodeData.screenshot_url &&
        typeof nodeData.original_width === 'number' && nodeData.original_width > 0 &&
        typeof nodeData.original_height === 'number' && nodeData.original_height > 0) {

        panelScreenshotAreaDiv.style.display = 'block';
        panelScreenshotContainer.appendChild(panelScreenshotImage);

        panelScreenshotImage.onload = null;
        panelScreenshotImage.onerror = null;
        panelScreenshotImage.src = "";
        panelScreenshotImage.alt = `Ảnh chụp màn hình cho ${nodeData.id}`;
        panelScreenshotImage.style.display = 'block';
        panelScreenshotImage.dataset.screenId = nodeData.id;

        const loadingMsg = document.createElement('p');
        loadingMsg.className = 'text-muted small fst-italic mt-1 loading-image-text';
        loadingMsg.textContent = 'Đang tải ảnh...';
        panelScreenshotContainer.appendChild(loadingMsg);

        const onImageLoadSuccess = () => {
            if (!panelScreenshotImage) return;
            console.log(`DETAILS_PANEL: Ảnh ${nodeData.id} đã tải. Natural W/H: ${panelScreenshotImage.naturalWidth}x${panelScreenshotImage.naturalHeight}. Client W/H (sau onload): ${panelScreenshotImage.clientWidth}x${panelScreenshotImage.clientHeight}`);

            const existingLoadingMsg = panelScreenshotContainer.querySelector('.loading-image-text');
            if (existingLoadingMsg) existingLoadingMsg.textContent = 'Đang tải elements...';

            let retryCount = 0;
            const MAX_RETRIES = 30;
            const RETRY_INTERVAL = 150;

            function checkSizeAndFetchElements() {
                if (!panelScreenshotImage || !panelScreenshotContainer || !panelScreenshotContainer.contains(panelScreenshotImage)) {
                    if (existingLoadingMsg) existingLoadingMsg.remove();
                    return;
                }
                // Log kích thước client mỗi lần kiểm tra
                console.log(`DETAILS_PANEL: checkSizeAttempt ${retryCount + 1} - Client W/H: ${panelScreenshotImage.clientWidth}x${panelScreenshotImage.clientHeight}`);

                if (panelScreenshotImage.clientWidth > 0 && panelScreenshotImage.clientHeight > 0) {
                    console.log(`DETAILS_PANEL: Kích thước client của ảnh ${nodeData.id} hợp lệ. Bắt đầu tìm nạp elements...`);
                    const currentLoadingMsg = panelScreenshotContainer.querySelector('.loading-image-text');
                    if (currentLoadingMsg) currentLoadingMsg.remove();

                    const baseUrlForElements = APP_CONFIG.API_BASE_URLS.SCREEN_ELEMENTS;
                    const screenIdToFetch = nodeData.id;

                    console.log("DETAILS_PANEL: DEBUG - Base URL for elements from APP_CONFIG:", baseUrlForElements);
                    console.log("DETAILS_PANEL: DEBUG - screenIdToFetch for elements:", screenIdToFetch);

                    if (!baseUrlForElements || typeof baseUrlForElements !== 'string' || !baseUrlForElements.includes('__SCREEN_ID_PLACEHOLDER__')) {
                        console.error("DETAILS_PANEL: Lỗi cấu hình API_BASE_URLS.SCREEN_ELEMENTS! Không chứa '__SCREEN_ID_PLACEHOLDER__' hoặc không hợp lệ. URL hiện tại:", baseUrlForElements);
                        const errorMsgP = document.createElement('p'); errorMsgP.className = 'text-danger small fst-italic mt-1';
                        errorMsgP.textContent = `(Lỗi cấu hình URL API elements. Không thể tải.)`;
                        panelScreenshotContainer.appendChild(errorMsgP);
                        return;
                    }
                    if (!screenIdToFetch) {
                        console.error("DETAILS_PANEL: screenIdToFetch (nodeData.id) bị thiếu, không thể fetch elements.");
                        const errorMsgP = document.createElement('p'); errorMsgP.className = 'text-danger small fst-italic mt-1';
                        errorMsgP.textContent = `(Lỗi: Thiếu ID của node để tải elements.)`;
                        panelScreenshotContainer.appendChild(errorMsgP);
                        return;
                    }

                    const elementsApiUrl = baseUrlForElements.replace('__SCREEN_ID_PLACEHOLDER__', encodeURIComponent(screenIdToFetch));
                    console.log("DETAILS_PANEL: Final constructed elementsApiUrl:", elementsApiUrl);

                    sendApiRequest(elementsApiUrl, 'GET')
                        .then(data => {
                            console.log("DETAILS_PANEL: Dữ liệu elements nhận được từ API:", JSON.parse(JSON.stringify(data)));
                            if (data.success && Array.isArray(data.elements)) {
                                if (data.elements.length > 0) {
                                    console.log("DETAILS_PANEL: Element đầu tiên:", JSON.stringify(data.elements[0]));
                                } else {
                                    console.log("DETAILS_PANEL: API trả về danh sách elements rỗng cho node " + screenIdToFetch);
                                }
                                drawScreenOverlays(panelScreenshotImage, data.elements, nodeData.original_width, nodeData.original_height);
                            } else {
                                const errorMsgP = document.createElement('p'); errorMsgP.className = 'text-danger small fst-italic mt-1';
                                errorMsgP.textContent = `(Lỗi tải elements: ${data.error || data.message || 'Dữ liệu elements không hợp lệ.'})`;
                                panelScreenshotContainer.appendChild(errorMsgP);
                            }
                        })
                        .catch(error => {
                            console.error(`DETAILS_PANEL: Lỗi fetch elements cho ${nodeData.id} từ URL ${elementsApiUrl}:`, error);
                            const errorMsgP = document.createElement('p'); errorMsgP.className = 'text-danger small fst-italic mt-1';
                            errorMsgP.textContent = `(Lỗi fetch elements: ${error.message}. URL đã gọi: ${elementsApiUrl})`;
                            panelScreenshotContainer.appendChild(errorMsgP);
                        });
                } else if (retryCount < MAX_RETRIES) {
                    retryCount++;
                    console.warn(`DETAILS_PANEL: Ảnh ${nodeData.id} clientWidth/Height vẫn là 0. Thử lại (${retryCount}/${MAX_RETRIES})...`);
                    const currentLoadingMsg = panelScreenshotContainer.querySelector('.loading-image-text');
                    if (currentLoadingMsg) currentLoadingMsg.textContent = `Đang chờ render ảnh (${retryCount})...`;
                    setTimeout(checkSizeAndFetchElements, RETRY_INTERVAL);
                } else {
                    console.error(`DETAILS_PANEL: Vẫn không lấy được kích thước client của ảnh ${nodeData.id} sau ${MAX_RETRIES} lần thử.`);
                    const currentLoadingMsg = panelScreenshotContainer.querySelector('.loading-image-text');
                    if (currentLoadingMsg) currentLoadingMsg.remove();
                    const errorMsgP = document.createElement('p'); errorMsgP.className = 'text-danger small fst-italic mt-1';
                    errorMsgP.textContent = '(Lỗi: Không xác định được kích thước ảnh sau nhiều lần thử.)';
                    panelScreenshotContainer.appendChild(errorMsgP);
                }
            }
            // Bắt đầu vòng lặp kiểm tra kích thước ngay sau khi ảnh onload thành công
            // hoặc đợi một frame để trình duyệt có thời gian tính toán kích thước client
            requestAnimationFrame(checkSizeAndFetchElements);
        };
        const onImageLoadError = () => {
            const currentLoadingMsg = panelScreenshotContainer.querySelector('.loading-image-text');
            if (currentLoadingMsg) currentLoadingMsg.remove();
            console.error("DETAILS_PANEL: Lỗi tải ảnh cho node " + nodeData.id + ". URL: " + nodeData.screenshot_url);
            if (panelScreenshotImage) panelScreenshotImage.alt = `Lỗi tải ảnh cho ${nodeData.id}`;
            const errorMsgP = document.createElement('p'); errorMsgP.className = 'text-danger small fst-italic mt-1';
            errorMsgP.textContent = '(Lỗi tải ảnh. Kiểm tra URL và file trên server.)';
            panelScreenshotContainer.appendChild(errorMsgP);
        };

        panelScreenshotImage.onload = onImageLoadSuccess;
        panelScreenshotImage.onerror = onImageLoadError;
        panelScreenshotImage.src = nodeData.screenshot_url;

        // Xử lý trường hợp ảnh đã được cache và complete ngay lập tức
        if (panelScreenshotImage.complete) {
            console.log("DETAILS_PANEL: Ảnh đã 'complete'. Natural W/H:", panelScreenshotImage.naturalWidth, panelScreenshotImage.naturalHeight);
            if (panelScreenshotImage.naturalWidth > 0 && panelScreenshotImage.src === nodeData.screenshot_url) {
                // Kích hoạt onload handler nếu ảnh đã load xong từ cache
                // Đôi khi trình duyệt không tự kích hoạt lại onload cho ảnh cache
                onImageLoadSuccess();
            } else if (panelScreenshotImage.naturalWidth === 0 && panelScreenshotImage.src === nodeData.screenshot_url) {
                // Ảnh complete nhưng lỗi (ví dụ URL sai, file không tồn tại)
                console.error("DETAILS_PANEL: Ảnh đã complete nhưng naturalWidth là 0 (ảnh lỗi).");
                onImageLoadError();
            }
        }
    } else {
        panelScreenshotAreaDiv.style.display = 'none';
        let reason = [];
        if (!nodeData.screenshot_url) reason.push("không có URL ảnh chụp");
        if (typeof nodeData.original_width !== 'number' || nodeData.original_width <= 0) reason.push("thiếu hoặc không hợp lệ kích thước rộng gốc");
        if (typeof nodeData.original_height !== 'number' || nodeData.original_height <= 0) reason.push("thiếu hoặc không hợp lệ kích thước cao gốc");

        const reasonText = reason.length > 0 ? reason.join(' và ') : 'Không rõ lý do';
        console.warn(`DETAILS_PANEL: Không hiển thị ảnh và elements cho node ${nodeData.id} vì: ${reasonText}`);

        const reasonP = document.createElement('p');
        reasonP.className = 'text-muted mt-2 text-center small fst-italic';
        reasonP.textContent = `(Không có ảnh chụp hoặc thiếu thông tin kích thước gốc, không thể hiển thị elements. Lý do: ${reasonText})`;
        panelTextContentDiv.appendChild(reasonP);
    }
}


/**
 * Hiển thị chi tiết của một Cạnh (Transition).
 * @param {object} edgeData - Dữ liệu của cạnh từ Cytoscape (edge.data()).
 */
export function displayEdgeDetails(edgeData) {
    if (!panelTextContentDiv || !panelActionsAreaDiv || !panelScreenshotAreaDiv) {
        console.error("DETAILS_PANEL: Không thể hiển thị chi tiết Edge, thiếu DOM elements.");
        return;
    }
    console.log("DETAILS_PANEL: Displaying Edge Details:", edgeData);

    panelScreenshotAreaDiv.style.display = 'none'; // Ẩn khu vực ảnh
    panelActionsAreaDiv.innerHTML = '';

    // Xóa các nút hành động cũ

    // Hiển thị thông tin chi tiết của cạnh
    let edgeDetailsHtml = `<h5>Chi tiết Cạnh (Transition)</h5><ul class="list-group list-group-flush">`;
    edgeDetailsHtml += `<li class="list-group-item"><strong>ID (Cytoscape):</strong> <code>${escapeHtml(edgeData.id)}</code></li>`; // edgeData.id là ID của Cytoscape
    if (edgeData.neo4j_edge_id) edgeDetailsHtml += `<li class="list-group-item"><strong>ID (Neo4j):</strong> <code>${escapeHtml(edgeData.neo4j_edge_id)}</code></li>`;
    edgeDetailsHtml += `<li class="list-group-item"><strong>Nguồn:</strong> <code>${escapeHtml(edgeData.source)}</code></li>`;
    edgeDetailsHtml += `<li class="list-group-item"><strong>Đích:</strong> <code>${escapeHtml(edgeData.target)}</code></li>`;
    edgeDetailsHtml += `<li class="list-group-item"><strong>Loại H.Động:</strong> ${escapeHtml(edgeData.action_type || 'N/A')}</li>`;
    edgeDetailsHtml += `<li class="list-group-item"><strong>Macro Code:</strong> <code>${escapeHtml(edgeData.macro_code || 'N/A')}</code></li>`;
    edgeDetailsHtml += `<li class="list-group-item"><strong>Element ID (tương tác):</strong> <code>${escapeHtml(edgeData.element_id || 'N/A')}</code></li>`;
    edgeDetailsHtml += `<li class="list-group-item"><strong>Loại ID (element):</strong> ${escapeHtml(edgeData.identifier_type || 'N/A')}</li>`;
    edgeDetailsHtml += `<li class="list-group-item"><strong>Element Text:</strong> ${escapeHtml(edgeData.element_text || '--')}</li>`;
    edgeDetailsHtml += `<li class="list-group-item"><strong>Trạng thái Cạnh:</strong> <span class="badge bg-secondary">${escapeHtml(edgeData.status || 'N/A')}</span></li>`;
    edgeDetailsHtml += `<li class="list-group-item"><strong>Lần thử:</strong> ${edgeData.attempt_count !== undefined ? edgeData.attempt_count : 'N/A'}</li>`;
    edgeDetailsHtml += `<li class="list-group-item"><strong>Thành công:</strong> ${edgeData.success_count !== undefined ? edgeData.success_count : 'N/A'}</li>`;
    if (edgeData.params_json) {
        try {
            const paramsObj = JSON.parse(edgeData.params_json);
            const formattedParams = JSON.stringify(paramsObj, null, 2);
            edgeDetailsHtml += `<li class="list-group-item"><strong>Params (JSON):</strong> <pre><code style="white-space: pre-wrap; word-break: break-all;">${escapeHtml(formattedParams)}</code></pre></li>`;
        } catch (e) {
            edgeDetailsHtml += `<li class="list-group-item"><strong>Params (Raw):</strong> <pre><code>${escapeHtml(edgeData.params_json)}</code></pre></li>`;
        }
    } else {
        edgeDetailsHtml += `<li class="list-group-item"><strong>Params:</strong> N/A</li>`;
    }
    edgeDetailsHtml += `</ul>`;
    panelTextContentDiv.innerHTML = edgeDetailsHtml;

    // Tạo và thêm nút "Sửa Transition"
    if (edgeData.neo4j_edge_id) { // Chỉ thêm nút nếu có neo4j_edge_id
        const editButton = document.createElement('button');
        editButton.type = 'button';
        editButton.className = 'btn btn-sm btn-outline-warning mt-2';
        editButton.innerHTML = '<i class="fas fa-edit me-1"></i> Sửa Transition';
        editButton.addEventListener('click', function () {
            console.log("DETAILS_PANEL: Nút 'Sửa Transition' được click. Data:", edgeData);
            openEditTransitionModal(edgeData); // Gọi hàm đã import
        });
        panelActionsAreaDiv.appendChild(editButton);
        console.log("DETAILS_PANEL: Đã thêm nút 'Sửa Transition'.");
    } else {
        console.warn("DETAILS_PANEL: Không thể thêm nút 'Sửa Transition' vì thiếu neo4j_edge_id.");
    }
    // THÊM NÚT XÓA TRANSITION
    if (edgeData.neo4j_edge_id) {
        const deleteButton = document.createElement('button');
        deleteButton.type = 'button';
        deleteButton.className = 'btn btn-sm btn-outline-danger mt-2';
        deleteButton.innerHTML = '<i class="fas fa-trash-alt me-1"></i> Xóa Transition';
        deleteButton.addEventListener('click', async function () {
            if (confirm(`Bạn có chắc chắn muốn xóa transition này (Neo4j ID: ${edgeData.neo4j_edge_id}) không? Hành động này không thể hoàn tác.`)) {
                // Vô hiệu hóa nút để tránh click nhiều lần
                deleteButton.disabled = true;
                deleteButton.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Đang xóa...';

                try {
                    const apiUrl = `/admin/api/mapping/transition/delete/${encodeURIComponent(edgeData.neo4j_edge_id)}`;

                    console.log(`DETAILS_PANEL: Gửi yêu cầu DELETE đến: ${apiUrl}`);
                    const response = await sendApiRequest(apiUrl, 'DELETE'); // CSRF token được xử lý trong sendApiRequest

                    if (response.success) {
                        // Không dùng alert nữa
                        console.log("DETAILS_PANEL: Xóa transition thành công!", response.message || '');

                        // Gọi hàm để xóa cạnh khỏi đồ thị Cytoscape
                        // Hàm này cần được truyền từ main_mapping.js qua initDetailsPanelManager
                        // hoặc thông qua một event bus / global function (window.removeEdge...)
                        if (typeof window.removeEdgeFromCytoscapeGraph === 'function') {
                            window.removeEdgeFromCytoscapeGraph(edgeData.id); // edgeData.id là ID của Cytoscape
                        } else {
                            console.warn("DETAILS_PANEL: Hàm removeEdgeFromCytoscapeGraph không tìm thấy trên window. Cần tải lại đồ thị thủ công.");
                        }
                        showDefaultDetailsMessage(); // Hiển thị lại thông báo mặc định
                    } else {
                        console.error("DETAILS_PANEL: Lỗi khi xóa transition từ server:", response.error || 'Lỗi không xác định.');
                        alert(`Lỗi khi xóa transition: ${response.error || 'Lỗi không xác định.'}`);
                    }
                } catch (error) {
                    console.error("DETAILS_PANEL: Lỗi client khi gửi yêu cầu xóa transition:", error);
                    alert(`Lỗi client khi xóa transition: ${error.message || String(error)}`);
                } finally {
                    // Kích hoạt lại nút sau khi xử lý xong (nếu không thành công)
                    // Nếu thành công thì panel sẽ bị xóa/thay đổi nên không cần kích hoạt lại
                    if (deleteButton.parentElement) { // Kiểm tra xem nút còn trong DOM không
                        deleteButton.disabled = false;
                        deleteButton.innerHTML = '<i class="fas fa-trash-alt me-1"></i> Xóa Transition';
                    }
                }
            }
        });
        panelActionsAreaDiv.appendChild(deleteButton);
        // console.log("DETAILS_PANEL: Đã thêm nút 'Xóa Transition'."); // Đã có log tương tự ở trên
    }
}

/**
 * Vẽ các overlay của elements lên ảnh.
 * (Đây là hàm drawMapScreenOverlays đã sửa từ lần trước, đảm bảo nó dùng defaultSizesForOverlay từ APP_CONFIG)
 */
function drawScreenOverlays(imgElement, elementsData, nodeOriginalWidth, nodeOriginalHeight) {
    if (!panelScreenshotContainer) {
        console.error("DETAILS_PANEL (drawScreenOverlays): panelScreenshotContainer is null.");
        return;
    }
    panelScreenshotContainer.querySelectorAll('.element-overlay').forEach(el => el.remove());
    panelScreenshotContainer.querySelectorAll('.overlay-dimension-error-dsp, .text-warning, .text-muted.small.fst-italic.mt-1').forEach(el => {
        if (!el.classList.contains('loading-image-text')) {
            el.remove();
        }
    });

    const containerWidth = imgElement.parentElement.clientWidth; // Kích thước của panelScreenshotContainer
    const containerHeight = imgElement.parentElement.clientHeight; // Kích thước của panelScreenshotContainer

    const naturalWidth = imgElement.naturalWidth;
    const naturalHeight = imgElement.naturalHeight;

    if (naturalWidth === 0 || naturalHeight === 0) {
        console.warn("DETAILS_PANEL (drawScreenOverlays): Ảnh có kích thước gốc bằng 0, không thể vẽ overlay.");
        return;
    }

    const imageAspectRatio = naturalWidth / naturalHeight;
    // Sử dụng clientWidth/Height của thẻ img, vì object-fit:contain sẽ điều chỉnh kích thước hiển thị bên trong nó
    const displayBoxWidth = imgElement.clientWidth;
    const displayBoxHeight = imgElement.clientHeight;
    const displayBoxAspectRatio = displayBoxWidth / displayBoxHeight;

    let renderedImgWidth, renderedImgHeight, offsetX = 0, offsetY = 0;

    if (imageAspectRatio > displayBoxAspectRatio) {
        // Ảnh rộng hơn display box -> chiều rộng ảnh render = chiều rộng display box, chiều cao tính theo tỷ lệ
        renderedImgWidth = displayBoxWidth;
        renderedImgHeight = displayBoxWidth / imageAspectRatio;
        offsetY = (displayBoxHeight - renderedImgHeight) / 2; // Khoảng trống trên dưới
    } else {
        // Ảnh cao hơn display box (hoặc vừa khít) -> chiều cao ảnh render = chiều cao display box, chiều rộng tính theo tỷ lệ
        renderedImgHeight = displayBoxHeight;
        renderedImgWidth = displayBoxHeight * imageAspectRatio;
        offsetX = (displayBoxWidth - renderedImgWidth) / 2; // Khoảng trống trái phải
    }

    console.log(`DETAILS_PANEL (drawScreenOverlays): Image natural: ${naturalWidth}x${naturalHeight} (AR: ${imageAspectRatio.toFixed(3)})`);
    console.log(`DETAILS_PANEL (drawScreenOverlays): Img tag client: ${displayBoxWidth}x${displayBoxHeight} (AR: ${displayBoxAspectRatio.toFixed(3)})`);
    console.log(`DETAILS_PANEL (drawScreenOverlays): Rendered image inside tag: ${renderedImgWidth.toFixed(1)}x${renderedImgHeight.toFixed(1)}. Offset: X=${offsetX.toFixed(1)}, Y=${offsetY.toFixed(1)}`);


    if (renderedImgWidth === 0 || renderedImgHeight === 0) {
        console.warn(`DETAILS_PANEL (drawScreenOverlays): Kích thước ảnh render bằng 0, không thể vẽ overlay.`);
        return;
    }

    // Tỷ lệ scale dựa trên kích thước ảnh GỐC của screenshot (nodeOriginalWidth/Height)
    // và kích thước ảnh được RENDER THỰC TẾ trên màn hình (renderedImgWidth/Height)
    const scaleX = renderedImgWidth / nodeOriginalWidth;
    const scaleY = renderedImgHeight / nodeOriginalHeight;
    console.log(`DETAILS_PANEL (drawScreenOverlays): Final Scaling: X=${scaleX.toFixed(3)}, Y=${scaleY.toFixed(3)} (based on rendered image size)`);

    if (!elementsData || !Array.isArray(elementsData) || elementsData.length === 0) {
        console.info("DETAILS_PANEL (drawScreenOverlays): No valid elementsData to draw.");
        // ... (thêm thông báo nếu cần)
        return;
    }

    let drawnCount = 0;
    elementsData.forEach((elData, index) => {
        console.log(`DETAILS_PANEL (drawScreenOverlays): Processing element ${index}:`, JSON.stringify(elData).substring(0, 150));
        if (!elData) {
            console.warn(`DETAILS_PANEL (drawScreenOverlays): Element data at index ${index} is null/undefined.`);
            return;
        }
        const elIdentifier = elData.element_id || elData.resource_id || `generated_overlay_id_${index}`;
        let el_orig_left, el_orig_top, el_orig_width, el_orig_height;
        const bounds = elData.bounds;

        if (bounds && typeof bounds === 'object' &&
            bounds.left !== undefined && bounds.top !== undefined &&
            bounds.right !== undefined && bounds.bottom !== undefined) {
            try {
                el_orig_left = parseInt(bounds.left, 10);
                el_orig_top = parseInt(bounds.top, 10);
                const el_orig_right = parseInt(bounds.right, 10);
                const el_orig_bottom = parseInt(bounds.bottom, 10);
                if ([el_orig_left, el_orig_top, el_orig_right, el_orig_bottom].some(isNaN)) {
                    el_orig_width = undefined;
                } else {
                    el_orig_width = el_orig_right - el_orig_left;
                    el_orig_height = el_orig_bottom - el_orig_top;
                    if (el_orig_width <= 0 || el_orig_height <= 0) {
                        el_orig_width = undefined;
                    }
                }
            } catch (e) { el_orig_width = undefined; }
        } else { el_orig_width = undefined; }

        if (el_orig_width === undefined) {
            let coord_x_val = elData.coordinate_x; let coord_y_val = elData.coordinate_y;
            if (elData.coordinates && typeof elData.coordinates === 'object' && elData.coordinates.x !== undefined) { coord_x_val = elData.coordinates.x; coord_y_val = elData.coordinates.y; }
            if (coord_x_val !== undefined && coord_y_val !== undefined) {
                try {
                    const coord_x = parseInt(coord_x_val, 10);
                    const coord_y = parseInt(coord_y_val, 10);
                    if (isNaN(coord_x) || isNaN(coord_y)) throw new Error("NaN in coordinates");
                    const defaultSizeKey = elData.element_type || elData.class_name || 'default';
                    const defaultSize = APP_CONFIG.DEFAULT_SIZES_FOR_OVERLAY[defaultSizeKey] || APP_CONFIG.DEFAULT_SIZES_FOR_OVERLAY['default'];
                    el_orig_width = defaultSize.width;
                    el_orig_height = defaultSize.height;
                    el_orig_left = coord_x - (el_orig_width / 2);
                    el_orig_top = coord_y - (el_orig_height / 2);
                } catch (e) {
                    console.warn(`DETAILS_PANEL (drawScreenOverlays): Error in fallback for element ${elIdentifier}:`, e, elData);
                    return;
                }
            } else {
                console.warn(`DETAILS_PANEL (drawScreenOverlays): Element ${elIdentifier} has no valid bounds or coordinates. Skipping.`);
                return;
            }
        }
        console.log(`DETAILS_PANEL (drawScreenOverlays): Element ${elIdentifier} - Original Coords: L${el_orig_left}, T${el_orig_top}, W${el_orig_width}, H${el_orig_height}`);

        const x = (el_orig_left * scaleX) + offsetX;
        const y = (el_orig_top * scaleY) + offsetY;
        const w = Math.max(3, el_orig_width * scaleX);
        const h = Math.max(3, el_orig_height * scaleY);

        console.log(`DETAILS_PANEL (drawScreenOverlays): Element ${elIdentifier} - Final Pos: L${x.toFixed(1)}, T${y.toFixed(1)}, W${w.toFixed(1)}, H${h.toFixed(1)}`);

        const overlay = document.createElement('div');
        overlay.className = 'element-overlay';
        overlay.title = `ID: ${elIdentifier}\nType: ${elData.element_type || elData.class_name || 'N/A'}\nText: ${elData.text_content || '--'}`;
        overlay.style.left = `${x.toFixed(1)}px`;
        overlay.style.top = `${y.toFixed(1)}px`;
        overlay.style.width = `${w.toFixed(1)}px`;
        overlay.style.height = `${h.toFixed(1)}px`;

        const elementType = elData.element_type || elData.class_name || '';
        if (elementType.toLowerCase().includes('button')) {
            overlay.classList.add('element-overlay-button');
        }

        panelScreenshotContainer.appendChild(overlay);
        drawnCount++;
    });
    console.log(`DETAILS_PANEL (drawScreenOverlays): Drawn ${drawnCount} overlays for screen ${imgElement.dataset.screenId}.`);
    if (drawnCount === 0 && elementsData.length > 0) {
        console.warn("DETAILS_PANEL (drawScreenOverlays): Có dữ liệu elements nhưng không vẽ được overlay nào. Kiểm tra logic tính toán tọa độ/kích thước.");
        const noOverlayMsg = document.createElement('p');
        noOverlayMsg.className = 'text-warning small fst-italic mt-1';
        noOverlayMsg.textContent = '(Có elements nhưng không thể vẽ overlay. Kiểm tra console log.)';
        panelScreenshotContainer.appendChild(noOverlayMsg);
    }
}

// static/js/admin_mapping_viewer/cytoscape_manager.js
import { APP_CONFIG } from './config_mapping.js';
import { sendApiRequest, escapeHtml } from './utils_mapping.js'; // escapeHtml được dùng trong catch
import { displayNodeDetails, displayEdgeDetails, showDefaultDetailsMessage } from './details_panel_manager.js';

let cy = null;
// Không khai báo graphContainerElement và loadingIndicatorElement ở đây nữa ở cấp module
// Chúng sẽ được lấy và sử dụng cục bộ trong init hoặc truyền qua tham số.
let currentAppName = null;

export function initCytoscapeManager(appNameToLoad) {
    console.log("CYTOSCAPE_MANAGER: initCytoscapeManager called with appNameToLoad:", appNameToLoad);

    // Lấy DOM elements và gán vào biến cục bộ (local constants)
    const localGraphContainerElement = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.graphContainer);
    const localLoadingIndicatorElement = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.loadingIndicator);

    // Dòng 22 của bạn có thể là một trong những dòng console.log này hoặc gần đó.
    // Đảm bảo rằng các dòng này sử dụng 'localGraphContainerElement' và 'localLoadingIndicatorElement'.
    console.log(`CYTOSCAPE_MANAGER: Attempting to get graphContainer with ID '${APP_CONFIG.DOM_ELEMENT_IDS.graphContainer}'. Found:`, localGraphContainerElement ? 'YES' : 'NO');
    console.log(`CYTOSCAPE_MANAGER: Attempting to get loadingIndicator with ID '${APP_CONFIG.DOM_ELEMENT_IDS.loadingIndicator}'. Found:`, localLoadingIndicatorElement ? 'YES' : 'NO');

    if (!localGraphContainerElement) {
        console.error(`CYTOSCAPE_MANAGER: CRITICAL - Graph container ('${APP_CONFIG.DOM_ELEMENT_IDS.graphContainer}') KHÔNG TÌM THẤY trong DOM khi init. Đồ thị sẽ không hoạt động.`);
        return false; // Trả về false để main_mapping.js biết khởi tạo thất bại
    }
    // localLoadingIndicatorElement là tùy chọn, nhưng nếu có ID mà không tìm thấy thì cảnh báo
    if (APP_CONFIG.DOM_ELEMENT_IDS.loadingIndicator && !localLoadingIndicatorElement) {
        console.warn(`CYTOSCAPE_MANAGER: Loading indicator ('${APP_CONFIG.DOM_ELEMENT_IDS.loadingIndicator}') KHÔNG TÌM THẤY, nhưng ID đã được định nghĩa.`);
    }

    currentAppName = appNameToLoad;
    if (currentAppName) {
        // Truyền các DOM element đã lấy được (localGraphContainerElement, localLoadingIndicatorElement)
        // vào hàm fetchAndRenderGraph.
        fetchAndRenderGraph(currentAppName, localGraphContainerElement, localLoadingIndicatorElement);
    } else {
        // Xử lý trường hợp không có app name được chọn ban đầu
        if (localLoadingIndicatorElement) localLoadingIndicatorElement.style.display = 'none';
        // Đảm bảo localGraphContainerElement được sử dụng ở đây
        if (localGraphContainerElement) localGraphContainerElement.innerHTML = '<p class="text-center text-muted mt-5">Vui lòng chọn một ứng dụng để hiển thị bản đồ.</p>';
        if (typeof showDefaultDetailsMessage === 'function') showDefaultDetailsMessage();
    }
    console.log("CYTOSCAPE_MANAGER: Initialized (hoặc đã cố gắng khởi tạo).");
    return true; // Báo hiệu khởi tạo (ít nhất là phần tìm DOM) thành công
}

// Sửa hàm fetchAndRenderGraph để nhận container và indicator làm tham số
export async function fetchAndRenderGraph(appName, graphContainer, loadingIndicator) {
    // graphContainer và loadingIndicator bây giờ là các tham số được truyền vào
    if (!graphContainer) {
        console.error("CYTOSCAPE_MANAGER: fetchAndRenderGraph - Graph container là null (không được truyền vào hoặc không tìm thấy ở init).");
        // Thử lấy lại một lần nữa như một biện pháp dự phòng cuối cùng, mặc dù không nên xảy ra
        const fallbackContainer = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.graphContainer);
        if (fallbackContainer) {
            fallbackContainer.innerHTML = '<p class="text-danger text-center mt-5">Lỗi khởi tạo Cytoscape (container không được truyền đúng khi fetch).</p>';
        }
        return;
    }

    currentAppName = appName;
    console.log(`CYTOSCAPE_MANAGER: Fetching and rendering graph for app: ${appName}`);
    if (loadingIndicator) { // Kiểm tra loadingIndicator trước khi sử dụng
        loadingIndicator.style.display = 'block';
        loadingIndicator.textContent = 'Đang tải dữ liệu đồ thị...';
    }
    if (typeof showDefaultDetailsMessage === 'function') showDefaultDetailsMessage();

    if (cy) {
        cy.destroy();
        cy = null;
    }
    graphContainer.innerHTML = ''; // Sử dụng tham số graphContainer

    const apiUrl = `${APP_CONFIG.API_BASE_URLS.MAPPING_DATA}?app_name=${encodeURIComponent(appName)}`;

    try {
        const graphData = await sendApiRequest(apiUrl, 'GET');
        if (loadingIndicator) loadingIndicator.style.display = 'none';
        console.log("CYTOSCAPE_MANAGER: Graph data received:", JSON.parse(JSON.stringify(graphData)));

        if (!graphData || !Array.isArray(graphData.nodes) || !Array.isArray(graphData.edges)) {
            console.error("CYTOSCAPE_MANAGER: Dữ liệu đồ thị không hợp lệ.", graphData);
            graphContainer.innerHTML = `<p class="text-center text-danger mt-5">Lỗi: Dữ liệu đồ thị nhận được không đúng định dạng.</p>`;
            return;
        }
        if (graphData.nodes.length === 0) {
            console.warn("CYTOSCAPE_MANAGER: Không có nodes nào trong dữ liệu đồ thị.");
            graphContainer.innerHTML = '<p class="text-center text-muted mt-5">Không có màn hình (nodes) nào được tìm thấy cho ứng dụng này.</p>';
            return;
        }

        console.log("CYTOSCAPE_MANAGER: Sample nodes (first 2):", JSON.stringify(graphData.nodes.slice(0, 2)));

        console.log(`CYTOSCAPE_MANAGER: Graph container dimensions before init: W=${graphContainer.clientWidth}, H=${graphContainer.clientHeight}`);
        if (graphContainer.clientWidth === 0 || graphContainer.clientHeight === 0) {
            console.warn("CYTOSCAPE_MANAGER: Graph container has zero width or height. Cytoscape might not render correctly. Will attempt to resize later.");
        }

        cy = cytoscape({
            container: graphContainer, // Sử dụng tham số graphContainer
            elements: graphData,
            style: [ /* ... Style của bạn (đã đơn giản hóa ở lần trước) ... */
                { selector: 'node', style: { 'background-color': (ele) => { const status = ele.data('status'); if (status === 'defined' || status === 'defined_from_unknown') return '#28a745'; if (status === 'provisional_unknown' || status === 'unknown') return '#ffc107'; if (status === 'merged_to_defined') return '#17a2b8'; return '#007bff'; }, 'label': 'data(label)', 'width': '60px', 'height': '60px', 'font-size': '9px', 'color': '#ffffff', 'text-outline-width': 2, 'text-outline-color': '#555555', 'text-valign': 'center', 'text-halign': 'center', 'border-width': 2, 'border-color': '#333' } },
                { selector: 'node:selected', style: { 'background-color': '#fd7e14', 'border-color': '#c66510' } },
                { selector: 'edge', style: { 'width': 2, 'line-color': '#adb5bd', 'target-arrow-color': '#adb5bd', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier', 'label': 'data(action_type)', 'font-size': '8px', 'color': '#495057', 'text-rotation': 'autorotate', 'text-margin-y': -10, 'text-background-color': '#ffffff', 'text-background-opacity': 0.7, 'text-background-padding': '2px' } },
                { selector: 'edge:selected', style: { 'line-color': '#fd7e14', 'target-arrow-color': '#fd7e14', 'width': 3 } }
            ],
            layout: { name: 'cose', idealEdgeLength: 150, nodeRepulsion: node => 800000, edgeElasticity: edge => 120, numIter: 1800, fit: true, padding: 60, animate: 'end', animationDuration: 300, randomize: false, nodeDimensionsIncludeLabels: true },
            wheelSensitivity: 0.15, minZoom: 0.05, maxZoom: 3
        });

        attachCytoscapeEventListeners();

        cy.ready(() => {
            console.log("CYTOSCAPE_MANAGER: Cytoscape instance is ready.");
            cy.fit(null, 60);
            console.log("CYTOSCAPE_MANAGER: Graph layout complete and fitted to view.");
            console.log("CYTOSCAPE_MANAGER: Number of nodes rendered by Cytoscape:", cy.nodes().length);
            console.log("CYTOSCAPE_MANAGER: Number of edges rendered by Cytoscape:", cy.edges().length);
            if (cy.nodes().length === 0 && graphData.nodes.length > 0) {
                console.error("CYTOSCAPE_MANAGER: CRITICAL - Data has nodes, but Cytoscape rendered 0 nodes! Check data format (node needs data: {id: '...'}) and styles.");
            }
            requestAnimationFrame(() => {
                if (cy) {
                    cy.resize();
                    cy.fit(null, 60);
                    console.log("CYTOSCAPE_MANAGER: Called resize() and fit() after layout ready.");
                }
            });
        });

    } catch (error) {
        console.error("CYTOSCAPE_MANAGER: Lỗi khi lấy hoặc vẽ đồ thị:", error);
        if (loadingIndicator) loadingIndicator.style.display = 'none';
        if (graphContainer) {
            const errorMsg = (error.data && (error.data.error || error.data.message)) ? (error.data.error || error.data.message) : (error.message || 'Lỗi không xác định');
            graphContainer.innerHTML = `<div class="alert alert-danger m-5" role="alert"><strong>Lỗi tải đồ thị:</strong> ${escapeHtml(errorMsg)}</div>`;
        }
    }
}

function attachCytoscapeEventListeners() {
    if (!cy) {
        console.warn("CYTOSCAPE_MANAGER: Cannot attach event listeners, Cytoscape instance is null.");
        return;
    }
    cy.on('tap', 'node', function (evt) {
        const node = evt.target;
        if (typeof displayNodeDetails === 'function') displayNodeDetails(node.data());
    });
    cy.on('tap', 'edge', function (evt) {
        const edge = evt.target;
        if (typeof displayEdgeDetails === 'function') displayEdgeDetails(edge.data());
    });
    cy.on('tap', function (event) {
        if (event.target === cy) {
            if (typeof showDefaultDetailsMessage === 'function') showDefaultDetailsMessage();
        }
    });
}

export function updateEdgeInGraph(neo4jEdgeId, updatedData) {
    if (!cy) {
        console.warn("CYTOSCAPE_MANAGER: Cannot update edge, Cytoscape instance is null.");
        return;
    }
    // ... (code updateEdgeInGraph như cũ)
}

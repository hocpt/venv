// static/js/admin_mapping_viewer/cytoscape_manager.js
import { APP_CONFIG } from './config_mapping.js';
import { sendApiRequest } from './utils_mapping.js';
import { displayNodeDetails, displayEdgeDetails, showDefaultDetailsMessage } from './details_panel_manager.js';

let cy = null; // Cytoscape instance
let graphContainer = null;
let loadingIndicator = null;
let currentAppName = null; // Lưu trữ app name hiện tại đang hiển thị

/**
 * Khởi tạo Cytoscape Manager.
 * @param {string} appNameToLoad - Tên app để tải đồ thị ban đầu (nếu có).
 */
export function initCytoscapeManager(appNameToLoad) {
    graphContainer = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.graphContainer);
    loadingIndicator = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.loadingIndicator);

    if (!graphContainer || !loadingIndicator) {
        console.error("CYTOSCAPE_MANAGER: Graph container hoặc loading indicator không tìm thấy.");
        return;
    }

    currentAppName = appNameToLoad; // Lưu app name ban đầu
    if (currentAppName) {
        fetchAndRenderGraph(currentAppName);
    } else {
        if (loadingIndicator) loadingIndicator.style.display = 'none';
        if (graphContainer) graphContainer.innerHTML = '<p class="text-center text-muted mt-5">Vui lòng chọn một ứng dụng để hiển thị bản đồ.</p>';
        showDefaultDetailsMessage();
    }
    console.log("CYTOSCAPE_MANAGER: Initialized.");
}

/**
 * Lấy dữ liệu và vẽ đồ thị.
 * @param {string} appName - Tên ứng dụng để tải đồ thị.
 */
export async function fetchAndRenderGraph(appName) {
    if (!graphContainer || !loadingIndicator) {
        console.error("CYTOSCAPE_MANAGER: Không thể fetch/render graph, thiếu container hoặc indicator.");
        return;
    }
    if (typeof cytoscape === 'undefined') {
        loadingIndicator.textContent = 'Lỗi: Cytoscape.js chưa tải.';
        loadingIndicator.style.display = 'block';
        return;
    }

    currentAppName = appName; // Cập nhật app name hiện tại
    console.log(`CYTOSCAPE_MANAGER: Đang khởi tạo/làm mới Cytoscape cho ứng dụng: ${appName}`);
    loadingIndicator.style.display = 'block';
    showDefaultDetailsMessage(); // Reset panel chi tiết

    if (cy) { // Hủy instance cũ nếu có
        cy.destroy();
        cy = null;
    }
    graphContainer.innerHTML = ''; // Xóa đồ thị cũ

    const apiUrl = `${APP_CONFIG.API_BASE_URLS.MAPPING_DATA}?app_name=${encodeURIComponent(appName)}`;
    console.log(`CYTOSCAPE_MANAGER: Đang gọi API đồ thị: ${apiUrl}`);

    try {
        const graphData = await sendApiRequest(apiUrl, 'GET');
        loadingIndicator.style.display = 'none';
        console.log("CYTOSCAPE_MANAGER: Dữ liệu đồ thị nhận được:", graphData);

        if (!graphData || !graphData.nodes) {
            graphContainer.innerHTML = `<p class="text-center text-danger mt-5">Lỗi: Dữ liệu đồ thị không hợp lệ.</p>`;
            return;
        }
        if (!graphData.nodes.length && (!graphData.edges || !graphData.edges.length)) {
            graphContainer.innerHTML = '<p class="text-center text-muted mt-5">Chưa có dữ liệu bản đồ cho ứng dụng này.</p>';
            return;
        }

        cy = cytoscape({
            container: graphContainer,
            elements: graphData,
            style: [ /* ... (style của bạn như cũ, đảm bảo khớp với dữ liệu node/edge) ... */
                { selector: 'node', style: { 'background-color': '#66a3ff', 'label': 'data(label)', 'width': '30px', 'height': '30px', 'font-size': '8px', 'color': '#333', 'text-outline-width': 1, 'text-outline-color': '#fff', 'text-valign': 'center', 'text-halign': 'center', 'border-width': 1, 'border-color': '#444' } },
                { selector: 'node[status="defined"]', style: { 'background-color': '#4CAF50' } }, // Ví dụ
                { selector: 'node[status="provisional_unknown"]', style: { 'background-color': '#ffc107' } },
                { selector: 'node:selected', style: { 'border-width': 3, 'border-color': '#ff6600', 'background-color': '#ffa500' } },
                { selector: 'edge', style: { 'width': 1.5, 'line-color': '#ccc', 'target-arrow-color': '#ccc', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier' } },
                { selector: 'edge[action_type]', style: { 'label': 'data(action_type)', 'font-size': '7px', 'color': '#555', 'text-outline-width': 1, 'text-outline-color': '#fff', 'arrow-scale': 0.8 } },
                { selector: 'edge:selected', style: { 'line-color': '#ff6600', 'target-arrow-color': '#ff6600', 'width': 3 } }
            ],
            layout: { name: 'cose', idealEdgeLength: 100, nodeRepulsion: node => 400000, edgeElasticity: edge => 100, numIter: 1000, fit: true, padding: 30, animate: true, animationDuration: 500, randomize: false },
            wheelSensitivity: 0.2, minZoom: 0.1, maxZoom: 5
        });

        // Gắn sự kiện Cytoscape
        attachCytoscapeEventListeners();

        cy.ready(() => {
            cy.fit(null, 50); // Fit đồ thị vào view với padding 50
            console.log("CYTOSCAPE_MANAGER: Layout Cytoscape đã sẵn sàng và fit.");
        });
        // Không cần cy.resize() ở đây trừ khi container thay đổi kích thước ngay sau đó.

    } catch (error) {
        console.error("CYTOSCAPE_MANAGER: Lỗi khi lấy hoặc vẽ đồ thị:", error);
        loadingIndicator.style.display = 'none';
        graphContainer.innerHTML = `<div class="alert alert-danger m-5" role="alert"><strong>Lỗi tải đồ thị:</strong> ${escapeHtml(error.data?.error || error.message || 'Lỗi không xác định')}</div>`;
    }
}

/**
 * Gắn các trình xử lý sự kiện cho Cytoscape instance.
 */
function attachCytoscapeEventListeners() {
    if (!cy) return;

    cy.on('tap', 'node', function (evt) {
        const node = evt.target;
        displayNodeDetails(node.data()); // Gọi hàm từ details_panel_manager
    });

    cy.on('tap', 'edge', function (evt) {
        const edge = evt.target;
        displayEdgeDetails(edge.data()); // Gọi hàm từ details_panel_manager
    });

    cy.on('tap', function (event) {
        if (event.target === cy) { // Click vào nền đồ thị
            showDefaultDetailsMessage(); // Gọi hàm từ details_panel_manager
        }
    });
}

/**
 * Cập nhật dữ liệu của một cạnh trên đồ thị sau khi sửa.
 * @param {string} neo4jEdgeId - ID Neo4j của cạnh đã được cập nhật.
 * @param {object} updatedData - Dữ liệu mới của cạnh.
 */
export function updateEdgeInGraph(neo4jEdgeId, updatedData) {
    if (!cy) return;
    const edgeInGraph = cy.edges(`[neo4j_edge_id = "${neo4jEdgeId}"]`);
    if (edgeInGraph.length > 0) {
        let dataToUpdateInGraph = { ...updatedData };
        // Cytoscape dùng 'params_json', backend có thể gửi 'params_json_str'
        if (dataToUpdateInGraph.hasOwnProperty('params_json_str')) {
            dataToUpdateInGraph.params_json = dataToUpdateInGraph.params_json_str;
            delete dataToUpdateInGraph.params_json_str;
        }
        edgeInGraph.data(dataToUpdateInGraph);
        console.log("CYTOSCAPE_MANAGER: Dữ liệu cạnh đã được cập nhật trong Cytoscape instance:", edgeInGraph.data());

        // Hiển thị lại chi tiết của cạnh vừa cập nhật
        displayEdgeDetails(edgeInGraph.data());
    } else {
        console.warn("CYTOSCAPE_MANAGER: Không tìm thấy cạnh trong đồ thị để cập nhật, làm mới toàn bộ đồ thị.");
        if (currentAppName) fetchAndRenderGraph(currentAppName);
    }
}

// Có thể thêm các hàm khác như removeEdgeFromGraph, addNodeToGraph, v.v. nếu cần

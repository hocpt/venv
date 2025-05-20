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
    console.log("CYTOSCAPE_MANAGER: initCytoscapeManager called with appNameToLoad:", appNameToLoad);

    // Lấy DOM elements ngay khi init được gọi và kiểm tra
    const graphContainerId = APP_CONFIG.DOM_ELEMENT_IDS.graphContainer;
    const loadingIndicatorId = APP_CONFIG.DOM_ELEMENT_IDS.loadingIndicator;

    graphContainerElement = document.getElementById(graphContainerId);
    loadingIndicatorElement = document.getElementById(loadingIndicatorId);

    console.log(`CYTOSCAPE_MANAGER: Attempting to get graphContainer with ID '${graphContainerId}'. Found:`, graphContainerElement !== null);
    console.log(`CYTOSCAPE_MANAGER: Attempting to get loadingIndicator with ID '${loadingIndicatorId}'. Found:`, loadingIndicatorElement !== null);

    if (!graphContainerElement) { // Chỉ cần kiểm tra graphContainerElement ở đây
        console.error(`CYTOSCAPE_MANAGER: CRITICAL - Graph container ('${graphContainerId}') KHÔNG TÌM THẤY trong DOM khi init. Đồ thị sẽ không hoạt động.`);
        // Không return ngay, để main_mapping.js có thể xử lý tiếp nếu muốn
        return false; // Trả về false để báo hiệu khởi tạo thất bại
    }
    if (!loadingIndicatorElement) {
        console.warn(`CYTOSCAPE_MANAGER: Loading indicator ('${loadingIndicatorId}') KHÔNG TÌM THẤY. Một số chức năng có thể bị ảnh hưởng.`);
        // Không return, vẫn có thể cố gắng vẽ đồ thị
    }

    currentAppName = appNameToLoad;
    if (currentAppName) {
        fetchAndRenderGraph(currentAppName);
    } else {
        // Trường hợp này thường được xử lý bởi main_mapping.js
        if (loadingIndicatorElement) loadingIndicatorElement.style.display = 'none';
        if (graphContainerElement) graphContainerElement.innerHTML = '<p class="text-center text-muted mt-5">Vui lòng chọn một ứng dụng để hiển thị bản đồ.</p>';
        if (typeof showDefaultDetailsMessage === 'function') showDefaultDetailsMessage();
    }
    console.log("CYTOSCAPE_MANAGER: Initialized (hoặc đã cố gắng khởi tạo).");
    return true; // Báo hiệu khởi tạo (ít nhất là phần tìm DOM) thành công
}

export async function fetchAndRenderGraph(appName) {
    if (!graphContainerElement) { // Kiểm tra lại trước khi sử dụng
        console.error("CYTOSCAPE_MANAGER: fetchAndRenderGraph - Graph container là null. Không thể fetch/render.");
        const graphContainerById = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.graphContainer);
        if (graphContainerById) {
            graphContainerById.innerHTML = '<p class="text-danger text-center mt-5">Lỗi khởi tạo Cytoscape (container không sẵn sàng khi fetch).</p>';
        }
        return;
    }
    if (!loadingIndicatorElement) { // Kiểm tra lại
        console.warn("CYTOSCAPE_MANAGER: fetchAndRenderGraph - Loading indicator là null.");
    }


    currentAppName = appName;
    console.log(`CYTOSCAPE_MANAGER: Fetching and rendering graph for app: ${appName}`);
    if (loadingIndicatorElement) {
        loadingIndicatorElement.style.display = 'block';
        loadingIndicatorElement.textContent = 'Đang tải dữ liệu đồ thị...';
    }
    if (typeof showDefaultDetailsMessage === 'function') showDefaultDetailsMessage();

    if (cy) {
        cy.destroy();
        cy = null;
    }
    graphContainerElement.innerHTML = '';

    const apiUrl = `${APP_CONFIG.API_BASE_URLS.MAPPING_DATA}?app_name=${encodeURIComponent(appName)}`;

    try {
        const graphData = await sendApiRequest(apiUrl, 'GET');
        if (loadingIndicatorElement) loadingIndicatorElement.style.display = 'none';
        console.log("CYTOSCAPE_MANAGER: Graph data received:", JSON.parse(JSON.stringify(graphData)));

        if (!graphData || !Array.isArray(graphData.nodes) || !Array.isArray(graphData.edges)) {
            console.error("CYTOSCAPE_MANAGER: Dữ liệu đồ thị không hợp lệ.", graphData);
            graphContainerElement.innerHTML = `<p class="text-center text-danger mt-5">Lỗi: Dữ liệu đồ thị nhận được không đúng định dạng.</p>`;
            return;
        }
        if (graphData.nodes.length === 0) {
            console.warn("CYTOSCAPE_MANAGER: Không có nodes nào trong dữ liệu đồ thị.");
            graphContainerElement.innerHTML = '<p class="text-center text-muted mt-5">Không có màn hình (nodes) nào được tìm thấy cho ứng dụng này.</p>';
            return;
        }

        console.log("CYTOSCAPE_MANAGER: Sample nodes (first 2):", JSON.stringify(graphData.nodes.slice(0, 2)));

        console.log(`CYTOSCAPE_MANAGER: Graph container dimensions before init: W=${graphContainerElement.clientWidth}, H=${graphContainerElement.clientHeight}`);
        if (graphContainerElement.clientWidth === 0 || graphContainerElement.clientHeight === 0) {
            console.warn("CYTOSCAPE_MANAGER: Graph container has zero width or height. Cytoscape might not render correctly. Will attempt to resize later.");
        }

        cy = cytoscape({
            container: graphContainerElement,
            elements: graphData,

            style: [
                {
                    selector: 'node',
                    style: {
                        'background-color': (ele) => { // Thêm màu dựa trên status
                            const status = ele.data('status');
                            if (status === 'defined' || status === 'defined_from_unknown') return '#28a745'; // Green
                            if (status === 'provisional_unknown' || status === 'unknown') return '#ffc107'; // Yellow
                            if (status === 'merged_to_defined') return '#17a2b8'; // Info blue
                            return '#007bff'; // Default blue
                        },
                        'label': 'data(label)',
                        'width': '60px', // Tăng kích thước node
                        'height': '60px',
                        'font-size': '9px', // Giảm font một chút
                        'color': '#ffffff',
                        'text-outline-width': 2, // Tăng viền chữ
                        'text-outline-color': '#555555', // Màu viền chữ đậm hơn
                        'text-valign': 'center',
                        'text-halign': 'center',
                        'border-width': 2,
                        'border-color': '#333' // Border đậm hơn
                    }
                },
                {
                    selector: 'node:selected',
                    style: {
                        'background-color': '#fd7e14', // Orange for selected
                        'border-color': '#c66510'
                    }
                },
                {
                    selector: 'edge',
                    style: {
                        'width': 2,
                        'line-color': '#adb5bd',
                        'target-arrow-color': '#adb5bd',
                        'target-arrow-shape': 'triangle',
                        'curve-style': 'bezier',
                        'label': 'data(action_type)',
                        'font-size': '8px',
                        'color': '#495057',
                        'text-rotation': 'autorotate',
                        'text-margin-y': -10, // Đẩy label lên trên cạnh một chút
                        'text-background-color': '#ffffff', // Nền trắng cho label
                        'text-background-opacity': 0.7,
                        'text-background-padding': '2px'
                    }
                },
                {
                    selector: 'edge:selected',
                    style: {
                        'line-color': '#fd7e14',
                        'target-arrow-color': '#fd7e14',
                        'width': 3
                    }
                }
            ],

            layout: {
                name: 'cose',
                idealEdgeLength: 150, // Tăng khoảng cách
                nodeRepulsion: node => 800000,
                edgeElasticity: edge => 120,
                numIter: 1800,
                fit: true,
                padding: 60, // Tăng padding
                animate: 'end', // Chỉ animate ở cuối
                animationDuration: 300,
                randomize: false,
                nodeDimensionsIncludeLabels: true // Để layout tính cả label
            },
            wheelSensitivity: 0.15,
            minZoom: 0.05,
            maxZoom: 3 // Giảm max zoom một chút
        });

        attachCytoscapeEventListeners();

        cy.ready(() => {
            console.log("CYTOSCAPE_MANAGER: Cytoscape instance is ready.");
            cy.fit(null, 60);
            console.log("CYTOSCAPE_MANAGER: Graph layout complete and fitted to view.");
            console.log("CYTOSCAPE_MANAGER: Number of nodes rendered by Cytoscape:", cy.nodes().length);
            console.log("CYTOSCAPE_MANAGER: Number of edges rendered by Cytoscape:", cy.edges().length);
            if (cy.nodes().length === 0 && graphData.nodes.length > 0) {
                console.error("CYTOSCAPE_MANAGER: CRITICAL - Data has nodes, but Cytoscape rendered 0 nodes!");
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
        if (loadingIndicatorElement) loadingIndicatorElement.style.display = 'none';
        if (graphContainerElement) {
            const errorMsg = (error.data && (error.data.error || error.data.message)) ? (error.data.error || error.data.message) : (error.message || 'Lỗi không xác định');
            graphContainerElement.innerHTML = `<div class="alert alert-danger m-5" role="alert"><strong>Lỗi tải đồ thị:</strong> ${escapeHtml(errorMsg)}</div>`;
        }
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

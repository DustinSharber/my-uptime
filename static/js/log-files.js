// Log Files Management JavaScript
let logFilesData = null;

async function loadLogFiles(monitorId) {
    const container = document.getElementById('logFilesContainer');
    if (!container) return;
    
    container.innerHTML = '<div class="flex justify-center py-4"><div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div></div>';
    
    try {
        const hoursSelect = document.getElementById('hours');
        const hours = hoursSelect ? hoursSelect.value : 24;
        const response = await fetch(`/api/monitors/${monitorId}/logs/files?hours=${hours}`);
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Failed to load log files');
        }
        
        logFilesData = data;
        displayLogFiles(data, monitorId);
    } catch (error) {
        console.error('Error loading log files:', error);
        container.innerHTML = `
            <div class="text-center py-8">
                <i class="fas fa-exclamation-triangle text-2xl text-amber-500 mb-2"></i>
                <p class="text-gray-600 dark:text-gray-400">Error loading log files: ${error.message}</p>
            </div>
        `;
    }
}

function displayLogFiles(data, monitorId) {
    const container = document.getElementById('logFilesContainer');
    if (!container) return;
    
    if (data.total_batches === 0) {
        container.innerHTML = `
            <div class="text-center py-8">
                <i class="fas fa-folder-open text-2xl text-gray-400 mb-2"></i>
                <p class="text-gray-600 dark:text-gray-400">No log files uploaded for the selected time range.</p>
            </div>
        `;
        return;
    }

    let html = `
        <div class="mb-4 p-3 bg-blue-50 dark:bg-blue-900 rounded-md">
            <div class="flex items-center justify-between text-sm">
                <span class="text-blue-800 dark:text-blue-200">
                    <i class="fas fa-info-circle mr-1"></i>
                    ${data.total_batches} upload batch${data.total_batches !== 1 ? 'es' : ''} • ${data.total_files} file${data.total_files !== 1 ? 's' : ''}
                </span>
            </div>
        </div>
        <div class="space-y-4 max-h-96 overflow-y-auto">
    `;

    data.batches.forEach(batch => {
        const timestamp = new Date(batch.timestamp).toLocaleString();
        const totalSizeMB = (batch.total_size / (1024 * 1024)).toFixed(2);
        
        html += `
            <div class="border border-gray-200 dark:border-gray-600 rounded-lg p-4">
                <div class="flex items-center justify-between mb-3">
                    <div>
                        <h4 class="font-medium text-gray-800 dark:text-gray-200">
                            <i class="fas fa-clock mr-2"></i>${timestamp}
                        </h4>
                        <p class="text-sm text-gray-600 dark:text-gray-400">
                            ${batch.total_files} file${batch.total_files !== 1 ? 's' : ''} • ${totalSizeMB} MB
                        </p>
                    </div>
                    <button onclick="downloadBatch('${batch.timestamp}', ${monitorId})" 
                            class="btn btn-primary btn-sm">
                        <i class="fas fa-download mr-1"></i>Download All
                    </button>
                </div>
                <div class="grid gap-2">
        `;

        batch.files.forEach(file => {
            const fileSizeKB = (file.file_size / 1024).toFixed(1);
            html += `
                <div class="flex items-center justify-between p-2 bg-gray-50 dark:bg-gray-700 rounded">
                    <div class="flex items-center space-x-2">
                        <i class="fas fa-file-alt text-gray-400"></i>
                        <span class="text-sm font-mono text-gray-700 dark:text-gray-300">${file.filename}</span>
                        <span class="text-xs text-gray-500">(${fileSizeKB} KB)</span>
                    </div>
                    <button onclick="downloadFile('${file.download_url}')" 
                            class="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-200">
                        <i class="fas fa-download"></i>
                    </button>
                </div>
            `;
        });

        html += `
                </div>
            </div>
        `;
    });

    html += '</div>';
    container.innerHTML = html;
}

function downloadFile(url) {
    window.open(url, '_blank');
}

function downloadBatch(timestamp, monitorId) {
    window.open(`/api/monitors/${monitorId}/logs/download-batch/${encodeURIComponent(timestamp)}`, '_blank');
}

// Initialize log files functionality
function initLogFiles(monitorId, isServerClient) {
    if (!isServerClient) return;
    
    // Set up refresh button
    const refreshBtn = document.getElementById('refreshFiles');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => loadLogFiles(monitorId));
    }
    
    // Set up modal close button
    const closeModalBtn = document.getElementById('closeModal');
    if (closeModalBtn) {
        closeModalBtn.addEventListener('click', () => {
            const modal = document.getElementById('fileModal');
            if (modal) {
                modal.classList.add('hidden');
            }
        });
    }
    
    // Load files on page load
    document.addEventListener('DOMContentLoaded', () => {
        loadLogFiles(monitorId);
    });
    
    // Reload files when time range changes
    const hoursSelect = document.getElementById('hours');
    if (hoursSelect) {
        hoursSelect.addEventListener('change', () => {
            loadLogFiles(monitorId);
        });
    }
}

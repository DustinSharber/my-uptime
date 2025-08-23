// JavaScript for Python Monitor

// Auto-refresh functionality
let autoRefreshInterval = null;
const REFRESH_INTERVAL = 30000; // 30 seconds

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    console.log('Python Monitor loaded');
    
    // Start auto-refresh for dashboard
    if (window.location.pathname === '/') {
        startAutoRefresh();
    }
    
    // Initialize tooltips
    initializeTooltips();
    
    // Initialize form validation
    initializeFormValidation();
});

// Auto-refresh functions
function startAutoRefresh() {
    autoRefreshInterval = setInterval(function() {
        refreshPage();
    }, REFRESH_INTERVAL);
    
    console.log('Auto-refresh started');
}

function stopAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
        console.log('Auto-refresh stopped');
    }
}

function refreshPage() {
    // Only refresh if the page is visible
    if (!document.hidden) {
        window.location.reload();
    }
}

// Handle page visibility changes
document.addEventListener('visibilitychange', function() {
    if (document.hidden) {
        stopAutoRefresh();
    } else if (window.location.pathname === '/') {
        startAutoRefresh();
    }
});

// Tooltip initialization
function initializeTooltips() {
    // Simple tooltip implementation
    const tooltipElements = document.querySelectorAll('[title]');
    tooltipElements.forEach(function(element) {
        element.addEventListener('mouseenter', showTooltip);
        element.addEventListener('mouseleave', hideTooltip);
    });
}

function showTooltip(event) {
    const element = event.target;
    const title = element.getAttribute('title');
    
    if (title) {
        element.setAttribute('data-original-title', title);
        element.removeAttribute('title');
        
        const tooltip = document.createElement('div');
        tooltip.className = 'tooltip bg-gray-800 text-white text-sm rounded px-2 py-1 absolute z-10';
        tooltip.textContent = title;
        tooltip.style.top = (element.offsetTop - 30) + 'px';
        tooltip.style.left = element.offsetLeft + 'px';
        
        document.body.appendChild(tooltip);
        element.tooltipElement = tooltip;
    }
}

function hideTooltip(event) {
    const element = event.target;
    const originalTitle = element.getAttribute('data-original-title');
    
    if (originalTitle) {
        element.setAttribute('title', originalTitle);
        element.removeAttribute('data-original-title');
    }
    
    if (element.tooltipElement) {
        document.body.removeChild(element.tooltipElement);
        element.tooltipElement = null;
    }
}

// Form validation
function initializeFormValidation() {
    const forms = document.querySelectorAll('form');
    forms.forEach(function(form) {
        form.addEventListener('submit', validateForm);
    });
}

function validateForm(event) {
    const form = event.target;
    const requiredFields = form.querySelectorAll('[required]');
    let isValid = true;
    
    requiredFields.forEach(function(field) {
        if (!field.value.trim()) {
            isValid = false;
            showFieldError(field, 'This field is required');
        } else {
            clearFieldError(field);
        }
        
        // Validate URL fields
        if (field.type === 'url' && field.value) {
            if (!isValidUrl(field.value)) {
                isValid = false;
                showFieldError(field, 'Please enter a valid URL');
            }
        }
        
        // Validate number fields
        if (field.type === 'number' && field.value) {
            const min = field.getAttribute('min');
            const max = field.getAttribute('max');
            const value = parseInt(field.value);
            
            if (min && value < parseInt(min)) {
                isValid = false;
                showFieldError(field, `Value must be at least ${min}`);
            }
            
            if (max && value > parseInt(max)) {
                isValid = false;
                showFieldError(field, `Value must be at most ${max}`);
            }
        }
        
        // Validate JSON fields
        if (field.name === 'headers' && field.value.trim()) {
            try {
                JSON.parse(field.value);
            } catch (e) {
                isValid = false;
                showFieldError(field, 'Invalid JSON format');
            }
        }
    });
    
    if (!isValid) {
        event.preventDefault();
    }
}

function showFieldError(field, message) {
    clearFieldError(field);
    
    field.classList.add('border-red-500');
    
    const errorDiv = document.createElement('div');
    errorDiv.className = 'text-red-500 text-sm mt-1 field-error';
    errorDiv.textContent = message;
    
    field.parentNode.appendChild(errorDiv);
}

function clearFieldError(field) {
    field.classList.remove('border-red-500');
    
    const existingError = field.parentNode.querySelector('.field-error');
    if (existingError) {
        existingError.remove();
    }
}

function isValidUrl(string) {
    try {
        new URL(string);
        return true;
    } catch (_) {
        return false;
    }
}

// API functions
async function apiRequest(url, options = {}) {
    try {
        const response = await fetch(url, {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        return await response.json();
    } catch (error) {
        console.error('API request failed:', error);
        throw error;
    }
}

// Utility functions
function formatDuration(seconds) {
    if (seconds < 60) {
        return `${seconds}s`;
    } else if (seconds < 3600) {
        const minutes = Math.floor(seconds / 60);
        const remainingSeconds = seconds % 60;
        return `${minutes}m ${remainingSeconds}s`;
    } else {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        return `${hours}h ${minutes}m`;
    }
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function formatDate(date) {
    return new Date(date).toLocaleString();
}

// Status checking functions
function checkMonitorStatus(monitorId) {
    return apiRequest(`/api/monitors/${monitorId}`);
}

function getSystemStatus() {
    return apiRequest('/api/status');
}

// Notification functions
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification fixed top-4 right-4 p-4 rounded-md shadow-lg z-50 ${getNotificationClass(type)}`;
    notification.innerHTML = `
        <div class="flex items-center">
            <i class="fas ${getNotificationIcon(type)} mr-2"></i>
            <span>${message}</span>
            <button class="ml-4 text-current hover:opacity-75" onclick="this.parentNode.parentNode.remove()">
                <i class="fas fa-times"></i>
            </button>
        </div>
    `;
    
    document.body.appendChild(notification);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        if (notification.parentNode) {
            notification.remove();
        }
    }, 5000);
}

function getNotificationClass(type) {
    const classes = {
        'success': 'bg-green-100 text-green-800 border border-green-200',
        'error': 'bg-red-100 text-red-800 border border-red-200',
        'warning': 'bg-yellow-100 text-yellow-800 border border-yellow-200',
        'info': 'bg-blue-100 text-blue-800 border border-blue-200'
    };
    return classes[type] || classes['info'];
}

function getNotificationIcon(type) {
    const icons = {
        'success': 'fa-check-circle',
        'error': 'fa-exclamation-circle',
        'warning': 'fa-exclamation-triangle',
        'info': 'fa-info-circle'
    };
    return icons[type] || icons['info'];
}

// Export functions for global use
window.PythonMonitor = {
    startAutoRefresh,
    stopAutoRefresh,
    refreshPage,
    showNotification,
    apiRequest,
    formatDuration,
    formatBytes,
    formatDate,
    checkMonitorStatus,
    getSystemStatus
};
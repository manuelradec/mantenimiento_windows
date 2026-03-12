/**
 * Windows Maintenance Tool - Frontend JavaScript
 */

// Execute an action with confirmation and loading state
async function executeAction(url, buttonEl, options = {}) {
    const {
        method = 'POST',
        confirm = false,
        confirmTitle = 'Confirm Action',
        confirmMessage = 'Are you sure you want to proceed?',
        body = null,
        onSuccess = null,
        dangerLevel = 'safe',
    } = options;

    // Show confirmation if required
    if (confirm) {
        const confirmed = await showConfirm(confirmTitle, confirmMessage, dangerLevel);
        if (!confirmed) return null;
    }

    // Set loading state
    const originalText = buttonEl.innerHTML;
    buttonEl.disabled = true;
    buttonEl.innerHTML = '<span class="spinner"></span> Running...';

    try {
        const fetchOptions = { method };
        if (body) {
            fetchOptions.headers = { 'Content-Type': 'application/json' };
            fetchOptions.body = JSON.stringify(body);
        }

        const response = await fetch(url, fetchOptions);
        const data = await response.json();

        // Show result in output console
        displayResult(data);

        if (onSuccess) onSuccess(data);
        return data;
    } catch (error) {
        displayResult({
            status: 'error',
            error: `Request failed: ${error.message}`,
        });
        return null;
    } finally {
        buttonEl.disabled = false;
        buttonEl.innerHTML = originalText;
    }
}

// Display result in the page output console
function displayResult(data) {
    const console = document.getElementById('output-console');
    if (!console) return;

    const timestamp = new Date().toLocaleTimeString();
    let statusClass = 'line-info';
    let statusIcon = 'i';

    if (data.status === 'success') {
        statusClass = 'line-success';
        statusIcon = '+';
    } else if (data.status === 'warning') {
        statusClass = 'line-warning';
        statusIcon = '!';
    } else if (data.status === 'error' || data.status === 'timeout') {
        statusClass = 'line-error';
        statusIcon = 'x';
    }

    let lines = `<span class="${statusClass}">[${timestamp}] [${statusIcon}] Status: ${data.status || 'unknown'}</span>\n`;

    if (data.command) {
        lines += `<span class="line-info">  Command: ${escapeHtml(data.command)}</span>\n`;
    }
    if (data.output) {
        lines += `${escapeHtml(data.output)}\n`;
    }
    if (data.error) {
        lines += `<span class="line-error">  Error: ${escapeHtml(data.error)}</span>\n`;
    }
    if (data.duration !== undefined) {
        lines += `<span class="line-info">  Duration: ${data.duration}s</span>\n`;
    }
    lines += '\n';

    console.innerHTML += lines;
    console.scrollTop = console.scrollHeight;
}

// Fetch and display diagnostic data
async function fetchDiagnostic(url, targetId) {
    const target = document.getElementById(targetId);
    if (!target) return;

    target.innerHTML = '<span class="spinner-dark"></span> Loading...';

    try {
        const response = await fetch(url);
        const data = await response.json();

        if (data.output) {
            target.innerHTML = `<pre class="console">${escapeHtml(data.output)}</pre>`;
        } else if (data.status === 'not_applicable') {
            target.innerHTML = `<div class="alert alert-info">${escapeHtml(data.error || data.output || 'Not applicable on this system.')}</div>`;
        } else if (data.error) {
            target.innerHTML = `<div class="alert alert-danger">${escapeHtml(data.error)}</div>`;
        } else {
            target.innerHTML = `<pre class="console">${escapeHtml(JSON.stringify(data, null, 2))}</pre>`;
        }
    } catch (error) {
        target.innerHTML = `<div class="alert alert-danger">Failed to load: ${escapeHtml(error.message)}</div>`;
    }
}

// Confirmation modal
function showConfirm(title, message, dangerLevel = 'safe') {
    return new Promise((resolve) => {
        const overlay = document.getElementById('confirm-modal');
        if (!overlay) {
            resolve(window.confirm(message));
            return;
        }

        const titleEl = overlay.querySelector('.modal-title');
        const msgEl = overlay.querySelector('.modal-message');
        const confirmBtn = overlay.querySelector('.modal-confirm');
        const cancelBtn = overlay.querySelector('.modal-cancel');

        titleEl.textContent = title;
        msgEl.textContent = message;

        if (dangerLevel === 'danger') {
            confirmBtn.className = 'btn btn-danger';
        } else if (dangerLevel === 'warning') {
            confirmBtn.className = 'btn btn-warning';
        } else {
            confirmBtn.className = 'btn btn-primary';
        }

        overlay.classList.add('active');

        const cleanup = () => {
            overlay.classList.remove('active');
            confirmBtn.removeEventListener('click', onConfirm);
            cancelBtn.removeEventListener('click', onCancel);
        };

        const onConfirm = () => { cleanup(); resolve(true); };
        const onCancel = () => { cleanup(); resolve(false); };

        confirmBtn.addEventListener('click', onConfirm);
        cancelBtn.addEventListener('click', onCancel);
    });
}

// Utility: escape HTML
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Refresh system overview on dashboard
async function refreshDashboard() {
    try {
        const response = await fetch('/api/system-overview');
        const data = await response.json();

        const updates = {
            'cpu-percent': data.cpu_percent !== undefined ? data.cpu_percent + '%' : '--',
            'ram-percent': data.ram_percent !== undefined ? data.ram_percent + '%' : '--',
            'ram-used': data.ram_used_gb !== undefined ? data.ram_used_gb + ' / ' + data.ram_total_gb + ' GB' : '--',
            'disk-percent': data.disk_percent !== undefined ? data.disk_percent + '%' : '--',
            'disk-free': data.disk_free_gb !== undefined ? data.disk_free_gb + ' GB free' : '--',
            'uptime': data.uptime_str || '--',
        };

        for (const [id, value] of Object.entries(updates)) {
            const el = document.getElementById(id);
            if (el) el.textContent = value;
        }
    } catch (e) {
        // Silent fail for dashboard refresh
    }
}

// Export report
async function exportReport(format) {
    try {
        const response = await fetch(`/reports/api/export/${format}`, { method: 'POST' });
        const data = await response.json();
        if (data.status === 'success') {
            alert(`Report exported to:\n${data.path}`);
        }
    } catch (error) {
        alert(`Export failed: ${error.message}`);
    }
}

// Download report
function downloadReport(format) {
    window.open(`/reports/api/download/${format}`, '_blank');
}

// Highlight active sidebar link
document.addEventListener('DOMContentLoaded', () => {
    const path = window.location.pathname;
    document.querySelectorAll('.sidebar-nav a').forEach(link => {
        const href = link.getAttribute('href');
        if (href === path || (href !== '/' && path.startsWith(href))) {
            link.classList.add('active');
        }
    });
});

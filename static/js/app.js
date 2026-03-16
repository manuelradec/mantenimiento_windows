/**
 * CleanCPU v3.0 - Professional Windows Maintenance Tool
 * Frontend JavaScript with:
 * - CSRF protection on all state-changing requests
 * - Background job polling with cancellation
 * - Governed action support (policy, confirmation, rollback)
 * - Enhanced operational observability
 */

// ============================================================
// CSRF Token Management
// ============================================================

function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
}

function getDefaultHeaders() {
    return {
        'Content-Type': 'application/json',
        'X-CSRF-Token': getCsrfToken(),
    };
}

// ============================================================
// Action Execution (with Governance, CSRF, Job Support)
// ============================================================

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

    // Show confirmation if required by caller
    if (confirm) {
        const confirmed = await showConfirm(confirmTitle, confirmMessage, dangerLevel);
        if (!confirmed) return null;
    }

    // Set loading state
    const originalText = buttonEl.innerHTML;
    buttonEl.disabled = true;
    buttonEl.innerHTML = '<span class="spinner"></span> Running...';

    try {
        const fetchOptions = {
            method,
            headers: getDefaultHeaders(),
        };
        if (body) {
            fetchOptions.body = JSON.stringify(body);
        }

        const response = await fetch(url, fetchOptions);

        if (response.status === 403) {
            const errorData = await response.json().catch(() => ({}));
            displayResult({
                status: 'error',
                error: errorData.description || errorData.error || 'Request forbidden (CSRF or policy violation)',
            });
            return null;
        }

        const data = await response.json();

        // Handle governance responses

        // 1. Background job submitted
        if (data.status === 'submitted' && data.job_id) {
            displayResult({
                status: 'info',
                output: `Background job started: ${data.action_name || data.action_id} (ID: ${data.job_id})`,
                action_id: data.action_id,
                risk_class: data.risk_class,
            });
            pollJobStatus(data.job_id, data.action_name || data.action_id);
            return data;
        }

        // 2. Needs confirmation (server-side policy)
        if (data.status === 'needs_confirmation') {
            buttonEl.disabled = false;
            buttonEl.innerHTML = originalText;

            const warnings = data.warnings || [];
            if (data.needs_reboot) {
                warnings.push('This action may require a system reboot.');
            }
            if (data.needs_restore_point) {
                warnings.push('Creating a restore point before this action is recommended.');
            }

            const confirmed = await showConfirm(
                data.action_id || 'Confirm Action',
                data.confirm_message || 'This action requires confirmation.',
                data.risk_class === 'destructive' ? 'danger' : 'warning',
                warnings
            );

            if (confirmed) {
                // First register the confirmation token via API
                await fetch('/api/policy/confirm', {
                    method: 'POST',
                    headers: getDefaultHeaders(),
                    body: JSON.stringify({ token: data.action_id }),
                });
                // Re-submit with confirmation token
                return executeAction(url, buttonEl, {
                    ...options,
                    confirm: false,
                    body: { ...(body || {}), confirmation_token: data.action_id },
                });
            }
            return null;
        }

        // 3. Rejected by policy
        if (data.status === 'rejected') {
            displayResult({
                status: 'error',
                error: data.reason || 'Action rejected by policy engine.',
                action_id: data.action_id,
            });
            return null;
        }

        // 4. Not applicable
        if (data.status === 'not_applicable') {
            displayResult({
                status: 'info',
                output: data.error || 'Action not applicable on this system.',
                action_id: data.action_id,
            });
            return data;
        }

        // 5. Normal result - display with enriched info
        displayResult(data);

        // Show rollback info if available
        if (data.rollback_info) {
            const rb = data.rollback_info;
            if (rb.reversible && rb.reversible !== 'n/a') {
                displayResult({
                    status: 'info',
                    output: `Rollback: ${rb.reversible} — ${rb.instructions}`,
                });
            }
        }

        // Show reboot warning
        if (data.needs_reboot) {
            displayResult({
                status: 'warning',
                output: 'A system reboot is recommended to complete this operation.',
            });
        }

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

// ============================================================
// Background Job Polling (with cancellation support)
// ============================================================

let activeJobId = null;

async function pollJobStatus(jobId, actionName) {
    activeJobId = jobId;
    const statusBar = document.getElementById('job-status-bar');
    const statusText = document.getElementById('job-status-text');
    const statusName = document.getElementById('job-status-name');

    if (statusBar) {
        statusBar.style.display = 'flex';
        if (statusName) statusName.textContent = actionName;
    }

    const maxPolls = 720;
    let pollCount = 0;

    const poll = async () => {
        try {
            const response = await fetch(`/api/jobs/${jobId}`);
            const job = await response.json();

            if (job.error && response.status === 404) {
                if (statusBar) statusBar.style.display = 'none';
                displayResult({ status: 'error', error: 'Job not found.' });
                activeJobId = null;
                return;
            }

            if (statusText) {
                const elapsed = job.duration_ms ? `${Math.round(job.duration_ms/1000)}s` : '';
                statusText.textContent = `${job.status}... ${elapsed}`;
            }

            if (['completed', 'failed', 'cancelled', 'partial_success'].includes(job.status)) {
                if (statusBar) statusBar.style.display = 'none';
                activeJobId = null;

                displayResult({
                    status: job.status === 'completed' ? 'success' :
                            job.status === 'partial_success' ? 'warning' :
                            job.status === 'cancelled' ? 'info' : 'error',
                    output: job.stdout || job.output || `Job ${job.status}`,
                    error: job.stderr || job.error_message || job.error || '',
                    duration: job.duration_ms ? (job.duration_ms / 1000) : undefined,
                    command: job.command || '',
                    job_id: job.job_id,
                    action_id: job.action_id,
                    risk_class: job.risk_class,
                });

                if (job.needs_reboot) {
                    displayResult({
                        status: 'warning',
                        output: 'A system reboot is recommended to complete this operation.',
                    });
                }
                return;
            }

            pollCount++;
            if (pollCount < maxPolls) {
                setTimeout(poll, 5000);
            } else {
                if (statusBar) statusBar.style.display = 'none';
                activeJobId = null;
                displayResult({
                    status: 'warning',
                    output: `Job ${jobId} is still running. Check back later.`,
                });
            }
        } catch (error) {
            pollCount++;
            if (pollCount < maxPolls) {
                setTimeout(poll, 5000);
            }
        }
    };

    setTimeout(poll, 2000);
}

async function cancelActiveJob() {
    if (!activeJobId) {
        displayResult({ status: 'info', output: 'No active job to cancel.' });
        return;
    }
    try {
        const response = await fetch(`/api/jobs/${activeJobId}/cancel`, {
            method: 'POST',
            headers: getDefaultHeaders(),
        });
        const data = await response.json();
        displayResult({
            status: data.status === 'error' ? 'error' : 'info',
            output: data.message || data.error || 'Cancel requested.',
        });
    } catch (error) {
        displayResult({ status: 'error', error: `Cancel failed: ${error.message}` });
    }
}

// ============================================================
// Display Results (Enhanced with governance metadata)
// ============================================================

function displayResult(data) {
    const consoleEl = document.getElementById('output-console') || document.getElementById('output-area');
    if (!consoleEl) return;

    const timestamp = new Date().toLocaleTimeString();
    let statusClass = 'line-info';
    let statusIcon = 'i';

    const status = data.status || 'unknown';
    if (status === 'success' || status === 'completed') {
        statusClass = 'line-success';
        statusIcon = '+';
    } else if (status === 'warning' || status === 'partial_success') {
        statusClass = 'line-warning';
        statusIcon = '!';
    } else if (status === 'error' || status === 'timeout' || status === 'failed') {
        statusClass = 'line-error';
        statusIcon = 'x';
    }

    let lines = `<span class="${statusClass}">[${timestamp}] [${statusIcon}] Status: ${escapeHtml(status)}</span>\n`;

    if (data.action_id) {
        lines += `<span class="line-info">  Action: ${escapeHtml(data.action_id)}</span>\n`;
    }
    if (data.job_id) {
        lines += `<span class="line-info">  Job ID: ${escapeHtml(data.job_id)}</span>\n`;
    }
    if (data.risk_class) {
        lines += `<span class="line-info">  Risk: ${escapeHtml(data.risk_class)}</span>\n`;
    }
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
    if (data.operation_id) {
        lines += `<span class="line-info">  Op ID: ${escapeHtml(data.operation_id)}</span>\n`;
    }
    lines += '\n';

    consoleEl.innerHTML += lines;
    consoleEl.scrollTop = consoleEl.scrollHeight;
}

// ============================================================
// Diagnostic Fetch (Read-Only)
// ============================================================

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

// ============================================================
// Confirmation Modal
// ============================================================

function showConfirm(title, message, dangerLevel = 'safe', warnings = []) {
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
        const warningsEl = document.getElementById('modal-warnings');

        titleEl.textContent = title;
        msgEl.textContent = message;

        if (warningsEl) {
            if (warnings.length > 0) {
                warningsEl.innerHTML = warnings.map(w =>
                    `<div class="alert alert-warning" style="margin:4px 0;padding:6px 10px;font-size:12px;">${escapeHtml(w)}</div>`
                ).join('');
                warningsEl.style.display = 'block';
            } else {
                warningsEl.style.display = 'none';
            }
        }

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

// ============================================================
// Utility Functions
// ============================================================

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

// ============================================================
// Dashboard Auto-Refresh
// ============================================================

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

// ============================================================
// Report Export
// ============================================================

async function exportReport(format) {
    try {
        const response = await fetch(`/reports/api/export/${format}`, {
            method: 'POST',
            headers: getDefaultHeaders(),
        });
        const data = await response.json();
        if (data.status === 'success') {
            displayResult({ status: 'success', output: `Report exported to: ${data.path}` });
        } else {
            displayResult({ status: 'error', error: data.error || 'Export failed.' });
        }
    } catch (error) {
        displayResult({ status: 'error', error: `Export failed: ${error.message}` });
    }
}

function downloadReport(format) {
    window.open(`/reports/api/download/${format}`, '_blank');
}

// ============================================================
// Operation Mode Switcher
// ============================================================

async function setOperationMode(mode) {
    try {
        const response = await fetch('/api/policy/mode', {
            method: 'POST',
            headers: getDefaultHeaders(),
            body: JSON.stringify({ mode }),
        });
        const data = await response.json();
        const badge = document.getElementById('mode-badge');
        if (badge) badge.textContent = data.mode.toUpperCase();
        displayResult({
            status: 'success',
            output: `Operation mode changed to: ${data.mode}`,
        });
    } catch (error) {
        displayResult({
            status: 'error',
            error: `Failed to change mode: ${error.message}`,
        });
    }
}

// ============================================================
// Initialization
// ============================================================

document.addEventListener('DOMContentLoaded', () => {
    // Highlight active sidebar link
    const path = window.location.pathname;
    document.querySelectorAll('.sidebar-nav a').forEach(link => {
        const href = link.getAttribute('href');
        if (href === path || (href !== '/' && path.startsWith(href))) {
            link.classList.add('active');
        }
    });

    // Wire up cancel button if present
    const cancelBtn = document.getElementById('cancel-job-btn');
    if (cancelBtn) {
        cancelBtn.addEventListener('click', cancelActiveJob);
    }
});

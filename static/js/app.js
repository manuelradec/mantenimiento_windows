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

/**
 * Centralised POST helper for all state-changing requests.
 *
 * Guarantees:
 *   - CSRF + Content-Type headers via getDefaultHeaders()
 *   - JSON body serialisation when provided
 *   - JSON response parsing with a graceful fallback when the server
 *     returns a non-JSON body (e.g. during a transient proxy error).
 *
 * The helper normalises network/parsing failures into an object shaped
 * like a governance error response so callers can treat all failure
 * modes uniformly:
 *
 *   { status: 'error', error: '<message>', httpStatus?: <code> }
 */
async function apiPost(url, body = null, extraOptions = {}) {
    const options = {
        method: 'POST',
        headers: getDefaultHeaders(),
        ...extraOptions,
    };
    if (body !== null && body !== undefined) {
        options.body = JSON.stringify(body);
    }

    let response;
    try {
        response = await fetch(url, options);
    } catch (err) {
        return { status: 'error', error: `Error de red: ${err.message}` };
    }

    const text = await response.text();
    let data = null;
    if (text) {
        try {
            data = JSON.parse(text);
        } catch (_) {
            data = null;
        }
    }

    if (!response.ok) {
        const message = (data && (data.error || data.description))
            || text
            || `HTTP ${response.status}`;
        return { status: 'error', error: message, httpStatus: response.status };
    }

    return data !== null
        ? data
        : { status: 'error', error: 'Respuesta vacía del servidor' };
}

// Expose on window for legacy inline scripts in templates.
if (typeof window !== 'undefined') {
    window.apiPost = apiPost;
    window.getDefaultHeaders = getDefaultHeaders;
    window.getCsrfToken = getCsrfToken;
}

// ============================================================
// Action Execution (with Governance, CSRF, Job Support)
// ============================================================

async function executeAction(url, buttonEl, options = {}) {
    const {
        method = 'POST',
        confirm = false,
        confirmTitle = 'Confirmar acción',
        confirmMessage = '¿Está seguro de que desea continuar?',
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
    buttonEl.innerHTML = '<span class="spinner"></span> Ejecutando...';

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
                error: errorData.description || errorData.error || 'Solicitud prohibida (violación de CSRF o política)',
            });
            return null;
        }

        const data = await response.json();

        // Handle governance responses

        // 1. Background job submitted
        if (data.status === 'submitted' && data.job_id) {
            displayResult({
                status: 'info',
                output: `Tarea en segundo plano iniciada: ${data.action_name || data.action_id} (ID: ${data.job_id})`,
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
                warnings.push('Esta acción puede requerir un reinicio del sistema.');
            }
            if (data.needs_restore_point) {
                warnings.push('Se recomienda crear un punto de restauración antes de esta acción.');
            }

            const confirmed = await showConfirm(
                data.action_id || 'Confirmar acción',
                data.confirm_message || 'Esta acción requiere confirmación.',
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
            const reason = data.reason || '';
            // Show permission denied modal for mode/admin rejections
            if (reason.includes('not allowed in current mode') ||
                reason.includes('requires admin') ||
                reason.includes('no permitid')) {
                showPermissionDenied(
                    data.action_name || data.action_id || url,
                    data.current_mode || '—'
                );
            }
            displayResult({
                status: 'error',
                error: data.reason || 'Acción rechazada por el motor de políticas.',
                action_id: data.action_id,
            });
            return null;
        }

        // 4. Not applicable
        if (data.status === 'not_applicable') {
            displayResult({
                status: 'info',
                output: data.error || 'Acción no aplicable en este sistema.',
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
                output: 'Se recomienda reiniciar el sistema para completar esta operación.',
            });
        }

        if (onSuccess) onSuccess(data);
        return data;
    } catch (error) {
        displayResult({
            status: 'error',
            error: `Solicitud fallida: ${error.message}`,
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
                displayResult({ status: 'error', error: 'Tarea no encontrada.' });
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
                        output: 'Se recomienda reiniciar el sistema para completar esta operación.',
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
                    output: `La tarea ${jobId} aún se está ejecutando. Verifique más tarde.`,
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
        displayResult({ status: 'info', output: 'No hay tarea activa para cancelar.' });
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
            output: data.message || data.error || 'Cancelación solicitada.',
        });
    } catch (error) {
        displayResult({ status: 'error', error: `Cancelación fallida: ${error.message}` });
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

    // Scroll console internally to bottom and scroll page to show it
    scrollToOutput();

    // Lower-right toast notification — brief summary of this result
    const _toastTypeMap = {
        success: 'success', completed: 'success',
        warning: 'warning', partial_success: 'warning',
        error: 'error', timeout: 'error', failed: 'error',
    };
    const _toastType = _toastTypeMap[status] || 'info';
    const _toastMsg = data.error
        ? String(data.error).substring(0, 88)
        : data.output
        ? String(data.output).substring(0, 88)
        : status;
    showToast(_toastMsg, _toastType);
}

// ============================================================
// Diagnostic Fetch (Read-Only)
// ============================================================

async function fetchDiagnostic(url, targetId) {
    const target = document.getElementById(targetId);
    if (!target) return;

    target.innerHTML = '<span class="spinner-dark"></span> Cargando...';

    try {
        const response = await fetch(url);
        const data = await response.json();

        if (data.output) {
            target.innerHTML = `<pre class="console">${escapeHtml(data.output)}</pre>`;
        } else if (data.status === 'not_applicable') {
            target.innerHTML = `<div class="alert alert-info">${escapeHtml(data.error || data.output || 'No aplicable en este sistema.')}</div>`;
        } else if (data.error) {
            target.innerHTML = `<div class="alert alert-danger">${escapeHtml(data.error)}</div>`;
        } else {
            target.innerHTML = `<pre class="console">${escapeHtml(JSON.stringify(data, null, 2))}</pre>`;
        }
    } catch (error) {
        target.innerHTML = `<div class="alert alert-danger">Error al cargar: ${escapeHtml(error.message)}</div>`;
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

        if (!titleEl || !msgEl || !confirmBtn || !cancelBtn) {
            resolve(window.confirm(message));
            return;
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
            displayResult({ status: 'success', output: `Reporte exportado a: ${data.path}` });
        } else {
            displayResult({ status: 'error', error: data.error || 'Error al exportar.' });
        }
    } catch (error) {
        displayResult({ status: 'error', error: `Error al exportar: ${error.message}` });
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
        if (badge && data.mode) badge.textContent = data.mode.toUpperCase();
        displayResult({
            status: 'success',
            output: `Modo de operación cambiado a: ${data.mode}`,
        });
    } catch (error) {
        displayResult({
            status: 'error',
            error: `Error al cambiar modo: ${error.message}`,
        });
    }
}

// ============================================================
// Global Search (Client-Side)
// ============================================================

const SEARCH_INDEX = [
    // Dashboard
    {name:'Panel principal', section:'General', desc:'Vista general del sistema', url:'/'},
    // Diagnostics
    {name:'Diagnósticos del sistema', section:'Diagnóstico', desc:'Información completa del sistema', url:'/diagnostics'},
    {name:'Versión de Windows', section:'Diagnóstico', desc:'Build y versión del SO', url:'/diagnostics'},
    {name:'RAM', section:'Diagnóstico', desc:'Detalles de memoria RAM', url:'/diagnostics'},
    {name:'Discos', section:'Diagnóstico', desc:'Estado de discos y SMART', url:'/diagnostics'},
    {name:'Procesos activos', section:'Diagnóstico', desc:'Procesos con mayor consumo', url:'/diagnostics'},
    {name:'Servicios críticos', section:'Diagnóstico', desc:'Estado de servicios de Windows', url:'/diagnostics'},
    {name:'Temperatura CPU', section:'Diagnóstico', desc:'Sensor de temperatura del procesador', url:'/diagnostics'},
    // Drivers
    {name:'Controladores', section:'Diagnóstico', desc:'Lista de drivers instalados', url:'/drivers'},
    {name:'Dispositivos con problemas', section:'Diagnóstico', desc:'Dispositivos con errores', url:'/drivers'},
    // Cleanup
    {name:'Limpieza de temporales', section:'Limpieza', desc:'Eliminar archivos temporales del usuario', url:'/cleanup'},
    {name:'Limpieza Windows Temp', section:'Limpieza', desc:'Eliminar temporales del sistema', url:'/cleanup'},
    {name:'Vaciar papelera', section:'Limpieza', desc:'Vaciar la Papelera de reciclaje', url:'/cleanup'},
    {name:'Limpiar caché DNS', section:'Limpieza', desc:'Vaciar caché del resolver DNS', url:'/cleanup'},
    {name:'Limpiar caché Internet', section:'Limpieza', desc:'Eliminar caché del navegador', url:'/cleanup'},
    {name:'Limpiar caché WU', section:'Limpieza', desc:'Eliminar caché de Windows Update', url:'/cleanup'},
    {name:'Limpiar Prefetch', section:'Limpieza', desc:'Vaciar carpeta Prefetch', url:'/cleanup'},
    {name:'Reiniciar Explorer', section:'Limpieza', desc:'Reiniciar el shell de Windows', url:'/cleanup'},
    {name:'Limpieza de disco', section:'Limpieza', desc:'Ejecutar cleanmgr', url:'/cleanup'},
    {name:'TRIM SSD', section:'Limpieza', desc:'Ejecutar TRIM en discos SSD', url:'/cleanup'},
    {name:'Desfragmentar HDD', section:'Limpieza', desc:'Optimizar disco duro mecánico', url:'/cleanup'},
    // Repair
    {name:'SFC /scannow', section:'Reparación', desc:'Verificar integridad de archivos del sistema', url:'/repair'},
    {name:'DISM CheckHealth', section:'Reparación', desc:'Verificación rápida de componentes', url:'/repair'},
    {name:'DISM ScanHealth', section:'Reparación', desc:'Escaneo profundo de componentes', url:'/repair'},
    {name:'DISM RestoreHealth', section:'Reparación', desc:'Reparar almacén de componentes', url:'/repair'},
    {name:'CHKDSK', section:'Reparación', desc:'Verificar integridad del disco', url:'/repair'},
    {name:'WinSAT', section:'Reparación', desc:'Benchmark de rendimiento de disco', url:'/repair'},
    // Network
    {name:'Flush DNS', section:'Red', desc:'Vaciar caché DNS', url:'/network'},
    {name:'Renovar IP', section:'Red', desc:'Renovar dirección IP por DHCP', url:'/network'},
    {name:'Reparación de red', section:'Red', desc:'Secuencia completa de reparación de red', url:'/network'},
    {name:'Reset TCP/IP', section:'Red', desc:'Reiniciar pila TCP/IP', url:'/network'},
    {name:'Reset Winsock', section:'Red', desc:'Reiniciar catálogo Winsock', url:'/network'},
    {name:'Test de conectividad', section:'Red', desc:'Probar conexión a host remoto', url:'/network'},
    // Update
    {name:'Buscar actualizaciones', section:'Windows Update', desc:'Escanear actualizaciones disponibles', url:'/update'},
    {name:'Descargar actualizaciones', section:'Windows Update', desc:'Descargar actualizaciones pendientes', url:'/update'},
    {name:'Instalar actualizaciones', section:'Windows Update', desc:'Instalar actualizaciones descargadas', url:'/update'},
    {name:'Sincronizar hora', section:'Windows Update', desc:'Resincronizar reloj del sistema', url:'/update'},
    {name:'Reset Windows Update', section:'Windows Update', desc:'Reinicio completo de componentes WU', url:'/update'},
    // Power
    {name:'Plan de energía', section:'Energía', desc:'Ver y cambiar plan de energía activo', url:'/power'},
    {name:'Alto rendimiento', section:'Energía', desc:'Activar plan de alto rendimiento', url:'/power'},
    {name:'Reporte de batería', section:'Energía', desc:'Generar informe de salud de batería', url:'/power'},
    {name:'Hibernación', section:'Energía', desc:'Habilitar o deshabilitar hibernación', url:'/power'},
    // Security
    {name:'Windows Defender', section:'Seguridad', desc:'Estado y configuración del antivirus', url:'/security'},
    {name:'Escaneo rápido', section:'Seguridad', desc:'Escaneo rápido de malware', url:'/security'},
    {name:'Escaneo completo', section:'Seguridad', desc:'Escaneo completo del sistema', url:'/security'},
    {name:'Smart App Control', section:'Seguridad', desc:'Control Inteligente de Aplicaciones', url:'/security'},
    // Reports
    {name:'Reportes', section:'Herramientas', desc:'Generar y exportar reportes', url:'/reports'},
    // Advanced
    {name:'Punto de restauración', section:'Avanzado', desc:'Crear punto de restauración del sistema', url:'/advanced'},
    {name:'GPU/Display', section:'Avanzado', desc:'Diagnósticos de pantalla y GPU', url:'/advanced'},
    // New pages
    {name:'Mantenimiento Lógico', section:'Herramientas', desc:'Secuencia completa de mantenimiento preventivo (9 pasos)', url:'/maintenance'},
    {name:'Reinicio Programado', section:'Herramientas', desc:'Administrar tarea de reinicio automático', url:'/scheduled-restart'},
    {name:'Registros', section:'Herramientas', desc:'Visor de registros de la aplicación', url:'/logs'},
];

let searchSelectedIndex = -1;

function initGlobalSearch() {
    const input = document.getElementById('global-search-input');
    const results = document.getElementById('search-results');
    if (!input || !results) return;

    input.addEventListener('input', () => {
        const query = input.value.trim().toLowerCase();
        if (query.length < 2) {
            results.style.display = 'none';
            searchSelectedIndex = -1;
            return;
        }

        const matches = SEARCH_INDEX.filter(item =>
            item.name.toLowerCase().includes(query) ||
            item.desc.toLowerCase().includes(query) ||
            item.section.toLowerCase().includes(query)
        ).slice(0, 10);

        if (matches.length === 0) {
            results.innerHTML = '<div style="padding:12px;text-align:center;opacity:0.5;font-size:13px;">Sin resultados</div>';
            results.style.display = 'block';
            return;
        }

        results.innerHTML = matches.map((item, i) =>
            `<div class="search-result-item" data-index="${i}" data-url="${item.url}" onclick="window.location='${item.url}'">
                <span class="result-name">${escapeHtml(item.name)}</span>
                <span class="result-section">${escapeHtml(item.section)}</span>
                <div class="result-desc">${escapeHtml(item.desc)}</div>
            </div>`
        ).join('');

        results.style.display = 'block';
        searchSelectedIndex = -1;
    });

    input.addEventListener('keydown', (e) => {
        const items = results.querySelectorAll('.search-result-item');
        if (!items.length) return;

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            searchSelectedIndex = Math.min(searchSelectedIndex + 1, items.length - 1);
            items.forEach((el, i) => el.classList.toggle('active', i === searchSelectedIndex));
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            searchSelectedIndex = Math.max(searchSelectedIndex - 1, 0);
            items.forEach((el, i) => el.classList.toggle('active', i === searchSelectedIndex));
        } else if (e.key === 'Enter' && searchSelectedIndex >= 0) {
            e.preventDefault();
            const url = items[searchSelectedIndex].dataset.url;
            if (url) window.location = url;
        } else if (e.key === 'Escape') {
            results.style.display = 'none';
            searchSelectedIndex = -1;
            input.blur();
        }
    });

    // Close on click outside
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.search-wrapper')) {
            results.style.display = 'none';
        }
    });
}

// ============================================================
// Permission Denied Notification (Task 5)
// ============================================================

function showPermissionDenied(toolName, userRole) {
    // Create overlay if it doesn't exist
    let overlay = document.getElementById('permission-denied-overlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'permission-denied-overlay';
        overlay.className = 'permission-denied-overlay';
        overlay.innerHTML = `
            <div class="permission-denied-box">
                <span class="permission-denied-icon">&#128683;</span>
                <div class="permission-denied-title">ACCESO DENEGADO</div>
                <p class="permission-denied-message" id="perm-denied-msg"></p>
                <p class="permission-denied-role" id="perm-denied-role"></p>
                <button class="permission-denied-btn" onclick="closePermissionDenied()">Aceptar</button>
            </div>
        `;
        document.body.appendChild(overlay);
    }

    const msg = document.getElementById('perm-denied-msg');
    const role = document.getElementById('perm-denied-role');
    if (msg) msg.textContent = `No tiene los permisos necesarios para ejecutar "${toolName}". Contacte al administrador para solicitar acceso.`;
    if (role) role.textContent = `Perfil actual: ${userRole || 'Desconocido'}`;

    overlay.classList.add('active');

    // Play system alert sound
    try { new Audio('data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdH+Jj4+Jh4F8d3V5foSIi4qJiIV/e3h3eX2Ag4WHiIiHhYJ+e3l4eXyAg4WHiImIhoN/').play(); } catch(e) {}

    // Log the access attempt
    console.warn(`[PERMISSION DENIED] Tool: ${toolName}, Role: ${userRole}`);
}

function closePermissionDenied() {
    const overlay = document.getElementById('permission-denied-overlay');
    if (overlay) overlay.classList.remove('active');
}

// ============================================================
// Auto-scroll to Output (Phase 1 — Global UX)
// ============================================================

/**
 * scrollToOutput()
 * Scrolls the page to bring the output console into view AND scrolls
 * the console's internal content to the latest (bottom) entry.
 * Looks for #output-console first, then #output-area as fallback.
 * Safe to call even if neither element exists on the current page.
 */
function scrollToOutput() {
    const consoleEl = document.getElementById('output-console')
                   || document.getElementById('output-area');
    if (!consoleEl) return;
    // Scroll internal content to bottom so the latest entry is visible
    consoleEl.scrollTop = consoleEl.scrollHeight;
    // Scroll the page to bring the console into the viewport
    consoleEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ============================================================
// Toast Notifications (Phase 1 — Global UX)
// ============================================================

/**
 * showToast(msg, type, duration)
 *
 *   msg      — text to display. HTML-escaped automatically. Truncate long
 *              strings before passing; displayResult() truncates to 88 chars.
 *   type     — 'success' | 'warning' | 'error' | 'info'   (default: 'info')
 *   duration — ms before auto-dismiss                      (default: 4000)
 *
 * Requires <div id="toast-container"> in the page (injected by base.html).
 * Safe to call from any module page — silently no-ops if container absent.
 * Multiple toasts stack vertically; each auto-dismisses independently.
 * Returns the created DOM element so callers can dismiss it early if needed.
 */
function showToast(msg, type = 'info', duration = 4000) {
    const container = document.getElementById('toast-container');
    if (!container) return null;

    const icons = { success: '✓', warning: '⚠', error: '✕', info: 'i' };

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.setAttribute('role', 'alert');
    toast.innerHTML =
        `<span class="toast-icon">${icons[type] || 'i'}</span>` +
        `<span class="toast-msg">${escapeHtml(String(msg))}</span>` +
        `<button class="toast-close" aria-label="Cerrar">&times;</button>`;

    container.appendChild(toast);

    // Double requestAnimationFrame: first rAF lets the browser paint the
    // element without the visible class, second rAF adds it so the CSS
    // transition actually fires (opacity 0→1, translateX 24px→0).
    requestAnimationFrame(() =>
        requestAnimationFrame(() => toast.classList.add('toast-visible'))
    );

    let dismissTimer = setTimeout(dismiss, duration);

    function dismiss() {
        clearTimeout(dismissTimer);
        toast.classList.remove('toast-visible');
        toast.classList.add('toast-hiding');
        // Remove from DOM after the 0.2s CSS transition completes
        setTimeout(() => { if (toast.parentElement) toast.remove(); }, 250);
    }

    toast.querySelector('.toast-close').addEventListener('click', dismiss);
    return toast;
}

// ============================================================
// Progress Bar Helper (Task 6)
// ============================================================

function createProgressBar(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return null;

    container.innerHTML = `
        <div class="task-progress-container">
            <div class="task-progress-bar indeterminate" id="${containerId}-bar">Estimando...</div>
        </div>
        <div class="task-progress-timing">
            <span id="${containerId}-elapsed">Transcurrido: 00:00</span>
            <span id="${containerId}-remaining"></span>
        </div>
    `;

    const startTime = Date.now();
    const interval = setInterval(() => {
        const elapsed = Math.round((Date.now() - startTime) / 1000);
        const mins = Math.floor(elapsed / 60);
        const secs = elapsed % 60;
        const el = document.getElementById(`${containerId}-elapsed`);
        if (el) el.textContent = `Transcurrido: ${String(mins).padStart(2,'0')}:${String(secs).padStart(2,'0')}`;
    }, 1000);

    return {
        update(pct, status) {
            const bar = document.getElementById(`${containerId}-bar`);
            if (!bar) return;
            bar.classList.remove('indeterminate');
            bar.style.width = pct + '%';
            bar.textContent = pct + '%';
            if (status === 'completed') bar.classList.add('completed');
            if (status === 'failed') bar.classList.add('failed');
        },
        complete(status) {
            clearInterval(interval);
            const bar = document.getElementById(`${containerId}-bar`);
            if (!bar) return;
            bar.classList.remove('indeterminate');
            bar.style.width = '100%';
            bar.textContent = status === 'failed' ? 'Error' : 'Completado';
            if (status === 'failed') bar.classList.add('failed');
            else bar.classList.add('completed');
        },
        destroy() { clearInterval(interval); }
    };
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

    // Initialize global search
    initGlobalSearch();
});

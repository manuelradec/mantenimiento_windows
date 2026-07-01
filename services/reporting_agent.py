"""Agente de reporte al servidor centralizado RADEC.

Envía datos de mantenimiento y heartbeats al módulo Mantenimiento de
APPS-RADEC de forma asíncrona (thread daemon). Si el servidor no está
disponible, los reportes se encolan localmente en SQLite y se reenvían
en el siguiente intento.

Configuración via variables de entorno:
    CLEANCPU_SERVER_URL    — URL del servidor RADEC (ej: https://192.168.136.130:8110)
    CLEANCPU_AGENT_TOKEN   — Token Bearer compartido con el servidor
    CLEANCPU_SUCURSAL      — Nombre de la sucursal (ej: CN PUEBLA)
"""

import json
import logging
import os
import sqlite3
import ssl
import threading
import time
from datetime import datetime
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

from config import Config

logger = logging.getLogger('cleancpu.reporting_agent')

SERVER_URL = os.environ.get('CLEANCPU_SERVER_URL', '').rstrip('/')
AGENT_TOKEN = os.environ.get('CLEANCPU_AGENT_TOKEN', '')
SUCURSAL = os.environ.get('CLEANCPU_SUCURSAL', '')

MAX_RETRIES = 3
RETRY_DELAYS = [5, 15, 30]
QUEUE_DB = os.path.join(Config.LOG_DIR, 'report_queue.db')

_lock = threading.Lock()


def _get_ssl_context() -> ssl.SSLContext:
    """Contexto SSL permisivo para certificados internos mkcert."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _post_json(endpoint: str, payload: dict, timeout: int = 30) -> dict:
    """Envía POST JSON al servidor RADEC."""
    url = f'{SERVER_URL}{endpoint}'
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = Request(url, data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    req.add_header('Authorization', f'Bearer {AGENT_TOKEN}')
    req.add_header('User-Agent', f'CleanCPU-Agent/{Config.APP_VERSION}')

    ctx = _get_ssl_context() if url.startswith('https') else None
    with urlopen(req, timeout=timeout, context=ctx) as resp:
        return json.loads(resp.read().decode('utf-8'))


def is_configured() -> bool:
    return bool(SERVER_URL and AGENT_TOKEN)


# ---------------------------------------------------------------------------
# Cola local (offline queue)
# ---------------------------------------------------------------------------

def _init_queue_db():
    conn = sqlite3.connect(QUEUE_DB, timeout=5)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pending_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            endpoint TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            attempts INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


def _enqueue(endpoint: str, payload: dict):
    try:
        _init_queue_db()
        conn = sqlite3.connect(QUEUE_DB, timeout=5)
        conn.execute(
            'INSERT INTO pending_reports (endpoint, payload_json, created_at) VALUES (?, ?, ?)',
            (endpoint, json.dumps(payload, ensure_ascii=False), datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()
        logger.info('Report enqueued for later delivery')
    except Exception as e:
        logger.warning('Failed to enqueue report: %s', e)


def _flush_queue():
    """Intenta reenviar reportes pendientes."""
    try:
        _init_queue_db()
        conn = sqlite3.connect(QUEUE_DB, timeout=5)
        rows = conn.execute(
            'SELECT id, endpoint, payload_json FROM pending_reports ORDER BY id LIMIT 20'
        ).fetchall()

        for row_id, endpoint, payload_json in rows:
            try:
                payload = json.loads(payload_json)
                _post_json(endpoint, payload)
                conn.execute('DELETE FROM pending_reports WHERE id = ?', (row_id,))
                conn.commit()
                logger.info('Flushed queued report #%d', row_id)
            except Exception as e:
                conn.execute(
                    'UPDATE pending_reports SET attempts = attempts + 1 WHERE id = ?',
                    (row_id,),
                )
                conn.commit()
                logger.debug('Queued report #%d still pending: %s', row_id, e)
                break
        conn.close()
    except Exception as e:
        logger.debug('Queue flush error: %s', e)


# ---------------------------------------------------------------------------
# Recolectores opcionales (silenciosos si no están disponibles)
# ---------------------------------------------------------------------------

def _collect_system_info() -> dict:
    """Recolecta info del sistema usando la función existente de maintenance."""
    try:
        from routes.maintenance import _collect_system_info as collect
        return collect()
    except Exception as e:
        logger.warning('Could not collect system info: %s', e)
        import socket
        return {
            'hostname': socket.gethostname(),
            'ip_address': '',
            'manufacturer': '',
            'model': '',
        }


def _try_collect_inventory() -> dict:
    """Intenta recolectar inventario completo. Devuelve {} si no disponible."""
    try:
        from services.system_inventory import collect_inventory
        return collect_inventory()
    except Exception as e:
        logger.debug('Inventory collection not available: %s', e)
        return {}


def _try_run_security_audit() -> dict:
    """Intenta ejecutar auditoría de seguridad. Devuelve {} si no disponible."""
    try:
        from services.security_audit import run_security_audit
        return run_security_audit()
    except Exception as e:
        logger.debug('Security audit not available: %s', e)
        return {}


def _build_hardware_inventory(inventory: dict) -> dict:
    """Extrae sección hardware del inventario completo."""
    hw = inventory.get('hardware', {})
    sys = inventory.get('system', {})
    net = inventory.get('network', {})
    basic = inventory.get('basic', {})
    return {
        'manufacturer': hw.get('manufacturer', ''),
        'model': hw.get('model', ''),
        'serial': hw.get('serial', ''),
        'uuid': hw.get('uuid', ''),
        'processor': sys.get('processor', ''),
        'ram_total': sys.get('ram_total', ''),
        'ram_modules': sys.get('ram_modules', []),
        'disks': sys.get('disks', []),
        'os_name': sys.get('os_name', ''),
        'os_version': sys.get('os_version', ''),
        'os_build': sys.get('os_build', ''),
        'os_arch': sys.get('os_arch', ''),
        'ethernet_mac': net.get('ethernet_mac', ''),
        'ethernet_ip': net.get('ethernet_ip', ''),
        'wifi_mac': net.get('wifi_mac', ''),
        'wifi_ip': net.get('wifi_ip', ''),
        'full_name': basic.get('full_name', ''),
        'username': basic.get('username', ''),
    }


def _build_licenses(inventory: dict) -> dict:
    """Extrae licencias del inventario. Solo expone datos parciales (sin full key)."""
    office = inventory.get('office', {})
    if not office:
        return {}
    return {
        'windows': {},  # Windows license se obtiene vía SoftwareLicensingProduct — omitida aquí
        'office': [{
            'product_name': office.get('product_name', ''),
            'version': office.get('version', ''),
            'platform': office.get('platform', ''),
            'channel': office.get('channel', ''),
            'release_ids': office.get('release_ids', ''),
            'activation_status': '',  # No se consulta automáticamente sin ospp.vbs
        }] if office.get('product_name') else [],
    }


def _normalize_steps(steps: list) -> list:
    """Normaliza los pasos para incluir campos v2 (stdout/stderr/exit_code)."""
    normalized = []
    for step in steps:
        normalized.append({
            'id': step.get('id', step.get('step_id', '')),
            'name': step.get('name', step.get('step_name', '')),
            'status': step.get('status', ''),
            'message': step.get('message', ''),
            'elapsed_seconds': step.get('elapsed_seconds', 0),
            'command_text': step.get('command_text', ''),
            'stdout': step.get('stdout', ''),
            'stderr': step.get('stderr', ''),
            'exit_code': step.get('exit_code'),
            'findings': step.get('findings', step.get('findings_json', [])),
            'actions': step.get('actions', step.get('actions_json', [])),
            'errors': step.get('errors', step.get('errors_json', [])),
            'warnings': step.get('warnings', step.get('warnings_json', [])),
            'space_freed_mb': step.get('space_freed_mb', 0),
        })
    return normalized


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def send_report(
    session: dict,
    system_info: Optional[dict] = None,
    include_security: bool = True,
    include_inventory: bool = True,
):
    """Envía un reporte de mantenimiento completo al servidor (payload v2).

    Llamar después de completar una sesión de mantenimiento.
    Se ejecuta en un thread daemon para no bloquear la UI.

    Args:
        session: Datos de la sesión completada.
        system_info: Info del sistema pre-recolectada. Si None, se recolecta aquí.
        include_security: Si True, intenta incluir auditoría de seguridad.
        include_inventory: Si True, intenta incluir inventario completo de hardware.
    """
    if not is_configured():
        return

    def _do_send():
        import socket

        # Info básica del sistema
        info = system_info or _collect_system_info()
        hostname = info.get('hostname', socket.gethostname())
        upgrade_opportunities = info.pop('upgrade_opportunities', {})

        # Inventario completo (opcional, no bloquea si falla)
        hw_inventory = {}
        sw_inventory = []
        licenses = {}
        if include_inventory:
            full_inv = _try_collect_inventory()
            if full_inv:
                hw_inventory = _build_hardware_inventory(full_inv)
                licenses = _build_licenses(full_inv)

        # Auditoría de seguridad (opcional)
        security_audit = {}
        if include_security:
            audit_result = _try_run_security_audit()
            if audit_result:
                security_audit = {
                    'status': audit_result.get('status', ''),
                    'started_at': audit_result.get('started_at', ''),
                    'ended_at': audit_result.get('ended_at', ''),
                    'duration': audit_result.get('duration', 0),
                    'findings': audit_result.get('findings', []),
                    'warnings': audit_result.get('warnings', []),
                    'errors': audit_result.get('errors', []),
                    'recommended_actions': audit_result.get('recommended_actions', []),
                }

        # Recomendaciones desde upgrade_opportunities
        recommendations = []
        for rec in upgrade_opportunities.get('recommendations', []):
            recommendations.append({
                'category': rec.get('category', 'hardware'),
                'title': rec.get('title', rec.get('component', '')),
                'description': rec.get('recommendation', rec.get('description', '')),
                'priority': rec.get('priority', 'medium'),
            })

        # Normalizar pasos con campos v2
        steps = _normalize_steps(session.get('steps', []))

        payload = {
            'schema_version': '2.0',
            'agent_version': Config.APP_VERSION,
            'hostname': hostname,
            'sucursal': SUCURSAL,
            'system_info': info,
            'hardware_inventory': hw_inventory,
            'software_inventory': sw_inventory,
            'security_audit': security_audit,
            'licenses': licenses,
            'recommendations': recommendations,
            'session': {
                'id': session.get('id', ''),
                'mode': session.get('mode', 'full'),
                'status': session.get('status', 'unknown'),
                'started_at': session.get('started_at', ''),
                'completed_at': session.get('completed_at', ''),
                'total_steps': session.get('total_steps', len(steps)),
                'steps_completed': session.get('steps_completed', 0),
                'steps_failed': session.get('steps_failed', 0),
                'steps': steps,
            },
            'upgrade_opportunities': upgrade_opportunities,
        }

        for attempt in range(MAX_RETRIES):
            try:
                result = _post_json('/api/agent/report', payload)
                logger.info('Report sent successfully: %s', result.get('status'))
                _flush_queue()
                return
            except Exception as e:
                logger.warning('Report attempt %d failed: %s', attempt + 1, e)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAYS[attempt])

        _enqueue('/api/agent/report', payload)

    thread = threading.Thread(target=_do_send, daemon=True, name='reporting-agent')
    thread.start()


def send_heartbeat():
    """Envía un heartbeat con info actualizada del equipo.

    Llamar al arrancar la aplicación.
    """
    if not is_configured():
        return

    def _do_heartbeat():
        time.sleep(3)
        import socket
        info = _collect_system_info()
        hostname = info.get('hostname', socket.gethostname())
        upgrade_opportunities = info.pop('upgrade_opportunities', {})

        payload = {
            'agent_version': Config.APP_VERSION,
            'hostname': hostname,
            'system_info': info,
            'sucursal': SUCURSAL,
            'upgrade_opportunities': upgrade_opportunities,
        }

        try:
            result = _post_json('/api/agent/heartbeat', payload)
            logger.info('Heartbeat sent: %s', result.get('status'))
            _flush_queue()
        except Exception as e:
            logger.info('Heartbeat failed (server may be unreachable): %s', e)

    thread = threading.Thread(target=_do_heartbeat, daemon=True, name='heartbeat')
    thread.start()


def send_error(error_type: str, message: str, context: Optional[dict] = None):
    """Reporta un error del agente al servidor.

    No bloqueante — falla silenciosamente si el servidor no está disponible.
    """
    if not is_configured():
        return

    def _do_send():
        import socket
        payload = {
            'agent_version': Config.APP_VERSION,
            'hostname': socket.gethostname().upper(),
            'error_type': error_type,
            'message': message,
            'context': context or {},
        }
        try:
            _post_json('/api/agent/error', payload, timeout=10)
        except Exception as e:
            logger.debug('Error report not delivered: %s', e)

    thread = threading.Thread(target=_do_send, daemon=True, name='error-report')
    thread.start()

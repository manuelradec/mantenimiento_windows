"""
Network share credential manager.

Thin wrapper around Windows' ``cmdkey`` built-in so the technician can
pre-register a username/password for the report share before the
maintenance flow attempts to copy files there. Prevents the WinError 1326
"The user name or password is incorrect" crash at report-upload time.

The password never leaves this process in any loggable form:
  - It's passed as a single argv element to ``cmdkey /pass:<p>``.
  - The ``description`` sent to ``run_cmd`` is always the masked form.
  - The allowlist redactor masks ``pass=*`` / ``pass:*`` in audit trails.
"""
import logging
import re
import sys

from services.command_runner import run_cmd, CommandStatus

logger = logging.getLogger('cleancpu.network_credentials')

# Target patterns we accept:
#   \\host\share                 (UNC)
#   \\host                       (server only)
#   host                         (NetBIOS name)
# Reject anything with shell metacharacters or newlines.
_TARGET_RE = re.compile(r'^[A-Za-z0-9_.\-\\$ ]+$')


def _validate_target(target: str) -> str:
    """Normalize and validate a credential target; raise ValueError on bad input."""
    t = (target or '').strip().strip('"').strip("'")
    if not t:
        raise ValueError('Target de credencial vacio.')
    if not _TARGET_RE.match(t):
        raise ValueError(f'Target de credencial invalido: {target!r}')
    return t


def list_credentials() -> dict:
    """
    Return stored credential targets via ``cmdkey /list``.
    Parses a minimal subset (``Target: ...`` lines) so callers only see
    targets, never usernames. Returns ``{'status': ..., 'targets': [...]}``.
    """
    if sys.platform != 'win32':
        return {'status': 'not_applicable', 'targets': [], 'message': 'Solo en Windows.'}

    result = run_cmd(
        ['cmdkey', '/list'],
        timeout=15,
        description='List stored Windows credentials',
    )
    if result.is_error:
        return {
            'status': 'error',
            'targets': [],
            'message': result.error or 'Error ejecutando cmdkey /list.',
        }

    targets = []
    for line in (result.output or '').splitlines():
        stripped = line.strip()
        if stripped.lower().startswith('target:'):
            _, _, value = stripped.partition(':')
            value = value.strip()
            if value:
                targets.append(value)
    return {'status': 'success', 'targets': targets}


def save_credential(target: str, user: str, password: str) -> dict:
    """
    Store a generic credential so subsequent access to ``target`` uses it.
    Returns a status dict; the password is never echoed back or logged.
    """
    if sys.platform != 'win32':
        return {'status': 'not_applicable', 'message': 'Solo en Windows.'}

    try:
        normalized = _validate_target(target)
    except ValueError as e:
        return {'status': 'invalid_target', 'message': str(e)}

    if not (user or '').strip():
        return {'status': 'invalid_user', 'message': 'Usuario requerido.'}
    if not password:
        return {'status': 'invalid_password', 'message': 'Password requerido.'}

    result = run_cmd(
        ['cmdkey', f'/add:{normalized}', f'/user:{user.strip()}', f'/pass:{password}'],
        timeout=15,
        description=f'Save credential for {normalized} (user=***)',
    )
    if result.is_error:
        return {
            'status': 'error',
            'message': result.error or 'cmdkey /add fallo.',
            'target': normalized,
        }
    return {'status': 'success', 'target': normalized}


def delete_credential(target: str) -> dict:
    """Remove a stored credential by target."""
    if sys.platform != 'win32':
        return {'status': 'not_applicable', 'message': 'Solo en Windows.'}

    try:
        normalized = _validate_target(target)
    except ValueError as e:
        return {'status': 'invalid_target', 'message': str(e)}

    result = run_cmd(
        ['cmdkey', f'/delete:{normalized}'],
        timeout=15,
        description=f'Delete stored credential for {normalized}',
    )
    if result.status == CommandStatus.ERROR and 'element not found' in (result.output or '').lower():
        return {'status': 'not_found', 'target': normalized}
    if result.is_error:
        return {
            'status': 'error',
            'message': result.error or 'cmdkey /delete fallo.',
            'target': normalized,
        }
    return {'status': 'success', 'target': normalized}

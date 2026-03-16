"""
Smart App Control (Control Inteligente de Aplicaciones) detection and management.

Handles:
- Detection of Smart App Control availability and state
- State management (disable only, when technically possible)
- Opening Windows Security Smart App Control page

Windows Smart App Control states:
- On (Enabled): Actively blocking untrusted apps
- Evaluation: Learning mode, collecting data before enabling
- Off (Disabled): Not active, may require clean install to re-enable
- Not available: Feature not present on this Windows edition/version
- Unknown: Could not determine state reliably

IMPORTANT:
- Smart App Control can only be re-enabled via a clean Windows install
  once it has been turned off.
- Disabling it is effectively a ONE-WAY operation.
- Available only on Windows 11 22H2+ with clean installs or upgrades
  that went through OOBE with it enabled.
"""
import logging
import sys

from services.command_runner import (
    run_powershell, run_cmd, CommandStatus, CommandResult
)

logger = logging.getLogger('cleancpu.smart_app_control')

# Registry path where Smart App Control state is stored
SAC_REGISTRY_PATH = r'HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy'
SAC_REGISTRY_VALUE = 'VerifiedAndReputablePolicyState'

# State values from registry (DWORD):
# 0 = Off/Disabled
# 1 = On/Enforcing
# 2 = Evaluation mode
SAC_STATE_MAP = {
    0: 'off',
    1: 'on',
    2: 'evaluation',
}

SAC_STATE_LABELS_ES = {
    'on': 'Activado',
    'evaluation': 'Evaluación',
    'off': 'Desactivado',
    'not_available': 'No disponible',
    'unsupported': 'No soportado',
    'unknown': 'Desconocido',
}


def detect_smart_app_control_status():
    """
    Detect Smart App Control availability and current state.

    Uses a layered approach:
    1. Check Windows version (requires Win 11 22H2+)
    2. Read registry for SAC policy state
    3. Validate with Windows Security Center if possible

    Returns:
        CommandResult with details containing:
        - state: on/evaluation/off/not_available/unsupported/unknown
        - state_label: Spanish label
        - supported: bool
        - changeable: bool (can the state be modified)
        - can_disable: bool
        - can_enable: bool
        - admin_required: bool
        - reboot_required: bool
        - one_way_disable: bool
        - detection_method: str
        - raw_value: int or None
        - explanation: str
    """
    # Non-Windows: not applicable
    if sys.platform != 'win32':
        return CommandResult(
            status=CommandStatus.NOT_APPLICABLE,
            output='Smart App Control no está disponible en esta plataforma.',
            details=_build_status_details(
                state='not_available',
                supported=False,
                explanation='Solo disponible en Windows 11 22H2 o posterior.',
                detection_method='platform_check',
            ),
        )

    # Step 1: Check Windows version
    version_check = _check_windows_version()
    if not version_check['supported']:
        return CommandResult(
            status=CommandStatus.SUCCESS,
            output=f"Control Inteligente de Aplicaciones: {SAC_STATE_LABELS_ES['unsupported']}",
            details=_build_status_details(
                state='unsupported',
                supported=False,
                explanation=version_check.get(
                    'reason',
                    'Este equipo no cumple los requisitos de versión de Windows.'),
                detection_method='version_check',
            ),
        )

    # Step 2: Read registry value
    registry_result = _read_sac_registry()
    if registry_result['success']:
        raw_value = registry_result['value']
        state = SAC_STATE_MAP.get(raw_value, 'unknown')
        label = SAC_STATE_LABELS_ES.get(state, 'Desconocido')

        # Determine changeability
        can_disable = state in ('on', 'evaluation')
        # Re-enabling is NOT possible once disabled (requires clean install)
        can_enable = False

        explanation = _get_state_explanation(state)

        return CommandResult(
            status=CommandStatus.SUCCESS,
            output=(
                f"Control Inteligente de Aplicaciones: {label}\n"
                f"Valor del registro: {raw_value}\n"
                f"Se puede desactivar: {'Sí' if can_disable else 'No'}\n"
                f"Se puede reactivar: No (requiere reinstalación limpia de Windows)"
            ),
            details=_build_status_details(
                state=state,
                supported=True,
                changeable=can_disable,
                can_disable=can_disable,
                can_enable=can_enable,
                raw_value=raw_value,
                explanation=explanation,
                detection_method='registry',
            ),
        )

    # Step 3: Fallback - try Windows Security app query
    fallback_result = _fallback_detection()
    if fallback_result['success']:
        state = fallback_result.get('state', 'unknown')
        return CommandResult(
            status=CommandStatus.SUCCESS,
            output=f"Control Inteligente de Aplicaciones: {SAC_STATE_LABELS_ES.get(state, 'Desconocido')}",
            details=_build_status_details(
                state=state,
                supported=True,
                explanation='Estado detectado por método alternativo. '
                            'Precisión reducida.',
                detection_method='fallback',
            ),
        )

    # Could not determine
    return CommandResult(
        status=CommandStatus.WARNING,
        output='No se pudo determinar el estado del Control Inteligente de Aplicaciones.',
        details=_build_status_details(
            state='unknown',
            supported=True,  # Version check passed
            explanation='El registro no contiene la clave esperada. '
                        'Es posible que la función nunca haya sido habilitada en este equipo.',
            detection_method='none',
        ),
    )


def attempt_disable_smart_app_control():
    """
    Attempt to disable Smart App Control by setting registry value to 0.

    WARNING: This is a ONE-WAY operation. Once disabled, Smart App Control
    can only be re-enabled with a clean Windows installation.

    Returns:
        CommandResult with before/after state information.
    """
    if sys.platform != 'win32':
        return CommandResult(
            status=CommandStatus.NOT_APPLICABLE,
            output='No disponible en esta plataforma.',
        )

    # First detect current state
    current = detect_smart_app_control_status()
    current_state = current.details.get('state', 'unknown')

    if current_state == 'off':
        return CommandResult(
            status=CommandStatus.WARNING,
            output='El Control Inteligente de Aplicaciones ya está desactivado.',
            details={
                'state_before': 'off',
                'state_after': 'off',
                'action_taken': False,
                'explanation': 'No se realizó ningún cambio.',
            },
        )

    if current_state in ('not_available', 'unsupported', 'unknown'):
        return CommandResult(
            status=CommandStatus.ERROR,
            output=f'No se puede desactivar: estado actual es "{SAC_STATE_LABELS_ES.get(current_state, current_state)}".',
            error='La función no está disponible o no se pudo detectar el estado.',
            details={
                'state_before': current_state,
                'action_taken': False,
            },
        )

    # Attempt to set registry value to 0 (Off)
    result = run_powershell(
        f'Set-ItemProperty -Path "{SAC_REGISTRY_PATH}" '
        f'-Name "{SAC_REGISTRY_VALUE}" -Value 0 -Type DWord -Force',
        requires_admin=True,
        description='Desactivar Control Inteligente de Aplicaciones',
    )

    if result.status in (CommandStatus.SUCCESS, CommandStatus.WARNING):
        # Verify the change
        verify = _read_sac_registry()
        new_state = SAC_STATE_MAP.get(verify.get('value'), 'unknown') if verify['success'] else 'unknown'

        if new_state == 'off':
            return CommandResult(
                status=CommandStatus.SUCCESS,
                output=(
                    'Control Inteligente de Aplicaciones desactivado correctamente.\n'
                    'ADVERTENCIA: Esta acción NO es reversible sin una reinstalación limpia de Windows.\n'
                    'Se recomienda reiniciar el equipo para aplicar los cambios completamente.'
                ),
                details={
                    'state_before': current_state,
                    'state_after': 'off',
                    'action_taken': True,
                    'reboot_recommended': True,
                    'reversible': False,
                },
            )
        else:
            return CommandResult(
                status=CommandStatus.WARNING,
                output=(
                    f'Se ejecutó el comando pero el estado verificado es: '
                    f'{SAC_STATE_LABELS_ES.get(new_state, new_state)}.\n'
                    f'Es posible que se requiera reiniciar para completar el cambio.'
                ),
                details={
                    'state_before': current_state,
                    'state_after': new_state,
                    'action_taken': True,
                    'reboot_recommended': True,
                },
            )

    # Command failed
    return CommandResult(
        status=CommandStatus.ERROR,
        output='No se pudo desactivar el Control Inteligente de Aplicaciones.',
        error=result.error or 'Error al modificar el registro.',
        details={
            'state_before': current_state,
            'action_taken': False,
            'command_error': result.error,
        },
    )


def open_smart_app_control_settings():
    """Open the Windows Security Smart App Control settings page."""
    return run_cmd(
        'start ms-settings:windowsdefender',
        shell=True,
        timeout=10,
        description='Abrir configuración de Control Inteligente de Aplicaciones',
    )


# ============================================================
# Internal helpers
# ============================================================

def _build_status_details(state, supported=False, changeable=False,
                          can_disable=False, can_enable=False,
                          raw_value=None, explanation='',
                          detection_method=''):
    """Build a structured details dict for SAC status."""
    return {
        'state': state,
        'state_label': SAC_STATE_LABELS_ES.get(state, 'Desconocido'),
        'supported': supported,
        'changeable': changeable,
        'can_disable': can_disable,
        'can_enable': can_enable,
        'admin_required': True,
        'reboot_required': state in ('on', 'evaluation'),
        'one_way_disable': True,
        'detection_method': detection_method,
        'raw_value': raw_value,
        'explanation': explanation,
    }


def _check_windows_version():
    """Check if the Windows version supports Smart App Control."""
    result = run_powershell(
        "[System.Environment]::OSVersion.Version.Build",
        timeout=10,
        description='Check Windows build number for SAC support',
    )

    if result.status == CommandStatus.NOT_APPLICABLE:
        return {'supported': False, 'reason': 'No es un sistema Windows.'}

    if not result.is_success:
        # Cannot determine, assume possibly supported
        return {'supported': True, 'reason': 'No se pudo verificar la versión.'}

    try:
        build = int(result.output.strip())
        # Smart App Control requires Windows 11 22H2 (build 22621) or later
        if build >= 22621:
            return {'supported': True, 'build': build}
        else:
            return {
                'supported': False,
                'build': build,
                'reason': (
                    f'Se requiere Windows 11 22H2 o posterior (build 22621+). '
                    f'Build actual: {build}.'
                ),
            }
    except (ValueError, AttributeError):
        # Can't parse, assume possibly supported
        return {'supported': True, 'reason': 'No se pudo determinar el número de build.'}


def _read_sac_registry():
    """Read Smart App Control state from registry."""
    result = run_powershell(
        f'(Get-ItemProperty -Path "{SAC_REGISTRY_PATH}" '
        f'-Name "{SAC_REGISTRY_VALUE}" '
        f'-ErrorAction Stop).{SAC_REGISTRY_VALUE}',
        timeout=10,
        description='Read Smart App Control registry value',
    )

    if result.status == CommandStatus.NOT_APPLICABLE:
        return {'success': False, 'reason': 'not_windows'}

    if result.is_success and result.output.strip():
        try:
            value = int(result.output.strip())
            return {'success': True, 'value': value}
        except (ValueError, TypeError):
            return {'success': False, 'reason': f'unexpected_value: {result.output.strip()}'}

    return {'success': False, 'reason': result.error or 'registry_key_not_found'}


def _fallback_detection():
    """Fallback detection using Get-MpComputerStatus if registry fails."""
    result = run_powershell(
        "try { "
        "$status = Get-MpComputerStatus -ErrorAction Stop; "
        "$status.SmartAppControlState "
        "} catch { 'not_available' }",
        timeout=15,
        description='Fallback SAC detection via Defender status',
    )

    if result.status == CommandStatus.NOT_APPLICABLE:
        return {'success': False}

    if result.is_success and result.output.strip():
        output = result.output.strip().lower()
        if output in ('on', 'enabled', '1'):
            return {'success': True, 'state': 'on'}
        elif output in ('evaluation', '2'):
            return {'success': True, 'state': 'evaluation'}
        elif output in ('off', 'disabled', '0'):
            return {'success': True, 'state': 'off'}
        elif output == 'not_available':
            return {'success': False}

    return {'success': False}


def _get_state_explanation(state):
    """Get a Spanish explanation for a given SAC state."""
    explanations = {
        'on': (
            'El Control Inteligente de Aplicaciones está activo. '
            'Bloquea aplicaciones no confiables o sin firma digital. '
            'Desactivarlo es irreversible sin reinstalar Windows.'
        ),
        'evaluation': (
            'El sistema está en modo de evaluación. Windows está aprendiendo '
            'los patrones de uso para decidir si activa la protección automáticamente. '
            'Si se desactiva, no se podrá volver a activar sin reinstalar Windows.'
        ),
        'off': (
            'El Control Inteligente de Aplicaciones está desactivado. '
            'Para reactivarlo se requiere una instalación limpia de Windows 11.'
        ),
        'not_available': (
            'Esta función no está disponible en este equipo. '
            'Puede deberse a la edición de Windows o a que el equipo no pasó '
            'por la experiencia inicial (OOBE) con la función habilitada.'
        ),
        'unsupported': (
            'Este equipo no cumple los requisitos. Se requiere Windows 11 '
            'versión 22H2 (build 22621) o posterior.'
        ),
        'unknown': (
            'No se pudo determinar el estado con certeza. '
            'Verifique manualmente en Seguridad de Windows > '
            'Control de aplicaciones y navegador.'
        ),
    }
    return explanations.get(state, '')

"""
System restore and operational safety module.

Handles: restore point creation, restore enablement, operation modes.
"""
import logging
from datetime import datetime

from services.command_runner import run_powershell, CommandStatus

logger = logging.getLogger('maintenance.restore')


def enable_system_restore(drive='C:'):
    """Enable System Restore on the specified drive."""
    return run_powershell(
        f'Enable-ComputerRestore -Drive "{drive}\\\\"',
        requires_admin=True,
        description=f'Enable System Restore on {drive}',
    )


def create_restore_point(description=None):
    """
    Create a system restore point.
    Should be called before any potentially destructive operation.
    """
    from services.command_runner import CommandResult

    if description is None:
        description = f'CleanCPU - {datetime.now().strftime("%Y-%m-%d %H:%M")}'

    # Check if System Restore service (srservice) is enabled
    svc_check = run_powershell(
        "(Get-Service srservice -ErrorAction SilentlyContinue).StartType",
        description='Check System Restore service status',
    )
    svc_start_type = (svc_check.output or '').strip().lower()

    if svc_start_type == 'disabled':
        # Attempt to enable the service
        logger.info("System Restore service is disabled, attempting to enable...")
        enable_svc = run_powershell(
            "Set-Service -Name srservice -StartupType Manual; "
            "Start-Service srservice",
            requires_admin=True,
            timeout=30,
            description='Enable System Restore service',
        )
        if enable_svc.status == CommandStatus.ERROR:
            logger.warning(f"Could not enable System Restore service: {enable_svc.error}")
            return CommandResult(
                status=CommandStatus.ERROR,
                error=(
                    'El servicio de Restauración del Sistema está deshabilitado en este equipo. '
                    'No se pudo habilitar automáticamente. Contacte al administrador del sistema '
                    'para habilitarlo.'
                ),
                details={'service_status': 'disabled', 'auto_enable_failed': True},
            )

    # Ensure System Restore is enabled on the drive
    enable_result = enable_system_restore()
    if enable_result.status == CommandStatus.ERROR:
        logger.warning(f"Could not enable System Restore: {enable_result.error}")

    result = run_powershell(
        f'Checkpoint-Computer -Description "{description}" -RestorePointType MODIFY_SETTINGS',
        requires_admin=True,
        timeout=120,
        description='Create system restore point',
    )

    # Handle service-disabled errors gracefully
    if result.status == CommandStatus.ERROR and 'deshabilitado' in (result.error or '').lower():
        result.error = (
            'El servicio de Restauración del Sistema está deshabilitado en este equipo. '
            'Contacte al administrador del sistema para habilitarlo.'
        )
        result.details['service_disabled'] = True

    return result


def get_restore_points():
    """List existing system restore points."""
    return run_powershell(
        'Get-ComputerRestorePoint | '
        'Select-Object SequenceNumber,Description,CreationTime,RestorePointType | '
        'Format-Table -AutoSize',
        requires_admin=True,
        description='List restore points',
    )


# Operation modes
class OperationMode:
    """Define operation modes for the maintenance tool."""

    DIAGNOSTIC = 'diagnostic'
    AUTOMATIC = 'automatic'
    ADVANCED = 'advanced'

    @staticmethod
    def get_mode_info(mode):
        modes = {
            'diagnostic': {
                'name': 'Diagnostic Only',
                'description': 'Only reads system information. No changes are made.',
                'allows_changes': False,
                'requires_confirmation': False,
            },
            'automatic': {
                'name': 'Automatic Maintenance',
                'description': 'Performs safe cleanup and basic maintenance. '
                               'Asks confirmation for anything beyond safe operations.',
                'allows_changes': True,
                'requires_confirmation': True,
            },
            'advanced': {
                'name': 'Advanced Technician',
                'description': 'Full access to all tools including risky operations. '
                               'Requires admin privileges. Still asks confirmation for '
                               'destructive actions.',
                'allows_changes': True,
                'requires_confirmation': True,
            },
        }
        return modes.get(mode, modes['diagnostic'])

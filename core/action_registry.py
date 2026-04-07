"""
Action Registry - Central catalog of all maintenance actions.

Every action exposed by CleanCPU is registered here with metadata:
- risk classification
- privilege requirements
- confirmation rules
- timeout policy
- reboot requirements
- restore point recommendations
"""
from enum import Enum
from typing import Optional, Callable


class RiskClass(str, Enum):
    """Risk classification for maintenance actions."""
    SAFE_READONLY = 'safe_readonly'        # Read-only diagnostics
    SAFE_MUTATION = 'safe_mutation'        # Temp cleanup, DNS flush, etc.
    DISRUPTIVE = 'disruptive'              # Explorer restart, IP release
    RISKY = 'risky'                        # Power changes, WU install, service restart
    DESTRUCTIVE = 'destructive'            # Winsock reset, IP stack reset, WU hard reset


class OperationMode(str, Enum):
    """Technician operation modes controlling which risk levels are permitted."""
    DIAGNOSTIC = 'diagnostic'              # Only SAFE_READONLY
    SAFE_MAINTENANCE = 'safe_maintenance'  # SAFE_READONLY + SAFE_MUTATION
    ADVANCED = 'advanced'                  # All except DESTRUCTIVE
    EXPERT = 'expert'                      # All actions (requires explicit opt-in)


# Which risk classes are allowed in each mode
MODE_ALLOWED_RISKS = {
    OperationMode.DIAGNOSTIC: {RiskClass.SAFE_READONLY},
    OperationMode.SAFE_MAINTENANCE: {RiskClass.SAFE_READONLY, RiskClass.SAFE_MUTATION},
    OperationMode.ADVANCED: {RiskClass.SAFE_READONLY, RiskClass.SAFE_MUTATION,
                             RiskClass.DISRUPTIVE, RiskClass.RISKY},
    OperationMode.EXPERT: {RiskClass.SAFE_READONLY, RiskClass.SAFE_MUTATION,
                           RiskClass.DISRUPTIVE, RiskClass.RISKY, RiskClass.DESTRUCTIVE},
}


class ActionDef:
    """Definition of a registered maintenance action."""

    __slots__ = (
        'action_id', 'name', 'module', 'risk_class', 'requires_admin',
        'requires_confirmation', 'confirm_message', 'default_timeout',
        'needs_restore_point', 'needs_reboot', 'is_long_running',
        'handler', 'description',
    )

    def __init__(
        self,
        action_id: str,
        name: str,
        module: str,
        risk_class: RiskClass,
        handler: Optional[Callable] = None,
        requires_admin: bool = False,
        requires_confirmation: bool = False,
        confirm_message: str = '',
        default_timeout: int = 120,
        needs_restore_point: bool = False,
        needs_reboot: bool = False,
        is_long_running: bool = False,
        description: str = '',
    ):
        self.action_id = action_id
        self.name = name
        self.module = module
        self.risk_class = risk_class
        self.handler = handler
        self.requires_admin = requires_admin
        self.requires_confirmation = requires_confirmation
        self.confirm_message = confirm_message
        self.default_timeout = default_timeout
        self.needs_restore_point = needs_restore_point
        self.needs_reboot = needs_reboot
        self.is_long_running = is_long_running
        self.description = description

    def to_dict(self):
        return {
            'action_id': self.action_id,
            'name': self.name,
            'module': self.module,
            'risk_class': self.risk_class.value,
            'requires_admin': self.requires_admin,
            'requires_confirmation': self.requires_confirmation,
            'confirm_message': self.confirm_message,
            'default_timeout': self.default_timeout,
            'needs_restore_point': self.needs_restore_point,
            'needs_reboot': self.needs_reboot,
            'is_long_running': self.is_long_running,
            'description': self.description,
        }


class ActionRegistry:
    """Central registry of all maintenance actions."""

    def __init__(self):
        self._actions: dict[str, ActionDef] = {}

    def register(self, action: ActionDef):
        """Register an action definition."""
        self._actions[action.action_id] = action
        return action

    def get(self, action_id: str) -> Optional[ActionDef]:
        """Get action definition by ID."""
        return self._actions.get(action_id)

    def list_all(self) -> list[ActionDef]:
        """List all registered actions."""
        return list(self._actions.values())

    def list_by_module(self, module: str) -> list[ActionDef]:
        """List actions by module."""
        return [a for a in self._actions.values() if a.module == module]

    def list_by_risk(self, risk_class: RiskClass) -> list[ActionDef]:
        """List actions by risk class."""
        return [a for a in self._actions.values() if a.risk_class == risk_class]

    def list_allowed(self, mode: OperationMode) -> list[ActionDef]:
        """List actions allowed in the given operation mode."""
        allowed_risks = MODE_ALLOWED_RISKS[mode]
        return [a for a in self._actions.values() if a.risk_class in allowed_risks]

    def to_dict(self):
        """Export the full registry as a dict."""
        return {aid: a.to_dict() for aid, a in self._actions.items()}


# Global registry instance
registry = ActionRegistry()


def _register_all_actions():
    """Register all known actions with their metadata."""

    # === DIAGNOSTICS (SAFE_READONLY) ===
    _diag_actions = [
        ('diag.system_overview', 'System Overview', 'diagnostics'),
        ('diag.ram', 'RAM Details', 'diagnostics'),
        ('diag.disks', 'Disk Details', 'diagnostics'),
        ('diag.smart', 'SMART Status', 'diagnostics'),
        ('diag.trim', 'TRIM Status', 'diagnostics'),
        ('diag.top_processes', 'Top Processes', 'diagnostics'),
        ('diag.services', 'Critical Services', 'diagnostics'),
        ('diag.startup', 'Startup Programs', 'diagnostics'),
        ('diag.remote_access', 'Remote Access Detection', 'diagnostics'),
        ('diag.windows_version', 'Windows Version', 'diagnostics'),
        ('diag.license', 'Windows License', 'diagnostics'),
        ('diag.time_sync', 'Time Sync Status', 'diagnostics'),
        ('diag.routes', 'Routing Table', 'diagnostics'),
        ('diag.temperature', 'CPU Temperature', 'diagnostics'),
        ('diag.drivers', 'Installed Drivers', 'drivers'),
        ('diag.problem_devices', 'Problem Devices', 'drivers'),
        ('diag.display_drivers', 'GPU/Display Drivers', 'drivers'),
        ('diag.driver_errors', 'Driver Errors', 'drivers'),
        ('diag.driver_overview', 'Driver Overview', 'drivers'),
        ('diag.network_adapters', 'Network Adapters', 'network'),
        ('diag.ip_config', 'IP Configuration', 'network'),
        ('diag.tcp_global', 'TCP Global Settings', 'network'),
        ('diag.proxy', 'WinHTTP Proxy', 'network'),
        ('diag.shared_folders', 'Shared Folders', 'network'),
        ('diag.smb_sessions', 'SMB Sessions', 'network'),
        ('diag.network_services', 'Network Services', 'network'),
        ('diag.wu_services', 'WU Services Status', 'update'),
        ('diag.defender_status', 'Defender Status', 'security'),
        ('diag.defender_config', 'Defender Configuration', 'security'),
        ('diag.third_party_av', 'Third-Party Antivirus', 'security'),
        ('diag.security_overview', 'Security Overview', 'security'),
        ('diag.smart_app_control', 'Smart App Control Status', 'security'),
        ('diag.active_power_plan', 'Active Power Plan', 'power'),
        ('diag.list_power_plans', 'All Power Plans', 'power'),
        ('diag.power_plan_details', 'Power Plan Details', 'power'),
        ('diag.processor_info', 'Processor Power Info', 'power'),
        ('diag.restore_points', 'Restore Points List', 'advanced'),
        ('diag.gpu_drivers', 'GPU Drivers Info', 'advanced'),
        ('diag.display_events', 'Display Events', 'advanced'),
        ('diag.display_diagnostics', 'Display Diagnostics', 'advanced'),
        ('diag.psr_check', 'Panel Self-Refresh Check', 'advanced'),
        ('diag.fragmentation', 'Disk Fragmentation Analysis', 'cleanup'),
    ]
    for aid, name, module in _diag_actions:
        registry.register(ActionDef(
            action_id=aid, name=name, module=module,
            risk_class=RiskClass.SAFE_READONLY,
        ))

    # === SAFE_MUTATION ===
    for aid, name, module, desc, timeout in [
        ('cleanup.user_temp', 'Clean User Temp', 'cleanup', 'Delete user temporary files', 60),
        ('cleanup.windows_temp', 'Clean System Temp', 'cleanup', 'Delete Windows temporary files', 60),
        ('cleanup.recycle_bin', 'Empty Recycle Bin', 'cleanup', 'Empty the Recycle Bin', 60),
        ('cleanup.dns_cache', 'Flush DNS Cache', 'cleanup', 'Flush local DNS resolver cache', 30),
        ('cleanup.inet_cache', 'Clean Internet Cache', 'cleanup', 'Delete browser cache files', 60),
        ('cleanup.software_dist', 'Clean WU Cache', 'cleanup', 'Delete Windows Update download cache', 60),
        ('cleanup.prefetch', 'Clean Prefetch', 'cleanup', 'Clear Prefetch folder', 30),
        ('cleanup.store_cache', 'Reset Store Cache', 'cleanup', 'Reset Microsoft Store cache', 60),
        ('cleanup.scan_duplicates', 'Scan Duplicates', 'cleanup', 'Scan Downloads for duplicates (read-only)', 120),
        ('network.flush_dns', 'Flush DNS', 'network', 'Flush DNS resolver cache', 30),
        ('network.purge_netbios', 'Purge NetBIOS Cache', 'network', 'Purge NetBIOS name cache', 30),
        ('network.renew_ip', 'Renew IP', 'network', 'Renew DHCP IP address', 30),
        ('network.set_autotuning', 'Set TCP Autotuning', 'network', 'Set autotuning to normal', 30),
        ('network.test_connectivity', 'Test Connectivity', 'network', 'Test network connection', 30),
        ('security.update_signatures', 'Update Defender Signatures', 'security', 'Download latest definitions', 120),
        ('security.set_cpu_load', 'Set Defender CPU Load', 'security', 'Adjust Defender scan CPU usage', 30),
        ('security.quick_scan', 'Defender Quick Scan', 'security', 'Run a quick malware scan', 600),
        ('update.scan', 'Scan for Updates', 'update', 'Check for Windows Updates', 120),
        ('update.download', 'Download Updates', 'update', 'Download pending updates', 300),
        ('update.open_settings', 'Open Windows Update', 'update', 'Open WU settings page', 10),
        ('security.open_sac_settings', 'Open SAC Settings', 'security', 'Open Windows Security Smart App Control page', 10),
    ]:
        registry.register(ActionDef(
            action_id=aid, name=name, module=module,
            risk_class=RiskClass.SAFE_MUTATION,
            description=desc, default_timeout=timeout,
        ))

    # === DISRUPTIVE ===
    for aid, name, module, desc, timeout, confirm_msg in [
        ('cleanup.restart_explorer', 'Restart Explorer', 'cleanup',
         'Restart Windows Explorer shell', 30,
         'The taskbar will briefly disappear. Continue?'),
        ('cleanup.cleanmgr', 'Disk Cleanup', 'cleanup',
         'Run Windows Disk Cleanup utility', 300, ''),
        ('cleanup.retrim', 'ReTrim SSD', 'cleanup',
         'Run TRIM optimization on SSD', 120, ''),
        ('cleanup.defrag', 'Defragment HDD', 'cleanup',
         'Defragment hard disk drive', 600,
         'This only runs if an HDD is detected. Continue?'),
        ('cleanup.component_cleanup', 'DISM Component Cleanup', 'cleanup',
         'Remove obsolete Windows components', 600, ''),
        ('network.release_ip', 'Release IP', 'network',
         'Release current DHCP address (brief disconnect)', 30,
         'You may briefly lose network connectivity. Continue?'),
        ('network.clear_smb', 'Clear SMB Sessions', 'network',
         'Remove mapped drives and NetBIOS cache', 30,
         'All mapped network drives will be disconnected. Continue?'),
        ('power.set_balanced', 'Set Balanced Mode', 'power',
         'Switch to Balanced power plan', 10, ''),
        ('repair.component_cleanup', 'DISM Component Cleanup (Repair)', 'repair',
         'Remove obsolete Windows components via repair module', 600, ''),
        ('advanced.create_restore_point', 'Create Restore Point', 'advanced',
         'Create a system restore point', 60, ''),
    ]:
        registry.register(ActionDef(
            action_id=aid, name=name, module=module,
            risk_class=RiskClass.DISRUPTIVE,
            requires_admin=True,
            requires_confirmation=bool(confirm_msg),
            confirm_message=confirm_msg,
            default_timeout=timeout,
            description=desc,
        ))

    # === RISKY ===
    for aid, name, module, desc, timeout, confirm_msg, restore_pt, reboot, long_run in [
        ('repair.sfc', 'SFC /scannow', 'repair',
         'Verify and repair system files', 900,
         'SFC scan takes 5-15 minutes. Continue?', False, False, True),
        ('repair.dism_check', 'DISM CheckHealth', 'repair',
         'Quick component integrity check', 120, '', False, False, False),
        ('repair.dism_scan', 'DISM ScanHealth', 'repair',
         'Deep component scan', 600,
         'Deep scan may take 10+ minutes. Continue?', False, False, True),
        ('repair.dism_restore', 'DISM RestoreHealth', 'repair',
         'Repair component store from Windows Update', 1800,
         'RestoreHealth may take 30+ minutes and download files. Continue?', True, False, True),
        ('repair.chkdsk_scan', 'CHKDSK Online Scan', 'repair',
         'Online disk check without reboot', 600,
         'Online CHKDSK scan may take several minutes. Continue?', False, False, True),
        ('repair.winsat', 'WinSAT Disk Benchmark', 'repair',
         'Windows System Assessment Tool for disk', 120, '', False, False, False),
        ('repair.full_sequence', 'Full Repair Sequence', 'repair',
         'SFC + DISM complete sequence', 3600,
         'This runs SFC, DISM CheckHealth, ScanHealth, RestoreHealth and ComponentCleanup. '
         'It may take 30+ minutes. Continue?', True, False, True),
        ('security.full_scan', 'Defender Full Scan', 'security',
         'Full system malware scan', 7200,
         'A full scan can take 2+ hours and will use significant CPU. Continue?', False, False, True),
        ('update.install', 'Install Updates', 'update',
         'Install downloaded Windows Updates', 600,
         'May require a reboot. Save all work. Continue?', True, True, True),
        ('update.resync_time', 'Sync Time', 'update',
         'Resynchronize system clock', 30, '', False, False, False),
        ('power.set_high_performance', 'Set High Performance', 'power',
         'Switch to High Performance power plan', 10,
         'This increases power consumption and fan speed. Continue?', False, False, False),
        ('power.battery_report', 'Battery Report', 'power',
         'Generate battery health report', 60, '', False, False, False),
        ('power.enable_hibernation', 'Enable Hibernation', 'power',
         'Re-enable hibernate option', 10, '', False, False, False),
        ('network.repair', 'Network Repair Sequence', 'network',
         'Flush DNS + Release/Renew IP + Autotuning', 60,
         'Brief disconnection possible during network repair. Continue?', False, False, False),
        ('network.service_startup', 'Cambiar inicio de servicio de red', 'network',
         'Change startup type (Manual/Automatic) of a managed network service', 30,
         'Esto cambiará el tipo de inicio del servicio seleccionado. '
         'Puede afectar la conectividad de red. ¿Continuar?', False, False, False),
        ('network.enable_adapter', 'Habilitar adaptador de red', 'network',
         'Habilitar un adaptador de red desactivado', 30,
         'Esto habilitará el adaptador de red seleccionado. ¿Continuar?',
         False, False, False),
        ('network.disable_adapter', 'Deshabilitar adaptador de red', 'network',
         'Deshabilitar un adaptador de red activo', 30,
         'ADVERTENCIA: Deshabilitar este adaptador interrumpirá la conectividad de red '
         'a través de él. ¿Continuar?',
         False, False, False),
    ]:
        registry.register(ActionDef(
            action_id=aid, name=name, module=module,
            risk_class=RiskClass.RISKY,
            requires_admin=True,
            requires_confirmation=bool(confirm_msg),
            confirm_message=confirm_msg,
            default_timeout=timeout,
            needs_restore_point=restore_pt,
            needs_reboot=reboot,
            is_long_running=long_run,
            description=desc,
        ))

    # === DESTRUCTIVE ===
    for aid, name, module, desc, timeout, confirm_msg, reboot in [
        ('update.hard_reset', 'Hard Reset Windows Update', 'update',
         'Stop WU services and rename SoftwareDistribution/catroot2', 120,
         'WARNING: This is the nuclear option for broken Windows Update. '
         'Only use when all other methods have failed. Continue?', True),
        ('network.reset_ip_stack', 'Reset TCP/IP Stack', 'network',
         'Reset entire TCP/IP networking stack', 30,
         'WARNING: This resets the TCP/IP stack. You may lose connectivity. '
         'A reboot is REQUIRED afterward. Continue?', True),
        ('network.reset_winsock', 'Reset Winsock', 'network',
         'Reset Winsock catalog', 30,
         'WARNING: This resets the Winsock catalog. A reboot is REQUIRED afterward. '
         'Continue?', True),
        ('repair.chkdsk_schedule', 'Schedule Full CHKDSK', 'repair',
         'Schedule full disk check on next reboot', 30,
         'This schedules a full CHKDSK on next reboot (1-3 hours). Continue?', True),
        ('repair.memory_diagnostic', 'Memory Diagnostic', 'repair',
         'Schedule memory diagnostic test on next reboot', 10,
         'The memory test runs on next reboot. Continue?', True),
        ('power.disable_hibernation', 'Disable Hibernation', 'power',
         'Delete hiberfil.sys and disable hibernate', 10,
         'This deletes hiberfil.sys and frees space equal to your RAM. '
         'You will no longer be able to hibernate. Continue?', False),
        ('security.disable_sac', 'Disable Smart App Control', 'security',
         'Disable Windows Smart App Control (irreversible without clean install)', 30,
         'ADVERTENCIA: Desactivar el Control Inteligente de Aplicaciones es una '
         'acción NO REVERSIBLE. Una vez desactivado, solo se puede reactivar '
         'reinstalando Windows 11 desde cero. ¿Desea continuar?', True),
    ]:
        registry.register(ActionDef(
            action_id=aid, name=name, module=module,
            risk_class=RiskClass.DESTRUCTIVE,
            requires_admin=True,
            requires_confirmation=True,
            confirm_message=confirm_msg,
            default_timeout=timeout,
            needs_restore_point=True,
            needs_reboot=reboot,
            description=desc,
        ))


def _register_office_actions():
    """Register Phase 4 Office actions."""

    # SAFE_READONLY — diagnostics, no side effects
    for aid, name, desc in [
        ('office.inspect', 'Inspeccionar licencia Office',
         'Consultar estado de activacion de Office via ospp.vbs'),
        ('office.paqueteria', 'Listar programas instalados',
         'Inventario de software instalado (registro de Windows)'),
    ]:
        registry.register(ActionDef(
            action_id=aid, name=name, module='office',
            risk_class=RiskClass.SAFE_READONLY,
            description=desc,
        ))

    # SAFE_MUTATION — GUI launchers; low risk, no data destruction
    for aid, name, desc, timeout in [
        ('office.safe_mode', 'Outlook modo seguro',
         'Iniciar Outlook con /safe (sin complementos)', 10),
        ('office.configure_mail', 'Configurar correo',
         'Abrir panel de perfiles de Outlook (mlcfg32.cpl)', 10),
        ('office.scanpst', 'Reparar PST (SCANPST)',
         'Iniciar herramienta de reparacion de archivos PST/OST', 10),
    ]:
        registry.register(ActionDef(
            action_id=aid, name=name, module='office',
            risk_class=RiskClass.SAFE_MUTATION,
            description=desc, default_timeout=timeout,
        ))

    # RISKY — require confirmation; affect running services or download data
    for aid, name, desc, timeout, confirm_msg, needs_admin in [
        ('office.repair_quick', 'Reparacion rapida Office',
         'Ejecutar reparacion rapida de Office (ClickToRun, archivos locales)', 300,
         'La reparacion rapida corregira archivos locales de Office. '
         'Office debe estar cerrado. Continuar?', True),
        ('office.repair_online', 'Reparacion en linea Office',
         'Ejecutar reparacion en linea de Office (descarga todos los archivos)', 1800,
         'La reparacion en linea descarga todos los archivos de Office desde Microsoft. '
         'Requiere internet y puede tardar 30+ minutos. Office debe estar cerrado. Continuar?', True),
        ('office.rebuild_index', 'Reconstruir indice de busqueda',
         'Detener Windows Search, borrar indice y reconstruir (afecta toda la busqueda)', 60,
         'Se detendra temporalmente Windows Search y se eliminara el indice actual. '
         'Afecta toda la busqueda del sistema (no solo Outlook). Continuar?', True),
    ]:
        registry.register(ActionDef(
            action_id=aid, name=name, module='office',
            risk_class=RiskClass.RISKY,
            requires_admin=needs_admin,
            requires_confirmation=True,
            confirm_message=confirm_msg,
            description=desc, default_timeout=timeout,
        ))


def _register_startup_actions():
    """Register Wave 2 Phase 1 startup management actions."""

    # RISKY — persistent system-level change affecting every boot
    for aid, name, desc, confirm_msg in [
        (
            'startup.disable_item',
            'Deshabilitar inicio automático',
            'Deshabilitar un programa del inicio automático de Windows',
            'Esto deshabilitará el inicio automático de este programa. '
            'No se iniciará al arrancar Windows. ¿Continuar?',
        ),
        (
            'startup.enable_item',
            'Habilitar inicio automático',
            'Volver a habilitar un programa del inicio automático de Windows',
            'Esto habilitará el inicio automático de este programa. '
            'Se iniciará automáticamente al arrancar Windows. ¿Continuar?',
        ),
    ]:
        registry.register(ActionDef(
            action_id=aid,
            name=name,
            module='startup',
            risk_class=RiskClass.RISKY,
            requires_admin=True,
            requires_confirmation=True,
            confirm_message=confirm_msg,
            default_timeout=30,
            description=desc,
        ))


def _register_sharing_actions():
    """Register Wave 2 Phase 3 sharing and NetBIOS actions."""
    for aid, name, desc, timeout, confirm_msg in [
        (
            'sharing.enable_network_discovery',
            'Habilitar detección de redes',
            'Habilitar el grupo de reglas de firewall para detección de redes',
            30,
            'Esto habilitará la detección de redes en el firewall de Windows. '
            'Otros equipos podrán descubrir este equipo en la red. ¿Continuar?',
        ),
        (
            'sharing.disable_network_discovery',
            'Deshabilitar detección de redes',
            'Deshabilitar el grupo de reglas de firewall para detección de redes',
            30,
            'Esto deshabilitará la detección de redes. '
            'Este equipo no será visible para otros en la red. ¿Continuar?',
        ),
        (
            'sharing.set_netbios',
            'Cambiar modo NetBIOS',
            'Cambiar la configuración de NetBIOS sobre TCP/IP de un adaptador',
            30,
            'Esto cambiará la configuración de NetBIOS del adaptador seleccionado. '
            'Puede afectar el acceso a recursos de red por nombre NetBIOS. ¿Continuar?',
        ),
    ]:
        registry.register(ActionDef(
            action_id=aid,
            name=name,
            module='sharing',
            risk_class=RiskClass.RISKY,
            requires_admin=True,
            requires_confirmation=True,
            confirm_message=confirm_msg,
            default_timeout=timeout,
            description=desc,
        ))


def _register_windows_features_actions():
    """Register Wave 2 Phase 4 shared-folder troubleshooting actions."""
    for aid, name, desc, timeout in [
        (
            'windows_features.test_unc',
            'Probar conectividad TCP 445 a ruta UNC',
            'Test-NetConnection TCP 445 al servidor de una ruta UNC (sólo lectura)',
            30,
        ),
        (
            'windows_features.open_network_path',
            'Abrir ruta de red en Explorador',
            'Lanzar Windows Explorer con una ruta UNC (sin cambios de estado)',
            10,
        ),
    ]:
        registry.register(ActionDef(
            action_id=aid,
            name=name,
            module='windows_features',
            risk_class=RiskClass.SAFE_MUTATION,
            requires_admin=False,
            requires_confirmation=False,
            default_timeout=timeout,
            description=desc,
        ))


_register_all_actions()
_register_office_actions()
_register_startup_actions()
_register_sharing_actions()
_register_windows_features_actions()

"""
Antivirus and security module.

Handles: Microsoft Defender scans, configuration, MRT,
third-party tool detection.
"""
import logging
import os
import sys

from services.command_runner import run_cmd, run_powershell, CommandStatus, CommandResult

logger = logging.getLogger('maintenance.antivirus')


def _get_mpcmdrun_path():
    """Find MpCmdRun.exe path."""
    default = r'C:\Program Files\Windows Defender\MpCmdRun.exe'
    if os.path.exists(default):
        return default
    alt = r'C:\ProgramData\Microsoft\Windows Defender\Platform'
    if os.path.exists(alt):
        for folder in sorted(os.listdir(alt), reverse=True):
            candidate = os.path.join(alt, folder, 'MpCmdRun.exe')
            if os.path.exists(candidate):
                return candidate
    return default


def defender_quick_scan():
    """Run Microsoft Defender quick scan."""
    mpcmd = _get_mpcmdrun_path()
    return run_cmd(
        f'"{mpcmd}" -Scan -ScanType 1',
        timeout=600,
        description='Defender quick scan',
    )


def defender_full_scan():
    """Run Microsoft Defender full scan. This takes a very long time."""
    mpcmd = _get_mpcmdrun_path()
    return run_cmd(
        f'"{mpcmd}" -Scan -ScanType 2',
        timeout=7200,
        description='Defender full scan',
    )


def get_defender_config():
    """Get Microsoft Defender configuration."""
    return run_powershell(
        'Get-MpPreference | Select-Object DisableRealtimeMonitoring,'
        'ScanAvgCPULoadFactor,ExclusionPath,ExclusionExtension,'
        'SignatureLastUpdated | Format-List',
        description='Get Defender configuration',
    )


def get_defender_status():
    """Get Microsoft Defender current status."""
    return run_powershell(
        'Get-MpComputerStatus | Select-Object AMRunningMode,AntivirusEnabled,'
        'AntispywareEnabled,RealTimeProtectionEnabled,IoavProtectionEnabled,'
        'NISEnabled,QuickScanAge,FullScanAge,AntivirusSignatureLastUpdated | '
        'Format-List',
        description='Get Defender status',
    )


def set_defender_cpu_load(factor=50):
    """
    Set Defender scan CPU load factor.
    Valid range: 5-100. Default is 50.
    Lower values = less impact during scans but slower scans.
    """
    if not isinstance(factor, int) or not (5 <= factor <= 100):
        return CommandResult(
            status=CommandStatus.ERROR,
            error=f'Invalid CPU load factor: {factor}. Must be 5-100.',
        )
    return run_powershell(
        f'Set-MpPreference -ScanAvgCPULoadFactor {factor}',
        requires_admin=True,
        description=f'Set Defender CPU load to {factor}%',
    )


def update_defender_signatures():
    """Update Microsoft Defender virus definitions."""
    mpcmd = _get_mpcmdrun_path()
    return run_cmd(
        f'"{mpcmd}" -SignatureUpdate',
        timeout=120,
        description='Update Defender signatures',
    )


def open_mrt():
    """Open Microsoft Malicious Software Removal Tool."""
    return run_cmd(
        'mrt.exe',
        timeout=10,
        description='Open MRT',
    )


def detect_third_party_antivirus():
    """Detect installed third-party antivirus/security software."""
    known_tools = {
        'Malwarebytes': ['mbam.exe', 'mbamservice.exe', 'MBAMService'],
        'Norton': ['norton.exe', 'NortonSecurity.exe'],
        'Kaspersky': ['avp.exe', 'avpui.exe'],
        'Bitdefender': ['bdagent.exe', 'bdservicehost.exe'],
        'ESET': ['egui.exe', 'ekrn.exe'],
        'Avast': ['AvastSvc.exe', 'AvastUI.exe'],
        'AVG': ['avgui.exe', 'avgsvc.exe'],
        'McAfee': ['mcshield.exe', 'mfemms.exe'],
    }

    result = run_powershell(
        "Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct "
        "-ErrorAction SilentlyContinue | "
        "Select-Object displayName,pathToSignedProductExe,productState | Format-List",
        description='Detect third-party antivirus',
    )
    result.details['known_tools'] = list(known_tools.keys())
    return result


def get_security_overview():
    """Get a complete security overview."""
    results = {}
    results['defender_status'] = get_defender_status().to_dict()
    results['defender_config'] = get_defender_config().to_dict()
    results['third_party'] = detect_third_party_antivirus().to_dict()
    return results

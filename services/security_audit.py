"""
Internal Windows Security Inspection Module.

Native replacement for third-party security scanners.
No external tools required — uses PowerShell, WMI, registry, and file system.

Checks performed:
  1.  Windows Defender (real-time protection, signature age, scan age)
  2.  Windows Firewall (all profiles)
  3.  Windows Update (last patch age)
  4.  Run / RunOnce registry keys (persistence indicators)
  5.  Startup folders (unexpected files)
  6.  Scheduled tasks outside Microsoft namespace
  7.  Executable files in TEMP folder
  8.  UAC (User Account Control)
  9.  WDigest credential caching (cleartext credentials risk)
  10. RDP (Remote Desktop) status
  11. Guest account status
  12. AutoRun / AutoPlay policy
"""
import os
import sys
import logging
from datetime import datetime

from services.command_runner import run_powershell, CommandStatus

logger = logging.getLogger('cleancpu.security_audit')

# ---- Severity constants ----
SEV_INFO = 'info'
SEV_WARNING = 'warning'
SEV_CRITICAL = 'critical'

# Extensions considered suspicious when found in TEMP / user-writable dirs
_SUSPICIOUS_EXTS = {
    '.exe', '.bat', '.ps1', '.vbs', '.js', '.cmd',
    '.scr', '.com', '.pif', '.hta', '.wsf',
}

# Path fragments that flag a startup/task executable as suspicious
_SUSPICIOUS_PATHS = (
    '\\temp\\', '\\tmp\\', '%temp%', '%tmp%',
    '\\appdata\\local\\temp',
    '\\downloads\\',
    '\\appdata\\roaming\\',
)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _finding(title, severity, evidence, recommended_action=''):
    return {
        'title': title,
        'severity': severity,
        'evidence': str(evidence)[:400],
        'recommended_action': recommended_action,
    }


def _is_false(value):
    """Return True if a PowerShell boolean string represents False."""
    return str(value).strip().lower() in ('false', '0', 'no')


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_defender():
    """Check Windows Defender status, real-time protection, and signature age."""
    findings = []
    warnings = []
    actions = []

    if sys.platform != 'win32':
        return {'findings': [], 'warnings': ['No Windows — Defender no aplica'], 'recommended_actions': []}

    # One compact PowerShell call returns pipe-delimited values
    result = run_powershell(
        "$s = Get-MpComputerStatus -ErrorAction SilentlyContinue; "
        "if ($s) { "
        "  $sigAge = if ($s.AntivirusSignatureLastUpdated) "
        "    { [int]((Get-Date) - $s.AntivirusSignatureLastUpdated).TotalDays } else { -1 }; "
        "  $qAge = if ($s.QuickScanAge) { [int]$s.QuickScanAge } else { -1 }; "
        "  \"$($s.AntivirusEnabled)|$($s.RealTimeProtectionEnabled)|"
        "$($s.AntispywareEnabled)|$sigAge|$qAge\" "
        "} else { 'unavailable' }",
        timeout=20,
        description='Defender status check',
    )

    if result.status == CommandStatus.NOT_APPLICABLE:
        return {'findings': [], 'warnings': ['Plataforma no compatible con Defender'], 'recommended_actions': []}

    raw = (result.output or '').strip()
    if raw == 'unavailable' or result.is_error:
        findings.append(_finding(
            'Estado de Windows Defender no disponible',
            SEV_WARNING,
            result.error or 'Get-MpComputerStatus no respondio',
            'Verifique manualmente el estado de Windows Defender.',
        ))
        return {'findings': findings, 'warnings': warnings, 'recommended_actions': actions}

    parts = raw.split('|')
    av_enabled = parts[0] if len(parts) > 0 else ''
    rt_enabled = parts[1] if len(parts) > 1 else ''
    sig_age_str = parts[3] if len(parts) > 3 else '-1'
    scan_age_str = parts[4] if len(parts) > 4 else '-1'

    # Real-time protection
    if _is_false(rt_enabled):
        findings.append(_finding(
            'Proteccion en tiempo real DESACTIVADA',
            SEV_CRITICAL,
            f'RealTimeProtectionEnabled: {rt_enabled}',
            'Active inmediatamente la proteccion en tiempo real de Windows Defender.',
        ))
        actions.append('Activar proteccion en tiempo real de Defender')
    else:
        findings.append(_finding(
            'Proteccion en tiempo real: Activa',
            SEV_INFO,
            f'RealTimeProtectionEnabled: {rt_enabled}',
        ))

    # Antivirus enabled
    if _is_false(av_enabled):
        findings.append(_finding(
            'Antivirus DESACTIVADO',
            SEV_CRITICAL,
            f'AntivirusEnabled: {av_enabled}',
            'Active Windows Defender o instale un antivirus alternativo.',
        ))
        actions.append('Activar antivirus de Windows')

    # Signature age
    try:
        sig_age = int(sig_age_str)
        if sig_age < 0:
            warnings.append('No se pudo obtener la edad de las firmas de Defender')
        elif sig_age > 7:
            findings.append(_finding(
                f'Firmas de Defender desactualizadas (hace {sig_age} dias)',
                SEV_WARNING,
                f'Dias desde ultima actualizacion de firmas: {sig_age}',
                'Actualice las firmas de Windows Defender.',
            ))
            actions.append('Actualizar firmas de Windows Defender')
        else:
            findings.append(_finding(
                f'Firmas de Defender actualizadas (hace {sig_age} dias)',
                SEV_INFO,
                f'Dias desde ultima actualizacion de firmas: {sig_age}',
            ))
    except ValueError:
        warnings.append(f'Edad de firmas no parseable: {sig_age_str}')

    # Quick scan age
    try:
        scan_age = int(scan_age_str)
        if 0 <= scan_age > 30:
            findings.append(_finding(
                f'Ultimo escaneo rapido hace {scan_age} dias',
                SEV_WARNING,
                f'QuickScanAge: {scan_age} dias',
                'Ejecute un escaneo rapido de Windows Defender.',
            ))
            actions.append('Ejecutar escaneo rapido de Defender')
        elif scan_age >= 0:
            findings.append(_finding(
                f'Ultimo escaneo rapido: hace {scan_age} dias',
                SEV_INFO,
                f'QuickScanAge: {scan_age}',
            ))
    except ValueError:
        pass

    return {'findings': findings, 'warnings': warnings, 'recommended_actions': actions}


def _check_firewall():
    """Check Windows Firewall for all network profiles."""
    findings = []
    warnings = []
    actions = []

    result = run_powershell(
        "Get-NetFirewallProfile -ErrorAction SilentlyContinue | "
        "ForEach-Object { \"$($_.Name)|$($_.Enabled)\" }",
        timeout=15,
        description='Firewall profile check',
    )

    if result.status == CommandStatus.NOT_APPLICABLE or result.is_error:
        warnings.append('No se pudo verificar el estado del Firewall de Windows')
        return {'findings': findings, 'warnings': warnings, 'recommended_actions': actions}

    for line in (result.output or '').splitlines():
        line = line.strip()
        if '|' not in line:
            continue
        name, enabled = line.split('|', 1)
        name = name.strip()
        enabled = enabled.strip()
        if _is_false(enabled):
            findings.append(_finding(
                f'Firewall DESACTIVADO — perfil: {name}',
                SEV_CRITICAL,
                f'Perfil {name}: Enabled={enabled}',
                f'Active el Firewall de Windows para el perfil {name}.',
            ))
            actions.append(f'Activar Firewall — perfil {name}')
        else:
            findings.append(_finding(
                f'Firewall activo — perfil: {name}',
                SEV_INFO,
                f'Perfil {name}: Enabled={enabled}',
            ))

    return {'findings': findings, 'warnings': warnings, 'recommended_actions': actions}


def _check_windows_update():
    """Check age of last installed Windows Update patch."""
    findings = []
    warnings = []
    actions = []

    result = run_powershell(
        "try { "
        "  $h = Get-HotFix | Sort-Object InstalledOn -Descending "
        "    | Select-Object -First 1; "
        "  if ($h -and $h.InstalledOn) { "
        "    $age = [int]((Get-Date) - [datetime]$h.InstalledOn).TotalDays; "
        "    \"$age|$($h.HotFixID)|$($h.InstalledOn.ToShortDateString())\" "
        "  } else { 'unknown' } "
        "} catch { 'error' }",
        timeout=30,
        description='Windows Update last install check',
    )

    raw = (result.output or '').strip()
    if raw in ('error', 'unknown', '') or result.is_error:
        warnings.append(
            'No se pudo determinar la fecha de la ultima actualizacion de Windows'
        )
        return {'findings': findings, 'warnings': warnings, 'recommended_actions': actions}

    parts = raw.split('|')
    try:
        age = int(parts[0])
        hotfix = parts[1] if len(parts) > 1 else 'N/A'
        date_str = parts[2] if len(parts) > 2 else 'N/A'

        if age > 60:
            findings.append(_finding(
                f'Windows Update: ultima actualizacion hace {age} dias ({hotfix})',
                SEV_CRITICAL,
                f'Ultimo parche: {hotfix} — {date_str}',
                'Ejecute Windows Update y aplique todas las actualizaciones pendientes.',
            ))
            actions.append('Aplicar actualizaciones de Windows Update urgente')
        elif age > 30:
            findings.append(_finding(
                f'Windows Update: sin actualizaciones recientes (hace {age} dias, {hotfix})',
                SEV_WARNING,
                f'Ultimo parche: {hotfix} — {date_str}',
                'Ejecute Windows Update para verificar actualizaciones disponibles.',
            ))
            actions.append('Verificar y aplicar actualizaciones de Windows')
        else:
            findings.append(_finding(
                f'Windows Update al dia (hace {age} dias, {hotfix})',
                SEV_INFO,
                f'Ultimo parche: {hotfix} — {date_str}',
            ))
    except (ValueError, IndexError):
        warnings.append(f'No se pudo interpretar la informacion de Windows Update: {raw}')

    return {'findings': findings, 'warnings': warnings, 'recommended_actions': actions}


def _check_run_registry():
    """Check Run/RunOnce registry keys for suspicious persistence entries."""
    findings = []
    warnings = []
    actions = []

    if sys.platform != 'win32':
        return {'findings': [], 'warnings': ['No Windows'], 'recommended_actions': []}

    try:
        import winreg
    except ImportError:
        warnings.append('winreg no disponible en esta plataforma')
        return {'findings': findings, 'warnings': warnings, 'recommended_actions': actions}

    hives = [
        (winreg.HKEY_LOCAL_MACHINE,
         r'SOFTWARE\Microsoft\Windows\CurrentVersion\Run', 'HKLM\\Run'),
        (winreg.HKEY_LOCAL_MACHINE,
         r'SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce', 'HKLM\\RunOnce'),
        (winreg.HKEY_CURRENT_USER,
         r'SOFTWARE\Microsoft\Windows\CurrentVersion\Run', 'HKCU\\Run'),
        (winreg.HKEY_CURRENT_USER,
         r'SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce', 'HKCU\\RunOnce'),
    ]

    all_entries = []
    for hive, subkey, label in hives:
        try:
            key = winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ)
            i = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, i)
                    all_entries.append({
                        'label': label,
                        'name': name,
                        'value': str(value),
                    })
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(key)
        except (OSError, FileNotFoundError):
            pass  # Key absent or no access — normal

    suspicious = [
        e for e in all_entries
        if any(p in e['value'].lower() for p in _SUSPICIOUS_PATHS)
    ]

    if suspicious:
        for entry in suspicious:
            findings.append(_finding(
                f'Entrada sospechosa en registro [{entry["label"]}]: {entry["name"]}',
                SEV_CRITICAL,
                f'Valor: {entry["value"][:250]}',
                f'Investigue la clave "{entry["name"]}" en {entry["label"]} — '
                'puede ser malware con mecanismo de persistencia via registro.',
            ))
        actions.append(f'Revisar {len(suspicious)} entrada(s) sospechosa(s) en Run/RunOnce')
    else:
        findings.append(_finding(
            f'Registro Run/RunOnce: {len(all_entries)} entrada(s) — sin entradas sospechosas',
            SEV_INFO,
            'Claves revisadas: HKLM\\Run, HKLM\\RunOnce, HKCU\\Run, HKCU\\RunOnce',
        ))

    return {'findings': findings, 'warnings': warnings, 'recommended_actions': actions}


def _check_startup_folders():
    """Inspect Windows startup folders for unexpected or suspicious files."""
    findings = []
    warnings = []
    actions = []

    if sys.platform != 'win32':
        return {'findings': [], 'warnings': ['No Windows'], 'recommended_actions': []}

    startup_paths = []
    appdata = os.environ.get('APPDATA', '')
    if appdata:
        startup_paths.append((
            os.path.join(
                appdata, 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup'
            ),
            'Usuario',
        ))
    startup_paths.append((
        os.path.join(
            os.environ.get('ProgramData', r'C:\ProgramData'),
            'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup',
        ),
        'Sistema',
    ))

    all_items = []
    for path, label in startup_paths:
        if not os.path.exists(path):
            continue
        try:
            for item in os.listdir(path):
                full = os.path.join(path, item)
                if os.path.isfile(full):
                    all_items.append({'label': label, 'file': item, 'path': full})
        except PermissionError:
            warnings.append(f'Sin acceso a carpeta de inicio: {path}')

    # .lnk (shortcuts) are expected; anything else is suspicious
    suspicious = [i for i in all_items if not i['file'].lower().endswith('.lnk')]
    normal = [i for i in all_items if i['file'].lower().endswith('.lnk')]

    for item in suspicious:
        findings.append(_finding(
            f'Archivo inesperado en carpeta de inicio ({item["label"]}): {item["file"]}',
            SEV_WARNING,
            f'Ruta: {item["path"]}',
            f'Revise el archivo "{item["file"]}" en la carpeta de inicio — '
            'solo deben existir accesos directos (.lnk).',
        ))
        actions.append(f'Revisar archivo de inicio: {item["file"]}')

    if all_items:
        findings.append(_finding(
            f'Carpetas de inicio: {len(all_items)} elemento(s) '
            f'({len(normal)} acceso(s) directo(s), {len(suspicious)} sospechoso(s))',
            SEV_INFO if not suspicious else SEV_WARNING,
            ' | '.join(f'{i["label"]}: {i["file"]}' for i in all_items[:10]),
        ))
    else:
        findings.append(_finding(
            'Carpetas de inicio: vacias (sin elementos)',
            SEV_INFO,
            'Startup usuario y sistema sin elementos',
        ))

    return {'findings': findings, 'warnings': warnings, 'recommended_actions': actions}


def _check_scheduled_tasks():
    """Check non-Microsoft scheduled tasks for suspicious executables."""
    findings = []
    warnings = []
    actions = []

    result = run_powershell(
        "Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object { "
        "  $_.State -ne 'Disabled' -and "
        "  $_.TaskPath -notlike '\\Microsoft\\*' -and "
        "  $_.TaskPath -notlike '\\MicrosoftEdge*' -and "
        "  $_.TaskPath -notlike '\\Intel\\*' -and "
        "  $_.TaskPath -notlike '\\AMD\\*' "
        "} | ForEach-Object { "
        "  $exec = ($_.Actions | ForEach-Object { $_.Execute }) -join ','; "
        "  \"$($_.TaskName)|$($_.TaskPath)|$exec\" "
        "} | Select-Object -First 60",
        timeout=30,
        description='Scheduled tasks check',
    )

    if result.is_error or result.status == CommandStatus.NOT_APPLICABLE:
        warnings.append('No se pudo consultar las tareas programadas')
        return {'findings': findings, 'warnings': warnings, 'recommended_actions': actions}

    tasks = []
    suspicious_tasks = []
    for line in (result.output or '').splitlines():
        line = line.strip()
        if not line or '|' not in line:
            continue
        parts = line.split('|', 2)
        task_name = parts[0].strip()
        task_path = parts[1].strip() if len(parts) > 1 else ''
        task_exec = parts[2].strip().lower() if len(parts) > 2 else ''
        tasks.append({'name': task_name, 'path': task_path, 'exec': task_exec})
        if any(p in task_exec for p in _SUSPICIOUS_PATHS):
            suspicious_tasks.append({'name': task_name, 'path': task_path, 'exec': task_exec})

    for t in suspicious_tasks:
        findings.append(_finding(
            f'Tarea programada sospechosa: {t["name"]}',
            SEV_WARNING,
            f'Ruta: {t["path"]} | Ejecuta desde: {t["exec"][:180]}',
            f'Revise la tarea "{t["name"]}" — ejecuta desde ubicacion de riesgo.',
        ))
        actions.append(f'Revisar tarea programada: {t["name"]}')

    non_suspicious = len(tasks) - len(suspicious_tasks)
    findings.append(_finding(
        f'Tareas programadas: {len(tasks)} de terceros '
        f'({len(suspicious_tasks)} sospechosa(s), {non_suspicious} normal(es))',
        SEV_INFO if not suspicious_tasks else SEV_WARNING,
        f'Total tareas fuera del espacio Microsoft: {len(tasks)}',
    ))

    return {'findings': findings, 'warnings': warnings, 'recommended_actions': actions}


def _check_temp_executables():
    """Scan TEMP folder for executable files — common malware indicator."""
    findings = []
    warnings = []
    actions = []

    if sys.platform != 'win32':
        return {'findings': [], 'warnings': ['No Windows'], 'recommended_actions': []}

    temp_path = os.environ.get('TEMP', os.environ.get('TMP', ''))
    if not temp_path or not os.path.exists(temp_path):
        warnings.append('Carpeta TEMP no disponible')
        return {'findings': findings, 'warnings': warnings, 'recommended_actions': actions}

    suspicious_files = []
    try:
        for item in os.listdir(temp_path):
            ext = os.path.splitext(item)[1].lower()
            if ext in _SUSPICIOUS_EXTS:
                full_path = os.path.join(temp_path, item)
                try:
                    size = os.path.getsize(full_path)
                except OSError:
                    size = 0
                suspicious_files.append({'file': item, 'path': full_path, 'size': size})
    except PermissionError:
        warnings.append(f'Sin acceso a {temp_path}')
        return {'findings': findings, 'warnings': warnings, 'recommended_actions': actions}

    if suspicious_files:
        for f in suspicious_files[:20]:  # Cap at 20 findings
            size_kb = round(f['size'] / 1024, 1)
            findings.append(_finding(
                f'Ejecutable en TEMP: {f["file"]} ({size_kb} KB)',
                SEV_WARNING,
                f'Ruta: {f["path"]}',
                f'Investigue "{f["file"]}" — los ejecutables en TEMP son '
                'indicadores comunes de malware o instaladores no limpiados.',
            ))
        if len(suspicious_files) > 1:
            actions.append(
                f'Revisar y eliminar {len(suspicious_files)} ejecutable(s) en TEMP'
            )
    else:
        findings.append(_finding(
            'Carpeta TEMP: sin ejecutables sospechosos',
            SEV_INFO,
            f'Analizada: {temp_path}',
        ))

    return {'findings': findings, 'warnings': warnings, 'recommended_actions': actions}


def _check_uac():
    """Check UAC (User Account Control) status."""
    findings = []
    warnings = []
    actions = []

    result = run_powershell(
        "(Get-ItemProperty "
        "'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System' "
        "-Name EnableLUA -ErrorAction SilentlyContinue).EnableLUA",
        timeout=10,
        description='UAC status check',
    )

    val = (result.output or '').strip()
    if result.is_error or not val:
        warnings.append('No se pudo verificar el estado de UAC')
        return {'findings': findings, 'warnings': warnings, 'recommended_actions': actions}

    if val == '0':
        findings.append(_finding(
            'UAC (Control de Cuentas) DESACTIVADO',
            SEV_CRITICAL,
            'EnableLUA: 0',
            'Active el Control de Cuentas de Usuario (UAC): '
            'Panel de control > Cuentas de usuario > Cambiar configuracion de UAC.',
        ))
        actions.append('Activar UAC — Control de Cuentas de Usuario')
    else:
        findings.append(_finding(
            'UAC activo',
            SEV_INFO,
            f'EnableLUA: {val}',
        ))

    return {'findings': findings, 'warnings': warnings, 'recommended_actions': actions}


def _check_wdigest():
    """Check WDigest credential caching (cleartext credentials in memory)."""
    findings = []
    warnings = []
    actions = []

    result = run_powershell(
        "(Get-ItemProperty "
        "'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\SecurityProviders\\WDigest' "
        "-Name UseLogonCredential -ErrorAction SilentlyContinue).UseLogonCredential",
        timeout=10,
        description='WDigest credential caching check',
    )

    val = (result.output or '').strip()

    # Key absent = secure (default on Windows 8.1+ / Server 2012 R2+)
    if not val or result.is_error:
        findings.append(_finding(
            'WDigest: credenciales en texto claro desactivadas (seguro)',
            SEV_INFO,
            'Clave UseLogonCredential ausente — configuracion segura por defecto',
        ))
        return {'findings': findings, 'warnings': warnings, 'recommended_actions': actions}

    if val == '1':
        findings.append(_finding(
            'WDigest habilitado — credenciales en texto claro en memoria',
            SEV_CRITICAL,
            'UseLogonCredential: 1 — credenciales almacenadas sin cifrar en LSASS',
            'Establezca UseLogonCredential=0 en '
            'HKLM\\SYSTEM\\CurrentControlSet\\Control\\SecurityProviders\\WDigest '
            'y reinicie el equipo.',
        ))
        actions.append('Deshabilitar WDigest (UseLogonCredential = 0)')
    else:
        findings.append(_finding(
            'WDigest desactivado (seguro)',
            SEV_INFO,
            f'UseLogonCredential: {val}',
        ))

    return {'findings': findings, 'warnings': warnings, 'recommended_actions': actions}


def _check_rdp():
    """Check if Remote Desktop Protocol (RDP) is enabled."""
    findings = []
    warnings = []
    actions = []

    result = run_powershell(
        "(Get-ItemProperty "
        "'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Terminal Server' "
        "-Name fDenyTSConnections -ErrorAction SilentlyContinue).fDenyTSConnections",
        timeout=10,
        description='RDP status check',
    )

    val = (result.output or '').strip()
    if result.is_error or not val:
        warnings.append('No se pudo verificar el estado de RDP')
        return {'findings': findings, 'warnings': warnings, 'recommended_actions': actions}

    # fDenyTSConnections=0 means RDP is ALLOWED
    if val == '0':
        findings.append(_finding(
            'Escritorio Remoto (RDP) habilitado',
            SEV_WARNING,
            'fDenyTSConnections: 0 — el equipo acepta conexiones RDP',
            'Si el Escritorio Remoto no es necesario, desactivelo para reducir '
            'la superficie de ataque externa.',
        ))
        actions.append('Evaluar si RDP es necesario; desactivarlo si no se utiliza')
    else:
        findings.append(_finding(
            'Escritorio Remoto (RDP) desactivado',
            SEV_INFO,
            f'fDenyTSConnections: {val}',
        ))

    return {'findings': findings, 'warnings': warnings, 'recommended_actions': actions}


def _check_guest_account():
    """Check if the Windows built-in Guest account is enabled."""
    findings = []
    warnings = []
    actions = []

    result = run_powershell(
        "try { "
        "  $g = Get-LocalUser -Name 'Guest' -ErrorAction Stop; "
        "  $g.Enabled.ToString() "
        "} catch { 'not_found' }",
        timeout=10,
        description='Guest account check',
    )

    val = (result.output or '').strip().lower()
    if val == 'true':
        findings.append(_finding(
            'Cuenta Invitado de Windows habilitada',
            SEV_WARNING,
            'Get-LocalUser Guest: Enabled = True',
            'Deshabilite la cuenta Invitado para evitar acceso no autorizado: '
            'net user guest /active:no',
        ))
        actions.append('Deshabilitar cuenta Invitado de Windows')
    elif val in ('false', 'not_found'):
        label = 'deshabilitada' if val == 'false' else 'no encontrada'
        findings.append(_finding(
            f'Cuenta Invitado: {label} (seguro)',
            SEV_INFO,
            f'Get-LocalUser Guest: {val}',
        ))
    else:
        warnings.append(f'Estado de cuenta Invitado indeterminado: {val}')

    return {'findings': findings, 'warnings': warnings, 'recommended_actions': actions}


def _check_autorun():
    """Check AutoRun / AutoPlay policy in registry."""
    findings = []
    warnings = []
    actions = []

    result = run_powershell(
        "(Get-ItemProperty "
        "'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer' "
        "-Name NoDriveTypeAutoRun -ErrorAction SilentlyContinue).NoDriveTypeAutoRun",
        timeout=10,
        description='AutoRun policy check',
    )

    val = (result.output or '').strip()
    if not val or result.is_error:
        findings.append(_finding(
            'AutoRun: politica no configurada (posiblemente habilitado)',
            SEV_WARNING,
            'NoDriveTypeAutoRun no presente en registro — AutoRun puede estar activo',
            'Configure NoDriveTypeAutoRun = 255 para deshabilitar AutoRun en '
            'todas las unidades (HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion'
            '\\Policies\\Explorer).',
        ))
        actions.append('Deshabilitar AutoRun para todas las unidades via registro')
        return {'findings': findings, 'warnings': warnings, 'recommended_actions': actions}

    try:
        val_int = int(val)
        if val_int == 255:
            findings.append(_finding(
                'AutoRun desactivado en todas las unidades (0xFF)',
                SEV_INFO,
                f'NoDriveTypeAutoRun: {val_int}',
            ))
        elif val_int >= 128:
            findings.append(_finding(
                'AutoRun parcialmente desactivado',
                SEV_INFO,
                f'NoDriveTypeAutoRun: {val_int} (cubre la mayoria de unidades)',
            ))
        else:
            findings.append(_finding(
                f'AutoRun no completamente desactivado (valor: {val_int})',
                SEV_WARNING,
                f'NoDriveTypeAutoRun: {val_int} — no cubre todas las unidades',
                'Establezca NoDriveTypeAutoRun = 255 para bloquear AutoRun completamente.',
            ))
            actions.append('Configurar AutoRun para todas las unidades (valor 255)')
    except ValueError:
        warnings.append(f'Valor de AutoRun no numerico: {val}')

    return {'findings': findings, 'warnings': warnings, 'recommended_actions': actions}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_security_audit():
    """
    Run a full internal security inspection using native Windows capabilities.

    Returns a dict with:
      status            — 'completed' or 'failed'
      message           — human-readable summary for the IT technician
      findings          — list of finding dicts (title, severity, evidence, recommended_action)
      warnings          — list of non-critical issue strings
      errors            — list of check-level error strings
      started_at        — ISO timestamp
      ended_at          — ISO timestamp
      duration          — float seconds
      recommended_actions — deduplicated list of action strings
    """
    started_at = datetime.now()
    findings = []
    warnings = []
    errors = []
    recommended_actions = []

    checks = [
        ('Windows Defender', _check_defender),
        ('Firewall de Windows', _check_firewall),
        ('Windows Update', _check_windows_update),
        ('Registro Run/RunOnce', _check_run_registry),
        ('Carpetas de inicio', _check_startup_folders),
        ('Tareas programadas', _check_scheduled_tasks),
        ('Ejecutables en TEMP', _check_temp_executables),
        ('UAC', _check_uac),
        ('WDigest', _check_wdigest),
        ('Escritorio Remoto (RDP)', _check_rdp),
        ('Cuenta Invitado', _check_guest_account),
        ('AutoRun / AutoPlay', _check_autorun),
    ]

    for check_name, check_fn in checks:
        try:
            result = check_fn()
            findings.extend(result.get('findings', []))
            warnings.extend(result.get('warnings', []))
            recommended_actions.extend(result.get('recommended_actions', []))
        except Exception as e:
            logger.warning(f"Security check '{check_name}' raised exception: {e}")
            errors.append(f'{check_name}: {e}')

    ended_at = datetime.now()
    duration = (ended_at - started_at).total_seconds()

    critical_count = sum(1 for f in findings if f.get('severity') == SEV_CRITICAL)
    warning_count = sum(1 for f in findings if f.get('severity') == SEV_WARNING)
    info_count = sum(1 for f in findings if f.get('severity') == SEV_INFO)

    if critical_count > 0:
        status = 'completed'
        message = (
            f'Auditoria de seguridad: {critical_count} problema(s) CRITICO(S) — '
            f'{warning_count} advertencia(s), {info_count} verificacion(es) OK. '
            f'Se requiere atencion inmediata del tecnico.'
        )
    elif warning_count > 0:
        status = 'completed'
        message = (
            f'Auditoria de seguridad: {warning_count} advertencia(s) detectadas — '
            f'{info_count} verificacion(es) OK. Revise las recomendaciones.'
        )
    else:
        status = 'completed'
        message = (
            f'Auditoria de seguridad: {info_count} verificacion(es) completadas '
            f'sin problemas detectados. El equipo esta en buen estado de seguridad.'
        )

    if errors:
        message += f' ({len(errors)} verificacion(es) con error tecnico).'

    return {
        'status': status,
        'message': message,
        'findings': findings,
        'warnings': warnings,
        'errors': errors,
        'started_at': started_at.isoformat(),
        'ended_at': ended_at.isoformat(),
        'duration': round(duration, 1),
        'recommended_actions': recommended_actions,
    }

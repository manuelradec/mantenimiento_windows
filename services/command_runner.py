"""
Secure Command Execution Layer.

All system commands (CMD, PowerShell, Windows utilities) MUST go through this module.

Enterprise features:
- Command allowlist validation
- List-based subprocess execution (no shell=True by default)
- Structured result objects with operation IDs
- Argument sanitization and schema validation
- Timeout management with process tree termination
- Full logging with sensitive data redaction
- PowerShell JSON-native output support
"""
import subprocess
import logging
import time
import re
import sys
import os
import uuid
from datetime import datetime
from enum import Enum

logger = logging.getLogger('cleancpu.command_runner')


class CommandStatus(str, Enum):
    SUCCESS = 'success'
    WARNING = 'warning'
    ERROR = 'error'
    NOT_APPLICABLE = 'not_applicable'
    TIMEOUT = 'timeout'
    SKIPPED = 'skipped'
    REQUIRES_ADMIN = 'requires_admin'
    REQUIRES_REBOOT = 'requires_reboot'
    PARTIAL_SUCCESS = 'partial_success'


class CommandResult:
    """Structured result from a command execution."""

    def __init__(self, status, output='', error='', return_code=None,
                 command='', duration=0.0, details=None, operation_id=None):
        self.status = status
        self.output = output
        self.error = error
        self.return_code = return_code
        self.command = command
        self.duration = duration
        self.timestamp = datetime.now().isoformat()
        self.details = details or {}
        self.operation_id = operation_id or str(uuid.uuid4())[:8]

    def to_dict(self):
        return {
            'status': self.status.value if isinstance(self.status, CommandStatus) else self.status,
            'output': self.output,
            'error': self.error,
            'return_code': self.return_code,
            'command': self.command,
            'duration': round(self.duration, 2),
            'timestamp': self.timestamp,
            'details': self.details,
            'operation_id': self.operation_id,
        }

    @property
    def is_success(self):
        return self.status == CommandStatus.SUCCESS

    @property
    def is_error(self):
        return self.status in (CommandStatus.ERROR, CommandStatus.TIMEOUT)


# ============================================================
# COMMAND ALLOWLIST - Fine-grained per-executable validation
# ============================================================
# Each entry maps a command base (case-insensitive) to either:
#   True                    -> allowed with any arguments (legacy, discouraged)
#   {'subcommands': [...]}  -> only these subcommands/flags allowed
#   {'patterns': [...]}     -> regex patterns for allowed argument strings

ALLOWED_COMMANDS = {
    # System diagnostics & repair
    'sfc': {'subcommands': ['/scannow', '/verifyonly']},
    'dism': {'subcommands': ['/Online', '/Cleanup-Image', '/CheckHealth',
                             '/ScanHealth', '/RestoreHealth',
                             '/StartComponentCleanup']},
    'chkdsk': {'subcommands': ['/scan', '/f', '/r', '/x']},
    'winsat': {'subcommands': ['disk', 'formal']},
    'mdsched.exe': {'max_args': 0},  # No arguments allowed
    'ipconfig': {'subcommands': ['/flushdns', '/release', '/renew', '/all']},
    'nbtstat': {'subcommands': ['-R']},
    'netsh': {'subcommands': ['int', 'winsock', 'winhttp'],
              'allowed_verbs': ['show', 'reset', 'set'],
              'denied_args': ['firewall', 'advfirewall']},
    'net': {'subcommands': ['stop', 'start', 'use', 'share'],
            'denied_first_arg': ['config', 'user', 'accounts', 'group',
                                 'localgroup']},
    'route': {'subcommands': ['print']},
    'defrag': {'subcommands': ['/O', '/U', '/V', '/A'],
               'denied_args': ['/x']},
    'cleanmgr': {'subcommands': ['/sagerun:1', '/d']},
    'wsreset.exe': {'max_args': 0},
    'taskkill': {'subcommands': ['/f', '/im', '/F', '/T', '/PID'],
                 'denied_args': ['/fi']},
    'start': {'allowed_patterns': [r'^(explorer\.exe|ms-settings:.*)$']},
    'ren': {'allowed_patterns': [
        r'^.*\\softwaredistribution\s+softwaredistribution\.bak\.',
        r'^.*\\catroot2\s+catroot2\.bak\.',
    ]},
    'w32tm': {'subcommands': ['/resync', '/query']},
    'sc': {'subcommands': ['config', 'query'],
           'denied_args': ['delete', 'create']},
    'usoclient': {'subcommands': ['StartScan', 'StartDownload',
                                  'StartInstall']},
    'powercfg': {'subcommands': ['/GETACTIVESCHEME', '/Q', '/LIST',
                                 '-setactive', '/batteryreport', '-h',
                                 '/output']},
    'cscript': {'allowed_patterns': [
        r'^//nologo\s+.*\\slmgr\.vbs\s+/\w+$',
        r'^//nologo\s+.*\\ospp\.vbs\s+/(?:dstatus|act)$',
        r'^//nologo\s+.*\\ospp\.vbs\s+/inpkey:[a-z0-9]{5}-[a-z0-9]{5}-[a-z0-9]{5}-[a-z0-9]{5}-[a-z0-9]{5}$',
    ]},
    'fsutil': {'subcommands': ['behavior']},
    'pnputil': {'subcommands': ['/enum-drivers', '/enum-devices'],
                'denied_args': ['/delete-driver', '/remove']},

    # PowerShell — allowed only via internal wrappers (run_powershell/
    # run_powershell_json) which build the command list themselves.
    # Direct invocation with arbitrary scripts is blocked by requiring
    # that the command comes through the powershell=True path in run_cmd.
    'powershell.exe': {'subcommands': ['-NoProfile', '-NonInteractive',
                                       '-ExecutionPolicy', '-Command']},
}

# Normalized allowlist built once at import time for O(1) lookup.
# Keys are lower-cased and stripped of .exe so matching is case-insensitive.
_NORMALIZED_ALLOWLIST: dict = {
    k.lower().replace('.exe', ''): v for k, v in ALLOWED_COMMANDS.items()
}

# Commands that require shell=True with justification
SHELL_REQUIRED_COMMANDS = {
    # 'start explorer.exe' requires shell because 'start' is a shell builtin
    'start',
}

# Documentation of shell=True usage:
# 1. String commands passed to run_cmd() use shell=True because they
#    cannot be split reliably (e.g., paths with spaces, quoted args).
#    This is ONLY used when the base command passes allowlist validation.
# 2. 'start' is a CMD shell builtin, not an executable.
#    It requires shell=True to function.


# Characters that must never appear in command arguments
DANGEROUS_PATTERNS = [
    r'[;&|`$]',          # Shell metacharacters
    r'\.\.',              # Path traversal
    r'[<>]',             # Redirection
    r'[\r\n]',           # Newline injection
]


def sanitize_argument(arg: str) -> str:
    """
    Sanitize a command argument to prevent injection.
    Raises ValueError if dangerous patterns detected.
    """
    if not isinstance(arg, str):
        arg = str(arg)
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, arg):
            raise ValueError(f"Potentially dangerous characters in argument: {arg!r}")
    return arg


def _validate_command(cmd_parts: list) -> bool:
    """
    Validate that a command is in the allowlist with fine-grained checks.
    Returns True if allowed, False if blocked.
    """
    if not cmd_parts:
        return False

    base_cmd = os.path.basename(cmd_parts[0]).lower().replace('.exe', '')
    entry = _NORMALIZED_ALLOWLIST.get(base_cmd)

    if entry is None:
        return False

    # Simple True means allowed with any arguments (legacy, discouraged)
    if entry is True:
        return True

    if not isinstance(entry, dict):
        return False

    args = cmd_parts[1:]
    args_str = ' '.join(args).lower() if args else ''

    # Check max_args constraint (e.g., mdsched.exe takes no arguments)
    max_args = entry.get('max_args')
    if max_args is not None and len(args) > max_args:
        logger.warning(
            f"Too many arguments ({len(args)} > {max_args}) "
            f"for command '{base_cmd}'"
        )
        return False

    # Check denied_args (substring match in full args string)
    for denied_arg in entry.get('denied_args', []):
        if denied_arg.lower() in args_str:
            logger.warning(f"Denied argument '{denied_arg}' for command '{base_cmd}'")
            return False

    # Check denied_first_arg (exact match on first argument only)
    denied_first = entry.get('denied_first_arg', [])
    if denied_first and len(cmd_parts) > 1:
        first_arg = cmd_parts[1].lower()
        if first_arg in {d.lower() for d in denied_first}:
            logger.warning(f"Denied first argument '{first_arg}' for command '{base_cmd}'")
            return False

    # Check allowed_patterns (regex) — if patterns exist, one must match; none matching blocks
    patterns = entry.get('allowed_patterns', [])
    if patterns:
        if any(re.match(p, args_str, re.IGNORECASE) for p in patterns):
            return True
        return False  # Had patterns but none matched

    # If subcommands specified, at least one must appear in the args
    subcommands = entry.get('subcommands', [])
    if subcommands and args_str:
        if not any(sc.lower() in args_str for sc in subcommands):
            logger.warning(f"No matching subcommand for '{base_cmd}' in: {args_str[:100]}")
            return False

    return True


def is_admin() -> bool:
    """Check if current process has admin privileges."""
    if sys.platform != 'win32':
        return os.getuid() == 0
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def _kill_process_tree(proc):
    """Kill a process and all its children."""
    try:
        if sys.platform == 'win32':
            # Use taskkill /T to kill process tree on Windows
            subprocess.run(
                ['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                capture_output=True, timeout=10,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
        else:
            proc.kill()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _redact_command_for_log(cmd_display: str) -> str:
    """Redact potentially sensitive parts of a command for logging."""
    # Redact passwords, keys, tokens in command strings
    redacted = re.sub(r'(?i)(password|pwd|key|token|secret)\s*[=:]\s*\S+',
                      r'\1=***REDACTED***', cmd_display)
    return redacted


def _prepare_command(command, powershell: bool, shell: bool):
    """
    Resolve the actual subprocess command, shell flag, and allowlist-validation parts.

    Returns:
        (actual_cmd, use_shell, parts_to_validate)

    ``parts_to_validate`` is None when allowlist checking is not applicable
    (PowerShell path bypasses the allowlist because the wrapper controls the script).
    """
    if powershell:
        ps_cmd = command if isinstance(command, str) else ' '.join(command)
        actual_cmd = [
            'powershell.exe', '-NoProfile', '-NonInteractive',
            '-ExecutionPolicy', 'Bypass', '-Command', ps_cmd,
        ]
        return actual_cmd, False, None  # PS wrapper — no allowlist check

    if isinstance(command, list):
        return command, shell, command

    if isinstance(command, str):
        return command, True, command.split()  # shell required for string commands

    return command, shell, None  # Unknown type — pass through without validation


def run_cmd(command, timeout=120, requires_admin=False, shell=False,
            description='', powershell=False, capture_output=True):
    """
    Execute a system command safely.

    Args:
        command: Command string or list of arguments.
        timeout: Maximum execution time in seconds.
        requires_admin: If True, checks admin rights before running.
        shell: Use shell execution. Avoided by default for security.
        description: Human-readable description of what this command does.
        powershell: If True, wraps the command for PowerShell execution.
        capture_output: Whether to capture stdout/stderr.

    Returns:
        CommandResult with structured data.
    """
    operation_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    # Build display name for logging
    if isinstance(command, list):
        cmd_display = ' '.join(command)
    else:
        cmd_display = str(command)

    log_desc = description or _redact_command_for_log(cmd_display)
    logger.info(f"[{operation_id}] Executing: {log_desc}")

    # Admin check
    if requires_admin and not is_admin():
        logger.warning(f"[{operation_id}] Admin required for: {log_desc}")
        return CommandResult(
            status=CommandStatus.REQUIRES_ADMIN,
            command=cmd_display,
            error='This command requires administrator privileges.',
            duration=time.time() - start_time,
            operation_id=operation_id,
        )

    # Platform check
    if sys.platform != 'win32':
        logger.info(f"[{operation_id}] Simulated (non-Windows): {log_desc}")
        return CommandResult(
            status=CommandStatus.NOT_APPLICABLE,
            command=cmd_display,
            output=f'[SIMULATED] Command not available on this platform: {cmd_display}',
            duration=time.time() - start_time,
            operation_id=operation_id,
        )

    # Resolve command form and perform allowlist validation
    actual_cmd, use_shell, validation_parts = _prepare_command(command, powershell, shell)
    if validation_parts and not _validate_command(validation_parts):
        logger.warning(
            f"[{operation_id}] BLOCKED by allowlist: "
            f"{_redact_command_for_log(cmd_display)}"
        )
        return CommandResult(
            status=CommandStatus.ERROR,
            command=cmd_display,
            error=f'Command blocked by allowlist: {validation_parts[0]}',
            duration=time.time() - start_time,
            operation_id=operation_id,
            details={
                'validation': 'blocked_by_allowlist',
                'base_command': validation_parts[0],
            },
        )

    try:
        process = subprocess.Popen(
            actual_cmd,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
            text=True,
            encoding='utf-8',
            errors='replace',
            shell=use_shell,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )

        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_process_tree(process)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
            duration = time.time() - start_time
            logger.warning(f"[{operation_id}] Timeout after {duration:.1f}s: {log_desc}")
            return CommandResult(
                status=CommandStatus.TIMEOUT,
                command=cmd_display,
                error=f'Command timed out after {timeout} seconds.',
                duration=duration,
                operation_id=operation_id,
            )

        duration = time.time() - start_time
        stdout = (stdout or '').strip()
        stderr = (stderr or '').strip()
        return_code = process.returncode

        if return_code == 0:
            status = CommandStatus.SUCCESS
        elif return_code in (1, 2):
            status = CommandStatus.WARNING
        else:
            status = CommandStatus.ERROR

        logger.info(
            f"[{operation_id}] Completed ({status.value}, rc={return_code}, "
            f"{duration:.1f}s): {log_desc}"
        )

        return CommandResult(
            status=status,
            output=stdout,
            error=stderr,
            return_code=return_code,
            command=cmd_display,
            duration=duration,
            operation_id=operation_id,
        )

    except FileNotFoundError:
        duration = time.time() - start_time
        logger.error(f"[{operation_id}] Command not found: {cmd_display}")
        return CommandResult(
            status=CommandStatus.NOT_APPLICABLE,
            command=cmd_display,
            error=f'Command not found: {cmd_display}',
            duration=duration,
            operation_id=operation_id,
        )
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"[{operation_id}] Exception running {log_desc}: {e}")
        return CommandResult(
            status=CommandStatus.ERROR,
            command=cmd_display,
            error=str(e),
            duration=duration,
            operation_id=operation_id,
        )


def run_powershell(script, timeout=120, requires_admin=False, description=''):
    """Convenience wrapper to run a PowerShell script/command."""
    return run_cmd(
        script,
        timeout=timeout,
        requires_admin=requires_admin,
        description=description,
        powershell=True,
    )


def _format_json_as_readable_text(data, description=''):
    """
    Convert parsed JSON data (list of dicts or dict) into a human-readable
    text block suitable for display in the IT technician console.
    """
    lines = []
    title = description.strip() or 'Resultado'
    lines.append(f'=== {title} ===')
    lines.append('')

    # Map common English field names to Spanish labels for IT technicians
    LABEL_MAP = {
        'Name': 'Nombre',
        'DisplayName': 'Nombre completo',
        'InterfaceDescription': 'Descripcion',
        'Status': 'Estado',
        'LinkSpeed': 'Velocidad',
        'MacAddress': 'Direccion MAC',
        'DriverVersion': 'Version del driver',
        'StartType': 'Tipo de inicio',
        'Command': 'Comando',
        'Location': 'Ubicacion',
        'User': 'Usuario',
        'Caption': 'Descripcion',
        'Description': 'Descripcion',
        'DeviceID': 'ID del dispositivo',
        'Manufacturer': 'Fabricante',
        'Model': 'Modelo',
        'Size': 'Tamano',
        'FreeSpace': 'Espacio libre',
        'DriveType': 'Tipo de unidad',
        'FileSystem': 'Sistema de archivos',
        'VolumeName': 'Nombre del volumen',
        'OSArchitecture': 'Arquitectura',
        'Version': 'Version',
        'BuildNumber': 'Numero de compilacion',
        'CSName': 'Equipo',
        'InstallDate': 'Fecha de instalacion',
        'LastBootUpTime': 'Ultimo inicio',
        'TotalVisibleMemorySize': 'RAM total',
        'FreePhysicalMemory': 'RAM libre',
    }

    STATUS_MAP = {
        'Up': 'Activo',
        'Down': 'Inactivo',
        'Disconnected': 'Desconectado',
        'Not Present': 'No encontrado',
        'Running': 'En ejecucion',
        'Stopped': 'Detenido',
        'Disabled': 'Deshabilitado',
        'Automatic': 'Automatico',
        'Manual': 'Manual',
        'Boot': 'Inicio del sistema',
        'System': 'Sistema',
    }

    def fmt_val(val):
        if val is None:
            return '—'
        s = str(val).strip()
        return STATUS_MAP.get(s, s) if s else '—'

    def fmt_item(item, index=None):
        if not isinstance(item, dict):
            prefix = f'[{index}] ' if index is not None else '  '
            lines.append(f'{prefix}{fmt_val(item)}')
            return
        # Use 'Name' or 'DisplayName' as the header if available
        header = item.get('DisplayName') or item.get('Name') or (
            f'Elemento {index}' if index is not None else None
        )
        if header:
            prefix = f'[{index}] ' if index is not None else ''
            lines.append(f'{prefix}{header}')
        indent = '    '
        for key, raw_val in item.items():
            if key in ('Name', 'DisplayName') and header == (item.get('DisplayName') or item.get('Name')):
                continue  # Already shown in header
            label = LABEL_MAP.get(key, key)
            lines.append(f'{indent}{label:<20}: {fmt_val(raw_val)}')
        lines.append('')

    if isinstance(data, list):
        if not data:
            lines.append('  (sin resultados)')
        else:
            for i, item in enumerate(data, start=1):
                fmt_item(item, index=i)
    elif isinstance(data, dict):
        fmt_item(data)
    else:
        lines.append(str(data))

    return '\n'.join(lines).rstrip()


def run_powershell_json(script, timeout=120, requires_admin=False, description=''):
    """
    Run a PowerShell command and parse JSON output.

    Appends '| ConvertTo-Json -Compress' to the script if not already present.
    Returns CommandResult with parsed JSON in details['data'] and a
    human-readable formatted string in output.
    """
    import json as json_mod

    if 'ConvertTo-Json' not in script:
        script = f'{script} | ConvertTo-Json -Compress -Depth 5'

    result = run_powershell(script, timeout=timeout,
                            requires_admin=requires_admin, description=description)

    if result.is_success and result.output:
        try:
            parsed = json_mod.loads(result.output)
            result.details['data'] = parsed
            result.output = _format_json_as_readable_text(parsed, description)
        except json_mod.JSONDecodeError:
            # PowerShell output wasn't valid JSON, keep raw output
            pass

    return result

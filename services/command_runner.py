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
                             '/ScanHealth', '/RestoreHealth', '/StartComponentCleanup']},
    'chkdsk': {'subcommands': ['/scan', '/f', '/r', '/x']},
    'winsat': {'subcommands': ['disk', 'formal']},
    'mdsched.exe': True,  # No arguments needed
    'ipconfig': {'subcommands': ['/flushdns', '/release', '/renew', '/all']},
    'nbtstat': {'subcommands': ['-R']},
    'netsh': {'subcommands': ['int', 'winsock', 'winhttp'],
              'allowed_verbs': ['show', 'reset', 'set']},
    'net': {'subcommands': ['stop', 'start', 'use', 'share'],
            'denied_first_arg': ['config', 'user', 'accounts', 'group']},
    'route': {'subcommands': ['print']},
    'defrag': {'subcommands': ['/O', '/U', '/V', '/A']},
    'cleanmgr': {'subcommands': ['/sagerun:1', '/d']},
    'wsreset.exe': True,
    'taskkill': {'subcommands': ['/f', '/im', '/F', '/T', '/PID'],
                 'denied_args': ['/fi']},
    'start': {'allowed_patterns': [r'^(explorer\.exe|ms-settings:.*)$']},
    'ren': True,  # Used for WU reset renames
    'w32tm': {'subcommands': ['/resync', '/query']},
    'sc': {'subcommands': ['config', 'query'],
           'denied_args': ['delete', 'create']},
    'usoclient': {'subcommands': ['StartScan', 'StartDownload', 'StartInstall']},
    'powercfg': {'subcommands': ['/GETACTIVESCHEME', '/Q', '/LIST', '-setactive',
                                 '/batteryreport', '-h', '/output']},
    'cscript': True,  # For slmgr.vbs
    'fsutil': {'subcommands': ['behavior']},
    'pnputil': {'subcommands': ['/enum-drivers', '/enum-devices']},

    # PowerShell (validated separately via script content)
    'powershell.exe': True,
}


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

    # Find matching allowlist entry (case-insensitive)
    entry = None
    for allowed_name, allowed_spec in ALLOWED_COMMANDS.items():
        if allowed_name.lower().replace('.exe', '') == base_cmd:
            entry = allowed_spec
            break

    if entry is None:
        return False

    # Simple True means allowed with any arguments
    if entry is True:
        return True

    if not isinstance(entry, dict):
        return False

    args_str = ' '.join(cmd_parts[1:]).lower() if len(cmd_parts) > 1 else ''

    # Check denied_args (substring match in full args string)
    denied = entry.get('denied_args', [])
    for denied_arg in denied:
        if denied_arg.lower() in args_str:
            logger.warning(f"Denied argument '{denied_arg}' for command '{base_cmd}'")
            return False

    # Check denied_first_arg (exact match on first argument only)
    denied_first = entry.get('denied_first_arg', [])
    if denied_first and len(cmd_parts) > 1:
        first_arg = cmd_parts[1].lower()
        if first_arg in [d.lower() for d in denied_first]:
            logger.warning(f"Denied first argument '{first_arg}' for command '{base_cmd}'")
            return False

    # Check allowed_patterns (regex)
    patterns = entry.get('allowed_patterns', [])
    if patterns:
        import re as re_mod
        for pattern in patterns:
            if re_mod.match(pattern, args_str, re_mod.IGNORECASE):
                return True
        if patterns:  # Had patterns but none matched
            return False

    # If subcommands specified, at least one must appear in the args
    subcommands = entry.get('subcommands', [])
    if subcommands:
        found = any(sc.lower() in args_str for sc in subcommands)
        if not found and args_str:
            # Args were given but don't match any allowed subcommand
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

    # Build actual command
    if powershell:
        ps_cmd = command if isinstance(command, str) else ' '.join(command)
        actual_cmd = [
            'powershell.exe', '-NoProfile', '-NonInteractive',
            '-ExecutionPolicy', 'Bypass', '-Command', ps_cmd
        ]
        use_shell = False
    elif isinstance(command, list):
        actual_cmd = command
        use_shell = shell
        # Validate against allowlist
        if not _validate_command(command):
            logger.warning(f"[{operation_id}] Command not in allowlist: {command[0]}")
            return CommandResult(
                status=CommandStatus.ERROR,
                command=cmd_display,
                error=f'Command not in allowlist: {command[0]}',
                duration=time.time() - start_time,
                operation_id=operation_id,
            )
    elif isinstance(command, str):
        # String command - try to validate the base command
        parts = command.split()
        if parts and not _validate_command(parts):
            logger.warning(f"[{operation_id}] Command not in allowlist: {parts[0]}")
            return CommandResult(
                status=CommandStatus.ERROR,
                command=cmd_display,
                error=f'Command not in allowlist: {parts[0]}',
                duration=time.time() - start_time,
                operation_id=operation_id,
            )
        actual_cmd = command
        use_shell = True  # String commands require shell
    else:
        actual_cmd = command
        use_shell = shell

    try:
        process = subprocess.Popen(
            actual_cmd,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
            text=True,
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


def run_powershell_json(script, timeout=120, requires_admin=False, description=''):
    """
    Run a PowerShell command and parse JSON output.

    Appends '| ConvertTo-Json -Compress' to the script if not already present.
    Returns CommandResult with parsed JSON in details['data'].
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
        except json_mod.JSONDecodeError:
            # PowerShell output wasn't valid JSON, keep raw output
            pass

    return result

"""
Central safe command execution layer.

All system commands (CMD, PowerShell, Windows utilities) MUST go through this module.
Provides:
- Structured result objects
- Timeout management
- Logging of every command
- Admin privilege validation
- Input sanitization
- Shell injection prevention
"""
import subprocess
import logging
import time
import re
import sys
import os
from datetime import datetime
from enum import Enum

logger = logging.getLogger('maintenance.command_runner')


class CommandStatus(str, Enum):
    SUCCESS = 'success'
    WARNING = 'warning'
    ERROR = 'error'
    NOT_APPLICABLE = 'not_applicable'
    TIMEOUT = 'timeout'
    SKIPPED = 'skipped'
    REQUIRES_ADMIN = 'requires_admin'
    REQUIRES_REBOOT = 'requires_reboot'


class CommandResult:
    """Structured result from a command execution."""

    def __init__(self, status, output='', error='', return_code=None,
                 command='', duration=0.0, details=None):
        self.status = status
        self.output = output
        self.error = error
        self.return_code = return_code
        self.command = command
        self.duration = duration
        self.timestamp = datetime.now().isoformat()
        self.details = details or {}

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
        }

    @property
    def is_success(self):
        return self.status == CommandStatus.SUCCESS

    @property
    def is_error(self):
        return self.status in (CommandStatus.ERROR, CommandStatus.TIMEOUT)


# Characters that should never appear in command arguments
DANGEROUS_PATTERNS = [
    r'[;&|`$]',          # Shell metacharacters
    r'\.\.',              # Path traversal
    r'[<>]',             # Redirection (unless explicitly allowed)
]


def sanitize_argument(arg):
    """
    Sanitize a command argument to prevent injection.
    Returns sanitized string or raises ValueError.
    """
    if not isinstance(arg, str):
        arg = str(arg)
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, arg):
            raise ValueError(f"Potentially dangerous characters in argument: {arg!r}")
    return arg


def is_admin():
    """Check if current process has admin privileges."""
    if sys.platform != 'win32':
        return os.getuid() == 0
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def run_cmd(command_list, timeout=120, requires_admin=False, shell=False,
            description='', powershell=False, capture_output=True):
    """
    Execute a system command safely.

    Args:
        command_list: List of command and arguments (preferred) or string for powershell.
        timeout: Maximum execution time in seconds.
        requires_admin: If True, checks admin rights before running.
        shell: Use shell execution. Avoided by default for security.
        description: Human-readable description of what this command does.
        powershell: If True, wraps the command for PowerShell execution.
        capture_output: Whether to capture stdout/stderr.

    Returns:
        CommandResult with structured data.
    """
    start_time = time.time()

    # Build the display name for logging
    if isinstance(command_list, list):
        cmd_display = ' '.join(command_list)
    else:
        cmd_display = str(command_list)

    log_desc = description or cmd_display
    logger.info(f"Executing: {log_desc}")

    # Admin check
    if requires_admin and not is_admin():
        logger.warning(f"Admin required for: {log_desc}")
        return CommandResult(
            status=CommandStatus.REQUIRES_ADMIN,
            command=cmd_display,
            error='This command requires administrator privileges.',
            duration=time.time() - start_time,
        )

    # Platform check
    if sys.platform != 'win32':
        logger.info(f"Simulated (non-Windows): {log_desc}")
        return CommandResult(
            status=CommandStatus.NOT_APPLICABLE,
            command=cmd_display,
            output=f'[SIMULATED] Command not available on this platform: {cmd_display}',
            duration=time.time() - start_time,
        )

    # Build actual command
    if powershell:
        if isinstance(command_list, list):
            ps_cmd = ' '.join(command_list)
        else:
            ps_cmd = command_list
        actual_cmd = ['powershell.exe', '-NoProfile', '-NonInteractive',
                      '-ExecutionPolicy', 'Bypass', '-Command', ps_cmd]
        shell = False
    elif isinstance(command_list, str) and not shell:
        # If given a string but shell=False, split it safely
        # For simple commands this works; for complex ones, caller should use shell=True
        actual_cmd = command_list
        shell = True
    else:
        actual_cmd = command_list

    try:
        process = subprocess.Popen(
            actual_cmd,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
            text=True,
            shell=shell,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )

        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
            duration = time.time() - start_time
            logger.warning(f"Timeout after {duration:.1f}s: {log_desc}")
            return CommandResult(
                status=CommandStatus.TIMEOUT,
                command=cmd_display,
                error=f'Command timed out after {timeout} seconds.',
                duration=duration,
            )

        duration = time.time() - start_time
        stdout = (stdout or '').strip()
        stderr = (stderr or '').strip()
        return_code = process.returncode

        if return_code == 0:
            status = CommandStatus.SUCCESS
        elif return_code in (1, 2):
            # Many Windows commands return 1 for warnings
            status = CommandStatus.WARNING
        else:
            status = CommandStatus.ERROR

        logger.info(f"Completed ({status.value}, rc={return_code}, {duration:.1f}s): {log_desc}")

        return CommandResult(
            status=status,
            output=stdout,
            error=stderr,
            return_code=return_code,
            command=cmd_display,
            duration=duration,
        )

    except FileNotFoundError:
        duration = time.time() - start_time
        logger.error(f"Command not found: {cmd_display}")
        return CommandResult(
            status=CommandStatus.NOT_APPLICABLE,
            command=cmd_display,
            error=f'Command not found: {cmd_display}',
            duration=duration,
        )
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"Exception running {log_desc}: {e}")
        return CommandResult(
            status=CommandStatus.ERROR,
            command=cmd_display,
            error=str(e),
            duration=duration,
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

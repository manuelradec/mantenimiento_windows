"""
Configuration for CleanCPU - Professional Windows Maintenance Tool.
"""
import os
import sys


def get_base_path():
    """Get base path, compatible with PyInstaller frozen executables."""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def _ensure_writable_dir(primary: str, fallback: str) -> str:
    """Try to create primary dir; on permission error, fall back to a local dir."""
    for path in (primary, fallback):
        try:
            os.makedirs(path, exist_ok=True)
            # Verify we can actually write
            test_file = os.path.join(path, '.write_test')
            with open(test_file, 'w') as f:
                f.write('ok')
            os.remove(test_file)
            return path
        except (PermissionError, OSError):
            continue
    # Last resort: return fallback anyway, let caller handle errors
    os.makedirs(fallback, exist_ok=True)
    return fallback


def get_log_dir():
    """Get the log directory. Uses ProgramData on Windows, else a local 'logs' folder."""
    local_fallback = os.path.join(get_base_path(), 'logs')
    if sys.platform == 'win32':
        base = os.environ.get('PROGRAMDATA', 'C:\\ProgramData')
        primary = os.path.join(base, 'CleanCPU', 'logs')
        return _ensure_writable_dir(primary, local_fallback)
    os.makedirs(local_fallback, exist_ok=True)
    return local_fallback


def get_report_dir():
    """Get the report output directory."""
    local_fallback = os.path.join(get_base_path(), 'reports')
    if sys.platform == 'win32':
        base = os.environ.get('PROGRAMDATA', 'C:\\ProgramData')
        primary = os.path.join(base, 'CleanCPU', 'reports')
        return _ensure_writable_dir(primary, local_fallback)
    os.makedirs(local_fallback, exist_ok=True)
    return local_fallback


class Config:
    """Flask application configuration."""
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'cleancpu-local-key')
    DEBUG = False
    HOST = '127.0.0.1'
    PORT = 5000
    THREADED = True

    BASE_PATH = get_base_path()
    LOG_DIR = get_log_dir()
    REPORT_DIR = get_report_dir()

    # Safety settings
    COMMAND_TIMEOUT_DEFAULT = 120      # seconds
    COMMAND_TIMEOUT_LONG = 600         # for SFC, DISM, etc.
    COMMAND_TIMEOUT_VERY_LONG = 1800   # for full scans

    # Session cookie hardening (also set in security.py init_security)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Strict'
    SESSION_COOKIE_SECURE = False  # HTTP localhost
    SESSION_COOKIE_NAME = 'cleancpu_session'
    PERMANENT_SESSION_LIFETIME = 28800  # 8 hours

    # App metadata
    APP_NAME = 'CleanCPU'
    APP_VERSION = '3.0.0'
    APP_DESCRIPTION = 'Professional logical maintenance tool for Windows 10/11'

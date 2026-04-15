"""
Configuration for CleanCPU - Professional Windows Maintenance Tool.

All tuneable values can be overridden via environment variables without
touching this file.  See .env.example for the full list.

Deployment environments
-----------------------
local       Default.  Waitress on 127.0.0.1.  No proxy headers trusted.
staging     Behind a reverse proxy (Apache / nginx / AWS ALB).
            X-Forwarded-For / X-Forwarded-Proto headers are trusted.
production  Same as staging but SESSION_COOKIE_SECURE is forced True
            and the app is expected to be behind HTTPS.

Set the environment via:  CLEANCPU_ENV=production
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


def _parse_bool_env(name: str, default: bool) -> bool:
    """Parse a boolean environment variable (1/true/yes → True)."""
    val = os.environ.get(name, '').strip().lower()
    if not val:
        return default
    return val in ('1', 'true', 'yes', 'on')


def _parse_extra_hosts() -> list:
    """
    Parse CLEANCPU_ALLOWED_HOSTS env var into a list of host strings.

    Value is comma-separated.  Wildcards are supported: *.example.com
    Example: CLEANCPU_ALLOWED_HOSTS=mysite.com,*.mysite.com,10.0.0.5
    """
    raw = os.environ.get('CLEANCPU_ALLOWED_HOSTS', '')
    return [h.strip() for h in raw.split(',') if h.strip()]


class Config:
    """Flask application configuration."""

    # ------------------------------------------------------------------ #
    # Deployment environment                                               #
    # ------------------------------------------------------------------ #
    # local       — Waitress on 127.0.0.1, no proxy headers trusted
    # staging     — behind reverse proxy, proxy headers trusted
    # production  — behind HTTPS reverse proxy / AWS ALB
    ENVIRONMENT: str = os.environ.get('CLEANCPU_ENV', 'local').lower()

    # ------------------------------------------------------------------ #
    # Flask core                                                           #
    # ------------------------------------------------------------------ #
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'cleancpu-local-key')
    DEBUG = False

    # ------------------------------------------------------------------ #
    # Network binding (Waitress)                                           #
    # ------------------------------------------------------------------ #
    # In local mode stay on loopback.  In AWS set CLEANCPU_HOST=0.0.0.0
    HOST: str = os.environ.get('CLEANCPU_HOST', '127.0.0.1')
    PORT: int = int(os.environ.get('CLEANCPU_PORT', '5000'))
    THREADED = True

    # ------------------------------------------------------------------ #
    # Allowed Host headers (DNS-rebinding protection)                      #
    # ------------------------------------------------------------------ #
    # Each entry is matched against the request's Host header.
    # Wildcards (*.example.com) match any direct subdomain.
    # CLEANCPU_ALLOWED_HOSTS extends this list at runtime.
    ALLOWED_HOSTS: list = [
        # Production / LAN hostname
        'mantenimiento_logico_radec.com.mx',
        '*.radec.com.mx',
        # LAN IP of the WampServer host
        '192.168.136.130',
        # Loopback — always required for local health checks
        '127.0.0.1',
        'localhost',
    ] + _parse_extra_hosts()

    # ------------------------------------------------------------------ #
    # Reverse-proxy trust                                                  #
    # ------------------------------------------------------------------ #
    # When True, Werkzeug ProxyFix is applied and X-Forwarded-For /
    # X-Forwarded-Proto headers are trusted.
    # Automatically True for staging and production.
    TRUST_PROXY_HEADERS: bool = (
        ENVIRONMENT in ('staging', 'production')
        or _parse_bool_env('CLEANCPU_TRUST_PROXY', False)
    )

    # Number of trusted reverse-proxy hops (Werkzeug ProxyFix x_for / x_proto).
    # Set to 1 for a single Apache/nginx in front.  AWS ALB = 1.
    PROXY_COUNT: int = int(os.environ.get('CLEANCPU_PROXY_COUNT', '1'))

    # ------------------------------------------------------------------ #
    # Paths                                                                #
    # ------------------------------------------------------------------ #
    BASE_PATH = get_base_path()
    LOG_DIR = get_log_dir()
    REPORT_DIR = get_report_dir()

    # ------------------------------------------------------------------ #
    # Safety / timeout settings                                            #
    # ------------------------------------------------------------------ #
    COMMAND_TIMEOUT_DEFAULT = 120      # seconds
    COMMAND_TIMEOUT_LONG = 600         # for SFC, DISM, etc.
    COMMAND_TIMEOUT_VERY_LONG = 1800   # for full scans

    # ------------------------------------------------------------------ #
    # Session cookie                                                        #
    # ------------------------------------------------------------------ #
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Strict'
    # SESSION_COOKIE_SECURE: True only when traffic reaches the browser
    # over HTTPS.  In production behind HTTPS ALB/Apache this must be True.
    SESSION_COOKIE_SECURE: bool = ENVIRONMENT == 'production'
    SESSION_COOKIE_NAME = 'cleancpu_session'
    PERMANENT_SESSION_LIFETIME = 28800  # 8 hours

    # ------------------------------------------------------------------ #
    # App metadata                                                         #
    # ------------------------------------------------------------------ #
    APP_NAME = 'CleanCPU'
    APP_VERSION = '3.0.0'
    APP_DESCRIPTION = 'Professional logical maintenance tool for Windows 10/11'

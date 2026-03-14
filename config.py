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


def get_log_dir():
    """Get the log directory. Uses ProgramData on Windows, else a local 'logs' folder."""
    if sys.platform == 'win32':
        base = os.environ.get('PROGRAMDATA', 'C:\\ProgramData')
        log_dir = os.path.join(base, 'CleanCPU', 'logs')
    else:
        log_dir = os.path.join(get_base_path(), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    return log_dir


def get_report_dir():
    """Get the report output directory."""
    if sys.platform == 'win32':
        base = os.environ.get('PROGRAMDATA', 'C:\\ProgramData')
        report_dir = os.path.join(base, 'CleanCPU', 'reports')
    else:
        report_dir = os.path.join(get_base_path(), 'reports')
    os.makedirs(report_dir, exist_ok=True)
    return report_dir


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

    # App metadata
    APP_NAME = 'CleanCPU'
    APP_VERSION = '2.1.0'
    APP_DESCRIPTION = 'Professional logical maintenance tool for Windows 10/11'

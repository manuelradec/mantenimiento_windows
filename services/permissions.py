"""
Admin privilege validation and elevation utilities.
"""
import sys
import logging

logger = logging.getLogger('maintenance.permissions')


def is_admin():
    """Check if the current process has administrator privileges."""
    if sys.platform != 'win32':
        import os
        return os.getuid() == 0
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def get_elevation_info():
    """Return a dict describing the current privilege state."""
    admin = is_admin()
    return {
        'is_admin': admin,
        'platform': sys.platform,
        'message': 'Running with administrator privileges.' if admin
                   else 'Running WITHOUT administrator privileges. Some features will be unavailable.',
    }


def request_elevation():
    """
    Attempt to restart the current process with elevated privileges.
    Only works on Windows. Returns False if elevation cannot be performed.
    """
    if sys.platform != 'win32':
        logger.warning("Elevation not supported on this platform.")
        return False

    if is_admin():
        logger.info("Already running as admin.")
        return True

    try:
        import ctypes
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1
        )
        return True
    except Exception as e:
        logger.error(f"Failed to elevate: {e}")
        return False

# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for CleanCPU v3.0.0
#
# Build:
#   pip install -r requirements-build.txt
#   pyinstaller mantenimiento_windows.spec
#
# Output: dist\CleanCPU.exe

import os

# Collect all template and static files (non-Python data files Flask needs at runtime)
templates_dir = 'templates'
static_dir = 'static'

a = Analysis(
    ['server.py'],
    pathex=[os.getcwd()],
    binaries=[],
    datas=[
        # Only non-Python files go here. Flask reads these at runtime from disk.
        (templates_dir, 'templates'),
        (static_dir, 'static'),
        # Excel template for RADEC form
        ('templates_data', 'templates_data'),
        # Google credentials (if present)
        ('credentials', 'credentials'),
    ],
    hiddenimports=[
        # Flask and WSGI server
        'flask',
        'jinja2',
        'jinja2.ext',
        'markupsafe',
        'psutil',
        'waitress',
        'waitress.task',
        'waitress.channel',
        'waitress.server',
        # Config and app factory
        'config',
        'app',
        # Core infrastructure
        'core',
        'core.action_registry',
        'core.policy_engine',
        'core.job_runner',
        'core.persistence',
        'core.security',
        # Service modules
        'services',
        'services.command_runner',
        'services.permissions',
        'services.system_info',
        'services.cleanup',
        'services.repair',
        'services.network_tools',
        'services.windows_update',
        'services.power_tools',
        'services.graphics_tools',
        'services.antivirus_tools',
        'services.restore_tools',
        'services.drivers',
        'services.reports',
        'services.event_viewer',
        'services.smart_app_control',
        # Core infrastructure (additional)
        'core.governance',
        'core.snapshots',
        # Maintenance and reporting
        'services.maintenance_report',
        'services.security_audit',
        'services.system_inventory',
        'services.office_tools',
        # Routes
        'routes.office',
        # Route modules
        'routes',
        'routes.logs',
        'routes.scheduled_restart',
        'routes.maintenance',
        'routes.dashboard',
        'routes.diagnostics',
        'routes.cleanup',
        'routes.repair',
        'routes.network',
        'routes.update',
        'routes.power',
        'routes.drivers',
        'routes.security',
        'routes.reports',
        'routes.advanced',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'unittest',
        'pydoc',
        'doctest',
        'test',
        'xmlrpc',
        'pdb',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='CleanCPU',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # No console window (--windowed)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,         # Request UAC elevation on launch
)

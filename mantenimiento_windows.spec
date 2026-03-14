# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for CleanCPU v2.1
#
# Build:
#   pip install flask psutil pyinstaller
#   pyinstaller mantenimiento_windows.spec
#
# Output: dist\CleanCPU.exe

import os

# Collect all template and static files (non-Python data files Flask needs at runtime)
templates_dir = 'templates'
static_dir = 'static'

a = Analysis(
    ['app.py'],
    pathex=[os.getcwd()],
    binaries=[],
    datas=[
        # Only non-Python files go here. Flask reads these at runtime from disk.
        (templates_dir, 'templates'),
        (static_dir, 'static'),
    ],
    hiddenimports=[
        # Flask and dependencies
        'flask',
        'jinja2',
        'jinja2.ext',
        'markupsafe',
        'psutil',
        # Our config (imported by app.py, but explicit for safety)
        'config',
        # Service modules (Python code - PyInstaller bundles these as compiled .pyc)
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
        # Route modules
        'routes',
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
    console=True,           # True = muestra consola con la URL del servidor
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,         # Pide elevacion UAC al ejecutar
)

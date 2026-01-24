# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Trace Python backend.

This creates a standalone executable that can be bundled with the Electron app.

Build with:
    uv run pyinstaller trace.spec --distpath electron/python-dist

The output will be in electron/python-dist/trace/
"""

import os
import sys
from pathlib import Path

# Get the project root directory
project_root = Path(SPECPATH)

# Find sqlite-vec extension
sqlite_vec_path = None
try:
    import sqlite_vec
    sqlite_vec_dir = Path(sqlite_vec.__file__).parent
    # Look for the .dylib or .so file
    for ext in ['*.dylib', '*.so', '*.pyd']:
        for f in sqlite_vec_dir.glob(ext):
            sqlite_vec_path = str(f)
            break
        if sqlite_vec_path:
            break
except ImportError:
    print("Warning: sqlite-vec not found")

# Collect all data files
datas = []

# Include sqlite-vec extension if found
if sqlite_vec_path:
    datas.append((sqlite_vec_path, 'sqlite_vec'))

# Include database migrations SQL files
migrations_dir = project_root / 'src' / 'db' / 'migrations'
if migrations_dir.exists():
    for sql_file in migrations_dir.glob('*.sql'):
        datas.append((str(sql_file), 'src/db/migrations'))

# Hidden imports for PyObjC frameworks used by the app
hiddenimports = [
    # PyObjC core
    'objc',
    'Foundation',
    'Cocoa',

    # PyObjC frameworks used for capture
    'Quartz',
    'Quartz.CoreGraphics',
    'Quartz.ImageIO',
    'CoreLocation',
    'ScreenCaptureKit',

    # PyObjC framework bindings
    'pyobjc_framework_Cocoa',
    'pyobjc_framework_Quartz',
    'pyobjc_framework_CoreLocation',
    'pyobjc_framework_ScreenCaptureKit',

    # Application modules
    'src',
    'src.trace_app',
    'src.trace_app.cli',
    'src.trace_app.ipc',
    'src.trace_app.ipc.server',
    'src.trace_app.ipc.handlers',
    'src.trace_app.ipc.chat_handlers',
    'src.trace_app.ipc.service_handlers',
    'src.core',
    'src.core.paths',
    'src.core.services',
    'src.capture',
    'src.capture.daemon',
    'src.capture.screenshots',
    'src.capture.foreground',
    'src.capture.now_playing',
    'src.capture.media_remote',
    'src.capture.location',
    'src.capture.urls',
    'src.capture.events',
    'src.capture.dedup',
    'src.db',
    'src.db.migrations',
    'src.db.vectors',
    'src.summarize',
    'src.jobs',
    'src.jobs.note_recovery',
    'src.revise',
    'src.chat',

    # Dependencies
    'sqlite_vec',
    'pydantic',
    'fire',
    'openai',
    'apscheduler',
    'PIL',
    'fitz',  # PyMuPDF
    'dotenv',
    'tiktoken',
    'tiktoken_ext',
    'tiktoken_ext.openai_public',
    'mss',
    'mss.darwin',
]

# Collect submodules for packages that need it
collect_submodules = [
    'pyobjc',
    'pyobjc_framework_Cocoa',
    'pyobjc_framework_Quartz',
    'pyobjc_framework_CoreLocation',
    'pyobjc_framework_ScreenCaptureKit',
    'PIL',
    'fitz',
    'tiktoken',
    'apscheduler',
    'pydantic',
    'openai',
    'mss',
]

# Analysis
a = Analysis(
    ['src/trace_app/cli.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude test modules
        'pytest',
        'test',
        'tests',
        # Exclude unused modules
        'tkinter',
        'matplotlib',
        'numpy.testing',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# Collect submodules
for module in collect_submodules:
    try:
        from PyInstaller.utils.hooks import collect_submodules as cs
        a.hiddenimports.extend(cs(module))
    except Exception as e:
        print(f"Warning: Could not collect submodules for {module}: {e}")

# PYZ archive
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# Executable
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='trace',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # Disable UPX compression for macOS compatibility
    console=True,  # We need console for stdio IPC
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,  # Build for current architecture
    codesign_identity=None,
    entitlements_file=None,
)

# Collect all files
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='trace',
)

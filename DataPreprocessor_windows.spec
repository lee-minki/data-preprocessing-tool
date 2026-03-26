# -*- mode: python ; coding: utf-8 -*-

from version import __version__

a = Analysis(
    ['gui_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('MANUAL.html', '.'),
        ('MANUAL.md', '.'),
        ('developer_info.json', '.'),
        ('data_preprocessor.py', '.'),
        ('preset_manager.py', '.'),
        ('version.py', '.'),
        ('CHANGELOG.md', '.'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name=f'DataPreprocessor_v{__version__}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
)

# -*- mode: python ; coding: utf-8 -*-
import os, sys

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['PyQt5.sip', 'PIL._tkinter_finder']
hiddenimports += collect_submodules('watermark_remover')
hiddenimports += collect_submodules('cv2')


a = Analysis(
    ['run.py'],
    pathex=[os.path.dirname(os.path.abspath(__file__))],
    binaries=[],
    datas=[
        (resource_path('watermark_remover/logo.png'), 'watermark_remover'),
    ],
    hiddenimports=hiddenimports,
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
    name='WatermarkRemover',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

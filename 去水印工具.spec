# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['PyQt5.sip', 'PIL._tkinter_finder']
hiddenimports += collect_submodules('watermark_remover')
hiddenimports += collect_submodules('cv2')


a = Analysis(
    ['D:\\works\\PycharmProjects\\python-utils\\run.py'],
    pathex=[],
    binaries=[],
    datas=[('D:\\works\\PycharmProjects\\python-utils\\watermark_remover\\logo.png', 'watermark_remover')],
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
    name='去水印工具',
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
    icon=['D:\\works\\PycharmProjects\\python-utils\\watermark_remover\\logo.ico'],
)

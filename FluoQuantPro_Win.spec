# -*- mode: python ; coding: utf-8 -*-
import sys
import os
from PyInstaller.utils.hooks import collect_submodules

# 动态收集所有核心模块
hidden_imports = collect_submodules('src')
hidden_imports += [
    'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets', 'PySide6.QtSvg',
    'numpy', 'cv2', 'tifffile', 'qimage2ndarray', 'skimage', 
    'scipy', 'pywt', 'matplotlib', 'matplotlib.backends.backend_qtagg'
]

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('resources', 'resources'), 
        ('src/resources/translations.json', 'src/resources'), 
        ('FluoQuantPro_User_Manual.html', '.'), 
        ('manual.html', '.'), 
        ('project.json', '.')
    ],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'unittest', 'pydoc', 'IPython', 'notebook'],
    noarchive=False,
    optimize=2, # 使用更高级别的优化
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='FluoQuantPro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True, # 使用 UPX 压缩减小单文件体积
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False, # 隐藏控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['resources/icon.ico'],
)

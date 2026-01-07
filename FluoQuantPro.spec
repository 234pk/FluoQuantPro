# -*- mode: python ; coding: utf-8 -*-
import sys
import os
from PyInstaller.utils.hooks import collect_submodules

# 动态收集 src 下的所有子模块，防止 ModuleNotFoundError
hidden_imports = collect_submodules('src')
hidden_imports += [
    'PySide6', 'numpy', 'cv2', 'tifffile', 'qimage2ndarray', 'skimage', 
    'scipy', 'pywt', 'matplotlib', 'matplotlib.backends.backend_qtagg',
    'src.gui.export_settings_dialog' # 显式添加之前丢失的模块
]

a = Analysis(
    ['main.py'],
    pathex=['.'], # 设置为根目录
    binaries=[],
    datas=[
        ('resources', 'resources'), 
        ('src/resources/translations.json', 'src/resources'), 
        ('FluoQuantPro_User_Manual.html', '.'), 
        ('manual.html', '.'), 
        ('change_log.md', '.'), 
        ('docs', 'docs'), 
        ('project.json', '.')
    ],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter'],
    noarchive=False,
    optimize=0,
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
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['resources/icon.ico'],
)

if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='FluoQuantPro.app',
        icon='resources/icon.icns',
        bundle_identifier='com.fluoquantpro.app',
        info_plist={
            'NSHighResolutionCapable': 'True',
            'NSRequiresAquaSystemAppearance': 'False',
            'CFBundleShortVersionString': '1.1.0',
            'CFBundleVersion': '1.1.0',
            'CFBundleName': 'FluoQuantPro',
            'CFBundleDisplayName': 'FluoQuantPro',
            'CFBundleExecutable': 'FluoQuantPro',
            'CFBundlePackageType': 'APPL',
            'LSMinimumSystemVersion': '10.13.0',
            'NSAppleEventsUsageDescription': 'FluoQuantPro needs access to Apple Events for better system integration.',
        }
    )

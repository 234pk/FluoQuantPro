# -*- mode: python ; coding: utf-8 -*-
import sys
import os
from PyInstaller.utils.hooks import collect_submodules

# 动态收集 src 下的所有子模块
hidden_imports = collect_submodules('src')
hidden_imports += [
    'PySide6', 'numpy', 'cv2', 'tifffile', 'qimage2ndarray', 'skimage', 
    'scipy', 'pywt', 'matplotlib', 'matplotlib.backends.backend_qtagg',
    'src.gui.export_settings_dialog'
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

# ---------------------------------------------------------
# macOS 特定配置：使用 Onedir 模式以避免启动挂起和兼容性问题
# ---------------------------------------------------------
if sys.platform == 'darwin':
    # 1. 创建不包含二进制文件的可执行文件引导程序
    exe = EXE(
        pyz,
        a.scripts,
        [], # macOS Onedir 模式不在此处打包二进制文件
        exclude_binaries=True,
        name='FluoQuantPro',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False, # macOS 上禁用 UPX 以提高兼容性
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )

    # 2. 收集所有依赖到一个目录 (Onedir)
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        a.zipfiles,
        strip=False,
        upx=False,
        upx_exclude=[],
        name='FluoQuantPro',
    )

    # 3. 将该目录打包为 macOS .app Bundle
    app = BUNDLE(
        coll,
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

# ---------------------------------------------------------
# Windows/Linux 默认配置：使用 Onefile 模式 (单文件 EXE)
# ---------------------------------------------------------
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        a.zipfiles,
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

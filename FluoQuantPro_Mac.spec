# -*- mode: python ; coding: utf-8 -*-
import sys
import os
from PyInstaller.utils.hooks import collect_submodules

# 动态收集所有相关子模块
hidden_imports = collect_submodules('src')
hidden_imports += collect_submodules('skimage')
hidden_imports += collect_submodules('scipy')
hidden_imports += [
    'unittest',
    'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets', 'PySide6.QtSvg',
    'numpy', 'cv2', 'tifffile', 'qimage2ndarray', 'skimage', 
    'scipy', 'pywt', 'matplotlib', 'matplotlib.backends.backend_qtagg',
    'src.gui.export_settings_dialog',
    # 补充相关子模块
    'skimage.feature._orb_descriptor_positions',
    'skimage.filters.rank.core_cy_3d',
    'skimage.morphology._max_tree',
    'skimage.morphology.disk_decompositions',
    'skimage.morphology.ball_decompositions',
    'scipy.special.cython_special',
    'scipy.linalg.cython_blas',
    'scipy.linalg.cython_lapack',
    'scipy.optimize',
    'scipy.ndimage',
    'scipy.special',
    'scipy.sparse',
    'scipy.stats',
    'scipy.linalg',
    'scipy.spatial',
    'scipy.integrate',
    'scipy.signal',
    'scipy.fft',
    'pandas',
    'numpy',
    'numexpr',
    'numba',
    'pyarrow',
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
    excludes=['tkinter', 'ipython', 'notebook', 'jedi'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# ---------------------------------------------------------
# macOS 特定配置：使用 Onedir 模式以避免启动挂起和兼容性问题
# ---------------------------------------------------------

# 1. 创建不包含二进制文件的可执行文件引导程序
exe = EXE(
    pyz,
    a.scripts,
    [], # macOS Onedir 模式不在此处打包二进制文件
    exclude_binaries=True,
    name='FluoQuantPro',
    debug=True,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False, # macOS 上禁用 UPX 以提高兼容性
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file='entitlements.plist',
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
        'CFBundleShortVersionString': '3.0.0',
        'CFBundleVersion': '3.0.0',
        'CFBundleName': 'FluoQuantPro',
        'CFBundleDisplayName': 'FluoQuantPro',
        'CFBundleExecutable': 'FluoQuantPro',
        'CFBundlePackageType': 'APPL',
        'LSMinimumSystemVersion': '10.13.0',
        'NSAppleEventsUsageDescription': 'FluoQuantPro needs access to Apple Events for better system integration.',
        'NSCameraUsageDescription': 'FluoQuantPro does not use the camera but needs declaration for some libraries.',
        'NSMicrophoneUsageDescription': 'FluoQuantPro does not use the microphone but needs declaration for some libraries.',
        'NSPhotoLibraryUsageDescription': 'FluoQuantPro needs access to save and open images.',
        'LSSupportsOpeningDocumentsInPlace': 'True',
    }
)

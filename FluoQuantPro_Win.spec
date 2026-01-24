# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# 明确定义隐藏依赖，防止打包后找不到模块
hidden_imports = sorted(set([
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PySide6.QtPrintSupport',
    'PySide6.QtOpenGLWidgets',
    'numpy',
    'cv2',
    'tifffile',
    'imagecodecs',
    'matplotlib',
    'matplotlib.pyplot',
    'matplotlib.backends.backend_qtagg',
    'scipy',
    'scipy.stats',
    'scipy.ndimage',
    'scipy.optimize',
    'skimage',
    'skimage.measure',
    'skimage.filters',
    'skimage.morphology',
    'skimage.segmentation',
    'skimage.exposure',
    'skimage.restoration',
    'qimage2ndarray',
    'src.gui.canvas_view',
    'src.gui.multi_view',
    'src.gui.roi_toolbox',
    'src.gui.colocalization_panel',
    'src.gui.tools',
    'src.core.data_model',
    'src.core.analysis',
    'src.core.algorithms',
    'src.core.overlap_analyzer',
    'certifi',
    'tencentcloud',
    'tencentcloud.common',
    'tencentcloud.log',
    'google.protobuf',
    *collect_submodules('qimage2ndarray'),
    *collect_submodules('scipy'),
    *collect_submodules('skimage'),
    *collect_submodules('imagecodecs'),
]))

a = Analysis(
    ['main.py'],
    pathex=['.', 'src'], # 将 src 加入搜索路径
    binaries=[],
    datas=[
        ('resources', 'resources'), 
        ('src/resources/translations.json', 'src/resources'), 
        ('FluoQuantPro_User_Manual.html', '.'), 
        ('project.json', '.')
    ],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'ipython', 'notebook', 'jedi', 'PyQt5', 'PyQt6'], # 排除不必要的库
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# 启动画面配置
splash = Splash(
    'resources/icon.png',  # 使用 icon 作为启动图
    binaries=a.binaries,
    datas=a.datas,
    text_pos=(10, 50),
    text_size=12,
    text_color='white',
    always_on_top=True,
)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    splash,
    splash.binaries,
    name='FluoQuantPro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False, # 禁用 UPX 以提高启动速度并避免部分杀毒软件误报
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False, # 最终版关闭控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='resources/icon.ico'
)

# -*- mode: python ; coding: utf-8 -*-
import sys
import os

a = Analysis(
    ['main.py'],
    pathex=['src'],
    binaries=[],
    datas=[('resources', 'resources'), ('src/resources/translations.json', 'src/resources'), ('FluoQuantPro_User_Manual.html', '.'), ('manual.html', '.'), ('change_log.md', '.'), ('docs', 'docs'), ('project.json', '.')],
    hiddenimports=['PySide6', 'numpy', 'cv2', 'tifffile', 'qimage2ndarray', 'skimage', 'scipy', 'skimage.feature._orb_descriptor_positions', 'skimage.filters.rank.core_cy_3d', 'skimage.morphology._max_tree', 'skimage.morphology.disk_decompositions', 'skimage.morphology.ball_decompositions', 'pywt', 'scipy.special.cython_special', 'scipy.linalg.cython_blas', 'scipy.linalg.cython_lapack', 'sklearn.utils._cython_blas', 'sklearn.neighbors._partition_nodes', 'sklearn.tree._utils'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'pandas'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='FluoQuantPro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['resources\\icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='FluoQuantPro',
)

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='FluoQuantPro.app',
        icon='resources/icon.png',
        bundle_identifier='com.fluoquantpro.app',
    )

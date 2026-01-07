# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[('resources', 'resources'), ('src/resources/translations.json', 'src/resources')],
    hiddenimports=['skimage', 'skimage.feature._orb_descriptor_positions', 'skimage.filters.rank.core_cy_3d', 'skimage.morphology._max_tree', 'skimage.morphology.disk_decompositions', 'skimage.morphology.ball_decompositions', 'pywt', 'scipy.special.cython_special', 'scipy.linalg.cython_blas', 'scipy.linalg.cython_lapack'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'ipython', 'notebook', 'jedi'],
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
    version='version_info.txt',
    icon=['resources\\icon.ico'],
)

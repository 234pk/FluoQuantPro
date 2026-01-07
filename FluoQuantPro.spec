# -*- mode: python ; coding: utf-8 -*-


from PyInstaller.utils.hooks import collect_submodules

hidden_imports = collect_submodules('src')
hidden_imports += collect_submodules('skimage')
hidden_imports += collect_submodules('scipy')
hidden_imports += [
    'unittest',
    'pywt',
    'scipy.special.cython_special',
    'scipy.linalg.cython_blas',
    'scipy.linalg.cython_lapack',
    'matplotlib.backends.backend_qtagg',
    'PySide6.QtSvg',
]

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[('resources', 'resources'), ('src/resources/translations.json', 'src/resources')],
    hiddenimports=hidden_imports,
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
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='version_info.txt',
    icon=['resources\\icon.ico'],
)

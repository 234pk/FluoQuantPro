# -*- mode: python ; coding: utf-8 -*-


from PyInstaller.utils.hooks import collect_submodules

# 动态收集所有相关子模块，确保动态导入不遗漏
hidden_imports = collect_submodules('src')
hidden_imports += collect_submodules('skimage')
hidden_imports += collect_submodules('scipy')
hidden_imports += collect_submodules('pandas')
hidden_imports += collect_submodules('matplotlib')

hidden_imports += [
    'unittest',
    'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets', 'PySide6.QtSvg',
    'numpy', 'numpy._core', 'cv2', 'tifffile', 'qimage2ndarray', 'skimage', 
    'scipy', 'pywt', 'matplotlib', 'matplotlib.backends.backend_qtagg',
    'scipy.special.cython_special',
    'scipy.linalg.cython_blas',
    'scipy.linalg.cython_lapack',
    'scipy.special.beta',
    'scipy.sparse.csr_array',
    'pandas.core.internals.Block',
    'pandas',
    'psutil',
    'pyarrow',
    'networkx',
    'six',
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
        ('README.md', '.'),
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
    icon=['resources/icon.ico'],
)

import PyInstaller.__main__
import os
import shutil
import sys

def build():
    print("Cleaning previous build...")
    if os.path.exists('dist'): shutil.rmtree('dist')
    if os.path.exists('build'): shutil.rmtree('build')

    print("Starting PyInstaller Build...")
    
    # Define build arguments
    args = [
        'main.py',
        '--name=FluoQuantPro',
        '--windowed',          # GUI mode (no console)
        '--onedir',            # Directory output (Faster startup)
        '--noconfirm',
        '--clean',
        '--icon=resources/icon.ico', # EXE Icon
        '--add-data=resources;resources', # Include resources folder
        '--add-data=src/resources/translations.json;src/resources', # Include translations
        '--add-data=FluoQuantPro_User_Manual.html;.', # Include user manual
        '--add-data=manual.html;.', # Include secondary manual if exists
        '--add-data=change_log.md;.', # Include change log
        
        # Optimization: Exclude unnecessary modules to reduce size and startup time
        '--exclude-module=tkinter',
        '--exclude-module=matplotlib', # Unless used? (HistogramWidget uses QPainter, not matplotlib)
        '--exclude-module=pandas',     # Unless used? (Export uses csv module, not pandas)
        
        # Ensure critical modules are included
        '--hidden-import=PySide6',
        '--hidden-import=numpy',
        '--hidden-import=cv2',
        '--hidden-import=tifffile',
        '--hidden-import=qimage2ndarray',
        '--hidden-import=skimage',
        '--hidden-import=scipy',
        
        # Paths
        '--paths=src',
    ]
    
    PyInstaller.__main__.run(args)
    
    print("Build Complete.")
    print(f"Executable is located at: {os.path.abspath('dist/FluoQuantPro/FluoQuantPro.exe')}")

if __name__ == "__main__":
    try:
        build()
    except ImportError:
        print("Error: PyInstaller is not installed. Please run: pip install pyinstaller")
    except Exception as e:
        print(f"Build Failed: {e}")

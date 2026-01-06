import PyInstaller.__main__
import os
import shutil
import sys

def build():
    print("Cleaning previous build...")
    if os.path.exists('dist'): shutil.rmtree('dist')
    if os.path.exists('build'): shutil.rmtree('build')

    print("Starting PyInstaller Build using FluoQuantPro.spec...")
    
    # Run PyInstaller with the spec file
    # This ensures consistency between local builds and CI/CD
    PyInstaller.__main__.run([
        'FluoQuantPro.spec',
        '--noconfirm',
        '--clean'
    ])
    
    print("Build Complete.")
    print(f"Executable is located at: {os.path.abspath('dist/FluoQuantPro.exe')}")

if __name__ == "__main__":
    try:
        build()
    except ImportError:
        print("Error: PyInstaller is not installed. Please run: pip install pyinstaller")
    except Exception as e:
        print(f"Build Failed: {e}")

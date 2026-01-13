import os
import sys
import subprocess
import shutil

def build():
    # 1. Project Root
    project_root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_root)
    
    # Set Nuitka cache directory via environment variable
    os.environ["NUITKA_CACHE_DIR"] = os.path.join(project_root, ".nuitka-cache")
    if not os.path.exists(os.environ["NUITKA_CACHE_DIR"]):
        os.makedirs(os.environ["NUITKA_CACHE_DIR"])

    # 2. Command definition
    version = "3.0"
    command = [
        sys.executable, "-m", "nuitka",
        "--onefile",
        "--show-progress",
        "--show-memory",
        "--enable-plugins=pyside6",
        "--assume-yes-for-downloads",
        
        # UI related
        "--windows-console-mode=disable",
        "--windows-icon-from-ico=resources/icon.ico",
        
        # Version Info
        f"--file-version={version}",
        f"--product-version={version}",
        "--company-name=FluoQuant",
        "--product-name=FluoQuant Pro",
        "--file-description=Advanced Fluorescence Image Analysis Pro",
        "--copyright=Copyright 2026 FluoQuant",
        
        # Include data files
        "--include-data-dir=resources=resources",
        "--include-data-dir=src/resources=src/resources",
        
        # Necessary Packages
        "--include-package=imagecodecs",
        "--include-package=tifffile",
        "--include-package-data=matplotlib",
        
        # Optimization
        "--mingw64", # Use MinGW64 to avoid MSVC environment issues
        "--lto=no",   # Disable LTO to avoid linking complexities
        "--prefer-source-code",
        "--clean-cache=all",
        
        # Main entry point
        "main.py"
    ]

    # Optional: Onefile mode (can be slow to start, but convenient)
    # command.append("--onefile")

    print(f"Starting Nuitka build for FluoQuantPro...")
    print(f"Command: {' '.join(command)}")
    
    try:
        subprocess.run(command, check=True)
        print("\nBuild successful!")
        
        # In onefile mode, the output is main.exe
        exe_name = "main.exe"
        target_name = "FluoQuantPro.exe"
        if os.path.exists(exe_name):
            if os.path.exists(target_name):
                os.remove(target_name)
            os.rename(exe_name, target_name)
            print(f"Output available as: {target_name}")
            
    except subprocess.CalledProcessError as e:
        print(f"\nBuild failed with error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    build()

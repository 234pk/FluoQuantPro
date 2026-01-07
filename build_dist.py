import PyInstaller.__main__
import os
import shutil
import sys

def build():
    # 1. Cleanup
    if os.path.exists("dist"):
        try:
            shutil.rmtree("dist")
        except Exception as e:
            print(f"Warning: Could not clean dist folder: {e}")
            
    if os.path.exists("build"):
        try:
            shutil.rmtree("build")
        except Exception as e:
            print(f"Warning: Could not clean build folder: {e}")

    # 2. Version Info (create version_info.txt)
    version_info = """
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(3, 0, 3, 0),
    prodvers=(3, 0, 3, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'FluoQuantPro Team'),
        StringStruct(u'FileDescription', u'FluoQuantPro Image Analysis Software'),
        StringStruct(u'FileVersion', u'3.0.3.0'),
        StringStruct(u'InternalName', u'FluoQuantPro'),
        StringStruct(u'LegalCopyright', u'Copyright (c) 2024 FluoQuantPro Team'),
        StringStruct(u'OriginalFilename', u'FluoQuantPro.exe'),
        StringStruct(u'ProductName', u'FluoQuantPro'),
        StringStruct(u'ProductVersion', u'3.0.3.0')])
      ]), 
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""
    with open("version_info.txt", "w") as f:
        f.write(version_info)

    # 3. Check for required resources before building
    required_files = [
        "resources",
        "src/resources/translations.json",
        "FluoQuantPro_User_Manual.html",
        "project.json"
    ]
    for f in required_files:
        if not os.path.exists(f):
            print(f"Error: Required file/folder '{f}' is missing!")
            sys.exit(1)

    # 4. Run PyInstaller
    print("Starting PyInstaller Build using FluoQuantPro.spec...")
    
    # 使用 subprocess 调用 pyinstaller 确保环境干净
    # 所有的 hidden-imports, datas, options 都应该在 Spec 文件中管理
    try:
        subprocess.check_call([
            sys.executable, "-m", "PyInstaller",
            "FluoQuantPro.spec",
            "--clean",
            "--noconfirm"
        ])
    except subprocess.CalledProcessError as e:
        print(f"Build failed with error code {e.returncode}")
        sys.exit(e.returncode)

    # 5. Create Readme (if not already there)
    readme_path = "dist/README.txt"
    if not os.path.exists("dist"):
        os.makedirs("dist")
        
    with open(readme_path, "w") as f:
        f.write("FluoQuantPro v3.0.3\n\n")
        f.write("Usage:\n")
        f.write("1. Double click FluoQuantPro.exe to launch.\n")
        f.write("2. No installation required.\n")
        f.write("3. For detailed instructions, see FluoQuantPro_User_Manual.html.\n")

    # 5. Copy Manual is now handled by Spec file's 'datas'
    # shutil.copy("FluoQuantPro_User_Manual.html", "dist/FluoQuantPro_User_Manual.html")
    
    # 6. Cleanup temp files
    if os.path.exists("version_info.txt"):
        os.remove("version_info.txt")

    print("Build Complete.")
    print(f"Executable: {os.path.abspath('dist/FluoQuantPro.exe')}")

if __name__ == "__main__":
    build()

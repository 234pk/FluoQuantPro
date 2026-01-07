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
    filevers=(3, 0, 0, 0),
    prodvers=(3, 0, 0, 0),
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
        StringStruct(u'FileVersion', u'3.0.0.0'),
        StringStruct(u'InternalName', u'FluoQuantPro'),
        StringStruct(u'LegalCopyright', u'Copyright (c) 2024 FluoQuantPro Team'),
        StringStruct(u'OriginalFilename', u'FluoQuantPro.exe'),
        StringStruct(u'ProductName', u'FluoQuantPro'),
        StringStruct(u'ProductVersion', u'3.0.0.0')])
      ]), 
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""
    with open("version_info.txt", "w") as f:
        f.write(version_info)

    # 3. Run PyInstaller
    print("Starting PyInstaller Build using FluoQuantPro.spec...")
    
    # 直接使用 Spec 文件，不再重复传递命令行参数
    # 所有的 hidden-imports, datas, options 都应该在 Spec 文件中管理
    args = [
        'FluoQuantPro.spec',
        '--clean',
        '--noconfirm',
    ]
    
    PyInstaller.__main__.run(args)

    # 4. Create Readme
    with open("dist/README.txt", "w") as f:
        f.write("FluoQuantPro v3.0\n\n")
        f.write("Usage:\n")
        f.write("1. Double click FluoQuantPro.exe to launch.\n")
        f.write("2. No installation required.\n")
        f.write("3. For detailed instructions, see FluoQuantPro_User_Manual.html.\n")

    # 5. Copy Manual
    if os.path.exists("FluoQuantPro_User_Manual.html"):
        shutil.copy("FluoQuantPro_User_Manual.html", "dist/FluoQuantPro_User_Manual.html")
    
    # 6. Cleanup temp files
    if os.path.exists("version_info.txt"):
        os.remove("version_info.txt")

    print("Build Complete.")
    print(f"Executable: {os.path.abspath('dist/FluoQuantPro.exe')}")

if __name__ == "__main__":
    build()

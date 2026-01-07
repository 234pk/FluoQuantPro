import PyInstaller.__main__
import os
import shutil
import sys
import time
import io

# 强制设置输出编码为 UTF-8，解决 Windows CI 环境下的 UnicodeEncodeError
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def check_pre_build():
    """打包前全面检查 / Pre-build comprehensive check"""
    print("\n[1/3] 执行打包前检查 / Executing pre-build checks...")
    
    # 1. 验证关键目录和文件
    required_paths = [
        'main.py',
        'src/gui/export_settings_dialog.py',
        'resources',
        'src/resources/translations.json'
    ]
    for path in required_paths:
        if not os.path.exists(path):
            print(f"  ❌ 错误: 找不到关键路径: {path}")
            return False
        print(f"  ✅ 找到: {path}")

    # 2. 验证依赖环境
    try:
        import PySide6
        import numpy
        import cv2
        print(f"  ✅ 环境检查通过 (PySide6 v{PySide6.__version__})")
    except ImportError as e:
        print(f"  ❌ 环境检查失败: 缺少依赖 {e}")
        return False
        
    return True

def build():
    """执行打包 / Execute Build"""
    print("\n[2/3] 开始生产环境模式打包 / Starting production build...")
    start_time = time.time()
    
    if os.path.exists('dist'): shutil.rmtree('dist')
    if os.path.exists('build'): shutil.rmtree('build')

    try:
        PyInstaller.__main__.run([
            'FluoQuantPro.spec',
            '--noconfirm',
            '--clean'
        ])
        
        duration = time.time() - start_time
        print(f"  ✅ 打包完成 / Build completed, Time: {duration:.2f}s")
        return True
    except Exception as e:
        print(f"  ❌ 打包过程出错 / Error during build: {e}")
        return False

def verify_post_build():
    """打包后验证 / Post-build verification"""
    print("\n[3/3] 执行打包后验证 / Executing post-build verification...")
    
    exe_path = 'dist/FluoQuantPro.exe'
    if sys.platform == 'darwin':
        exe_path = 'dist/FluoQuantPro.app'
        
    if not os.path.exists(exe_path):
        print(f"  ❌ 验证失败 / Verification failed: {exe_path} not found")
        return False
        
    size_mb = os.path.getsize(exe_path) / (1024 * 1024) if os.path.isfile(exe_path) else 0
    print(f"  ✅ 目标文件存在 / Target exists: {exe_path} ({size_mb:.2f} MB)")
    
    print("\n✨ 所有检查通过！打包产物已准备就绪 / All checks passed! Build ready.")
    return True

if __name__ == "__main__":
    print("="*50)
    print(" FluoQuantPro 标准化打包流程 / Standardized Build Process ")
    print("="*50)
    
    if check_pre_build():
        if build():
            if verify_post_build():
                sys.exit(0)
    
    print("\n❌ 打包流程因错误终止。")
    sys.exit(1)

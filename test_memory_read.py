
import os
import sys
import time

def get_memory_mb():
    current_mb = 0.0
    print(f"Platform: {sys.platform}")
    
    # 1. Try psutil
    try:
        import psutil
        print("psutil: Available")
        process = psutil.Process()
        mem_info = process.memory_info()
        print(f"psutil rss: {mem_info.rss / 1024 / 1024:.2f} MB")
        current_mb = mem_info.rss / (1024 * 1024)
    except ImportError:
        print("psutil: Not installed")
    except Exception as e:
        print(f"psutil error: {e}")

    # 2. Try Windows Fallback
    if sys.platform == 'win32':
        try:
            import ctypes
            from ctypes import wintypes
            
            class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
                _fields_ = [
                    ('cb', wintypes.DWORD),
                    ('PageFaultCount', wintypes.DWORD),
                    ('PeakWorkingSetSize', wintypes.SIZE_T),
                    ('WorkingSetSize', wintypes.SIZE_T),
                    ('QuotaPeakPagedPoolUsage', wintypes.SIZE_T),
                    ('QuotaPagedPoolUsage', wintypes.SIZE_T),
                    ('QuotaPeakNonPagedPoolUsage', wintypes.SIZE_T),
                    ('QuotaNonPagedPoolUsage', wintypes.SIZE_T),
                    ('PagefileUsage', wintypes.SIZE_T),
                    ('PeakPagefileUsage', wintypes.SIZE_T),
                    ('PrivateUsage', wintypes.SIZE_T),
                ]
                
            p = ctypes.windll.kernel32.GetCurrentProcess()
            mem_struct = PROCESS_MEMORY_COUNTERS_EX()
            mem_struct.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX)
            
            # Need Psapi.dll
            psapi = ctypes.windll.psapi
            if psapi.GetProcessMemoryInfo(p, ctypes.byref(mem_struct), ctypes.sizeof(mem_struct)):
                print(f"Windows API WorkingSetSize: {mem_struct.WorkingSetSize / 1024 / 1024:.2f} MB")
                print(f"Windows API PrivateUsage: {mem_struct.PrivateUsage / 1024 / 1024:.2f} MB")
                if current_mb == 0:
                    current_mb = mem_struct.PrivateUsage / (1024 * 1024)
            else:
                print("Windows API GetProcessMemoryInfo failed")
                print(f"Error code: {ctypes.GetLastError()}")
        except Exception as e:
            print(f"Windows fallback error: {e}")
            import traceback
            traceback.print_exc()

    return current_mb

if __name__ == "__main__":
    mb = get_memory_mb()
    print(f"Final Result: {mb:.2f} MB")

"""Small read-only Windows process/system monitor; no additional dependency."""
import ctypes as C
from ctypes import wintypes as W
import os
import time

K = C.WinDLL('kernel32', use_last_error=True)
P = C.WinDLL('psapi', use_last_error=True)
K.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
K.OpenProcess.restype = W.HANDLE
K.CloseHandle.argtypes = [W.HANDLE]
K.GetProcessTimes.argtypes = [W.HANDLE] + [C.POINTER(W.FILETIME)] * 4
K.GetSystemTimes.argtypes = [C.POINTER(W.FILETIME)] * 3

class Memory(C.Structure):
    _fields_ = [('cb', W.DWORD), ('PageFaultCount', W.DWORD)] + [(n, C.c_size_t) for n in
        ['PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage',
         'QuotaPeakNonPagedPoolUsage', 'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage', 'PrivateUsage']]

class SystemMemory(C.Structure):
    _fields_ = [('dwLength', W.DWORD), ('dwMemoryLoad', W.DWORD)] + [(n, C.c_ulonglong) for n in
        ['ullTotalPhys', 'ullAvailPhys', 'ullTotalPageFile', 'ullAvailPageFile', 'ullTotalVirtual', 'ullAvailVirtual', 'ullAvailExtendedVirtual']]

P.GetProcessMemoryInfo.argtypes = [W.HANDLE, C.POINTER(Memory), W.DWORD]
K.GlobalMemoryStatusEx.argtypes = [C.POINTER(SystemMemory)]

def ticks(t): return (t.dwHighDateTime << 32) + t.dwLowDateTime

class Monitor:
    def __init__(self): self.previous = {}

    def sample(self, pids):
        now = time.monotonic()
        row = {}
        for name, pid in pids.items():
            handle = K.OpenProcess(0x0400 | 0x0010, False, pid)
            if not handle: continue
            try:
                create, exit_, kernel, user = [W.FILETIME() for _ in range(4)]
                if K.GetProcessTimes(handle, C.byref(create), C.byref(exit_), C.byref(kernel), C.byref(user)):
                    total = (ticks(kernel) + ticks(user)) / 1e7
                    previous = self.previous.get(name)
                    row[name+'_cpu_percent_one_core'] = (total-previous[1])/(now-previous[0])*100 if previous else None
                    row[name+'_cpu_percent_machine'] = row[name+'_cpu_percent_one_core']/os.cpu_count() if previous else None
                    self.previous[name] = now, total
                mem = Memory()
                mem.cb = C.sizeof(mem)
                if P.GetProcessMemoryInfo(handle, C.byref(mem), mem.cb):
                    row[name+'_rss_mb'] = mem.WorkingSetSize/1024**2
                    row[name+'_private_mb'] = mem.PrivateUsage/1024**2
            finally: K.CloseHandle(handle)
        idle, kernel, user = [W.FILETIME() for _ in range(3)]
        if K.GetSystemTimes(C.byref(idle), C.byref(kernel), C.byref(user)):
            total = ticks(kernel) + ticks(user)
            current = ticks(idle)
            prev = self.previous.get('system')
            if prev and total > prev[0]: row['system_cpu_percent'] = (1-(current-prev[1])/(total-prev[0]))*100
            self.previous['system'] = total, current
        mem = SystemMemory()
        mem.dwLength = C.sizeof(mem)
        if K.GlobalMemoryStatusEx(C.byref(mem)):
            row['system_memory_percent'] = mem.dwMemoryLoad
            row['system_total_memory_mb'] = mem.ullTotalPhys/1024**2
        return row

"""并发安全闸 —— 按可用内存自动降级 worker 数，防内核 OOM 误杀 Hermes 网关。

背景（实证，不是拍脑袋）
------------------------
`cli.py` 原先默认 `pytest -n auto`，而本机 `nproc = 2` ⇒ 起 2 个 worker，
每个 worker 一个 headless Chromium，**实测 ≈ 515 MB/实例**（多轮重复测量 513~516MB），
2 个即 ~1030 MB，吃穿仅剩 ~700 MB 的 MemAvailable ⇒ 内核 global OOM
⇒ 渲染进程被杀（Target crashed）+ **Hermes 网关被连带杀**。

策略
----
    cap = max(1, min( (MemAvailable - RESERVE_MB) // PER_WORKER_MB , CPU 核数 ))
本机当前值：(725-450)//550 = 0 → max(1,0) = 1 ⇒ 自动降到 1 worker（实测安全档位）。

⚠️ 预算是**启发式**：Chromium 的 RSS 含大量可共享的 file-backed 映射，
不同负载下波动较大（实测区间 383~516MB/实例）。故取**观测上界 550MB** + 系统保留，
宁保守不冒险；确有把握时用 `--force-workers` 覆盖。

环境变量可调
------------
    HYBRID_MB_PER_WORKER=550   每 worker 内存预算（观测上界）
    HYBRID_RESERVE_MB=450      留给 Hermes 网关 + OS 的余量
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

PER_WORKER_MB = int(os.environ.get("HYBRID_MB_PER_WORKER", "550"))
RESERVE_MB = int(os.environ.get("HYBRID_RESERVE_MB", "450"))


def mem_available_mb() -> int:
    """/proc/meminfo 的 MemAvailable（MB）；读不到返回 0（视为未知）。

    Windows 上没有 /proc ⇒ 退到 GlobalMemoryStatusEx（ullAvailPhys）。读到 0 时
    `safe_workers` 会恒降级为 1（保守不冒险，不会 OOM）——非 Linux 上的"读不到"以前
    就是这样处理的，这里只是补上 Windows 的真实读数，避免大内存机器被无谓压到 1 并发。
    """
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            import ctypes
            class _MEMSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            st = _MEMSTATUSEX()
            st.dwLength = ctypes.sizeof(_MEMSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
                return int(st.ullAvailPhys) // (1024 * 1024)
        except Exception:
            pass
    return 0


def safe_workers(requested: int | None = None) -> tuple[int, str]:
    """返回 (安全并发数, 人类可读的理由)。requested=None 表示"由系统决定"。"""
    avail = mem_available_mb()
    by_mem = max(1, (avail - RESERVE_MB) // PER_WORKER_MB) if avail else 1
    try:
        by_cpu = len(os.sched_getaffinity(0))
    except Exception:
        by_cpu = os.cpu_count() or 1
    cap = max(1, min(by_mem, by_cpu))
    want = requested if requested and requested > 0 else cap
    final = min(want, cap)
    why = (f"MemAvailable={avail}MB, 每worker预算={PER_WORKER_MB}MB, "
           f"系统保留={RESERVE_MB}MB, CPU={by_cpu}核 → 安全并发={cap}")
    if final < want:
        why += f"; 请求 {want} → 降级 {final}"
    return final, why

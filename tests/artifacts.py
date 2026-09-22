"""生成物（`scripts/*.py`）读取的唯一入口 —— 失败时给**可行动诊断**（2026-09-22）。

为什么需要它（AprilPark1012 2026-09-22 本地 Windows 验收 19 红里最有代表性的 9 条）：
他本地两个产物文件是 **0 字节**（解压不完整），于是 9 条契约判据各自报
「生成物 缺这些接线：['def _act', 'def _goto', 'def _data', ...]」——
读的人**根本看不出真因是「产物是空的」**，也没有任何一条判据告诉他下一步做什么。

口径（MEMORY「开关开了就要好用」：失败信息要能让人当场知道下一步）：
    产物不存在 / 0 字节 / 明显残缺 ⇒ 直接给一句人话 + 建议命令（`python -m framework.cli generate`）；
    产物正常 ⇒ 照常返回文本，后续契约判据各判各的（原来是真问题的，还是真问题）。

判据（一类，秒级，不需要 demo）见 `tests/test_env_adaptation.py`。
"""
from __future__ import annotations

from pathlib import Path

# 正常产物在 30KB 量级；这里只拦「空 / 近空」这种明显不是产物的形态，绝不误伤小产物
DEFAULT_MIN_BYTES = 64


def read_artifact(path: Path, *, role: str, min_bytes: int = DEFAULT_MIN_BYTES) -> str:
    """读一份生成物；不健康就抛**带动作**的 AssertionError。"""
    if not path.exists():
        raise AssertionError(
            f"{role} 不存在：{path}\n"
            f"  ⇒ 生成物还没产出。先确认被测目标起着（另开一个窗口 `python -m demo.app`），"
            f"再跑 `python -m framework.cli generate`（或 `cli all` 一条龙）。\n"
            f"  ⇒ 若这是从交付包解压出来的目录：说明解压不完整，重新完整解压一次。"
        )
    size = path.stat().st_size
    if size < min_bytes:
        raise AssertionError(
            f"{role} 只有 {size} 字节（{path}）⇒ 产物是空的 / 残缺的，不是「缺接线」这种细节问题。\n"
            f"  ⇒ 常见原因：解压不完整（压缩包没解全）或上一次生成被中断。\n"
            f"  ⇒ 修法：另开一个窗口起 demo（`python -m demo.app`），然后跑 "
            f"`python -m framework.cli generate` 重新生成产物。"
        )
    return path.read_text(encoding="utf-8")

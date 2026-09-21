"""快照归档保留策略：output/element_maps/ 下只保留最近 N 份 element_map / probe 快照。

背景（2026-09-11）
------------------
explore / probe 每跑一次就落一份快照，攒久了会有三个坏处：
  1. 目录被旧文件淹没，"最新的那一份"不再显眼；
  2. `generate` 取 `emaps[-1]`（按名字排序=时间序）时，一条过期的 mock 快照
     会顶在最前面，把定位来源带偏（实测踩到：合同页用例去读了待办页快照）；
  3. 人工排查时无法一眼看出哪些是本次产物。

策略很朴素：**按文件名（含时间戳）排序，每类各留最近 keep 个，超出的删掉**。
刻意做成显式、可打印、可 `--dry-run` 预演 —— 不做静默清理。

    cli:  python -m framework.cli prune [--keep 20] [--dry-run]
    env:  HYBRID_KEEP_SNAPSHOTS 改默认保留数
"""
from __future__ import annotations

import os
from pathlib import Path

from framework.tools.common.config import ELEMENT_MAP_DIR

DEFAULT_KEEP = int(os.environ.get("HYBRID_KEEP_SNAPSHOTS", "20"))

# 两类快照分开计数（element_map 是 explore 产物，probe 是纯探测产物，语义不同）
_PATTERNS = ("element_map_*.json", "probe_*.json")


def prune_snapshots(
    keep: int = DEFAULT_KEEP,
    snap_dir: Path | None = None,
    dry_run: bool = False,
    quiet_if_none: bool = True,
) -> list[Path]:
    """每类快照各保留最近 keep 个，返回被删（或将被删）的文件列表。

    keep<1 时按 1 处理（至少留最新的那份，绝不删空）。
    quiet_if_none=True：没有可清理的就不打印（供 explore/probe 自动调用，不刷屏）。
    """
    d = Path(snap_dir or ELEMENT_MAP_DIR)
    keep = max(1, int(keep))
    removed: list[Path] = []

    for pat in _PATTERNS:
        files = sorted(d.glob(pat))          # 文件名含 YYYYMMDD_HHMMSS ⇒ 名字序=时间序
        victims = files[: max(0, len(files) - keep)]
        for f in victims:
            try:
                if not dry_run:
                    f.unlink()
                removed.append(f)
            except OSError as e:
                print(f"  [prune] ⚠️ 删除失败 {f.name}: {e}")
        if victims or not quiet_if_none:
            tag = "（dry-run，未删）" if dry_run else ""
            act = f"清理 {len(victims)} 个" if victims else "无需清理"
            print(f"  [prune] {pat}: 共 {len(files)} 个 → 保留 {min(len(files), keep)} 个，{act}{tag}")
    return removed

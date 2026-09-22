"""归档保留策略：两类"只增不减"的自动产物目录，各自可预演地清理。

策略一（2026-09-11）：`output/element_maps/` 下只保留最近 N 份 element_map / probe 快照。
策略二（L5，2026-09-22）：`log/<run_id>/` 与 `output/verify/` —— 见文件末尾 `prune_runs()`。

策略一背景（2026-09-11）
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

import json
import os
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from framework.tools.common.config import ELEMENT_MAP_DIR, LOG_DIR
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


# ==================== 策略二：run / verify 归档保留（L5，2026-09-22） ====================
#
# 背景与取舍见 references/design/P13-归档保留策略-方案.md。核心：
#   `log/<run_id>/` 是真跑产物（每用例 .log + assets + **traces/*.zip 录像**），只增不减 ——
#   实测 281 个目录 / 212 MB，其中 103 MB 是 trace 录像。矛盾是**证据价值 vs 空间**，
#   所以策略分两级，而不是"删旧的"：
#     ① **瘦身**：超龄的 run 只删大体积录像（traces/*.zip），保留 .log + report.html + summary.json
#        ⇒ 证据摘要永久在，大头回收；
#     ② **整删**：**只对能证明是成功的 run** 执行（有 summary.json 且 exit_code==0 且 failed_cases==0）。
#   历史 run 没有 summary.json ⇒ **一律只瘦身**（宁可不回收，也不赌它成功）。
#
#     cli:  python -m framework.cli prune --all [--dry-run]
#     env:  HYBRID_KEEP_RUNS=30 · HYBRID_KEEP_RUN_DAYS=7 · HYBRID_MAX_DELETE_PER_PRUNE=20
#           HYBRID_MAX_FREE_MB=100 · HYBRID_NO_AUTO_PRUNE=1（关掉 run/generate 结束时的自动清理）

DEFAULT_KEEP_RUNS = int(os.environ.get("HYBRID_KEEP_RUNS", "30"))
DEFAULT_KEEP_RUN_DAYS = int(os.environ.get("HYBRID_KEEP_RUN_DAYS", "7"))   # 他 2026-09-22 定 7 天
DEFAULT_MAX_DELETE = int(os.environ.get("HYBRID_MAX_DELETE_PER_PRUNE", "20"))
DEFAULT_MAX_FREE_BYTES = int(os.environ.get("HYBRID_MAX_FREE_MB", "100")) * 1024 * 1024

# run 目录命名：`YYYYMMDD_HHMMSS`（cli run/generate）· `slowgate_YYYYMMDD_HHMMSS`（慢目标闸门）
_RUN_DIR_RE = re.compile(r"^(?:slowgate_)?\d{8}_\d{6}$")
_PROTECTED_NAME = ".protected_runs"
_TS_RE = re.compile(r"(\d{8})_(\d{6})")
# 瘦身对象：只认这两种"大体积证据"，其余文件一律不动
_SLIM_GLOBS = ("traces/*.zip", "traces/*.webm")


def _parse_run_time(name: str) -> datetime | None:
    """从目录名解时间戳（取名字里最后一个 YYYYMMDD_HHMMSS）；解不出 ⇒ None（调用方必须跳过）。"""
    m = None
    for m in _TS_RE.finditer(name):
        pass
    if not m:
        return None
    try:
        return datetime.strptime(f"{m.group(1)}_{m.group(2)}", "%Y%m%d_%H%M%S")
    except ValueError:
        return None


def read_protected_runs(log_dir: Path) -> dict[str, str]:
    """读 `log/.protected_runs`（每行 `run_id  # 理由`）⇒ {run_id: 理由}。

    为什么清单在**仓库内**：框架不许依赖 skill / 门禁路径（R1）。台账、发行说明或交付邮件
    引用过某个 run 时，由 skill 侧规程往这里登记一行 —— 这样"被引用即受保护"落成机制，不靠记性。
    """
    f = Path(log_dir) / _PROTECTED_NAME
    if not f.is_file():
        return {}
    out: dict[str, str] = {}
    for raw in f.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        rid, _, why = line.partition("#")
        rid = rid.strip()
        if rid:
            out[rid] = why.strip()
    return out


def read_run_summary(run_dir: Path) -> dict | None:
    """读 run 目录的 summary.json（runner 收尾写）；缺失或损坏 ⇒ None（= 不可证明成功）。"""
    f = Path(run_dir) / "summary.json"
    if not f.is_file():
        return None
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def run_is_proven_success(run_dir: Path) -> bool:
    """**只有** summary.json 明确说全绿才算"能证明成功"；缺证据一律不算。"""
    s = read_run_summary(run_dir)
    if not s:
        return False
    try:
        return int(s.get("exit_code", 1)) == 0 and int(s.get("failed_cases", 1)) == 0
    except (TypeError, ValueError):
        return False


def _evidence_files(run_dir: Path) -> list[Path]:
    out: list[Path] = []
    for pat in _SLIM_GLOBS:
        out.extend(p for p in Path(run_dir).glob(pat) if p.is_file())
    return out


def _path_bytes(p: Path) -> int:
    try:
        if p.is_dir():
            return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
        return p.stat().st_size
    except OSError:
        return 0


def auto_prune_runs(quiet_if_none: bool = True) -> dict | None:
    """run/generate 结束时的**自动**清理入口；`HYBRID_NO_AUTO_PRUNE=1` 时什么都不做。

    单独一个入口而不是让调用方自己判环境变量：开关只有一处，别在两处各写一遍（会漂移）。
    正在排查时设 `HYBRID_NO_AUTO_PRUNE=1` ⇒ 证据一份不动。
    """
    if os.environ.get("HYBRID_NO_AUTO_PRUNE") == "1":
        return None
    return prune_runs(quiet_if_none=quiet_if_none)


def prune_runs(
    keep: int = DEFAULT_KEEP_RUNS,
    keep_days: int = DEFAULT_KEEP_RUN_DAYS,
    log_dir: Path | None = None,
    verify_dir: Path | None = None,
    max_delete: int = DEFAULT_MAX_DELETE,
    max_free_bytes: int = DEFAULT_MAX_FREE_BYTES,
    dry_run: bool = False,
    quiet_if_none: bool = True,
    now: datetime | None = None,
) -> dict:
    """run / verify 归档保留策略；返回一份可核对的结果（**不静默**）。

    判定口径（安全交集）：run 目录**同时**满足「不在最近 keep 个之内」**且**「超龄 keep_days 天」
    才进入处理范围 ⇒ 保留集 = 最近 keep 个 ∪ 最近 keep_days 天。**两个旋钮取并集保护**。

    单次上限（max_delete 个目录 / max_free_bytes 字节）到顶即停，余量留到下次
    —— 防"策略写错、一夜清空"。任何异常**中止并如实报**（fail-safe，不 fail-open）。
    """
    lg = Path(log_dir or LOG_DIR)
    vd = Path(verify_dir) if verify_dir is not None else lg.parent / "output" / "verify"
    now = now or datetime.now()
    keep = max(1, int(keep))
    cutoff = now - timedelta(days=max(0, int(keep_days)))

    res: dict = {
        "removed_dirs": [], "slimmed_dirs": [], "removed_files": [], "protected_skipped": [],
        "slim_files": [], "verify_files": [],
        "freed_bytes": 0, "capped": False, "unknown_skipped": 0, "failed_abort": None,
        "total_runs": 0, "kept": 0,
    }
    if not lg.is_dir():
        if not quiet_if_none:
            print(f"  [prune] run 目录不存在，跳过：{lg}")
        return res

    protected = read_protected_runs(lg)

    runs: list[Path] = []
    for d in lg.iterdir():
        if not d.is_dir():
            continue
        if not _RUN_DIR_RE.match(d.name):
            res["unknown_skipped"] += 1          # 不认识的命名（用户手工产物）⇒ 一律不动
            continue
        runs.append(d)
    runs.sort(key=lambda d: _parse_run_time(d.name) or datetime.min, reverse=True)   # 新 → 旧
    res["total_runs"] = len(runs)

    keep_recent = {d.name for d in runs[:keep]}
    # 实际保留数 = 最近 keep 个 ∪ 未超龄的（两个旋钮取并集）—— 汇报要报这个，不然会误以为只留了 N 个
    res["kept"] = sum(1 for d in runs
                      if d.name in keep_recent or (_parse_run_time(d.name) or datetime.min) >= cutoff)
    latest_ok = next((d for d in runs if run_is_proven_success(d)), None)
    latest_bad = next((d for d in runs if read_run_summary(d) and not run_is_proven_success(d)), None)
    hard_protect = set(protected)
    for d in (latest_ok, latest_bad):
        if d is not None:
            hard_protect.add(d.name)

    def _room(freed: int, dirs: int) -> bool:
        """还有额度吗？（单次上限）"""
        return dirs < max_delete and freed < max_free_bytes

    # ---------- 第一步：run 目录 ----------
    for d in runs:
        if d.name in keep_recent:
            continue
        ts = _parse_run_time(d.name)
        if ts is None or ts >= cutoff:           # 未超龄 ⇒ 不动（安全交集）
            continue
        try:
            if d.name in protected:              # 显式登记过（被文档/邮件引用）⇒ 完全不碰
                res["protected_skipped"].append(d.name)
                continue
            if not _room(res["freed_bytes"], len(res["removed_dirs"])):
                res["capped"] = True
                break
            if d.name in hard_protect or not run_is_proven_success(d):
                # ① 瘦身：删大体积录像，留 .log + report.html + summary.json
                files = _evidence_files(d)
                freed = sum(_path_bytes(f) for f in files)
                if not dry_run:
                    for f in files:
                        f.unlink()
                res["slimmed_dirs"].append(d.name)
                res["freed_bytes"] += freed
                res["slim_files"].extend(str(f) for f in files)
                res["removed_files"].extend(str(f) for f in files)
            else:
                # ② 整删：只有能证明成功的 run 才走这条路
                freed = _path_bytes(d)
                if not dry_run:
                    shutil.rmtree(d)
                res["removed_dirs"].append(d.name)
                res["freed_bytes"] += freed
        except OSError as e:                     # 单项失败：如实报，继续处理别的
            print(f"  [prune] ⚠️ 处理失败 {d.name}: {e}")

    # ---------- 第二步：output/verify/ 日志 ----------
    v_logs = []
    if vd.is_dir():
        v_logs = sorted((p for p in vd.glob("*.log") if p.is_file()),
                        key=lambda p: _parse_run_time(p.stem) or datetime.min)
    for i, p in enumerate(v_logs):
        if i >= len(v_logs) - keep:              # 最近 keep 个 ⇒ 保留
            continue
        ts = _parse_run_time(p.stem)
        if ts is None or ts >= cutoff:           # 未超龄或名字里没时间戳 ⇒ 保留（保守）
            continue
        if not _room(res["freed_bytes"], len(res["removed_dirs"])):
            res["capped"] = True
            break
        try:
            freed = _path_bytes(p)
            if not dry_run:
                p.unlink()
            res["verify_files"].append(str(p))
            res["removed_files"].append(str(p))
            res["freed_bytes"] += freed
        except OSError as e:
            print(f"  [prune] ⚠️ 处理失败 {p.name}: {e}")

    # ---------- 汇报（删了什么必须看得见） ----------
    mb = res["freed_bytes"] / 1024 / 1024
    nothing = not res["removed_dirs"] and not res["slimmed_dirs"] and not res["removed_files"]
    if nothing and quiet_if_none:
        return res
    tag = "（dry-run 预演，未动磁盘）" if dry_run else ""
    print(f"  [prune] run 归档：共 {res['total_runs']} 个 → 保留最近 {keep} 个 ∪ {keep_days} 天 "
          f"= {res['kept']} 个{tag}")
    if res["removed_dirs"] or res["slimmed_dirs"] or res["removed_files"]:
        print(f"  [prune]   · 整删 {len(res['removed_dirs'])} 个目录（能证明成功且超龄）"
              f" · 瘦身 {len(res['slimmed_dirs'])} 个目录"
              f"（删掉录像 {len(res['slim_files'])} 个文件，日志与报告保留）")
        if res["verify_files"]:
            print(f"  [prune]   · 清理 verify 日志 {len(res['verify_files'])} 个")
        print(f"  [prune]   · 释放 {mb:.1f} MB"
              + ("（已达单次上限，余量留到下次）" if res["capped"] else ""))
    else:
        print("  [prune]   · 无需清理")
    if res["protected_skipped"]:
        print(f"  [prune]   · 显式保护跳过 {len(res['protected_skipped'])} 个（.protected_runs 登记）")
    if res["unknown_skipped"]:
        print(f"  [prune]   · 命名不认识跳过 {res['unknown_skipped']} 个（用户手工产物，不动）")
    return res

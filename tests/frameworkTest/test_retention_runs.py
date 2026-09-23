"""L5 归档保留策略（run / verify）· 一类判据（2026-09-22，服务目标 ③ 稳定 + ④ 脚本健壮）。

背景：`log/<run_id>/` 是真跑产物（每用例 `.log` + `assets` + **`traces/*.zip` 录像**），只增不减 ——
实测 281 个目录 / 212 MB，其中 **103 MB 是 trace 录像**。矛盾是「证据价值 vs 空间」，所以策略分两级，
而不是"删旧的"。方案见 `references/design/P13-归档保留策略-方案.md`。

本文件在**秒级、不启浏览器、不碰真数据**下钉住这些"不许错"的点：

  1. **保留集 = 最近 N 个 ∪ 最近 D 天**（两个旋钮取**并集保护**，不是"满足其一就删"）；
  2. **未超龄的东西一动不动**（连大录像也不删 —— 新鲜证据必须完整）；
  3. **两级处理**：只有**能证明成功**的 run（`summary.json` 且 `exit_code==0` 且 `failed_cases==0`）
     才整删；**历史（无 summary.json）/ 失败** ⇒ 只**瘦身**（删录像、留 `.log` + `report.html` + `summary.json`）；
  4. **最近一次全绿 / 全红各保一个**（无论 N/D）；
  5. **`.protected_runs` 登记过的 ⇒ 完全不碰**（被台账/发行说明/交付邮件引用过的 run）；
  6. **不认识的命名一律不动**（用户手工产物绝不误删）；
  7. **`dry-run` 必须真不动**（前后目录树逐字节一致）；
  8. **单次上限生效**（防"策略写错、一夜清空"）；
  9. **`output/verify/` 同口径**（留最近 N 个 + 超龄才删；名字里没时间戳的保守保留）。

跑法（秒级，不需要 demo / 浏览器）：
    cd ~/hybrid_gui_qa && .venv/bin/python -m pytest tests/frameworkTest/test_retention_runs.py -v
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from framework.tools.common.retention import (       # noqa: E402
    prune_runs,
    read_protected_runs,
    read_run_summary,
    run_is_proven_success,
)

NOW = datetime(2026, 9, 22, 9, 0, 0)                 # 固定"现在"，让用例可复现
GREEN = {"exit_code": 0, "failed_cases": 0}
RED = {"exit_code": 1, "failed_cases": 2}


# ----------------------------------------------------------------- 造数据（只用 tmp_path）
def _mk_run(log: Path, name: str, *, traces: int = 0, summary: dict | None = None,
            mtime: datetime | None = None) -> Path:
    """造一个 run 目录：N 个 1 MB 假录像 + 一个用例日志 + 一个报告（+可选 summary.json）。"""
    d = log / name
    (d / "traces").mkdir(parents=True)
    (d / "case.log").write_text("[TEST] 场景开始\n[CHECK] ✓ 断言\n", encoding="utf-8")
    (d / "report.html").write_text("<html>report</html>", encoding="utf-8")
    for i in range(traces):
        (d / "traces" / f"case{i}_trace.zip").write_bytes(b"x" * 1_000_000)
    if summary is not None:
        (d / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    ts = (mtime or datetime.strptime(name[-15:], "%Y%m%d_%H%M%S")).timestamp()
    for p in [d, *d.rglob("*")]:
        os.utime(p, (ts, ts))
    return d


def _name(days_ago: int, hhmmss: str = "120000") -> str:
    return (NOW - timedelta(days=days_ago)).strftime("%Y%m%d_") + hhmmss


def _mk_verify(verify: Path, days_ago: int) -> Path:
    verify.mkdir(parents=True, exist_ok=True)
    f = verify / f"nonexistent_case_{(NOW - timedelta(days=days_ago)).strftime('%Y%m%d_%H%M%S')}.log"
    f.write_text("pytest session starts\n", encoding="utf-8")
    ts = (NOW - timedelta(days=days_ago)).timestamp()
    os.utime(f, (ts, ts))
    return f


def _scene(tmp_path: Path) -> dict:
    """一套标准现场：新建/较新/较老全绿/历史/失败/被引用/手工目录 + verify 日志。"""
    log = tmp_path / "log"
    log.mkdir()
    verify = tmp_path / "output" / "verify"
    d = {
        "fresh": _mk_run(log, "20260922_080000", traces=2),                       # 今天：未超龄
        "d2": _mk_run(log, _name(2), traces=2),                                   # 2 天前：未超龄
        "ok_new": _mk_run(log, _name(10), traces=2, summary=GREEN),               # 最近一次全绿 ⇒ 保护
        "ok_old": _mk_run(log, _name(30), traces=2, summary=GREEN),               # 较老全绿 ⇒ 整删
        "legacy": _mk_run(log, _name(15), traces=3),                              # 历史无 summary ⇒ 只瘦身
        "fail": _mk_run(log, _name(16), traces=2, summary=RED),                   # 失败 ⇒ 只瘦身
        "ref": _mk_run(log, _name(20), traces=2),                                 # 被引用 ⇒ 完全不碰
    }
    (log / ".protected_runs").write_text(f"# 示例：台账引用过的 run\n{d['ref'].name}  # 被交付邮件引用\n",
                                         encoding="utf-8")
    (log / "manual_dir").mkdir()
    (log / "manual_dir" / "手工文件.txt").write_text("用户手工放的，绝不许动\n", encoding="utf-8")
    for i in range(12):
        _mk_verify(verify, 20 - i)
    return {"log": log, "verify": verify, "runs": d}


def _prune(scene: dict, **kw) -> dict:
    kw.setdefault("keep", 2)
    kw.setdefault("keep_days", 7)
    kw.setdefault("log_dir", scene["log"])
    kw.setdefault("verify_dir", scene["verify"])
    kw.setdefault("now", NOW)
    kw.setdefault("quiet_if_none", True)
    return prune_runs(**kw)


def _snapshot(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


# ----------------------------------------------------------------- 正向：策略本体
def test_keeps_recent_count_union_recent_days(tmp_path):
    """保留集 = 最近 N 个 ∪ 最近 D 天：两个旋钮是"并集保护"，不是"满足其一就删"。"""
    sc = _scene(tmp_path)
    _prune(sc, keep=3, keep_days=7)
    runs = sc["runs"]
    # 最近 3 个（fresh/d2/ok_new）与 7 天内的都在
    assert runs["fresh"].exists() and runs["d2"].exists()
    assert runs["ok_new"].exists()
    # 超过 7 天且不在最近 3 个内的历史 ⇒ 已被处理（整删或瘦身）
    assert not runs["ok_old"].exists(), "较老的全绿应被整删"


def test_fresh_runs_untouched_including_traces(tmp_path):
    """未超龄的 run 一动不动 —— 连大体积录像也不删（新鲜证据必须完整）。"""
    sc = _scene(tmp_path)
    _prune(sc)
    for k in ("fresh", "d2"):
        d = sc["runs"][k]
        assert len(list(d.glob("traces/*.zip"))) == 2, f"{k} 的录像不该被删"
        assert (d / "case.log").exists() and (d / "report.html").exists()


def test_two_level_policy_slim_vs_whole_delete(tmp_path):
    """两级处理：能证明成功的整删；历史/失败只瘦身且日志+报告留下。"""
    sc = _scene(tmp_path)
    res = _prune(sc)
    runs = sc["runs"]
    assert not runs["ok_old"].exists(), "能证明成功且超龄 ⇒ 整删"
    assert runs["legacy"].exists(), "历史（无 summary）不许整删"
    assert (runs["legacy"] / "case.log").exists() and (runs["legacy"] / "report.html").exists()
    assert not list(runs["legacy"].glob("traces/*.zip")), "历史 run 的录像应被瘦身掉"
    assert runs["ok_old"].name in res["removed_dirs"]
    assert runs["legacy"].name in res["slimmed_dirs"]


def test_latest_green_and_latest_red_are_protected(tmp_path):
    """最近一次全绿 / 全红各保一个（无论 N/D）：它们只瘦身，不整删。"""
    sc = _scene(tmp_path)
    _prune(sc)
    runs = sc["runs"]
    assert runs["ok_new"].exists(), "最近一次全绿必须保留"
    assert runs["fail"].exists(), "最近一次全红必须保留"
    assert (runs["fail"] / "summary.json").exists(), "失败证据的 summary 不许被删"


# ----------------------------------------------------------------- 负向自证（每条都要能真的抓住）
def test_negative_protected_runs_untouched(tmp_path):
    """`.protected_runs` 登记过的 ⇒ 完全不碰（连录像也不删）。"""
    sc = _scene(tmp_path)
    res = _prune(sc)
    ref = sc["runs"]["ref"]
    assert ref.exists() and len(list(ref.glob("traces/*.zip"))) == 2
    assert res["protected_skipped"] == [ref.name]


def test_negative_unknown_naming_never_touched(tmp_path):
    """不认识的命名（用户手工产物）一律不动 —— 误删别人的东西是不可接受错误。"""
    sc = _scene(tmp_path)
    _prune(sc)
    keep_file = sc["log"] / "manual_dir" / "手工文件.txt"
    assert keep_file.exists(), "手工目录/文件绝不许被删"
    assert sc["log"].joinpath("manual_dir").is_dir()


def test_negative_dry_run_changes_nothing(tmp_path):
    """`dry-run` 必须真不动：前后目录树逐字节一致（含录像、verify 日志）。"""
    sc = _scene(tmp_path)
    before = _snapshot(tmp_path)
    res = _prune(sc, dry_run=True)
    assert _snapshot(tmp_path) == before, "dry-run 动了磁盘"
    assert res["removed_dirs"], "dry-run 仍应报告『将删什么』"


def test_negative_single_run_cap(tmp_path):
    """单次上限生效：造一批超龄全绿，一次只许删到上限，其余留到下次。"""
    sc = _scene(tmp_path)
    for i in range(30):
        _mk_run(sc["log"], _name(40 + i), summary=GREEN)
    res = _prune(sc, max_delete=5, max_free_bytes=10 ** 12)
    assert len(res["removed_dirs"]) <= 5, f"超过单次上限：{len(res['removed_dirs'])}"
    assert res["capped"] is True, "到上限应标记 capped，供下次继续"
    assert len([d for d in sc["log"].iterdir() if d.is_dir()]) > 5, "余量必须留到下次，不能一次清空"


def test_negative_byte_cap(tmp_path):
    """字节上限同样生效（瘦身也计入），且如实标记 capped。"""
    sc = _scene(tmp_path)
    for i in range(20):
        _mk_run(sc["log"], _name(50 + i), traces=3)
    res = _prune(sc, max_delete=999, max_free_bytes=4 * 1024 * 1024)
    assert res["freed_bytes"] <= 4 * 1024 * 1024 + 3_000_000, "字节上限被无视"
    assert res["capped"] is True


def test_negative_verify_dir_same_policy(tmp_path):
    """`output/verify/` 同口径：留最近 N 个 + 超龄才删；名字里没时间戳的保守保留。"""
    sc = _scene(tmp_path)
    verify = sc["verify"]
    (verify / "no_timestamp_here.log").write_text("老日志但没时间戳\n", encoding="utf-8")
    _prune(sc, keep=2, keep_days=7)
    left = sorted(p.name for p in verify.glob("*.log"))
    assert len([n for n in left if n.startswith("nonexistent_case_")]) == 2, f"应留最近 2 个，实为 {left}"
    assert "no_timestamp_here.log" in left, "解析不出时间戳的必须保守保留"


def test_negative_slowgate_naming_included(tmp_path):
    """慢目标闸门的 `slowgate_YYYYMMDD_HHMMSS` 目录同样在管理范围（同一个"只增不减"面）。"""
    sc = _scene(tmp_path)
    sg = _mk_run(sc["log"], f"slowgate_{_name(25)}", traces=2)
    res = _prune(sc)
    assert sg.name in res["slimmed_dirs"] + res["removed_dirs"], "slowgate 目录应被纳入管理"
    assert len(list(sg.glob("traces/*.zip"))) == 0


# ----------------------------------------------------------------- 辅助函数本身的契约
def test_summary_contract_only_proven_success_counts(tmp_path):
    """「能证明成功」口径：缺 summary / 坏 JSON / 有失败数 ⇒ 都不算成功（宁可不回收）。"""
    log = tmp_path / "log"
    log.mkdir()
    good = _mk_run(log, _name(30), summary=GREEN)
    bad = _mk_run(log, _name(31), summary=RED)
    none = _mk_run(log, _name(32))
    broken = _mk_run(log, _name(33))
    (broken / "summary.json").write_text("{不是合法 json", encoding="utf-8")
    assert run_is_proven_success(good) is True
    assert run_is_proven_success(bad) is False
    assert run_is_proven_success(none) is False
    assert run_is_proven_success(broken) is False, "坏 summary 不能算成功"
    assert read_run_summary(broken) is None


def test_summary_writer_contract(tmp_path):
    """`summary.json` 的写入契约（**这条本该挡住一次真实事故**）。

    2026-09-22 实测：`framework/cli.py` 里写 summary 的 helper 用了 `json` 却没 import ⇒
    只有真跑 `cli run` 才炸（一类当时全绿、二类是抓出来的）。所以这里直接调那个 helper，
    把「字段齐全 + 失败计数口径 + 不因缺东西而崩」钉在一类里。
    """
    from framework.cli import _write_run_summary

    run = tmp_path / "log" / "20260922_120000"
    (run / "traces").mkdir(parents=True)
    (run / "ok.log").write_text("[CHECK] ✓ 断言\n", encoding="utf-8")
    (run / "bad.log").write_text("[CHECK] ✗ 断言\n", encoding="utf-8")
    (run / "traces" / "x_trace.zip").write_bytes(b"z" * 1234)

    _write_run_summary(run, "20260922_120000", 0)
    data = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    assert data["run_id"] == "20260922_120000" and data["exit_code"] == 0
    assert data["case_logs"] == 2, f"用例日志计数（实为 {data.get('case_logs')}）"
    assert data["failed_cases"] == 1, "含 ✗ 的日志必须计为失败（策略据此只瘦身）"
    assert data["traces_bytes"] == 1234, "录像体积要记账（供体量观测）"
    # 失败运行：exit_code 如实记下（策略据此保留"最近一次全红"）
    _write_run_summary(run, "20260922_120000", 3)
    assert json.loads((run / "summary.json").read_text(encoding="utf-8"))["exit_code"] == 3
    # 目录不存在 / 不可写也不许炸（宁可少写一份，也不许把 run 带崩）
    _write_run_summary(tmp_path / "不存在的目录" / "run1", "run1", 0)


def test_protected_file_parsing(tmp_path):
    """保护清单解析：注释与空行忽略、`#` 后是理由、行内多空格也认。"""
    log = tmp_path / "log"
    log.mkdir()
    (log / ".protected_runs").write_text(
        "# 这是注释\n\n20260901_120000  # 被发行说明引用\n  20260902_130000   #  被台账引用\n",
        encoding="utf-8")
    got = read_protected_runs(log)
    assert got == {"20260901_120000": "被发行说明引用", "20260902_130000": "被台账引用"}

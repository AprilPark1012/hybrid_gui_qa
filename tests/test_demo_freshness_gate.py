"""demo 新鲜度闸门的判据（一类，秒级、不需要 demo 在跑）。

为什么要有它：二类验证（R7）跑在**常驻 demo** 上。改了 `demo/app.py` / `demo/*.html` 却忘了重启，
验证就在旧版本上跑 —— 用例**白跑**，还可能给出误导性结论。本判据保证「闸门本身」是可靠的：
判定逻辑、进程启动时刻读取、以及「不新鲜必须拦」这三件事都要有负向自证（只跑正向不算验证过）。

被测对象：`tests/demo_freshness.py`。端到端用法见 `tests/run_verifications.sh`（跑二类前先 `--ensure`）。
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import demo_freshness as df          # noqa: E402


# ---------------- 判定逻辑 ----------------

def test_fresh_when_process_newer():
    now = time.time()
    state, _ = df.verdict(now, now - 60)
    assert state == "fresh"


def test_stale_when_source_newer():
    """★ 核心负向：改了 demo 没重启，必须判 stale（放过它就等于让二类验证失去意义）。"""
    now = time.time()
    state, detail = df.verdict(now - 600, now)          # 进程 10 分钟前起，源码刚改
    assert state == "stale", detail


def test_no_process():
    state, _ = df.verdict(None, time.time())
    assert state == "no_process"


def test_same_second_is_fresh_not_stale():
    """同秒容差：mtime 与启动时刻同秒时不许误报 stale（假红会让人关掉闸门）。"""
    now = time.time()
    assert df.verdict(now, now)[0] == "fresh"
    assert df.verdict(now, now - df.CLOCK_TOLERANCE_S)[0] == "fresh"


def test_stale_boundary_just_outside_tolerance():
    now = time.time()
    assert df.verdict(now, now + df.CLOCK_TOLERANCE_S + 0.5)[0] == "stale"


# ---------------- 源码 mtime 收集 ----------------

def test_newest_src_mtime_picks_newest_and_skips_pycache(tmp_path):
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "a.html").write_text("<html></html>", encoding="utf-8")
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "app.cpython-311.pyc").write_text("junk", encoding="utf-8")

    old = time.time() - 1000
    os.utime(tmp_path / "app.py", (old, old))
    os.utime(tmp_path / "pages" / "a.html", (old + 500, old + 500))
    os.utime(cache / "app.cpython-311.pyc", (time.time(), time.time()))   # 缓存文件“更新”但不该计入

    newest, who = df.newest_src_mtime(tmp_path)
    assert who.endswith("a.html"), f"应取到 a.html，实际 {who}"
    assert abs(newest - (old + 500)) < 1


def test_newest_src_mtime_empty_dir(tmp_path):
    newest, who = df.newest_src_mtime(tmp_path)
    assert newest == 0.0 and who == ""


# ---------------- 进程时刻读取（对真实进程）----------------

def test_proc_start_epoch_of_self_is_sane():
    started = df.proc_start_epoch(os.getpid())
    assert started is not None, "读不到自身进程启动时刻 ⇒ /proc 解析错了"
    now = time.time()
    assert 0 < started <= now + 1, f"启动时刻不在合理范围：{started} vs now={now}"
    assert now - started < 24 * 3600, "启动时刻离谱（可能字段索引错）"


def test_proc_start_epoch_missing_pid_returns_none():
    assert df.proc_start_epoch(999_999_991) is None


def test_demo_pids_shape_without_demo():
    """没在跑也要能安全调用（返回列表，不抛异常）——别的脚本会在各种状态下调它。"""
    assert isinstance(df.demo_pids(), list)


# ---------------- check() 结构与一致性 ----------------

def test_check_returns_full_shape():
    r = df.check()
    assert set(r) >= {"state", "detail", "pid", "started_epoch", "newest_mtime", "newest_file", "base_url"}
    assert r["state"] in {"fresh", "stale", "no_process"}
    assert isinstance(r["newest_mtime"], float)


def test_check_state_matches_verdict():
    r = df.check()
    if r["state"] == "no_process":
        assert r["pid"] is None
    else:
        expect, _ = df.verdict(r["started_epoch"], r["newest_mtime"])
        assert r["state"] == expect, "check() 与 verdict() 必须同一口径"


# ---------------- CLI 退出码契约（给脚本调用方）----------------

def _run(args, cwd):
    return subprocess.run([sys.executable, "tests/demo_freshness.py", *args], cwd=str(cwd),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=60)


def test_cli_json_is_machine_readable():
    """`--json` 要能被脚本调用方直接解析（不许混进人话以外的噪声）。"""
    import json
    repo = Path(__file__).resolve().parents[1]
    r = _run(["--json"], repo)
    assert r.returncode in (0, 3, 4), f"退出码契约：0=fresh / 3=stale / 4=no_process，实际 {r.returncode}\n{r.stderr}"
    assert '"state"' in r.stdout, f"--json 未输出 state 字段：{r.stdout!r}"
    # stale+ensure 时可能打两段 JSON；取第一段验证结构即可
    first = r.stdout[r.stdout.index("{"): r.stdout.index("}") + 1]
    assert json.loads(first)["state"] in {"fresh", "stale", "no_process"}

"""demo 新鲜度闸门的判据（一类，秒级、不需要 demo 在跑）。

为什么要有它：二类验证（R7）跑在**常驻 demo** 上。改了 `demo/app.py` / `demo/*.html` 却忘了重启，
验证就在旧版本上跑 —— 用例**白跑**，还可能给出误导性结论。本判据保证「闸门本身」是可靠的：
判定逻辑、进程启动时刻读取、以及「不新鲜必须拦」这三件事都要有负向自证（只跑正向不算验证过）。

⚠️ 2026-09-22 扩了两块（AprilPark1012 本地 Windows 验收 5 条红驱动）：
① **跨平台分支判据** —— 老实现只认 `/proc`，Windows 上整条闸门不可用。现在
   linux / windows / posix 三分支各自有判据，Windows/POSIX 分支用**注入假命令输出**验解析逻辑
   （本机是 Linux，跑不了真 PowerShell；真机验收必须由人在 Windows 上跑，见 skill 的 P14 方案）；
② **unknown 状态** —— 「探测到 demo 进程但读不到启动时刻」必须如实报 unknown：既不许当 fresh
   （假绿），也不许当 no_process（会诱导重启一个其实在跑的 demo）。退出码 5。

被测对象：`tests/demo_freshness.py`。端到端用法见 `tests/run_verifications.sh`（跑二类前先 `--ensure`）。
"""
from __future__ import annotations

import json
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


# ---------------- 平台口径 ----------------

def test_platform_kind_is_sane():
    assert df._platform_kind() in {"linux", "windows", "posix"}


def _fake_run(mapping: dict[str, str]):
    """按命令里的关键字返回假输出的 `_run` 替身（用来在本机验别的平台分支）。"""
    def _inner(cmd, timeout=15.0):
        joined = " ".join(cmd)
        for key, val in mapping.items():
            if key in joined:
                return val
        return None
    return _inner


def test_windows_branch_parses_pids(monkeypatch):
    monkeypatch.setattr(df, "_platform_kind", lambda: "windows")
    monkeypatch.setattr(df, "_run", _fake_run({"Get-CimInstance": "1234\r\n5678\r\n"}))
    assert df.demo_pids() == [1234, 5678]


def test_windows_branch_parses_start_epoch(monkeypatch):
    monkeypatch.setattr(df, "_platform_kind", lambda: "windows")
    monkeypatch.setattr(df, "_run", _fake_run({"Get-Process": "1789000000\r\n"}))
    assert df.proc_start_epoch(1234) == pytest.approx(1789000000.0)


def test_windows_branch_garbage_or_missing_is_none(monkeypatch):
    """★ 负向：PowerShell 被策略禁用 / 输出垃圾 ⇒ 必须 None（上层判 unknown），绝不猜。"""
    monkeypatch.setattr(df, "_platform_kind", lambda: "windows")
    monkeypatch.setattr(df, "_run", _fake_run({"Get-Process": "拒绝访问。\r\n"}))
    assert df.proc_start_epoch(1234) is None
    monkeypatch.setattr(df, "_run", lambda cmd, timeout=15.0: None)
    assert df.demo_pids() == []
    assert df.proc_start_epoch(1234) is None


def test_posix_branch_parses_pids_and_start(monkeypatch):
    out = ("  111 python -m demo.app\n"
           "  222 /usr/bin/python3 other_tool.py\n"
           "  333 python -m demo.app --port 8000\n")
    monkeypatch.setattr(df, "_platform_kind", lambda: "posix")
    monkeypatch.setattr(df, "_run", _fake_run({"ps -eo": out,
                                               "-o lstart": "Wed Sep 17 10:00:00 2026\n"}))
    assert df.demo_pids() == [111, 333]
    assert df.proc_start_epoch(111) is not None


def test_posix_branch_garbage_start_is_none(monkeypatch):
    monkeypatch.setattr(df, "_platform_kind", lambda: "posix")
    monkeypatch.setattr(df, "_run", _fake_run({"-o lstart": "不是时间\n"}))
    assert df.proc_start_epoch(111) is None


# ---------------- unknown 状态（读不到启动时刻）----------------

def test_unknown_state_never_reported_as_fresh_or_no_process(monkeypatch):
    """★ 核心负向：进程在、但读不到启动时刻 ⇒ 必须 unknown（不许假绿、不许诱导重启）。"""
    monkeypatch.setattr(df, "newest_src_mtime", lambda *a, **k: (time.time(), "app.py"))
    monkeypatch.setattr(df, "demo_pids", lambda: [4242])
    monkeypatch.setattr(df, "proc_start_epoch", lambda pid: None)
    r = df.check()
    assert r["state"] == "unknown", r
    assert r["pid"] == 4242, "unknown 时仍要报出进程号（人工排查用）"
    assert "无法判定" in r["detail"]


def test_unknown_exit_code_is_5(monkeypatch, capsys):
    monkeypatch.setattr(df, "check", lambda: {
        "state": "unknown", "detail": "读不到启动时刻", "pid": 42,
        "started_epoch": None, "newest_mtime": 0.0, "newest_file": "", "base_url": df.BASE_URL})
    assert df.main([]) == 5, "unknown 必须有自己的退出码（不许复用 0/3/4 骗调用方）"
    assert "无法判定" in capsys.readouterr().out


# ---------------- 进程时刻读取（对真实进程）----------------

def test_proc_start_epoch_of_self_is_sane():
    started = df.proc_start_epoch(os.getpid())
    if started is None:
        if df._platform_kind() == "linux":
            pytest.fail("Linux 上读不到自身启动时刻 ⇒ /proc 解析错了")
        pytest.skip(f"平台 {df._platform_kind()}：本机拿不到进程启动时刻（外部命令不可用）"
                    f"⇒ 闸门会如实报 unknown，不算通过")
    now = time.time()
    assert 0 < started <= now + 1, f"启动时刻不在合理范围：{started} vs now={now}"
    assert now - started < 24 * 3600, "启动时刻离谱（可能字段索引错）"


def test_proc_start_epoch_missing_pid_returns_none():
    assert df.proc_start_epoch(999_999_991) is None


def test_demo_pids_shape_without_demo():
    """没在跑也要能安全调用（返回列表，不抛异常）——别的脚本会在各种状态下调它。

    ⚠️ Windows 上老实现这里直接 `FileNotFoundError: '\\\\proc'`（本地验收实测）。
    """
    assert isinstance(df.demo_pids(), list)


# ---------------- check() 结构与一致性 ----------------

def test_check_returns_full_shape():
    r = df.check()
    assert set(r) >= {"state", "detail", "pid", "started_epoch", "newest_mtime", "newest_file", "base_url"}
    assert r["state"] in {"fresh", "stale", "no_process", "unknown"}
    assert isinstance(r["newest_mtime"], float)


def test_check_state_matches_verdict():
    r = df.check()
    if r["state"] in ("no_process", "unknown"):
        assert r["pid"] is None or r["state"] == "unknown"
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
    repo = Path(__file__).resolve().parents[1]
    r = _run(["--json"], repo)
    assert r.returncode in (0, 3, 4, 5), (
        f"退出码契约：0=fresh / 3=stale / 4=no_process / 5=unknown，实际 {r.returncode}\n{r.stderr}")
    assert '"state"' in r.stdout, f"--json 未输出 state 字段：{r.stdout!r}"
    # stale+ensure 时可能打两段 JSON；取第一段验证结构即可
    first = r.stdout[r.stdout.index("{"): r.stdout.index("}") + 1]
    assert json.loads(first)["state"] in {"fresh", "stale", "no_process", "unknown"}

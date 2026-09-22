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
    # stale+ensure 时可能打两段 JSON；取**第一段完整对象**（用 raw_decode 而不是找第一个 '}' ——
    # check() 的输出含嵌套对象 snapshot，按花括号切片会切到嵌套层 ⇒ 解析失败）
    first = json.JSONDecoder().raw_decode(r.stdout[r.stdout.index("{"):])[0]
    assert json.loads(json.dumps(first))["state"] in {"fresh", "stale", "no_process", "unknown"}


# ================ 内容指纹（2026-09-22 新增 · AprilPark1012 拍 A 档 ================
# 背景（他 2026-09-22 现场口径）：demo 是常驻进程，「测试开始确保最新、跑完按需停」这件事不能只靠 mtime：
#   mtime 口径有两个漏判口 —— ① `git checkout` / 解压覆盖 / `cp -p` 会**保留旧 mtime** ⇒ 内容变了却判 fresh；
#   ② 系统时钟回拨。⇒ 升级为「**demo 源码内容指纹**」，且**每轮都查**（不只在入口开头查一次）。
# 快照口径：谁起/重启 demo，谁就把"启动那一刻的指纹 + 进程号"落盘；check() 只有在**快照进程号 == 当前在跑的
# 进程号**时才采信快照（别人的快照一律不认，退回 mtime 口径 —— 保守优先）。

def test_fingerprint_stable_for_same_content(tmp_path):
    (tmp_path / "a.html").write_text("<html>1</html>", encoding="utf-8")
    f1 = df.demo_fingerprint(tmp_path)["fingerprint"]
    f2 = df.demo_fingerprint(tmp_path)["fingerprint"]
    assert f1 == f2, "同一份内容两次取指纹必须一致（否则闸门天天误报）"
    assert len(f1) >= 12, f"指纹太短，碰撞风险高：{f1!r}"


def test_fingerprint_changes_on_content_change(tmp_path):
    p = tmp_path / "a.html"
    p.write_text("<html>1</html>", encoding="utf-8")
    f1 = df.demo_fingerprint(tmp_path)["fingerprint"]
    p.write_text("<html>2</html>", encoding="utf-8")
    assert df.demo_fingerprint(tmp_path)["fingerprint"] != f1, "内容改了指纹必须变"


def test_fingerprint_immune_to_touch(tmp_path):
    """★ 负向：只动 mtime（`touch`）**不算**改动 ⇒ 指纹必须不变（否则每次 touch 都白重启）。"""
    p = tmp_path / "a.html"
    p.write_text("x", encoding="utf-8")
    f1 = df.demo_fingerprint(tmp_path)["fingerprint"]
    now = time.time()
    os.utime(p, (now + 100, now + 100))
    assert df.demo_fingerprint(tmp_path)["fingerprint"] == f1


def test_fingerprint_ignores_pycache_and_non_source(tmp_path):
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "app.cpython-311.pyc").write_text("junk", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("not source", encoding="utf-8")
    f1 = df.demo_fingerprint(tmp_path)["fingerprint"]
    (cache / "app.cpython-311.pyc").write_text("changed junk", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("changed", encoding="utf-8")
    assert df.demo_fingerprint(tmp_path)["fingerprint"] == f1, "__pycache__ / 非源码文件不许进指纹"
    assert df.demo_fingerprint(tmp_path)["files"] == 1


def test_verdict_stale_when_content_differs_even_if_mtime_old():
    """★★ 核心负向：**内容变了、但 mtime 比进程旧**（`git checkout` / 解压覆盖场景）⇒ 必须 stale。

    这是 mtime 口径的漏判口：老口径会判 fresh ⇒ 二类验证跑在旧页面上 = 假绿。
    """
    now = time.time()
    state, detail = df.verdict(now, now - 3600,
                              snapshot={"fingerprint": "aaaa", "pid": 1}, fingerprint="bbbb")
    assert state == "stale", detail
    assert "内容" in detail or "指纹" in detail, f"stale 原因要说清是「内容变了」：{detail}"


def test_verdict_fresh_when_snapshot_matches_even_if_mtime_newer():
    """对称场景：指纹一致（内容没变）⇒ fresh，哪怕 mtime 看着比进程新（时钟漂移/同秒）。"""
    now = time.time()
    assert df.verdict(now, now + 60,
                      snapshot={"fingerprint": "same", "pid": 1}, fingerprint="same")[0] == "fresh"


def test_verdict_without_snapshot_keeps_old_mtime_semantics():
    """没有快照（demo 不是你起的）⇒ 退回原 mtime 口径，老判据一条都不许变。"""
    now = time.time()
    assert df.verdict(now, now - 60)[0] == "fresh"
    assert df.verdict(now - 600, now)[0] == "stale"


def test_check_ignores_snapshot_from_other_pid(monkeypatch):
    """★ 负向：快照存在但**进程号不是当前在跑的那个** ⇒ 不许采信（否则会假 fresh）。"""
    fp = {"fingerprint": "cur", "files": 1, "newest_mtime": time.time(), "newest_file": "app.py"}
    monkeypatch.setattr(df, "demo_pids", lambda: [4242])
    monkeypatch.setattr(df, "proc_start_epoch", lambda pid: 100.0)
    monkeypatch.setattr(df, "demo_fingerprint", lambda *a, **k: dict(fp))
    monkeypatch.setattr(df, "read_snapshot", lambda: {"fingerprint": "cur", "pid": 9999})
    r = df.check()
    assert r["state"] == "stale", f"别人的快照必须退回 mtime 口径（此处应 stale）：{r}"


def test_check_uses_snapshot_of_same_pid(monkeypatch):
    """快照属于当前进程且指纹一致 ⇒ fresh（即使 mtime 比进程新）。"""
    fp = {"fingerprint": "cur", "files": 1, "newest_mtime": time.time(), "newest_file": "app.py"}
    monkeypatch.setattr(df, "demo_pids", lambda: [4242])
    monkeypatch.setattr(df, "proc_start_epoch", lambda pid: 100.0)
    monkeypatch.setattr(df, "demo_fingerprint", lambda *a, **k: dict(fp))
    monkeypatch.setattr(df, "read_snapshot", lambda: {"fingerprint": "cur", "pid": 4242})
    assert df.check()["state"] == "fresh"


def test_restart_writes_snapshot(monkeypatch):
    """重启后必须落快照（指纹 = 启动那一刻的 demo 源码），否则下次 check 又只能退回 mtime 口径。"""
    written: dict = {}
    monkeypatch.setattr(df, "demo_pids", lambda: [])
    monkeypatch.setattr(df, "_wait_ready", lambda timeout=None: True)
    monkeypatch.setattr(df, "demo_fingerprint",
                        lambda *a, **k: {"fingerprint": "fp1", "files": 2,
                                         "newest_mtime": 0.0, "newest_file": ""})
    monkeypatch.setattr(df, "write_snapshot", lambda **kw: written.update(kw))

    class _P:
        pid = 4242

    monkeypatch.setattr(df.subprocess, "Popen", lambda *a, **k: _P())
    assert df.restart(quiet=True) is True
    assert written.get("fingerprint") == "fp1", f"没落快照：{written}"


def test_ensure_fresh_restarts_when_stale(monkeypatch, tmp_path):
    """每轮调用的封装：stale ⇒ 必须重启并复检，返回 (False, 原因) 表示"本轮一开始是不新鲜的"。"""
    calls = {"restart": 0}
    states = iter([{"state": "stale", "detail": "内容变了", "pid": 1},
                   {"state": "fresh", "detail": "ok", "pid": 2}])
    monkeypatch.setattr(df, "check", lambda *a, **k: next(states, {"state": "fresh", "detail": "", "pid": 2}))
    monkeypatch.setattr(df, "restart", lambda quiet=False: (calls.__setitem__("restart", calls["restart"] + 1) or True))
    ok, note = df.ensure_fresh(quiet=True)
    assert ok is True and calls["restart"] == 1, f"stale 时没重启：{ok}, {note}"


def test_ensure_fresh_unknown_state_does_not_restart(monkeypatch):
    """★ 负向：读不到启动时刻（unknown）⇒ **不许**擅自重启（重启是破坏性动作，交人工）。"""
    monkeypatch.setattr(df, "check", lambda *a, **k: {"state": "unknown", "detail": "读不到", "pid": 7})
    monkeypatch.setattr(df, "restart", lambda quiet=False: pytest.fail("unknown 时不许重启"))
    ok, note = df.ensure_fresh(quiet=True)
    assert ok is False and "无法判定" in note


def test_run_verifications_checks_gate_every_round():
    """契约：**每轮都查**（闸门调用必须在脚本循环体内，不能只在入口开头查一次）。

    为什么（AprilPark1012 2026-09-22）：一轮里跑十几个脚本、期间有人改了 demo ⇒ 后面几个脚本就白跑了；
    只在开头查挡不住这种中途污染。
    """
    src = (Path(__file__).resolve().parents[1] / "tests" / "run_verifications.py").read_text(encoding="utf-8")
    assert "_ensure_demo_fresh" in src, "run_verifications 没接每轮闸门（应调 _ensure_demo_fresh）"
    loop = src.index("for i, script in enumerate(scripts")
    body_end = src.index("finally:", loop)
    assert "_ensure_demo_fresh(" in src[loop:body_end], \
        "闸门必须写在脚本循环体内（每轮都查），不能只在循环之前查一次"

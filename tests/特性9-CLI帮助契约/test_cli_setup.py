"""`cli setup` 与「分发采纳返回值」的判据（V8.2.3 · 2026-09-23）。

守两件事：

1. **`setup --check` 的退出码必须能区分好坏** —— 环境好 ⇒ 0；环境坏 ⇒ **非 0**。
   为什么单独立判据：修之前 `main()` 的分发是 8 个裸调用，**返回值被丢弃** ⇒
   `cmd_generate` 里 `DanglingDatasetError` 的 `return 2` 是**空转**
   （"报了错却告诉调用方成功"，exit 0）。同族另外三个错误都是 `-> NoReturn` 直接 raise，
   只有那一条走 return ⇒ 典型的不一致。本文件守住"子命令 return 非 0 ⇒ 进程就非 0"。

2. **`setup --check` 只读** —— 它不能顺手装东西（体检命令不该有副作用）。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _run(args, browsers_path=None, timeout=240):
    env = dict(os.environ)
    if browsers_path:
        env["PLAYWRIGHT_BROWSERS_PATH"] = browsers_path
    env.pop("HYBRID_SKIP_BROWSER_CHECK", None)
    env["PYTHONUTF8"] = "1"
    p = subprocess.run([sys.executable, "-m", "framework.cli", *args],
                       cwd=str(REPO), env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _empty_dir(tmp_path):
    d = tmp_path / "no_browsers"
    d.mkdir(exist_ok=True)
    return str(d)


def test_setup_check_ok_exit_zero():
    """环境好 ⇒ exit 0，且明确说"就绪"。"""
    rc, out = _run(["setup", "--check"])
    if rc != 0:
        import pytest
        pytest.skip("本机浏览器不可用（负向用例已覆盖该路径）")
    assert "就绪" in out, f"--check 通过时必须明确报就绪：{out[-400:]}"
    assert "① 依赖" in out and "② 浏览器" in out, "应当分步报告（依赖 / 浏览器）"


def test_setup_check_missing_browser_exit_nonzero(tmp_path):
    """★负向（核心）：环境坏 ⇒ 必须 **非 0** 退出（这正是修 dispatch 丢弃返回值的那件事）。"""
    rc, out = _run(["setup", "--check"], browsers_path=_empty_dir(tmp_path))
    assert rc != 0, f"环境不就绪却返回 {rc}（调用方会以为成功）"
    assert "还没就绪" in out, f"应当明确说没就绪：{out[-400:]}"
    assert "playwright install chromium" in out or "framework.cli setup" in out, \
        "必须给出可照抄的修复命令"


def test_setup_check_is_read_only(tmp_path):
    """体检不许有副作用：不许因为 --check 就去装东西。"""
    before = set()
    cache = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or
                 (Path.home() / ".cache" / "ms-playwright"))
    if cache.exists():
        before = {p.name for p in cache.iterdir()}
    _run(["setup", "--check"], browsers_path=_empty_dir(tmp_path))
    after = {p.name for p in cache.iterdir()} if cache.exists() else set()
    assert after <= before, f"--check 竟然往浏览器缓存里写了东西：{after - before}"


def test_setup_is_registered_in_help():
    """回归：新子命令必须出现在 --help（文档与代码同源，别只加代码忘了注册）。"""
    rc, out = _run(["--help"])
    assert rc == 0
    assert "setup" in out, "--help 里没有 setup ⇒ 新人看不到这条命令"
    assert "第一次跑" in out or "装浏览器" in out, "setup 的说明要能自解释"


def test_unknown_flag_still_rejected():
    """不误伤：setup 自己的参数表要能挡住乱写的 flag（不许静默忽略）。"""
    rc, out = _run(["setup", "--check-browser"])
    assert rc == 2, f"乱写的参数必须报错退出 2（拿到 {rc}）"
    assert "不认识的参数" in out


# ---------- V8.2.4：版本锁定与漂移可见性 ----------

def _load_cli():
    import importlib
    import sys
    sys.path.insert(0, str(REPO))
    return importlib.import_module("framework.cli")


def test_pinned_playwright_reads_exact_pin(tmp_path):
    """能从 requirements.txt 读出 `playwright==X` 的锁定版本。"""
    (tmp_path / "requirements.txt").write_text(
        "# 注释\nplaywright==1.63.0\npytest>=8.0\n", encoding="utf-8")
    assert _load_cli()._pinned_playwright(tmp_path) == "1.63.0"


def test_pinned_playwright_ignores_range_and_missing(tmp_path):
    """★边界：范围约束（>=/~/…）**不算**锁定；没有文件/被注释掉也不算（别把"没锁"误判成"锁了"）。"""
    cli = _load_cli()
    (tmp_path / "requirements.txt").write_text("playwright>=1.45\n", encoding="utf-8")
    assert cli._pinned_playwright(tmp_path) is None, "范围约束不是锁定"
    (tmp_path / "requirements.txt").write_text("# playwright==1.63.0\n", encoding="utf-8")
    assert cli._pinned_playwright(tmp_path) is None, "注释掉的不算"
    empty = tmp_path / "nodir"
    empty.mkdir()
    assert cli._pinned_playwright(empty) is None, "没有 requirements.txt 不该炸"


def test_repo_requirements_pins_playwright():
    """★回归：本项目 requirements.txt 必须**锁定** playwright（V8.2.4 的决定，别被改回范围）。"""
    text = (REPO / "requirements.txt").read_text(encoding="utf-8")
    active = [ln.split("#", 1)[0].strip() for ln in text.splitlines()]
    pins = [ln for ln in active if ln.startswith("playwright==")]
    assert pins, f"requirements.txt 里 playwright 没有锁定（应为 playwright==X）：{active[:6]}"


def test_version_report_warns_on_mismatch():
    """★核心：版本对不上必须**告警 + 给对齐命令**（且不能说成错误 —— 新版未必不能用）。"""
    cli = _load_cli()
    lines = "\n".join(cli._version_report("1.63.0", "1.64.0"))
    assert "不一致" in lines, "版本漂移必须看得见"
    assert "--force-browser" in lines, "必须给出可照抄的对齐命令"
    assert "不是错" in lines, "不能把版本漂移说成错误（框架不挑版本）"
    ok = "\n".join(cli._version_report("1.63.0", "1.63.0"))
    assert "一致" in ok and "⚠️" not in ok


def test_version_report_edge_cases():
    """边界：只装没锁 / 只锁没装 / 都没有 —— 都不能炸。"""
    cli = _load_cli()
    assert "没锁" in "\n".join(cli._version_report(None, "1.63.0"))
    assert "未装" in "\n".join(cli._version_report("1.63.0", None))
    assert cli._version_report(None, None) == []

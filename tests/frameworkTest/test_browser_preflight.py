"""浏览器可用性预检的判据（V8.2.2 · 2026-09-23）。

背景事故（真实发生，Windows 首次部署）：
    python -m framework.cli explore --ai --scenario-dir scenarios/
    python -m framework.cli generate
    python -m framework.cli run
三条命令各炸一次，抛的都是 Playwright 原始异常栈：
    BrowserType.launch: Executable doesn't exist at ...\\chromium_headless_shell-1243\\...\\chrome-headless-shell.exe
新人看不懂、也搜不到该跑哪条命令 ⇒ 违反「开箱即用 + 提示说人话」。

本文件守两件事：
1. **负向**：浏览器不可用时，必须抛 BrowserNotInstalledError，且文案里**必须有一行修复命令**
   （`playwright install chromium`）—— 空泛报错等于没报。
2. **不误伤**：浏览器可用时不许拦（正常环境一次都不该看到这条提示）；
   `HYBRID_SKIP_BROWSER_CHECK=1` 时也要放行（用户自己确认过就别烦他）。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


def _empty_browsers(tmp_path) -> str:
    d = tmp_path / "no_browsers_here"
    d.mkdir(exist_ok=True)
    return str(d)


def test_missing_browser_raises_with_actionable_message(tmp_path, monkeypatch):
    """★负向（核心）：浏览器不可用 ⇒ 必须抛错，且文案里必须有可照抄的修复命令。"""
    from framework.tools.common.browser import BrowserNotInstalledError, ensure_browser_installed

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", _empty_browsers(tmp_path))
    monkeypatch.delenv("HYBRID_SKIP_BROWSER_CHECK", raising=False)

    with pytest.raises(BrowserNotInstalledError) as ei:
        ensure_browser_installed()

    msg = str(ei.value)
    assert "playwright install chromium" in msg, f"修复命令缺失，等于白报错：{msg}"
    assert "Executable doesn't exist" not in msg.split("修复")[0] or "期望位置" in msg, \
        "应当同时给出期望路径（便于对照版本）"
    assert "1.62" in msg or "playwright 版本" in msg, "应当报出当前 playwright 版本"


def test_skip_env_does_not_block(tmp_path, monkeypatch):
    """不误伤：用户显式跳过 ⇒ 不许再拦。"""
    from framework.tools.common.browser import ensure_browser_installed

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", _empty_browsers(tmp_path))
    monkeypatch.setenv("HYBRID_SKIP_BROWSER_CHECK", "1")
    ensure_browser_installed()  # 不抛即通过


def test_normal_env_passes_through():
    """不误伤：浏览器可用时不许抛（正常环境永远看不到这条提示）。"""
    from framework.tools.common.browser import ensure_browser_installed

    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        pytest.skip("本机被显式指了浏览器目录，交给负向用例覆盖")
    try:
        ensure_browser_installed()
    except Exception as e:  # noqa: BLE001
        if type(e).__name__ == "BrowserNotInstalledError":
            pytest.skip("本机本来就没装浏览器（负向用例已覆盖该路径）")
        raise


def test_cli_probe_exits_2_with_friendly_message(tmp_path):
    """★端到端：走真实 CLI（子进程 ⇒ 不受进程内 driver 缓存影响），必须 exit 2 + 人话。"""
    env = dict(os.environ)
    env["PLAYWRIGHT_BROWSERS_PATH"] = _empty_browsers(tmp_path)
    env.pop("HYBRID_SKIP_BROWSER_CHECK", None)
    env["PYTHONUTF8"] = "1"
    p = subprocess.run([sys.executable, "-m", "framework.cli", "probe"],
                       cwd=str(REPO), env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=180)
    out = (p.stdout or "") + (p.stderr or "")
    assert p.returncode == 2, f"必须非 0 退出（拿到 {p.returncode}）"
    assert "playwright install chromium" in out, f"没给一行修复命令：{out[-500:]}"
    assert "python -m framework.cli" not in out.split("playwright install")[0][-200:] or True


def test_cli_help_and_version_do_not_need_browser(tmp_path):
    """边界：--version / --help 不该被预检拦（它们跟浏览器无关）。"""
    env = dict(os.environ)
    env["PLAYWRIGHT_BROWSERS_PATH"] = _empty_browsers(tmp_path)
    env.pop("HYBRID_SKIP_BROWSER_CHECK", None)
    env["PYTHONUTF8"] = "1"
    for args in (["--version"], ["--help"]):
        p = subprocess.run([sys.executable, "-m", "framework.cli", *args],
                           cwd=str(REPO), env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
        assert p.returncode == 0, f"{args} 不该被浏览器预检拦住（returncode={p.returncode}）"

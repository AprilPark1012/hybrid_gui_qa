"""CLI 退出码契约（2026-09-13 冷启动端到端排查时挖出的三个「静默成功」缺陷）。

背景：clean-room 重跑场景1 时实测到
  ① `cli run` 在 scripts/ 缺失时只提示一句就 `return` ⇒ **exit 0**；
  ② `cli run` **完全不吃 pytest 的退出码** ⇒ 用例失败(1)/没匹配到用例(5) 也 exit 0；
  ③ `cli generate` 在 cases/ 为空时照打「生成 0 个用例」⇒ **exit 0**；
  ④ `ensure_dirs()` 不管 log/ 与 scripts/，冷启动时靠"碰巧"被别的 mkdir 建出来。
这些都会让 CI / 脚本调用方把失败当成功 —— 与 V7.1 立的「不许静默」契约同一条线。

跑法（不需要 demo、不需要浏览器、秒级）：
    cd ~/hybrid_gui_qa && source .venv/bin/activate && python -m pytest tests/test_cli_exit_codes.py -q
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from framework import cli
from framework.tools.common import config
from framework.tools.generate import generator


def test_run_without_generated_scripts_exits_2(monkeypatch, tmp_path):
    """scripts/test_cases.py 不存在 → 明确失败(2)，不能 exit 0。"""
    monkeypatch.setattr(config, "SCRIPTS_DIR", tmp_path)          # 空目录，没有 test_cases.py
    with pytest.raises(SystemExit) as e:
        cli.cmd_run(1)
    assert e.value.code == 2


@pytest.mark.parametrize("returncode", [1, 2, 5])
def test_run_propagates_pytest_exit_code(monkeypatch, tmp_path, returncode):
    """pytest 非 0 → cli 必须返回同一个退出码（CI 判成败就靠它）。"""
    (tmp_path / "test_cases.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(config, "SCRIPTS_DIR", tmp_path)
    monkeypatch.setattr(cli, "LOG_DIR", tmp_path / "log")         # 别把测试产物写进真 log/

    class _R:
        pass

    r_fake = _R()
    r_fake.returncode = returncode          # 不能写在 class 体里：那里看不见外层变量
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: r_fake)
    with pytest.raises(SystemExit) as e:
        cli.cmd_run(1)
    assert e.value.code == returncode


def test_run_success_still_exits_zero(monkeypatch, tmp_path):
    """pytest 全绿 → cli 正常返回（不抛 SystemExit），别把成功路径也改坏。"""
    (tmp_path / "test_cases.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(config, "SCRIPTS_DIR", tmp_path)
    monkeypatch.setattr(cli, "LOG_DIR", tmp_path / "log")

    class _R:
        returncode = 0

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R())
    cli.cmd_run(1)          # 不抛异常 = 通过


def test_generate_with_zero_cases_exits_2(monkeypatch):
    """cases/ 为空 → 生成 0 个用例必须失败，而不是"成功生成空集"。"""
    fake = {"count": 0, "tests": [], "datasets": [], "locator_sources": "(无)",
            "scripts_dir": ".", "locator_sources_note": ""}
    monkeypatch.setattr(generator, "generate_scripts", lambda **kw: fake)
    with pytest.raises(SystemExit) as e:
        cli.cmd_generate([])
    assert e.value.code == 2


def test_generate_with_cases_exits_normally(monkeypatch):
    """有用例时正常返回（不抛 SystemExit）。"""
    fake = {"count": 3, "tests": ["t"], "datasets": ["d"], "locator_sources": "x"}
    monkeypatch.setattr(generator, "generate_scripts", lambda **kw: fake)
    cli.cmd_generate([])


def test_ensure_dirs_covers_runtime_dirs():
    """冷启动可用性：ensure_dirs() 必须自己把 log/ scripts/ cases/ 也建出来。"""
    cli.ensure_dirs()
    for d in (config.LOG_DIR, config.SCRIPTS_DIR, config.CASES_DIR,
              config.OUTPUT_DIR, config.ELEMENT_MAP_DIR):
        assert d.exists(), f"{d} 没有被 ensure_dirs() 创建"


def test_no_stdio_exit_zero_paths_in_run():
    """源码级防复发：cmd_run 里不许再出现「只 print 一句 + return」这种静默成功写法。"""
    src = open(cli.__file__, encoding="utf-8").read()
    assert "先跑 generate\")\n        return" not in src, "run 的静默成功写法又回来了"
    assert "raise SystemExit(r.returncode)" in src, "run 必须如实传递 pytest 退出码"


def test_ensure_dirs_only_declares_used_dirs():
    """防复发（2026-09-14）：ensure_dirs() 急切创建的目录，必须在 config.py 之外有真实使用者。

    背景：PLAN_DIR / GENERATED_TESTS_DIR / TEST_SCENARIO_DIR / DATASETS_DIR 四个旧概念常量
    已无任何使用者，唯一\"效果\"就是每次启动凭空建出空目录（用户实测反馈的空目录残留）。
    判据同「未映射元素」：没有使用者的目录声明 = \"为了存在而存在\"，必须删，而不是只在仓库里 rmdir。
    """
    src = open(config.__file__, encoding="utf-8").read()
    m = re.search(r"def ensure_dirs\(\):.*?for d in \((.*?)\):", src, re.S)
    assert m, "ensure_dirs() 的写法变了，请同步本测试的解析正则"
    names = [n.strip() for n in m.group(1).replace("\n", " ").split(",") if n.strip()]
    assert names, "ensure_dirs() 一个目录都没声明？"

    repo = config.BASE          # 仓库根（单一来源；config 挪过位置，别再用 parents[N] 推）
    corpus = ""
    files = (list((repo / "framework").rglob("*.py")) + list((repo / "tests").glob("*.py"))
             + list((repo / "build_tools").glob("*.py")))
    for p in files:
        if p.name == "config.py":
            continue
        corpus += p.read_text(encoding="utf-8")
    unused = [n for n in names if n not in corpus]
    assert not unused, f"这些目录常量没有任何使用者，别在 ensure_dirs 里建空目录: {unused}"

    for dead in ("PLAN_DIR", "GENERATED_TESTS_DIR", "TEST_SCENARIO_DIR", "DATASETS_DIR"):
        assert not hasattr(config, dead), f"已删除的死概念常量 {dead} 又回来了"

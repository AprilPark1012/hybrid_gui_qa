"""统一 UTF-8 的回归测试（2026-09-13 gbk 事故配套，V7.3）。

保护两条铁律：
  ① **跨进程/落盘文本一律显式 UTF-8** —— 绝不依赖「系统默认编码」
     （AprilPark1012 Windows 上实测：`explore --ai` 的 --verify 报
      `UnicodeDecodeError: 'gbk' codec can't decode byte 0xbb in position 13`）；
  ② `framework.cli` 的入口必须先把 stdio 拉齐到 UTF-8（force_stdio），
     否则 cp936 控制台下中文/✓ 会乱码或直接 UnicodeEncodeError。

跑法（秒级，不需要 demo、不需要 DeepSeek key）：
    cd ~/hybrid_gui_qa && source .venv/bin/activate
    python -m pytest tests/test_utf8_io.py -v

⚠️ 本机装了 zh_CN.gbk locale 才能跑「精确复现」那条；没有则自动 skip（不当失败）。
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from framework.text_io import UTF8_ENV, force_stdio, run_capture, utf8_env  # noqa: E402

SKIP_DIRS = {".venv", "__pycache__", ".pytest_cache", "log", "output",
             "node_modules"}
SUBPROC_FUNCS = {"run", "Popen", "check_output", "check_call", "call"}


# ==================== 一、工具本身 ====================

def test_utf8_env_forces_utf8_and_is_pure():
    """utf8_env() 必须强制 UTF-8 两个变量，且不改动传入的 dict（纯函数）。"""
    assert UTF8_ENV == {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    base = {"X": "1", "PYTHONIOENCODING": "gbk"}
    out = utf8_env(base)
    assert out["PYTHONUTF8"] == "1"
    assert out["PYTHONIOENCODING"] == "utf-8"      # 覆盖掉脏值
    assert out["X"] == "1"
    assert base["PYTHONIOENCODING"] == "gbk"       # 原 dict 未被改（避免污染 os.environ）


def test_force_stdio_is_idempotent_and_safe():
    """force_stdio() 幂等、不抛错；且会把 UTF-8 口径写进 os.environ（子进程继承）。"""
    os.environ.pop("PYTHONUTF8", None)
    force_stdio()
    force_stdio()
    assert os.environ.get("PYTHONUTF8") == "1"
    assert os.environ.get("PYTHONIOENCODING") == "utf-8"


def test_run_capture_decodes_utf8_child_output():
    """run_capture 能正确解码子进程的 UTF-8 中文输出（父进程 locale 与之无关）。"""
    r = run_capture([sys.executable, "-c", "print('[generate] 读 cases/ → 草稿')"])
    assert r.returncode == 0
    assert "读 cases/ → 草稿" in r.stdout


def test_run_capture_tolerates_legacy_kwargs():
    """run_capture 要能容忍调用方多写的 text/capture_output（老调用点迁移时不该炸）。"""
    r = run_capture([sys.executable, "-c", "print('ok')"],
                    capture_output=True, text=True, encoding="gbk", errors="strict")
    assert r.stdout.strip() == "ok"


# ==================== 二、精确复现AprilPark1012那条报错 ====================
# 关键：子进程打印 `[generate] 读 cases/`（真实存在的一行日志）。
#   `[generate] ` 占 11 字节，`读` = E8 AF BB ⇒ **第 13 字节 = 0xbb**。
# 父进程若按 gbk 解码（中文 Windows 默认）⇒ 与AprilPark1012报错逐字一致。

_LOCALE_GBK = "zh_CN.gbk"


def _has_gbk_locale() -> bool:
    try:
        out = subprocess.run(["locale", "-a"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace").stdout
        return _LOCALE_GBK in out
    except Exception:
        return False


_PROBE = r'''
import locale, os, subprocess, sys, tempfile
sys.path.insert(0, r"{repo}")
from framework.text_io import force_stdio, run_capture
force_stdio()                                  # 本进程 stdio 拉齐（等价 cli.main 的行为）
print("MIDDLE_LOCALE=", locale.getpreferredencoding(False))
# 子脚本落**临时文件**：argv 里带中文在 GBK locale 下会先炸（同一个病），
# 所以这里只让「子进程的 stdout」承担中文，专测解码方向。
_child = os.path.join(tempfile.mkdtemp(), "child.py")
with open(_child, "w", encoding="utf-8") as f:
    f.write("print('[generate] 读 cases/')\n")
child = [sys.executable, _child]
r = run_capture(child)                         # ★ 修好的写法
print("NEW=", r.stdout.strip())
try:                                           # 修前的写法（对照，用来证明本机真能复现）
    subprocess.run(child, capture_output=True, text=True)
    print("OLD= 未复现")
except UnicodeDecodeError as e:
    print("OLD=", type(e).__name__, str(e))
'''


@pytest.mark.skipif(not _has_gbk_locale(), reason="本机没有 zh_CN.gbk locale，无法精确复现")
def test_reproduce_and_fix_gbk_byte_0xbb_position_13(tmp_path):
    """在 GBK locale 下：修前写法必须精确复现 `byte 0xbb in position 13`；run_capture 必须正常。

    ⚠️ 探针写成**临时文件**跑，不用 `python -c`：GBK locale 下连命令行参数里的中文
    都解不开（`Unable to decode the command from the command line`）—— 同一个病。
    """
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTHONIOENCODING", "PYTHONUTF8", "LC_ALL", "LANG")}
    env["LC_ALL"] = _LOCALE_GBK
    probe = tmp_path / "probe.py"
    probe.write_text(_PROBE.format(repo=str(REPO)), encoding="utf-8")
    out = subprocess.run([sys.executable, str(probe)],
                         cwd=str(REPO), capture_output=True, text=True,
                         encoding="utf-8", errors="replace", env=env).stdout

    assert "MIDDLE_LOCALE= GBK" in out, f"用例前提不成立（中间进程 locale 不是 GBK）:\n{out}"
    # ① 修前写法：与AprilPark1012报错逐字一致（codec=gbk / byte 0xbb / position 13）
    assert "UnicodeDecodeError" in out and "'gbk' codec can't decode byte 0xbb in position 13" in out, \
        f"未复现出原始报错，本测试失去意义:\n{out}"
    # ② 修好后的写法：同一条中文输出正常解码
    assert "NEW= [generate] 读 cases/" in out, f"run_capture 未能正确解码 UTF-8 输出:\n{out}"


# ==================== 三、CLI 入口必须统一 UTF-8 ====================

@pytest.mark.skipif(not _has_gbk_locale(), reason="本机没有 zh_CN.gbk locale")
def test_cli_output_is_utf8_even_under_gbk_locale():
    """gbk 控制台 locale 下，`cli --version` 的中文也必须按 UTF-8 输出（不乱码、不崩）。

    刻意**不**注入 PYTHONIOENCODING/PYTHONUTF8：要验证的是 cli.main() 里的 force_stdio()
    自己把 stdio 拉齐（否则中文会是 gbk 字节 → 这里解码成乱码，断言失败）。
    """
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTHONIOENCODING", "PYTHONUTF8", "LC_ALL", "LANG")}
    env["LC_ALL"] = _LOCALE_GBK
    r = subprocess.run([sys.executable, "-m", "framework.cli", "--version"],
                       cwd=str(REPO), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env, timeout=60)
    assert r.returncode == 0
    assert "被测目标" in r.stdout, f"CLI 输出不是 UTF-8（force_stdio 失效？）:\n{r.stdout!r}"


def test_fs_encoding_warning_only_fires_off_utf8():
    """文件名按「文件系统编码」落地 ⇒ 非 UTF-8（中文 Windows/GBK locale）必须大声提醒，UTF-8 时闭嘴。"""
    from framework.text_io import fs_encoding_warning
    assert fs_encoding_warning("utf-8") is None
    assert fs_encoding_warning("UTF-8") is None
    assert fs_encoding_warning("utf8") is None
    for bad in ("cp936", "gbk", "gb18030", "ascii", "ANSI_X3.4-1968"):
        msg = fs_encoding_warning(bad)
        assert msg and "PYTHONUTF8=1" in msg, f"{bad} 应该给出提醒"


def test_cli_source_calls_fs_encoding_warning():
    """cli.main() 必须检查文件系统编码（否则 GBK 环境下中文用例名会落成乱码字节名）。"""
    src = (REPO / "framework" / "cli.py").read_text(encoding="utf-8")
    assert "fs_encoding_warning()" in src


def test_verify_cases_does_not_crash_under_gbk_locale(tmp_path):
    """`_verify_cases`（--verify 的实现）在 GBK locale 下必须不因编码崩掉。

    子进程（generate / pytest）输出中文 → 父进程必须按 UTF-8 解码；用不存在的用例名，
    断言「没有 UnicodeDecodeError」+「走完了校验流程」（失败/未执行都算走完，编码崩不算）。
    """
    if not _has_gbk_locale():
        pytest.skip("本机没有 zh_CN.gbk locale")
    probe = tmp_path / "probe_verify.py"
    probe.write_text(
        'import sys\n'
        f'sys.path.insert(0, r"{REPO}")\n'
        'from framework.text_io import force_stdio\n'
        'force_stdio()\n'
        'from framework.cli import _verify_cases\n'
        'res = _verify_cases([("UTF-8复现", "nonexistent_case_for_encoding_test")])\n'
        'print("RESULT=", res)\n', encoding="utf-8")
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTHONIOENCODING", "PYTHONUTF8", "LC_ALL", "LANG")}
    env["LC_ALL"] = _LOCALE_GBK
    r = subprocess.run([sys.executable, str(probe)], cwd=str(REPO),
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=env, timeout=300)
    out = (r.stdout or "") + (r.stderr or "")
    assert "UnicodeDecodeError" not in out, f"编码问题仍在:\n{out[-2000:]}"
    assert "RESULT=" in out, f"校验流程没走完:\n{out[-2000:]}"


# ==================== 四、源码级防复发（AST 扫描） ====================

def _py_files():
    for p in REPO.rglob("*.py"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        yield p


def _kw(call: ast.Call, name: str):
    return next((k for k in call.keywords if k.arg == name), None)


def test_no_locale_dependent_text_io_in_source():
    """全仓扫描：绝不允许「靠系统默认编码」的文本 IO（就是 gbk 事故的根因）。

    规则（跨平台铁律，Windows cp936 下必炸的那几类）：
      · subprocess.run/Popen/...：写了 text=True/universal_newlines 就必须带 encoding=
      · open(...)：非二进制模式必须带 encoding=
      · Path.read_text()/write_text()：必须带 encoding=
    新增代码违反 → 本测试直接失败（并打印文件名:行号）。
    """
    bad: list[str] = []
    for p in _py_files():
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError as e:                       # 语法坏的另行报错，这里不掩盖
            bad.append(f"{p.relative_to(REPO)}: 无法解析（{e}）")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            rel = f"{p.relative_to(REPO)}:{node.lineno}"
            if (isinstance(fn, ast.Attribute) and fn.attr in SUBPROC_FUNCS
                    and isinstance(fn.value, ast.Name) and fn.value.id == "subprocess"):
                if (_kw(node, "text") or _kw(node, "universal_newlines")) and not _kw(node, "encoding"):
                    bad.append(f"{rel} subprocess.{fn.attr}(text=True) 缺 encoding= "
                               f"（改用 framework.text_io.run_capture）")
            if isinstance(fn, ast.Attribute) and fn.attr in ("read_text", "write_text"):
                if not _kw(node, "encoding"):
                    bad.append(f"{rel} .{fn.attr}() 缺 encoding=\"utf-8\"")
            if (isinstance(fn, ast.Attribute) and fn.attr == "open") or \
               (isinstance(fn, ast.Name) and fn.id == "open"):
                mode = None
                if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                    mode = node.args[1].value
                mk = _kw(node, "mode")
                if mk is not None and isinstance(mk.value, ast.Constant):
                    mode = mk.value
                if (mode is None or "b" not in str(mode)) and not _kw(node, "encoding"):
                    bad.append(f"{rel} open() 缺 encoding= （文本模式必须显式 UTF-8）")
    assert not bad, "以下位置依赖系统默认编码（Windows cp936 会 UnicodeDecodeError）：\n  " + \
                    "\n  ".join(sorted(set(bad)))


def test_cli_main_calls_force_stdio_first():
    """cli.main() 必须在任何输出之前 force_stdio()（源码级防复发）。"""
    src = (REPO / "framework" / "cli.py").read_text(encoding="utf-8")
    main_src = src.split("def main():", 1)[1]
    assert "force_stdio()" in main_src.split("args = sys.argv", 1)[0], \
        "cli.main() 开头没有 force_stdio() → cp936 控制台下中文/✓ 会乱码或崩"


def test_generated_conftest_template_carries_utf8_bootstrap():
    """生成的 scripts/conftest.py 必须自带 UTF-8 自举（裸跑 pytest 也不炸）。"""
    from framework.generator import _CONFTEST_TEMPLATE
    assert 'reconfigure(encoding="utf-8"' in _CONFTEST_TEMPLATE
    assert "SetConsoleOutputCP(65001)" in _CONFTEST_TEMPLATE

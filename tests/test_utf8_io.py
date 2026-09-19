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

⚠️ 「精确复现 GBK」那三条，需要**本机能造出「默认编码 = GBK 家族」的子进程**才跑得起：
  · POSIX：`locale -a` 里有 zh_CN.gbk（靠注入 LC_ALL 生效）；
  · Windows：**没有 `locale` 命令**（POSIX 专有）⇒ 老写法在中文 Windows 上恒判 False、
    三条用例永远跳过 —— 而那恰恰是 gbk 事故的**原发环境**（2026-09-15 实测挖出）。
    中文 Windows 的 ANSI 代码页就是 936 ⇒ 天然满足，无需注入任何变量。
造不出则自动 skip（**不当失败**：在没有 GBK 的机器上硬失败 = 把环境噪声当业务结论）。
"""
from __future__ import annotations

import ast
import locale
import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

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
# GBK 家族的编码别名：Windows 上 `locale.getpreferredencoding()` 给的是 `cp936`，
# 而报错信息里的 codec 名永远显示成 `gbk`（cp936 是 gbk 的别名，canonical name 就是 gbk）。
_GBK_FAMILY = {"gbk", "cp936", "gb2312", "gb18030", "936"}
_GBK_SKIP_REASON = ("本机无法把子进程默认编码压到 GBK 家族"
                    "（POSIX 需 zh_CN.gbk locale；Windows 需 ANSI 代码页 936）")


def _norm_enc(name) -> str:
    """编码名归一化：`CP-936` / `cp_936` / ` GBK ` 一律压成形如 `cp936` 的小写形式。"""
    return str(name or "").strip().lower().replace("-", "").replace("_", "").replace(" ", "")


def _gbk_default_encoding() -> str | None:
    """本机能否让子进程的**默认**编码落在 GBK 家族？能返回编码名，不能返回 None。

    · POSIX：`locale -a` 里得有 zh_CN.gbk（靠注入 LC_ALL 生效）；
    · Windows：**根本没有 `locale` 命令**（POSIX 专有）⇒ 老写法在这里 FileNotFoundError
      → 恒判 False → 三条 GBK 用例永远跳过；而中文 Windows 恰恰是 gbk 事故的原发环境
      （2026-09-15 AprilPark1012 Windows 验收时挖出）。中文 Windows 的 ANSI 代码页就是 936，
      默认编码天然是 cp936/gbk ⇒ 直接判「能跑」，不需要注入任何变量。
    """
    if os.name == "nt":
        enc = _norm_enc(locale.getpreferredencoding(False))     # = GetACP()，中文 Win = cp936
        return enc if enc in _GBK_FAMILY else None
    try:
        out = subprocess.run(["locale", "-a"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace").stdout
    except Exception:
        return None                       # 连 locale 命令都没有（非 POSIX 环境）
    return _LOCALE_GBK if _LOCALE_GBK in out else None


def _gbk_env_delta() -> dict:
    """把子进程压到 GBK 默认编码所需的**额外**环境变量（Windows 上为空：它本来就是）。"""
    return {} if os.name == "nt" else {"LC_ALL": _LOCALE_GBK}


def _gbk_child_env() -> dict:
    """构造「默认编码 = GBK 家族」的子进程环境：先剥掉会覆盖默认编码的变量，再按平台补。

    ⚠️ 过滤按**大小写无关**（Windows 的环境变量名不区分大小写，别只挡全大写那一种写法）。
    """
    kill = {"PYTHONIOENCODING", "PYTHONUTF8", "LC_ALL", "LANG"}
    env = {k: v for k, v in os.environ.items() if k.upper() not in kill}
    env.update(_gbk_env_delta())
    return env


def _middle_locale_from(out: str) -> str | None:
    """从探针输出里取「中间进程的默认编码名」（跨平台：POSIX 给 GBK，Windows 给 cp936）。"""
    for line in out.splitlines():
        if line.startswith("MIDDLE_LOCALE="):
            return line.split("=", 1)[1].strip() or None
    return None


_PROBE = r'''
import locale, os, subprocess, sys, tempfile
sys.path.insert(0, r"{repo}")
from framework.text_io import force_stdio, run_capture
# ⚠️ 顺序要紧：**先读默认编码，再 force_stdio()** —— force_stdio 会把 PYTHONUTF8 写进 os.environ，
#    而 UTF-8 模式下 `locale.getpreferredencoding()` 会返回 utf-8 ⇒ 那读到的就不是「默认编码」了。
print("MIDDLE_LOCALE=", locale.getpreferredencoding(False))
force_stdio()                                  # 本进程 stdio 拉齐（等价 cli.main 的行为）
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


@pytest.mark.skipif(_gbk_default_encoding() is None, reason=_GBK_SKIP_REASON)
def test_reproduce_and_fix_gbk_byte_0xbb_position_13(tmp_path):
    """在 GBK locale 下：修前写法必须精确复现 `byte 0xbb in position 13`；run_capture 必须正常。

    ⚠️ 探针写成**临时文件**跑，不用 `python -c`：GBK locale 下连命令行参数里的中文
    都解不开（`Unable to decode the command from the command line`）—— 同一个病。
    """
    env = _gbk_child_env()
    probe = tmp_path / "probe.py"
    probe.write_text(_PROBE.format(repo=str(REPO)), encoding="utf-8")
    out = subprocess.run([sys.executable, str(probe)],
                         cwd=str(REPO), capture_output=True, text=True,
                         encoding="utf-8", errors="replace", env=env).stdout

    mid = _middle_locale_from(out)
    assert mid is not None and _norm_enc(mid) in _GBK_FAMILY, \
        f"用例前提不成立（中间进程默认编码不在 GBK 家族，实际={mid!r}）:\n{out}"
    # ① 修前写法：与AprilPark1012报错逐字一致（codec = gbk 家族 / byte 0xbb / position 13）
    #    ⚠️ codec 名跨平台可能是 `gbk`（POSIX 报错口径）或 `cp936`（Windows 拿到的默认编码名）——
    #    两者是同一个 codec（cp936 是 gbk 的别名）⇒ 用「家族」判，但字节与位置必须精确到 0xbb@13。
    assert "UnicodeDecodeError" in out, f"未复现出报错，本测试失去意义:\n{out}"
    assert re.search(r"'(?:gbk|cp936)' codec can't decode byte 0xbb in position 13", out), \
        f"未复现出 0xbb@13 这个原始签名，本测试失去意义:\n{out}"
    # ② 修好后的写法：同一条中文输出正常解码
    assert "NEW= [generate] 读 cases/" in out, f"run_capture 未能正确解码 UTF-8 输出:\n{out}"


# ==================== 三、CLI 入口必须统一 UTF-8 ====================

@pytest.mark.skipif(_gbk_default_encoding() is None, reason=_GBK_SKIP_REASON)
def test_cli_output_is_utf8_even_under_gbk_locale():
    """gbk 控制台 locale 下，`cli --version` 的中文也必须按 UTF-8 输出（不乱码、不崩）。

    刻意**不**注入 PYTHONIOENCODING/PYTHONUTF8：要验证的是 cli.main() 里的 force_stdio()
    自己把 stdio 拉齐（否则中文会是 gbk 字节 → 这里解码成乱码，断言失败）。
    """
    env = _gbk_child_env()
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


def test_verify_scripts_call_force_stdio():
    """`tests/verify_*.py` 都必须统一 UTF-8 —— 否则中文 Windows 控制台上中文会显示成乱码。

    2026-09-15 实测：AprilPark1012跑 `verify_slow_target.py` 时看到 `Failed: Ԫ��δӳ��`
    （= UTF-8 字节被 cp936 解释），因为该脚本自己没调 force_stdio()；而另外两个 verify 早就调了
    ⇒ 同一个仓库里两种口径，现象看着像「框架坏了」。判据：一个都不许漏。
    """
    missing = [p.name for p in sorted((REPO / "tests").glob("verify_*.py"))
               if "force_stdio()" not in p.read_text(encoding="utf-8")]
    assert not missing, f"这些 verify 脚本没统一 UTF-8（控制台会乱码）：{missing}"


def test_verify_cases_does_not_crash_under_gbk_locale(tmp_path):
    """`_verify_cases`（--verify 的实现）在 GBK locale 下必须不因编码崩掉。

    子进程（generate / pytest）输出中文 → 父进程必须按 UTF-8 解码；用不存在的用例名，
    断言「没有 UnicodeDecodeError」+「走完了校验流程」（失败/未执行都算走完，编码崩不算）。

    ⚠️ 目标**钉成确定性不可达**（2026-09-19 修，别改回去）：本用例只关心「解码中文不崩」，
    但 `_verify_cases` 会先 generate 一次 ⇒ **若本机恰好有 demo 在跑，它会去真 probe（起浏览器）**。
    实测同一条用例：无 demo 1.16s / 有 demo **162.71s**（占全套 93%，整包 13s → 175s）
    —— 跑的东西都不一样，等于「一类自测 = 秒级、不需要 demo」的契约被这条悄悄突破。
    钉成不可达后 0.91s，且输出仍有中文（依旧真题解码路径，反而不再受环境影响）。
    """
    if _gbk_default_encoding() is None:
        pytest.skip(_GBK_SKIP_REASON)
    probe = tmp_path / "probe_verify.py"
    probe.write_text(
        'import sys\n'
        f'sys.path.insert(0, r"{REPO}")\n'
        'from framework.text_io import force_stdio\n'
        'force_stdio()\n'
        'from framework.cli import _verify_cases\n'
        'res = _verify_cases([("UTF-8复现", "nonexistent_case_for_encoding_test")])\n'
        'print("RESULT=", res)\n', encoding="utf-8")
    # 确定性不可达的目标：只用失败路径（它同样会打中文诊断），别让它去 probe 真 demo
    # （2026-09-19：本条测试只关心"解码中文不崩"，不该因本机恰好有 demo 就变成 162s 的端到端）
    env = {**_gbk_child_env(),
           "TARGET_URL": "http://127.0.0.1:1",
           "HYBRID_BASE_URL": "http://127.0.0.1:1"}
    r = subprocess.run([sys.executable, str(probe)], cwd=str(REPO),
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=env, timeout=300)
    out = (r.stdout or "") + (r.stderr or "")
    assert "UnicodeDecodeError" not in out, f"编码问题仍在:\n{out[-2000:]}"
    assert "RESULT=" in out, f"校验流程没走完:\n{out[-2000:]}"
    # 收紧判据（2026-09-19）：必须**真的解码到中文** —— 否则「没崩」可能只是「没东西可解码」
    assert re.search(r"[\u4e00-\u9fff]", out), (
        f"输出里没有中文 ⇒ 没走到「解码中文」这条路径，本用例等于空验:\n{out[-2000:]}")


# ============ 三·补充、guard 自己必须跨平台（否则 Windows 上静默跳过三条） ============
# 2026-09-15 AprilPark1012 Windows 验收实测：`pytest tests/ -q` = 97 passed + 3 skipped。
# 根因 = guard 用的是 POSIX 专有命令 `locale -a`，Windows 上必然 FileNotFoundError → False
# ⇒ 三条 GBK 用例在**中文 Windows（gbk 事故的原发环境）**上永远不执行 = 静默覆盖漏洞。
# 下面几条就是「测试的测试」：把两个平台分支都钉住。

def test_gbk_guard_accepts_chinese_windows_ansi_codepage(monkeypatch):
    """中文 Windows（没有 locale 命令、ANSI 代码页 936）必须判「能跑」，且不注入任何变量。"""
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(locale, "getpreferredencoding", lambda do_setlocale=True: "cp936")
    assert _gbk_default_encoding() == "cp936"
    assert _gbk_env_delta() == {}          # Windows 上默认编码本来就是 936，无需 LC_ALL


def test_gbk_guard_rejects_non_gbk_windows(monkeypatch):
    """英文 Windows（cp1252）复现不了 GBK ⇒ 如实判「不能跑」，绝不在错环境下硬跑出假结论。"""
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(locale, "getpreferredencoding", lambda do_setlocale=True: "cp1252")
    assert _gbk_default_encoding() is None


def test_gbk_guard_posix_uses_locale_and_injects_lc_all(monkeypatch):
    """POSIX 分支照旧：靠 `locale -a` 判定，命中才注入 LC_ALL。"""
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: SimpleNamespace(stdout="C\nPOSIX\nzh_CN.gbk\n"))
    assert _gbk_default_encoding() == _LOCALE_GBK
    assert _gbk_env_delta() == {"LC_ALL": _LOCALE_GBK}


def test_gbk_guard_posix_without_locale_command_is_not_an_error(monkeypatch):
    """`locale` 命令不存在（老写法在这里静默跳过三条用例）⇒ 判「不能跑」，但绝不抛异常。"""
    monkeypatch.setattr(os, "name", "posix")

    def _boom(*a, **k):
        raise FileNotFoundError("locale")

    monkeypatch.setattr(subprocess, "run", _boom)
    assert _gbk_default_encoding() is None


def test_middle_locale_parser_accepts_both_platform_names():
    """探针返回值解析：POSIX 给 `GBK`、Windows 给 `cp936`，两者都必须落在 GBK 家族里。"""
    assert _middle_locale_from("MIDDLE_LOCALE= GBK\nNEW= x\n") == "GBK"
    assert _norm_enc(_middle_locale_from("MIDDLE_LOCALE= cp936\r\n")) in _GBK_FAMILY
    assert _norm_enc(" cp-936 ") == "cp936"
    assert _middle_locale_from("nothing here") is None


def test_gbk_guard_is_cross_platform_and_actually_wired_in():
    """源码级防复发：guard 必须有 NT 分支，且三条 GBK 用例真的挂在它上面。

    ⚠️ 这里**刻意不数字符串出现次数**（第一版就写错了：断言里的字面量会把自己也数进去，
    另加两条单测也含同一串 ⇒ `3` 变成 `6`）。改成结构判据：解析 AST，逐条用例函数看它的
    `ast.unparse()` 里有没有引用 guard。
    """
    src = (REPO / "tests" / "test_utf8_io.py").read_text(encoding="utf-8")
    guard = src.split("def _gbk_default_encoding", 1)[1].split("\ndef ", 1)[0]
    assert 'os.name == "nt"' in guard, "guard 缺 NT 分支 → 中文 Windows 上又会静默跳过三条"
    assert "getpreferredencoding" in guard, "NT 分支应读 ANSI 代码页（getpreferredencoding）"

    tree = ast.parse(src)
    fns = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    cases = ("test_reproduce_and_fix_gbk_byte_0xbb_position_13",
             "test_cli_output_is_utf8_even_under_gbk_locale",
             "test_verify_cases_does_not_crash_under_gbk_locale")
    missing = [c for c in cases
               if c not in fns or "_gbk_default_encoding" not in ast.unparse(fns[c])]
    assert not missing, f"这些 GBK 用例没挂在跨平台 guard 上（Windows 上会静默跳过）: {missing}"


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

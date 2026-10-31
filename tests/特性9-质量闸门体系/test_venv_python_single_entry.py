"""V8.7.20 判据：venv 解释器定位必须走**唯一入口** `framework/shared/paths.py`。

由来（2026-10-29 用户 Windows 实测：6 skipped vs 本机 3 skipped）：
  按点号位置逐个反推出多出来的那一条，是
      tests/特性1-混合链路/test_offline_chain_python.py::test_probe_deps_on_repo_venv_if_present
  它硬编码：
      venv = REPO / ".venv" / "bin" / "python"      # POSIX only
      if not venv.exists(): pytest.skip(...)
  而 Windows 的 venv 布局是 `.venv\\Scripts\\python.exe`（**根本没有 bin/ 目录**）
  => 这条判据在 Windows 上**永远 skip**，等于**从没被验证过**。

  全仓共 **3 处**同类硬编码（只认 POSIX）：
      test_offline_chain_python.py:125     -> 永远 skip（假绿）
      verify_slow_target.py:44             -> 静默退回 sys.executable（依赖可能缺）
      verify_offline_chain_deps.py:99      -> 拿到不存在的路径，跑就失败
  而正确的那份（`run_verifications._venv_python`）其实早就存在 —— `test_env_adaptation`
  还专门测过它认得 `Scripts/python.exe`。**典型「同一能力多份实现、只有一份对」**。

守六件事：
  ① Windows 布局（`.venv/Scripts/python.exe`）必须认得；
  ② POSIX 布局（`.venv/bin/python3` / `.venv/bin/python`）必须认得，且 python3 优先于 python；
  ③ 没有 venv 时 `venv_python_or_none()` **必须返回 None**（不许假装找到了）；
  ④ 同名但是**目录**不算找到（用 is_file 而不是 exists —— 防止拿到一个目录去当解释器）；
  ⑤ 全仓**不许**再出现硬编码 `.venv/bin/python`（防漂移，这条是重点）；
  ⑥ `run_verifications._venv_python` 只做**转发**，不许再自己实现一份。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


# ---------------- ① Windows 布局 ----------------

def test_windows_venv_layout_is_found(tmp_path) -> None:
    """① Windows：`.venv/Scripts/python.exe`。"""
    from framework.shared.paths import venv_python, venv_python_or_none

    d = tmp_path / ".venv" / "Scripts"
    d.mkdir(parents=True)
    (d / "python.exe").write_text("", encoding="utf-8")
    got = venv_python_or_none(tmp_path)
    assert got is not None, "Windows 的 .venv/Scripts/python.exe 没认出来 -> 判据在那里会永远 skip"
    assert got.name == "python.exe"
    assert venv_python(tmp_path).endswith("python.exe")


# ---------------- ② POSIX 布局 ----------------

def test_posix_venv_layout_python3_preferred(tmp_path) -> None:
    """② POSIX：python3 优先于 python（两个都在时）。"""
    from framework.shared.paths import venv_python_or_none

    d = tmp_path / ".venv" / "bin"
    d.mkdir(parents=True)
    (d / "python3").write_text("", encoding="utf-8")
    assert venv_python_or_none(tmp_path).name == "python3"
    (d / "python").write_text("", encoding="utf-8")
    assert venv_python_or_none(tmp_path).name == "python3", (
        "两个都在时应优先 python3（python 可能是 py2 时代的符号链接）"
    )


def test_posix_venv_layout_python_fallback(tmp_path) -> None:
    """② 只有 `.venv/bin/python`（没有 python3）时也要找到。"""
    from framework.shared.paths import venv_python_or_none

    d = tmp_path / ".venv" / "bin"
    d.mkdir(parents=True)
    (d / "python").write_text("", encoding="utf-8")
    assert venv_python_or_none(tmp_path).name == "python"


# ---------------- ③ 没有 venv 必须如实 None ----------------

def test_no_venv_returns_none_and_falls_back(tmp_path) -> None:
    """③ `venv_python_or_none` 必须如实 None；`venv_python` 才退回当前解释器。"""
    from framework.shared.paths import venv_python, venv_python_or_none

    assert venv_python_or_none(tmp_path) is None, (
        "没有 venv 却返回了路径 —— 判据会在没有 venv 的机器上假装通过（绝不许）"
    )
    assert venv_python(tmp_path) == (sys.executable or "python3")


# ---------------- ④ 同名目录不算 ----------------

def test_directory_named_python_is_not_an_interpreter(tmp_path) -> None:
    """④ `.venv/Scripts/python.exe` 若是**目录**，不许当成解释器。"""
    from framework.shared.paths import venv_python_or_none

    (tmp_path / ".venv" / "Scripts" / "python.exe").mkdir(parents=True)
    assert venv_python_or_none(tmp_path) is None, (
        "把目录当解释器了 —— 调用方拿去执行会炸；必须 is_file() 而不是 exists()"
    )


# ---------------- ⑤ 全仓不许再硬编码 POSIX 路径 ----------------

#: 允许出现 `.venv/bin/python` 字样的场合（都不是「定位解释器」的逻辑）
_ALLOWED_FILES = {
    "framework/shared/paths.py",          # 唯一入口本体
    "tests/特性9-质量闸门体系/test_venv_python_single_entry.py",   # 本判据
    # 正确写法：把两个平台的路径都列出来当候选（`(repo/".venv"/"bin"/"python", "Linux"),
    # + (repo/".venv"/"Scripts"/"python.exe", "Windows")`）—— 不是漏了 Windows。
    "build_tools/offline_explore_chain.py",
}
_ALLOWED_SUBSTRINGS = (
    ".venv/bin/activate",                 # 文档里的激活命令
    ".venv\\Scripts\\activate",
    ".venv/bin/python -m pytest",         # 文档里的跑法
)


def _python_files():
    for d in ("framework", "tests", "build_tools", "demo"):
        base = REPO / d
        if not base.exists():
            continue
        for p in base.rglob("*.py"):
            if "__pycache__" in p.parts or ".venv" in p.parts:
                continue
            yield p


def test_no_hardcoded_posix_venv_python_in_logic() -> None:
    """⑤ 全仓扫描：不许再有**只认 POSIX** 的解释器定位逻辑（防漂移）。

    只查**代码**，不查注释/文档字符串里的跑法说明（那些是给人看的命令）。

    [!] 判据自身的两条放行规则（第一版没写，误报 4 处，被自己抓出来）：
      (1) **`tmp_path` 开头的行** —— 那是测试自己在临时目录里**造假 venv**，
          造的就是 POSIX 布局，属于被测数据，不是定位逻辑；
      (2) **同一文件里同时出现 `Scripts/python.exe`** —— 那是「把两个平台的路径都列出来当候选」
          的正确写法（`build_tools/offline_explore_chain.py:108` 就是），不是漏了 Windows。
    真正要拦的是「**只列 POSIX、从不提 Windows**」的那种。
    """
    pat = re.compile(r"""["']\.venv["']\s*/\s*["']bin["']\s*/\s*["']python""")
    offenders = []
    for p in _python_files():
        rel = p.relative_to(REPO).as_posix()
        if rel in _ALLOWED_FILES:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        # [!] 这里原来有一条「全文件提到 Scripts/python.exe 就放行」的规则 —— **已删除**。
        #   它被注释和 docstring 里的文字满足了（`test_offline_chain_python.py:9` 的 docstring
        #   就写着 `.venv/{bin,Scripts}`），于是整个文件被放行，**反向验证当场没变红**。
        #   => 教训：白名单按**文件**给，别按「文件里出现过某词」给 —— 注释谁都能写。
        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            # 放行规则 (1)：测试造假 venv
            if "tmp_path" in line:
                continue
            if any(s in line for s in _ALLOWED_SUBSTRINGS):
                continue
            if pat.search(line):
                offenders.append(f"{rel}:{i}: {stripped[:90]}")
    assert not offenders, (
        "还有**只认 POSIX** 的 venv 解释器定位逻辑 -> Windows 上会永远 skip / 找不到：\n  "
        + "\n  ".join(offenders)
        + "\n  => 改用 framework.shared.paths.venv_python / venv_python_or_none"
    )


# ---------------- ⑥ 唯一入口只转发 ----------------

def test_run_verifications_delegates_to_shared_paths() -> None:
    """⑥ `run_verifications._venv_python` 不许再自己实现一份，只许转发。"""
    src = (REPO / "tests/_runner/run_verifications.py").read_text(encoding="utf-8")
    i = src.find("def _venv_python")
    assert i > 0, "找不到 _venv_python"
    seg = src[i : i + 900]
    assert "from framework.shared.paths import venv_python" in seg, (
        "`_venv_python` 没有转发到唯一入口 —— 又要分叉出第二份实现了"
    )
    assert "Scripts" not in seg, (
        "`_venv_python` 里还留着自己的候选路径表 —— 应该完全交给 framework.shared.paths"
    )


@pytest.mark.parametrize("script", ["tests/特性7-并发与资源安全/verify_slow_target.py",
                                    "tests/特性8-离线回放/verify_offline_chain_deps.py",
                                    "tests/特性1-混合链路/test_offline_chain_python.py"])
def test_callers_use_the_single_entry(script: str) -> None:
    """⑥ 三个曾经的受害点都必须改成引用唯一入口。"""
    text = (REPO / script).read_text(encoding="utf-8")
    assert "framework.shared.paths" in text, f"{script} 没引用唯一入口"

# -*- coding: utf-8 -*-
"""未绑定名闸门（静态 · 零依赖 · 不依赖 demo）—— 防「拷代码漏作用域」复发。

**为什么需要**（2026-10-10 干净环境 E2E 实录）：
`explorer._collect_page_context()` 的单页路径引用了只在**多页路径**存在的 `page_name`
（S1 收口把两行拷过去、漏了作用域）-> Python 只在跑到那行抛 `NameError`，
而它被 `except Exception` 兜成「探测失败 -> 退化 0 项」——**一类判据全绿、真跑才红**，
整条单页探测静默失效。同类：`cli._int_flag` 里 `cast(raw)`（`cast` 全文件从没定义），
`prune --keep/--keep-runs/--keep-days/--max-delete` 一带值就崩 —— 也是老代码里躺了很久才被抓出。

判据：
  1) 正向：`framework/` + `build_tools/` 无未绑定名
  2) 负向自证：故意写一个未绑定名文件，扫描器**必须报**（防「闸门永远绿」）
  3) 负向自证：干净文件必须 0 报（防「闸门无脑红」）
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCAN = REPO / "tests" / "特性9-质量闸门体系" / "verify_undefined_names.py"


def _run(paths: list[str]):
    r = subprocess.run([sys.executable, str(SCAN), *paths],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=str(REPO))
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def test_framework_and_build_tools_have_no_undefined_names():
    """正向：框架与构建工具里不得有「引用了但作用域内没绑定」的名字。"""
    code, out = _run(["framework", "build_tools"])
    assert code == 0, f"发现未绑定名（这类错会被 except 兜成静默降级，必须当场修）：\n{out}"


def test_scanner_catches_copy_paste_scope_bug():
    """负向自证：把 2026-10-10 那个真 bug 的最小形态喂进去 —— 必须报。"""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "copy_paste_bug.py"
        f.write_text(
            "def multi(pages):\n"
            "    page_name = pages[0]['name']\n"
            "    return _register(page_items, page_name)\n"
            "\n"
            "def single(pages):\n"
            "    return _register(page_items, page_name)\n",
            encoding="utf-8")
        code, out = _run([str(f)])
    assert code == 1, f"扫描器没抓到未绑定名（闸门失效）：\n{out}"
    assert "page_name" in out and "single" in out, out


def test_scanner_stays_green_on_clean_code():
    """负向自证（反向）：干净代码必须 0 报 —— 否则闸门会「无脑红」被无视。"""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "clean.py"
        f.write_text(
            "import os\n"
            "X = 1\n"
            "COMPS = [i for i in range(3)]\n"
            "if __name__ == '__main__':\n"
            "    y = os.getcwd()\n"
            "\n"
            "def f(a):\n"
            "    b = a + X\n"
            "    return [b for _ in range(2)]\n",
            encoding="utf-8")
        code, out = _run([str(f)])
    assert code == 0, f"干净代码被误报（宁漏不误伤）：\n{out}"

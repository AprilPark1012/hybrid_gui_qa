"""培训页渲染入口的「真跑」判据（2026-09-24 补 —— 一类当晚没抓住的漏网）。

**为什么要有它**：`tests/` 结构搬迁那天，我做了批量路径替换，**误伤了没搬家的 `build_tools/build_html.py`**
（它的 `parents[1]` 被改成 `parents[2]` ⇒ 输出路径指到 `/home/admin/docs` ⇒ 渲染 `FileNotFoundError`）。
当时一类 **485 passed 全绿** —— 因为它只 import `build_html`，**从不真跑渲染** ⇒ 又一次「判据比现实宽松」。
本判据直接**子进程真跑一次渲染**（幂等、秒级），并断言产物落在仓库内。

判据：
  ① `python build_tools/build_html.py` exit 0（真跑，不是只 import）
  ② 渲染产物 `docs/training.html` 落在**仓库内**且非空
  ③ 负向自证：断言脚本里的输出路径常量由 `__file__` 推导（防被改成绝对/越界路径）
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HTML = REPO / "docs" / "training.html"
BUILDER = REPO / "build_tools" / "build_html.py"


def test_render_entrypoint_really_runs():
    """★真跑渲染：失败会立刻暴露「输出路径被改坏 / 生成器坏了」这类一类看不出的病。"""
    assert BUILDER.is_file(), f"缺 {BUILDER}"
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    p = subprocess.run([sys.executable, str(BUILDER.relative_to(REPO))], cwd=str(REPO),
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=420, env=env)
    out = (p.stdout or "") + (p.stderr or "")
    assert p.returncode == 0, "渲染入口起不来（exit %s）：\n%s" % (p.returncode, out[-600:])
    assert HTML.is_file() and HTML.stat().st_size > 50_000, (
        f"渲染产物异常：{HTML}（存在={HTML.exists()}）—— 输出路径可能被改到仓库外")
    # 路径必须落在仓库里（越界 = 交付包里没有培训页）
    assert REPO in HTML.resolve().parents, f"培训页输出到了仓库外：{HTML}"
    assert "tests/frameworkTest" in HTML.read_text(encoding="utf-8", errors="replace"), (
        "培训页里没有新目录结构（tests/frameworkTest）⇒ 生成器的路径文案没同步")


def test_builder_resolves_paths_from_its_own_file():
    """契约：渲染器的路径由 `__file__` 推导（写死绝对路径 / 层级写错都会立刻越界）。"""
    src = BUILDER.read_text(encoding="utf-8")
    assert "__file__" in src, "渲染器没有用 __file__ 推导路径 ⇒ 换个工作目录就会写错地方"
    assert "/home/" not in src.replace("\n", ""), "渲染器里出现了绝对家目录路径"

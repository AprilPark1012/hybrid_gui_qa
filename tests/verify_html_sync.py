#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R8 判据（特性验证）：`docs/training.html` 必须能由代码**可复现地**生成、且与当前代码一致。

三条判据，缺一不可：
1. **可复现**：换哈希种子各生成一次（输出到 /tmp，不碰仓库）→ 两次 md5 必须相同。
2. **同步**：生成结果与仓库里已提交的 `docs/training.html` **逐字节一致**（以代码为基准）。
3. **健康**：生成结果里零 `<span <span`（畸形嵌套 —— 高亮器退化的信号）。

为什么必须单独有这条：不改代码也能「html 看着没问题」，但生成器不可复现时，
**「html 与代码是否同步」根本无法用「重跑比对」来判定**（重跑必出 diff）。这条判据把 R8 变成可验证的。

跑法： python tests/verify_html_sync.py            （推荐）
       python -m pytest tests/verify_html_sync.py -q
退出码：0 通过 / 1 不同步（需 `python build_tools/build_html.py` 后提交）/ 2 用法 / 3 跳过（缺文件）
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "docs" / "training.html"
PY = sys.executable
OK, FAIL, USAGE, SKIP = 0, 1, 2, 3


def force_stdio():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")       # type: ignore[union-attr]
        except Exception:
            pass


def _build(dst: Path, seed: str):
    """在 /tmp 生成一份（BUILD_HTML_OUT + 指定哈希种子），返回 (ok, 输出)。"""
    env = {**os.environ, "BUILD_HTML_OUT": str(dst), "PYTHONHASHSEED": seed}
    r = subprocess.run([PY, "build_tools/build_html.py"], cwd=str(BASE), env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def main() -> int:
    force_stdio()
    print("=" * 64)
    print("  R8 判据 · 培训页 html 与代码的同步性 / 可复现性")
    print(f"  仓库: {BASE}")
    print("=" * 64)
    if not (BASE / "build_tools" / "build_html.py").exists():
        print("  ⏭️ 跳过：找不到 build_tools/build_html.py")
        return SKIP

    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="verify_html_sync_"))
    a, b = tmp / "a.html", tmp / "b.html"
    bad = []

    ok1, out1 = _build(a, "0")
    ok2, out2 = _build(b, "12345")
    if not (ok1 and ok2):
        print(f"  ❌ 生成失败：{(out1 or out2)[-400:]}")
        return USAGE

    # ① 可复现
    same = _md5(a) == _md5(b)
    print(f"  {'✅' if same else '❌'} ① 可复现：两个哈希种子 → md5 {'相同' if same else '不同'}"
          f"  ({_md5(a)[:8]} / {_md5(b)[:8]})")
    if not same:
        bad.append("生成不可复现")

    # ② 同步（与仓库里已提交的那份逐字节比）
    if not OUT.exists():
        print("  ⏭️ 仓库里没有 docs/training.html，跳过『同步』判据")
    else:
        synced = a.read_bytes() == OUT.read_bytes()
        print(f"  {'✅' if synced else '❌'} ② 同步：生成结果与 docs/training.html "
              f"{'逐字节一致' if synced else '不一致 ⇒ 需 python build_tools/build_html.py 后提交'}")
        if not synced:
            bad.append("html 与代码不同步")

    # ③ 健康（零畸形嵌套）
    txt = a.read_text(encoding="utf-8")
    n_bad = txt.count("<span <span")
    print(f"  {'✅' if n_bad == 0 else '❌'} ③ 健康：畸形 span <span <span = {n_bad} 处（要求 0）")
    if n_bad:
        bad.append(f"畸形 span {n_bad} 处")

    print("-" * 64)
    if bad:
        print(f"  ❌ 未通过：{' / '.join(bad)}")
        print("     修法：python build_html.py && git add docs/training.html && 提交")
        return FAIL
    print("  ✅ 全部通过（可复现 + 与代码同步 + 无畸形嵌套）")
    return OK


def test_html_sync():                      # pytest 入口
    force_stdio()
    assert main() == OK


if __name__ == "__main__":
    sys.exit(main())

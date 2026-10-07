"""二类验证（真跑 demo）：锚点内表单字段的 target 步**不能落到 get_by_text**（P22 批 5）。

真值背景（2026-09-30）：订单详情页行内输入框 `<input name="qty" title="数量" aria-label="数量">`
在「锚点下钻」路径上被生成成 `...get_by_text("数量", exact=True)` ⇒ 表单控件没有文本节点
⇒ 定位永远 0 命中（用例报「元素定位失败且自愈未成功」）。

判据：
  V1 这类元素的 path 的 target 步 by ∈ {placeholder,label,title,role}（**不许是 text**）；
  V2 且由它合成出的 primary 表达式里不含 get_by_text（避免"a 过了、拼出来还是错的"）。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from framework.tools.common.text_io import force_stdio       # noqa: E402

force_stdio()

import os
import sys

# cwd 归位到仓库根（sys.path 上面已按 __file__ 自动定位；这里同样不写死本机路径）
os.chdir(str(Path(__file__).resolve().parents[2]))

from playwright.sync_api import sync_playwright                              # noqa: E402

from framework.tools.generate.generator import _semantic_to_locator_expr     # noqa: E402
from framework.tools.probe.probe import probe_page                            # noqa: E402
from framework.tools.run.login import ensure_logged_in                       # noqa: E402

BASE = "http://localhost:8000"
AUTH = {"login_api": "/api/login", "username": "super",
        "password": "super@123", "token_key": "demo_token"}


def main() -> int:
    fails: list[str] = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        ctx = b.new_context()
        ensure_logged_in(ctx, BASE, AUTH)
        page = ctx.new_page()
        page.goto(BASE + "/order_detail.html?no=SO-1101", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        items = probe_page(page, page_name="订单详情页")
        b.close()

    targets = [it for it in items if "数量" in str(it.get("semantic_name") or "")
               and it.get("path")]
    print(f"带 path 的「数量」元素：{len(targets)} 个")
    if not targets:
        print("❌ 没探到这类元素（探测口径变了？）")
        return 1
    for it in targets:
        tgt = [s for s in it["path"] if s.get("axis") == "target"]
        expr = _semantic_to_locator_expr(it)
        by = (tgt[0].get("by") if tgt else None)
        print(f"  {it.get('semantic_name')}: target.by={by} → {expr[:96]}")
        if by == "text":
            fails.append(f"{it.get('semantic_name')} 的 target 步落到了 text（对表单控件无效）")
        if "get_by_text" in expr:
            fails.append(f"{it.get('semantic_name')} 合成出 get_by_text：{expr[:80]}")

    if fails:
        print("\n❌ FAIL")
        for f in fails:
            print("   -", f)
        return 1
    print("\n✅ PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())

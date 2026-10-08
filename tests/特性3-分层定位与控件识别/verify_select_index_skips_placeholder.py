"""二类验证（真跑 demo）：select 的 `index` 语义 = 第 N 个**非空**选项。

为什么（P22 批 5 · 真值 2026-09-30）：
  demo 的 `#sel-o-bu/#sel-o-mu/#sel-o-file/#sel-o-cust` 第一个 option 是 `value=""` 的
  「请选择」（`demo/order_new.html:45,51,57,69`），而场景里「各选第一项」的人话意思显然是
  「选第一个**真**选项」-> `index=0` 必须落到 bu_a 之类。
  踩过的坑：按字面 index 0 选到「请选择」-> 表单校验不过 -> 订单建不出来 ->
  后续 first_row 断言报「表格没有第一行」（排查了两轮）。

判据：
  1. 正向：`index=0` 之后该 select 的 value 非空、selectedIndex > 0；
  2. 越界：`index` 超出真实选项数 -> 明确报错（绝不静默选空）。
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

from playwright.sync_api import sync_playwright                     # noqa: E402

from framework.tools.run.login import ensure_logged_in              # noqa: E402

BASE = "http://localhost:8000"
AUTH = {"login_api": "/api/login", "username": "super",
        "password": "super@123", "token_key": "demo_token"}


def _only(page, sel: str) -> tuple[str, int]:
    return page.locator(sel).input_value(), page.eval_on_selector(sel, "e => e.selectedIndex")


def main() -> int:
    fails: list[str] = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        ctx = b.new_context()
        ensure_logged_in(ctx, BASE, AUTH)
        page = ctx.new_page()
        page.goto(f"{BASE}/order_new.html", wait_until="domcontentloaded")
        # 等字典真的加载完（fetch /api/dict?kind=bu 回来才有真选项）—— 原来固定 1.5s 太短，
        # 会把「还没加载完」误判成「控件只有 1 个选项」（2026-09-30 踩过）。
        for _ in range(30):
            page.wait_for_timeout(200)
            if page.locator("#sel-o-bu option").count() > 1:
                break
        print(f"#sel-o-bu 选项数 = {page.locator('#sel-o-bu option').count()}")

        sys.path.insert(0, "scripts/generated")
        import _harness as H                                        # noqa: E402

        # (1) 正向：index=0 -> 第一个真选项（跳过「请选择」）
        H._act(page, "select", semantic="业务单元@新建订单页",
               primary=lambda p: p.get_by_role("combobox", name="业务单元"), index=0)
        val, idx = _only(page, "#sel-o-bu")
        print(f"(1) index=0 -> #sel-o-bu value={val!r} selectedIndex={idx}")
        if not val.strip() or idx == 0:
            fails.append(f"index=0 选到了空占位（value={val!r} selectedIndex={idx}）")

        # (2) 反向自证：同一控件按字面选 0（不跳占位）会是空值 —— 证明(1)确实来自新逻辑
        page.select_option("#sel-o-bu", index=0)
        v0, i0 = _only(page, "#sel-o-bu")
        print(f"(2) 字面 index=0（旧行为）-> value={v0!r} selectedIndex={i0}（应为空/0，作为对照）")

        # (3) 越界 -> 明确报错
        try:
            H._act(page, "select", semantic="业务单元@新建订单页",
                   primary=lambda p: p.get_by_role("combobox", name="业务单元"), index=99)
            fails.append("越界 index=99 居然没报错（静默选中 = 假绿）")
        except AssertionError as e:
            print(f"(3) 越界 index=99 -> 正确报错：{str(e)[:80]}")
        except Exception as e:                                      # noqa: BLE001
            print(f"(3) 越界 index=99 -> 报了别的异常 {type(e).__name__}: {str(e)[:80]}（可接受但非预期）")

        b.close()

    if fails:
        print("\n[NG] FAIL")
        for f in fails:
            print("   -", f)
        return 1
    print("\n[OK] PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())

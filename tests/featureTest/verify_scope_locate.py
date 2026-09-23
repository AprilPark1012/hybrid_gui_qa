"""「顶层锚点 + 容器内下钻」定位能力的端到端验证（二类）—— P16 批 1「判据先行」第 ② 组。

**为什么要有它**（AprilPark1012 2026-09-22 现场口径）：
真实系统一般**只有顶层元素**有 `data-testid`（表格 / 弹层 / 工具栏…），要操作的子元素（行、单元格、
行内链接按钮）**没有**埋点 ⇒ 框架必须会「从锚点下钻」。而当前框架的 Tier1 第一级就是 `data-testid`，
demo 又几乎每个控件都埋了 ⇒ **这条能力从来没被真实触发过**（未验 ≠ 已验证）。
本脚本就是它的判据：用**零 testid 的夹具页**（`tests/featureTest/fixtures/zero_testid_page.html`）当真环境。

**被测契约（批 2/3 要实现）**：
    framework.tools.probe.scope_locate(page, anchor, path) -> dict
      anchor = {"kind": "table|dialog|region|form", "by": "test_id|heading|aria_label|role", "value": ...}
      path   = [{"axis": "row", "by": "text|nth",  "value": ...},
                {"axis": "col", "by": "header|field|index", "value": ...},
                {"axis": "target", "by": "role|text", "value": ...}]
      返回   {"ok": bool, "locator": str|None, "locator_obj": Locator|None, "count": int|None,
              "strategy": str, "reason": str}
    **红线**：任一级歧义（count != 1）⇒ `ok=False` 如实失败，**不许 nth 猜**（猜错 = 假通过）。

**红态预期**：能力未实现 ⇒ 本脚本红（批 3 目标转绿）。退出码 0 通过 / 3 跳过（无浏览器）/ 1 失败。
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests" / "frameworkTest"))
from framework.tools.common.text_io import force_stdio          # noqa: E402

force_stdio()

FIXTURE = REPO / "tests" / "featureTest" / "fixtures" / "zero_testid_page.html"
checks: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" —— {detail}" if detail else ""))


def demo_up() -> bool:
    try:
        urllib.request.urlopen("http://localhost:8000/api/health", timeout=3)
        return True
    except Exception:
        return False


def main() -> int:
    print("=" * 64)
    print(" 顶层锚点 + 容器内下钻 · 端到端验证（P16 批 1 判据 · 零 testid 夹具页）")
    print("=" * 64)

    # 能力是否已实现（批 2/3 的目标）—— 未实现就如实红，不假装通过
    # 用 importlib 探测（不用静态 import）：本能力批 2/3 才落地，静态 import 会让 R9「搬家协议」判据
    # （tests/frameworkTest/test_import_targets.py）报「import 目标不存在」——那会掩盖真正的搬家漏改，属于污染判据。
    import importlib
    try:
        scope_locate = importlib.import_module("framework.tools.probe.scope_locate").scope_locate
        have_api = True
        err = ""
    except Exception as e:                                             # noqa: BLE001
        have_api = False
        scope_locate = None
        err = f"{type(e).__name__}: {e}"

    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:                                             # noqa: BLE001
        print(f"  ⏭️  没有 playwright（{e}）⇒ 跳过")
        return 3

    if not have_api:
        print(f"  ❌ 定位能力尚未实现（预期红态）：{err}")
        print("     批 2/3 目标：probe 采集 anchor/path + locator_bridge 新增 anchor+path 级 + "
              "scope_locate 入口")

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(FIXTURE.as_uri())
        page.wait_for_selector("table")

        # ⓪ P16 批 2 判据：probe 采集 —— 零 testid 页上必须能采集出「锚点 + 相对路径」
        # （本批已实现 ⇒ 这条应当**绿**；下面 ①~⑥ 要等批 3 的 scope_locate 能力 ⇒ 红）
        from framework.tools.probe.probe import probe_page
        items = probe_page(page)
        row_items = [it for it in items if it.get("path")]
        row_links = [it for it in row_items
                     if any(s.get("axis") == "target" and s.get("value") == "link" for s in it["path"])]
        anchor_ok = bool(row_links) and all(
            (it.get("anchor") or {}).get("kind") == "table" for it in row_links)
        record("⓪ probe 采集：零 testid 表格里的行内链接带 anchor(kind=table)",
               anchor_ok, f"行内链接 {len(row_links)} 个 · anchor={[it.get('anchor') for it in row_links]}")

        row_path_ok = False
        if row_links:
            p0 = row_links[0].get("path") or []
            axes = {(s.get("axis"), s.get("by")) for s in p0}
            row_path_ok = (("row", "text") in axes and ("col", "header") in axes and ("target", "role") in axes)
        record("⓪-b probe 采集：路径 = 行锚文本 + 表头列（无 data-field 即降级）+ 目标语义",
               row_path_ok, f"path={row_links[0].get('path') if row_links else None}")

        toolbar_btns = [it for it in items if it.get("tag") == "button" and it.get("name") == "搜索"]
        region_ok = bool(toolbar_btns) and (toolbar_btns[0].get("anchor") or {}).get("kind") == "region"
        # ★2026-09-22（P16 批 6 · 口径 C）判据更新：旧契约是「工具栏按钮**无**行内路径」，
        # 那是在「只有表格行内才有路径」的时代。撤掉内层埋点后，**只要有锚点就该产出相对路径**
        # （弹层/区块内的字段全靠它定位，实测四个下拉没了它就定位不了）——
        # 所以现在断言的是「锚到 region **且恰好一条 target 步**」。
        _btn_path = toolbar_btns[0].get("path") if toolbar_btns else None
        record("⓪-c probe 采集：工具栏按钮锚到 region（aria-label=工具栏），且产出一条容器内相对路径（口径 C 新契约）",
               region_ok and isinstance(_btn_path, list) and len(_btn_path) == 1
               and _btn_path[0].get("axis") == "target",
               f"anchor={toolbar_btns[0].get('anchor') if toolbar_btns else None} path={toolbar_btns[0].get('path') if toolbar_btns else None}")

        # ★形状对 ≠ 能用：拿探到的锚点+路径**真定位一次**（下面 locate 定义在即，先声明再补这条判据）
        def locate(anchor, path):
            if not have_api:
                return {"ok": False, "reason": "capability_missing"}
            return scope_locate(page, anchor=anchor, path=path)

        # ★形状对 ≠ 能用（2026-09-22）：把刚探到的「锚点 + 路径」**真定位一次**。
        # 只断言字段形状是**假绿**的高发区——路径长得对、执行层不认（或表达式拼不出）照样定位不到。
        _r_btn = locate(toolbar_btns[0].get("anchor"), _btn_path) if toolbar_btns else {"ok": False}
        record("⓪-d 工具栏按钮的「锚点 + 路径」**真能定位**（唯一命中）",
               bool(_r_btn.get("ok")) and _r_btn.get("count") == 1,
               f"ok={_r_btn.get('ok')} count={_r_btn.get('count')} {_r_btn.get('reason','')}")

        # ① 零 testid 页面：按「行锚文本 + 表头文本列 + 目标语义」下钻拿到行内链接
        r = locate({"kind": "table", "by": "heading", "value": "采购单列表"},
                   [{"axis": "row", "by": "text", "value": "PO-1001"},
                    {"axis": "col", "by": "header", "value": "链接"},
                    {"axis": "target", "by": "role", "value": "link"}])
        # 2026-09-22（P16 批 3）加严：`locator` 必须是**表达式字符串**（可直接粘进控制台 / 进日志），
        # 不是 Locator 对象的 repr —— 实测踩到过：把 Locator 当字符串插值 ⇒ 值变成 `<Locator frame=…>`。
        _loc = r.get("locator")
        record("① 零 testid 页：行锚文本 + 表头列 + 链接 ⇒ 唯一命中（count=1）",
               bool(r.get("ok")) and r.get("count") == 1,
               f"ok={r.get('ok')} count={r.get('count')} locator={_loc} {r.get('reason','')}")
        record("①-b locator 是**表达式字符串**（不是 `<Locator …>` repr）",
               isinstance(_loc, str) and "locator(" in _loc and "get_by_role" in _loc
               and not _loc.startswith("<Locator"),
               f"locator={str(_loc)[:90]}")

        # ② 表格**无 data-field** ⇒ 按「表头文本 + 列序」定位该列里的按钮（他 2026-09-22 拍的 C 降级路径）
        r = locate({"kind": "table", "by": "heading", "value": "采购单列表"},
                   [{"axis": "row", "by": "text", "value": "PO-1002"},
                    {"axis": "col", "by": "header", "value": "操作"},
                    {"axis": "target", "by": "role", "value": "button"}])
        record("② 无 data-field ⇒ 表头文本 + 列序降级仍能定位（count=1）",
               bool(r.get("ok")) and r.get("count") == 1,
               f"ok={r.get('ok')} count={r.get('count')} {r.get('reason','')}")

        # ③ ★ 负向：行锚文本「选择」在两行都出现 ⇒ 必须**如实失败**，绝不许 nth 猜第一个
        r = locate({"kind": "table", "by": "heading", "value": "采购单列表"},
                   [{"axis": "row", "by": "text", "value": "选择"},
                    {"axis": "target", "by": "role", "value": "button"}])
        reason = str(r.get("reason", ""))
        ambiguous_reasons = ("歧义", "唯一", "ambiguous", "unique")
        record("③ ★负向：行锚文本歧义（两行都含「选择」）⇒ 必须 ok=False 且理由指向歧义/唯一性",
               r.get("ok") is False and any(w in reason.lower() or w in reason for w in ambiguous_reasons),
               f"ok={r.get('ok')} reason={reason or '（空 ⇒ 能力缺失也会假绿，必须给理由）'}")

        # ④ 同名控件消歧：工具栏里的输入框 vs 弹层里的同名输入框 ⇒ 靠容器锚点（aria-label）区分
        r_bar = locate({"kind": "region", "by": "aria_label", "value": "工具栏"},
                       [{"axis": "target", "by": "role", "value": "textbox"}])
        r_dlg = locate({"kind": "dialog", "by": "aria_label", "value": "新建采购单"},
                       [{"axis": "target", "by": "role", "value": "textbox"}])
        ok4 = (r_bar.get("ok") and r_bar.get("count") == 1 and r_dlg.get("ok")
               and r_dlg.get("count") is not None and r_dlg.get("count") >= 1)
        record("④ 同名输入框：容器锚点（aria-label）区分工具栏 vs 弹层 ⇒ 各自能定位",
               bool(ok4),
               f"bar={r_bar.get('ok')}/{r_bar.get('count')} dialog={r_dlg.get('ok')}/{r_dlg.get('count')}")

        browser.close()

    # ⑤/⑥ demo 侧（真实容器 testid 下的下钻；撤掉行内埋点后这条路径必须照样成立）
    if not demo_up():
        print("  ⏭️  demo 未在运行 ⇒ 跳过 ⑤/⑥（不当作通过）")
    else:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.goto("http://localhost:8000/contracts.html")
            page.wait_for_selector("table")

            r = scope_locate(page,
                             anchor={"kind": "table", "by": "test_id", "value": "tbl-contracts"},
                             path=[{"axis": "row", "by": "text", "value": "HT-1005"},
                                   {"axis": "col", "by": "field", "value": "contractNo"},
                                   {"axis": "target", "by": "role", "value": "link"}]) if have_api else {"ok": False}
            record("⑤ demo：tbl-contracts 锚点 + 行锚文本 + data-field 列 ⇒ 唯一命中（不依赖 link-HT-1005）",
                   bool(r.get("ok")) and r.get("count") == 1, f"ok={r.get('ok')} {r.get('reason','')}")

            r = scope_locate(page,
                             anchor={"kind": "dialog", "by": "test_id", "value": "modal-customer"},
                             path=[{"axis": "row", "by": "text", "value": "北京华信科技有限公司"},
                                   {"axis": "target", "by": "role", "value": "button"}]) if have_api else {"ok": False}
            record("⑥ demo：弹层容器锚点 + 行锚文本 + 按钮 ⇒ 唯一命中（不依赖 pick-* 埋点）",
                   bool(r.get("ok")) and r.get("count") == 1, f"ok={r.get('ok')} {r.get('reason','')}")
            browser.close()

    bad = [n for n, ok, _ in checks if not ok]
    print("-" * 64)
    if bad:
        print(f"  ❌ 未通过：{len(bad)}/{len(checks)} 项 —— {bad}")
        if not have_api:
            print("  ⓘ 红态原因：定位能力未实现（批 2/3 目标）—— 判据先行，符合预期")
        return 1
    print(f"  ✅ 全部通过（{len(checks)} 项：零 testid 下钻 + data-field 降级 + 歧义如实失败 + 容器消歧）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

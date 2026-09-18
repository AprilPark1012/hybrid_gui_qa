"""元素歧义闸门 · 端到端复现（批次 2 · S1/S2 / 2026-09-18）。

为什么单独一个脚本、不叫 test_*.py：它要开真浏览器（本机 1.87G / 无 swap，内存紧），
跟主用例套件跑在一起会抢内存 —— 与 `verify_picker_layer.py` / `verify_slow_target.py` 同一口径。

跑法（**不需要 demo**，用 tests/fixtures/ambiguous_page.html 起一个自包含页面）：
    cd ~/hybrid_gui_qa && .venv/bin/python tests/verify_element_ambiguity.py
期望：最后一行 `全部符合预期 ✅` 且 exit 0；内存不足时 **SKIP exit 3（绝不报假绿）**。

判据：
  ① 静态：`explorer._merge_items` 真的在**合并之后**调 `probe.assign_semantic_names`（结构判据，不数字符串）；
  ② 真浏览器：事故形态（两枚同名按钮，一枚在未打开的弹窗里）下 ——
     · 旧算法（按名字 setdefault 合并）裸名「选择客户」**仍然存在**、且指向搜索区那枚 ⇒ 复现「静默点错」；
     · 新算法（合并后统一重命名）裸名**必须消失**、两枚各有唯一名 ⇒ 用例引用裸名会被映射质量闸拦下（fail loud）；
  ③ 报错体检：缺失名若是同名冲突组的 base 名，报错必须**列出候选**（人话，不是干巴巴「未映射」）。
"""
from __future__ import annotations

import ast
import inspect
import sys
import textwrap
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from framework.text_io import force_stdio                   # noqa: E402

force_stdio()

from framework.browser import launch_opts                  # noqa: E402
from framework.probe import probe_page, assign_semantic_names   # noqa: E402
from framework.explorer import _try_collect_modal_items, _merge_items   # noqa: E402

FIXTURE = BASE / "tests" / "fixtures" / "ambiguous_page.html"
MIN_MEM_MB = 550          # 一个 headless Chromium ≈515MB；不够就 SKIP，不硬跑（本机 OOM 会连杀网关）

fails: list[str] = []


def check(ok: bool, desc: str, detail: str = "") -> None:
    print(f"  {'✅' if ok else '❌'} {desc}{('  ' + detail) if detail else ''}")
    if not ok:
        fails.append(desc)


def mem_available_mb() -> int:
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) // 1024
    return -1


def old_merge_by_name(base_items: list[dict], layer_items: list[dict]) -> list[dict]:
    """**改造前的合并算法**（按 semantic_name 字符串 setdefault）—— 只为对照复现，不参与生产路径。"""
    out, seen = list(base_items), {it.get("semantic_name") for it in base_items}
    for it in layer_items:
        if it.get("semantic_name") not in seen:
            out.append(it)
            seen.add(it["semantic_name"])
    return out


def main() -> int:
    # —— 一、静态判据 ——
    print("===== 一、静态判据（防复发：合并不重命名 / 命名不留痕）=====")
    src = textwrap.dedent(inspect.getsource(_merge_items))
    called = {n.func.id for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    check("assign_semantic_names" in called,
          "_merge_items 在合并后调 assign_semantic_names（合并后统一重命名）")
    probe_src = (BASE / "framework" / "probe.py").read_text(encoding="utf-8")
    for key in ("base_name", "ctx_token", "name_source", "base_conflict"):
        check(key in probe_src, f"probe 命名留痕字段存在：{key}")

    mem = mem_available_mb()
    print(f"\n[内存] MemAvailable = {mem} MB（跑浏览器需要 ≥{MIN_MEM_MB} MB）")
    if mem < MIN_MEM_MB:
        print("SKIP：内存不够，未跑浏览器判据（如实跳过，不报假绿）→ exit 3")
        return 3

    # —— 二、真浏览器：把事故形态跑出来 ——
    print("\n===== 二、真浏览器复现（两枚同名按钮，一枚在未打开的弹窗里）=====")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(**launch_opts(headless=True))
        pg = b.new_page()
        pg.goto(FIXTURE.as_uri())
        pg.wait_for_load_state("networkidle")

        base_items = probe_page(pg)
        layer_items = _try_collect_modal_items(pg, base_items)

        def name_of(items_, test_id):
            return next((i["semantic_name"] for i in items_ if i.get("test_id") == test_id), None)

        search_base = name_of(base_items, "btn-pick-c-search")
        print(f"  基础轮：搜索区那枚 = {search_base!r}；本轮清单里 '选择客户' 出现 "
              f"{sum(1 for i in base_items if i.get('semantic_name') == '选择客户')} 次")
        check(search_base == "选择客户",
              "前提成立：弹窗未开时，搜索区那枚确实「唯一」⇒ 独占裸名（这就是陷阱）")
        check(any(i.get("test_id") == "btn-pick-c-modal" for i in layer_items),
              "弹层探测收到了弹窗里那枚同名按钮", f"(layer {len(layer_items)} 项)")

        # 旧算法：裸名被搜索区那枚占住 ⇒ 用例引用裸名会静默点到它（错的那枚）
        old_merged = old_merge_by_name(base_items, layer_items)
        old_bare = name_of(old_merged, "btn-pick-c-search")
        check(old_bare == "选择客户",
              "复现旧病：裸名仍存在 ⇒ 用例引用裸名会静默绑定到**搜索区**那枚（被遮挡 ⇒ 点击超时）")
        check(name_of(old_merged, "btn-pick-c-modal") not in (None, "", "选择客户"),
              "旧算法下弹窗那枚只能靠后缀区分（与裸名并存，极易选错）",
              f"→ {name_of(old_merged, 'btn-pick-c-modal')!r}")

        # 新算法：合并后统一重命名 ⇒ 裸名消失，两枚各有唯一名
        merged = _merge_items(base_items, layer_items)
        names = [i["semantic_name"] for i in merged]
        check("选择客户" not in names,
              "修复生效：合并后裸名 '选择客户' 已消失 ⇒ 用例引用裸名会被映射质量闸拦下（fail loud）")
        n_search, n_modal = name_of(merged, "btn-pick-c-search"), name_of(merged, "btn-pick-c-modal")
        check(n_search and n_modal and n_search != n_modal,
              "两枚同名控件各有唯一且不同的名字", f"{n_search!r} / {n_modal!r}")
        check(all(i.get("base_conflict") == 2 for i in merged
                  if i.get("test_id") in ("btn-pick-c-search", "btn-pick-c-modal")),
              "命名留痕：base_conflict=2（下游据此判歧义）")
        check(all(i.get("name_source") in ("ctx", "seq") for i in merged
                  if i.get("test_id") in ("btn-pick-c-search", "btn-pick-c-modal")),
              "命名留痕：name_source 标明是「上下文/序号消歧」而非裸名")
        # 非同名控件不受影响（不误伤）
        check(bool(name_of(merged, "btn-new") == "新建合同"
                   and name_of(merged, "btn-search") == "搜索"),
              "不误伤：本来唯一的控件仍保持裸名（老用例零影响）")
        b.close()

    # —— 三、报错体检：缺失名要给候选 ——
    print("\n===== 三、报错体检（同名歧义 ≠ 拼写错误）=====")
    import framework.generator as g
    from framework.generator import _record_conflict_bases, UnmappedElementsError
    g._CONFLICT_BASES.clear()
    items = [it for it in merged if it.get("test_id") in ("btn-pick-c-search", "btn-pick-c-modal")]
    if not items:                                   # 内存跳过时兜底（正常路径不会到这）
        items = [{"semantic_name": "选择客户@客户", "base_name": "选择客户", "base_conflict": 2},
                 {"semantic_name": "选择客户@新建合同", "base_name": "选择客户", "base_conflict": 2}]
    if items[0].get("name_source") is None:         # 兜底样本需要先命名
        assign_semantic_names(items)
    _record_conflict_bases(items)
    e = UnmappedElementsError(["选择客户"], sources="现场probe补齐 0/1 项",
                              conflicts=g._CONFLICT_BASES)
    check("选择客户" in e.conflicts and len(e.conflicts["选择客户"]) == 2,
          "缺失名是冲突组 base 名时，报错带上了候选清单",
          f"→ {e.conflicts.get('选择客户')}")
    g._CONFLICT_BASES.clear()

    print()
    if fails:
        print(f"❌ {len(fails)} 条判据不符预期：")
        for f in fails:
            print(f"   · {f}")
        return 1
    print("全部符合预期 ✅（旧行为可复现、新行为拦得住、既有唯一名未误伤）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""【Playwright】测试代码生成器 —— 按操作类型翻译 + 数据抽离版。

职责（对应需求：cases 自然语言用例 → 生成 Playwright 脚本 + 抽离数据）：
  1. 读 cases/*.json（自然语言用例，写死测试数据）
  2. 按【操作类型】(op) 翻译成 Playwright 代码（goto/click/fill/select/check/assert）
     —— 元素定位走 locator_bridge（唯一性校验），彻底解耦 demo。
  3. 抽离步骤里的字面值（fill.value / select.value / asserts[].expect）到
     scripts/datasets/<case_id>.json，脚本中对应位置替换成 _data(key, ctx) 引用（脚本数据分离）。
  4. 生成 scripts/<case_id>.py(pytest用例) + scripts/conftest.py(浏览器/变量池/动态占位符/日志)。

✔ 本文件不含 LLM 调用 —— 纯确定性生成。AI 语义识别(explore)在之前已完成元素映射。
"""
from __future__ import annotations
import json
from pathlib import Path

from .config import BASE, CASES_DIR, SCRIPTS_DIR
from .browser import CHROMIUM_ARGS
from .case_builder import CaseQualityError, case_errors


def _gate_false_green(cases: list[dict]) -> None:
    """**假绿红线闸**（2026-09-17）：用例带红线问题 ⇒ 拒绝生成任何产物。

    与映射质量闸（UnmappedElementsError）同一口径：**产物永不允许带假绿**。
    目前红线只有一类 —— 换页证据（kind=url 断言）没有区分力（如 `expect: localhost`：
    换页前后两个页面都含它 ⇒ 点击后立刻通过，等于没验换页）。
    手写用例与 AI 用例一视同仁：这条讲的是「证据有没有牙」，与谁写的无关。
    """
    bad = [(str(c.get("case_id") or "(无名)"), case_errors(c)) for c in cases]
    bad = [(cid, errs) for cid, errs in bad if errs]
    if bad:
        raise CaseQualityError(bad)


def _chromium_args_literal() -> str:
    """把 CHROMIUM_ARGS 渲染成 Python 字面量，供【内联】进 conftest 模板。

    内联而非 import：生成的 scripts/ 保持自包含，可单独拷走运行（Q1 决策）。
    """
    body = "\n".join(f"    {a!r}," for a in CHROMIUM_ARGS)
    return "[\n" + body + "\n]"


def _render_conftest() -> str:
    """渲染 conftest 模板（把 __CHROMIUM_ARGS__ 占位符替换为当前参数）。"""
    return _CONFTEST_TEMPLATE.replace("__CHROMIUM_ARGS__", _chromium_args_literal())


# ---------------- 数据抽离 ----------------
def _extract_data(case: dict) -> dict:
    """抽离用例里的字面测试数据 → 数据字典（key 用 语义+序号，避免冲突）。

    - steps[].value（fill/select 等）→ 存成 <op>_<idx>
    - asserts[].expect → 存成 expect_<idx>
    """
    data = {}
    idx = 0
    for st in case.get("steps", []):
        if st.get("value"):
            data[f"{st['op']}_{idx}"] = st["value"]
            idx += 1
    for i, a in enumerate(case.get("asserts", [])):
        # 判据是「有没有 expect 字段」而不是「值是否为真」——0 / "" 都是合法期望值
        # （count 期望 0 行、value 期望空串=被清空），用真值判断会把它们吞掉，断言就静默变形了。
        if "expect" in a:
            data[f"expect_{i}"] = a["expect"]
    return data


def _add_payload_refs(case: dict) -> dict:
    """把 cases 步骤里的字面 value 替换成 _payload_ref 标记，脚本生成时按它取 _data(key, ctx)。"""
    case = json.loads(json.dumps(case, ensure_ascii=False))  # 深拷贝，不改源
    idx = 0
    for st in case.get("steps", []):
        if st.get("value"):
            st["_payload_ref"] = f"{st['op']}_{idx}"
            idx += 1
    for i, a in enumerate(case.get("asserts", [])):
        if "expect" in a:
            a["_payload_ref"] = f"expect_{i}"
    return case


# ---------------- 断言类型契约（2026-09-13 D 项扩展）----------------
# 每种 kind 的「必备字段」——缺字段一律 pytest.fail（假绿红线：少验一步还报绿 = 造假）。
#   text/exists/visible/hidden/count/attr/value/url/checked/unchecked/enabled/disabled
_ASSERT_KINDS = {
    "text", "visible", "hidden", "count", "attr", "value", "url",
    "checked", "unchecked", "enabled", "disabled",
}
# 需要 expect 的 kind（期望值）
_ASSERT_NEED_EXPECT = {"text", "count", "attr", "value", "url"}
# 需要定位（selector 或 element→loc_map）的 kind
_ASSERT_NEED_LOC = {"visible", "hidden", "count", "attr", "value",
                    "checked", "unchecked", "enabled", "disabled"}


def _render_assert(a: dict, loc_map: dict, cross_page: bool = False) -> list[str]:
    """把一条断言（cases 的 asserts[i]）翻译成生成脚本里的调用行。

    定位优先级：selector（手写用例显式给，确定性）> element（语义名 → generate 映射的 locator）。
    缺字段 / 未知 kind / 元素未映射 → pytest.fail（绝不静默少验一步 = 假绿）。
    """
    kind = str(a.get("kind") or "text").strip()
    desc = a.get("desc", "")
    elem = a.get("element")
    sel = a.get("selector")
    payload = f"_data({a['_payload_ref']!r}, ctx)" if a.get("_payload_ref") else None

    if kind not in _ASSERT_KINDS:
        return [f"    pytest.fail({'未知断言类型 ' + kind + '：generator 不支持，拒绝静默跳过'!r},"
                f" pytrace=False)"]
    if kind in _ASSERT_NEED_EXPECT and payload is None:
        return [f"    pytest.fail({'断言 kind=' + kind + ' 缺少 expect（期望值）'!r}, pytrace=False)"]
    if kind == "attr" and not a.get("name"):
        return [f"    pytest.fail({'断言 kind=attr 缺少 name（属性名）'!r}, pytrace=False)"]

    if cross_page and elem and elem in _DUP_RAW_NAMES:
        reason = (f"跨页用例的断言用了跨页重名的原始名 {elem!r} —— 它在多个页面都存在，"
                  f"必须写成 {elem}@<页名> 之一（否则会落到另一页的元素上）。"
                  f"generate 日志里有 ⚠️ 跨页同名元素的唯一化清单")
        return [f"    _log(page, \"cross_page_ambiguous\", '跨页重名原始名: {elem}')",
                f"    pytest.fail({reason!r}, pytrace=False)"]

    prim = None
    if sel:
        prim = f"lambda p: p.locator({sel!r})"
    elif elem:
        if elem in _AMBIGUOUS_NAMES:
            reason = (f"断言语义名歧义：{elem!r} 在多页命中不同 locator → 无法确定用哪一个；"
                      f"请改成唯一名或改用 selector（绝不猜）")
            return [f"    _log(page, \"ambiguous\", '断言语义名歧义: {elem}')",
                    f"    pytest.fail({reason!r}, pytrace=False)"]
        loc = loc_map.get(elem)
        if loc is None:
            reason = (f"断言元素未映射：语义名 {elem!r} 不在探测清单/快照里 → 断言无法定位"
                      f"（generate 日志有 ⚠️ 仍未映射）；请检查 element 拼写，或改用 selector")
            return [f"    _log(page, \"unmapped\", '断言元素未映射: {elem}')",
                    f"    pytest.fail({reason!r}, pytrace=False)"]
        prim = f"lambda p: p.{loc}"
    if kind in _ASSERT_NEED_LOC and prim is None:
        return [f"    pytest.fail({'断言 kind=' + kind + ' 需要 selector 或 element 才能定位'!r},"
                f" pytrace=False)"]

    semantic = repr(elem) if elem else "None"
    d = f"{desc!r}"
    if kind == "text":
        return [f"    _assert_text(page, {payload}, {d})"]
    if kind == "url":
        return [f"    _assert_url(page, {payload}, {d})"]
    if kind == "visible":
        return [f"    _assert_visible(page, {prim}, semantic={semantic}, desc={d})"]
    if kind == "hidden":
        return [f"    _assert_hidden(page, {prim}, semantic={semantic}, desc={d})"]
    if kind == "count":
        return [f"    _assert_count(page, {payload}, {prim}, semantic={semantic}, desc={d})"]
    if kind == "attr":
        return [f"    _assert_attr(page, {a['name']!r}, {payload}, {prim},"
                f" semantic={semantic}, desc={d})"]
    if kind == "value":
        return [f"    _assert_value(page, {payload}, {prim}, semantic={semantic}, desc={d})"]
    # checked / unchecked / enabled / disabled
    return [f"    _assert_{kind}(page, {prim}, semantic={semantic}, desc={d})"]


# ---------------- 生成一个用例的 pytest 函数 ----------------
def _semantic_to_locator_expr(it: dict) -> str:
    """probe 元素字典 → Playwright 定位表达式（确定性，Tier1 顺序）。"""
    if it.get("test_id"):
        return f'get_by_test_id("{it["test_id"]}")'
    if it.get("role") and it.get("name"):
        return f'get_by_role("{it["role"]}", name="{it["name"]}")'
    if it.get("placeholder"):
        return f'get_by_placeholder("{it["placeholder"]}")'
    if it.get("text"):
        return f'get_by_text("{it["text"]}", exact=True)'
    # 上下文锚点
    if it.get("nearby_text") and it.get("role"):
        return f'locator("li").filter(has_text="{it["nearby_text"]}").get_by_role("{it["role"]}")'
    raise RuntimeError(f"元素 {it.get('semantic_name')} 无可用定位语义")


def _render_pytest_case(case: dict, loc_map: dict) -> str:
    """把单个 cases 用例渲染成一个 pytest test 函数（locator 内联确定性定位）。

    断言位置（P3）：`asserts[i].after_step = N`（1 起）→ 渲染在第 N 步之后**原地执行**；
    不带 after_step 的照旧全部放在用例末尾（向后兼容）。
    为什么需要：跨页流程的「换页证据」（url 断言）必须在换页当下验，堆到末尾就只能验最后一页。

    跨页用例（带 pages）：用到跨页重名的**原始名**时显式失败 —— 必须写成 `原名@页名`，
    否则会静默落到另一页的 locator（就是 P3 要根治的坑）。
    """
    cid = case["case_id"]
    name = (case.get("name") or cid).replace('"', '\\"')
    steps = case.get("steps", [])
    asserts = case.get("asserts", [])
    is_cross_page = len(case.get("pages") or []) > 1

    by_step: dict[int, list[dict]] = {}
    tail: list[dict] = []
    for a in asserts:
        pos = a.get("after_step")
        if isinstance(pos, int) and pos >= 1:
            by_step.setdefault(pos, []).append(a)
        else:
            tail.append(a)

    lines = [
        f'def test_{cid}(page, ctx):',
        f'    """{name}"""',
        f'    _CURRENT_LOG["case_id"] = "{cid}"',
        f'    _goto(page, {case.get("base_url", "http://localhost:8000")!r})',
        f'    _log(page, "场景开始", f"case={cid}")',
        '',
    ]

    for i, st in enumerate(steps):
        op = st.get("op")
        desc = st.get("desc", "")
        lines.append(f'    # step {i+1}: {desc}')
        if op == "goto":
            lines.append(f"    _goto(page, {st.get('url', case.get('base_url'))!r})")
        else:
            elem = st.get("element", "")
            if is_cross_page and elem and elem in _DUP_RAW_NAMES:
                reason = (f"跨页用例的步骤用了跨页重名的原始名 {elem!r} —— 它在多个页面都存在，"
                          f"必须写成 {elem}@<页名> 之一（否则会静默落到另一页的 locator）")
                lines.append(f"    _log(page, \"cross_page_ambiguous\", '跨页重名原始名: {elem}')")
                lines.append(f"    pytest.fail({reason!r}, pytrace=False)")
                continue
            loc = loc_map.get(elem) if elem not in _AMBIGUOUS_NAMES else None
            if elem in _AMBIGUOUS_NAMES:
                reason = (f"语义名歧义：{elem!r} 在多页命中不同 locator → 无法确定该用哪一个"
                          f"（generate 日志有 ⚠️ 多页命中）→ 请改成唯一名，或改用 selector 精确定位；"
                          f"绝不猜一个可能点错的 locator")
                lines.append(f"    _log(page, \"ambiguous\", '语义名歧义: {elem}')")
                lines.append(f"    pytest.fail({reason!r}, pytrace=False)")
                continue
            if loc is None:
                # 不静默跳过：只留注释的话，这一步被丢掉、用例照样 PASSED = 假绿
                # （2026-09-11 实测：手搓用例把控件名写错 ⇒ 生成的测试仍"通过"）。
                reason = (f"元素未映射：语义名 {elem!r} 不在探测清单/快照里 → 该步无法定位"
                          f"（generate 日志有 ⚠️ 仍未映射）；请检查用例里的 element 拼写，"
                          f"或先跑 probe 刷新快照")
                lines.append(f"    _log(page, \"unmapped\", '元素未映射: {elem}')")
                lines.append(f"    pytest.fail({reason!r}, pytrace=False)")
                continue
            primary = f"lambda p: p.{loc}"
            semantic = repr(elem) if elem else "None"
            if op in ("fill", "select"):
                ref = st["_payload_ref"]
                lines.append(f'    _act(page, "{op}", semantic={semantic}, '
                             f'primary={primary}, value=_data({ref!r}, ctx))')
            elif op in ("click", "check", "press_enter"):
                lines.append(f'    _act(page, "{op}", semantic={semantic}, primary={primary})')
            else:
                # 同上：未知动作也要显式失败，绝不静默少做一步
                lines.append(f"    pytest.fail({'未知操作类型 ' + str(op) + '：generator 不支持，拒绝静默跳过'!r},"
                             f" pytrace=False)")
        lines.append(f'    _log(page, "{op}", f"{desc}")')
        # 该步之后的原地断言（after_step = i+1）
        for a in by_step.get(i + 1, []):
            lines.extend(_render_assert(a, loc_map, cross_page=is_cross_page))
        lines.append("")

    if tail:
        lines.append("    # ---- 断言（用例末尾）----")
        for a in tail:
            lines.extend(_render_assert(a, loc_map, cross_page=is_cross_page))
        lines.append("")
    return "\n".join(lines)


# ---------------- 生成 scripts/ 整套 ----------------
def _load_loc_map_from_probe_snapshot(path: Path) -> dict:
    """从 probe_*.json（probe 产出的控件快照）建 semantic_name → locator 表达式。"""
    out: dict[str, str] = {}
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return out
    for it in (items if isinstance(items, list) else []):
        name = it.get("semantic_name")
        if not name or name in out:
            continue
        try:
            out[name] = _semantic_to_locator_expr(it)
        except Exception:
            continue
    return out


def _load_loc_map_from_element_map(path: Path) -> dict:
    """从 element_map_*.json（explore 产物）建 semantic_name → locator 表达式。"""
    out: dict[str, str] = {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return out
    for st in data.get("steps", []):
        el = st.get("element") or {}
        name = el.get("semantic_name")
        if not name or name in out:
            continue
        try:
            out[name] = _semantic_to_locator_expr(el)
        except Exception:
            continue
    return out


_AMBIGUOUS_NAMES: set[str] = set()      # 本次 generate 里「同名但落点不同」的语义名（用到即显式失败）
_DUP_RAW_NAMES: set[str] = set()        # 跨页重复过的**原始名**（跨页用例必须写成 原名@页名）


def _collect_declared_pages(cases: list[dict]) -> list[tuple[str, str]]:
    """收集用例声明的页面 [(页名, url)]（去重、保序）—— 只有跨页用例（带 pages 字段）才算。

    P3：generate 的「现场 probe 补齐」要知道**该探哪些页**，否则跨页元素永远补不上。
    """
    out: list[tuple[str, str]] = []
    seen = set()
    for c in cases:
        for pg in (c.get("pages") or []):
            key = (str(pg.get("name") or ""), str(pg.get("url") or ""))
            if key[1] and key not in seen:
                seen.add(key)
                out.append(key)
    return out


def _probe_declared_pages(pages: list[tuple[str, str]]) -> tuple[dict, set[str], set[str]]:
    """按用例声明的页面逐页现场探测（P3 跨页补齐），返回 (loc_map, ambiguous_names)。

    · 一个浏览器 + 一个 context 顺序 goto（本机 1.87G 无 swap，绝不为多页多开/并发）；
    · 每页做基础探测 + 弹窗补充（与单页老路径同一套逻辑）；
    · 合并时走**与 explore 同一套** `uniquify_across_pages`：同名跨页 → `原名@页名`。
      这样手写用例与 AI 用例的命名规则一致（不会两边各叫一套名）。
    · ambiguous 是**防御性**判据：正常路径下唯一化已保证名字不撞；万一同一名字落到不同 locator
      （说明探测/命名逻辑被改坏了）就记下来，生成时**显式失败**而不是静默挑一个。
    """
    from playwright.sync_api import sync_playwright
    from .probe import probe_page, uniquify_across_pages
    from .browser import launch_opts

    if len(pages) > 3:
        print(f"[generate] ⚠️ 现场探测 {len(pages)} 个页面（>3）——耗时与内存都会涨，"
              f"建议只为确实需要的页面写用例")
    per_page: list[tuple[str, list[dict]]] = []
    with sync_playwright() as p:
        b = p.chromium.launch(**launch_opts(headless=True))
        ctx = b.new_context()
        pg = ctx.new_page()
        for pname, url in pages:
            pg.goto(url)
            pg.wait_for_load_state("networkidle")
            items = probe_page(pg, page_name=pname or None)
            # 2026-09-14：改用与 explore **同一套**弹窗/弹层探测（含嵌套 picker 层，探完会关掉）。
            # 以前这里自己点一遍「新建」按钮、只探一层、而且**不关弹窗**：
            #   ① 「客户弹层里选一行」这类控件在 generate 的现场补齐里永远看不到
            #      ⇒ 手写用例报「元素未映射」（实测 2026-09-14 踩到）；
            #   ② 弹窗不关，下一页的探测是在"弹窗盖着"的状态下做的，结果不可信。
            from .explorer import _try_collect_modal_items
            layer = _try_collect_modal_items(pg, items)
            for it in layer:
                it["page"] = pname or ""
            merged = {i["semantic_name"]: i for i in items}
            for i in layer:
                merged.setdefault(i["semantic_name"], i)
            print(f"[generate] 现场探测 [{pname or '页面1'}] {url} → {len(merged)} 个控件"
                  f"（含弹窗/弹层 {len(layer)} 个）")
            per_page.append((pname or "页面1", list(merged.values())))
        b.close()

    merged_items, collisions = uniquify_across_pages(per_page)
    dup_raw = {c["semantic_name"] for c in collisions}   # 原始名：跨页用例必须用 @页名 形式
    for c in collisions:
        print(f"[generate] ⚠️ 跨页同名元素 {c['semantic_name']!r} 出现在 {'、'.join(c['pages'])}"
              f" → 已唯一化为 "
              + "、".join(f"{c['semantic_name']}@{p}" for p in c["pages"]))
    loc_map: dict[str, str] = {}
    ambiguous: set[str] = set()
    for it in merged_items:
        name = it["semantic_name"]
        try:
            expr = _semantic_to_locator_expr(it)
        except Exception:
            continue
        if name in loc_map and loc_map[name] != expr:
            ambiguous.add(name)
            print(f"[generate] ⚠️ 语义名 {name!r} 命中两个不同 locator"
                  f"（{loc_map[name]} vs {expr}）→ 用到它时显式失败（请改成唯一名或改用 selector）")
            continue
        loc_map[name] = expr
    return loc_map, ambiguous, dup_raw


class UnmappedElementsError(RuntimeError):
    """映射质量闸（V7.5.1，2026-09-15 交付事故根因）：有语义名映射不上时**拒绝落盘**。

    事故复盘：现场 probe 不可用（目标没起 / OOM / 探测失败）时，旧代码只打一句警告就继续写文件，
    产出一份「16 个用例、每个步骤都是 pytest.fail(元素未映射)」的垃圾产物，而且 **exit 0** ——
    它被提交、被打包、被交付，直到闸门跑起来才炸成 50 条失败，真因已无处可查。
    口径（与「0 个用例 ⇒ exit 2」同源）：**拿不到定位就不要产出产物**，先失败、先说话。
    """

    def __init__(self, missing, sources: str = "", probe_error: str | None = None):
        self.missing = sorted(str(m) for m in missing)
        self.sources = sources
        self.probe_error = probe_error
        super().__init__(f"{len(self.missing)} 个语义名未映射：{self.missing[:5]}…")


def generate_scripts(cases_dir: Path | None = None, scripts_dir: Path | None = None,
                     element_map_path: Path | None = None, live_probe: bool = False,
                     allow_unmapped: bool = False) -> dict:
    """读 cases/*.json → 生成 scripts/test_cases.py + scripts/conftest.py + scripts/datasets/<case_id>.json。

    定位来源（Req2：**消费 probe 生成的 element.map**，而不是每次自己现场重探）：
      1) `--element-map <file>` 指定的 element_map_*.json（explore 产物）
      2) 否则用【最新 element_map_*.json】；再否则用【最新 probe_*.json】（probe 快照）
      3) 快照命中不全 → 现场 probe **只补缺失项**；`--live-probe` 则强制全量现场 probe
    来源与命中数会打印出来（可追溯，不静默）。

    ⚠️ **映射质量闸（V7.5.1）**：算完映射后仍有语义名对不上 ⇒ 抛 `UnmappedElementsError` 且**不写任何产物**；
    只有显式 `allow_unmapped=True`（CLI 的 `--allow-unmapped`，调试用）才放行，产物里会留 pytest.fail 存根。
    返回 dict：{scripts_dir, tests, datasets, count, locator_sources, unmapped, probe_error}
    """
    from playwright.sync_api import sync_playwright
    from .probe import probe_page
    from .config import TARGET_URL, ELEMENT_MAP_DIR
    from .browser import launch_opts

    cases_dir = cases_dir or CASES_DIR
    scripts_dir = scripts_dir or SCRIPTS_DIR
    _AMBIGUOUS_NAMES.clear()      # 每次 generate 从零开始（避免上一次运行的歧义名单残留）
    _DUP_RAW_NAMES.clear()
    datasets_dir = scripts_dir / "datasets"
    datasets_dir.mkdir(parents=True, exist_ok=True)
    scripts_dir.mkdir(parents=True, exist_ok=True)

    case_files = sorted(cases_dir.glob("*.json"))
    cases = [json.loads(f.read_text(encoding="utf-8")) for f in case_files]
    # 假绿红线闸：在读用例之后、算映射之前拦（有问题就一个产物都不写）
    _gate_false_green(cases)
    # 需要映射的语义名：**步骤元素 + 断言元素都要**（断言也能用 element 定位，
    # 只收步骤元素会让「断言引用的元素」被误判成未映射 → 2026-09-13 修）
    needed = {st.get("element") for c in cases for st in c.get("steps", []) if st.get("element")}
    needed |= {a.get("element") for c in cases for a in c.get("asserts", []) if a.get("element")}
    needed.discard(None)
    needed.discard("")

    # 0) 解析 locator 映射：优先 element.map 快照，缺口才现场补探测
    loc_map: dict[str, str] = {}
    src_parts: list[str] = []

    if not live_probe:
        candidates: list[tuple[str, Path, str]] = []
        if element_map_path:
            candidates.append(("element_map(--element-map)", Path(element_map_path), "element"))
        else:
            emaps = sorted(ELEMENT_MAP_DIR.glob("element_map_*.json"))
            if emaps:
                candidates.append((f"element_map({emaps[-1].name})", emaps[-1], "element"))
            snaps = sorted(ELEMENT_MAP_DIR.glob("probe_*.json"))
            if snaps:
                candidates.append((f"probe快照({snaps[-1].name})", snaps[-1], "probe"))
        for label, f, kind in candidates:
            if not f.exists():
                continue
            got = (_load_loc_map_from_element_map(f) if kind == "element"
                   else _load_loc_map_from_probe_snapshot(f))
            hit = {k: v for k, v in got.items() if k in needed}
            if hit:
                loc_map.update(hit)
                src_parts.append(f"{label} 命中 {len(hit)}/{len(needed)}")
                break

    missing = needed - set(loc_map)
    declared_pages = _collect_declared_pages(cases)
    probe_error: str | None = None
    if live_probe or missing:
        try:
            live: dict[str, str] = {}
            # ① 单页惯例探测（TARGET_URL + 弹窗补充）—— **始终执行**，保证老用例的原始名不受跨页影响
            with sync_playwright() as p:
                b = p.chromium.launch(**launch_opts(headless=True))
                pg = b.new_page()
                pg.goto(TARGET_URL)
                pg.wait_for_load_state("networkidle")
                for it in probe_page(pg):
                    live[it["semantic_name"]] = _semantic_to_locator_expr(it)
                # 点开弹窗，补充弹窗内表单控件
                for it in probe_page(pg):
                    if it.get("role") == "button" and any(h in (it.get("name") or "") for h in ("新建", "添加", "新增")):
                        try:
                            pg.get_by_role("button", name=it["name"]).first.click()
                            pg.wait_for_timeout(400)
                            for it2 in probe_page(pg):
                                live.setdefault(it2["semantic_name"], _semantic_to_locator_expr(it2))
                        except Exception:
                            pass
                        break
                b.close()
            # ② 跨页用例：额外按声明的页面逐页探测（补 `原名@页名` 形式的跨页元素）
            if declared_pages:
                page_live, amb, dup_raw = _probe_declared_pages(declared_pages)
                for k, v in page_live.items():
                    live.setdefault(k, v)
                _AMBIGUOUS_NAMES.clear()
                _AMBIGUOUS_NAMES.update(amb)
                _DUP_RAW_NAMES.clear()
                _DUP_RAW_NAMES.update(dup_raw)
            if live_probe:
                loc_map.update(live)
                src_parts.append(f"现场probe(强制全量, {len(live)} 项)"
                                 + (f"，跨页 {len(declared_pages)} 页" if declared_pages else ""))
            else:
                filled = {k: v for k, v in live.items() if k in missing}
                loc_map.update(filled)
                src_parts.append(f"现场probe补齐 {len(filled)}/{len(missing)} 项"
                                 + (f"，跨页 {len(declared_pages)} 页" if declared_pages else ""))
        except Exception as e:
            probe_error = f"{type(e).__name__}: {e}"
            src_parts.append(f"现场probe失败({type(e).__name__})")
            print(f"[generate] probe 映射警告: {e}")

    locator_sources = " + ".join(src_parts) or "(无)"
    still_missing = needed - set(loc_map)
    if still_missing:
        locator_sources += f"；⚠️ 仍未映射 {len(still_missing)} 项: {sorted(still_missing)}"

    # ---- 映射质量闸（V7.5.1）：拿不到定位 ⇒ **不写产物**，先失败、先说话 ----
    # 为什么必须在这里拦（而不是靠运行时的 pytest.fail 存根兜底）：存根只是「万一」的保险，
    # 而「探测拿不到」是**生成期的已知错误**。让它继续落盘 = 产出一份看着合法的垃圾产物，
    # 且 generate 自己 exit 0 ⇒ 会被提交/打包/交付（2026-09-15 V7.5 交付事故就是这个）。
    if still_missing and not allow_unmapped:
        raise UnmappedElementsError(still_missing, locator_sources, probe_error=probe_error)

    # 1) 抽离数据 → scripts/datasets/<case_id>.json
    for case in cases:
        data = _extract_data(case)
        (datasets_dir / f"{case['case_id']}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # 2) 生成 pytest 用例函数（locator 内联）
    rewritten = [_add_payload_refs(c) for c in cases]
    funcs = "\n\n".join(_render_pytest_case(c, loc_map) for c in rewritten)

    (scripts_dir / "test_cases.py").write_text(_TEST_FILE_HEADER + funcs + "\n", encoding="utf-8")
    (scripts_dir / "conftest.py").write_text(_render_conftest(), encoding="utf-8")

    return {
        "scripts_dir": str(scripts_dir),
        "tests": [str(scripts_dir / "test_cases.py")],
        "datasets": [str(datasets_dir / f"{c['case_id']}.json") for c in cases],
        "count": len(cases),
        "locator_sources": locator_sources,
        "unmapped": sorted(still_missing),
        "probe_error": probe_error,
    }


_TEST_FILE_HEADER = '''"""hybrid_gui_qa 数据驱动测试用例 —— 由 cases/*.json 自动生成。
数据抽离到 scripts/datasets/<case_id>.json；脚本与数据分离。
运行（推荐走 cli：自带资源预检 + run-id 隔离的日志/报告）:
  cd hybrid_gui_qa
  python -m framework.cli run --workers 2             # 资源预检：内存不足自动降并发
  python -m framework.cli run --debug                 # 调试开关：有屏幕弹浏览器；没屏幕录视频+逐步截图
  python -m framework.cli run --debug --case <case_id>          # 只调试一条用例
  python -m framework.cli run --debug --slowmo 500 --case <case_id>  # 放慢 500ms/动作，肉眼跟步

裸跑 pytest（未设 HYBRID_RUN_ID 时日志落 log/latest/，会话开始清空）:
  pytest scripts/test_cases.py -v
  pytest scripts/test_cases.py -n 1 --html=log/latest/report.html
"""
from conftest import (_CURRENT_LOG, _log, _data, _act, _goto,
                      _assert_text, _assert_url,
                      _assert_visible, _assert_hidden, _assert_count,
                      _assert_attr, _assert_value,
                      _assert_checked, _assert_unchecked,
                      _assert_enabled, _assert_disabled)
import pytest
from playwright.sync_api import expect as _pw_expect

'''


# conftest 模板：浏览器工厂 + 数据注入 + 变量池 + 动态占位符 + 日志
_CONFTEST_TEMPLATE = '''"""scripts 配套 fixture —— 浏览器工厂 / 数据注入 / 变量池 / 动态占位符 / 日志。

数据流：scripts/datasets/<case_id>.json（generate 从 cases/ 抽离）→ _data(key, ctx) 注入。
浏览器生命周期（E 项提速后）：**整个会话共用一个 Chromium**（_pool，session scope），
每条用例只新建 context + page（function scope）——隔离性不变（cookie/存储/trace/录像按 context 走），
但省掉「每条用例重启浏览器」的 ≈0.6s/条（实测 9 用例 setup 由 5.4s → 若干毫秒）。
case.vars 变量池（运行过程数据）+ 动态占位符 {datetime} 解析（一次解析固化，填表名==断言名，重跑不重名）。
"""
# ---- 统一 UTF-8（生成物自带，裸跑 pytest 也不炸；与 framework/text_io.py 同口径）----
# 为什么：Windows 控制台是 cp936 时，本文件里的 ✓/⚠️ 会 UnicodeEncodeError（跑到一半崩）；
# 而 pytest 的 fd 捕获把输出写回真实 fd 时**硬编码 UTF-8**（_pytest/capture.py），
# 只要外层按 locale 解码就 UnicodeDecodeError。这里把本进程 stdio 拉齐到 UTF-8，
# 并把 Windows 控制台代码页设成 65001（否则我们写出的 UTF-8 中文在控制台显示成乱码）。
import os as _os
import sys as _sys
_os.environ.setdefault("PYTHONUTF8", "1")
_os.environ.setdefault("PYTHONIOENCODING", "utf-8")
for _s in (_sys.stdout, _sys.stderr):
    try:
        if _s is None or not hasattr(_s, "reconfigure"):
            continue
        _s.fileno()                      # pytest 捕获替身没有 fileno → 跳过，别去动它
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if _sys.platform == "win32":
    try:
        import ctypes as _ctypes
        _ctypes.windll.kernel32.SetConsoleOutputCP(65001)
    except Exception:
        pass

from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright
from playwright.sync_api import expect as _expect

BASE = Path(__file__).resolve().parent.parent
LOG_DIR = BASE / "log"

# ---- 本次运行的日志目录（run-id 隔离）----
# cli run 会设 HYBRID_RUN_ID=YYYYmmdd_HHMMSS，日志/报告落 log/<run_id>/；
# 裸跑 pytest（未设）则落 log/latest/，并在会话开始时清空 ⇒ 每次运行都干净。
import os
RUN_ID = os.environ.get("HYBRID_RUN_ID", "latest")
RUN_LOG_DIR = LOG_DIR / RUN_ID

# ---- Chromium 启动参数（内联自 framework/browser.py:CHROMIUM_ARGS；生成物自包含）----
CHROMIUM_ARGS = __CHROMIUM_ARGS__


def _launch_opts(headless):
    """headless=True 无头(默认)；False 有头(显示浏览器)。
    支持 HYBRID_SLOWMO=<毫秒> 放慢每个动作，方便肉眼看用例一步步走。"""
    args = list(CHROMIUM_ARGS)
    heap = os.environ.get("HYBRID_JS_HEAP_MB")
    if heap and heap.isdigit():
        args.append(f"--js-flags=--max-old-space-size={int(heap)}")
    opts = {"headless": headless, "args": args}
    slow = os.environ.get("HYBRID_SLOWMO")
    if slow and slow.isdigit() and int(slow) > 0:
        opts["slow_mo"] = int(slow)
    return opts


import sys
sys.path.insert(0, str(BASE))
from framework.data_driven import resolve_dynamic_inputs, format_template  # noqa
from framework.healer import Healer  # noqa: E402

# ---- 自愈开关（Q1 决策：默认开，可用 HYBRID_SELF_HEAL=0 关）----
# 0 → 确定性 locator 失效即报错，不做语义兜底/自愈（CI 里常要"失败即报"）
_SELF_HEAL = os.environ.get("HYBRID_SELF_HEAL", "1") != "0"
_HEALER = Healer()   # 进程内单例：累积 heal 事件，会话结束统一落盘（可审 diff）

# 用例上下文：数据 + 变量池 + 动态占位符固化
class CaseCtx:
    __slots__ = ("case_id", "data", "vars")
    def __init__(self, case_id, data):
        self.case_id = case_id
        self.data = data
        self.vars = {}          # 用例级变量池：存运行过程数据(编号/抓取值)，function-scope 隔离
        resolve_dynamic_inputs(self.data)   # 动态占位符 {datetime}→实际值(固化)


def _data(key, ctx):
    """从用例数据字典取 key 的值；若含 {占位符} 则动态解析（保留 {datetime} 能力）。"""
    v = ctx.data.get(key, key)
    if isinstance(v, str) and "{" in v:
        return format_template(v, ctx.data)
    return v


def _load_data(case_id):
    import json
    p = Path(__file__).resolve().parent / "datasets" / f"{case_id}.json"
    return json.loads(p.read_text(encoding="utf-8"))


@pytest.fixture(scope="session", autouse=True)
def _prepare_run_log_dir():
    """保证"本次运行"的日志目录干净。

    - 有 HYBRID_RUN_ID（cli run 传入）→ 该目录是全新 run-id，天然干净，不清。
    - 无 HYBRID_RUN_ID（裸跑 pytest）→ 落 log/latest/，会话开始先清空。
    注意 xdist：worker 进程不清理（避免并发删除互相打架），只由主进程清。
    """
    if not os.environ.get("HYBRID_RUN_ID") and "PYTEST_XDIST_WORKER" not in os.environ:
        import shutil
        shutil.rmtree(RUN_LOG_DIR, ignore_errors=True)
    RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
    yield RUN_LOG_DIR


# ---- 用例级看门狗（2026-09-14）----
# 为什么要：Playwright 驱动**内部崩溃**时（实测 coreBundle.js:463 Assertion error，机器内存吃紧时触发），
# 它的同步 API 会一直等一个永远不来的响应 —— Python 侧 100% CPU 空转、**永不退出**
# （2026-09-14 实测卡了 11 分钟，只能手工 kill）。挂死比失败更糟：CI 一直挂着、也没人知道卡在哪。
# 用 stdlib 的 faulthandler：超时就打印**所有线程的调用栈**（直接看出卡在哪一行）并退出，绝不静默。
# 口径：HYBRID_CASE_TIMEOUT 秒（默认 120）；设为 0/off 关掉。
_CASE_TIMEOUT = os.environ.get("HYBRID_CASE_TIMEOUT", "120")
_WATCHDOG_SINK = None


def _watchdog_sink():
    """看门狗转储目标：run 日志目录里的 watchdog.txt（无缓冲，一定落盘）。

    为什么不用 stderr：pytest 的 fd 捕获会把 **fd 2 也换成临时文件** ⇒ 硬退出时那段调用栈
    随临时文件一起被丢弃（实测：日志里一个字节都没有，看门狗等于没留证据）。
    自己开一个专用文件（fd 3+，不受捕获影响）+ buffering=0 ⇒ 转储一定写进去；
    这也比 stderr 更好找：`log/<run_id>/watchdog.txt`。
    """
    global _WATCHDOG_SINK
    if _WATCHDOG_SINK is None:
        try:
            RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
            _WATCHDOG_SINK = open(RUN_LOG_DIR / "watchdog.txt", "ab", buffering=0)
        except Exception:
            _WATCHDOG_SINK = _sys.__stderr__
    return _WATCHDOG_SINK


@pytest.fixture(autouse=True)
def _case_watchdog():
    """每条用例一个硬超时：超时把**所有线程的调用栈**写进 log/<run>/watchdog.txt 并退出。

    防的是「Playwright 驱动崩溃 → 同步 API 空转不返回」那种永久挂死（比失败更糟）。
    口径：HYBRID_CASE_TIMEOUT 秒（默认 120）；设 0/off 关掉。
    """
    import faulthandler
    secs = (_CASE_TIMEOUT or "").strip().lower()
    if secs in ("", "0", "off", "none", "false"):
        yield None
        return
    try:
        faulthandler.dump_traceback_later(int(float(secs)), exit=True, file=_watchdog_sink())
    except Exception as e:
        print(f"[setup] ⚠️ 用例看门狗没装上（HYBRID_CASE_TIMEOUT={_CASE_TIMEOUT!r}）：{e}", flush=True)
        yield None
        return
    try:
        yield None
    finally:
        faulthandler.cancel_dump_traceback_later()


# ---- 分区（F6）+ 就绪契约（F1）+ 定位等待（F2）—— 2026-09-14 ----
# 为什么会需要（团队演示实测，详见 docs/P4-慢目标与并发-修复方案.md）：
#   ① 被测页面是异步取数（fetch 之后才 render），goto 之后立刻动作/断言，在慢机器/高并发下必假红；
#   ② 多 worker 打同一个「有状态」被测服务，精确计数断言互相踩。
# 约定：worker 分区号 = PYTEST_XDIST_WORKER（没有 xdist 时为空串 ⇒ 单跑行为与以前完全一致）；
#       页面从 window.__HYBRID_W 读自己的分区，并把它带进所有 /api 调用。
_WORKER = os.environ.get("PYTEST_XDIST_WORKER", "")
_PARTITION = os.environ.get("HYBRID_PARTITION", _WORKER)
_HYBRID_BASE = (os.environ.get("HYBRID_BASE_URL") or "").strip().rstrip("/")
_WAIT_READY = os.environ.get("HYBRID_WAIT_READY", "1") != "0"
_READY_TIMEOUT_MS = int(os.environ.get("HYBRID_READY_TIMEOUT", "15000"))
_READY_SELECTOR = os.environ.get("HYBRID_READY_SELECTOR", "")
_READY_REQUIRED = os.environ.get("HYBRID_READY_REQUIRED", "0") == "1"
_LOCATE_TIMEOUT_MS = int(os.environ.get("HYBRID_LOCATE_TIMEOUT", "5000"))
_READY_WARNED = set()


def _with_partition(url):
    """把分区号带进 URL（?w=gw0）—— 框架自己发的请求（复位等）要用。"""
    if not _PARTITION:
        return url
    import urllib.parse as _up
    return url + ("&" if "?" in url else "?") + "w=" + _up.quote(_PARTITION)


def _count_attached(cand, timeout_ms=None):
    """有界等待之后再数元素（F2）。

    为什么不用瞬时 count()：慢机器/高并发下元素「晚到」是常态，瞬时判定会把
    「还没渲染出来」误判成「不存在」（实测：慢目标下弹层行未渲染即判失败并抛误导性错误）。
    等到 attached 再数，判定语义不变（仍要求 count==1 才接受）。
    """
    ms = _LOCATE_TIMEOUT_MS if timeout_ms is None else timeout_ms
    try:
        cand.first.wait_for(state="attached", timeout=ms)
    except Exception:
        pass
    return cand.count()


def _goto(page, url):
    """统一导航入口：① 支持 HYBRID_BASE_URL 覆盖目标（同一套用例跑本机/慢代理/预发）
    ② goto 之后等页面数据就绪（F1）。生成脚本里的每个 goto 都走这里。"""
    target = url
    if _HYBRID_BASE:
        import urllib.parse as _up
        u, o = _up.urlsplit(url), _up.urlsplit(_HYBRID_BASE)
        target = _up.urlunsplit((o.scheme, o.netloc, u.path, u.query, u.fragment))
    page.goto(target)
    _wait_ready(page, target)


def _wait_ready(page, url=""):
    """等页面数据就绪（F1 契约）。

    ① 页面声明契约：<body data-hybrid-ready="0"> …… 渲染完成后置 "1"（本项目 demo 两页已实现）；
    ② 老页面没契约：用 HYBRID_READY_SELECTOR 指定一个「数据已就绪」选择器；
    ③ 两者都没有：只提醒一次、不阻塞（后续动作/断言自带 F2 的有界等待）。
    超时默认只告警；HYBRID_READY_REQUIRED=1 时才硬失败（CI 想要「页面必须就绪」语义时用）。
    """
    if not _WAIT_READY:
        return
    if _READY_SELECTOR:
        try:
            page.wait_for_selector(_READY_SELECTOR, timeout=_READY_TIMEOUT_MS, state="attached")
        except Exception:
            _ready_timeout(url)
        return
    try:
        has_contract = page.locator("body[data-hybrid-ready]").count() > 0
    except Exception:
        return
    if not has_contract:
        if "no_contract" not in _READY_WARNED:
            _READY_WARNED.add("no_contract")
            print("[ready] ⚠️ 被测页面没有就绪契约（body[data-hybrid-ready]）——建议页面补上；"
                  "或设置 HYBRID_READY_SELECTOR=<数据已就绪选择器>；本次不阻塞（动作/断言仍自带等待）。", flush=True)
        return
    try:
        page.wait_for_selector("body[data-hybrid-ready='1']", timeout=_READY_TIMEOUT_MS, state="attached")
    except Exception:
        _ready_timeout(url)


def _ready_timeout(url=""):
    msg = (f"[ready] ⚠️ 等待页面数据就绪超时（{_READY_TIMEOUT_MS}ms）：{url}"
           f" —— 页面可能卡在取数或报错；用 --debug 看逐步截图（log/<run_id>/shots/）与浏览器 console。")
    if _READY_REQUIRED:
        raise RuntimeError(msg)
    print(msg, flush=True)


# ---- 用例间数据复位（2026-09-14）----
# 为什么需要：被测应用（demo）现在把合同数据放在**服务端**（详情页要读同一条真实记录），
# 新建用例会真的写进去 ⇒ 不复位的话「列表恢复 20 行」这类断言会被上一条用例的残留数据打乱，
# 而且失败原因会指向错误的地方（用例互相污染比用例失败更难查）。
# 口径：HYBRID_RESET_URL 可覆盖默认值；设为 off/0/none/空 则完全不复位（被测应用没有复位接口时）。
# 复位失败**大声告警但不中断**：那是「用例可能互相污染」的信号，绝不该被静默吞掉。
_RESET_URL = os.environ.get("HYBRID_RESET_URL", "http://localhost:8000/api/reset")
_RESET_OFF = ("", "off", "0", "none", "no", "false")


@pytest.fixture(autouse=True)
def _reset_target_data():
    """每条用例开始前把被测应用的数据复位（默认 POST http://localhost:8000/api/reset）。"""
    url = (_RESET_URL or "").strip()
    if url.lower() in _RESET_OFF:
        yield None
        return
    import urllib.request
    target = _with_partition(url)
    try:
        req = urllib.request.Request(target, data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            print(f"[setup] 数据复位 {target} → HTTP {r.status}"
                  + (f"（分区 {_PARTITION}）" if _PARTITION else ""), flush=True)
    except Exception as e:
        print(f"[setup] ⚠️ 数据复位失败（{target}）：{type(e).__name__}: {e}"
              f" —— 用例之间可能互相污染（要关掉这条提示：HYBRID_RESET_URL=off）", flush=True)
    yield None


@pytest.fixture(scope="session", autouse=True)
def _dump_heals_at_session_end():
    """会话结束把自愈记录落盘（可审 diff）；带 worker 后缀，避免并发同秒同名相撞。"""
    yield
    if _HEALER.events:
        worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
        paths = _HEALER.dump(suffix=f"_{worker}")
        print(f"[heal] 本次运行自愈 {len(_HEALER.events)} 条 -> {paths}")


class _BrowserPool:
    """**会话级**浏览器持有者（2026-09-13 E 项提速）。

    改造前：每条用例各起一次 Chromium（实测 setup ≈0.6s/条 ×9 条 ≈5.4s，占总时长一半）。
    现在：整场（一个 worker 进程）共用一个浏览器，每条用例只新建 context + page（隔离不变：
    每个 context 有自己的 cookie/存储/trace/录像）。
    崩溃兜底：若浏览器被内核 OOM 杀掉或自身崩了 → **大声告警 + 重启**（绝不静默拿坏句柄继续跑，
    那会让后面所有用例连锁失败且原因不明）。
    """

    def __init__(self, opts):
        self._opts = opts
        self._p = None
        self.browser = None
        self.restarts = 0

    def get(self):
        from playwright.sync_api import sync_playwright
        if self._p is None:
            self._p = sync_playwright().start()
        if self.browser is None or not self.browser.is_connected():
            if self.browser is not None:
                self.restarts += 1
                print(f"[browser] ⚠️ 会话级浏览器已断开（第 {self.restarts} 次）→ 重启。"
                      f"若 dmesg 有 OOM 记录，说明内存不够（见 framework/limits.py 的并发降级）",
                      flush=True)
            self.browser = self._p.chromium.launch(**self._opts)
        return self.browser

    def close(self):
        for fn in (lambda: self.browser and self.browser.close(),
                   lambda: self._p and self._p.stop()):
            try:
                fn()
            except Exception:
                pass


def _is_headed():
    """调试·有头判定：HYBRID_HEADED=1 且不在 xdist worker 里（worker 一律无头，见 cli.py 注释）。"""
    import os as _os
    return _os.environ.get("HYBRID_HEADED", "") == "1" and "PYTEST_XDIST_WORKER" not in _os.environ


@pytest.fixture(scope="session")
def _pool():
    """会话级浏览器池（每场一个 Chromium；kill 掉也不用管，下一场重新起）。"""
    pool = _BrowserPool(_launch_opts(not _is_headed()))
    yield pool
    pool.close()


@pytest.fixture
def page(request, _pool):
    global _SHOT_N
    _SHOT_N = 0                                # 每条用例从 01 重新编号
    import re as _re
    # trace 文件名带 case_id：多用例并发/多次运行**不再互相覆盖**（原先都写 latest_trace.zip）
    _m = _re.search(r"test_(.+)", request.node.name)
    _cid = _m.group(1) if _m else request.node.name
    browser = _pool.get()                      # 会话级浏览器（崩了由 pool 重启 + 告警）
    _ctx_kw = {}
    if _DEBUG_VIDEO:                           # 调试·录制：整条用例录成 webm
        _ctx_kw = {"record_video_dir": str(RUN_LOG_DIR / "videos"),
                   "record_video_size": {"width": 1280, "height": 720}}
    context = browser.new_context(**_ctx_kw)
    if _PARTITION:
        # F6：把分区号注入页面（页面据此把 /api 调用带上 ?w=…）⇒ 并发 worker 各用各的数据
        context.add_init_script("window.__HYBRID_W = " + repr(_PARTITION) + ";")
    context.tracing.start(screenshots=True, snapshots=True)
    pg = context.new_page()
    try:
        yield pg
    finally:
        trace_dir = RUN_LOG_DIR / "traces"
        trace_dir.mkdir(parents=True, exist_ok=True)
        context.tracing.stop(path=str(trace_dir / f"{_cid}_trace.zip"))
        _vid = pg.video if _DEBUG_VIDEO else None   # 必须在关闭前拿到 video 句柄
        context.close()                             # ⚠️ 关上下文才会把 webm 真正写盘（否则只有几 KB）
        if _vid:
            try:
                _t = RUN_LOG_DIR / "videos" / f"{_cid}.webm"
                _t.parent.mkdir(parents=True, exist_ok=True)
                _vid.save_as(str(_t))               # 改名成 <case_id>.webm（默认是随机名）
            except Exception:
                pass
        try:                                        # 清掉 Playwright 留下的随机名空壳
            for _f in (RUN_LOG_DIR / "videos").glob("page@*.webm"):
                _f.unlink()
        except Exception:
            pass
        # 注意：这里**不关浏览器**——会话级复用，由 _pool 在整场结束时关闭


@pytest.fixture
def ctx(request):
    import re
    node = request.node.name          # test_<case_id>
    m = re.search(r"test_(.+)", node)
    case_id = m.group(1) if m else "run"
    return CaseCtx(case_id, _load_data(case_id))


# ---- 操作辅助（生成用例脚本引用）----
_CURRENT_LOG: dict = {}

def _log(page, step, detail=""):
    cid = _CURRENT_LOG.get("case_id", "run")
    line = f"[TEST] {step}: {detail}"
    print(line, flush=True)
    _append_log(cid, line)

def _append_log(case_id, line):
    try:
        RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(RUN_LOG_DIR / f"{case_id}.log", "a", encoding="utf-8") as f:
            f.write(line + "\\n")
    except Exception:
        pass

_INDEX: dict = {}


def _item_for(hint, page):
    """semantic_name → probe 控件项。缓存优先；未命中才重探一次（兼容弹窗后出现的控件）。

    改造前每个动作都全页 probe（并发下页面时序不稳会超时）；现在只在首次/未命中时探。
    """
    from framework.probe import probe_page
    it = _INDEX.get(hint)
    if it is None:
        for x in probe_page(page):
            _INDEX.setdefault(x.get("semantic_name"), x)
        it = _INDEX.get(hint)
    if it is None:                      # 模糊兜底（包含关系），与改造前一致
        for k, v in _INDEX.items():
            if k and (hint in k or k in hint):
                return v
    return it


def _to_ref(it):
    from framework.element_map import ElementRef
    return ElementRef(
        semantic_name=it["semantic_name"],
        test_id=it.get("test_id"),
        role=it.get("role"),
        name=it.get("name"),
        placeholder=it.get("placeholder"),
        text=it.get("text"),
        label=it.get("label"),
        nearby_text=it.get("nearby_text"),
    )


def _loc(hint, page):
    """semantic_name → 真实 locator：分层定位（Tier1/Tier2/意图复验），失败走 Healer 自愈。

    HYBRID_SELF_HEAL=0 → 关闭自愈（CI 语义：失败即报，不做任何猜测性定位）。
    """
    from framework.locator_bridge import resolve_locator
    from framework.element_map import TestStep
    it = _item_for(hint, page)
    if it is None:
        raise RuntimeError(
            f"元素语义未找到: {hint} —— 确定性主定位没命中，语义兜底也没找到这个语义名。"
            f"常见原因：① 页面还在异步取数/弹层未渲染（慢机器与高并发下常见；检查就绪契约或设 HYBRID_READY_SELECTOR）；"
            f"② 弹层没打开（先确认上一步点击是否生效）；③ 语义名过期（页面改版后要重跑 probe/generate）。"
            f"排查：加 --debug 看逐步截图（log/<run_id>/shots/）。"
        )
    el = _to_ref(it)
    r = resolve_locator(page, el)
    if r["ok"]:
        if r.get("healed"):
            _HEALER.record_heal(TestStep(0, "locate", element=el, description=hint), r)
            _log(page, "heal", f"{hint} 指纹自愈 -> {r['strategy']} conf={r['confidence']}")
        return r["locator_obj"]
    if _SELF_HEAL:
        h = _HEALER.try_heal(page, TestStep(0, "locate", element=el, description=hint))
        if h.get("recovered"):
            _log(page, "heal", f"{hint} 自愈 -> {h['strategy']} conf={h['confidence']}")
            return h["locator_obj"]
        raise RuntimeError(f"元素定位失败且自愈未成功: {hint}（{h.get('reason') or '未知'}）")
    raise RuntimeError(f"元素定位失败: {hint}（{r.get('reason')}）")


# ---- 调试模式（cli run --debug）产物：逐步截图 + 录像 ----
# HYBRID_SHOTS=1 → 每步存一张 PNG（直接打开就能看"这一步长什么样"，序号即执行顺序）
# HYBRID_VIDEO=1 → 整个用例录成 webm（本机没有图形显示时的"看得见"方案）
_DEBUG_SHOTS = os.environ.get("HYBRID_SHOTS", "") == "1"
_DEBUG_VIDEO = os.environ.get("HYBRID_VIDEO", "") == "1"
_SHOT_N = 0


def _shot(page, tag):
    """调试模式：把当前页面存成 PNG（失败不影响用例执行）。"""
    global _SHOT_N
    if not _DEBUG_SHOTS:
        return
    try:
        import re as _re2
        _SHOT_N += 1
        d = RUN_LOG_DIR / "shots" / _CURRENT_LOG.get("case_id", "run")
        d.mkdir(parents=True, exist_ok=True)
        safe = _re2.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "_", str(tag))[:40].strip("_") or "step"
        page.screenshot(path=str(d / f"{_SHOT_N:02d}_{safe}.png"))
    except Exception:
        pass


def _act(page, action, semantic=None, primary=None, value=None):
    """执行动作：主用【确定性 locator】(零探测)；主失效才走语义定位/自愈兜底。

    健康页面 → 与改造前完全一致（零额外开销）；页面漂移 → 自动降级/自愈而非硬失败。
    HYBRID_SELF_HEAL=0 → 不做语义兜底（要"失败即报"时用）。
    """
    loc = None
    if primary is not None:
        try:
            cand = primary(page)
            n = _count_attached(cand)          # F2：有界等待后再数，别用瞬时 count 判生死
            if n == 1:
                loc = cand
            elif n == 0:
                _log(page, "warn", f"primary 等了 {_LOCATE_TIMEOUT_MS}ms 仍是 0 个 → 语义兜底 {semantic}")
            else:
                _log(page, "warn", f"primary 命中 {n} 个(非唯一) → 语义兜底 {semantic}")
        except Exception as e:
            _log(page, "warn", f"primary 失效 → 语义兜底 {semantic} ({type(e).__name__})")
    if loc is None:
        if not _SELF_HEAL:
            raise RuntimeError(f"确定性 locator 失效且 HYBRID_SELF_HEAL=0（不做推测性定位）: {semantic or action}")
        if not semantic:
            raise RuntimeError(f"确定性 locator 失效且无语义兜底: {action}")
        loc = _loc(semantic, page)
    if action == "click":
        loc.click()
    elif action == "fill":
        loc.fill(value if value is not None else "")
    elif action == "select":
        loc.select_option(value if value is not None else "")
    elif action == "check":
        loc.check()
    elif action == "press_enter":
        loc.press("Enter")
    else:
        raise NotImplementedError(f"未知动作: {action}")
    _shot(page, f"{action}_{semantic or ''}")      # 调试模式：动作执行后存一张图


def _click(page, hint):
    return _act(page, "click", semantic=hint)


def _fill(page, hint, value):
    return _act(page, "fill", semantic=hint, value=value)


def _select(page, hint, value):
    return _act(page, "select", semantic=hint, value=value)


def _check(page, hint):
    return _act(page, "check", semantic=hint)


def _press_enter(page, hint):
    return _act(page, "press_enter", semantic=hint)

def _assert_text(page, text, desc=""):
    loc = page.get_by_text(text)
    loc.first.wait_for(timeout=5000)
    from playwright.sync_api import expect
    expect(loc.first).to_be_visible()
    line = f"[CHECK] ✓ 断言: {desc or text}"
    print(line, flush=True)
    _append_log(_CURRENT_LOG.get("case_id", "run"), line)
    _shot(page, f"assert_{text}")                  # 调试模式：断言通过后也存一张


# ---- 断言辅助（2026-09-13 D 项：断言类型从「只有文本」扩展到 11 种）----
# 约定：全部 web-first（playwright expect 自动重试）；成功统一打印 [CHECK] ✓ 断言: …
#       并写逐用例日志（调试模式另存一张截图）。
#       ❗ 缺字段 / 定位不到时，由**生成的脚本** pytest.fail（绝不静默少验一步 = 假绿）。


def _ok(page, desc, tag, detail=""):
    line = f"[CHECK] ✓ 断言: {desc}" + (f"（{detail}）" if detail else "")
    print(line, flush=True)
    _append_log(_CURRENT_LOG.get("case_id", "run"), line)
    _shot(page, f"assert_{tag}")


def _resolve(page, primary, semantic=None, *, unique=True):
    """断言定位：主用确定性 locator；失效才走语义兜底/自愈（与 _act 同策略）。

    unique=False 用于「复数元素」断言（count）——命中的 locator 本来就允许多个/零个，
    不能按「必须唯一」判定。
    """
    loc = None
    if primary is not None:
        try:
            cand = primary(page)
            # F2：unique=True（要唯一命中的断言）→ 有界等待后再判；
            #     unique=False（count 这类复数断言）保持瞬时判定 —— 「期望 0 个」是合法用例，
            #     等它 attached 只会白等一个超时。
            n = cand.count() if not unique else _count_attached(cand)
            if n == 1 or not unique:
                loc = cand
            elif n == 0:
                _log(page, "warn", f"断言 primary 等了 {_LOCATE_TIMEOUT_MS}ms 仍是 0 个 → 语义兜底 {semantic}")
            else:
                _log(page, "warn", f"断言 primary 命中 {n} 个(非唯一) → 语义兜底 {semantic}")
        except Exception as e:
            _log(page, "warn", f"断言 primary 失效 → 语义兜底 {semantic} ({type(e).__name__})")
    if loc is None:
        if not unique:
            raise RuntimeError(f"复数元素断言必须有确定性 locator（selector / 已映射 element）: {semantic}")
        if not _SELF_HEAL:
            raise RuntimeError(f"断言 locator 失效且 HYBRID_SELF_HEAL=0（不做推测性定位）: {semantic}")
        if not semantic:
            # F3：说人话 —— 旧文案「既没 selector 也没 element」与事实相反（该断言其实有 selector），
            #     实测把排查方向带偏。这里给出真实原因 + 下一步。
            raise RuntimeError(
                f"断言主定位失效：等了 {_LOCATE_TIMEOUT_MS}ms 仍然是 0 个元素；该断言用的是 selector，没有语义兜底可走。"
                f" 常见原因：① 刚做完 goto/点击，页面还在异步取数（给页面加就绪契约，或设 HYBRID_READY_SELECTOR）；"
                f" ② 元素真的不在了（真 bug）；③ 结果行还没渲染出来。"
                f" 排查：加 --debug 看逐步截图（log/<run_id>/shots/）。"
            )
        loc = _loc(semantic, page)
    return loc


def _assert_visible(page, primary, semantic=None, desc=""):
    """元素可见（如弹窗打开、提示出现）。"""
    loc = _resolve(page, primary, semantic)
    _expect(loc.first).to_be_visible()
    _ok(page, desc or f"{semantic or '该元素'} 可见", f"visible_{semantic or 'selector'}", "visible")


def _assert_hidden(page, primary, semantic=None, desc=""):
    """元素不可见/不存在（如弹窗关闭）。"""
    loc = _resolve(page, primary, semantic)
    _expect(loc.first).to_be_hidden()
    _ok(page, desc or f"{semantic or '该元素'} 不可见", f"hidden_{semantic or 'selector'}", "hidden")


def _assert_count(page, n, primary, semantic=None, desc=""):
    """元素数量（如结果行数）——注意 expect 必须是**操作前可确定**的值，别拿运行时计数硬凑。"""
    loc = _resolve(page, primary, semantic, unique=False)
    _expect(loc).to_have_count(int(n))
    _ok(page, desc or f"{semantic or '该元素'} 数量 = {n}", f"count_{semantic or 'selector'}", f"count={n}")


def _assert_attr(page, name, value, primary, semantic=None, desc=""):
    """元素属性值（如 data-field / class / href）。"""
    loc = _resolve(page, primary, semantic)
    _expect(loc.first).to_have_attribute(name, str(value))
    _ok(page, desc or f"{semantic or '该元素'} 属性 {name}={value}", f"attr_{name}", f"{name}={value}")


def _assert_value(page, value, primary, semantic=None, desc=""):
    """输入框当前值（注意：断言「刚填进去的值」= 输入回显，属假绿；要验「被清空/被改写」）。"""
    loc = _resolve(page, primary, semantic)
    _expect(loc.first).to_have_value(str(value))
    _ok(page, desc or f"{semantic or '该元素'} 输入值 = {value!r}", f"value_{semantic or 'selector'}", f"value={value!r}")


def _assert_checked(page, primary, semantic=None, desc=""):
    loc = _resolve(page, primary, semantic)
    _expect(loc.first).to_be_checked()
    _ok(page, desc or f"{semantic or '该元素'} 已勾选", f"checked_{semantic or 'selector'}", "checked")


def _assert_unchecked(page, primary, semantic=None, desc=""):
    loc = _resolve(page, primary, semantic)
    _expect(loc.first).not_to_be_checked()
    _ok(page, desc or f"{semantic or '该元素'} 未勾选", f"unchecked_{semantic or 'selector'}", "unchecked")


def _assert_enabled(page, primary, semantic=None, desc=""):
    loc = _resolve(page, primary, semantic)
    _expect(loc.first).to_be_enabled()
    _ok(page, desc or f"{semantic or '该元素'} 可用", f"enabled_{semantic or 'selector'}", "enabled")


def _assert_disabled(page, primary, semantic=None, desc=""):
    loc = _resolve(page, primary, semantic)
    _expect(loc.first).to_be_disabled()
    _ok(page, desc or f"{semantic or '该元素'} 不可用", f"disabled_{semantic or 'selector'}", "disabled")


def _assert_url(page, expected, desc=""):
    """页面 URL：以 http 开头 = 精确匹配；否则按「包含」匹配（跨页面跳转常用）。"""
    import re as _re
    exp = str(expected)
    if exp.startswith("http"):
        _expect(page).to_have_url(exp)
    else:
        _expect(page).to_have_url(_re.compile(_re.escape(exp)))
    _ok(page, desc or f"URL 含 {exp}", f"url_{exp[:24]}", "url")
'''

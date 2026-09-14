"""【Playwright】确定性元素探测 (probe)

职责：打开目标页面，用 Playwright 遍历所有可交互元素，抓取它们的
**结构化语义**（tag / ARIA role / accessible name / placeholder / label /
test_id / 可见文本），产出一个小写标识符 semantic_name。

关键设计：这一步【不经过 LLM】，是 100% 确定性代码。它把页面上的
交互元素"翻译"成人类可读的语义清单，供 Browser Use 的 agent 推理时
引用。精确定位永远由这里 + locator_bridge 的确定性逻辑完成，
LLM 只负责"理解意图 / 规划步骤 / 挑元素"，绝不负责"定位"。
"""
from __future__ import annotations
import re
import unicodedata
from playwright.sync_api import Page

# 被探测的交互元素选择器（覆盖绝大多数 GUI 控件）
INTERACTIVE_SELECTOR = (
    "button, input, select, textarea, a[href], "
    "[role=button], [role=link], [role=checkbox], [role=radio], "
    "[role=menuitem], [role=tab]"
)


def _slug(name: str) -> str:
    """把可读名字转成稳定的标识符片段（保留中文，空格/标点→下划线）。"""
    s = unicodedata.normalize("NFKC", name or "")
    s = re.sub(r"[^\w]+", "_", s, flags=re.UNICODE).strip("_")
    return s or "el"


def _visible(page: Page, locator) -> bool:
    try:
        return locator.is_visible()
    except Exception:
        return False


def _accessible_name(locator) -> str:
    """优先 aria-label，其次可见文本 / value。"""
    try:
        if locator.get_attribute("aria-label"):
            return locator.get_attribute("aria-label").strip()
        if locator.inner_text():
            return locator.inner_text().strip()
    except Exception:
        pass
    return ""


def _placeholder(locator) -> str:
    return (locator.get_attribute("placeholder") or "").strip()


def _label_text(page: Page, locator) -> str:
    """通过 for 属性关联的 label，或包裹的 <label>，取可见 label 文本。"""
    tag = locator.evaluate("e => e.tagName.toLowerCase()")
    el_id = locator.get_attribute("id")
    if el_id:
        for_ = page.locator(f'label[for="{el_id}"]')
        if _visible(page, for_) and for_.count():
            return for_.first.inner_text().strip()
    if tag == "input":
        wrapped = locator.evaluate("e => e.closest('label')?.innerText || ''")
        if wrapped:
            return wrapped.strip()
    # 兜底（2026-09-11 新增）：同容器内【前置的 <label>】——最常见的手写表单写法：
    #   <div class="field"><label>合同名称</label><input id="inp-name"></div>
    # （label 无 for、input 也没被 label 包裹 ⇒ 上面两条都拿不到，导致 AI 对表单字段完全失去标签信号）
    try:
        near = locator.evaluate("""(e) => {
            let cur = e.parentElement;
            for (let i = 0; cur && i < 3; i++) {
                const lab = cur.querySelector(':scope > label');
                if (lab && (lab.innerText || '').trim()) return lab.innerText;
                cur = cur.parentElement;
            }
            return '';
        }""")
        if near:
            return near.strip()[:60]
    except Exception:
        pass
    return ""


def _role_of(locator, page) -> str:
    """推断 ARIA role（显式 role 优先，否则按标签映射）。"""
    explicit = locator.get_attribute("role")
    if explicit:
        return explicit.strip()
    tag = locator.evaluate("e => e.tagName.toLowerCase()")
    mapping = {
        "button": "button", "input": "textbox", "select": "combobox",
        "textarea": "textbox", "a": "link", "checkbox": "checkbox",
    }
    itype = (locator.get_attribute("type") or "").lower()
    if tag == "input" and itype in ("checkbox", "radio", "button", "submit"):
        return itype
    return mapping.get(tag, tag)


# --- P4 新增：近邻结构/帮助文本抓取（解决同 role+name 元素消歧） ---
# 页面常见"多条同结构"场景（todo 列表、表格行、卡片），同一个 role+name
# 会命中多个元素（如两个 checkbox、两个"删除"链接）。单靠 role+name 无法区分，
# 必须带上【所属逻辑单元的关键文本】——这就是 nearby_text / container_heading 的价值。

# 判定"逻辑单元容器"的选择器：列表项、表格行、卡片、组合字段（就近优先）。
_LOGICAL_UNIT_SELECTOR = (
    "li, tr, article, [role=listitem], [role=row], [role=group], "
    "fieldset, .card, .todo-item"
)


def _nearest_container_text(locator) -> str:
    """向上找最近的逻辑单元容器，提取代表该单元的核心可见文本。

    对 todo 页：checkbox/删除 都在 li 里，li 里的 <span> 就是该项待办内容。
    但要【排除操作控件文本】（如"删除"、按钮名）——只留内容文本，
    否则 nearby_text 会混入"删除"二字，污染 Tier2 消歧匹配。
    """
    try:
        # 逐级向上找最近匹配逻辑单元容器的祖先；容器内取【非交互控件】的可见文本
        info = locator.evaluate("""(e) => {
            const sel = %r;
            const NON_TEXT = 'button, a, input, select, textarea, [role=button], [role=link], [role=checkbox], [role=radio], [role=tab], [role=menuitem]';
            let cur = e.parentElement;
            while (cur && cur !== document.body) {
                if (cur.matches(sel)) {
                    // 克隆后删掉所有交互后代，只留纯文本内容节点
                    const clone = cur.cloneNode(true);
                    clone.querySelectorAll(NON_TEXT).forEach(n => n.remove());
                    const txt = (clone.innerText || clone.textContent || '')
                        .replace(/\\s+/g, ' ').trim();
                    if (txt) return txt.slice(0, 80);
                    // 容器内没纯文本（比如全是操作按钮）→ 退回父容器继续往上找
                    cur = cur.parentElement;
                    continue;
                }
                cur = cur.parentElement;
            }
            return '';
        }""" % _LOGICAL_UNIT_SELECTOR)
    except Exception:
        return ""
    return info or ""


def _nearest_heading(locator) -> str:
    """向上找最近的标题，作为所在区块/栏目标题（区域消歧信号）。

    两级（2026-09-11 增强）：
      ① 祖先链上本身是 heading（原逻辑）；
      ② **最近一个"内部含 heading"的祖先区块**的标题 —— 例如
         <div class="modal"><h3>新建合同</h3><div class="field"><input id="inp-name"></div></div>
         从这里能拿到「新建合同」这个区域名，AI 才分得清"弹窗内字段"和"列表页筛选控件"
         （实测：缺了它，AI 把弹窗的客户下拉错选成搜索区的"全部客户_c1_c2_c3_c4"）。
    """
    try:
        h = locator.evaluate("""(e) => {
            let cur = e.parentElement;
            while (cur && cur !== document.body) {
                if (/^H([1-6])$/.test(cur.tagName) || cur.getAttribute('role') === 'heading') {
                    return cur.innerText || '';
                }
                cur = cur.parentElement;
            }
            cur = e.parentElement;
            while (cur && cur !== document.body) {
                const head = cur.querySelector('h1,h2,h3,h4,h5,h6,[role=heading]');
                if (head) return head.innerText || '';
                cur = cur.parentElement;
            }
            return '';
        }""")
    except Exception:
        return ""
    if not h:
        return ""
    import re as _re
    return _re.sub(r"\s+", " ", h).strip()[:80]


def _help_text(page: Page, locator) -> str:
    """取帮助文本：aria-describedby 指向内容 或 title 或 aria-label（若与 name 不同）。

    aria-describedby 是标准无障碍"帮助文本"来源；title 是传统提示。
    """
    try:
        describedby = locator.get_attribute("aria-describedby")
        if describedby:
            ids = describedby.split()
            for _id in ids:
                t = page.locator(f"#{_id}").first.inner_text() if page.locator(f"#{_id}").count() else ""
                if t:
                    return t.strip().replace("\\s+", " ")[:80]
        title = (locator.get_attribute("title") or "").strip()
        if title:
            return title[:80]
        aria = (locator.get_attribute("aria-label") or "").strip()
        if aria:
            return aria[:80]
    except Exception:
        pass
    return ""


def _ctx_token(nearby_text: str, container_heading: str, help_text: str) -> str:
    """同名元素消歧用的「上下文关键词」：优先取近邻文本的**第一个片段**。

    为什么取第一个片段：表格行内同名按钮（每行的「选择」）要的就是**这一行的首列内容**
    （客户名称）—— 近邻文本形如「北京华信科技有限公司 北京市朝阳区建国路88号」，
    第一片段正好是「北京华信科技有限公司」，对 AI 和人都可读、可判断点哪一行。
    """
    for raw in (nearby_text, container_heading, help_text):
        t = (raw or "").strip()
        if not t:
            continue
        first = re.split(r"[\s/|·,，、;；]+", t, maxsplit=1)[0].strip()
        if first:
            return first
    return ""


def _assign_semantic_names(items: list[dict], max_len: int = 26) -> None:
    """给探测结果统一分配 semantic_name（**两遍命名**，2026-09-14 改造）。

    规则：基础名**全局唯一**时保持原名（老用例零影响，如「搜索」）；
    一旦同名（≥2 个），这一组**全部**带上上下文后缀 `base@上下文`，拿不到上下文才退回 `base_2/base_3`。

    为什么不沿用「第一个用原名、后续加序号」：
      ① 序号是 DOM 顺序，行序一变就指向别的行（脆弱）；
      ② 对 AI 就是"天书"——`选择_3` 是哪一行？而 `选择@北京华信科技有限公司` 一眼就懂；
      ③ 一致性：同一组按钮里"只有一个不带上下文"会让人误以为它是特殊的那一个。
    """
    counts: dict[str, int] = {}
    for it in items:
        counts[it["_base"]] = counts.get(it["_base"], 0) + 1
    seen: set[str] = set()
    for it in items:
        base, ctx = it.pop("_base"), it.pop("_ctx", "")
        if counts[base] == 1:
            name = base
        else:
            cand = f"{base}@{_slug(ctx)}"[:max_len].rstrip("_") if ctx else ""
            name = cand if cand and cand not in seen else ""
            if not name:
                k = 2
                name = f"{base}_{k}"
                while name in seen:
                    k += 1
                    name = f"{base}_{k}"
        it["semantic_name"] = name
        seen.add(name)


def probe_page(page: Page, max_items: int = 200, page_name: str | None = None) -> list[dict]:
    """抓取当前页面的可交互元素语义清单。

    返回 [ {semantic_name, tag, role, name, placeholder, label, test_id, text,
            nearby_text, container_heading, help_text, page} , ... ]
    page_name（跨页流程 P3 新增）：给每个元素打上所属页面标记，供「跨页同名唯一化」与 AI 分页理解用。
    单页场景不传 → 字段为空串，行为与改造前完全一致。

    注意：探测结果里**刻意不含任何 selector/CSS**（那是脆弱信息，不该外流给 AI）——
    这里只给"语义 + 探测锚点"，真正的 locator 一律由 generator / locator_bridge
    在需要时用这些语义字段确定性推导。
    """
    items = []
    locators = page.locator(INTERACTIVE_SELECTOR)
    n = min(locators.count(), max_items)
    for i in range(n):
        loc = locators.nth(i)
        if not _visible(page, loc):
            continue
        tag = loc.evaluate("e => e.tagName.toLowerCase()")
        role = _role_of(loc, page)
        name = _accessible_name(loc)
        placeholder = _placeholder(loc)
        label = _label_text(page, loc)
        text = (name or placeholder or label)[:60]
        test_id = (loc.get_attribute("data-testid") or "").strip()

        # --- P4：抓近邻结构 + 帮助文本上下文（消歧用） ---
        nearby_text = _nearest_container_text(loc)
        container_heading = _nearest_heading(loc)
        help_text = _help_text(page, loc)

        base = _slug(text or tag or f"el{i}")

        items.append({
            "_base": base,                       # 第一遍：只攒基础名 + 上下文
            "_ctx": _ctx_token(nearby_text, container_heading, help_text),
            "tag": tag,
            "role": role,
            "name": name,
            "placeholder": placeholder,
            "label": label,
            "test_id": test_id,
            "text": text,
            # P4 语义上下文（AI 挑元素 + Tier2 消歧用）
            "nearby_text": nearby_text,
            "container_heading": container_heading,
            "help_text": help_text,
            # 跨页流程（P3）：所属页面标记（单页场景为空串，行为不变）
            "page": page_name or "",
        })
    _assign_semantic_names(items)                # 第二遍：统一命名（同名 → 全部带上下文）
    return items


def uniquify_across_pages(pages_items: list[tuple[str, list[dict]]]) -> tuple[list[dict], list[dict]]:
    """跨页元素合并 + **同名唯一化**（P3 D2）。

    输入 [(页名, items), ...]（按场景声明顺序）。
    规则：某个 semantic_name 只出现在**一个**页面 → 保持原名（老用例零影响）；
         出现在**多个**页面 → 全部改名 `原名@页名`，并记录冲突（日志里明示，绝不静默）。
    返回 (合并后的 items, 冲突列表[{semantic_name, pages: [...]}])。

    为什么必须做：generator 的 semantic_name→locator 是**全局一张表**，跨页同名会让
    两页的元素争抢同一个键 —— 过去是静默 `continue`（丢掉后者 = 悄悄用错页面的 locator）。
    """
    from collections import defaultdict
    where: dict[str, list[str]] = defaultdict(list)
    for pname, items in pages_items:
        for it in items:
            sn = it.get("semantic_name")
            if sn and pname not in where[sn]:
                where[sn].append(pname)
    dup = {sn: pgs for sn, pgs in where.items() if len(pgs) > 1}

    merged: list[dict] = []
    for pname, items in pages_items:
        for it in items:
            sn = it.get("semantic_name") or ""
            if sn in dup:
                it = dict(it, semantic_name=f"{sn}@{pname}", original_name=sn)
            merged.append(it)
    collisions = [{"semantic_name": sn, "pages": pgs} for sn, pgs in sorted(dup.items())]
    return merged, collisions

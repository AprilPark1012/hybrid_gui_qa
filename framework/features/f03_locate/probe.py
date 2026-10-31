"""【Playwright】确定性元素探测 (probe)

职责：打开目标页面，用 Playwright 遍历所有可交互元素，抓取它们的
**结构化语义**（tag / ARIA role / accessible name / placeholder / label /
test_id / 可见文本），产出一个小写标识符 semantic_name。

关键设计：这一步【不经过 LLM】，是 100% 确定性代码。它把页面上的
交互元素"翻译"成人类可读的语义清单，供 LLM 编排时引用（**不是**
browser-use 的 Agent 在浏览器里自主探索）。精确定位永远由这里 +
locator_bridge 的确定性逻辑完成，LLM 只负责"理解意图 / 规划步骤 /
挑元素"，绝不负责"定位"。
"""
from __future__ import annotations
import re
import unicodedata
from playwright.sync_api import Page

from framework.features.f03_locate.anchor_locate import container_from_ancestors, path_for_table_row

# 被探测的交互元素选择器（覆盖绝大多数 GUI 控件）
INTERACTIVE_SELECTOR = (
    "button, input, select, textarea, a[href], "
    "[role=button], [role=link], [role=checkbox], [role=radio], "
    "[role=menuitem], [role=tab]"
)

# ---- 增量探测用：一次 evaluate 拿回「可见交互元素的 key -> 索引」------------------------------
# 为什么需要（V8.3.7 性能治理 D3）：`expand_and_collect` 的等待循环原先只要「信号变了」就整页
# 重探一遍，而 `probe_page` 对**每个元素**要打 ~13 次 CDP 往返（实测 212 元素的页面 ≈ 60s）。
# 点开一个菜单往往只新增 4 个控件，却付出整页重探的代价 -> expand 成为最大单项（118s/七页）。
# 这里用**一次**往返拿到「索引对齐的 key 表」，循环据此算出**新出现的索引**，只探那一小撮。
# [!] 索引口径：`document.querySelectorAll(INTERACTIVE_SELECTOR)` 与
#     `page.locator(INTERACTIVE_SELECTOR).nth(i)` 顺序一致 —— 所以 JS 侧直接回传原始索引 i
#     （跳过不可见的元素，但**保留原始 i**，绝不能压缩索引，否则两边错位）。
_JS_KEY_MAP = """(sel) => {  /* KEY_MAP_ONLY: light index map for incremental probe */
  const els = document.querySelectorAll(sel);
  const out = {};
  for (let i = 0; i < els.length; i++) {
    const e = els[i];
    const r = e.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) continue;
    const txt = (e.innerText || e.value || e.getAttribute('aria-label') || '').trim().slice(0, 60);
    out[[e.tagName, e.id || '', e.getAttribute('name') || '',
         e.getAttribute('data-testid') || '', txt].join('|')] = i;
  }
  return out;
}"""


def visible_key_map(page: Page) -> dict[str, int]:
    """一次 evaluate 拿回「可见交互元素的 稳定key -> 列表索引」。

    用途见 `_JS_KEY_MAP` 上方注释（增量探测）。**取不到时返回空 dict**：调用方据此退化为
    「照常全页探测」，绝不因为拿不到信号而漏探控件。
    """
    try:
        return page.evaluate(_JS_KEY_MAP, INTERACTIVE_SELECTOR) or {}
    except Exception:                                              # noqa: BLE001
        return {}

# P16：往上看几层祖先来找「可锚定容器」（表格/弹层/表单/区块）—— 8 层足够覆盖常见结构，
# 再看更外面只会拿到 body/html（没有锚点价值），白花时间。
ANCESTOR_MAX_DEPTH = 8


def _ancestor_chain(loc, max_depth: int = ANCESTOR_MAX_DEPTH) -> list[dict]:
    """采集该元素的祖先链（**由近到远**），带角色/类名/埋点/aria-label —— 供 anchor 模块挑锚点。

    只在探测期跑一次 JS（一次 evaluate 拿全链，不逐个祖先往返）。
    """
    try:
        return loc.evaluate(
            """(e, maxDepth) => {
                 const out = []; let n = e.parentElement; let d = 0;
                 while (n && d < maxDepth) {
                   out.push({tag: n.tagName.toLowerCase(),
                             role: n.getAttribute('role') || '',
                             class: (typeof n.className === 'string' ? n.className : ''),
                             test_id: n.getAttribute('data-testid') || '',
                             aria_label: n.getAttribute('aria-label') || ''});
                   n = n.parentElement; d++;
                 }
                 return out;
               }""", max_depth) or []
    except Exception:
        return []


def _table_context(loc, row_attr: str | None = None, col_attr: str | None = None) -> dict | None:
    """若元素在表格行内 -> 采集「行锚文本 + 行标识 + 列（列标识 / 表头文本 / 列序）」，供下钻定位。

    真实项目表格常没有 `data-field`（也不是埋点），所以列信息是**三级降级**：
    列标识属性 → 表头文本 → 显式列序。拿不到就留空（下游据此放弃或另找锚点，绝不猜）。

    **属性名不写死**（V8.8.0 P0-C）
    -----------------------------
    `row_attr` / `col_attr` 由调用方从 `infer_grid_attrs` 的推断结果传入：
      · `col_attr` —— 列标识属性（`data-colid="col_57"` / `data-colx` / 缺省回落 `data-field`）
      · `row_attr` —— 行标识属性（`data-rowid="row_1"` / `data-rid`）
    不传就退回 `data-field` 老口径（老页面行为完全不变）。

    **行锚口径（L18 修法 A · 2026-09-28）**：不再取整行 `textContent`（含 demo `seed()` 的随机字段
    -> 每次重启必失配、静默降级），改为「**整表内恰好出现 1 次**的最短单元格文本」。
    取不到唯一候选 -> **保持现状**（整行文本）并置 `row_anchor_stable=False`（由生成期告警，批 3 落地）。
    """
    try:
        ctx = loc.evaluate(
            # [!] Playwright 的 `locator.evaluate(js, arg)` **只接受一个 arg** ——
            #   传两个会被当成多余位置参数直接抛错（而这里被 `except` 吞掉 -> 整段行内
            #   上下文静默变 None，表现为「明明有 row_id 却不走行内定位」）。打包成数组传。
            """(e, [rowAttr, colAttr]) => {
                 const tr = e.closest('tr');
                 if (!tr) return null;
                 const td = e.closest('td,th');
                 const tbl = e.closest('table');
                 const heads = tbl ? Array.from(tbl.querySelectorAll('thead th'))
                                       .map(x => (x.textContent || '').trim()) : [];
                 let colField = '', colHeader = '', colIndex = null;
                 // V8.8.0：列标识属性名由调用方推断后传入，不写死 data-field
                 const cAttr = (colAttr || 'data-field');
                 if (td) {
                   colField = td.getAttribute(cAttr) || '';
                   const cells = Array.from(tr.children);
                   const idx = cells.indexOf(td);
                   colIndex = idx >= 0 ? idx + 1 : null;
                   if (colIndex && colIndex <= heads.length) colHeader = heads[colIndex - 1];
                 }
                 // ★L18 修法 A（2026-09-28）：行锚不再取整行文本（含 demo 随机字段 -> 每次重启必失配），
                 //   改为「**整表内恰好出现 1 次**的最短单元格文本」—— 纯数据驱动，不猜哪列是业务键。
                 //   取最短：编号列这类键值天然短 -> 表达式更短更稳（顺带缓解 L13）。
                 const norm = (x) => (x.textContent || '').replace(/\\s+/g, ' ').trim();
                 const counts = new Map();
                 if (tbl) {
                   for (const r of tbl.querySelectorAll('tbody tr'))
                     for (const c of r.children) {
                       const t = norm(c);
                       if (t) counts.set(t, (counts.get(t) || 0) + 1);
                     }
                 }
                 const cand = [];
                 Array.from(tr.children).forEach((c, i) => {
                   const t = norm(c);
                   if (t && counts.get(t) === 1) cand.push({t: t, i: i});
                 });
                 cand.sort((a, b) => (a.t.length - b.t.length) || (a.i - b.i));
                 const stable = cand.length > 0;
                 const rowText = (tr.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 120);
                 // [!] 无唯一候选 -> **保持现状**（整行文本），绝不静默编锚；stable=false 由生成期告警
                 //    （「该行锚未取得稳定值，数据变动后可能降级为语义兜底」——批 3 落地，P18 §四兜底）
                 // V8.8.0 P0-C：行标识（`tr[data-rowid="row_1"]` 这类，属性名由调用方推断传入）。
                 //   比行锚文本更稳：值稳定、与行序无关；行内文本重复时也不受影响。
                 let rowId = '';
                 if (rowAttr) {
                   const rid = (tr.getAttribute(rowAttr) || '').trim();
                   if (rid) rowId = rid;
                 }
                 return {row_text: stable ? cand[0].t : rowText, row_anchor_stable: stable,
                         row_text_full: rowText,
                         row_id: rowId,
                         col_field: colField, col_header: colHeader,
                         col_index: colIndex,
                         table_test_id: tbl ? (tbl.getAttribute('data-testid') || '') : ''};
               }""",
            [row_attr or "", col_attr or ""]
        )
        return ctx or None
    except Exception:
        return None


def _slug(name: str) -> str:
    """把可读名字转成稳定的标识符片段（保留中文，空格/标点→下划线）。"""
    s = unicodedata.normalize("NFKC", name or "")
    s = re.sub(r"[^\w]+", "_", s, flags=re.UNICODE).strip("_")
    return s or "el"


def readable_name(text: str, help_text: str) -> str:
    """挑一个「有信息量」的名字来给控件命名。

    纯标点的名字没有信息量：企业 UI 里「选择/更多」按钮常写成 `...`，与 title="选择业务单元"
    配对。若直接用 `...` 当基础名，`_slug` 会把标点全吃掉 -> 退化成 `el` / `el_2` / `el_3`
    （2026-09-17 实测：订单页 3 个「...」按钮全叫 `el@…`，AI 与人工都认不出是哪一个）。
    -> 名字里没有任何字母/数字/汉字时，用 help_text（title / aria-describedby）兜底。
    """
    t = (text or "").strip()
    if any(ch.isalnum() for ch in t):
        return t
    return (help_text or t).strip()


def _visible(page: Page, locator) -> bool:
    try:
        return locator.is_visible()
    except Exception:
        return False


def _accessible_name(locator) -> str:
    """优先 aria-label，其次可见文本。

    [!] 2026-09-24 事故(4)（真实系统也会踩）：**`<select>` 的 inner_text 是它全部 `<option>` 的拼接**，
    不是它的可访问名。demo 的 `<select id="sel-mu">` 因此被叫成
    `"请选择\n0021\n0451\n1031"`（换行连接）-> 拿这个名字去 `get_by_role(name=…)`
    **永远匹配不到**（实测 `RuntimeError: 元素定位失败且自愈未成功: 请选择_0021_0451_1031`）。
    浏览器口径：`<select>` 的可访问名只来自 aria-label/aria-labelledby/关联 `<label>`，与选项文本无关
    -> 这里对 select **不看 inner_text**，返回空 -> 上游自然回落到 label/placeholder 走「容器锚点 + 下钻」。
    """
    try:
        if locator.get_attribute("aria-label"):
            return locator.get_attribute("aria-label").strip()
        tag = (locator.evaluate("e => e.tagName.toLowerCase()") or "")
        if tag == "select":
            return ""
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
    # （label 无 for、input 也没被 label 包裹 -> 上面两条都拿不到，导致 AI 对表单字段完全失去标签信号）
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
      (1) 祖先链上本身是 heading（原逻辑）；
      (2) **最近一个"内部含 heading"的祖先区块**的标题 —— 例如
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


# 光秃秃的通用占位符（没有区分度，只能靠 label 认人）；描述性占位符不在其列。
_BARE_GENERIC_PLACEHOLDERS = {"请选择", "请输入", "选填", "全部", "请选择_", "选择", "-", "--"}


def assign_semantic_names(items: list[dict], max_len: int = 40,
                          page_name: str = "") -> None:
    """给探测结果统一分配 semantic_name（**两遍命名，且可重复调用**，2026-09-14 / 2026-09-18 批次 2 改造）。

    规则：基础名**在本次传入的清单里唯一**时保持原名（老用例零影响，如「搜索」）；
    一旦同名（≥2 个），这一组**全部**带上后缀，拿不到上下文才退回 `base_2/base_3`。

    [!] **后缀格式 = `基础名@页名[语境]`（2026-10-12 AprilPark1012拍板 B）**：
      页名**永远**是 `@` 后面的第一段，语境只在同页重名时补充。
      为什么必须这样（实测事故）：原先同页重名直接用**容器上下文**当后缀，产出
      `订单名称@订单系统`（应用名）、`订单名称@基础信息`（区块名）—— 而提示词里明写的
      硬约束是「`@` 后缀只能是场景声明的**页名**」。于是：
        · AI 遵守约束、按页名写 `订单名称@订单列表页` -> **清单里根本没有这个名字** -> 映射不上；
        · 框架自己产出的名字**违反了**自己立的约束。
      统一成「页名在前」之后，「`@` 后第一段是页名」成为**可机检的不变式**，
      AI 用例与判据按页名写名字必然能对上。

      页名来源：优先条目自带的 `page` 字段（跨页清单里每项都有），其次入参 `page_name`。
      两者都拿不到时才退回裸 `base@语境`（单页且未声明页名的老路径，行为与改造前一致）。

    为什么不沿用「第一个用原名、后续加序号」：
      (1) 序号是 DOM 顺序，行序一变就指向别的行（脆弱）；
      (2) 对 AI 就是"天书"——`选择_3` 是哪一行？而 `选择@北京华信科技有限公司` 一眼就懂；
      (3) 一致性：同一组按钮里"只有一个不带上下文"会让人误以为它是特殊的那一个。

    [!] **必须在「合并完所有探测轮次」之后重算一次**（2026-09-18 批次 2 S1 根因修复）：
    弹窗/弹层是**另起一轮 `probe_page`** 探的（`explorer._try_collect_modal_items`），
    每轮各自命名时，一个同名控件在「弹窗没开」那轮里是**唯一**的 -> 它独占裸名；
    另一个控件在别的轮次里带后缀 -> **裸名归谁取决于探测那一刻谁可见**，下游根本分不清
    （实测事故：两枚同名按钮，用例引用裸名，被静默映射到另一枚，点击被遮挡的按钮 30s 超时）。
    -> 落点：`explorer._merge_items()`（合并后统一重算）。

    留痕字段（下游判歧义 / 给人话用，绝不静默）：
      · `base_name`     唯一化前的基础名；
      · `ctx_token`     上下文关键词（消歧依据）；
      · `name_source`   `exact`（唯一，裸名）/ `ctx`（上下文消歧）/ `seq`（序号兜底）/ `page`（跨页唯一化，由
                        `uniquify_across_pages` 写，且**不再被本函数改写**）；
      · `base_conflict` 该 base 名在本清单里出现的**次数**（≥2 = 有过同名冲突）。
    """
    counts: dict[str, int] = {}
    for it in items:
        base = it.get("base_name") or it.pop("_base", "") or ""
        if not base:
            base = _slug(readable_name(it.get("text") or "", it.get("help_text") or "")
                         or it.get("tag") or "")
        # ★2026-09-22（口径 C 实测，订单页工具栏三个下拉）：
        # 占位符是**通用词**（"请选择"/"请输入"/"选填"）时拿它当基础名**毫无区分度** -> 同名一组只能落到
        # `请选择_2/3/4`（序号 = DOM 顺序，行序一变就指向别的控件）；而且**命名随探测范围漂移**
        # （一次性探测里是 `请选择_0021_0451_1031`，分轮探测里变成 `请选择_3`）-> 用例引用哪个名字都不稳。
        # 这类控件真正稳定的身份是它的 **label**（实测正是"业务单元/管理单元/帐套"）-> 通用占位符时改用 label。
        # [!] 只对**光秃秃的通用占位符**生效（"请选择"/"请输入"/"选填"）：像「请选择客户」「请输入合同名称」
        # 这类**描述性**占位符本身就是好名字，不该被改（改了反而与弹层里的客户字段撞名，
        # 实测把 5 个搜索用例引用的 `客户名称_右模糊_前缀匹配` 逼成了不稳的 `客户_2`）。
        _ph = _slug(it.get("placeholder") or "")
        if base and _ph and base == _ph and _ph in _BARE_GENERIC_PLACEHOLDERS:
            _lb = _slug((it.get("label") or "").split("\n")[0].strip())
            if _lb:
                base = _lb
        it["base_name"] = base
        it.setdefault("ctx_token", "")
        counts[base] = counts.get(base, 0) + 1
    seen: set[str] = set()
    for it in items:
        if it.get("name_source") == "page":        # 跨页唯一化后的名字是最终名，别再动
            seen.add(it.get("semantic_name") or "")
            continue
        base = it["base_name"]
        ctx = it.get("ctx_token") or ""
        if counts[base] == 1:
            name, src = base, "exact"
        else:
            # [!] 后缀 = `@页名[语境]`（AprilPark1012 2026-10-12 拍板 B）：页名永远在 `@` 后第一段，
            #   语境只在同页重名时补充。页名优先取条目自带的 `page`，其次入参。
            #   两者都没有（单页且未声明页名）才退回裸 `base@语境`，与改造前行为一致。
            _pg = str(it.get("page") or page_name or "").strip()
            _cx = _slug(ctx)
            if _pg and _cx:
                cand = f"{base}@{_pg}[{_cx}]"
            elif _pg:
                cand = f"{base}@{_pg}"
            elif _cx:
                cand = f"{base}@{_cx}"
            else:
                cand = ""
            cand = cand[:max_len].rstrip("_") if cand else ""
            if cand and cand not in seen:
                name, src = cand, "ctx"
            else:
                k = 2
                name = f"{base}_{k}"
                while name in seen:
                    k += 1
                    name = f"{base}_{k}"
                src = "seq"
        it["semantic_name"] = name
        it["name_source"] = src
        it["base_conflict"] = counts[base]
        seen.add(name)


def probe_page(page: Page, max_items: int = 200, page_name: str | None = None,
               *, only_indexes: set[int] | None = None) -> list[dict]:
    """抓取当前页面的可交互元素语义清单。

    返回 [ {semantic_name, tag, role, name, placeholder, label, test_id, text,
            nearby_text, container_heading, help_text, page, opens_new_tab,
            anchor, path} , ... ]

    P16（2026-09-22）新增两个字段 —— 为「真实系统只有顶层元素有 testid」这件事服务：
      · `anchor`：最近的**可锚定容器**（表格/弹层/表单/区块）+ 它的锚点信号
        （`{"kind","by","value"}`；有容器但没信号时 by/value 为 None；没有容器 -> None）；
      · `path`：行内元素的**容器内相对路径**（行锚文本 / 列 = data-field→表头文本→列序 / 目标语义）；
        不在表格行内 -> None（此时靠 anchor + role/name 定位，不需要相对路径）。
    两者都**只描述、不定位**，也不含任何 CSS/selector（本项目的铁律：不让 AI 猜 CSS）。
    page_name（跨页流程 P3 新增）：给每个元素打上所属页面标记，供「跨页同名唯一化」与 AI 分页理解用。
    单页场景不传 → 字段为空串，行为与改造前完全一致。

    注意：探测结果里**刻意不含任何 selector/CSS**（那是脆弱信息，不该外流给 AI）——
    这里只给"语义 + 探测锚点"，真正的 locator 一律由 generator / locator_bridge
    在需要时用这些语义字段确定性推导。
    """
    items = []
    # V8.8.0 P0-C：整页只做**一次**行/列标识属性推断，循环里反复复用。
    #   为什么只算一次：`infer_grid_attrs` 要扫全页 DOM，放在逐元素循环里会慢到不可用。
    #   推断不出来（空串）时，下游自动退回 `data-field` 老口径 —— 老页面行为完全不变。
    _grid_row_attr = ""
    _grid_col_attr = ""
    try:
        for _r in infer_grid_attrs(page):
            if _r.get("col_attr") and not _grid_col_attr:
                _grid_col_attr = _r["col_attr"]
            if _r.get("row_attr") and not _grid_row_attr:
                _grid_row_attr = _r["row_attr"]
    except Exception:
        _grid_row_attr, _grid_col_attr = "", ""
    locators = page.locator(INTERACTIVE_SELECTOR)
    n = min(locators.count(), max_items)
    for i in range(n):
        # D3（V8.3.7 性能治理）：只探指定索引 —— 增量重扫走这里，别把整页重探一遍。
        # None = 全探（默认，与改造前逐字段一致）；空集合 = 一个都不探（调用方据此跳过）。
        if only_indexes is not None and i not in only_indexes:
            continue
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
        # P25 第 4 个真缺陷修复（2026-10-11，AprilPark1012拍定）：**采集元素自身的 `id`**。
        # 为什么必要（实测证据）：订单详情页底部那两个「保存」里，行保存住在
        #   <section aria-label="详细信息"> -> 有锚点；而「右下角保存」（编辑态下「编辑」按钮
        #   文案变「保存」，id 恒为 #btn-detail-edit）住在 <div class="block"> —— 祖先链里
        #   **没有任何** anchor.py 认得的容器 -> anchor=None -> 只剩 role+name
        #   -> 与另一个"保存"**必然歧义**（实测 base_conflict=2，运行期定不住）。
        # 而 `id` 是元素**自身**的稳定契约、生产系统里最常见的选择器 —— 框架此前完全没采集它。
        # 口径：与 test_id 同级（都在元素自己身上）；优先级 test_id > element_id > 结构推导 > 裸语义。
        element_id = (loc.get_attribute("id") or "").strip()

        # --- 跨 tab 流程（2026-09-17）：这个控件点了会不会**新开 tab**？ ---
        # 判据：<a target="_blank">（含 formtarget）或 onclick 里出现 window.open。
        # 为什么由探针给这个信号：AI 需要知道「这个点击要开新 tab 并切过去」，
        # 而"会不会开新 tab"是 DOM 事实、不该让 LLM 猜（猜错就是点完还留在原页继续点，全乱）。
        opens_new_tab = _opens_new_tab(loc, tag)

        # --- P4：抓近邻结构 + 帮助文本上下文（消歧用） ---
        nearby_text = _nearest_container_text(loc)
        container_heading = _nearest_heading(loc)
        help_text = _help_text(page, loc)

        # --- P16（2026-09-22）：顶层锚点 + 容器内相对路径 -----------------------------
        # 为什么：真实系统一般只有顶层元素（表格/弹层/工具栏/区块）有 data-testid，
        # 子元素没有埋点 -> 定位必须"从锚点下钻"。这里把"锚点 + 相对路径"采集下来，
        # 交给 locator_bridge 合成 locator、交给 AI 作为描述口径（不让 AI 猜 CSS）。
        chain = _ancestor_chain(loc)
        if chain:
            chain[-1]["heading"] = container_heading        # 最外层节点带上最近 heading，供 region 锚用
        anchor = container_from_ancestors(chain)
        row_ctx = _table_context(loc, row_attr=_grid_row_attr, col_attr=_grid_col_attr)
        path = None
        if row_ctx:
            # V8.8.0 P0-C：行锚优先用 row_id（值稳定、与行序无关），
            #   拿不到才退回 row_text（行内唯一文本）再退回 row_index。
            path = path_for_table_row(row_text=row_ctx.get("row_text"),
                                      cell_field=row_ctx.get("col_field"),
                                      col_header=row_ctx.get("col_header"),
                                      col_index=row_ctx.get("col_index"),
                                      row_id=row_ctx.get("row_id") or None,
                                      target_role=role, target_text=None) or None
        elif anchor:
            # P16 批 6（口径 C）：**锚点里的表单字段**（弹层/区块内的输入框、下拉、按钮）没有行/列语境，
            # 但内层埋点撤除后它们恰恰最需要"从锚点下钻"。按字段自身信号产出一条 target 步：
            # placeholder（最稳）→ label → text。相对锚点定位，唯一性由 scope_locate 兜底。
            # 按**元素类型**挑最稳的信号（实测教训：demo 的 <label> 没有 for、也没包住 input
            # -> `get_by_label` 关联不上，给按钮选 label 步会定位失败 -> 按钮/链接优先用文本）
            if tag in ("input", "textarea", "select"):
                # P22 批 5：补 `title` 一步。为什么必须补：`get_by_text` 对表单控件**无效** ——
                # 它们的"名字"在 aria-label / title / name 上，没有文本节点。实测（demo 订单详情页
                # 行内输入框 `title="数量" aria-label="数量"`）：placeholder 空、label 空（<label> 无 for）
                # -> 原候选只剩 text -> 生成 `get_by_text("数量", exact=True)` -> 永远 0 命中。
                # title 是这类控件稳定且生产常见的写法（与下面按钮分支同一口径）。
                cands = (("placeholder", placeholder), ("label", label),
                         ("title", help_text), ("text", text))
            elif str(text or "").strip() in ("...", "…", "") and help_text:
                # ★2026-09-22：图标按钮（文字就是 "..."）**text 毫无区分度** —— 弹层里 3 个「…」
                # （业务单元/管理单元/帐套）用 text 步定位**必然歧义**（实测：primary 命中 3 个，
                # 用例直接红）。title（help_text）是这类按钮唯一的稳定标识，也是生产里的写法。
                cands = (("title", help_text), ("text", text), ("label", label))
            else:
                cands = (("text", text), ("label", label), ("placeholder", placeholder))
            for by, val in cands:
                if val:
                    path = [{"axis": "target", "by": by, "value": val}]
                    break

        base = _slug(readable_name(text, help_text) or tag or f"el{i}")

        items.append({
            # 命名留痕（2026-09-18 批次 2 S1）：基础名与上下文关键词**留在产物里**，不再 pop 掉。
            # 为什么必须留：合并多轮探测（基础页 + 弹窗/弹层）之后要能**重算**一次命名 ——
            # 否则「某一轮里恰好唯一」的控件会独占裸名，下游拿着裸名分不清它指哪一个（事故根因）。
            "base_name": base,
            "ctx_token": _ctx_token(nearby_text, container_heading, help_text),
            "tag": tag,
            "role": role,
            "name": name,
            "placeholder": placeholder,
            "label": label,
            "test_id": test_id,
            # P25：元素自身 id（同上；容器无语义时它是唯一可用的稳定身份）
            "element_id": element_id,
            "text": text,
            # P4 语义上下文（AI 挑元素 + Tier2 消歧用）
            "nearby_text": nearby_text,
            "container_heading": container_heading,
            "help_text": help_text,
            # 跨页流程（P3）：所属页面标记（单页场景为空串，行为不变）
            "page": page_name or "",
            # 跨 tab 流程（2026-09-17）：点击是否新开 tab（探针给信号，AI 据此选 click_new_tab）
            "opens_new_tab": opens_new_tab,
            # P16：顶层锚点 + 容器内相对路径（无锚点/不在行内 -> None，绝不编造）
            "anchor": anchor,
            "path": path,
            # P25 片 3（要求6）：**探测当场**认为它有效 => true。
            #   这个字段是「例外标记」：generate 补探/复核发现页面改版、容器收起、行数变少
            #   导致该控件已经找不到时才置 false（置 false 的条目保留留痕、但不进映射、不进提示词）。
            "isValid": True,
        })
    assign_semantic_names(items)                 # 第二遍：统一命名（同名 → 全部带上下文）
    return items


# 兼容旧名（改造前叫 `_assign_semantic_names`；外部/测试若引用旧名仍可用）
_assign_semantic_names = assign_semantic_names


def _opens_new_tab(loc, tag: str) -> bool:
    """该控件点击后是否会新开 tab：`<a target=_blank>`（或 formtarget）或 onclick 里的 window.open。"""
    try:
        if tag == "a":
            if (loc.get_attribute("target") or "").strip().lower() == "_blank":
                return True
        if (loc.get_attribute("formtarget") or "").strip().lower() == "_blank":
            return True
        onclick = (loc.get_attribute("onclick") or "")
        if "window.open" in onclick:
            return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# 非 <table> 的行内列（div 网格）—— V8.7.29
# ---------------------------------------------------------------------------
# 实测背景（2026-10-31）：`order_detail.html` 的明细行是 **div 网格**，不是 `<table>`：
#
#     <div class="lines-grid" id="lines-grid">
#       <div class="head">操作</div><div class="head">行号</div>...    <- 表头（10 个）
#       <div class="cell">...</div>
#       <div class="cell" data-field="lineNo">{{ idx + 1 }}</div>
#       ...
#       <div class="cell" data-field="lineStatus">{{ ln.status }}</div>
#     </div>
#
# 原实现只扫 `page.locator("table")` —— 这类页面**一条列都探不到**（真机实测 0 条），
# 于是 AI 永远不知道 `lineNo` / `lineStatus` 可用；它想做行内断言只能瞎猜列名，
# 而猜出来的名字在运行时必然找不到 -> 断言失败。
#
# 口径：**只认带 `data-field` 的单元格**（与 `<table>` 路径同一个"列字段"概念，
# 不引入新的定位原语）；`<table>` 内的元素这里跳过，避免与 table 路径重复产出。
# 表头**尽力对齐**：用"同 class 连续段"推断每行单元格数，推断不出就留空串
# （宁漏不误伤 —— 空表头比错表头安全，错表头会让 AI 把列名对到错误的语义上）。
_INFER_GRID_ATTRS_JS = r"""
() => {
  // 按**值的分布**推断：哪个 data-* 属性是「行标识」、哪个是「列标识」。
  // 判据（纯结构，**完全不看属性名**）：
  //   · 行标识：该属性在**每一行**都有值，且**行与行之间的值都不同**
  //             （如 data-rowid="row_1"/"row_2"/"row_3"）
  //   · 列标识：该属性在**同一列位置**跨行取到**相同的值**
  //             （如第 1 列的每个单元格都是 data-colid="col_57"）
  // 为什么不能靠属性名：不同前端框架叫法不同（data-field / data-colid /
  //   data-colx / data-key ...），写死任何一个都等于只支持一家。
  const attrMap = (el) => {
    const r = {};
    for (const a of Array.from(el.attributes || [])) {
      if (a.name.indexOf('data-') === 0) r[a.name] = (a.value || '').trim();
    }
    return r;
  };

  const infer = (rows, cellsOf, name, kindName) => {
    if (rows.length < 2) return null;

    // ---- 行标识：行元素**自身**的 data-*
    const rowCand = {};
    for (const r of rows) {
      const am = attrMap(r);
      for (const k in am) {
        if (!am[k]) continue;
        (rowCand[k] = rowCand[k] || []).push(am[k]);
      }
    }
    let rowAttr = '';
    for (const k in rowCand) {
      const vs = rowCand[k];
      // 每行都有 + 值互不相同 -> 行标识
      if (vs.length === rows.length && new Set(vs).size === rows.length) { rowAttr = k; break; }
    }

    // ---- 列标识：单元格的 data-*，同列位置跨行值相同
    const colCand = {};
    rows.forEach((r) => {
      Array.from(cellsOf(r) || []).forEach((c, ci) => {
        const am = attrMap(c);
        for (const k in am) {
          if (!am[k]) continue;
          colCand[k] = colCand[k] || {};
          (colCand[k][ci] = colCand[k][ci] || []).push(am[k]);
        }
      });
    });
    let colAttr = '';
    let colCount = 0;
    for (const k in colCand) {
      const byCol = colCand[k];
      const idxs = Object.keys(byCol).map(Number);
      if (!idxs.length) continue;
      // 每个列位置：至少 2 行都有该属性，且**值只有一种**（跨行稳定）
      const stable = idxs.every((ci) => {
        const vs = byCol[ci];
        return vs.length >= 2 && new Set(vs).size === 1;
      });
      if (stable && idxs.length > colCount) { colAttr = k; colCount = idxs.length; }
    }

    const toArr = (o) => { const a = []; for (const k in o) a.push(o[k]); return a; };
    return {
      container: name,
      kind: kindName,
      row_attr: rowAttr,
      col_attr: colAttr,
      rows: rows.length,
      cols: colCount,
      // 样本给诊断用（一眼能看出推断对不对）
      row_sample: rowAttr ? rowCand[rowAttr].slice(0, 3) : [],
      col_sample: colAttr ? (() => { const o = colCand[colAttr]; const ks = Object.keys(o).map(Number).sort((a,b)=>a-b); return ks.slice(0, 6).map((ci) => o[ci] && o[ci][0]); })() : [],
      all_attrs: Object.keys(Object.assign({}, rowCand, colCand)),
    };
  };

  const out = [];

  // ---- 路径 1：<table>（行 = tbody tr，单元格 = 直接子 td）
  //   容器命名必须与 Python 侧 probe_row_fields 的 tname **完全同序**
  //   （data-testid 优先、再 id、最后兜底名），否则两边对不上、推断白做。
  Array.from(document.querySelectorAll('table')).forEach((t, ti) => {
    const rows = Array.from(t.querySelectorAll('tbody tr'));
    if (rows.length < 2) return;
    const nm = (t.getAttribute('data-testid') || t.id || ('table' + ti)).trim();
    const r = infer(rows, (tr) => Array.from(tr.children).filter((c) => c.tagName.toLowerCase() === 'td'), nm, 'table');
    if (r) out.push(r);
  });

  // ---- 路径 2：div 网格（行 = 容器子元素，单元格 = 行子元素）
  Array.from(document.querySelectorAll('div, section, ul, ol')).forEach((c, ci0) => {
    if (c.closest('table')) return;                 // 表格里的 div 不算网格
    const kids = Array.from(c.children || []);
    if (kids.length < 2) return;
    // 行 = 那些「至少一个子元素带 data-*」的子元素
    const rows = kids.filter((k) => Array.from(k.children || []).some((g) => Object.keys(attrMap(g)).length > 0));
    if (rows.length < 2) return;
    const nm = (c.id || c.getAttribute('data-testid') || (typeof c.className === 'string' ? c.className.trim().split(/\s+/)[0] : '') || ('grid' + ci0)).trim();
    const r = infer(rows, (row) => Array.from(row.children || []), nm, 'div-grid');
    if (r && (r.row_attr || r.col_attr)) out.push(r);
  });

  // 同一容器名只留信息最全的一条（div 网格会因嵌套被扫多次）
  const best = {};
  for (const r of out) {
    const k = r.container + '|' + r.kind;
    const prev = best[k];
    const score = (x) => (x.row_attr ? 1 : 0) + (x.col_attr ? 1 : 0) * 2 + x.cols;
    if (!prev || score(r) > score(prev)) best[k] = r;
  }
  return Object.keys(best).map((k) => best[k]);
}
"""


def infer_grid_attrs(page: Page, max_containers: int = 8) -> list[dict]:
    """推断页面上每个表格/网格容器用哪个 `data-*` 属性做**行标识**和**列标识**。

    返回 ``[{"container", "kind", "row_attr", "col_attr", "rows", "cols",
    "row_sample", "col_sample", "all_attrs"}, ...]``

    为什么不写死属性名
    ------------------
    不同前端框架的命名完全不同：``data-field`` / ``data-colid`` / ``data-colx`` /
    ``data-key`` …… 写死任何一个都等于只支持一家。这里**只按值的分布**判断：

    · **行标识** = 该属性在每一行都有值、且**行与行之间值都不同**
      （``data-rowid="row_1"`` / ``"row_2"`` / ``"row_3"``）
    · **列标识** = 该属性在**同一列位置跨行取到相同的值**
      （第 1 列的每个单元格都是 ``data-colid="col_57"``）

    这两种分布互斥且可从页面直接验证，所以不需要认识属性名。

    注意
    ----
    这是**诊断/供下游使用**的推断结果，不是「唯一真相」。`probe_row_fields`
    会在推断出 ``col_attr`` 时优先用它，推断不出时退回 ``data-field``（老行为不变）。
    推断失败一律返回空列表，**不抛异常** —— 页面结构千奇百怪，探测层不许因为推断不出来就崩。
    """
    try:
        rows = page.evaluate(_INFER_GRID_ATTRS_JS)
    except Exception:
        return []
    if not rows:
        return []
    out: list[dict] = []
    for r in rows[:max_containers]:
        if not isinstance(r, dict):
            continue
        out.append({
            "container": str(r.get("container") or "").strip(),
            "kind": str(r.get("kind") or "").strip(),
            "row_attr": str(r.get("row_attr") or "").strip(),
            "col_attr": str(r.get("col_attr") or "").strip(),
            "rows": int(r.get("rows") or 0),
            "cols": int(r.get("cols") or 0),
            "row_sample": list(r.get("row_sample") or []),
            "col_sample": list(r.get("col_sample") or []),
            "all_attrs": list(r.get("all_attrs") or []),
        })
    return out


_DIV_GRID_JS = r"""
(attrName) => {
  // V8.8.0 P0-A：属性名由调用方传入（推断得到的列标识属性），不再写死 data-field。
  //   不同前端框架的叫法不同：data-field / data-colid / data-colx / data-key ...
  //   调用方推断不出时会传 data-field（历史默认，老行为不变）。
  const attr = (attrName || 'data-field');
  const cells = Array.from(document.querySelectorAll('[' + attr + ']'));
  if (!cells.length) return [];
  const clsOf = (el) => {
    const c = el.className;
    return (typeof c === 'string' ? c : (c && c.baseVal) || '').trim();
  };

  // ---- V8.8.0：找「表头行」的文案，供「同层兄弟」推不出表头时兜底。
  //   两种常见结构：
  //     (a) 表头单元格与数据单元格同父（`<div class=head>表头</div><div class=cell data-field=..>`）
  //         -> 由下面的「同 class 连续段」直接推断，无需本函数
  //     (b) 表头自成一行（`<div class=head><div>列名</div>...</div><div class=row><div data-colx=..>值</div>...</div>`）
  //         -> 本函数处理：找容器里那个「子元素都不带 attr」但子元素数量等于列数的子容器
  const headerTextsOf = (gridEl, want) => {
    if (!gridEl || !want) return [];
    const kids = Array.from(gridEl.children || []);
    for (const k of kids) {
      const gk = Array.from(k.children || []);
      if (gk.length !== want) continue;
      // 这一行的子元素必须**都没有**列标识属性（否则它是数据行）
      if (gk.some((g) => (g.getAttribute(attr) || '').trim())) continue;
      const txt = gk.map((g) => (g.innerText || '').trim().replace(/\s+/g, ' '));
      if (txt.some((t) => t)) return txt;
    }
    return [];
  };

  const out = [];
  for (const c of cells) {
    if (c.closest('table')) continue;
    const p = c.parentElement;
    if (!p) continue;
    const sibs = Array.from(p.children);
    if (sibs.length < 2) continue;
    const segs = [];
    for (const s of sibs) {
      const k = clsOf(s);
      if (segs.length && segs[segs.length - 1][0] === k) segs[segs.length - 1][1] += 1;
      else segs.push([k, 1]);
    }
    let perRow = 0;
    if (segs.length >= 2 && segs[0][1] > 0 && segs[1][1] % segs[0][1] === 0) perRow = segs[0][1];
    const idx = sibs.indexOf(c);
    let header = '';
    if (perRow && idx >= perRow) {
      const col = (idx - perRow) % perRow;
      if (col < perRow) header = (sibs[col].innerText || '').trim().replace(/\s+/g, ' ');
    }
    // (b) 兜底：表头自成一行的情况 —— 用「所在行」的序号当列号，去表头行里取
    if (!header) {
      const rowEl = p;                    // 数据行的容器（<div class=row>）
      const gridEl = rowEl.parentElement;  // 网格容器（<div class=grid>）
      const rowKids = Array.from(rowEl.children);
      const colInRow = rowKids.indexOf(c);
      const want = rowKids.length;
      if (colInRow >= 0 && want > 1) {
        const heads = headerTextsOf(gridEl, want);
        if (heads.length === want) header = heads[colInRow] || '';
      }
    }
    out.push({
      grid: p.id || p.getAttribute('data-testid') || clsOf(p) || 'div-grid',
      field: (c.getAttribute(attr) || '').trim(),
      index: idx + 1,
      perRow: perRow,
      header: header,
    });
  }
  return out;
}
"""


def probe_div_grid_fields(page: Page, max_grids: int = 5,
                          col_attr: str | None = None) -> list[dict]:
    """探测**非 `<table>`** 的行内列（`<div class="cell" data-field="...">` 这类网格）。

    返回与 `probe_row_fields` **同构**的条目：`{table, index, field, header, kind}` ——
    下游（提示词拼装 / 按页校验 / 首行断言补正）因此完全不用改，一处产出两处通用。

    · `table`   = 网格容器的 `id` / `data-testid` / class 名（对不上就用 `div-grid`）；
    · `index`   = 该单元格在容器子元素里的 DOM 序号（1 起）。**不是列号** ——
      div 网格没有 `<tr>`，列号靠表头对齐，这里不假装有；
    · `header`  = 按"同 class 连续段"推断出的表头文案，推断不出就空串。

    `col_attr`（V8.8.0 P0-A）
    ------------------------
    **列标识的属性名，不写死**。不给就按页面结构自动推断（`infer_grid_attrs`），
    推断不出再退回历史默认 `data-field`。为什么：不同前端框架叫法不同
    （`data-field` / `data-colid` / `data-colx` / `data-key`），写死任何一个都只支持一家
    —— 实测 `attr_name_variant.html`（用 `data-colx`）在写死版本上探到 **0 条**。
    """
    out: list[dict] = []
    # 先定「要试哪些属性」：显式指定 > 推断结果（可能多个容器各不同）> 历史默认
    attrs_to_try: list[str] = []
    if col_attr:
        attrs_to_try.append(col_attr.strip())
    else:
        try:
            for r in infer_grid_attrs(page):
                ca = str(r.get("col_attr") or "").strip()
                if ca and ca not in attrs_to_try:
                    attrs_to_try.append(ca)
        except Exception:
            attrs_to_try = []
    if "data-field" not in attrs_to_try:
        attrs_to_try.append("data-field")        # 历史默认（兜底，老行为不变）

    for attr in attrs_to_try:
        try:
            rows = page.evaluate(_DIV_GRID_JS, attr)
        except Exception:
            rows = []
        if not rows:
            continue
        if _collect_div_rows(rows, max_grids, out):
            break                                 # 这个属性探到了东西，就用它
    return out


def _collect_div_rows(rows, max_grids: int, out: list[dict]) -> bool:
    """把 `_DIV_GRID_JS` 的原始行按「同网格同名列去重」整理进 `out`。返回是否收集到东西。"""
    if not rows:
        return False
    grids: dict[str, list[dict]] = {}
    seen: set[tuple[str, str]] = set()
    for r in rows:
        if not isinstance(r, dict):
            continue
        field = str(r.get("field") or "").strip()
        if not field:                       # 没有列标识的不算"列字段"（表格路径才处理 kinds）
            continue
        gname = str(r.get("grid") or "").strip() or "div-grid"
        # [!] 同一个网格里**同名列只留一条**：div 网格每行都重复渲染一遍列标识
        #   （实测 2 行 -> lineNo 出现 2 次），不去重的话清单会随行数
        #   线性膨胀，提示词里全是重复项（"提示变成噪音就等于没提示"）。
        #   列清单要回答的是"**有哪些列**"，不是"每行各有什么"。
        key = (gname, field)
        if key in seen:
            continue
        seen.add(key)
        grids.setdefault(gname, []).append(r)
    got = False
    for gname, items in list(grids.items())[:max_grids]:
        for r in items:
            out.append({
                "table": gname,
                "index": int(r.get("index") or 0),
                "field": str(r.get("field") or "").strip(),
                "header": str(r.get("header") or "").strip(),
                "kind": "",
            })
            got = True
    return got


def probe_row_fields(page: Page, max_tables: int = 5,
                     include_div_grids: bool = True) -> list[dict]:
    """探测「表格的行内列」清单 —— 供 AI 做**行内定位**（按行内容锚行 + 取该行某列）。

    返回 [{"table": <表名/testid>, "field": "contractNo", "header": "合同编号"}, ...]

    为什么需要它：新建记录的编号/合同号是**服务端动态分配**的，元素清单里不可能预先有它的语义名，
    所以「点新建那一行的合同编号」这类步骤只能写成 `row_text`（行锚文本：刚输入的名称）+
    `cell_field`（列字段，即页面里 `td[data-field=...]` 的值）。AI 必须知道有哪些 field 可用 ——
    这个清单就是它的依据；不让 AI 猜 CSS（那是本项目铁律）。
    """
    out: list[dict] = []
    # V8.8.0 P0-A：先推断每个容器用**哪个属性**做列标识，不写死 `data-field`。
    #   为什么必须推断：真实生产系统的列标识常是前端框架生成的（`data-colid="col_57"`
    #   这类，值稳定、跨行同列相同），而 demo 用的是 `data-field="orderName"`。
    #   写死任何一个都只支持一家 -> 换系统就探到 0 列 -> AI 只能猜列名。
    #   推断不出来时退回 `data-field`（**老行为完全不变**）。
    _col_attr_of: dict[str, str] = {}
    try:
        for _r in infer_grid_attrs(page):
            if _r.get("col_attr"):
                _col_attr_of[_r.get("container") or ""] = _r["col_attr"]
    except Exception:
        _col_attr_of = {}
    try:
        tables = page.locator("table")
        n = min(tables.count(), max_tables)
    except Exception:
        return out
    for ti in range(n):
        tbl = tables.nth(ti)
        try:
            tname = (tbl.get_attribute("data-testid") or tbl.get_attribute("id") or f"table{ti}").strip()
            # 该容器推断出的列标识属性；推断不出就用历史默认 data-field
            col_attr = _col_attr_of.get(tname) or "data-field"
            headers = tbl.locator("thead th").all_inner_texts()
            # V8.4.3：按**真实列位置**遍历**全部 td**（不再只挑 td[data-field]）。
            #   为什么必须这样（Windows 实测追到这一层）：
            #     (1) 「勾选列」是 `<td><input type=checkbox></td>`，**没有 data-field**
            #         -> 原实现直接跳过它 -> 清单里根本没这一列 -> 提示词又写着
            #         「cell_field 只能取清单里的 field，禁止自造」-> AI 无处可写，
            #         只能违约束自造一个假 field（实测它填了 cell_field="pick"）。
            #     (2) `header = headers[ci]` 里的 ci 原本是 **data-field 单元格的序号**，
            #         不是真实列号 -> 列 = [勾选, 合同编号] 时 ci=0 拿到表头「勾选」，
            #         **表头错位**（拿到的是别列的表头）。
            #   现在每列都给：index(真实列号,从 1 起，与生成器 cell_index 同口径) /
            #   field(可能为空串) / header(按真实列号对齐) / kind(无 field 时标注控件种类)。
            tds = tbl.locator("tbody tr").first.locator("td")
            m = tds.count()
            for ci in range(m):
                td = tds.nth(ci)
                # V8.8.0 P0-A：按**推断出的列标识属性**取值（不再写死 data-field）。
                field = (td.get_attribute(col_attr) or "").strip()
                if not field and col_attr != "data-field":
                    # 推断属性在这一格没有值（勾选列/操作列常见）——
                    # 再试一次历史默认，避免把「别家框架的表格」里恰好用 data-field 的列漏掉。
                    field = (td.get_attribute("data-field") or "").strip()
                header = headers[ci].strip() if ci < len(headers) else ""
                kind = ""
                if not field:
                    # 没有 data-field 的列：标出里面是什么，AI 才知道「这列是勾选框」
                    try:
                        if td.locator("input[type=checkbox]").count():
                            kind = "checkbox"
                        elif td.locator("input[type=radio]").count():
                            kind = "radio"
                        elif td.locator("button, a").count():
                            kind = "action"
                    except Exception:
                        kind = ""
                out.append({"table": tname, "index": ci + 1, "field": field,
                            "header": header, "kind": kind})
        except Exception:
            continue
    # V8.7.29：<table> 扫完，再补**非 table** 的 div 网格（订单详情页这类）。
    #   两条路径产出**同构**条目，下游提示词/按页校验/首行断言补正都不用改。
    #   `include_div_grids=False` 只给"只看 table"的老判据用，生产路径永远开着。
    if include_div_grids:
        out.extend(probe_div_grid_fields(page))
    return out


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
                # 留痕口径与同页唯一化一致（2026-09-18 批次 2）：写明来源是「跨页」，
                # 并让 `assign_semantic_names` 之后不再改写它（name_source == "page"）。
                it = dict(it, semantic_name=f"{sn}@{pname}", original_name=sn,
                          name_source="page")
            merged.append(it)
    collisions = [{"semantic_name": sn, "pages": pgs} for sn, pgs in sorted(dup.items())]
    return merged, collisions

# -*- coding: utf-8 -*-
"""声明页的**统一探测入口**（P25 片 3 · B1 三合一）。

## 为什么要有它（实测：同一能力两处实现，只改一处必漏）

「按场景声明的 `pages` 顺序逐页探测」这件事，过去在**两处**各写了一遍：

  · `explore.explorer._collect_pages_context`（explore 跨页探测）
  · `generate.generator._probe_declared_pages`（generate 现场补探）

两处都是「一个浏览器 + 顺序 goto + 登录前置 + 逐页前置 + `scan_page` + 跨页唯一化」，
只是各自的**附加动作**不同。历史事故证明这个结构必漏：

  2026-10-08 V8.3.7：generate 那处**漏了「可展开容器」**那一步（explore 侧两条路径都有）
  -> 干净环境下拿不到右上角角色菜单里的控件（如「切换为订单管理员@合同列表页」）
  -> 映射质量闸拒绝产出任何产物。

=> 口径（项目铁律 13「同一能力收敛成唯一入口」）：**逐页探测的骨架只写在这里**；
   谁的附加动作不同，用 `on_page` 回调注入 —— 绝不把整段复制一遍。

## 边界

· 本模块只管「怎么按顺序探一遍」；**每页探哪些步骤**由 `page_scan.scan_page()` 决定
  （那份知识也只有一处，本模块不重复）。
· 本模块**不认识任何业务概念**（没有「登录」「订单」这类词）—— 前置由场景声明传进来。
"""
from __future__ import annotations

from dataclasses import dataclass, field

#: 页名缺省值（场景没声明页名时用；与既有日志口径一致）
PAGE_FALLBACK = "页面1"


@dataclass
class PageScanResult:
    """逐页探测的结果（调用方按需取用；不再各自拼「返回值元组」那种易错形状）。"""
    per_page: list = field(default_factory=list)      # [(页名, [条目])]
    merged_items: list = field(default_factory=list)  # 跨页唯一化后的合并清单
    collisions: list = field(default_factory=list)    # 跨页同名冲突（唯一化留痕，供 CLI 明示）
    dom_ctx: list = field(default_factory=list)       # DOM 上下文（每项带 page）
    row_fields: list = field(default_factory=list)    # 行内列清单（每项带 page）
    pre_pending: list = field(default_factory=list)   # 场景级前置**没跑到**的步骤
    labels: list = field(default_factory=list)        # [(页名, url)]（调用方打印用）
    error: str = ""


def _base_of(url: str) -> str:
    """取 URL 的 `scheme://host[:port]` —— 登录前置必须在同一 origin 上做。"""
    import urllib.parse as _up
    try:
        u = _up.urlparse(str(url or ""))
        return f"{u.scheme}://{u.netloc}" if u.scheme else ""
    except Exception:
        return ""


def _field(spec, key: str, default=""):
    """从 **dict 或 ScenarioPage** 里读字段（两种形状都认 —— 只认一种就换条路径崩）。"""
    if isinstance(spec, dict):
        v = spec.get(key)
    else:
        v = getattr(spec, key, None)
        if key == "probe_url" and not v:
            # 页面地址带运行期值（订单号之类）时，探测要去 `probe_url`（场景声明，框架不猜）
            fn = getattr(spec, "probe_url_for", None)
            if callable(fn):
                return str(fn() or "")
    return default if v is None else v


def scan_pages(pages, *, auth=None, probe_pre=None, login=True, label="探测",
               with_dom_ctx=False, with_row_fields=False, collapse=True,
               on_page=None) -> PageScanResult:
    """按声明顺序**逐页探测**（唯一入口）-> `PageScanResult`。

    · `pages`：`[{"name","url","page"?,"pre"?,"probe_url"?}]`（dict 或 `ScenarioPage` 均可）；
    · `login`：是否先做登录前置（`run.login.ensure_logged_in`，与执行期**同一个入口**）；
    · `probe_pre`：**场景级**探测前置（逐页尝试、每步只跑一次 —— 见下方注释）；
    · `on_page(page_name, pg, merged_one, clicked, seen, row_fields) -> list[dict]`：调用方的**附加动作**，
      返回要**追加**到本页清单的条目（例：generate 侧的行内列控件、
      explore 侧「前置动作证明可点的控件」）。返回空/None = 不追加。
    · `collapse`：跨页聚合后再过一次「同容器重复控件收敛」（清单不变式要落在**每个对外出口**上）。

    返回的对象**总是完整**的；探测中途失败时 `error` 非空、其余字段是已探到的部分
    （调用方可按需降级，且降级必须出声 —— 由调用方打印）。
    """
    from playwright.sync_api import sync_playwright
    from framework.shared.browser import launch_opts
    from framework.features.f03_locate.probe import probe_row_fields, uniquify_across_pages
    from framework.features.f03_locate.page_scan_probe import scan_page

    res = PageScanResult()
    per_page: list = []
    dom_ctx: list = []
    row_fields: list = []
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(**launch_opts(headless=True))
            ctx = b.new_context()
            _first = str(_field((pages or [{}])[0], "url", "") or "")
            if login:
                from framework.shared.login import ensure_logged_in
                _lg = ensure_logged_in(ctx, _base_of(_first), auth or {})
                if _lg.get("attempted"):
                    print(f"      [{label}] [key] 登录前置："
                          + ("ok" if _lg.get("ok") else f"[!] 失败 -> {_lg.get('reason')}"))
            pg = ctx.new_page()
            # 场景级探测前置的待办（每步只跑一次；跑不到的留到最后统一告警）
            _pp_pending = list(probe_pre or [])
            for spec in (pages or []):
                _pp_clicked: list = []           # 逐页重置：只补**本页**点到过的控件
                _pp_seen: dict = {}              # 逐页重置：点击那一刻记下的定位锚（名字 -> 字段）
                _name = str(_field(spec, "name", "") or PAGE_FALLBACK)
                _url = str(_field(spec, "probe_url", "") or _field(spec, "url", "") or "")
                res.labels.append((_name, _url))
                pg.goto(_url, wait_until="domcontentloaded")
                try:
                    # 本 demo 的 networkidle 不可靠（fetch 悬挂 -> 永不 idle -> 30s 超时），
                    # 所以等页面自己的就绪契约，拿不到再给有界缓冲。
                    pg.wait_for_selector("body[data-hybrid-ready='1']", timeout=8000, state="attached")
                except Exception:
                    pg.wait_for_timeout(500)
                # ---- 场景级探测前置：**逐页尝试、能跑就跑、每步只跑一次** ----
                # [!] 为什么不是「只跑第一页」（实测踩到）：第一页可能是登录页，那儿根本没有
                #   切身份控件 -> 前置报「没找到」。逐页尝试让「登录」自然落在登录页、
                #   「切身份」自然落在声明了该控件的页 —— 且**只按精确名字匹配**，
                #   找不到就留给后面的页，**绝不猜别的控件去点**（铁律：不让框架猜控件）。
                #   必须在 scan_page **之前**：前置常改变权限上下文（切角色），
                #   扫在它之后才拿得到编辑态/动态新增的控件。
                # [!] `_pp_done` 必须**先初始化再进 if**：没声明 probe_pre 的场景
                #   `_pp_pending` 一开始就是空，旧写法（只在 if 里赋值、下一行无条件读）
                #   会对任何没声明 probe_pre 的场景抛 UnboundLocalError（被兜住 = 探测静默退化）。
                _pp_done: list = []
                if _pp_pending:
                    _pp_done = _run_pre(pg, _pp_pending, "场景探测前置",
                                        quiet_missing=True, require_all_resolvable=True,
                                        seen=_pp_seen)
                    _pp_pending = [s for s in _pp_pending if s not in _pp_done]
                _pp2 = _run_pre(pg, _field(spec, "pre", None), _name, seen=_pp_seen)
                _pp_clicked += [x for x in (list(_pp_done) + list(_pp2)) if x not in _pp_clicked]
                # ---- 每页探哪些步骤：由唯一入口决定（本模块不重复这份知识）----
                _sc = scan_page(pg, page_name=_name, tag_page=True)
                merged_one = _sc.items
                _remember_required(merged_one, _name)      # 必填项覆盖校验（唯一入口）
                # [!] 行内列清单要在回调**之前**取好：回调（如 explore 侧）要用它合成
                #   `_当前行` 形态的列控件。若让回调自己去探一遍，就是**同一件事探两次**
                #   （多一次浏览器往返，还可能与这里的结果不一致）。
                _rf: list = []
                if with_row_fields:
                    _rf = list(probe_row_fields(pg) or [])
                    for x in _rf:
                        x["page"] = _name
                    row_fields.extend(_rf)
                if on_page is not None:
                    _extra = on_page(_name, pg, merged_one, _pp_clicked, _pp_seen, _rf)
                    if _extra:
                        merged_one = list(merged_one) + list(_extra)
                per_page.append((_name, list(merged_one)))
                if with_dom_ctx:
                    for d in _dom_context(pg):
                        d["page"] = _name
                        dom_ctx.append(d)
                print(f"      [{label}] 跨页探测: [{_name}] {_url} -> "
                      f"{len(merged_one)} 个控件（弹窗补充 {len(_sc.modal_items)}）")
            b.close()
        merged, collisions = uniquify_across_pages(per_page)
        if collapse:
            _collapse(merged)
        res.per_page = per_page
        res.merged_items = merged
        res.collisions = collisions
        res.dom_ctx = dom_ctx
        res.row_fields = row_fields
        res.pre_pending = list(_pp_pending)
        return res
    except Exception as e:                                     # noqa: BLE001
        res.error = f"{type(e).__name__}: {str(e)[:200]}"
        res.per_page = per_page
        res.dom_ctx = dom_ctx
        res.row_fields = row_fields
        return res


# ---- 内部小工具（保持"唯一入口"：各调用方不各写一份） ----

def _run_pre(pg, pre, page_name: str = "", *, quiet_missing: bool = False,
             require_all_resolvable: bool = False, seen: dict | None = None) -> list:
    """跑一组前置动作 —— **委托到唯一入口** `explorer_explore._run_pre_actions`。

    [!] 这里曾经自己写一份调用（直接 `run_pre_actions(..., seen=seen)`），而引擎**根本不认
        `seen` 参数** => 每次必然 `TypeError` => 被 `except TypeError` 兜成"旧签名调用"
        => `quiet_missing` / `require_all_resolvable` **全部丢失**，却**不报错**。
        后果（2026-10-12 实测）：`require_all_resolvable=True` 从未生效，场景级前置在**登录页**
        上被逐条执行，「超」被子串匹配点掉并记入 done => 后面所有业务页都不再切身份
        => 详情页「编辑」置灰 => 行内控件探不到 => AI 只能照场景文案编名字 => 定位失败。

    口径（铁律 13「同一能力收敛成唯一入口」）：探测期怎么点前置，只有一份实现。
    `explorer_explore._run_pre_actions` 已经把 `seen` 正确转成引擎的 `on_clicked` 回调，
    这里**只转发**，不再持有第二套调用姿势。
    """
    if not pre:
        return []
    from framework.features.f02_semantic.explorer_explore import _run_pre_actions
    return list(_run_pre_actions(pg, pre, page_name, quiet_missing=quiet_missing,
                                 require_all_resolvable=require_all_resolvable,
                                 seen=seen) or [])


def _remember_required(items, page_name: str) -> None:
    """必填项覆盖校验的登记入口（探测期把「页面标了必填」的控件记下来）。"""
    try:
        from framework.features.f02_semantic.explorer_explore import _remember_required_fields
        _remember_required_fields(items, page_name)
    except Exception:
        pass


def _dom_context(pg) -> list:
    """DOM 上下文（给 AI 的结构背景）—— 唯一实现在 explorer 侧，这里只转发。"""
    try:
        from framework.features.f02_semantic.explorer_explore import _collect_dom_context
        return list(_collect_dom_context(pg) or [])
    except Exception:
        return []


def _collapse(items) -> None:
    """同容器重复控件收敛（清单不变式：每个对外出口都要过这道）。"""
    try:
        from framework.features.f02_semantic.explorer_explore import _collapse_row_repeats
        _collapse_row_repeats(items)
    except Exception:
        pass


def _row_fields_of(pg) -> list:
    """行内列清单（唯一实现在 probe 侧）。"""
    from framework.features.f03_locate.probe import probe_row_fields
    return list(probe_row_fields(pg) or [])

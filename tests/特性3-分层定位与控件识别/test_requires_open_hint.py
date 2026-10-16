# -*- coding: utf-8 -*-
"""特性3 · C2'：把「控件藏在哪个弹层入口后面」传给 AI —— 生成的用例会**先开入口再操作控件**。

## 问题（真值 · 端到端跑同一个场景时 AI 生成的用例死在这里）

    TimeoutError: Locator.click: Timeout 30000ms exceeded.
      - waiting for get_by_text("切换为发票管理员", exact=True)
      - locator resolved to <button class="nu-item" data-switch="invoice_admin">…) </button>
      - element is not visible

即：控件**确实在 DOM 里、定位也 resolve 成功**，但它藏在**未展开的菜单/弹层**里
-> 不可见 -> 点击 30s 超时。这不是定位失败，是**缺了一步「先点开入口」**。

## 框架其实早就知道这件事，只是没告诉 AI

探测期日志里本来就有（真实输出）：

    [probe] [OK] 展开「nu-avatar」后补探到 4 个控件（容器 nu-menu）

本特性就把这句话变成①探针条目上的一个标记字段 + ②提示词里的一条硬规则。

## 判据口径（**全部不启动浏览器**：假 page + 假 items）

  1. 标记字段真的被打上，值 = **入口控件的语义名**（AI 只能引用清单里真实存在的名字）；
  2. 拿不到语义名时才降级成「可读的 DOM id」，且**不是空串**（空串等于没给线索）；
  3. 提示词里真的出现了这条规则，且说清了「为什么」（报错形态）与「入口只开一次」；
  4. 没有这个标记的条目**不许**被凭空加上该字段（否则等于给 AI 假信号）；
  5. 合并后重命名会让探测中途抓到的名字**悬空** -> 提示词组装时按稳定 id 重新解析成最终名。

跑法（秒级、不需要 demo / 浏览器）：
    python -m pytest tests/特性3-分层定位与控件识别/test_requires_open_hint.py -q
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from framework.features.f03_locate.expandable_probe import (   # noqa: E402
    mark_requires_open, opener_ref_for)
from framework.features.f02_semantic import explorer_explore as EX   # noqa: E402

REPO = Path(__file__).resolve().parents[2]
EXPANDABLE = REPO / "framework" / "features" / "f03_locate" / "expandable_probe.py"
EXPLORER = REPO / "framework" / "features" / "f02_semantic" / "explorer_explore.py"

FIELD = "requires_open"


def _fn_src(path: Path, name: str) -> str:
    """取某个函数的源码**并剔掉注释行** —— 只写在注释里的「实现」不算实现（本项目已犯 4 次）。"""
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            body = lines[node.lineno - 1: node.end_lineno]
            return "\n".join(ln for ln in body if not ln.lstrip().startswith("#"))
    raise AssertionError(f"{path.name} 里找不到 {name}()")


def _rule_block_src() -> str:
    """取源码里「规则:」那段静态提示词的原文（用于钉住「这条规则属于通用规则段」）。"""
    src = EXPLORER.read_text(encoding="utf-8")
    i = src.index("规则:")
    return src[i:i + 9000]


# ============================================================ (1) 入口身份怎么取


def test_opener_ref_prefers_the_name_the_ai_will_see():
    """优先用**语义名**：AI 只能引用清单里真实存在的 semantic_name（自造名字必被质量闸拦下）。"""
    base = [{"semantic_name": "入口甲", "element_id": "op-1"},
            {"semantic_name": "搜索", "element_id": "btn-1"}]
    assert opener_ref_for("op-1", base) == "入口甲", (
        "入口控件已经在基础清单里可见 -> 必须把它的语义名给 AI，而不是一个 id")


def test_opener_ref_falls_back_to_readable_id():
    """拿不到语义名时降级成**可读的 id**（降级而不是返回空 —— 空串等于没给任何线索）。"""
    base = [{"semantic_name": "别的控件", "element_id": "other"}]
    assert opener_ref_for("op-1", base) == "op-1"
    assert opener_ref_for("op-1", []) == "op-1", "清单里找不到入口也必须给出可读线索，不能返回空串"
    # 连 id 都没有时才如实给空（这种候选在 expand_and_collect 里本来就被跳过）
    assert opener_ref_for("", base) == ""


def test_opener_ref_matches_by_element_id_not_by_name():
    """对应关系是 **DOM id -> 条目**（`element_id`），不许拿语义名去瞎猜。"""
    base = [{"semantic_name": "op-1", "element_id": "x"}]      # 语义名恰好等于 id，但 element_id 不是
    assert opener_ref_for("op-1", base) == "op-1", (
        "只有 element_id 逐字相等才算命中；否则降级成 id（宁降级，不猜错控件）")


# ============================================================ (2) 标记字段被真的打上


def test_mark_requires_open_stamps_fields_and_keeps_existing_ones():
    fresh = [{"semantic_name": "菜单项甲", "role": "menuitem", "text": "菜单项甲"}]
    n = mark_requires_open(fresh, opener_id="op-1", opener_ref="入口甲", container_key="layer-1")
    assert n == 1
    assert fresh[0][FIELD] == "入口甲"
    assert fresh[0]["requires_open_id"] == "op-1", "必须留下稳定 id（合并改名后靠它重新解析）"
    assert fresh[0]["requires_open_container"] == "layer-1"
    # 既有字段一个都不许被动
    assert fresh[0]["semantic_name"] == "菜单项甲" and fresh[0]["role"] == "menuitem"


def test_mark_requires_open_is_noop_on_empty():
    assert mark_requires_open([], opener_id="op-1", opener_ref="入口甲") == 0


# ============================================================ (3) 接线：展开补探的控件会被标记


class _FakeLocator:
    def __init__(self):
        self.clicks = 0

    @property
    def first(self):
        return self

    def click(self, **kw):
        self.clicks += 1

    def is_visible(self):
        return False


class _FakePage:
    """最小假页：只实现 `expand_and_collect` 真正用到的那几个动作（不启动浏览器）。"""

    def __init__(self, scan, kmaps):
        self._scan = scan
        self._kmaps = list(kmaps)

    def evaluate(self, script, *a, **kw):
        if "KEY_MAP_ONLY" in script:              # 增量探测用的 key->索引 表
            return self._kmaps.pop(0) if self._kmaps else {}
        return self._scan                        # 可展开容器扫描

    def wait_for_timeout(self, ms):
        pass

    def locator(self, sel):
        return _FakeLocator()


def _cand(opener_id="op-1", container_id="layer-1"):
    """一个「隐藏容器 + 它的可见触发器」的候选（结构与探针侧 JS 采集的字段一一对应）。"""
    return [{
        "container_key": container_id, "container_id": container_id, "container_tag": "div",
        "siblings": [
            {"key": opener_id, "id": opener_id, "tag": "button", "visible": True,
             "interactive": True, "contains_interactive": False, "order": 0,
             "aria_controls": "", "aria_haspopup": False},
            {"key": container_id, "id": container_id, "tag": "div", "visible": False,
             "interactive": False, "contains_interactive": True, "order": 1,
             "aria_controls": "", "aria_haspopup": False},
        ],
    }]


def _expand(monkeypatch, base_items, opener_id="op-1", container_id="layer-1"):
    """跑一次 expand_and_collect：第 2 轮 key 表多出一个索引 -> 触发「只探新元素」并拿到 1 个新控件。"""
    import framework.features.f03_locate.expandable_probe as ex

    def _fake_probe(page, max_items=200, page_name=None, *, only_indexes=None):
        return [{"semantic_name": "菜单项甲", "role": "menuitem", "text": "菜单项甲"}]

    monkeypatch.setattr("framework.features.f03_locate.probe.probe_page", _fake_probe)
    rounds = {"n": 0}

    def _km(page):
        rounds["n"] += 1
        return {"a": 0} if rounds["n"] == 1 else {"a": 0, "b": 1}

    monkeypatch.setattr("framework.features.f03_locate.probe.visible_key_map", _km)
    return ex.expand_and_collect(_FakePage(_cand(opener_id, container_id), []),
                                 base_items, settle_s=0.7)


def test_expand_and_collect_marks_items_with_the_opener_name(monkeypatch):
    """接线：因展开某入口才被发现的控件，必须带上「先点开这个入口」的标记。"""
    base = [{"semantic_name": "入口甲", "element_id": "op-1"}]
    got = _expand(monkeypatch, base)
    assert len(got) == 1, f"假页应该恰好补探到 1 个新控件，实际 {len(got)}"
    assert got[0][FIELD] == "入口甲", (
        "补探到的控件没带上入口线索 -> AI 仍会直接点它 -> 运行期 element is not visible 超时")


def test_expand_and_collect_marks_id_when_opener_not_in_list(monkeypatch):
    """降级路径：基础清单里没有这个入口（探针截断/清单来源不是 probe_page）-> 给可读 id。"""
    got = _expand(monkeypatch, [])
    assert len(got) == 1
    assert got[0][FIELD] == "op-1", "拿不到语义名时必须降级成可读 id，而不是留空"


def test_expand_stamps_via_the_pure_helper():
    """源码守门（剔注释）：标记必须由 `mark_requires_open()` 落，别在循环里另写一段。"""
    body = _fn_src(EXPANDABLE, "expand_and_collect")
    assert "mark_requires_open(" in body, (
        "expand_and_collect 没有调用 mark_requires_open() —— 标记要么没落、要么被复制成第二份实现")


# ============================================================ (4) 提示词里的规则


def _menu_item(name="菜单项甲", **kw):
    d = {"semantic_name": name, "role": "menuitem", "tag": "button", "base_name": name,
         "text": name, FIELD: "入口甲", "requires_open_id": "op-1"}
    d.update(kw)
    return d


def test_prompt_states_open_entry_first_rule():
    """规则必须在提示词里，且说清「为什么」（报错形态）与「入口只开一次」。"""
    prompt = EX._build_planner_prompt("在某页面操作弹层里的控件", [_menu_item()], "http://x/1", [])
    assert FIELD in prompt, "提示词里没有提到标记字段 -> AI 根本没机会知道要开入口"
    assert "element is not visible" in prompt, (
        "规则只讲「要开入口」不讲「为什么」-> AI 会当成风格建议（实测它需要有后果才有约束力）")
    assert "点开" in prompt and "入口" in prompt


def test_rule_lives_in_the_generic_rules_block():
    """位置钉住：这条规则属于「规则:」通用规则段，且**编号位置就在 1b 与 2 之间**（换个场景也不会失效）。"""
    blk = _rule_block_src()
    assert FIELD in blk, "requires_open 的规则没写进通用规则段（换个场景就失效）"
    assert blk.index("1b.") < blk.index("1c.") < blk.index("2. semantic_name"), (
        "规则编号乱序/跑到了别的段里 —— 它在提示词里的位置决定 AI 读不读得到它")


def test_prompt_rule_text_is_not_comment_only():
    """剔注释后仍要在源码里看得到这条规则（「只写在注释里」本项目已犯过 4 次）。"""
    code = "\n".join(ln for ln in EXPLORER.read_text(encoding="utf-8").splitlines()
                     if not ln.lstrip().startswith("#"))
    assert FIELD in code


# ============================================================ (5) 字段怎么透给 AI


def test_compact_item_keeps_requires_open():
    c = EX._compact_item(_menu_item(), set())
    assert c[FIELD] == "入口甲", "压表示时把标记丢了 -> 规则形同虚设"


def test_compact_item_reports_nothing_when_absent():
    """负向自证：没有标记的控件**不许**凭空多出这个键（给 AI 假信号比不给更坏）。"""
    c = EX._compact_item({"semantic_name": "搜索", "role": "button"}, set())
    assert FIELD not in c
    assert "requires_open_id" not in c


def test_compact_item_refreshes_stale_opener_name_by_id():
    """合并重命名 -> 探测中途抓到的名字会悬空；按稳定 id 在**最终清单**里重新解析。

    这样做才不会让 AI 写一个清单里不存在的入口名（那会在生成期被映射闸拦下，白跑一轮）。
    """
    items = [{"semantic_name": "入口甲@页A", "element_id": "op-1"}]
    names = EX._opener_name_map(items)
    assert names == {"op-1": "入口甲@页A"}
    c = EX._compact_item(_menu_item(), set(), names)
    assert c[FIELD] == "入口甲@页A", f"悬空引用没被刷新（仍是 {c[FIELD]!r}）"


def test_compact_item_keeps_hint_when_id_unknown():
    """id 在最终清单里查不到（入口条目被裁/被合并掉）-> 保留原值，绝不静默清空。"""
    c = EX._compact_item(_menu_item(), set(), {})
    assert c[FIELD] == "入口甲"


def test_planner_prompt_passes_the_opener_map():
    """接线：提示词组装必须把「最终清单」的 id->名字映射传下去（否则刷新逻辑是死代码）。"""
    body = _fn_src(EXPLORER, "_build_planner_prompt")
    assert "_opener_name_map(" in body, "_build_planner_prompt 没建入口映射 -> 悬空引用刷新不了"
    assert body.count("_compact_item(") == 1, "控件清单有多处各自压缩 -> 两条路径会不同步"

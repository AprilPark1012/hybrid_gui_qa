"""探测路径「单一入口」契约（V8.3.7 起）。

背景（2026-10-08 事故）：
  同一个「页面探测」动作在框架里有 **三条实现**，各自手写一遍步骤：
    1) explorer.py::explore_single   (单页)
    2) explorer.py::explore_pages    (跨页)
    3) generator.py::_probe_declared_pages  (generate 现场探测)
  第 3 条**漏了「可展开容器」那一步** -> 拿不到右上角角色菜单里的控件 ->
  干净环境（无 element_map 快照）下 generate 报「2 个语义名映射不上」-> 质量闸拒绝产出任何产物。
  修法 = 收敛成唯一入口 scan_page()，三条路径都调它（方案 B，用户 2026-10-08 选定）。

判据口径：
  · 本文件守的是「结构契约 + 行为契约」，两者都**不需要 demo / 浏览器**（一类）。
  · 行为契约用**假 page + monkeypatch** 证明入口真的调了那几个底层步骤。
  · 负向自证：把入口里的 expand 那步摘掉，本文件必须红。
"""
from __future__ import annotations

import ast
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
SCAN_MOD = REPO / "framework" / "tools" / "probe" / "page_scan.py"
EXPLORER = REPO / "framework" / "tools" / "explore" / "explorer.py"
GENERATOR = REPO / "framework" / "tools" / "generate" / "generator.py"


# ---------------------------------------------------------------- 结构：入口存在

def test_scan_page_module_exists():
    """唯一入口模块必须存在。"""
    assert SCAN_MOD.is_file(), f"缺唯一入口模块: {SCAN_MOD.relative_to(REPO)}"


def test_scan_page_is_importable():
    from framework.tools.probe.page_scan import scan_page  # noqa: F401
    assert callable(scan_page)


# ---------------------------------------------------------------- 行为：入口真的调了各步骤

class _FakeLocator:
    def __init__(self, rec, sel):
        self._rec = rec
        self._sel = sel

    def click(self, **kw):
        self._rec.append(("click", self._sel))

    def is_visible(self):
        return False


class _FakePage:
    """最小假 page：只记录 evaluate / locator / wait_for_timeout 的调用。"""

    def __init__(self):
        self.calls = []

    def evaluate(self, *a, **kw):
        self.calls.append(("evaluate",))
        return []

    def locator(self, sel):
        return _FakeLocator(self.calls, sel)

    def wait_for_timeout(self, ms):
        self.calls.append(("wait", ms))

    def keyboard_press(self, k):
        pass


def _patch_layers(monkeypatch, calls):
    """把入口依赖的三个底层步骤换成记录器；返回各自被调用时的入参快照。"""
    import framework.tools.probe.page_scan as ps

    def fake_probe(page, **kw):
        calls.append(("probe_page", kw))
        return [{"semantic_name": "基础A", "name": "基础A"}]

    def fake_expand(page, base_items, **kw):
        calls.append(("expand_and_collect", {"base_len": len(base_items)}))
        return [{"semantic_name": "菜单项A", "name": "菜单项A"}]

    def fake_modal(page, items, **kw):
        calls.append(("_try_collect_modal_items", {"in_len": len(items)}))
        return [{"semantic_name": "弹层项A", "name": "弹层项A"}]

    def fake_merge(a, b):
        calls.append(("_merge_items", {"a_len": len(a), "b_len": len(b)}))
        return list(a) + list(b)

    monkeypatch.setattr(ps, "probe_page", fake_probe, raising=True)
    monkeypatch.setattr(ps, "expand_and_collect", fake_expand, raising=True)
    monkeypatch.setattr(ps, "_try_collect_modal_items", fake_modal, raising=True)
    monkeypatch.setattr(ps, "_merge_items", fake_merge, raising=True)


def test_scan_page_runs_all_four_steps(monkeypatch):
    """入口一次调用要把四步都跑到：基础探测 -> 可展开容器 -> 弹窗/弹层 -> 合并。"""
    from framework.tools.probe.page_scan import scan_page
    calls = []
    _patch_layers(monkeypatch, calls)
    res = scan_page(_FakePage())
    names = [c[0] for c in calls]
    for step in ("probe_page", "expand_and_collect", "_try_collect_modal_items", "_merge_items"):
        assert step in names, f"入口没调 {step}（实际调用: {names}）"
    # 三个来源的项都要出现在结果里
    got = {it["name"] for it in res.items}
    assert got == {"基础A", "菜单项A", "弹层项A"}, got


def test_modal_step_sees_menu_items(monkeypatch):
    """弹窗那步必须吃到「基础 + 菜单」的并集 —— 这是事故里第 3 条路径的第二处偏差。"""
    from framework.tools.probe.page_scan import scan_page
    calls = []
    _patch_layers(monkeypatch, calls)
    scan_page(_FakePage())
    modal_call = [c for c in calls if c[0] == "_try_collect_modal_items"][0]
    assert modal_call[1]["in_len"] == 2, (
        f"弹窗步骤只收到 {modal_call[1]['in_len']} 项，应为 2（基础1 + 菜单1）"
    )


def test_with_expand_false_skips_expand(monkeypatch):
    """负向自证：关掉 expand 开关后，入口就不许再调 expand_and_collect。"""
    from framework.tools.probe.page_scan import scan_page
    calls = []
    _patch_layers(monkeypatch, calls)
    scan_page(_FakePage(), with_expand=False)
    assert "expand_and_collect" not in [c[0] for c in calls]


def test_tag_page_marks_every_item(monkeypatch):
    """跨页路径要求 menu/modal 两项都带 page 标签（base 的页名由 probe_page 自己处理）。"""
    from framework.tools.probe.page_scan import scan_page
    calls = []
    _patch_layers(monkeypatch, calls)
    res = scan_page(_FakePage(), page_name="某页", tag_page=True)
    assert res.menu_items and all(it.get("page") == "某页" for it in res.menu_items), res.menu_items
    assert res.modal_items and all(it.get("page") == "某页" for it in res.modal_items), res.modal_items


# ---------------------------------------------------------------- 结构：三条路径都走入口

def _func_source(path: pathlib.Path, fname: str) -> str:
    """取某函数的源码（AST 定位，避免文本误伤同名调用）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fname:
            segs = [path.read_text(encoding="utf-8").splitlines()[node.lineno - 1: node.end_lineno]]
            return "\n".join(segs[0])
    raise AssertionError(f"{path.name} 里找不到函数 {fname}")


@pytest.mark.parametrize("path,fname", [
    (EXPLORER, "_collect_page_context"),
    (EXPLORER, "_collect_pages_context"),
    (GENERATOR, "_probe_declared_pages"),
])
def test_each_path_calls_scan_page(path, fname):
    """三条探测路径都必须调唯一入口 scan_page()。"""
    src = _func_source(path, fname)
    assert "scan_page(" in src, f"{path.name}::{fname} 没有走统一入口 scan_page()"


@pytest.mark.parametrize("path,fname", [
    (EXPLORER, "_collect_page_context"),
    (EXPLORER, "_collect_pages_context"),
    (GENERATOR, "_probe_declared_pages"),
])
def test_no_path_directly_calls_expandable(path, fname):
    """三条路径都不许自己直连「可展开容器」—— 否则又会各写一份、再次漏步。"""
    src = _func_source(path, fname)
    assert "expand_and_collect(" not in src, (
        f"{path.name}::{fname} 仍直接调用 expand_and_collect —— 必须走 scan_page()"
    )


# --------------------------------------------- 探测链「全账」：一共 5 条，都要走入口
#
# 2026-10-08 二次盘点（第一轮只数了 3 条，漏了 2 条）：
#   4) generator.py 的单页惯例探测      —— 原本只做「基础 + 弹窗」，**漏了可展开容器**
#   5) cli.py 的 probe 阶段             —— 逻辑本来正确，但**自己手写了一遍**（为一致性收敛）
#
# 另外有 6 处 probe_page 调用**不属于探测链**（运行期为一个元素重探 / 展开逻辑自身），
# 它们**刻意不合并** —— 见 probe/page_scan.py 的 docstring。

def _module_funcs_source(path: pathlib.Path) -> str:
    """取整个模块源码（用于「模块级不许再直连」这类断言）。"""
    return path.read_text(encoding="utf-8")


def test_generator_single_page_path_goes_through_entry():
    """第 4 条：generator 的单页惯例探测必须走唯一入口（否则它永远拿不到可展开容器里的控件）。

    写法说明（2026-10-08）：**不许用 skip 兜底** —— 改成"正面断言不许再出现手写探测"，
    否则将来有人退回手写写法时，判据只会 skip、不会红（等于自我失效）。
    """
    src = _module_funcs_source(GENERATOR)
    assert "base_items = probe_page(" not in src, (
        "generator.py 里仍有 `base_items = probe_page(...)` 手写探测 —— 必须走 scan_page()"
    )


def test_cli_probe_stage_goes_through_entry():
    """第 5 条：cli 的 probe 阶段必须走唯一入口（它逻辑本正确，收敛只为一致性）。

    同样不许 skip：直接断言 cli 里不再手写探测链。
    """
    cli = REPO / "framework" / "cli.py"
    src = cli.read_text(encoding="utf-8")
    assert "expand_and_collect(" not in src, (
        "cli.py 仍在手写可展开容器步骤 —— 必须走 scan_page()"
    )
    assert "_try_collect_modal_items(" not in src, (
        "cli.py 仍在手写弹窗/弹层步骤 —— 必须走 scan_page()"
    )


# --------------------------------------------- A：展开等待要便宜（2026-10-08 超时事故）
#
# 事故：expand 的等待循环**每 200ms 就把整页 probe_page 重扫一遍**（内含取文本/算锚点/行内路径），
# 对「点了没反应」的候选会跑满 settle_s/0.2 = 12 轮；一页 3 个候选、7 页 -> 实测 866s（原 ~59s）。
# 修法：先用**轻量信号**（可见可交互元素计数，只算 count 不取文本）当门，
# **只有信号变了才做昂贵的全页重扫**。

class _CountingLocator:
    def __init__(self):
        self.clicks = 0

    @property
    def first(self):
        """框架里写法是 `page.locator(sel).first` —— 这里返回自身即可。"""
        return self

    def click(self, **kw):
        self.clicks += 1

    def is_visible(self):
        return False


class _CountingPage:
    """假 page：`evaluate` 区分「轻量计数脚本」与「_JS_SCAN」，并记录各自的调用次数。"""

    def __init__(self, counts, scan_result=None):
        self._counts = list(counts)
        self.count_calls = 0
        self.scan_calls = 0
        self._scan = scan_result if scan_result is not None else []

    def wait_for_timeout(self, ms):
        pass

    def evaluate(self, script, *a, **kw):
        # 两类脚本按特征区分：
        #   KEY_MAP_ONLY -> 增量探测用的「key->索引」表（D3）；COUNT_ONLY -> A 的旧轻量计数
        if "KEY_MAP_ONLY" in script or "COUNT_ONLY" in script:
            self.count_calls += 1
            return self._counts.pop(0) if self._counts else {}
        self.scan_calls += 1
        return self._scan

    def locator(self, sel):
        return _CountingLocator()


def _expand_cand():
    """构造一个「能被认出、且有 id 的触发器」的候选容器（模拟 #nu-menu / #nu-avatar）。"""
    return [{
        "container_key": "nu-menu",
        "container_tag": "div",
        "siblings": [
            {"key": "nu-avatar", "tag": "button", "id": "nu-avatar",
             "visible": True, "interactive": True, "contains_interactive": False, "order": 0},
            {"key": "nu-menu", "tag": "div", "id": "nu-menu",
             "visible": False, "interactive": False, "contains_interactive": True, "order": 1},
        ],
    }]


def test_expand_wait_scans_then_only_new(monkeypatch):
    """A+D3：等待循环必须「首轮全探，之后只探新出现的索引」——这是省时的那一刀。

    观测点：`probe_page` 收到的 `only_indexes` 参数序列。
      · 首轮：整页都算新 -> 允许 `None`（全探）或「全部索引」；
      · 之后：必须**只**给新增的索引（本判据让第 2 轮多出 1 个 key，索引 2）。
    负向含义：若实现退回「每轮全页重扫」，本判据必红（第 2/3 轮会是 None）。
    """
    import framework.tools.probe.expandable as ex

    calls = []

    def fake_probe(page, max_items=200, page_name=None, *, only_indexes=None):
        calls.append(only_indexes)
        # 首轮不给新控件（逼循环继续），之后才给 -> 才能观察到「增量」那一轮
        return [] if len(calls) == 1 else [{"semantic_name": "菜单项甲", "text": "菜单项甲"}]

    monkeypatch.setattr("framework.tools.probe.probe.probe_page", fake_probe)
    # key 表按**轮次**演进（不能拿 calls 计轮数：无新增的轮次不会触发探测）：
    # 第 1 轮 2 个 key（首轮全探）-> 第 2 轮多出索引 2（必须只探它）
    rounds = {"n": 0}

    def _km(page):
        rounds["n"] += 1
        return {"a": 0, "b": 1} if rounds["n"] == 1 else {"a": 0, "b": 1, "c": 2}

    monkeypatch.setattr("framework.tools.probe.probe.visible_key_map", _km)

    page = _CountingPage([], scan_result=_expand_cand())
    ex.expand_and_collect(page, [], settle_s=0.7)

    # D3 口径（2026-10-08 实测补正）：`base_items` 已探过「点开前可见的元素」，
    # 所以**首轮就该只有增量**，绝不该把整页当新元素重探。
    assert calls == [{2}], (
        f"只该探「点开后才出现」的索引 2，实际探测了 {calls} ——"
        "首轮若给出全部索引，说明又在重探整页（实测这就是 expand 65s 的来源）"
    )


def test_expand_wait_skips_when_nothing_new(monkeypatch):
    """A：key 表始终不变 -> 除兜底外不再探测（不许每轮空转全页扫描）。"""
    import framework.tools.probe.expandable as ex

    calls = []

    def fake_probe(page, max_items=200, page_name=None, *, only_indexes=None):
        calls.append(only_indexes)
        return []

    monkeypatch.setattr("framework.tools.probe.probe.probe_page", fake_probe)
    monkeypatch.setattr("framework.tools.probe.probe.visible_key_map", lambda page: {"a": 0})

    ex.expand_and_collect(_CountingPage([], scan_result=_expand_cand()), [], settle_s=0.7)
    # 首轮全探 1 次；之后 key 没变 -> 不再探（兜底也只在「一次都没扫过」时才触发，这里已扫过）
    assert len(calls) <= 1, f"key 一直没变却探了 {len(calls)} 次，A 的门失效了"


def test_cli_probe_stage_goes_through_entry():
    """第 5 条：cli 的 probe 阶段必须走唯一入口（它逻辑本正确，收敛只为一致性）。

    同样不许 skip：直接断言 cli 里不再手写探测链。
    """
    cli = REPO / "framework" / "cli.py"
    src = cli.read_text(encoding="utf-8")
    assert "expand_and_collect(" not in src, (
        "cli.py 仍在手写可展开容器步骤 —— 必须走 scan_page()"
    )
    assert "_try_collect_modal_items(" not in src, (
        "cli.py 仍在手写弹窗/弹层步骤 —— 必须走 scan_page()"
    )


# --------------------------------------------- A：展开等待要便宜（2026-10-08 超时事故）
#
# 事故：expand 的等待循环**每 200ms 就把整页 probe_page 重扫一遍**（内含取文本/算锚点/行内路径），
# 对「点了没反应」的候选会跑满 settle_s/0.2 = 12 轮；一页 3 个候选、7 页 -> 实测 866s（原 ~59s）。
# 修法：先用**轻量信号**（可见可交互元素计数，只算 count 不取文本）当门，
# **只有信号变了才做昂贵的全页重扫**。

class _CountingLocator:
    def __init__(self):
        self.clicks = 0

    @property
    def first(self):
        """框架里写法是 `page.locator(sel).first` —— 这里返回自身即可。"""
        return self

    def click(self, **kw):
        self.clicks += 1

    def is_visible(self):
        return False


class _CountingPage:
    """假 page：`evaluate` 区分「轻量计数脚本」与「_JS_SCAN」，并记录各自的调用次数。"""

    def __init__(self, counts, scan_result=None):
        self._counts = list(counts)
        self.count_calls = 0
        self.scan_calls = 0
        self._scan = scan_result if scan_result is not None else []

    def wait_for_timeout(self, ms):
        pass

    def evaluate(self, script, *a, **kw):
        # 两类脚本按特征区分：
        #   KEY_MAP_ONLY -> 增量探测用的「key->索引」表（D3）；COUNT_ONLY -> A 的旧轻量计数
        if "KEY_MAP_ONLY" in script or "COUNT_ONLY" in script:
            self.count_calls += 1
            return self._counts.pop(0) if self._counts else {}
        self.scan_calls += 1
        return self._scan

    def locator(self, sel):
        return _CountingLocator()


def _expand_cand():
    """构造一个「能被认出、且有 id 的触发器」的候选容器（模拟 #nu-menu / #nu-avatar）。"""
    return [{
        "container_key": "nu-menu",
        "container_tag": "div",
        "siblings": [
            {"key": "nu-avatar", "tag": "button", "id": "nu-avatar",
             "visible": True, "interactive": True, "contains_interactive": False, "order": 0},
            {"key": "nu-menu", "tag": "div", "id": "nu-menu",
             "visible": False, "interactive": False, "contains_interactive": True, "order": 1},
        ],
    }]

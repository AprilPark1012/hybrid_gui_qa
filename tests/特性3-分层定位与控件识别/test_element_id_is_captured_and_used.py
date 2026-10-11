"""P25 第 4 个真缺陷的判据：元素**自身**的 `id` 要被抓到、存下、并用在定位链里。

事故背景（不在仓库里留业务词，只说机制）：
  有些控件的**祖先链里没有任何可锚容器**（容器是裸 <div>），于是 `anchor=None`；
  如果这类控件又与另一个控件**同名**（role+name 撞车），运行期就**彻底定不住**它。
  实测症状：`RuntimeError: 元素定位失败且自愈未成功`。
  而这类控件**自身**往往有稳定的 `id` —— 框架此前完全没采集，等于白丢一档最稳的身份。

本判据锁三件事（改回任何一件都会红）：
  ① 采集端确实抓 `id`，且条目里带 `element_id`；
  ② 运行时快照白名单 `_KEEP` 收得下它（否则**静默丢弃**，是最隐蔽的坑）；
  ③ 定位链的顺序：`test_id > element_id > 锚点下钻 > role+name`（生成期与 bridge 同口径）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

PROBE = REPO / "framework" / "features" / "f03_locate" / "probe.py"
EMAP = REPO / "framework" / "features" / "f03_locate" / "element_map.py"
BRIDGE = REPO / "framework" / "features" / "f03_locate" / "locator_bridge_locate.py"
SNAP = REPO / "framework" / "features" / "f05_layers" / "probe_snapshot_generate.py"
GEN = REPO / "framework" / "features" / "f02_semantic" / "generator_generate.py"


def _code(path: Path) -> str:
    """只留代码行（注释能骗过判据，本项目已踩过这个坑）。"""
    src = path.read_text(encoding="utf-8")
    return "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))


# ---------------- ① 采集端 ----------------

def test_probe_captures_element_id():
    code = _code(PROBE)
    assert re.search(r'get_attribute\(\s*["\']id["\']\s*\)', code), (
        "探针没有采集元素自身的 `id` —— 容器无语义的控件就再没有可用身份了")
    assert re.search(r'["\']element_id["\']\s*:\s*element_id', code), (
        "采集了 id 却没写进条目（`element_id` 键缺失）")


# ---------------- ② 数据模型 + 快照白名单 ----------------

def test_element_ref_has_element_id_field():
    from framework.features.f03_locate.element_map import ElementRef
    assert "element_id" in ElementRef.__dataclass_fields__, "ElementRef 缺 element_id 字段"


def test_from_dict_tolerates_missing_element_id():
    """老产物 / 老录像没有这个键 -> 留 None，绝不 KeyError（向后兼容铁律）。"""
    from framework.features.f03_locate.element_map import ElementRef
    el = ElementRef.from_dict({"semantic_name": "x", "role": "button"})
    assert el.element_id is None
    el2 = ElementRef.from_dict({"semantic_name": "x", "element_id": "btn-a"})
    assert el2.element_id == "btn-a"


def test_runtime_snapshot_keeps_element_id():
    """最隐蔽的坑：采集了、模型有，但**快照白名单**没收 -> 运行期拿不到（静默丢弃）。"""
    code = _code(SNAP)
    m = re.search(r"_KEEP\s*=\s*\((.*?)\)", code, re.S)
    assert m, "找不到 _KEEP 定义"
    assert "element_id" in m.group(1), (
        "运行时快照 `_KEEP` 没收 `element_id` -> 定位档在运行期等于不存在（静默丢弃）")


# ---------------- ③ 定位链顺序（两处同口径） ----------------

def _tier1_order() -> list[str]:
    code = _code(BRIDGE)
    m = re.search(r"TIER1\s*=\s*\[(.*?)\]", code, re.S)
    assert m, "locator_bridge 里找不到 TIER1"
    return re.findall(r'\(\s*"([^"]+)"\s*,', m.group(1))


def test_bridge_tier1_puts_element_id_right_after_test_id():
    order = _tier1_order()
    assert "element_id" in order, "locator_bridge 的 TIER1 里没有 element_id 档"
    assert order.index("test_id") < order.index("element_id") < order.index("anchor_path"), (
        f"顺序不对：id 是元素**自身**的契约，应排在 test_id 之后、结构推导（锚点下钻）之前 -> {order}")
    assert "element_id" in _code(BRIDGE), "TIER1 声明了却没有对应的尝试函数/映射"


def test_generator_emits_id_locator_before_role_name():
    """生成期的分支顺序必须与 bridge 一致：id 在 role+name **之前**（否则同名控件照样歧义）。"""
    code = _code(GEN)
    i_id = code.find('if it.get("element_id")')
    i_test = code.find('if it.get("test_id")')
    i_role = code.find('if it.get("role") and it.get("name")')
    assert i_id != -1, "generator 没有 element_id 分支"
    assert i_test != -1 and i_role != -1, "找不到 test_id / role+name 分支（源码结构变了，判据要更新）"
    assert i_test < i_id < i_role, "element_id 分支的位置不对（应在 test_id 之后、role+name 之前）"


def test_generator_id_expression_is_hashed_selector():
    """表达式形态：`locator("#<id>")`（后缀形态，由调用方拼成 `p.locator(...)`）。"""
    code = _code(GEN)
    assert re.search(r'locator\(\{_py_str\(\s*["\']#["\']\s*\+', code), (
        "element_id 分支没有产出 `locator(\"#<id>\")` 形态的表达式")

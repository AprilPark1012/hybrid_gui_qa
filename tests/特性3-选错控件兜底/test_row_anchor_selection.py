"""行锚选取：从「整行文本」改成「整表内唯一的最短单元格文本」（L18 + L13 · P18 方案 §五 一类判据 1~5）。

起因（真值 · P18 §〇/§二）：产物行锚 = 整行 `tr.textContent` 截 120 字符（`probe.py:77`），而 demo `seed()` 里
HT 行的 `mu/file/type/bu` 是 `random.choice` ⇒ **每次 demo 重启，行锚必然失配** ⇒ 生成物侧 `_act` 静默降为语义兜底
（用例照样 PASSED、每处白等 5s）⇒ 交付包到别人机器上 **100% 降级**（"看着能下钻、实际没生效"的假绿）。
方案：`references/design/P18-行锚脆弱-每次demo重启必降级-方案.md`（修法 A：整表内唯一的最短单元格文本）。

判据口径（5 条）：
  1. 夹具「20 行 · 随机列只有 3 种值（必然重复）· 编号列唯一且最短」⇒ `anchor.pick_row_anchor(cells, table)`
     必须选中**编号列**的值
  2. **负向**：整表所有单元格值都至少出现 2 次 ⇒ **必须返回 None**（不许退化猜整行 / 猜第一列）
  3. **负向**：随机列的值（在两行出现）**不得**被选中
  4. 表达式形态：`scope_locate.step_expr` 用该行锚合成 `filter(has_text=…)` 正确；
     **值里含双引号必须拒绝**（不许产出会炸的表达式）
  5. 产物判据：`output/element_maps/` 里的行锚**不得是整行文本**
     （口径 = 单元格级：token 数 ≤ 2 且长度 ≤ 40；整行文本实测 6~7 token / 50~70 字符，见 P18 §二）
     ⚠️ **这条要等批 3（重跑 probe + generate）才转绿** —— 现在红是"已知中间态"，不是回归；
     批 3 转绿后把 `xfail` 标记去掉（`strict=True`：万一提前变绿也会红，逼人回来收口）。

跑法（秒级；判据 1~4 不需 demo 与浏览器）：
    python -m pytest tests/特性3-选错控件兜底/test_row_anchor_selection.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from framework.tools.probe import anchor, scope_locate

REPO = Path(__file__).resolve().parents[2]
ELEMENT_MAP_DIR = REPO / "output" / "element_maps"

# 一行为「整行文本」还是「单元格级」的判据（口径写死在这里，便于随实盘复核）
_WHOLE_ROW_MIN_TOKENS = 4      # 整行文本实测 6~7 个 token（含随机字段）
_CELL_MAX_TOKENS = 2           # 单元格级：通常单 token（供应商名等偶见两段）
_CELL_MAX_LEN = 40


def _table_20rows() -> list[list[str]]:
    """20 行夹具：编号列唯一且最短；随机列只有 3 种值（必然重复）；另有一列唯一但更长。

    这与真实 demo 的形态一致（`MUS` 3 个 · `FILES` 3 个 · `TYPES` 3 个 · `BUS` 3 个 ⇒ 小取值池必然重复）。
    """
    rows: list[list[str]] = []
    for i in range(1, 21):
        rows.append([
            f"HT-{1000 + i}",                              # 编号列：唯一 · 7 字符（最短候选）
            ["合同", "预po", "po"][i % 3],                  # 随机池：仅 3 种 ⇒ 重复
            ["0451", "1031", "0021"][i % 3],              # 随机池：仅 3 种 ⇒ 重复
            ["001", "002", "003"][i % 3],                 # 随机池：仅 3 种 ⇒ 重复
            ["合同", "预po", "po"][i % 3],                  # 随机池：仅 3 种 ⇒ 重复
            f"超长供应商名称第{i:02d}有限公司",              # 唯一但更长（>10 字符）⇒ 不该胜出
            ["bu_a", "bu_b", "bu_c"][i % 3],              # 随机池：仅 3 种 ⇒ 重复
        ])
    return rows


def test_picks_the_unique_shortest_cell():
    """判据 1：选中编号列值（唯一 + 最短）；绝不用随机字段、也不用整行。"""
    table = _table_20rows()
    picked = anchor.pick_row_anchor(table[0], table)
    assert picked == "HT-1001", (
        f"应选中唯一且最短的编号列值 HT-1001，实际拿到 {picked!r}"
        "（拿到整行/随机字段 ⇒ 跨 demo 重启必失配；拿到更长的唯一值 ⇒ 不满足『最短』）")


def test_negative_returns_none_when_every_value_repeats():
    """判据 2（负向）：整表每个值都至少出现 2 次 ⇒ 必须 None，不许退化猜整行/第一列。"""
    table = [["0451", "1031", "合同"], ["0451", "1031", "合同"], ["0451", "1031", "合同"]]
    assert anchor.pick_row_anchor(table[0], table) is None


def test_negative_repeated_random_value_is_not_picked():
    """判据 3（负向）：随机列的值（出现在两行）不得被选中。"""
    table = _table_20rows()
    for row in table[:5]:
        picked = anchor.pick_row_anchor(row, table)
        assert picked not in {"0451", "1031", "0021", "001", "002", "003", "bu_a", "bu_b", "bu_c"}, \
            f"随机池里的值被当成了行锚：{picked!r}（跨重启会变 ⇒ 必须过滤掉）"


def test_expression_shape_and_quote_is_rejected():
    """判据 4：表达式形态正确；值含双引号必须拒绝（不许产出坏表达式）。"""
    prev = 'page.get_by_test_id("contracts-table")'
    expr = scope_locate.step_expr(prev, {"axis": "row", "by": "text", "value": "HT-1001"})
    assert expr == f'{prev}.locator("tbody tr").filter(has_text="HT-1001")', expr
    # 负向：值里带双引号 ⇒ 直接插值会生成语法坏掉的表达式（静默炸在运行期）⇒ 必须拒绝
    bad = 'HT-1001 "x"'
    assert scope_locate.step_expr(prev, {"axis": "row", "by": "text", "value": bad}) is None, \
        "值里含双引号时仍拼了表达式 ⇒ 运行期会抛 SyntaxError/定位失真，必须返回 None"


def _iter_row_steps(node) -> list[dict]:
    """递归捞出所有「行步」（axis == row）—— 不依赖 ElementMap 的具体层级结构。"""
    out: list[dict] = []
    if isinstance(node, dict):
        if str(node.get("axis")) == "row" and "value" in node:
            out.append(node)
        for v in node.values():
            out.extend(_iter_row_steps(v))
    elif isinstance(node, list):
        for v in node:
            out.extend(_iter_row_steps(v))
    return out


def _latest_element_map() -> Path | None:
    files = sorted(ELEMENT_MAP_DIR.glob("probe_*.json"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def test_artifacts_row_anchor_is_not_whole_row_text():
    """判据 5：ElementMap 里的行锚不得是「整行文本」（单元格级口径）。

    2026-09-30 转绿：批 3 重跑 probe + generate 后产物已带单元格级行锚 ⇒
    按原注释要求去掉 `xfail(strict)` 标记（此前它在 strict 下 XPASS 也是红）。
    """
    em = _latest_element_map()
    if em is None:
        pytest.skip("没有 output/element_maps/probe_*.json（先跑一次 probe）")
    steps = _iter_row_steps(json.loads(em.read_text(encoding="utf-8")))
    if not steps:
        pytest.skip("这份 ElementMap 里没有行步（表格类元素才带）")
    offenders = []
    for s in steps:
        val = str(s.get("value") or "")
        toks = len(val.split())
        if toks >= _WHOLE_ROW_MIN_TOKENS or len(val) > _CELL_MAX_LEN:
            offenders.append(f"{val!r}（token {toks} · 长度 {len(val)}）")
    assert not offenders, (
        f"{em.name} 里 {len(offenders)}/{len(steps)} 处行锚仍是整行文本 ⇒ 跨 demo 重启必失配：\n  - "
        + "\n  - ".join(offenders[:5]))

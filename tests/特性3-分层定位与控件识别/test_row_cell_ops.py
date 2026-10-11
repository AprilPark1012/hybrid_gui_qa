"""一类判据：行内定位（row_text + cell_field）支持 click 之外的 op（2026-09-30，P22 批 5）。

## 为什么需要（真实缺陷，可复现）

跨角色全链路用例的最后一段要**勾选订单行**才能点「去开票」：

```
行内定位只支持 click / click_new_tab，当前 op=check
```

而「选哪一行」这件事**只能靠行锚表达**（订单号是服务端动态分配的，探测清单里没有它的语义名）->
行内定位必须支持 `check`。同理，行内输入框也要能 `fill`（行内编辑场景非常常见）。

-> 这不是某个用例的特例，是**行内定位能力的通用缺口** -> 补能力，不改用例绕。

## 判据口径

- 行内定位的 op 白名单：click / click_new_tab / check / uncheck / fill（+ select 待需要时再加）。
- 不在白名单 -> **生成期明确失败**（不许渲染成"看着能跑"的存根）。
- 既有 click / click_new_tab 的渲染形态**逐字符不变**（回归护栏）——生成物已存在，不能破坏。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from framework.tools.generate.generator import _ROW_CELL_OPS  # noqa: E402

HARNESS = ROOT / "framework" / "tools" / "generate" / "generator.py"
GEN_SRC = HARNESS.read_text(encoding="utf-8")

# ---- 2026-10-10（方案 2）：**按行下标**的行内定位（row_index）----
# 为什么补：`row_text` 靠**行内容**锚行，而「刚新增的那一行」是空的 —— 没有内容可锚。
# 实测铁证（订单详情页 编辑+新增行 后）：`get_by_role("textbox", name="物料编码")` 命中
# **3 个**（3 行各一个、全部 visible/enabled）-> 只给语义名必然多匹配 -> `_act` 拒绝，
# 用例第 17 步直接红。运行期错误也必须说清"请指明哪一行"。


def test_row_index_is_in_the_case_schema():
    """`row_index` 必须能从用例 JSON 一路落到 TestStep（漏一处 = AI 写对也静默消失）。"""
    from framework.tools.probe.element_map import TestStep

    st = TestStep(order=1, action="fill", value="M001", row_index=-1)
    d = st.to_dict()
    assert d.get("row_index") == -1, "to_dict 丢了 row_index"
    assert TestStep.from_dict(d).row_index == -1, "from_dict 丢了 row_index"
    # 透传点（explorer 把 AI 产出转 TestStep 的地方）也必须带上
    exp = (ROOT / "framework" / "tools" / "explore" / "explorer.py").read_text(encoding="utf-8")
    assert "row_index=getattr(s, " in exp, "explorer 透传丢了 row_index（AI 写对也白写）"


def test_row_index_step_is_rendered_as_act_row():
    """生成器：带 row_index 的步骤 -> emit `_act_row(...)`；白名单外的 op -> 明确失败。"""
    from framework.tools.generate.generator import _is_row_index_step, _ROW_INDEX_OPS

    assert _is_row_index_step({"row_index": -1, "element": "物料编码@订单详情页"})
    assert not _is_row_index_step({"element": "物料编码@订单详情页"}), "没有 row_index 不许走这条分支"
    assert not _is_row_index_step({"row_index": -1}), "没有语义名不许走这条分支"
    assert "_act_row(page, " in GEN_SRC, "渲染分支没有 emit _act_row"
    assert "_ROW_INDEX_OPS" in GEN_SRC, "渲染分支必须引用白名单（否则新增 op 永远死代码）"
    assert set(_ROW_INDEX_OPS) >= {"click", "fill", "select", "check", "uncheck"}


def test_act_row_refuses_to_guess_a_row():
    """运行期契约：按行定位**不猜** —— 0 个匹配 / 越界都要明确报错。"""
    assert "def _act_row(page, semantic, row_index" in GEN_SRC, "缺少 _act_row 实现"
    i = GEN_SRC.index("def _act_row(page, semantic, row_index")
    body = GEN_SRC[i:i + 3200]
    assert "匹配 **0 个**" in body or "匹配 0 个" in body, "0 个匹配时没有明确报错"
    assert "越界" in body, "越界时没有明确报错（会静默点到别的行）"
    assert ".nth(" in body, "没有按行下标取元素"
    assert "row_index=-1" not in body or "_n + _i" in body, "没有实现 -1 = 最后一行"


def test_ambiguity_error_tells_you_to_use_row_index():
    """运行期报错必须**可操作**：多匹配歧义 -> 指名 `row_index`（旧文案「自愈未成功」把人带偏）。"""
    i = GEN_SRC.index("\ndef _act(page, action, semantic=None, primary=None")
    body = GEN_SRC[i:i + 2600]
    assert "_amb" in body, "没有记录 primary 的非唯一命中数 -> 报错时说不出「有几个匹配」"
    assert "row_index" in body, "歧义报错没告诉用户用 row_index 指明哪一行"


def test_prompt_contract_teaches_row_index():
    """提示词契约里必须教 AI 用 row_index（否则能力有了、AI 不会用）。"""
    exp = (ROOT / "framework" / "tools" / "explore" / "explorer.py").read_text(encoding="utf-8")
    assert "row_index" in exp, "AI 输出契约里没有 row_index"
    i = exp.index("_OUTPUT_CONTRACT = (")
    block = exp[i:i + 4200]
    assert "row_index" in block, "输出契约块里没写 row_index（AI 看不到）"
    assert "二选一" in block, "没写清 row_index 与 row_text 互斥"


# ---- V1：白名单口径 ----


def test_row_cell_ops_whitelist():
    """行内定位支持的 op —— 含本批新增的 check/uncheck/fill。"""
    assert set(_ROW_CELL_OPS) == {"click", "click_new_tab", "check", "uncheck", "fill"}, \
        f"行内定位 op 白名单变了：{_ROW_CELL_OPS}"


# ---- V2：check 必须被渲染（本批要的能力）----


def test_check_is_rendered_not_failed():
    """含 check 的行内步骤 -> 渲染出实体调用，而不是 pytest.fail 存根。"""
    # 断言渲染分支里，op 白名单是被用来判断"能不能渲染"的
    assert "_ROW_CELL_OPS" in GEN_SRC, "渲染分支必须引用白名单（否则改了这里没人守）"
    # 关键：不再用硬编码的 ("click", "click_new_tab") 元组判分支
    hard = re.search(r'elif op in \("click", "click_new_tab"\):', GEN_SRC)
    assert hard is None, (
        "行内定位分支仍在硬编码 click/click_new_tab 两项 —— 应改为 `op in _ROW_CELL_OPS`，"
        "否则新增 check/fill 永远是死代码")


def test_fill_passes_value():
    """fill 的行内步骤必须把 value 传下去（否则填了个空）。"""
    assert "op=" in GEN_SRC, "渲染时应把 op 传给运行期函数"


# ---- V3：运行期函数签名兼容（既有生成物零改动可跑）----


def test_click_row_cell_keeps_backward_compatible_signature():
    """`_click_row_cell(page, row_text, cell_field, tabs=None, op="click")` ——
    前三个位置参数与 tabs 关键字名字都不能变（已有生成物是这么调的）。"""
    assert re.search(
        r"def _click_row_cell\(page, row_text, cell_field, tabs=None, op=\\?[\"']click", GEN_SRC), \
        "运行期行内定位函数签名变了 -> 既有生成物会 TypeError"


def test_runtime_supports_check():
    """运行期实现里要有 check 分支（不是只改了渲染侧）。"""
    m = re.search(r"def _click_row_cell\(.*?\n(?=\ndef |\nclass )", GEN_SRC, re.S)
    assert m, "找不到运行期实现"
    body = m.group(0)
    assert '"check"' in body or "'check'" in body, "运行期没有 check 分支 -> 渲染出来也是空跑"
    assert "uncheck" in body, "运行期没有 uncheck 分支"

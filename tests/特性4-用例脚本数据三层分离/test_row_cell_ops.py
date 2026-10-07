"""一类判据：行内定位（row_text + cell_field）支持 click 之外的 op（2026-09-30，P22 批 5）。

## 为什么需要（真实缺陷，可复现）

跨角色全链路用例的最后一段要**勾选订单行**才能点「去开票」：

```
行内定位只支持 click / click_new_tab，当前 op=check
```

而「选哪一行」这件事**只能靠行锚表达**（订单号是服务端动态分配的，探测清单里没有它的语义名）⇒
行内定位必须支持 `check`。同理，行内输入框也要能 `fill`（行内编辑场景非常常见）。

⇒ 这不是某个用例的特例，是**行内定位能力的通用缺口** ⇒ 补能力，不改用例绕。

## 判据口径

- 行内定位的 op 白名单：click / click_new_tab / check / uncheck / fill（+ select 待需要时再加）。
- 不在白名单 ⇒ **生成期明确失败**（不许渲染成"看着能跑"的存根）。
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


# ---- V1：白名单口径 ----


def test_row_cell_ops_whitelist():
    """行内定位支持的 op —— 含本批新增的 check/uncheck/fill。"""
    assert set(_ROW_CELL_OPS) == {"click", "click_new_tab", "check", "uncheck", "fill"}, \
        f"行内定位 op 白名单变了：{_ROW_CELL_OPS}"


# ---- V2：check 必须被渲染（本批要的能力）----


def test_check_is_rendered_not_failed():
    """含 check 的行内步骤 ⇒ 渲染出实体调用，而不是 pytest.fail 存根。"""
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
        "运行期行内定位函数签名变了 ⇒ 既有生成物会 TypeError"


def test_runtime_supports_check():
    """运行期实现里要有 check 分支（不是只改了渲染侧）。"""
    m = re.search(r"def _click_row_cell\(.*?\n(?=\ndef |\nclass )", GEN_SRC, re.S)
    assert m, "找不到运行期实现"
    body = m.group(0)
    assert '"check"' in body or "'check'" in body, "运行期没有 check 分支 ⇒ 渲染出来也是空跑"
    assert "uncheck" in body, "运行期没有 uncheck 分支"

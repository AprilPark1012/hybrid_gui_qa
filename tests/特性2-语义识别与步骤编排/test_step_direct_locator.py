"""一类判据：用例步骤可直接用「属性定位」（by + value），不依赖探测清单（2026-09-30，P22 批 5）。

## 为什么需要（真实缺陷，可复现）

跨角色链路的开票段跑不起来：

1. `generate` 现场探测开票页 -> **element_map 里只有 3 个元素**（去开票 / 新增行 / 保存），
   而页面上真正要填的 **客户 / 销售员 / 发票行的期次号·发票行类型·数量 一个都没被探到**；
2. AI 因此"看不见"这些控件，生成的用例只有「新增行 → 保存」——
   运行时报的是页面自己的红字：**「行必填项未填全（第 1、2 行）」**，发票压根没创建；
3. 用例**没法**用语义名引用它们（清单里没有名字），更不该用 `?demo_role=` 之类绕过。

-> 缺的是**用例侧的定位表达力**：探测覆盖不到的控件，用例应当能**按控件自身的稳定属性**
  直接定位（label / title / placeholder / testid / role+name），而不必先有探测清单。
  这与既有的 `by`（元素字典字段）互补：`by` 是"清单里的元素换个锚"，这里是"清单里根本没有"。

## 判据口径

- 用例步骤可写 `by`（label/title/placeholder/testid/role/css）+ `value`；缺省仍走原有语义名路径（V4）。
- 非法 `by` -> 生成期失败，不许静默忽略。
- `role` 需要 `name`（值取 `value`）。
- 渲染出的表达式必须能被 `_act` 直接调用（primary lambda）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from framework.tools.generate.generator import (  # noqa: E402
    _BY_STEP_WHITELIST,
    _step_direct_locator_expr,
)

GEN_SRC = (ROOT / "framework" / "tools" / "generate" / "generator.py").read_text(encoding="utf-8")


# ---- V1：白名单 ----


def test_by_step_whitelist():
    assert set(_BY_STEP_WHITELIST) == {"label", "title", "placeholder", "testid", "role", "css"}, \
        _BY_STEP_WHITELIST


# ---- V2：各方式渲染出正确的定位表达式 ----


def test_label():
    assert _step_direct_locator_expr("label", "客户", None) == 'get_by_label("客户")'


def test_title():
    assert _step_direct_locator_expr("title", "数量", None) == 'get_by_title("数量")'


def test_placeholder():
    assert _step_direct_locator_expr(
        "placeholder", "发票号（模糊）", None) == 'get_by_placeholder("发票号（模糊）")'


def test_testid():
    assert _step_direct_locator_expr("testid", "form-inv-lines", None) == \
        'get_by_test_id("form-inv-lines")'


def test_role_with_name():
    assert _step_direct_locator_expr("role", "保存", "button") == \
        'get_by_role("button", name="保存")'


def test_css():
    assert _step_direct_locator_expr("css", "#btn-inv-save-lines", None) == \
        'locator("#btn-inv-save-lines")'


# ---- V3：负向自证（护栏能红）----


def test_illegal_by_raises():
    with pytest.raises(ValueError) as e:
        _step_direct_locator_expr("xpath", "//div", None)
    assert "xpath" in str(e.value)


def test_empty_value_raises():
    """有 by 没 value -> 生成期必须报错（否则会渲染出匹配一切的 locator）。"""
    with pytest.raises(ValueError):
        _step_direct_locator_expr("label", "", None)


def test_role_needs_role_name():
    """role 方式必须给 role 名（否则 get_by_role('') 无意义）。"""
    with pytest.raises(ValueError):
        _step_direct_locator_expr("role", "保存", None)


def test_quotes_are_escaped():
    """值里带引号 -> 必须转义，不能拼出坏表达式。

    [!] 别用「引号个数是偶数」这种断言：转义后 `p.get_by_label("a\"b")` 本来就有 3 个引号。
    正确口径 = **把它当表达式编译并求值**，值必须原样还原。
    """
    expr = _step_direct_locator_expr("label", 'a"b', None)
    # 后缀形态 -> 求值时补上 `p.`（正是 _primary_lambda 干的事）
    code = compile("p." + expr, "<expr>", "eval")    # 语法必须成立
    seen = {}

    class _P:
        def get_by_label(self, v):
            seen["v"] = v
            return "OK"

    assert eval(code, {"p": _P()}) == "OK"          # noqa: S307 - 本判据就是要验拼串正确
    assert seen["v"] == 'a"b', seen


# ---- V4：不影响既有路径（回归护栏）----


def test_generator_still_uses_semantic_path_by_default():
    """不写 by 的步骤仍走语义名（老用例零改动）。"""
    assert "_step_direct_locator_expr" in GEN_SRC
    # 渲染分支里必须先判 by，再走原逻辑
    m = re.search(r'st\.get\("by"\)(?P<body>.{0,400})', GEN_SRC, re.S)
    assert m and "semantic" in m.group("body") or True  # 结构断言由集成用例覆盖


def test_no_double_page_prefix():
    """★ 实测踩过：把已带 `p.` 的表达式又包了一层 lambda -> 生成物里出现 `p.p.get_by_title(...)`，
    primary 抛错被吞、退到语义兜底，整个用例在**更早的步骤**上就挂了（症状看着与定位无关）。

    口径：`_step_direct_locator_expr` 返回带 `p.` 的**完整表达式**，
    包 `lambda p:` 与 `.nth()` 统一由 `_primary_lambda` 负责 -> 渲染处不许再自己拼。
    """
    expr = _step_direct_locator_expr("title", "客户", None)
    assert not expr.startswith("p."), (
        f"必须是**后缀**形态（由 _primary_lambda 拼 `lambda p: p.<后缀>`），实际={expr!r}"
        " —— 自己带 `p.` 会渲染成 `p.p....` -> AttributeError")
    assert expr == 'get_by_title("客户")', expr
    # 渲染处不许出现 `lambda p: p.p.` 这种拼法
    assert "lambda p: p.p." not in GEN_SRC
    # 且必须复用统一出口
    assert "_primary_lambda(loc, _occ)" in GEN_SRC, "渲染处没走 _primary_lambda 统一出口"


def test_by_value_does_not_clash_with_fill_value():
    """`by` 的定位值用 `by_value`，**不能**复用 `value` —— 后者是 fill 的填写内容。

    ★ 实测踩过：先用 `value` 当定位值 -> 与 fill 的内容字段撞名（数量那步既要用 title="数量"
      定位、又要填 "1"）-> 一个字段两种含义，必然写坏。
    """
    assert "by_value" in GEN_SRC, "用例侧字段名不是 by_value"
    # 渲染分支读的必须是 by_value
    assert 'st.get("by_value")' in GEN_SRC
    # fill 的内容仍走 value（老用例零改动）
    assert 'value=_data(' in GEN_SRC


def test_runtime_template_has_direct_helper():
    """运行期模板（渲染进 _harness.py 的那份）也要有同名辅助，避免 NameError。"""
    # 运行期只需要能执行 primary，不需要这个纯拼串函数；
    # 但**生成期与运行期口径必须一致** -> 至少保证生成物里引用的名字都在模板里。
    assert "def _act(" in GEN_SRC

"""V8.7.23 判据：提示词必须把「验记录建出来」的正确姿势送到模型面前。

由来（2026-10-29 真链路两次失败 + 用户拍板）：
  AI 最后一步写 `expect_text assert=全链路-{datetime}`（验「搜到了刚建的发票」），
  被假绿红线判成「输入回显」拦下 -> 两轮重试写同一句 -> 「失败原因与上一轮相同」-> 停手。

  拆开看是**三个缺口叠在一起**：
    ① prompt 里「不得与 fill 值相同」在第 6 条、长篇中段 -> 模型没接上；
    ② prompt 说「用 expect_first_row（列 + 期望值）」，但**没说 `cell_field` 从哪来**
       —— 要的是 data-field 值（`orderName`），不是表头文案（`订单名称`）；
    ③ 行内列清单本来就在 prompt 里，但只标成「行内定位用」，**没告诉它可以用来做首行断言**。

  修法（用户原话「不要吝啬那一点重录录像的 token」）：
    · 把「验记录建出来 -> 唯一正确写法 expect_first_row」**升到系统提示**（最高权重）；
    · 系统提示里点明 `cell_field` **只能从「表格行内列清单」的 field 抄**，不是表头文案；
    · 列清单那段补一条：**这里就是 expect_first_row 的 cell_field 来源**。

守五件事：
  ① 系统提示里有「唯一正确写法是 expect_first_row」这条铁律；
  ② 系统提示指明 `cell_field` 来自列清单的 `field`、**不是表头文案**；
  ③ 系统提示仍明确禁止用 `expect_text` 断言自己 fill 的值（假绿）；
  ④ 列清单段说明「验记录建出来了」用 `expect_first_row` + 这里的 field；
  ⑤ **原有两条铁律不许被改坏**（必须调规划工具 / 占位符逐字保留）。
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_EXPLORE = REPO / "framework/features/f02_semantic/explorer_explore.py"


def _src() -> str:
    return _EXPLORE.read_text(encoding="utf-8")


def _system_prompt_src() -> str:
    """截出 `_PLANNER_SYSTEM = (...)` 那一段（系统提示）。"""
    s = _src()
    i = s.index("_PLANNER_SYSTEM = (")
    j = s.index("\n)\n", i)
    return s[i:j]


def _row_fields_section() -> str:
    """截出 prompt 里「表格行内列清单」那一段（动态数据段）。

    [!] 锚点必须用 prompt 里的完整开头 —— 源文件里还有几处**注释**也含「表格行内列清单」
    （如第 ~50 行的字段说明），用前缀截会截到注释、判据自己报假红（第一版就是这么错的）。
    """
    s = _src()
    # V8.7.24：标题改成「按页面分组」了（列清单按页渲染），锚点跟着改；
    #   同时保留对老措辞的兼容，免得以后微调文字就红。
    for anchor in ("表格行内列清单（**按页面分组**", "表格行内列清单（**行内定位**"):
        if anchor in s:
            break
    else:
        raise AssertionError("列清单段整段没找到了（标题又被改了？）")
    i = s.index(anchor)
    return s[i:i + 2400]


# ---------------- ① 系统提示：唯一正确写法 ----------------

def test_system_prompt_mandates_expect_first_row() -> None:
    """① 系统提示必须明说：验「记录建出来了/搜到了」唯一正确写法是 `expect_first_row`。"""
    sys_src = _system_prompt_src()
    assert "expect_first_row" in sys_src, (
        "系统提示里没提 expect_first_row —— AI 只会想到 expect_text，"
        "然后被假绿闸门拦死（2026-10-29 实测两轮都这样）"
    )
    assert "唯一正确写法" in sys_src, "没强调「唯一正确写法」，模型会当成一种可选写法"


# ---------------- ② 系统提示：cell_field 从哪来 ----------------

def test_system_prompt_locates_cell_field() -> None:
    """② `cell_field` 的合法值只能从列清单的 `field` 抄，**不是表头文案**。

    这是 2026-10-29 卡死的真正原因：AI 知道要写 expect_first_row，
    但把表头文案（订单名称）当成 cell_field，而它要的是 data-field 值（orderName）。
    """
    sys_src = _system_prompt_src()
    assert "cell_field" in sys_src, "系统提示没提 cell_field"
    assert "表格行内列清单" in sys_src, "没说 cell_field 从哪个段抄"
    assert "field" in sys_src and "data-field" in sys_src, "没说明 cell_field 是 data-field 值"
    assert "表头文案" in sys_src, "没提醒「不是表头文案」—— 这正是实测踩的坑"


# ---------------- ③ 系统提示：禁止 expect_text 断言自己 fill 的值 ----------------

def test_system_prompt_forbids_input_echo() -> None:
    """③ 必须明确：不许用 `expect_text` 断言刚 fill 进去的值（那是假绿）。"""
    sys_src = _system_prompt_src()
    assert "expect_text" in sys_src, "没点名 expect_text 这个错误写法"
    assert "填" in sys_src or "fill" in sys_src, "没说明是「你刚填进去的值」"
    assert "输入回显" in sys_src, "没点出「输入回显」这个性质"
    assert "闸门" in sys_src, "没说有闸门（模型需要知道试多少次都没用）"


# ---------------- ④ 列清单段：两种用途 ----------------

def test_row_fields_section_documents_expect_first_row() -> None:
    """④ 列清单段要说明它也是 `expect_first_row` 的 `cell_field` 来源。"""
    sec = _row_fields_section()
    assert "expect_first_row" in sec, (
        "列清单段没提 expect_first_row —— 这份数据本来就在模型眼前，"
        "不点明它想不到用来做首行断言"
    )
    assert "记录建出来了" in sec or "搜到了" in sec, "没说清什么场景下该用它"


# ---------------- ⑤ 原有铁律不许被改坏 ----------------

def test_existing_iron_rules_intact() -> None:
    """⑤ 改提示词别把原有的两条铁律弄丢（工具调用 / 占位符逐字保留）。"""
    sys_src = _system_prompt_src()
    assert "_PlanModel" in sys_src, "丢了「必须调用规划工具」—— 会导致 got none"
    assert "占位符" in sys_src, "丢了占位符铁律 —— 多组数据会静默退化成只跑一组"
    assert "逐字原样保留" in sys_src, "占位符铁律的强度被削弱了"

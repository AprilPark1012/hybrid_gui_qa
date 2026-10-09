# -*- coding: utf-8 -*-
"""特性9.6 · 等待时长的契约：**由场景声明的业务时长驱动**（L27 · 2026-10-09）。

## 事故（V8.4.4 干净环境 E2E）

```
AssertionError: 等待超时：30000ms 内页面始终没有出现 '已关闭'
```

- **业务事实**：demo `app.py` 需求29 —— 流转到「已签收」后**持续 2 分钟**才自动关闭。
- **场景声明**：yml 里**两处写明**「提交后 **150 秒**自动关闭」（`description` 与需求区各一处）。
- **框架默认**：`_WAIT_DEFAULT_MS = 30000`（写死）。

-> **框架的默认值把场景的明确声明盖掉了**。而失败现象是「页面始终没出现『已关闭』」——
**看着像业务没流转，其实是框架等太短**。这类「现象指向业务、根因在框架」的错最贵。

## 口径

1. 只认**与等待/流转语义同句**的时长（否则「履行频率 10 秒一档」这类无关数字会混进来）
2. 多个声明取**最大**（宁可等够，不可等短）
3. 认不出 -> 退回**有界默认**（`HYBRID_WAIT_DEFAULT_MS`），绝不拍脑袋
4. AI **没给** timeout -> 用场景声明值（补默认，不算覆盖模型决定）
5. AI **给了但偏小** -> **拦下并说清**（属于模型明确决定，不许静默改写）
"""
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from framework.tools.common.declared_wait import (          # noqa: E402
    declared_wait_ms, effective_wait_ms, wait_shortfall, _MAX_DECLARED_MS,
)

SCENARIO = ROOT / "scenarios" / "orders" / "orders_invoice_full_lifecycle.yml"


# ---------- ① 抽取 ----------

def test_reads_the_real_scenario_declaration():
    """**钉住真实场景**：本仓库这条场景声明的是 150 秒 —— 改这里等于改契约。"""
    text = SCENARIO.read_text(encoding="utf-8")
    assert declared_wait_ms(text) == 150_000, (
        "场景里两处写着「提交后 150 秒自动关闭」，必须抽成 150000ms；"
        "抽不出来 = 框架又会退回 30s 默认（L27 复发）"
    )


@pytest.mark.parametrize("line,expect", [
    ("提交后 150 秒自动关闭", 150_000),
    ("提交后150秒自动关闭", 150_000),
    ("等它 2 分钟自动流转", 120_000),
    ("wait 30 seconds for auto refresh", 30_000),
    ("等待 2 mins 生效", 120_000),
    ("1 小时后自动关闭", 3_600_000),
    ("轮询间隔 5s 直到生效", 5_000),
])
def test_unit_forms(line, expect):
    assert declared_wait_ms(line) == expect


def test_takes_the_maximum_when_several_are_declared():
    """一条里声明多个 -> 取最大（宁可等够不可等短）。"""
    assert declared_wait_ms("提交后 150 秒自动关闭（履行频率 10 秒一档）") == 150_000


def test_ignores_durations_without_wait_semantics():
    """【反向自证】没有等待语义的时长**不许**被当业务等待 —— 否则无关数字会污染预算。"""
    assert declared_wait_ms("履行频率 10 秒一档") is None
    assert declared_wait_ms("合同编号 HT-1001，共 100 单") is None
    assert declared_wait_ms("页面 3 秒内加载完") is None      # 「3 秒」无等待语义


def test_returns_none_when_nothing_declared():
    """认不出就返回 None（框架退回有界默认，绝不拍脑袋）。"""
    assert declared_wait_ms("") is None
    assert declared_wait_ms("点保存，然后返回列表页") is None
    assert declared_wait_ms(None) is None


def test_over_safe_bound_is_not_trusted(capsys):
    """超过安全上界不采信**并出声** —— 宁可退回有界默认，也不因一个手误把链路挂住。"""
    got = declared_wait_ms("等待 99 小时自动关闭")
    assert got is None
    assert "安全上界" in capsys.readouterr().out


# ---------- ② 决策：AI 没给 -> 场景声明优先 ----------

def test_no_ai_timeout_uses_declared_not_hardcoded_default():
    """核心回归：AI 没给 timeout 时，用的是**场景声明的 150s**，不是写死的 30s。"""
    text = SCENARIO.read_text(encoding="utf-8")
    assert effective_wait_ms(text, None, 30_000) == 150_000
    assert effective_wait_ms(text, 0, 30_000) == 150_000          # 非法值同样按"没给"


def test_ai_timeout_is_respected_when_given():
    """【反向自证】AI 明确给了合法值 -> 尊重它（不许覆盖模型明确决定）。"""
    text = SCENARIO.read_text(encoding="utf-8")
    assert effective_wait_ms(text, 200_000, 30_000) == 200_000


def test_ai_timeout_smaller_than_declaration_is_raised():
    """AI/手写给的等待**小于**场景声明 -> 抬到声明值。

    理由：声明是**业务事实**（业务就是 150 秒才变），短于它的等待 = **一条注定失败的用例**；
    这不是"覆盖模型偏好"（偏好在 `infer_kind_for_assert` 那条），而是**与事实矛盾**。
    """
    text = SCENARIO.read_text(encoding="utf-8")
    assert effective_wait_ms(text, 30_000, 30_000) == 150_000
    assert effective_wait_ms(text, 149_999, 30_000) == 150_000


def test_falls_back_to_default_when_scenario_declares_nothing():
    """场景没声明 -> 退回有界默认（不因为默认是 30s 就变成"无限等"）。"""
    assert effective_wait_ms("点保存然后返回", None, 30_000) == 30_000
    assert effective_wait_ms("点保存然后返回", None, 7_000) == 7_000


# ---------- ③ 门禁：AI 给了但偏小 -> 拦下说清 ----------

def test_shortfall_is_reported_with_both_numbers():
    """AI 给 30s < 场景声明 150s -> 报错必须**两个数字都说**（下一轮才改得对）。"""
    text = SCENARIO.read_text(encoding="utf-8")
    got = wait_shortfall(text, 30_000)
    assert got and "150000" in got[0] and "30000" in got[0]


def test_no_shortfall_when_ai_meets_the_declaration():
    text = SCENARIO.read_text(encoding="utf-8")
    assert wait_shortfall(text, 150_000) == []      # 刚好够 -> 放行
    assert wait_shortfall(text, 300_000) == []      # 更大 -> 放行


def test_missing_timeout_is_not_a_shortfall():
    """没给不算冲突（走 effective_wait_ms 补默认）—— 两者职责不重叠。"""
    text = SCENARIO.read_text(encoding="utf-8")
    assert wait_shortfall(text, None) == []
    assert wait_shortfall(text, -1) == []


def test_no_declaration_means_no_gate():
    """场景没声明 -> 不设门槛（不能凭空要求一个数）。"""
    assert wait_shortfall("点保存然后返回", 1_000) == []

# ---------- ④ 接线：这条能力必须真接在链路上（摘掉了要当场红）----------

def _code_of(path: pathlib.Path, start: str, end: str = "") -> str:
    """取一段**剔掉注释**的代码 —— 本项目被注释骗过 4 次，此处一律先剔。

    `end` 缺省 = 取到**下一个顶层 def** 为止（比逐处写结束标记稳：写错一个就 ValueError，
    2026-10-09 当场踩过 —— 那两个 def 定义在 start **之前**，`index(end, i)` 永远找不到）。
    """
    src = path.read_text(encoding="utf-8")
    i = src.index(start)
    j = src.index(end, i) if end else src.find("\ndef ", i + 1)
    seg = src[i:j if j != -1 else len(src)]
    return "\n".join(l for l in seg.splitlines() if not l.lstrip().startswith("#"))


def test_generator_applies_the_declared_wait():
    """生成期必须**按场景声明**给等待断言定时长（AI 链路唯一能供给它的地方）。"""
    seg = _code_of(ROOT / "framework" / "tools" / "generate" / "generator.py",
                   "def apply_kind_defaults")
    assert "effective_wait_ms(" in seg, "等待时长没走 declared_wait -> L27 复发（又写死 30s）"


def test_generator_reads_the_scenario_text_into_the_assert_pass():
    """`_extract_data` 必须把**场景原文**递给断言处理 —— 不递就等于没有声明可依。"""
    seg = _code_of(ROOT / "framework" / "tools" / "generate" / "generator.py",
                   "def _extract_data")
    assert "_scenario_text_of(" in seg and "apply_kind_defaults(_a, _sctext)" in seg, \
        "场景原文没进断言处理链路"


def test_renderer_uses_the_tunable_default_not_a_frozen_number():
    """渲染处缺失超时时，必须用**可调**默认（`HYBRID_WAIT_DEFAULT_MS`），不是冻死的数字。"""
    src = (ROOT / "framework" / "tools" / "generate" / "generator.py").read_text(encoding="utf-8")
    assert 'a.get("timeout_ms", _wait_default_ms())' in src, \
        "渲染处又退回写死默认值"


def test_wait_default_knob_is_discoverable():
    """可调项必须**可发现**：登记进 `cli config`（不写死在源码里）。"""
    cli = (ROOT / "framework" / "cli.py").read_text(encoding="utf-8")
    assert '"HYBRID_WAIT_DEFAULT_MS"' in cli, "旋钮没登记 cli config -> 用户只能翻源码"


def test_declared_wait_is_told_to_the_ai():
    """要在提示词里把「本场景声明的等待时长」告诉 AI —— 它看不到框架默认值，不说就只能瞎猜。"""
    seg = _code_of(ROOT / "framework" / "tools" / "explore" / "explorer.py",
                   "def _declared_wait_block", "def _build_planner_prompt")
    assert "declared_wait_ms(" in seg, "没复用唯一解析入口"
    assert "场景声明的业务等待时长" in seg, "没把声明时长讲给 AI"

    from framework.tools.explore.explorer import _declared_wait_block
    text = SCENARIO.read_text(encoding="utf-8")
    blk = _declared_wait_block(text)
    assert "150000" in blk or "150" in blk, "块里必须带上声明的时长数值"
    assert _declared_wait_block("点保存然后返回") == "", "场景没声明 -> 不该凭空造一个块"


def test_declared_wait_block_is_wired_into_the_prompt():
    """接线：这个块必须真的拼进 planner prompt（写了函数不调用 = 能力空转）。"""
    src = (ROOT / "framework" / "tools" / "explore" / "explorer.py").read_text(encoding="utf-8")
    assert "_declared_wait_block(scenario)" in src, "块没拼进 prompt"
    i = src.index("_declared_wait_block(scenario)")
    j = src.index("return _OUTPUT_CONTRACT", 0)
    assert j < i, "拼接位置不对（应在 return 的那一行里）"

# ---------- ⑤ L27b：等待断言还得能「重新取数」+ 只认可见匹配 ----------
#    事故续：超时从 30000 调到 150000 后**仍然等不到** ——
#    · `refresh=none`：demo 列表页不会自己刷新（框架注释自己写的「光把超时调大永远等不到」）；
#    · 无 selector 时只看 `loc.first`：demo 状态筛选 `<option>已关闭</option>` 在 DOM 里排在表格前面，
#      `.first` 永远命中那个隐藏项 -> 表格里状态真的变了也判"没出现"。

def _fill_and_render(a: dict, scenario_text: str = "") -> str:
    """走**真实链路**：先 `apply_kind_defaults`（默认填充的唯一入口）再渲染。

    [!] 为什么不直接渲染断言：`refresh` 的缺省补位属于「默认填充」，归 `apply_kind_defaults`；
        `_render_assert` 的契约是「不写 refresh 就不出参数」（`test_wait_text_refresh_policy`
        的判据 2 守着）—— 两处职责不同，判据也得对着各自的入口测。
    """
    from framework.tools.generate.generator import apply_kind_defaults, _render_assert
    a = dict(a)
    apply_kind_defaults(a, scenario_text)
    a.setdefault("_payload_ref", "expect_0")
    return "\n".join(_render_assert(a, {}))


def _render_wait(a: dict) -> str:
    """把一条 wait 断言渲染成脚本行。

    [!] 期望值走**三层分离**：`_render_assert` 读的是 `_payload_ref`（由 `_extract_data` 抽到
        `datasets/<case_id>.json`），不是直接读 `expect` —— 一开始漏了这个键，
        渲染出来是「缺少 expect」的 fail 行，判据反而"看起来通过了相反的结论"。
    """
    from framework.tools.generate.generator import _render_assert
    a = dict(a)
    a.setdefault("_payload_ref", "expect_0")
    return "\n".join(_render_assert(a, {}))


def test_refresh_is_inferred_to_research_when_no_selector():
    """无 selector（列表页等状态）-> 必须**每轮重新取数**（research），否则调大超时也没用。"""
    line = _fill_and_render({"desc": "有界等待状态流转", "expect": "已关闭", "timeout_ms": 150_000})
    assert "refresh='research'" in line, f"没推断出 research -> 列表页永远等不到：{line}"


def test_refresh_stays_none_when_selector_given():
    """【反向自证】给了 selector（元素级自更新，如详情页状态）-> 保持 none，不动既有行为。"""
    line = _fill_and_render({"desc": "有界等待状态流转", "expect": "已关闭", "timeout_ms": 150_000,
                             "selector": "#d-order-status"})
    assert "refresh=" not in line, f"带 selector 的等待（元素级自更新）不该加参数：{line}"


def test_explicit_refresh_is_respected():
    """显式给了 refresh 一律尊重（模型/用例的明确决定不许被推断覆盖）。"""
    for rf in ("none", "reload", "research"):
        line = _fill_and_render({"desc": "等待 x 出现", "expect": "x", "timeout_ms": 1000, "refresh": rf})
        assert f"refresh={rf!r}" in line


def test_wait_polls_visible_matches_not_only_the_first():
    """等待断言必须**只认可见的匹配** —— demo 的隐藏 `<option>` 排在表格前面，只看 first 永远等不到。"""
    trap = (ROOT / "framework" / "tools" / "generate" / "generator.py").read_text(encoding="utf-8")
    i = trap.index("def _assert_wait_text")
    seg = "\n".join(l for l in trap[i:i + 2200].splitlines() if not l.lstrip().startswith("#"))
    assert "loc.first.is_visible()" not in seg, "又退回「只看第一个匹配」-> 隐藏项会永久挡住等待"
    assert ".nth(_i).is_visible()" in seg, "没有逐个可见性判定"

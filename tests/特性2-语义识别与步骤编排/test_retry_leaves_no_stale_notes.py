# -*- coding: utf-8 -*-
"""特性2 · 重试不许留「旧账」（V8.4.3+ · 让 AI 白挨两轮的 bug）。

现场（实跑日志）：
    第 1 轮 AI 漏了「客户/销售员」-> 校验拦下 + 记入 `_REQUIRED_COVERAGE_NOTES`。
    第 2 轮 AI **已经补上了**（产出里明明白白有 `fill 客户@新建订单页`），
    但校验读到的还是第 1 轮的旧账 -> 又拦 -> 第 3 轮再拦 -> 重试用尽，报错收场。

根因：清了 notes，但**只在「本轮有缺失」时才清** —— 本轮没缺失 = 根本没进那个分支 = 旧账留着。

同一形态在本项目出现**三次**（三个 notes 一对一对齐后逐个体检才找全）：
    `_REQUIRED_COVERAGE_NOTES`  只在有缺失时清   -> 旧账
    `_HARDCODED_NOTES`          只在有写死时清   -> 旧账
    `SEMANTIC_MISMATCH_NOTES`   **完全没有 clear** -> 旧账（永久累积）

判据口径：行为级验证「上一轮有、本轮没有 -> 本轮必须读到空」，
而不是读源码看有没有调用 clear（那种判据骗得过）。
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from framework.tools.explore import explorer as EX   # noqa: E402


class _El:
    def __init__(self, n):
        self.semantic_name = n


class _St:
    def __init__(self, order, op="fill", desc="", semantic=None, value=None, url=None):
        self.order, self.op, self.description = order, op, desc
        self.value, self.url = value, url
        self.element = _El(semantic) if semantic else None
        self.assertion = None
        self.row_text = self.cell_field = self.cell_by = self.cell_index = None


_SCENARIO = ("4. 在新建订单页填写：订单名称用「全链路-{datetime}」、"
             "业务单元/管理单元/帐套各选第一行、订单类型选第一项、"
             "客户与销售员各选第一个、订单备注填「端到端全链路场景」；点「保存」。")

_REQUIRED = [
    {"name": "订单名称", "page": "新建订单页", "token": "*订单名称"},
    {"name": "客户",     "page": "新建订单页", "token": "*客户"},
    {"name": "销售员",   "page": "新建订单页", "token": "*销售员"},
]

# 第 1 轮：只做了订单名称（漏客户/销售员）
_ROUND1 = [_St(1, desc="填写订单名称", semantic="订单名称@新建订单页", value="全链路-{datetime}")]
# 第 2 轮：补全（这就是实测里 AI 第 2 轮的真实产出）
_ROUND2 = _ROUND1 + [
    _St(2, op="select", desc="客户选第一个", semantic="客户@新建订单页"),
    _St(3, op="select", desc="销售员选第一个", semantic="销售员@新建订单页"),
]


def test_round1_reports_missing():
    """第 1 轮确实漏了 -> 必须报（否则这个校验就是摆设）。"""
    EX._LAST_REQUIRED_FIELDS.clear()
    EX._LAST_REQUIRED_FIELDS.extend(_REQUIRED)
    miss = EX.check_required_field_coverage(_ROUND1, EX._LAST_REQUIRED_FIELDS, _SCENARIO)
    assert len(miss) == 2, f"应报客户+销售员，实际 {miss}"


def test_round2_after_round1_leaves_no_stale_notes():
    """【核心回归】第 1 轮记账后，第 2 轮补全 -> notes 必须为空（不许留旧账）。

    这正是让 AI 白挨两轮的 bug：旧账不清 -> 补好了还被拦 -> 重试用尽报错。
    """
    # 模拟第 1 轮：把缺失写进 notes（与生产代码同一路径）
    EX._REQUIRED_COVERAGE_NOTES.clear()
    EX._REQUIRED_COVERAGE_NOTES.extend(
        EX.check_required_field_coverage(_ROUND1, _REQUIRED, _SCENARIO))
    assert EX._REQUIRED_COVERAGE_NOTES, "前置：第 1 轮应留下记账"

    # 模拟第 2 轮：**先无条件清空**（生产代码 `_finalize_map` 里就是这么做的）
    miss2 = EX.check_required_field_coverage(_ROUND2, _REQUIRED, _SCENARIO)
    EX._REQUIRED_COVERAGE_NOTES.clear()
    if miss2:
        EX._REQUIRED_COVERAGE_NOTES.extend(miss2)

    assert miss2 == [], f"第 2 轮已补全却仍判缺失：{miss2}"
    assert EX._REQUIRED_COVERAGE_NOTES == [], \
        f"第 2 轮补全后 notes 仍留旧账：{EX._REQUIRED_COVERAGE_NOTES}"


def test_finalize_map_clears_notes_unconditionally():
    """`_finalize_map` 必须是**无条件**清空（源码级兜底，防将来有人把 clear 挪进 if）。"""
    src = pathlib.Path(EX.__file__).read_text(encoding="utf-8")
    for notes_name in ("_REQUIRED_COVERAGE_NOTES", "_HARDCODED_NOTES"):
        # clear 必须出现在 `if <条件>:` 之前（也就是不缩进在分支里）
        lines = src.splitlines()
        idx = [i for i, l in enumerate(lines) if f"{notes_name}.clear()" in l]
        assert idx, f"{notes_name} 没有任何 clear"
        for i in idx:
            indent = len(lines[i]) - len(lines[i].lstrip())
            assert indent == 4, \
                f"{notes_name}.clear() 缩进 {indent} -> 疑似被放进 if 分支里（会留旧账）"


def test_semantic_mismatch_notes_has_clear():
    """`SEMANTIC_MISMATCH_NOTES` 曾经**完全没有 clear**（永久累积）-> 必须有。"""
    src = pathlib.Path(EX.__file__).read_text(encoding="utf-8")
    assert "SEMANTIC_MISMATCH_NOTES.clear()" in src, \
        "语义校准的 notes 没有清空点 -> 跨轮累积（第三次同形态事故）"

"""L1 数据参数化「真展开」· 生成器契约回归（2026-09-21，服务目标 ① 降人力）。

背景：场景的 `data:` 一组数据应当产出**一条独立用例**（报告独立一行、失败能定位到具体数据集）。
本文件在秒级、不启浏览器下钉住四件事：

 1. **没数据的用例不许被碰到** —— 不加 parametrize（既有用例的产物形态与行为不变）；
 2. **占位符识别口径** —— 内置动态变量({datetime} 等)/框架自带键/数据键本身，都不算「要数据组提供的」；
 3. **写错必须硬拦** —— 组值少给占位符 / 给了用不到的键 ⇒ `DataSetsError`，且人话里要点名是哪个键；
 4. **描述里带 {占位符} 不许把生成代码搞崩** —— 渲染结果必须能被 `compile()`
    （实测踩过：desc 被塞进生成代码的 f-string，遇到 `{关键词}` 直接 NameError）；
 5. **场景 data 的写法校验** —— 坏形态（非列表/非映射/重复 id）⇒ `ScenarioError`。

跑法（秒级，不需要 demo、不需要浏览器）：
    cd ~/hybrid_gui_qa && .venv/bin/python -m pytest tests/test_data_expand.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from framework.tools.generate.generator import (                     # noqa: E402
    DataSetsError, _add_payload_refs, _brace_safe, _render_pytest_case,
    _validate_data_sets, placeholder_names_ordered,
)
from framework.tools.generate.scenario import ScenarioError, load_scenario_file   # noqa: E402


def _mini_case(**kw) -> dict:
    """一条最小可用用例（走真实的 `_add_payload_refs`，与生成链路同源）。"""
    case = {
        "case_id": "t_case",
        "name": "示例用例",
        "base_url": "http://localhost:8000",
        "steps": [
            {"op": "goto", "desc": "打开页面", "url": "http://localhost:8000"},
            {"op": "fill", "desc": "在搜索框输入 abc", "element": "搜索框", "value": "abc"},
            {"op": "click", "desc": "点搜索", "element": "搜索"},
        ],
        "asserts": [{"desc": "看到 abc", "expect": "abc", "after_step": 3}],
    }
    case.update(kw)
    return case


def _render(case: dict) -> str:
    return _render_pytest_case(_add_payload_refs(case), {})


# ---------------------------------------------------------------- 1) 不被动到
def test_case_without_data_generates_without_parametrize():
    """没有数据组 ⇒ 不加 parametrize（既有用例的产物形态不变，报告里也不是参数化行）。"""
    src = _render(_mini_case())
    assert "parametrize" not in src, "没有数据的用例不该被参数化"
    assert "def test_t_case(page, ctx):" in src


def test_case_with_data_generates_indirect_parametrize():
    """有数据组 ⇒ parametrize(indirect=True)，让 ctx fixture 接住本组数据（函数签名保持不变）。"""
    case = _mini_case()
    case["_data_sets"] = [{"id": "组1", "关键词": "1"}, {"id": "组2", "关键词": "2"}]
    src = _render(case)
    assert '@pytest.mark.parametrize("ctx"' in src, "有数据组必须参数化"
    assert "indirect=True" in src, "必须走 indirect（否则 ctx fixture 接不到本组数据）"
    assert "_ds_params('t_case')" in src and "_ds_ids('t_case')" in src
    assert "def test_t_case(page, ctx):" in src, "函数签名不许变（向后兼容）"


# ---------------------------------------------------------------- 2) 占位符口径
def test_placeholder_detection_ignores_builtin_and_framework_keys():
    data = {
        "fill_0": "输入{关键词}",              # ← 要数据组提供
        "expect_0": "{期望编号}",               # ← 也要
        "note": "合同_{datetime}",             # 内置动态变量 ⇒ 不算
        "x": "{contractName}",                 # 框架自己会填 ⇒ 不算
        "fill_1": "{fill_0}",                  # 引用本数据集的键 ⇒ 不算
    }
    assert placeholder_names_ordered(data) == ["关键词", "期望编号"]


def test_placeholder_detection_is_order_stable():
    """顺序口径要稳定（参数名回落取「第一个占位符」时依赖它）。"""
    data = {"a": "{乙}", "b": "{甲}", "c": "无占位符"}
    assert placeholder_names_ordered(data) == ["乙", "甲"]


# ---------------------------------------------------------------- 3) 写错必须拦
def test_validate_rejects_missing_placeholder_value():
    data = {"fill_0": "输入{关键词}", "expect_0": "{期望编号}"}
    sets = [{"id": "组1", "关键词": "1005"}]              # 少了 期望编号
    with pytest.raises(DataSetsError) as ei:
        _validate_data_sets({"case_id": "t"}, data, sets)
    msg = str(ei.value)
    assert "期望编号" in msg, f"人话里必须点名缺哪个键：{msg}"
    assert "{期望编号}" in msg, "要讲清症状：字面值会被原样填进页面"


def test_validate_rejects_unused_group_key():
    """给了用不到的键 = 写了不生效（静默误导）⇒ 也要拦。"""
    data = {"fill_0": "输入{关键词}"}
    sets = [{"id": "组1", "关键词": "1005", "打错的名字": "x"}]
    with pytest.raises(DataSetsError) as ei:
        _validate_data_sets({"case_id": "t"}, data, sets)
    assert "打错的名字" in str(ei.value)


def test_validate_accepts_exact_match():
    data = {"fill_0": "输入{关键词}", "expect_0": "{期望编号}"}
    sets = [{"id": "组1", "关键词": "1005", "期望编号": "HT-1005"}]
    _validate_data_sets({"case_id": "t"}, data, sets)     # 不抛 = 通过


# ---------------------------------------------------------------- 4) 描述带花括号
def test_desc_with_placeholder_renders_compilable_code():
    """★ 实测踩过的坑：desc 里带 {占位符} ⇒ 生成的 f-string 直接 NameError。渲染结果必须能编译。

    注意：`_log(page, "<op>", f"<desc>")` 只在**真渲染出动作**的步骤上出现
    （元素未映射的步骤会渲染成 pytest.fail 存根，没有那行）—— 这里用 goto 步骤走真路径。
    """
    case = _mini_case(steps=[
        {"op": "goto", "desc": "打开合同列表页（场景：{关键词}）", "url": "http://localhost:8000"},
    ], asserts=[])
    src = _render(case)
    compile(src, "<generated>", "exec")                   # 语法坏掉就会抛（这是主判据）
    assert 'f"打开合同列表页（场景：{{关键词}}）"' in src, "desc 嵌进 f-string 前必须转义大括号"
    # 只盯「会被当代码执行的 f-string」：步骤注释（# step N: …）里保留原文是无害的
    fstr_lines = [ln for ln in src.splitlines() if "_log(" in ln and 'f"' in ln]
    assert fstr_lines, "没找到渲染出的 _log f-string（判据失效，别再放着当绿）"
    assert all("{" not in ln.replace("{{", "").replace("}}", "") for ln in fstr_lines), \
        f"还有未转义的花括号会 NameError：{[ln for ln in fstr_lines if '{' in ln.replace('{{','').replace('}}','')]}"


def test_brace_safe_keeps_plain_text_identical():
    """无花括号的文本转义前后一致 ⇒ 既有用例的产物逐字节不变（这是「不破现状」的前提）。"""
    assert _brace_safe("在搜索框输入 abc") == "在搜索框输入 abc"
    assert _brace_safe("{关键词}") == "{{关键词}}"


# ---------------------------------------------------------------- 5) 场景 data 写法
def _write_scenario(tmp: Path, data_block: str) -> Path:
    p = tmp / "s.yml"
    p.write_text(
        "id: t_scenario\n"
        "title: 测试用场景\n"
        "scenario: |\n  在搜索框输入 '{关键词}'。\n" + data_block,
        encoding="utf-8")
    return p


def test_scenario_data_accepts_wellformed(tmp_path):
    sc = load_scenario_file(_write_scenario(
        tmp_path, 'data:\n  - {id: "组1", 关键词: "1005"}\n  - {关键词: "1007"}\n'))
    assert len(sc.data) == 2
    assert sc.data[0]["id"] == "组1"


@pytest.mark.parametrize("block,expect", [
    ("data: {关键词: 1005}\n", "应为列表"),                       # 不是列表
    ("data:\n  - 关键词\n", "应为映射"),                          # 不是映射
    ('data:\n  - {id: "同一", 关键词: "1"}\n  - {id: "同一", 关键词: "2"}\n', "id 重复"),
    ("data:\n  - {id: 3, 关键词: \"1\"}\n", "非空字符串"),         # id 类型错
    ("data:\n  - {'': \"1\"}\n", "占位符名"),                      # 空键
])
def test_scenario_data_rejects_bad_shape(tmp_path, block, expect):
    with pytest.raises(ScenarioError) as ei:
        load_scenario_file(_write_scenario(tmp_path, block))
    assert expect in str(ei.value), f"报错要说清坏在哪：{ei.value}"


# ---------------------------------------------------------------- 6) 防复发：ctx 节点名
def test_generated_conftest_strips_param_suffix():
    """参数化后节点名是 test_<cid>[<组>] —— 两处「从节点名反解 case_id」都必须切掉后缀。

    涉及两处（都是真坑）：① `ctx` fixture（取数据集）② `page` fixture（trace 文件名）。
    判据打在**渲染出的产物**上，不打模板源码 —— 模板是普通字符串、里头的反斜杠是写双的，
    按源码文本去查会假红（2026-09-21 实测踩到）；
    **功能层面的证明**在二类 `tests/verify_data_expand.py`（真按参数名跑单组）。
    """
    from framework.tools.generate import generator as G
    text = G._render_conftest()
    bad = text.count('re.search(r"test_(.+)"') + text.count('_re.search(r"test_(.+)"')
    assert bad == 0, f"还有 {bad} 处用 re.search(\'test_(.+)\') ⇒ 参数化后会把 [组名] 当 case_id 的一部分"
    assert text.count('r"test_([^\\[]+)"') >= 2, "ctx / page 两处都要用 re.match 切掉参数后缀"
    assert 'getattr(request, "param"' in text, "parametrize(indirect=True) 的数据没被 ctx 接住"

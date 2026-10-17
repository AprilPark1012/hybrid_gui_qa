"""`wait_text` 等待式断言 · **渲染契约**（P22 批 1/5 · V8.6.4 三合一）—— 秒级，不需 demo/浏览器。

起因（真值 · P22 §二 缺口 (2)）：
  · 11 种断言 kind 里没有"等状态变化"（`generator.py:149-155`）
  · `_assert_text` 超时**硬编码 5000ms**（`generator.py:1945`），连 `HYBRID_LOCATE_TIMEOUT` 都调不到，
    断言层也没有 per-assert timeout 字段
  · [!] 更要命的是 `demo/orders.html` **无任何自动刷新**（grep `setInterval/setTimeout/refresh` = 0 处）
    -> 光把超时调大**也等不到**，必须"每轮重新取数"（由 `refresh` 三态负责）
AprilPark1012 2026-09-29 拍板：**新增等待式断言 `wait_text`**（带超时 + 每轮重新取数）。

V8.6.4（合并重复判据 · 第一批）：本文件由三条**同源**判据合并而来 ——
  · `test_wait_text_kind.py`（kind 在册 / 超时渲染 / 有界默认 / 两个负向）
  · `test_wait_text_refresh_policy.py`（`refresh` 三态 + 缺省不出参数 + 负向）
  · `test_wait_text_selector.py`（`selector` 透传 + 向后兼容空 selector）
**为什么合成一条**：三者守的是同一件事 ——「一条 `wait_text` 断言渲染成生成脚本里的调用行
长什么样」，只是各守其中一个字段。分成三个文件 = 同一件事被三条判据分别守着：改一处要三处验，
且渲染入口有**三份 `_render` 副本**（其中两份手工塞 `_payload_ref`，还在注释里自承"等于测了个假形态"）。
本文件的 `_render` 一律走**真管线**（`_add_payload_refs` -> `_render_assert`）：
期望值由框架自己抽成 `_data('expect_N', ctx)`，与 generate 真实链路同口径。

判据口径（合并后 11 条）：
  1. 正向：`wait_text` 已登记进 `_ASSERT_KINDS`（否则渲染层直接判"未知断言类型"）
  2. 正向：`kind=wait_text` + `expect` + `timeout_ms` -> 渲染出 `_assert_wait_text(...)`
     且该毫秒值如实落进产物；期望值走**数据引用**（`_data(`）
  3. 正向：不写 `timeout_ms` -> 用**有界默认值**（必须是正整数毫秒，绝不无限等）
  4. 正向：`refresh` 三态（none / reload / research）都如实渲染（research 是列表页不刷新那条缺口的解药）
  5. 正向：不写 `refresh` -> 不产生该参数（保持与老产物形态一致）
  6. 正向：带 `selector` -> 渲染出 selector 参数（限定范围）
  7. 正向：不带 `selector` -> 渲染空 selector（向后兼容，行为不变）
  8. 负向：缺 `expect` -> 必须 `pytest.fail`（不许静默少验一步 = 假绿）
  9. 负向（**两组合并成一条 parametrize**）：非法 `timeout_ms`（负数 / 0 / 非数字 / 浮点）
     与非法 `refresh`（拼错 / 错类型）-> 都必须 `pytest.fail`
  10. 正向（**V8.6.4 新增**）：渲染出的 kwarg 名 == `_assert_wait_text` **真签名**的参数名（差集为空）
  11. 回归：11 种老 kind 仍在册（新增 kind 不许挤掉老的）

跑法（秒级）：
    python -m pytest tests/特性9-质量闸门体系/test_wait_text_render_contract.py -q
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from framework.features.f02_semantic import generator_generate as G

LOC: dict = {}

REPO = Path(__file__).resolve().parents[2]
GENERATOR = REPO / "framework" / "features" / "f02_semantic" / "generator_generate.py"

_OLD_KINDS = {"text", "visible", "hidden", "count", "attr", "value", "url",
              "checked", "unchecked", "enabled", "disabled", "first_row"}


def _render(a: dict) -> str:
    """把一条断言渲染成生成脚本里的调用行（走**真管线**，避免判据走"影子实现"）。

    [!] 必须经由 `_add_payload_refs()`：真实链路里期望值由它抽离成 `_data(ref, ctx)`。
    另两份被合并掉的副本是**手工**塞 `_payload_ref` 的 —— 它们自己都在注释里写明
    "不带它就等于测了个假形态"（首次写就踩：5 条**正向**判据全红，原因不是实现没生效，
    而是判据漏了这个字段）。所以这里只留一条真写法，别再抄第二份。
    """
    return "\n".join(G._render_assert(G._add_payload_refs({"asserts": [a]})["asserts"][0], LOC))


# ---------------------------------------------------------------- 1-3. kind 在册 / 超时 / 有界默认

def test_wait_text_registered_in_kinds():
    """判据 1：`wait_text` 必须在册 —— 否则渲染层会直接判"未知断言类型"。"""
    assert "wait_text" in G._ASSERT_KINDS, (
        f"wait_text 未登记进 _ASSERT_KINDS（现有：{sorted(G._ASSERT_KINDS)}）-> 用例写它必被当成非法类型")


def test_wait_text_renders_with_timeout():
    """判据 2：带超时渲染成 `_assert_wait_text(...)`，且毫秒值如实落到产物里。"""
    src = _render({"kind": "wait_text", "expect": "已关闭", "timeout_ms": 180000})
    assert "pytest.fail" not in src, f"不应被判非法：{src}"
    assert "_assert_wait_text(" in src, f"应渲染成等待式断言调用：{src}"
    assert "180000" in src, f"180000ms 必须原样落进产物（否则等的不是他要的时长）：{src}"
    # 期望值走**数据引用**：真实链路里它被抽到 scripts/datasets/*.json，生成代码里只有
    # `_data('expect_N', ctx)` —— 判据不该断言字面量出现在生成代码里（首次就是这么写错的）
    assert "_data(" in src, f"期望值必须经数据引用传入（与 text 断言同口径）：{src}"


def test_wait_text_default_timeout_is_bounded():
    """判据 3：不写 `timeout_ms` -> 用**有界**默认（正整数毫秒），绝不无限等。"""
    src = _render({"kind": "wait_text", "expect": "已关闭"})
    assert "pytest.fail" not in src, f"缺 timeout_ms 应走默认值而不是判非法：{src}"
    m = re.search(r"timeout_ms=(\d+)", src)
    assert m, f"默认超时必须显式落在产物里（便于审计「到底等了多久」）：{src}"
    assert int(m.group(1)) > 0, f"默认超时必须 > 0：{src}"


# ---------------------------------------------------------------- 4-5. refresh 三态 / 缺省不出参数

@pytest.mark.parametrize("mode", ["none", "reload", "research"])
def test_wait_text_refresh_modes_rendered(mode):
    """判据 4：三态都如实渲染（缺一不可 —— `research` 是列表页不刷新那条缺口的解药）。

    三态口径（AprilPark1012 2026-09-29 拍：带超时 + 每轮重新取数）：
      · `none`（缺省）：只轮询 DOM —— 等价现有 expect 语义，用于"页面自己会更新"的场景
      · `reload`：每轮重新加载当前 URL
      · `research`：每轮重新触发**上一次搜索**（框架重放最后一次「搜索」点击 + 当时输入）
    （`research` 的**重放实现**由端到端验证 —— 本判据只钉"参数被如实渲染 / 非法值必须红"，
     不把重放的内部 API 写死，避免判据反过来绑死实现）
    """
    src = _render({"kind": "wait_text", "expect": "已关闭", "timeout_ms": 60000, "refresh": mode})
    assert "pytest.fail" not in src, f"refresh={mode!r} 应合法，实际：{src}"
    assert "_assert_wait_text(" in src, f"应渲染成等待式断言：{src}"
    assert mode in src, f"refresh={mode!r} 必须落在产物里（否则等于没声明）：{src}"


def test_wait_text_default_refresh_is_absent():
    """判据 5：不写 refresh -> 不产生 refresh 参数（老产物形态不变，避免全量重渲染）。"""
    src = _render({"kind": "wait_text", "expect": "已关闭", "timeout_ms": 60000})
    assert "refresh=" not in src, f"未声明 refresh 时不该出现该参数：{src}"


# ---------------------------------------------------------------- 6. selector 透传 / 向后兼容

def test_wait_text_passes_selector_through():
    """判据 6a：带 selector -> 渲染出 selector 参数（限定范围）。

    为什么有它（真值 2026-09-30）：`expect="已关闭"` 用全页 `get_by_text` -> 命中**隐藏**的筛选
    下拉选项 `<option value="已关闭">`（demo/orders.html:531）-> 永远不可见 -> 5s 超时失败。
    正解是限定范围：在状态列 `td[data-field="orderStatus"]` 里等这段文本。
    """
    out = _render({"kind": "wait_text", "expect": "已关闭",
                   "selector": 'td[data-field="orderStatus"]',
                   "timeout_ms": 240000, "desc": "等状态列变已关闭"})
    assert "_assert_wait_text(page" in out and "selector=" in out, out
    assert "orderStatus" in out, out
    assert "pytest.fail" not in out, out


def test_wait_text_without_selector_is_backward_compatible():
    """判据 6b：不带 selector -> 渲染空 selector（向后兼容，行为不变）。"""
    out = _render({"kind": "wait_text", "expect": "已关闭", "timeout_ms": 30000, "desc": "d"})
    assert "_assert_wait_text(page" in out and "selector=''" in out, out
    assert "pytest.fail" not in out, out


# ---------------------------------------------------------------- 7-8. 负向（缺 expect + 合并的非法值）

def test_wait_text_missing_expect_must_fail():
    """判据 7（负向）：`wait_text` 没有 `expect` -> 必须 fail（等一个没写的东西 = 假绿）。

    断言里必须排除"未知断言类型"这种失败原因 —— 否则 kind 一旦没实现，本条判据恒真。
    """
    src = _render({"kind": "wait_text", "timeout_ms": 1000})
    assert "pytest.fail" in src and "未知断言类型" not in src, (
        f"缺 expect 必须**因为缺 expect**失败（不能是「kind 还没实现」这种失败，否则判据恒真）"
        f"—— 实际渲染：{src}")


@pytest.mark.parametrize("bad", [
    {"timeout_ms": -1}, {"timeout_ms": 0}, {"timeout_ms": "abc"}, {"timeout_ms": 3.5},
    {"refresh": "full"}, {"refresh": "re-search"}, {"refresh": "NONE"},
    {"refresh": 3}, {"refresh": ["reload"]},
], ids=lambda b: "bad-" + "-".join(f"{k}-{v}" for k, v in sorted(b.items())))
def test_wait_text_illegal_field_values_must_fail(bad):
    """判据 8（负向 · **两组合并成一条 parametrize**）：非法取值 / 错类型都必须当场 fail。

    合并前是两条（`timeout_ms` 一组 + `refresh` 一组），它们**共同**的前提是一样的：
    失败原因必须来自**值非法**，不能来自"kind 还没实现"—— 所以合成一条，共同断言
    「渲染出 `pytest.fail` 且**不含**『未知断言类型』」，一次把假绿的可能性堵死。
    语义不许被合并稀释：拼错一个词就静默退成"只等不重取" / 静默取默认值都是假绿。
    """
    a = {"kind": "wait_text", "expect": "已关闭", "timeout_ms": 60000, **bad}
    src = _render(a)
    assert "pytest.fail" in src and "未知断言类型" not in src, (
        f"{bad!r} 非法却渲染成了正常调用（或失败原因是「未实现」而非「值非法」）：{src}")


# ---------------------------------------------------------------- 9. 新增：kwarg 名 == 真签名（V8.6.4）

def _assert_wait_text_params(src: str) -> set[str]:
    """从 `generator_generate.py` 里抠出 `def _assert_wait_text(...)` 的**真参数名**集合。

    为什么读源码而不是在判据里抄一份名字：签名只有一份权威（生成器模板），
    在判据里再写一份就是又造一个会漂移的副本 —— 那正是本版在合并的东西。

    [!] 为什么**不能用 ast 找 `FunctionDef`**（第一版就是这么写错的，判据当场"先红"）：
    这个函数**不是模块里的真函数** —— 它是 generator 渲染进生成脚本的**配套 fixture 模板**
    （模块级字符串常量，`generator_generate.py:2425` 起那段）。ast 只看得到真 `def`，
    于是 `ast.walk` 遍历完一圈空手而归，判据报"找不到函数、前提失效"。
    正解：在源码文本里定位模板中的 def 行、按参数表解析 —— 权威仍然只有这一份。
    留着这条注释是因为"这个函数在模板里"这件事本身就是下次会再踩的坑。
    """
    m = re.search(r"def _assert_wait_text\(([^)]*)\)", src)
    assert m, ("generator_generate.py 的配套 fixture 模板里找不到 def _assert_wait_text()"
               "（判据前提失效 —— 函数被改名/删掉时要同步本判据）")
    params: set[str] = set()
    for part in m.group(1).split(","):
        name = part.strip().split("=")[0].strip().lstrip("*")
        if name:
            params.add(name)
    return params


def _rendered_wait_text_kwargs(src: str) -> set[str]:
    """取渲染出的 `_assert_wait_text(...)` 调用里出现的 kwarg 名。

    [!] 为什么用 `ast` 解析而不是正则扫 `名字=` 这类模式：渲染行是**真 Python 代码**，里面还会出现
    **字符串字面量里的等号** —— 例如 selector `'td[data-field="orderStatus"]'` 里的 `data-field=`。
    正则扫会把 `field` 当成一个 kwarg 名报出来（第一版就是这么假红的：差集报 `['field']`），
    于是判据把**自己解析错**的结果当成"渲染层写错了名字"，红得毫无意义。
    真解析代码结构（`ast.Call.keywords`）才不会把字符串内容当参数名。
    """
    line = next((ln for ln in src.splitlines() if "_assert_wait_text(" in ln), None)
    assert line, f"没有渲染出 `_assert_wait_text(...)` 调用：{src}"
    tree = ast.parse(line.strip())
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "_assert_wait_text"]
    assert len(calls) == 1, f"渲染行里应该有且仅有一个 `_assert_wait_text(` 调用，实际 {len(calls)}：{line}"
    return {k.arg for k in calls[0].keywords if k.arg}


def test_wait_text_rendered_kwargs_match_real_signature():
    """判据 9（**V8.6.4 新增**）：渲染出的 kwarg 名必须都在 `_assert_wait_text` **真签名**里。

    为什么加：渲染层是**字符串拼参数名**（`f"... timeout_ms={tm}, refresh=..."`），签名是 `def`
    —— 两边靠人眼保持一致。名字写错**在纯函数判据里完全看不见**：产物照样生成，
    实跑才 `TypeError: _assert_wait_text() got an unexpected keyword argument`
    （那时代价是一整轮端到端 + 一轮 AI 重试）。本判据把两边的**差集钉成空集**。
    先红后绿（本判据自带负向自证）：把渲染结果里的 `timeout_ms=` 改成拼错的 `timeout_ms_typo=`
    -> 差集必须非空；真渲染 -> 差集必须为空。不做这一步，本判据可能压根没在看。
    """
    src = open(GENERATOR, encoding="utf-8").read()
    params = _assert_wait_text_params(src)
    out = _render({"kind": "wait_text", "expect": "已关闭",
                   "selector": 'td[data-field="orderStatus"]',
                   "timeout_ms": 180000, "refresh": "research", "desc": "等状态列变已关闭"})
    rendered = _rendered_wait_text_kwargs(out)
    assert rendered, f"一条 kwarg 都没渲染出来（判据前提失效，别让它恒真）：{out}"
    gap = sorted(rendered - params)
    assert not gap, (
        f"渲染出的 kwarg 名不在 `_assert_wait_text` 真签名里：{gap}\n"
        f"  渲染出：{sorted(rendered)}\n  真签名：{sorted(params)}\n"
        f"  -> 生成脚本实跑会 TypeError（写错的名字在纯函数判据里看不见）")
    # 负向自证：故意拼错一个 kwarg 名 -> 差集必须非空（否则本判据恒真）
    bogus = out.replace("timeout_ms=", "timeout_ms_typo=")
    assert _rendered_wait_text_kwargs(bogus) - params, (
        f"判据自身抓不住拼错的 kwarg 名 -> 恒真，等于没判：{bogus}")


# ---------------------------------------------------------------- 10. 回归：老 kind 不许被挤掉

def test_old_kinds_not_broken():
    """判据 10（回归）：新增 kind 不许挤掉老的 11 种。"""
    missing = _OLD_KINDS - set(G._ASSERT_KINDS)
    assert not missing, f"老断言 kind 丢了：{sorted(missing)}"

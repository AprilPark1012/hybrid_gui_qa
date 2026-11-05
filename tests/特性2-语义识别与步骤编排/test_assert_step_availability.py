# -*- coding: utf-8 -*-
"""一类判据：**断言步骤可用性对齐**（V8.9.6 · L38 + `expect_first_row` 跨页取列）。

## 这道闸防的是什么

AI 能写的断言动作在 `shared/step_ops.py` 里只有三个（`ASSERT_OPS`）：
`expect_text` / `expect_url` / `expect_first_row`。但**执行能力不齐**：

| 断言 | 旧状态 |
|---|---|
| `expect_text` / `expect_url` | 主链路能执行；**登录段一律丢掉**（`_login_flow` 没有分支） |
| `expect_first_row` | 主链路能执行；**跨页取列只警告不拦**，运行期报错还不告诉你该页有哪些列 |

真机日志（2026-11-05，V8.9.5）：

    [login] [!] 登录步骤里有非操作动作，已跳过：[(4, 'expect_url')]

AI 顺手写的「断言已进入首页」**没有执行** —— 登录成功的判定少了一道。

## 口径（本文件钉死）

1. `ASSERT_OPS` 里每个成员**都必须**在 `_exec_assert` 有映射 —— 断言只有**一个执行入口**，
   主链路与登录链路共用；将来加断言类型时**不许只接主链路**。
2. 登录段执行 `expect_url` / `expect_text`；**失败必须当场抛**（错误含「断言失败」），不许静默跳过。
3. `expect_first_row` 在登录段丢掉是**允许**的，但日志必须**说清原因**（不许静默）。
4. 行断言失败时，错误信息必须给出**该页表格的实际列** —— 只说「没有这一列」等于让排查重新猜。
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HARNESS = REPO / "scripts" / "generated" / "_harness.py"

sys.path.insert(0, str(REPO))


def _load_harness():
    old = os.environ.pop("HYBRID_BASE_URL", None)
    try:
        spec = importlib.util.spec_from_file_location("_harness_assert_uut", HARNESS)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        if old is not None:
            os.environ["HYBRID_BASE_URL"] = old


class _FakePage:
    """登录流需要的最小面：goto / url / eval_on_selector_all。"""

    def __init__(self, cols=None):
        self.url = "http://x/"
        self.urls: list[str] = []
        self.cols = cols if cols is not None else []

    def goto(self, u, **kw):
        self.urls.append(str(u))
        self.url = str(u)

    def eval_on_selector_all(self, _sel, _js):
        return self.cols

    def wait_for_timeout(self, _ms):
        return None

    def wait_for_url(self, *a, **kw):
        return None


# ---------------- (1) 元判据：每个 ASSERT_OPS 成员都必须有映射 ----------------

def test_every_assert_op_has_a_mapping():
    """`ASSERT_OPS` 三个成员在 `_exec_assert` 里都要有分支 —— 这是「可用性对齐」的元判据。

    为什么钉这个而不是只钉那两条已经修好的：将来有人加 `expect_visible` 之类，
    只接主链路、忘了登录链路，行为判据全绿而歪路照样存在 —— 元判据能当场抓住。
    """
    from framework.shared.step_ops import ASSERT_OPS
    src = HARNESS.read_text(encoding="utf-8")
    i = src.index("def _exec_assert(")
    j = src.index("\ndef ", i + 10)
    body = src[i:j]
    missing = [op for op in sorted(ASSERT_OPS) if f'"{op}"' not in body]
    assert not missing, f"这些断言动作在 _exec_assert 里没有映射：{missing}"


def test_unknown_assert_op_is_loud():
    """未知断言动作必须报错，不许静默当成通过。"""
    h = _load_harness()
    try:
        h._exec_assert(_FakePage(), "expect_whatever", "x")
    except RuntimeError as e:
        assert "没有映射" in str(e), str(e)
    else:
        raise AssertionError("未知断言动作竟然没报错")


# ---------------- (2) 派发到正确的断言实现 ----------------

def test_exec_assert_dispatches_to_real_impl(monkeypatch):
    h = _load_harness()
    calls = []
    monkeypatch.setattr(h, "_assert_url", lambda p, v, d="": calls.append(("url", v)))
    monkeypatch.setattr(h, "_assert_text", lambda p, v, d="": calls.append(("text", v)))
    monkeypatch.setattr(h, "_assert_first_row",
                        lambda p, f, v, d="", timeout_ms=None, refresh="none":
                        calls.append(("row", f, v)))
    p = _FakePage()
    h._exec_assert(p, "expect_url", "/index")
    h._exec_assert(p, "expect_text", "欢迎")
    h._exec_assert(p, "expect_first_row", "订单A", cell_field="orderName")
    assert calls == [("url", "/index"), ("text", "欢迎"), ("row", "orderName", "订单A")], calls


def test_exec_assert_row_requires_cell_field():
    """行断言缺 `cell_field` 必须明确报错（不许默认拿第一列猜）。"""
    h = _load_harness()
    try:
        h._exec_assert(_FakePage(), "expect_first_row", "订单A")
    except RuntimeError as e:
        assert "cell_field" in str(e)
    else:
        raise AssertionError("缺 cell_field 竟然没报错")


# ---------------- (3) 登录段真的执行断言 ----------------

def _login_steps_with_assert():
    return [
        {"op": "goto", "value": "http://x/login.html"},
        {"op": "expect_url", "value": "/index", "desc": "确认已进入首页"},
    ]


def test_login_flow_executes_assert_steps(monkeypatch):
    """登录段的 `expect_url` 必须被**执行**（旧实现是丢掉 —— L38 的病灶）。"""
    h = _load_harness()
    monkeypatch.setattr(h, "_log", lambda *a, **k: None)
    seen = []
    monkeypatch.setattr(h, "_exec_assert",
                        lambda page, op, value="", desc="", **kw: seen.append((op, value)))
    p = _FakePage()
    h._login_flow(p, _login_steps_with_assert(), {"url_not": "login.html"}, "http://x/login.html")
    assert seen == [("expect_url", "/index")], f"登录段的断言没有被执行：{seen}"


def test_login_flow_assert_failure_is_loud(monkeypatch):
    """登录断言失败必须**当场抛**，错误里要能看出是登录第几步的哪个断言 —— 不许吞。"""
    h = _load_harness()
    monkeypatch.setattr(h, "_log", lambda *a, **k: None)

    def _boom(page, op, value="", desc="", **kw):
        raise AssertionError("URL 对不上")

    monkeypatch.setattr(h, "_exec_assert", _boom)
    try:
        h._login_flow(_FakePage(), _login_steps_with_assert(),
                      {"url_not": "login.html"}, "http://x/login.html")
    except RuntimeError as e:
        msg = str(e)
        assert "断言失败" in msg and "expect_url" in msg, msg
    else:
        raise AssertionError("登录断言失败被吞掉了")


# ---------------- (4) 生成侧：可执行断言不再被丢，无意义的要说明原因 ----------------

def _mk_map(ops):
    from framework.features.f03_locate.element_map import ElementMap, TestStep
    m = ElementMap(scenario="t")
    m.steps = [TestStep(order=i + 1, op=op, value="v") for i, op in enumerate(ops)]
    return m


def test_login_executable_keeps_url_and_text_asserts(capsys):
    from framework.features.f02_semantic.login_flow_explore import _executable
    m = _mk_map(["goto", "fill", "click", "expect_url", "expect_text"])
    got = [s.op for s in _executable(m)]
    assert got == ["goto", "fill", "click", "expect_url", "expect_text"], got
    assert "已跳过" not in capsys.readouterr().out, "可执行断言不该被报成「已跳过」"


def test_login_dropped_row_assert_says_why(capsys):
    """`expect_first_row` 在登录段丢掉是允许的，但必须**说清原因**（不许静默）。"""
    from framework.features.f02_semantic.login_flow_explore import _executable
    m = _mk_map(["goto", "expect_first_row"])
    got = [s.op for s in _executable(m)]
    assert got == ["goto"], got
    out = capsys.readouterr().out
    assert "expect_first_row" in out and ("cell_field" in out or "表格行" in out), \
        f"丢掉行断言却没说明原因：{out!r}"


# ---------------- (5) 行断言失败信息必须给「该页实际列」 ----------------

def test_first_row_failure_reports_actual_columns(monkeypatch):
    """断言失败的报错要给出该页**真实列清单** —— 只说「没有这一列」等于让人重新猜。"""
    h = _load_harness()
    monkeypatch.setattr(h, "_wait_summary", lambda *a, **k: None)

    class _ZeroLoc:
        def count(self):
            return 0

        class first:
            @staticmethod
            def inner_text():
                return ""

    class _P(_FakePage):
        def locator(self, _sel):
            return _ZeroLoc()

    p = _P(cols=["lineNo", "lineStatus", "invoiceNo"])
    try:
        h._assert_first_row(p, "orderName", "订单A", timeout_ms=0)
    except AssertionError as e:
        msg = str(e)
        assert "lineNo" in msg and "invoiceNo" in msg, f"报错没给出实际列：{msg}"
        assert "orderName" in msg
    else:
        raise AssertionError("没有第一行竟然没报错")


# ---------------- (6) 缓存口径：存 AI 原始决策，过滤在读侧 ----------------

def test_login_cache_keeps_raw_ai_decision():
    """登录缓存必须存 **AI 的原始决策**，不许把过滤后的步骤固化进去。

    为什么钉这个（2026-11-05 L38 的直接教训）：旧口径「只把可执行步落盘」，
    于是**过滤规则一改，老缓存永远不生效** —— AI 写的 `expect_url` 被永久埋在缓存里，
    必须重新规划才补得回来。过滤属于**执行侧**（框架怎么执行），不是 AI 的决策。
    """
    src = (REPO / "framework" / "features" / "f02_semantic" / "login_flow_explore.py") \
        .read_text(encoding="utf-8")
    assert "m.steps = steps" not in src, "又把过滤后的步写回缓存了（规则一改老缓存就永远不生效）"
    i = src.index("def plan_login(")
    body = src[i:]
    assert "_executable(m, quiet=True)" in body, "读缓存那条路没有应用执行侧过滤"


def test_cached_login_with_url_assert_is_reused(tmp_path, monkeypatch):
    """老缓存里带 `expect_url` 时，读出来必须**仍然包含**它（不许被新规则又滤掉）。"""
    from framework.features.f02_semantic import login_flow_explore as LF
    from framework.features.f03_locate.element_map import ElementMap, TestStep
    m = ElementMap(scenario="s")
    m.steps = [TestStep(order=1, op="goto", value="http://x/login.html"),
               TestStep(order=2, op="expect_url", value="/index")]
    p = tmp_path / "login_x.json"
    m.to_json(p)
    got = [s.op for s in LF._executable(ElementMap.from_json(p))]
    assert got == ["goto", "expect_url"], got


# ---------------- (7) 列名来源：绝不拿单元格文本当列名 ----------------

class _ColPage:
    """模拟三种页面：有数据行 / 只有表头 / 空状态提示行。"""

    def __init__(self, fields, heads, cells):
        self.fields, self.heads, self.cells = fields, heads, cells

    def eval_on_selector_all(self, sel, _js):
        if "td[data-field]" in sel:
            return self.fields
        if "thead th" in sel:
            return self.heads
        return self.cells


def test_table_field_list_prefers_data_field():
    h = _load_harness()
    p = _ColPage(["contractNo", "customer"], ["合同编号", "客户"], ["没有匹配的合同"])
    assert h._table_field_list(p) == ["contractNo", "customer"]


def test_table_field_list_falls_back_to_header_not_cell_text():
    """没有 `data-field` 时退回**表头文案**，绝不用单元格文本。

    真页面实测踩到（2026-11-05）：空表格第一行是空状态提示「没有匹配的合同」，
    用单元格文本兜底会把这句话报成「该页实际列」—— **比不报更误导**。
    """
    h = _load_harness()
    p = _ColPage([], ["合同编号", "客户"], ["没有匹配的合同"])
    got = h._table_field_list(p)
    assert got == ["合同编号", "客户"], got
    assert "没有匹配的合同" not in got


def test_table_field_list_empty_when_nothing_readable():
    h = _load_harness()
    p = _ColPage([], [], ["没有匹配的合同"])
    assert h._table_field_list(p) == []

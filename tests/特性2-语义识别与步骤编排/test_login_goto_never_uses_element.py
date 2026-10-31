"""V8.7.25 判据：`goto` 步骤的地址**只认 `value`，绝不许拿 `element` 顶替**。

由来（2026-10-30 用户 V8.7.24 真机 `all --ai`，PASSED 但日志里揪出）：
    日志第 18 行 / 第 196 行（两轮都有）：
        [explore] [key] 登录前置：[!] 失败
        -> Error: Page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
        Call log:
          - navigating to "ElementRef(semantic_name='账号', role='textbox', name='账号',
             label=None, placeholder='请输入账号', ...)"

  真因（`login_flow_explore.py` 的 `run_login_steps`）：
        if op == "goto":
            target = str(st.value or st.element or "").strip()   # <-- 这行
            page.goto(target, ...)

  `value` 为空、`element` 有值时，`str(ElementRef对象)` 就成了「URL」——
  于是 goto 收到 `ElementRef(semantic_name='账号', ...)` -> 协议错 -> **登录前置整条中断**。

  比「报错」更糟的是它**看起来像兜底**：真正该做的是报「goto 没有地址」让 AI 重生成，
  而不是拿一个语义对象去顶 URL 位置（静默降级 = 造假）。

  [!] `generator_generate.py` 那侧（`page.goto(str(st.get("value") or login_url))`）
      用的是 `login_url` 兜底，**安全**；但两侧口径不统一，所以这里也一并钉住。

守五件事：
  ① `goto` 的 value 为空 -> **必须抛错**，错误文本要说清「element 不能当 URL 用」；
  ② 该步还带了 element 时，错误里要提示「可能是把 goto 和 click 写混了」；
  ③ 正常 goto（value 有值）**不许被误拦**；
  ④ 全仓不许再出现 `value or ... element` 这类把语义对象当 URL 的兜底；
  ⑤ generate 侧登录执行器不许用 element 顶 URL。
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_SRC_LOGIN = (REPO / "framework/features/f02_semantic/login_flow_explore.py").read_text(encoding="utf-8")
_SRC_GEN = (REPO / "framework/features/f02_semantic/generator_generate.py").read_text(encoding="utf-8")


def _elref(name: str):
    """构造真实 `ElementRef`（TestStep.to_dict() 会对 element 调 .to_dict()，传 dict 会炸）。"""
    from framework.features.f03_locate.element_map import ElementRef

    return ElementRef(semantic_name=name, role="textbox", isValid=True)


def _step(op: str, value=None, element=None):
    from framework.features.f03_locate.element_map import TestStep

    return TestStep(1, op, element=element, value=value, desc="登录第 1 步")


def _fake_page() -> object:
    """最小 page 替身：只记 goto 的入参，不碰真实浏览器。"""
    class _P:
        def __init__(self):
            self.gotos = []

        def goto(self, url, **kw):
            self.gotos.append(url)

        def wait_for_timeout(self, *a, **k):
            pass

    return _P()


# ---------------- ① value 为空必须抛错 ----------------

def test_goto_without_value_raises() -> None:
    """① goto 的 value 为空 -> 必须抛错（旧实现会拿 element 顶替，静默走错）。"""
    from framework.features.f02_semantic.login_flow_explore import run_login_steps

    el = _elref("账号")
    page = _fake_page()
    with pytest.raises(RuntimeError) as ei:
        run_login_steps(page, {"steps": [_step("goto", value=None, element=el).to_dict()]})
    msg = str(ei.value)
    assert "goto 没有地址" in msg, f"错误没点明「goto 没有地址」：{msg}"
    # 核心：绝不许把 ElementRef 的 repr 塞进 goto
    assert page.gotos == [], f"竟然真的调了 goto：{page.gotos}"


# ---------------- ② 带了 element 要提示「可能写混了」 ----------------

def test_goto_error_hints_mixed_op() -> None:
    """② goto 带 element（value 空）时，错误要提示「可能把 goto 和 click 写混了」。"""
    from framework.features.f02_semantic.login_flow_explore import run_login_steps

    el = _elref("账号")
    with pytest.raises(RuntimeError) as ei:
        run_login_steps(_fake_page(), {"steps": [_step("goto", value="", element=el).to_dict()]})
    msg = str(ei.value)
    assert "element 不能当 URL 用" in msg, f"没说清 element 不能当 URL：{msg}"
    assert "账号" in msg, f"没指出是哪个元素（排查靠它）：{msg}"


# ---------------- ③ 正常 goto 不许误拦 ----------------

def test_normal_goto_still_works() -> None:
    """③ value 有值时必须正常 goto，不许被这道校验误伤。"""
    from framework.features.f02_semantic.login_flow_explore import run_login_steps

    page = _fake_page()
    url = "http://localhost:8000/login.html"
    # 只跑 goto 一步；后续成功后它会去等「登录成功条件」，用 pytest.raises 兜住即可
    try:
        run_login_steps(page, {"steps": [_step("goto", value=url).to_dict()]})
    except Exception:
        pass        # 后续等待/校验失败与本判据无关
    assert page.gotos and page.gotos[0] == url, f"正常 goto 没执行：{page.gotos}"


# ---------------- ④ 全仓不许再有同类兜底 ----------------

def test_no_element_as_url_fallback_anywhere() -> None:
    """④ 全仓不许出现「value 为空就拿 element 顶 URL」的写法。"""
    import re

    pat = re.compile(r"str\(\s*st\.value\s+or\s+st\.element")
    hits = []
    for p in (REPO / "framework").rglob("*.py"):
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            code = line.split("#", 1)[0]      # 只看代码，注释里记教训不算违规
            if pat.search(code):
                hits.append(f"{p.relative_to(REPO)}:{i}")
    assert not hits, f"仍有「拿 element 当 URL」的兜底：{hits}"


# ---------------- ⑤ generate 侧口径 ----------------

def test_generate_side_uses_login_url_not_element() -> None:
    """⑤ generate 侧 goto 兜底必须是 `login_url`（不是 element）。"""
    assert 'page.goto(str(st.get("value") or login_url)' in _SRC_GEN, (
        "generate 侧登录 goto 的兜底不是 login_url —— 别退化成 element"
    )
    assert 'st.get("value") or el' not in _SRC_GEN, "generate 侧有把 element 当 URL 的写法"

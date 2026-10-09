# -*- coding: utf-8 -*-
"""特性9 · 动作后置校验（post-condition）：**动作"做了"不等于"生效了"**。

事故（2026-10-10 实测踩到，代价 = 8 分钟 E2E 跑空 + 磁盘取证）：
    demo 订单详情页有一道业务前置 —— **页面有未保存修改时点「提交」不发请求、不报错**，
    只把原因写进状态行（`order_detail.html`: `if (this.dirty) { status='...'; return; }`）。
    而 `_act` 只记「动作执行了」=> 用例一路"成功"跑到下游断言才炸，表现成
    「等不到某个状态」，根因被埋了三层（先怀疑等待时长 -> 再怀疑取数方式 -> 才发现动作从未生效）。

口径（与业务解耦，框架零业务词）：
    · 只对**业务动词**点击校验（表可配）；
    · R2 = 页面提示区出现**拒绝语义**文本（最强、最直接）· R1 = 无导航且无写请求；
    · 默认**只留痕**；`HYBRID_STRICT_EFFECT=1` 时**只让 R2 判失败**（R1 有误伤风险，宁漏不误伤）。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
GEN = REPO / "framework" / "tools" / "generate" / "generator.py"
CLI = REPO / "framework" / "cli.py"


def _tmpl() -> str:
    return GEN.read_text(encoding="utf-8")


def _block() -> str:
    """从 `_CONFTEST_TEMPLATE` 模板字符串里取「后置校验」整段。

    [!] **不能用 AST**：这些函数住在 `_CONFTEST_TEMPLATE = '''...'''` 这个**字符串**里
        （渲染成 `scripts/generated/_harness.py`），不是 generator.py 的真函数。
    """
    src = _tmpl()
    i = src.index("_BIZ_VERBS = (")
    j = src.index("\ndef _act(page, action, semantic=None", i)
    return src[i:j]


def _code_only(body: str) -> str:
    """剔掉整行注释 —— 判据只看真代码（否则注释能骗过判据，本项目踩过 5 次）。"""
    return "\n".join(l for l in body.splitlines() if not l.strip().startswith("#"))


class _Loc:
    def __init__(self, texts):
        self._t = list(texts)

    def count(self):
        return len(self._t)

    def nth(self, i):
        outer = self

        class _N:
            def inner_text(self):
                return outer._t[i]

        return _N()


class FakePage:
    """最小假 page：只提供后置校验用到的那几样。"""

    def __init__(self, url="http://x/a", hints=None, hints_by_selector=None):
        self.url = url
        self._hints = list(hints or [])
        self._by_sel = hints_by_selector or {}
        self.listeners = {}

    def locator(self, sel):
        if self._by_sel:
            return _Loc(self._by_sel.get(sel, []))
        # 默认：所有候选选择器都返回同一批提示文本
        return _Loc(self._hints)

    def on(self, evt, fn):
        self.listeners.setdefault(evt, []).append(fn)


def _load(monkeypatch, **env):
    """把模板里的后置校验代码 exec 到独立命名空间（真跑行为，不是查字符串）。"""
    for k in ("HYBRID_EFFECT_CHECK", "HYBRID_STRICT_EFFECT", "HYBRID_HINT_SELECTORS",
              "HYBRID_REFUSE_HINTS", "HYBRID_BIZ_VERBS"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    logs: list[str] = []
    ns: dict = {"os": __import__("os")}
    exec(compile(_block(), "<template>", "exec"), ns)          # noqa: S102
    ns["_log"] = lambda page, level, msg: logs.append(msg)
    return ns, logs


# ---------- ① 行为：拒绝提示必须被大声报出来（本事故的靶心）----------

def test_refusal_hint_is_reported_with_raw_text(monkeypatch):
    ns, logs = _load(monkeypatch)
    page = FakePage()
    pre = ns["_effect_snapshot"](page, "提交")
    assert pre is not None, "业务动词「提交」必须被纳入校验范围"
    page._hints = ["页面有未保存的修改，请先点「保存」再提交"]     # 动作后出现拒绝提示
    ns["_check_effect"](page, pre, "提交")
    assert logs, "页面明确给出拒绝提示，却完全没有留痕 -> 根因又被埋掉"
    assert "拒绝提示" in logs[0]
    assert "未保存" in logs[0], "必须**原样回读**页面提示文本（这是最直接的根因线索）"


def test_strict_mode_fails_on_refusal(monkeypatch):
    ns, _ = _load(monkeypatch, HYBRID_STRICT_EFFECT="1")
    page = FakePage()
    pre = ns["_effect_snapshot"](page, "提交")
    page._hints = ["页面有未保存的修改，请先点「保存」再提交"]
    with pytest.raises(AssertionError) as ei:
        ns["_check_effect"](page, pre, "提交")
    assert "拒绝提示" in str(ei.value)


# ---------- ② 反向自证（防误伤 / 防空转）----------

def test_healthy_click_produces_no_warning(monkeypatch):
    """正常点击（发生导航）**不许**告警 —— 否则天天误报，用户就会关掉它。"""
    ns, logs = _load(monkeypatch)
    page = FakePage()
    pre = ns["_effect_snapshot"](page, "保存")
    page.url = "http://x/b"                    # 导航发生
    ns["_check_effect"](page, pre, "保存")
    assert logs == [], f"正常点击被误伤: {logs}"


def test_non_business_verb_is_out_of_scope(monkeypatch):
    """非业务动词（如展开菜单）**不参与**校验 —— 与业务解耦，不多管闲事。"""
    ns, logs = _load(monkeypatch)
    page = FakePage()
    assert ns["_effect_snapshot"](page, "展开菜单") is None
    ns["_check_effect"](page, None, "展开菜单")
    assert logs == []


def test_no_nav_no_write_is_flagged(monkeypatch):
    """既没导航也没写请求、又没有新提示 -> 也要留痕（可能被静默忽略）。"""
    ns, logs = _load(monkeypatch)
    page = FakePage()
    pre = ns["_effect_snapshot"](page, "保存")
    ns["_check_effect"](page, pre, "保存")
    assert logs and "无导航" in logs[0]


def test_effect_check_can_be_disabled(monkeypatch):
    ns, logs = _load(monkeypatch, HYBRID_EFFECT_CHECK="0")
    page = FakePage()
    assert ns["_effect_snapshot"](page, "提交") is None
    ns["_check_effect"](page, None, "提交")
    assert logs == []


# ---------- ③ 可配置：不许把 demo 的选择器/词汇写死 ----------

def test_hint_selectors_and_words_are_configurable(monkeypatch):
    ns, logs = _load(monkeypatch,
                     HYBRID_HINT_SELECTORS="#my-tip",
                     HYBRID_REFUSE_HINTS="库存不够")
    page = FakePage(hints_by_selector={"#my-tip": []})
    pre = ns["_effect_snapshot"](page, "提交")
    page._by_sel["#my-tip"] = ["库存不够，无法提交"]              # 自定义选择器 + 自定义拒绝词
    ns["_check_effect"](page, pre, "提交")
    assert logs and "拒绝提示" in logs[0], "自定义的提示区选择器/拒绝词没有生效"


def test_biz_verbs_are_configurable(monkeypatch):
    ns, _ = _load(monkeypatch, HYBRID_BIZ_VERBS="冲销")
    page = FakePage()
    assert ns["_effect_snapshot"](page, "冲销该凭证") is not None, "自定义业务动词没生效"


def test_framework_tables_have_no_business_words():
    """框架层**零业务词**：内置动词表/拒绝词表不许出现本项目的业务名词。"""
    code = _code_only(_block())
    tables = code[: code.index("def _env_csv")]
    for w in ("订单", "发票", "合同", "客户", "销售员", "开票", "物料", "税"):
        assert w not in tables, (
            f"框架内置表里出现了业务词 {w!r} -> 违反「与场景解耦、不写死」；"
            "项目专用词应由 HYBRID_BIZ_VERBS / HYBRID_REFUSE_HINTS 配置注入"
        )


# ---------- ④ 接线：能力必须真挂在动作后（钉住不许被摘掉）----------

def test_effect_check_is_wired_into_act():
    code = _code_only(_block())
    assert "def _check_effect(page, pre, semantic)" in code, "后置校验实现丢了"
    src = _code_only(_tmpl())
    assert "_eff_pre = _effect_snapshot(page, semantic)" in src, "动作前快照没挂进 _act"
    assert "_check_effect(page, _eff_pre, semantic)" in src, "动作后校验没挂进 _act"


def test_knobs_are_registered_in_config():
    """可调项必须可发现（`cli config` 一屏可见，别只活在源码环境变量里）。"""
    src = CLI.read_text(encoding="utf-8")
    for k in ("HYBRID_EFFECT_CHECK", "HYBRID_STRICT_EFFECT",
              "HYBRID_HINT_SELECTORS", "HYBRID_REFUSE_HINTS", "HYBRID_BIZ_VERBS"):
        assert f'("{k}"' in src, f"{k} 没登记进 TUNABLE_CATALOG -> 用户发现不了"


def test_config_catalog_is_valid_python():
    ast.parse(CLI.read_text(encoding="utf-8"))

# -*- coding: utf-8 -*-
"""特性3 · 「编辑态 / 动态新增」补探（C1）。

真值背景（2026-10-10 实测踩到，代价 = 一条全链路用例永远过不去）：
    订单详情页的行内字段是 `<div :readonly="!editing" v-model="ln.material">` ——
    **无 id、无 name**，且**只在「进编辑态 + 点新增行之后」才是输入框**。
    探针按静态 DOM 采（+ 可展开容器补探）=> 一个都进不了清单
    => AI 会填值（M-001/P-001/10）但**绑不到 element** => 映射质量闸拦下整条用例。
    对照组：开票页的行内字段是常显编辑表格，所以它在清单里（`数量@开票页`）——
    同一类控件，差别只在"要不要先点两下才出现"。

判据（一类）：
  E1 纯函数能认出「进编辑态」触发器（可见可点 + 名字命中动词表）
  E2 纯函数能认出「动态新增」触发器
  E3 反向自证：名字不命中动词表的按钮**不被选**
  E4 反向自证：不可见的**不被选**
  E5 反向自证：多个命中时取**最短名字**那个（避免选中复合长名按钮）
  E6 反向自证：`enabled=False` 直接返回空（证明"收得到"来自那两次点击）
  E7 框架零业务词（内置动词表不许出现本项目业务名词）
  E8 接线：探测管线真的调它、且结果并进 merged
  E9 收尾纪律：取不到「取消」类触发器时必须 reload 兜底（框架开的必须由框架关）
  E10 可调项可发现（4 个旋钮登记进 cli config）
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from framework.tools.probe import editable as E                                       # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SCAN = REPO / "framework" / "tools" / "probe" / "page_scan.py"
CLI = REPO / "framework" / "cli.py"


def _code_only(text: str) -> str:
    return "\n".join(l for l in text.splitlines() if not l.strip().startswith("#"))


def _btn(name, role="button", visible=True, extra=None):
    it = {"semantic_name": name, "name": name, "role": role, "visible": visible}
    if extra:
        it.update(extra)
    return it


def test_e1_picks_edit_trigger():
    got = E.pick_verb_opener([_btn("搜索"), _btn("编辑")], E.edit_verbs())
    assert got and got["semantic_name"] == "编辑", got


def test_e2_picks_add_trigger():
    got = E.pick_verb_opener([_btn("编辑"), _btn("新增行")], E.add_verbs())
    assert got and got["semantic_name"] == "新增行", got


def test_e3_ignores_non_verb_button():
    assert E.pick_verb_opener([_btn("搜索"), _btn("导出")], E.edit_verbs()) is None


def test_e4_ignores_invisible():
    assert E.pick_verb_opener([_btn("编辑", visible=False)], E.edit_verbs()) is None


def test_e5_prefers_shortest_name():
    got = E.pick_verb_opener([_btn("编辑并保存并提交全部内容"), _btn("编辑")], E.edit_verbs())
    assert got and got["semantic_name"] == "编辑", got


def test_e6_disabled_returns_empty():
    """负向自证：关掉开关 -> 收不到任何东西（所以"收得到"确实来自那两次点击）。"""
    assert E.enter_editable_and_collect(None, [_btn("编辑")], enabled=False) == []


def test_e7_no_business_words_in_builtin_verbs():
    for name in ("EDIT_VERBS", "ADD_VERBS", "REVERT_VERBS"):
        table = " ".join(getattr(E, name))
        for w in ("订单", "发票", "合同", "客户", "销售员", "物料", "开票", "应收"):
            assert w not in table, f"{name} 里出现了业务词 {w!r} -> 违反「与场景解耦」"


def test_e8_wired_into_scan_pipeline():
    code = _code_only(SCAN.read_text(encoding="utf-8"))
    assert "enter_editable_and_collect(" in code, "探测管线没有调用编辑态补探"
    assert "edit_items" in code, "探测管线没有承接补探结果"
    assert "_merge_items(_merge_items(_merge_items(base, menu), modal), edit_items)" in code, \
        "补探结果没有并进最终清单（等于白探）"


def test_e9_restore_is_mandatory():
    code = _code_only((REPO / "framework" / "tools" / "probe" / "editable.py").read_text(encoding="utf-8"))
    assert "_restore(page" in code, "没有收尾复原（框架开的必须由框架关）"
    assert "reload(" in code, "取不到取消类触发器时必须 reload 兜底"


def test_e10_knobs_registered():
    src = CLI.read_text(encoding="utf-8")
    for k in ("HYBRID_EDITABLE_PROBE", "HYBRID_EDIT_VERBS", "HYBRID_ADD_VERBS",
              "HYBRID_REVERT_VERBS"):
        assert f'("{k}"' in src, f"{k} 没登记进 TUNABLE_CATALOG -> 用户发现不了"


def test_e11_env_switch_disables():
    old = os.environ.get("HYBRID_EDITABLE_PROBE")
    os.environ["HYBRID_EDITABLE_PROBE"] = "0"
    try:
        assert E._default_enabled() is False
    finally:
        if old is None:
            os.environ.pop("HYBRID_EDITABLE_PROBE", None)
        else:
            os.environ["HYBRID_EDITABLE_PROBE"] = old

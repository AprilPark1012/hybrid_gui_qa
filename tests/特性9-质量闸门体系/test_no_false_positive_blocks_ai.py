# -*- coding: utf-8 -*-
"""特性9 · 质量闸门**不许误伤**（V8.4.3 · Windows 实测暴露的两个误拦）。

两次误拦，形态一模一样 —— **AI 是对的，判据错了**（铁律 10：先查它拿到的依据）：

  ① 语义校准：AI 给「展开角色切换菜单」选了右上角头像按钮
     （`name="超"` 是登录用户名，但 `help_text="点击切换角色 / 退出登录"`）。
     `_element_semantics_blob` **漏了 help_text** -> 重叠度 0.00 -> 判「一定选错」。
     紧接着第 4 步 AI 点的正是「切换为订单管理员」—— 它从头到尾都对。

  ② 写死行数据：场景原文逐字写着「（第一行，HT-1001）……故本条走**等价直达**：
     打开新建订单页并把该合同带进去（`order_new.html?contract_no=HT-1001`）」，
     AI 照抄该 URL 完全正确，闸门**从不对照场景原文** -> 判写死 -> 三轮重试全卡死。

判据口径：既要「改对了」（两条误拦消失），也要「没放宽」（真误选仍被拦）。
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from framework.tools.explore.explorer import (   # noqa: E402
    _semantic_sim, _element_semantics_blob, reject_hardcoded_row_values,
    looks_like_hardcoded_row_value,
)


class _St:
    """最小 TestStep 替身（只带闸门读的字段）。"""

    def __init__(self, order, value=None, url=None, element=None, description=""):
        self.order, self.value, self.url, self.element, self.description = \
            order, value, url, element, description


class _El:
    def __init__(self, semantic_name):
        self.semantic_name = semantic_name


# ============ ① 语义校准必须看得见 help_text ============

_ROLE_BTN = {"semantic_name": "超@合同列表页", "role": "button", "name": "超", "text": "超",
             "help_text": "点击切换角色 / 退出登录", "container_heading": "合同管理系统"}


def test_help_text_counts_as_element_semantics():
    """头像按钮的 help_text「点击切换角色」必须参与语义比对（否则 0.00 误杀）。"""
    assert "切换角色" in _element_semantics_blob(_ROLE_BTN)


def test_role_switch_step_no_longer_flagged_as_misselection():
    """实测数值：不含 help_text=0.00（误杀）→ 含 help_text=0.50（放行）。"""
    sim = _semantic_sim("展开角色切换菜单", _element_semantics_blob(_ROLE_BTN))
    assert sim >= 0.3, f"角色切换步骤仍被判误选（sim={sim:.2f}）"


def test_real_misselection_still_flagged():
    """【反向自证】真误选（拿业务数据当控件名）必须仍被拦 —— 不许为变绿而放宽。"""
    for bad_name in ("HT-1001", "全链路-20260101"):
        it = {"name": bad_name, "text": bad_name, "help_text": ""}
        sim = _semantic_sim("展开角色切换菜单", _element_semantics_blob(it))
        assert sim < 0.02, f"真误选 {bad_name} 被放过了（sim={sim:.2f}）"


# ============ ② 写死检测必须对照场景原文 ============

_SCENARIO = (
    "3. 进入合同列表页，**选中一条合同**（第一行，HT-1001）。\n"
    "   故本条走**等价直达**：打开新建订单页并把该合同带进去"
    "（`order_new.html?contract_no=HT-1001`）。\n"
)


def test_value_declared_in_scenario_is_allowed():
    """场景里逐字给出的 URL -> 放行（闸门自己的规矩：字面编号只允许场景逐字给出）。"""
    st = _St(5, url="http://localhost:8000/order_new.html?contract_no=HT-1001",
             description="等价直达新建订单页并带入合同 HT-1001")
    assert reject_hardcoded_row_values([st], scenario_text=_SCENARIO) == []


def test_value_NOT_in_scenario_still_flagged():
    """【反向自证】场景里没有的编号（AI 从页面观测来的）必须仍被判写死。"""
    st = _St(9, value="HT-2002", description="选中第二条合同")
    bad = reject_hardcoded_row_values([st], scenario_text=_SCENARIO)
    assert bad, "场景里没给出的编号被放过了"
    assert "HT-2002" in bad[0]


def test_partial_match_still_flagged():
    """【反向自证】**部分**编号在场景里也不行 —— 必须全部对得上才豁免。"""
    st = _St(9, url="http://localhost:8000/order_new.html?contract_no=HT-1001&extra=SO-9999")
    assert reject_hardcoded_row_values([st], scenario_text=_SCENARIO), "混入一个场景外编号却放行了"


def test_no_scenario_text_means_no_exemption():
    """拿不到场景原文时不豁免（保守：宁错杀，不放过）。"""
    st = _St(5, url="http://localhost:8000/order_new.html?contract_no=HT-1001")
    assert reject_hardcoded_row_values([st]), "无场景原文时不应豁免"


def test_underscore_and_plain_variants_recognized():
    """场景里写 `HT_1001` / 值里写 `HT-1001` 也要认得出是同一个编号。"""
    st = _St(5, value="HT-1001")
    assert reject_hardcoded_row_values([st], scenario_text="选中合同 HT_1001") == []
    assert reject_hardcoded_row_values([_St(5, value="HT1001")],
                                       scenario_text="选中合同 HT-1001") == []


def test_placeholder_value_never_hardcoded():
    """占位/示例形态（`{...}` / `SO-xxxx`）本来就不是写死（既有口径不许被改坏）。"""
    for v in ("{合同编号}", "SO-xxxx", "..."):
        assert not looks_like_hardcoded_row_value(v), f"{v} 被误判为写死"

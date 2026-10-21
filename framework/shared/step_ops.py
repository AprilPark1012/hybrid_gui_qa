# -*- coding: utf-8 -*-
"""步骤动作词表 —— **唯一权威**（L35 抽出，L34-a 的 `_STEP_OPS` 迁到这里）。

为什么必须单独一个模块（不是"文件整齐"的洁癖）：
  同一个动作词表原来活在三个地方 ——
    · `case_builder_generate._STEP_OPS`（控件图层 → 用例层）
    · `case_builder_generate._ASSERT_ACTIONS`（断言类）
    · `scenario_generate._OPS`（登录步骤，还比上面窄：少了 select / press_enter / 跨 tab）
  结果是「同一个 `op` 在不同层有不同合法集」：登录段写 `select` 会被拒，
  而用例步骤写 `select` 是合法的 —— 使用者只能靠试错发现。**一个名字，一套语义。**

依赖方向：`shared/` 是被所有特性层依赖的底座，所以词表放这里，
由 `features/f02_semantic`（用例转换/渲染）与 `shared/login`（登录步骤）共同 import，
不会再出现「shared 反向依赖 features」。
"""
from __future__ import annotations

# 操作类动作：会改变页面状态（每一步都要落到真实控件上，goto 除外）
STEP_OPS = frozenset({
    "goto", "click", "fill", "select", "check", "press_enter",
    # 跨 tab 流程（2026-09-17）：点**会开新 tab** 的控件并切过去 / 点「返回」关当前 tab 回上一个
    "click_new_tab", "close_tab",
})

# 断言类动作：不是"操作步骤"，落 `asserts[]`（不是 `steps[]`）
ASSERT_OPS = frozenset({"expect_text", "expect_url", "expect_first_row"})

# 全部合法动作（白名单的并集；"未知动作"判定只认这一处）
ALL_OPS = STEP_OPS | ASSERT_OPS


def is_known(op: str) -> bool:
    return str(op or "").strip() in ALL_OPS


def unknown_hint(op: str) -> str:
    """未知动作的**统一措辞**（三处报错文案共用，免得同一种错三种说法）。"""
    return (f"未知动作 {str(op or '').strip()!r}：操作类可用 {sorted(STEP_OPS)}，"
            f"断言类可用 {sorted(ASSERT_OPS)}")

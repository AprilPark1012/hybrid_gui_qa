"""页面探测动作的**唯一定义**（V8.3.7 起 · 用户 2026-10-08 选定的方案 B）。

## 为什么要有这个模块

同一个「在页面上做探测」的动作，框架里曾有**三份实现**，各自手写一遍步骤：

  1) `explorer._collect_page_context`      —— 单页探测
  2) `explorer._collect_pages_context`     —— 跨页探测
  3) `generator._probe_declared_pages`     —— generate 现场探测

三者本应等价，实际**第 3 份漏了「可展开容器」那一步**（`expand_and_collect`），
并且弹窗那步只吃了基础清单、没吃菜单清单。

后果（2026-10-08 用户实测）：`python -m framework.cli all --workers 2` 在**干净环境**
（无 `output/element_maps/` 快照）下，拿不到右上角「切换为XX管理员」这类**藏在可展开容器里**的控件
-> `映射质量闸拦下：2 个语义名映射不上 -> 拒绝产出任何产物`（不产出任何产物，包括 element map）。
而在有旧快照的机器上，因快照里恰好存着那两个名字，**问题被掩盖**。

## 本模块的职责边界（重要）

**只负责「页面已就绪之后」的探测动作**，即：

    基础探测(probe_page) -> 可展开容器(expand_and_collect) -> 弹窗/弹层(_try_collect_modal_items) -> 合并(_merge_items)

**不负责**：导航 goto、登录前置、页面就绪等待、场景声明的前置动作（`pre`）、
DOM 上下文与行内列清单的采集 —— 那些由各调用方自己做（它们的入参/时机各不相同）。

这样的切分让三条路径**共享同一份「探测包含哪些步骤」的知识**，
以后新增一步探测动作（例如 iframe 内控件），只需改本模块一处。

## 循环 import 说明

`explorer` 与 `generator` 都在**函数内部**import 本模块（不在模块顶层），
所以本模块可以安全地在顶层 import 它们的私有辅助函数。
"""
from __future__ import annotations

from dataclasses import dataclass, field

# 模块级绑定（供 monkeypatch 与判据替换；不要改成函数内 import）
from framework.tools.probe.probe import probe_page
from framework.tools.probe.expandable import expand_and_collect
from framework.tools.probe.editable import enter_editable_and_collect
from framework.tools.explore.explorer import _try_collect_modal_items, _merge_items

__all__ = ["ScanResult", "scan_page"]


@dataclass
class ScanResult:
    """一次页面探测的结果。

    `items` 是合并去重后的完整清单（调用方真正要用的那份）；
    其余字段保留各阶段的原始产物与计数，供日志/判据使用。
    """

    items: list[dict] = field(default_factory=list)
    base_items: list[dict] = field(default_factory=list)
    menu_items: list[dict] = field(default_factory=list)
    modal_items: list[dict] = field(default_factory=list)

    @property
    def base_count(self) -> int:
        return len(self.base_items)

    @property
    def menu_count(self) -> int:
        return len(self.menu_items)

    @property
    def modal_count(self) -> int:
        return len(self.modal_items)


def scan_page(
    page,
    *,
    page_name: str | None = None,
    tag_page: bool = False,
    with_expand: bool = True,
    with_modal: bool = True,
    with_editable: bool = True,
    settle_s: float = 2.5,
) -> ScanResult:
    """在**已就绪**的页面上做完一套标准探测。

    参数：
      page_name  : 传给 `probe_page` 的页名（影响语义名的页内上下文）。
      tag_page   : 给每一项打上 `page=<page_name>` 标签（跨页路径需要）。
      with_expand: 是否做「可展开容器」补充（隐藏菜单里的控件靠它才拿得到）。
      with_modal : 是否做「弹窗/弹层」补充。
      with_editable: 是否做「编辑态/动态新增」补充（点「编辑」「新增」各一次再重采，探完复原）。
      settle_s   : 展开后等待新控件出现的最长时间（有界轮询，不是固定 sleep）。

    返回 `ScanResult`。
    """
    # 1) 基础探测
    base = probe_page(page, page_name=page_name) if page_name else probe_page(page)

    # 2) 可展开容器（点开隐藏菜单再探一轮，探完自动关掉）
    menu: list[dict] = []
    if with_expand:
        menu = expand_and_collect(page, base, settle_s=settle_s)

    # 3) 弹窗/弹层（必须基于「基础 + 菜单」的并集 —— 事故里第 3 条路径在此也少吃了菜单）
    modal: list[dict] = []
    if with_modal:
        modal = _try_collect_modal_items(page, base + menu)

    # 3.5) 编辑态 / 动态新增（点「编辑」「新增」各一次再重采，探完**复原**）
    #      为什么需要：有些控件**只在编辑态/动态新增之后才存在** —— demo 订单详情的行内字段是
    #      `<div :readonly="!editing" v-model="ln.material">`（无 id/name，编辑态才成输入框），
    #      静态探测与可展开容器补探都拿不到 -> AI 绑不到 element -> 映射质量闸拦下整条用例。
    #      与可展开容器**同一条纪律**：框架开的必须由框架关（取不到取消触发器就 reload）。
    #      关掉：HYBRID_EDITABLE_PROBE=0。
    edit_items: list[dict] = []
    if with_editable:
        edit_items = enter_editable_and_collect(page, base + menu + modal, settle_s=settle_s)

    # 4) 打页名标签（跨页路径要求每一项都带 page）
    if tag_page and page_name:
        for it in menu:
            it["page"] = page_name
        for it in modal:
            it["page"] = page_name
        for it in edit_items:
            it["page"] = page_name

    # 5) 合并成一份清单（与 explore 侧同源的合并语义）
    merged = _merge_items(_merge_items(_merge_items(base, menu), modal), edit_items)

    return ScanResult(
        items=merged,
        base_items=base,
        menu_items=menu,
        modal_items=modal,
    )

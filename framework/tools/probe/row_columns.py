# -*- coding: utf-8 -*-
"""行内列控件（`_当前行`）条目构造 —— **唯一入口**（2026-10-11 V8.4.6 从 explorer 搬来）。

谁在用（两条链路必须用同一份，否则同一页在两条路径上产出不同名字 —— 铁律 13）：
  · explore：`_finalize_map` 造「_当前行」控件给 AI 引用；
  · generate 现场探测：没有 element_map 时的兜底路径（同样要造，否则 AI 用例引用不上）。

本模块**不许**依赖 explorer / browser-use：generate 必须在「没装 AI 依赖」的环境里也能跑。
依赖符号（如 collapse_ws）走本地 import，见函数内注释。
"""
from __future__ import annotations

from framework.tools.common.textutil import collapse_ws      # 与 explorer 同源的口径归一化

def row_columns_to_items(page_name: str, row_fields: list[dict],
                          page_items: list[dict] | None = None) -> list[dict]:
    """把「**没有 data-field 的行内列**」转成**有名字的控件条目**（V8.4.3 · A 方案）。

    为什么走这条路（Windows 实测追了 7 个提交才收敛）：
      勾选列 `<td><input type=checkbox></td>` 没有 data-field，用 `cell_field` 表达不了。
      我把 `cell_by`/`cell_index` 一路补进 Schema、提示词、格式示例、prompt 首位，
      **AI 仍然不填** —— 真实链路走**结构化输出**，而模型对 Schema 里新加的可选字段
      倾向**最小填充**（它把 `semantic_name` 这类旧字段用得滚瓜烂熟，新字段一律省略）。
      => 与其让 AI 学新字段，不如**让这个勾选框成为一个真实存在的控件**：
         AI 用它**已经会**的 `semantic_name` 引用它，由框架翻译成 cell_by=index/cell_index。
      这样与「AI 填不填新字段 / 结构化还是纯文本 / 探针时序」**全部解耦**。

    只转**没有 field** 的列：
      · 有 field 的列本来就靠 `cell_field` 表达（AI 对它很熟）—— 多造条目会污染控件清单、
        改变同名唯一化结果、并让 42 份录像的结构键漂移；
      · 无 field 的列才是「语言表达不了」的那一类（勾选列/操作列…）。
    """
    out: list[dict] = []
    seen: set[tuple[str, int]] = set()
    # 推断「行控件前缀」：该页 role=checkbox 的已有控件里，取 `前缀_后缀` 的公共前缀
    #   （实测：选择订单_SO_2301 / 选择订单_SO_1001 -> 前缀 = 选择订单）
    _row_prefix = ""
    _names = [str(i.get("semantic_name") or "") for i in (page_items or [])
              if str(i.get("role")) in ("checkbox", "radio")]
    _pre = [n.split("_")[0] for n in _names if "_" in n]
    if _pre:
        cand = min(_pre, key=len)
        if all(p.startswith(cand) for p in _pre):
            _row_prefix = cand.strip()
    for rf in row_fields or []:
        if str(rf.get("field") or "").strip():
            continue                      # 有 field -> 交给 cell_field，不造条目
        kind = str(rf.get("kind") or "").strip()
        try:
            idx = int(rf.get("index"))
        except (TypeError, ValueError):
            continue
        key = (str(rf.get("table") or ""), idx)
        if key in seen:
            continue
        seen.add(key)
        # 命名要**贴合这一页已有的行控件语义模式**：
        #   实测该页每一行的勾选框都叫「选择订单_SO_2301」这种（前缀 + 行标识），
        #   而新建的那一行探测时还不存在 -> AI 手上没有它的名字。
        #   所以行内列控件要叫「<同前缀>_当前行」，AI 才会把它当作「选当前这一行」。
        label = {"checkbox": "勾选列", "radio": "选择列"}.get(kind, "列")
        _prefix = _row_prefix or label
        out.append({
            "semantic_name": f"{_prefix}_当前行" if kind == "checkbox" else f"{label}{idx}",
            "role": "checkbox" if kind == "checkbox" else "cell",
            "page": page_name,
            # 框架据此把「引用了这个控件」翻译成行内定位：
            "row_table": rf.get("table"),
            "row_column_index": idx,
            "row_column_kind": kind,
            "nearby_text": f"{page_name} 表格第{idx}列（{label}，无 data-field）",
        })
    return out

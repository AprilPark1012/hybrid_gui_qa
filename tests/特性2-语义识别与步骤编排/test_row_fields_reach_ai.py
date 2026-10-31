"""V8.7.22 判据：行内列清单（`row_fields`）必须落盘并喂回给 AI。

由来（2026-10-29 真链路两次失败，用户 V8.7.21 实测）：
  用例最后一步 AI 写 `expect_text assert=全链路-{datetime}`（想验「搜到了刚建的发票」），
  被**假绿红线**判成「输入回显」拦下 —— 闸门是对的，重试反馈也带了这个原因。

  但错误信息让它「改用 expect_first_row」，而又**没有人给它 `cell_field` 的值**：
    · `cell_field` 是页面 `td[data-field=...]` 的值（`orderName`）
    · 不是表头文案（`订单名称`）
    · 探针**本来就有** header->field 映射（V8.7.16 的 `_fix_first_row_column_by_header` 靠它反查），
      但它只活在 explore 的内存里，**从没落进 elementMap**
      -> case_builder 拿不到 -> 只能干说「用 expect_first_row」
      -> AI 试两次都写同样 -> 「失败原因与上一轮相同」-> 整条链卡死。

修法（A 方案，用户 2026-10-29 拍板）：
  ① `probe_row_fields()` 的产物打上 `page` 标记；
  ② 落进 `ElementMap.page_row_fields`（页名 -> 列清单），`to_dict()` 时并进各页对象；
  ③ `assertion_hard_errors()` 收到映射后，**在错误信息里直接列出可抄的候选**：
     `；可用列 -> 发票列表页: orderName(订单名称)、invoiceNo(发票号)`

守八件事：
  ① `ElementMapPage.to_dict/from_dict` 带 `row_fields`；
  ② `ElementMap.to_dict()` 把 `page_row_fields` 按页名并进各页；
  ③ **单页兜底**：切页给出 `page=""` 时全部塞给这一页（否则数据活着但落盘为空）；
  ④ `load_pages` **不许丢掉**只有 `row_fields` 的页；
  ⑤ `from_data(to_dict())` 的 `page_row_fields` 可读回（不丢数据）；
  ⑥ `_row_field_hint` 格式正确；**空映射返回空串**（没依据不许编）；
  ⑦ `assertion_hard_errors` 传了映射就带上候选、不传则不带；
  ⑧ 静态接线：`_probe_one_page` 打 `page`、`_finalize_map` 传 `page_row_fields`、
     `elementmap_to_cases_file` 把 `m.page_row_fields` 交给闸门。
"""
from __future__ import annotations

import json
from pathlib import Path

from framework.features.f03_locate.element_map import ElementMap, ElementMapPage, TestStep
from framework.features.f02_semantic.case_builder_generate import (
    _row_field_hint,
    assertion_hard_errors,
)

REPO = Path(__file__).resolve().parents[2]

# 真实形状（探针 probe_row_fields() 的产物 + V8.7.22 打的 page）
_PRF = {
    "发票列表页": [
        {"table": "invoiceTable", "field": "orderName", "header": "订单名称",
         "index": 3, "kind": "text", "page": "发票列表页"},
        {"table": "invoiceTable", "field": "invoiceNo", "header": "发票号",
         "index": 0, "kind": "text", "page": "发票列表页"},
        {"table": "invoiceTable", "field": "", "header": "选择",
         "index": 1, "kind": "checkbox", "page": "发票列表页"},
    ],
    "登录页": [
        {"table": "loginForm", "field": "username", "header": "账号",
         "index": 0, "kind": "text", "page": "登录页"},
    ],
}


def _multi_page_map() -> ElementMap:
    steps = [
        TestStep(0, "goto", value="http://x/login.html", desc="打开登录页"),
        TestStep(1, "goto", value="http://x/invoice_list.html", desc="打开发票列表页"),
    ]
    meta = [{"name": "登录页", "url": "http://x/login.html"},
            {"name": "发票列表页", "url": "http://x/invoice_list.html"}]
    return ElementMap(url="http://x/invoice_list.html", scenario="s", steps=steps,
                      probe_items=[], page_meta=meta, page_row_fields=_PRF)


# ---------------- ① 页对象带 row_fields ----------------

def test_page_roundtrip_keeps_row_fields() -> None:
    """① `ElementMapPage` 的 to_dict/from_dict 必须保住 `row_fields`。"""
    pg = ElementMapPage(page="发票列表页", url="http://x/a.html",
                        row_fields=_PRF["发票列表页"])
    d = pg.to_dict()
    assert "row_fields" in d, "to_dict 里没有 row_fields 键 -> 落盘就丢了"
    assert len(d["row_fields"]) == 3
    back = ElementMapPage.from_dict(d)
    assert back.row_fields == _PRF["发票列表页"], "from_dict 读不回来（落盘形态与读取不对称）"


# ---------------- ② to_dict 按页并进去 ----------------

def test_to_dict_merges_row_fields_by_page() -> None:
    """② 多页时每页只拿**自己那页**的列清单（不能串味）。"""
    d = _multi_page_map().to_dict()
    assert len(d) == 2, f"页数应为 2，实际 {len(d)}"
    by_page = {pg.get("page"): pg.get("row_fields") or [] for pg in d}
    assert [r["field"] for r in by_page["登录页"]] == ["username"], by_page["登录页"]
    assert [r["field"] for r in by_page["发票列表页"]] == ["orderName", "invoiceNo", ""], \
        by_page["发票列表页"]


# ---------------- ③ 单页兜底 ----------------

def test_single_page_fallback_when_name_unmatched() -> None:
    """③ 切页给出 `page=""`（页名对不上）时，单页必须把列清单全塞进去。

    为什么必须兜：`normalized_pages()` 在 `steps` 为空或切页失败时会给出空页名，
    这时列清单**只有一份、没有歧义**；不兜就是「数据活着但落盘为空」= 等于没落
    （本项目 V8.5 因这类问题踩过）。
    """
    m = ElementMap(url="http://x/invoice_list.html", scenario="s", steps=[],
                   probe_items=[], page_row_fields={"发票列表页": _PRF["发票列表页"]})
    d = m.to_dict()
    assert len(d) == 1
    assert len(d[0].get("row_fields") or []) == 3, "单页兜底失效 -> 列清单没落盘"


# ---------------- ④ load_pages 不丢页 ----------------

def test_load_pages_keeps_row_fields_only_page() -> None:
    """④ 只有 `row_fields`、没有 steps/probe_items 的页不许被 `load_pages` 丢掉。"""
    from framework.features.f03_locate.element_map import load_pages
    got = load_pages([{"page": "发票列表页", "url": "", "scenario": "",
                       "steps": [], "probe_items": [],
                       "row_fields": _PRF["发票列表页"]}])
    assert len(got) == 1, "只有 row_fields 的页被丢掉了 -> 读回来 page_row_fields 是空"
    assert len(got[0].row_fields) == 3


# ---------------- ⑤ 读回幂等 ----------------

def test_from_data_reads_page_row_fields_back() -> None:
    """⑤ `from_data(to_dict())` 后 `page_row_fields` 必须能读回（不丢数据）。"""
    d = json.loads(json.dumps(_multi_page_map().to_dict(), ensure_ascii=False))
    back = ElementMap.from_data(d)
    assert set(back.page_row_fields) == {"登录页", "发票列表页"}, back.page_row_fields
    assert [r["field"] for r in back.page_row_fields["发票列表页"]] == ["orderName", "invoiceNo", ""]


# ---------------- ⑥ 提示格式 ----------------

def test_row_field_hint_format() -> None:
    """⑥ 提示要「页名: field(header)」，且**没有 data-field 的列不列**（表达不了 cell_field）。"""
    hint = _row_field_hint(_PRF)
    assert "发票列表页" in hint and "orderName(订单名称)" in hint, hint
    assert "invoiceNo(发票号)" in hint, hint
    assert "选择" not in hint, "没有 data-field 的勾选列不该出现在候选里（cell_field 表达不了）"


def test_row_field_hint_empty_is_empty_string() -> None:
    """⑥ 没数据就返回空串 —— **不许编造候选**（本项目铁律：没依据不下判断）。"""
    assert _row_field_hint(None) == ""
    assert _row_field_hint({}) == ""
    assert _row_field_hint({"页": []}) == ""
    assert _row_field_hint({"页": [{"header": "只有表头没 field"}]}) == ""


def test_row_field_hint_is_capped() -> None:
    """⑥ 列特别多的页不许刷屏（截断到 limit）。"""
    rows = [{"field": f"f{i}", "header": f"列{i}"} for i in range(30)]
    hint = _row_field_hint({"大表页": rows}, limit=5)
    assert "f4(列4)" in hint and "f5(列5)" not in hint, hint
    assert "等 30 列" in hint, f"截断时要说明总共有多少列：{hint}"


# ---------------- ⑦ 闸门带候选 ----------------

def _echo_case() -> dict:
    return {"steps": [{"op": "fill", "value": "全链路-{datetime}"}],
            "asserts": [{"kind": "text", "expect": "全链路-{datetime}"}]}


def test_gate_error_lists_cell_field_candidates() -> None:
    """⑦ 传了映射 -> 错误信息里必须有可抄的 `cell_field` 候选（这是本版的核心）。"""
    errs = assertion_hard_errors(_echo_case(), page_row_fields=_PRF)
    assert len(errs) == 1, errs
    msg = errs[0]
    assert "输入回显" in msg, msg
    assert "可用列" in msg, f"错误信息没给候选，AI 还是拼不出 cell_field：{msg}"
    assert "orderName(订单名称)" in msg, msg


def test_gate_error_without_map_has_no_candidates() -> None:
    """⑦ 不传映射就不许编候选（老行为保持不变）。"""
    errs = assertion_hard_errors(_echo_case())
    assert len(errs) == 1
    assert "可用列" not in errs[0], "没数据却给候选 = 编造"


# ---------------- ⑧ 静态接线 ----------------

def test_wiring_static() -> None:
    """⑧ 三处接线必须在位（任一断掉 -> 数据活着但传不到 AI）。"""
    ex = (REPO / "framework/features/f02_semantic/explorer_explore.py").read_text(encoding="utf-8")
    # ① 探测期给每条列打 page
    assert '_rf.setdefault("page", _single_page_name)' in ex, \
        "探测期没给 row_fields 打 page 标记 -> 落盘后无法按页归"
    # ② 收口处传 page_row_fields
    assert "page_row_fields=_prf" in ex, \
        "_finalize_map 没把 page_row_fields 带进 ElementMap -> 落盘为空"
    cb = (REPO / "framework/features/f02_semantic/case_builder_generate.py").read_text(encoding="utf-8")
    # ③ 闸门拿到映射
    assert 'page_row_fields=getattr(m, "page_row_fields", None)' in cb, \
        "elementmap_to_cases_file 没把 m.page_row_fields 交给假绿闸门 -> 错误信息没有候选"

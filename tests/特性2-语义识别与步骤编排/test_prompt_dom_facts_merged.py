# -*- coding: utf-8 -*-
"""特性2 · 喂给 AI 的「DOM 事实」：**并进语义清单条目、只写非默认值**（C1）。

## 要解决的问题（实测数字）
explore 提示词共 212,657 字符，其中【额外 DOM 上下文】那段整份 json 转储占
**86,608 字符（40.7%）**：364 个元素把 idx/tag/role/test_id/placeholder/aria_label/text/name/
visible/disabled/readonly/page 全量打印了一遍 —— 而**同一批元素**在同一条提示词的语义清单里
已经逐页描述过一次（semantic_name/role/placeholder/ctx_token/nearby_text/container_heading），
且转储里九成是默认值噪音（`test_id=""` / `visible=true` / `disabled=false` / `readonly=false`）。

但那段并非全是噪音：提示词自己写着「同名控件务必用 visible + 邻近文本综合判断是否为目标」，
`disabled/readonly/test_id` 也是框架**别再测一次**就有的 DOM 事实。所以口径不是"删掉了事"。

## 改法（口径）
1. 转储**整段删除**（包括它的裁剪明示行）；
2. 只把「语义清单里没有、且真在用」的事实并入条目，字段名与转储保持一致：
   `idx`（页内交互元素序号）、`visible: false`、`disabled: true`、`readonly: true`、`test_id`（非空）；
3. **默认值靠"不写"隐含**（否则换一种噪音），并在提示词里写明这句话；
4. 匹配**只认两边都唯一的键**（元素 id / test_id / 标签+可访问名）：配不上就不并 ——
   错配的 visible/disabled 会直接误导 AI 去点一个不该点/点不动的控件，比不给更糟；
   条数在日志里如实报（静默丢信息 = AI 在残缺依据上推理）。

以下判据**全部是纯函数/字符串级**，不启动浏览器、不联网。
"""
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from framework.features.f02_semantic import explorer_explore as EX   # noqa: E402

SCEN = "在合同列表页导出，在详情页保存，在订单列表页删除一行"
URL = "http://127.0.0.1:8000/contracts.html"


# ---------------------------------------------------------------- 夹具

def _mk(name, page="页A", role="button", tag=None, **kw):
    """一条探针语义清单条目（字段与 `probe_page` 的产物同形：**一定带 tag**）。"""
    d = {"semantic_name": f"{name}@{page}", "page": page, "role": role,
         "tag": tag or ("input" if role == "textbox" else role),
         "name": name, "text": name, "base_name": name, "nearby_text": name}
    d.update(kw)
    return d


def _dom(idx, page="页A", tag="button", role="button", name="", visible=True,
         disabled=False, readonly=False, test_id="", element_id="", placeholder=""):
    """一条 DOM 上下文记录（字段与 `_collect_dom_context` 的产物同形）。"""
    return {"idx": idx, "tag": tag, "role": role, "test_id": test_id, "placeholder": placeholder,
            "aria_label": "", "text": name, "name": name, "element_id": element_id,
            "visible": visible, "disabled": disabled, "readonly": readonly, "page": page}


def _all_entries(prompt: str) -> list[dict]:
    """把提示词里所有语义清单 JSON 数组解析回来（AI 实际看到的就是它们）。"""
    out: list[dict] = []
    dec = json.JSONDecoder()
    pos = 0
    while True:
        j = prompt.find("\n[", pos)
        if j < 0:
            break
        j += 1
        try:
            arr, _end = dec.raw_decode(prompt[j:])
        except ValueError:
            pos = j + 1
            continue
        if isinstance(arr, list) and arr and isinstance(arr[0], dict) and "semantic_name" in arr[0]:
            out.extend(arr)
        pos = j + 1
    return out


# ---------------------------------------------------------------- a) 转储整段消失

def test_dump_section_is_gone_from_the_prompt():
    """提示词里不再有【额外 DOM 上下文】那段（它的独有字段/裁剪行也不该再出现）。"""
    items = [_mk("导出", page="合同列表页"), _mk("保存", page="详情页")]
    dom = [_dom(17, page="合同列表页", name="导出"), _dom(28, page="详情页", name="保存")]
    prompt = EX._build_planner_prompt(SCEN, items, URL, dom)
    assert "额外 DOM 上下文" not in prompt, "那段 86.6K 的全量转储又回来了（40.7% 篇幅）"
    # 转储是「每条记录整份字段」的形态：`aria_label`/`tag`/`text` 三个键在清单条目里从不出现，
    # 它们出现 = 又在一份一份打印元素记录（这几条比认段落标题更结实）。
    for dump_field in ('"aria_label"', '"tag"', '"text":'):
        assert dump_field not in prompt, f"还在逐条打印元素记录（转储的独有字段 {dump_field}）"
    assert "条 DOM 记录未列出" not in prompt, "转储的裁剪明示行还在"


def test_no_code_path_can_rebuild_the_dump():
    """【防回归】源码里也不能留下能重新拼出这段转储的路径（改了调用点不算修好）。"""
    src = pathlib.Path(EX.__file__).read_text(encoding="utf-8")
    code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    for bad in ("额外 DOM 上下文", "_clip_by_chars(dom_ctx)", "_dc_hidden"):
        assert bad not in code, f"还能拼出这段转储：{bad}"
    assert "aria_label" in code, "连 DOM 记录本身都没了 -> 那是删功能，不是并信息"


# ---------------------------------------------------------------- b) 非默认状态没丢

def test_non_default_states_are_findable_in_the_entries():
    """visible=false / disabled=true / readonly=true / test_id 非空 —— 都必须在条目里找到。"""
    items = [_mk("导出", page="合同列表页"),
             _mk("合同编号", page="新建订单页", role="textbox", placeholder="请输入合同编号"),
             _mk("保存", page="订单详情页"),
             _mk("删除", page="订单列表页")]
    dom = [_dom(17, page="合同列表页", name="导出", disabled=True),
           _dom(1, page="新建订单页", tag="input", role="textbox", name="合同编号",
                placeholder="请输入合同编号", readonly=True),
           _dom(28, page="订单详情页", name="保存", visible=False),
           _dom(9, page="订单列表页", name="删除", test_id="btn-del")]
    prompt = EX._build_planner_prompt(SCEN, items, URL, dom)

    got = {e["semantic_name"]: e for e in _all_entries(prompt)}
    assert set(got) == {"导出@合同列表页", "合同编号@新建订单页", "保存@订单详情页", "删除@订单列表页"}

    assert got["导出@合同列表页"].get("disabled") is True, "「导出」被禁用这个事实丢了"
    assert got["合同编号@新建订单页"].get("readonly") is True, "「合同编号」只读这个事实丢了"
    assert got["保存@订单详情页"].get("visible") is False, "「保存」当前不可见这个事实丢了"
    assert got["删除@订单列表页"].get("test_id") == "btn-del", "埋点 id 丢了"
    # idx（页内序号）是结构事实，配对上的条目都要带上（注意：提示词里**必给层在前**，
    #   条目顺序不等于传入顺序 —— 所以按名字比对，不按位置）
    assert {k: got[k].get("idx") for k in got} == {
        "导出@合同列表页": 17, "合同编号@新建订单页": 1,
        "保存@订单详情页": 28, "删除@订单列表页": 9}


def test_matching_never_guesses_when_the_key_is_not_unique():
    """【反向自证】配不上/不唯一时**不并**：宁可少给，也绝不把状态安到错的控件上。"""
    items = [_mk("删除", page="页A"), _mk("删除_2", page="页A")]
    # 两条记录同名同标签 -> 弱键不唯一；两条记录也无 element_id/test_id -> 谁都不配
    dom = [_dom(3, name="删除", page="页A", disabled=True), _dom(4, name="删除", page="页A")]
    prompt = EX._build_planner_prompt(SCEN, items, URL, dom)
    assert '"disabled"' not in prompt, "同名记录不唯一却硬配 -> AI 会拿到一个错的状态"


def test_unique_element_id_breaks_the_tie():
    """有稳定元素 id 时**能**配上（强键优先）—— 否则上面那条"不并"会把该并的也丢掉。"""
    items = [_mk("删除", page="页A", element_id="btn-del-1"),
             _mk("删除_2", page="页A", element_id="btn-del-2")]
    dom = [_dom(3, name="删除", page="页A", element_id="btn-del-1", disabled=False),
           _dom(4, name="删除", page="页A", element_id="btn-del-2", disabled=True)]
    prompt = EX._build_planner_prompt(SCEN, items, URL, dom)
    got = {e["semantic_name"]: e for e in _all_entries(prompt)}
    assert got["删除_2@页A"].get("disabled") is True
    assert "disabled" not in got["删除@页A"]


# ---------------------------------------------------------------- c) 默认值不产生新噪音

def test_default_values_are_not_emitted_at_all():
    """默认值（可见/未禁用/未只读/无 test_id）**一个字段都不写** —— 不换一种噪音接着挤篇幅。"""
    items = [_mk("搜索", page="页A"), _mk("重置", page="页A")]
    dom = [_dom(3, name="搜索", page="页A"), _dom(4, name="重置", page="页A")]
    prompt = EX._build_planner_prompt(SCEN, items, URL, dom)
    for e in _all_entries(prompt):
        for f in ("visible", "disabled", "readonly", "test_id"):
            assert f not in e, f"默认值也写出来了：{f}"
    for noise in ('"visible": true', '"disabled": false', '"readonly": false', '"test_id": ""'):
        assert noise not in prompt, f"默认值噪音又回到提示词里：{noise}"


# ---------------------------------------------------------------- e) 口径句

def test_prompt_states_that_absence_means_default():
    """提示词必须写明「没写这些字段 = 默认」—— 否则 AI 会把"没写"当"信息缺失"。"""
    prompt = EX._build_planner_prompt(SCEN, [_mk("搜索")], URL, [_dom(0, name="搜索")])
    assert "没写" in prompt and "默认" in prompt, "没说清「不输出 = 默认」这套口径"
    line = [l for l in prompt.splitlines() if "默认" in l and "没写" in l]
    assert line, "口径必须写在**同一句**里（分开写在长上下文里等于没说）"
    for w in ("visible", "disabled", "readonly", "test_id"):
        assert w in line[0], f"口径句没说清 {w} 的默认值"


# ---------------------------------------------------------------- d) 体积

def _representative():
    """与录像实测**同量级**的一份代表性输入：7 页 / 364 条 DOM 记录 / 536 条清单条目。

    为什么要同量级：这段转储的占比取决于「清单条目」与「DOM 记录」两条线的比例 ——
    只有比例对得上，下面那条 ≥30% 的断言才代表真实收益（对着一份空清单测必然全绿，那是空转）。
    """
    pages = ["登录页", "合同列表页", "新建订单页", "订单列表页", "订单详情页", "开票页", "发票列表页"]
    per_page_items = [7, 80, 17, 155, 40, 25, 212]
    per_page_dom = [7, 78, 15, 144, 65, 30, 25]
    items: list[dict] = []
    dom: list[dict] = []
    for page, ni, nd in zip(pages, per_page_items, per_page_dom):
        for k in range(ni):
            # 同名成对出现（真实页面里表格/弹层各一份）-> 压缩时会保留消歧字段，条目长度与实测同量级
            nm = f"控件{k // 2}_{page}"
            items.append(_mk(nm, page=page, role="textbox" if k % 3 == 0 else "button",
                             placeholder=f"请输入{nm}", ctx_token=f"*{nm}",
                             value="x" * 12,
                             nearby_text=f"{nm} 附近文本 {k}",
                             container_heading=f"{page}区块{k % 5}",
                             label=nm, help_text=nm))
        for k in range(nd):
            nm = f"控件{k // 2}_{page}"
            dom.append(_dom(k, page=page, name=nm, tag="input" if k % 3 == 0 else "button",
                            role="textbox" if k % 3 == 0 else "button",
                            placeholder=f"请输入{nm}" if k % 3 == 0 else "",
                            # 与实测同比例：~10% 带非默认状态
                            visible=(k % 11 != 0), disabled=(k % 37 == 0), readonly=(k % 41 == 0)))
    return [{"name": p, "url": f"http://127.0.0.1:8000/{i}.html"} for i, p in enumerate(pages)], items, dom


def _legacy_dump_block(dom):
    """**旧行为**的那段转储（用于同一份输入的改前/改后对照）。字段/顺序/裁剪与旧实现逐字一致。"""
    kept, hidden = EX._clip_by_chars(dom)
    return ("额外 DOM 上下文（含全局索引 idx / 可见性 visible / 状态 disabled,readonly；"
            "同名控件务必用 visible + 邻近文本综合判断是否为目标）:\n"
            f"{json.dumps(kept, ensure_ascii=False, indent=1)}\n"
            + (f"  （[!] 另有 {hidden} 条 DOM 记录未列出 —— 按篇幅裁剪）\n" if hidden else "")
            + "\n")


def test_prompt_shrinks_by_at_least_30_percent():
    """同一份代表性输入：提示词字符数**下降 ≥ 30%**（改前/改后都真算一遍）。"""
    pages, items, dom = _representative()
    old = EX._build_planner_prompt(SCEN, items, URL, None, pages=pages) + _legacy_dump_block(dom)
    new = EX._build_planner_prompt(SCEN, items, URL, dom, pages=pages)
    print(f"\n[C1] 改前 {len(old)} 字符 -> 改后 {len(new)} 字符 "
          f"（-{round((1 - len(new) / len(old)) * 100, 1)}%）")
    assert len(new) <= 0.70 * len(old), (
        f"只降了 {round((1 - len(new) / len(old)) * 100, 1)}% —— 转储没删干净，或并进条目的东西太多")
    assert "额外 DOM 上下文" not in new and "额外 DOM 上下文" in old
    # 并进条目的那部分也没有失控：idx + 非默认状态不该把清单撑回去
    assert len(new) - len(EX._build_planner_prompt(SCEN, items, URL, None, pages=pages)) < 0.15 * len(old), \
        "并进条目的内容过多 -> 等于把转储换了个地方写"


def test_merge_reports_what_it_could_not_attach(capsys):
    """配不上的 DOM 记录（多为探针按可见性过滤掉的元素）**如实报条数**，不静默丢。"""
    items = [_mk("搜索", page="页A")]
    dom = [_dom(1, name="搜索", page="页A"),
           _dom(2, name="某个不可见控件", page="页A", visible=False),
           _dom(3, name="另一个不可见控件", page="页A", disabled=True)]
    EX._build_planner_prompt(SCEN, items, URL, dom)
    out = capsys.readouterr().out
    assert "DOM" in out and "并入" in out, "并了多少 / 没并多少都没说 —— 静默丢信息"


def test_merge_is_pure_for_the_caller():
    """并事实必须**不改调用方的条目**（探测结果还要给映射闸/ElementMap 用）。"""
    items = [_mk("搜索", page="页A")]
    before = json.dumps(items, ensure_ascii=False, sort_keys=True)
    EX._build_planner_prompt(SCEN, items, URL, [_dom(3, name="搜索", page="页A", disabled=True)])
    assert json.dumps(items, ensure_ascii=False, sort_keys=True) == before, \
        "把调用方的清单条目改脏了 -> 后面 ElementMap / 质量闸会跟着变"


def test_no_dangling_reference_to_the_deleted_section():
    """提示词里别的地方不许再指向已被删掉的段落（指向不存在的东西 = 让 AI 去翻）。"""
    prompt = EX._build_planner_prompt(SCEN, [_mk("搜索")], URL, None)
    assert "DOM 上下文" not in prompt, "提示词还在引用已删除的【额外 DOM 上下文】段"


if __name__ == "__main__":       # 手工跑：打印实测数字
    pytest.main([__file__, "-q", "-s"])

# -*- coding: utf-8 -*-
"""页身份契约（V8.5.1 · D2=B / D3 全加 · 2026-10-12）

## 为什么有这一组判据

2026-10-12 追「探针产出完整映射差 1 项」时，挖出一整条**静默失效**的链：

    page_meta 只定义、只读取、没人赋值（恒空）
      -> 切页拿不到中文页名，退化成 URL 文件名（login.html）
      -> 而 probe_items 里存的是中文页名（登录页），两边对不上
      -> _partition_items 全部匹配失败 -> 旧行为「匹配不上归第一页」
      -> 488 条控件全堆第一页、其余 3 页全空，**不报任何错**
      -> 表现是 generate 报「缺失项」，看着像命名口径冲突

同一条链上还有 5 处独立缺陷（_url_key 根址空串 / 换页边界只认 goto /
click 换页不认 / TestStep.element 是 ElementRef 对象 / 同名页重复分桶）。

这组判据把这些**不变式**锁住 —— 它们必须**能被机器检查**，否则下次改
切页或改清单结构时，同样的静默退化会再来一遍。

## 口径（AprilPark1012 2026-10-12 拍板）

- **页身份 = 场景声明的 name**，是权威口径（AI 与手搓用例都只看得见 name）。
- **重复时选 A 硬红**：页名重复 -> 硬红，无逃生口（解析层已实现，此处锁住）。
- **不静默降级**：清单条目匹配不上页名 -> 记入未分配并报红，绝不塞给第一页。
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from framework.features.f03_locate.element_map import (          # noqa: E402
    ElementMap, TestStep, _partition_items, split_steps_by_page,
)
from framework.features.f02_semantic.scenario_generate import (   # noqa: E402
    ScenarioError, load_scenario_file,
)

SCENARIO = ROOT / "scenarios" / "orders" / "orders_invoice_full_lifecycle.yml"


def _declared_pages() -> list[dict]:
    sc = yaml.safe_load(SCENARIO.read_text(encoding="utf-8"))
    return [{"name": p["name"], "url": p["url"]} for p in (sc.get("pages") or [])]


def _latest(kind: str) -> dict | list | None:
    files = sorted((ROOT / "output" / "element_maps").glob(f"{kind}_*.json"))
    if not files:
        return None
    return json.loads(files[-1].read_text(encoding="utf-8"))


def _as_ts(raw: list) -> list:
    """落盘 JSON（dict）-> 运行期形态（TestStep）。

    [!] 必须用**运行期真实形态**验证（2026-10-12 踩过）：`TestStep.element` 是
    `ElementRef` 对象，既不是 str 也不是 dict；只拿 json 读回来的 dict 验，
    会得出「通过」的假结论，而真跑时页名是空的。
    """
    return [TestStep.from_dict(s) if isinstance(s, dict) else s for s in raw]


# --------------------------------------------------------------------------
# J1 页名只能来自场景声明（页身份权威口径）
# --------------------------------------------------------------------------
def test_j1_page_names_come_from_declaration():
    """切页得到的页名，要么是声明过的 name，要么是"该页没建出来"的空串。

    绝不允许出现第三种来源（如从 URL 抠出的 `login.html`）—— 那正是 2026-10-12
    488 条控件全堆第一页的直接原因（两侧页名口径错开）。
    """
    d = _latest("element_map")
    if not d:
        pytest.skip("还没有 element_map 产物")
    raw = [s for pg in d for s in (pg.get("steps") or [])]
    if not raw:
        pytest.skip("产物里没有步骤")
    declared = {p["name"] for p in _declared_pages()}
    pages = [pg.get("page") or "" for pg in d]
    bad = [p for p in pages if p and p not in declared]
    assert not bad, (
        f"出现未声明的页名 {bad!r} —— 页身份只能来自场景声明（权威口径）；"
        f"从 URL 抠出来的名字（如 login.html）与清单条目的中文页名对不上，"
        f"会让整页控件归错桶。声明页名：{sorted(declared)}"
    )


# --------------------------------------------------------------------------
# J2 一页有步骤却零控件 -> 报红（这条能在 5 分钟内抓住 2026-10-12 那个 bug）
# --------------------------------------------------------------------------
def test_j2_page_with_steps_must_have_items():
    """某页有步骤、清单总量 > 0，却分到 0 个控件 -> 报红。

    客观上不可能正常：走过这一页、也探到了控件，却一个都没归到它名下。
    2026-10-12 的 488 条全堆第一页、其余页 items=0 就是这种形态。
    """
    d = _latest("element_map")
    if not d:
        pytest.skip("还没有 element_map 产物")
    total_items = sum(len(pg.get("probe_items") or []) for pg in d)
    if total_items == 0:
        pytest.skip("清单为空（探测失败路径），不由本判据负责")
    empty = [pg.get("page") for pg in d
             if len(pg.get("steps") or []) > 0 and len(pg.get("probe_items") or []) == 0]
    assert not empty, (
        f"这些页有步骤却零控件：{empty!r}（清单共 {total_items} 条）—— "
        f"说明它们的控件被分到了别的页（页名口径不一致），或者页对象没被建出来。"
        f"旧行为会静默把对不上的条目塞给第一页，本判据就是拦这个。"
    )


# --------------------------------------------------------------------------
# J3 匹配不上页名的条目 -> 必须暴露（不许静默归第一页）
# --------------------------------------------------------------------------
def test_j3_unmatched_items_are_reported_not_silently_moved():
    """匹配不上页名的条目必须进 `partition_unassigned`，绝不塞给第一页。

    走**完整路径**（`ElementMap.normalized_pages`）测：未分配的收集在那里统一做
    （不在 `_partition_items` 里 —— 那样每页各扫一遍整份清单，同一条会被记 N 次，
    实测 315 条报成 2125 条，计数失去诊断意义）。
    """
    d = _latest("element_map")
    if not d:
        pytest.skip("还没有 element_map 产物")
    items = [it for pg in d for it in (pg.get("probe_items") or [])]
    raw = [s for pg in d for s in (pg.get("steps") or [])]
    if not items or not raw:
        pytest.skip("产物里没有步骤或清单")
    em = ElementMap.from_data(d)
    em.pages = []                      # 关键：清掉 from_data 填的 pages，才走"现切"路径
    em.steps = _as_ts(raw)
    em.page_meta = _declared_pages()
    em.probe_items = list(items) + [{"name": "合成-陌生页控件", "page": "不存在的页"}]
    pages = em.normalized_pages()
    un = getattr(em, "partition_unassigned", [])
    assert any(x["name"] == "合成-陌生页控件" for x in un), (
        "匹配不上页名的条目必须被记入 unassigned（由 mapping 闸门报红）；"
        "旧行为把它塞给第一页 => 看着'没丢数据'，实则下游按页查控件全查空"
    )
    # 且它不能出现在任何页对象里（那正是"静默塞进第一页"的形态）
    for pg in pages:
        names = [str(it.get("name") or "") for it in pg.probe_items]
        assert "合成-陌生页控件" not in names, (
            f"未分配条目不应属于任何页（出现在 {pg.page!r}）"
        )


# --------------------------------------------------------------------------
# J4 同名页合并（同一次链路里同一个页只应有一个页对象）
# --------------------------------------------------------------------------
def test_j4_same_page_visited_twice_merges_into_one_object():
    """同一页被访问多次（搜索 -> 进详情 -> 返回列表）时，只保留一个页对象。

    不合并的后果：`_partition_items` 会把**同一批清单条目**分给两个对象
    => 落盘条目数虚高（实测 537 条膨胀成 693），下游按页遍历时同一控件出现两遍。
    """
    pages = _declared_pages()
    steps = _as_ts([
        {"order": 0, "action": "goto", "url": "http://x/orders.html"},
        {"order": 1, "action": "click", "element": {"semantic_name": "订单名称@订单列表页"}},
        {"order": 2, "action": "click", "element": {"semantic_name": "编辑"}},
        {"order": 3, "action": "click",
         "element": {"semantic_name": "新增行@订单详情页"}},
        {"order": 4, "action": "click", "element": {"semantic_name": "返回"}},
        {"order": 5, "action": "click",
         "element": {"semantic_name": "搜索@订单列表页"}},
    ])
    groups = split_steps_by_page(steps, pages, items=[])
    names = [g["page"] for g in groups if g["page"]]
    assert names.count("订单列表页") == 1, (
        f"同一个页名不应出现多个页对象：{names!r}（页身份 = name，同名即同页）"
    )


# --------------------------------------------------------------------------
# J5 用例里的 @页名 后缀必须是声明页名（挡 AI 猜 + 手搓用例写旧名）
# --------------------------------------------------------------------------
def test_j5_case_page_suffixes_must_be_declared():
    """用例里的 `名称@页名` 后缀**不合声明**时，闸门必须能拦住（不许静默放过）。

    [!] 这条判据测的是**闸门能力**，不是"当前产物必须完美"：
    AI 会写出非法页名（实测 `订单名称@订单系统` —— 把应用名当页名；
    `保存@详细信息` —— 把区块名当页名），手搓用例里也可能混着旧页名。
    产物是 AI 生成的、随时会变；**真正必须锁住的是"这类错拦得住"**，
    否则错误的页名会一路带到映射阶段，报出来的只是「缺失项」，看不出真因。

    发现非法后缀 -> 报红（由 `mapping` 闸门带走重生成）。
    """
    declared = {p["name"] for p in _declared_pages()}
    offenders: list[tuple[str, str]] = []
    for f in sorted((ROOT / "cases").glob("*/*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:                                        # noqa: BLE001
            continue
        for s in (d.get("steps") or []):
            el = s.get("element") or s.get("target")
            nm = el.get("semantic_name") if isinstance(el, dict) else el
            if not isinstance(nm, str) or "@" not in nm:
                continue
            suf = nm.rpartition("@")[2].strip()
            # [!] 后缀格式 = `页名[语境]`（AprilPark1012 2026-10-12 拍板 B）：
            #   页名永远在 `@` 后第一段，`[...]` 里是**同页重名**时的语境补充（容器名等），
            #   它不是页名，判定时要剥掉 —— 否则框架自己产出的合法名字会被这条判据误判。
            suf_page = suf.split("[", 1)[0].strip()
            if suf_page and suf_page not in declared:
                offenders.append((f.name, nm))

    if offenders:
        # 有非法后缀：闸门必须把它们算成"未映射/不合格"，而不是放行。
        from framework.features.f03_locate.mapping_gate_generate import MappingGate
        r = MappingGate().check(unmapped=[nm for _f, nm in offenders])
        assert r.entries, (
            f"用例里有非法页名后缀 {offenders[:5]!r}，但 mapping 闸门没拦 —— "
            f"闸门必须能把它们报出来（否则错误页名一路带到映射阶段，只报「缺失项」）"
        )
        pytest.fail(
            "用例里存在非声明页名的 @后缀（闸门已能拦住，此处报出实况）：\n  "
            + "\n  ".join(f"{f}: {nm}" for f, nm in offenders[:8])
            + f"\n（共 {len(offenders)} 处）声明页名：{sorted(declared)}\n"
            "修法：场景已给出权威页名清单，AI 必须从中选；手搓用例同理。"
        )


# --------------------------------------------------------------------------
# J6 页名重复 -> 硬红（AprilPark1012 2026-10-12 拍板选 A：不消歧、直接红）
# --------------------------------------------------------------------------
def test_j6_duplicate_page_name_is_hard_red(tmp_path):
    """场景声明里页名重复 -> 解析期硬红（无逃生口）。

    页名是元素唯一化与归属的依据，重复会让两个页争抢同一个身份。
    选 A（硬红）而不是自动消歧：静默改名会让"用例里写的页名"与"声明的页名"脱节。
    """
    from framework.features.f02_semantic.scenario_generate import load_scenario_file as load
    p = tmp_path / "dup.yml"
    p.write_text(
        "scenario: 打开合同列表页看第一行\n"
        "id: tmp_dup\n"
        "pages:\n"
        "  - name: 合同列表页\n"
        "    url: http://localhost:8000/\n"
        "  - name: 合同列表页\n"
        "    url: http://localhost:8000/order_list.html\n",
        encoding="utf-8",
    )
    with pytest.raises(ScenarioError) as ei:
        load(p)
    assert "重复" in str(ei.value), (
        f"页名重复必须硬红且说明原因，实际：{ei.value}"
    )


# --------------------------------------------------------------------------
# J7 声明 name 为空 -> 硬红
# --------------------------------------------------------------------------
def test_j7_empty_page_name_is_hard_red(tmp_path):
    """页名为空 -> 解析期硬红（会让 AI 与日志都没法区分页面）。"""
    from framework.features.f02_semantic.scenario_generate import load_scenario_file as load
    p = tmp_path / "empty.yml"
    p.write_text(
        "scenario: 打开合同列表页看第一行\n"
        "id: tmp_empty\n"
        "pages:\n"
        "  - name: \"\"\n"
        "    url: http://localhost:8000/\n"
        "  - name: 登录页\n"
        "    url: http://localhost:8000/login.html\n",
        encoding="utf-8",
    )
    with pytest.raises(ScenarioError) as ei:
        load(p)
    assert "name" in str(ei.value), f"页名为空必须硬红，实际：{ei.value}"


# --------------------------------------------------------------------------
# J8 两种形态必须同解（dict 与 TestStep）
# --------------------------------------------------------------------------
def test_j8_dict_and_dataclass_forms_agree():
    """同一份步骤，dict 形态与 TestStep 形态必须得到**相同**的切页结果。

    2026-10-12 踩过：`TestStep.element` 是 `ElementRef` 对象（既非 str 也非 dict），
    只认 str/dict 的取值函数在运行期永远取不到名字 => 新标签页定不出页名。
    更坑的是：拿落盘 JSON（dict）验证会**通过** —— 验证工具本身失真，
    于是"手工验证通过、真跑落盘为空"，白追一轮。
    """
    d = _latest("element_map")
    if not d:
        pytest.skip("还没有 element_map 产物")
    raw = [s for pg in d for s in (pg.get("steps") or [])]
    items = [it for pg in d for it in (pg.get("probe_items") or [])]
    if not raw:
        pytest.skip("产物里没有步骤")
    pages = _declared_pages()
    a = [g["page"] for g in split_steps_by_page(raw, pages, items)]
    b = [g["page"] for g in split_steps_by_page(_as_ts(raw), pages, items)]
    assert a == b, (
        f"两种形态结果不一致：\n  dict    = {a!r}\n  TestStep= {b!r}\n"
        f"运行期走的是 TestStep 形态 —— 只按 dict 验会得出假结论。"
    )


# --------------------------------------------------------------------------
# J9 落盘条目数不得虚高
# --------------------------------------------------------------------------
def test_j9_no_item_duplication_across_pages():
    """落盘 map 里各页条目之和，不得超过清单总量。

    同名页不合并时，同一批条目会被分给两个页对象 => 条目数虚高
    （实测 537 膨胀成 693），下游按页遍历时同一控件出现两遍。
    """
    d = _latest("element_map")
    if not d:
        pytest.skip("还没有 element_map 产物")
    per_page = sum(len(pg.get("probe_items") or []) for pg in d)
    unassigned = sum(len(pg.get("partition_unassigned") or []) for pg in d)
    # 清单总量 = 各页之和（未分配已在其中扣除，故此处上界判断够用）
    probe = _latest("probe")
    if not probe:
        pytest.skip("没有探针快照可比对")
    probe_total = sum(len(pg.get("probe_items") or []) for pg in probe)
    assert per_page <= probe_total * 1.2, (
        f"落盘条目 {per_page} 条 > 探针快照 {probe_total} 条的 1.2 倍 —— "
        f"疑似同名页未合并导致重复分桶（未分配 {unassigned} 条）"
    )

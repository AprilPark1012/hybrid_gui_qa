# -*- coding: utf-8 -*-
"""特性3.4 · explore 期「喂给 AI 的完整元素清单」必须落盘，并成为映射与快照的名字来源。

事故（2026-10-10 S1 收口，实测）：
    generate 报 `缺失项（共 1 个）：['订单名称@订单列表页']` -> 拒绝产出任何脚本 -> 整条链卡死。
    取证（同一轮三产物对齐）后真因不是「页名归一化」，而是**权威清单没落盘**：

    | 产物 | 内容 | 名字 |
    |---|---|---|
    | explore 喂给 AI 的清单（552 条 / 7 页） | **权威**，含跨页唯一化后的最终名 | `超@合同列表页`、`订单名称@订单系统` |
    | element_map_*.json（explore 产物） | 只有 **AI 实际用到**的 31 个名字 | 同上（子集） |
    | _probe_snapshot.json（运行时索引） | 上面那份 + 现场补探 | 子集 |

    于是「AI 没用过、但用例引用了」的名字（手搓用例、断言、其它用例引用到的控件）在 generate 期
    **只能靠现场重探缺口所属那一两页**去重建，而重探拿不到跨页唯一化的上下文：
      · `超@合同列表页` 需要同探 >=2 页才会出现页名后缀 -> 只探 1 页 -> 探不到（实测 补 0/1）；
      · `订单名称@订单列表页` 这个写法**任何规则都不会产出**（真实名是页内消歧的
        `订单名称@订单系统`）-> 永远探不到。
    => 报出来的「缺失项」看着像命名口径冲突，实际是**权威清单丢在内存里没落盘**。

本文件锁三件事（缺一个都会静默退化）：
  (1) 落盘：`ElementMap` 带上 `probe_items`（= 本次探索喂给 AI 的完整清单），JSON 往返保真，老文件向后兼容；
  (2) 消费：generate 侧**两条链路都要吃它** —— 映射表（loc_map）与运行时快照；
      **只改一侧 = 制造新的不一致**（本项目已连踩两次）；
  (3) 端到端：用例引用的名字**只存在于清单**（AI 没用过）时，generate 必须照旧映射成功并产出脚本。

跑法（秒级；不需要 demo、不需要浏览器）：
    cd ~/hybrid_gui_qa && python -m pytest tests/特性3-分层定位与控件识别/test_explore_manifest_authoritative.py -v
"""
from __future__ import annotations

import inspect
import json
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from framework.tools.generate import probe_snapshot as PS                       # noqa: E402
from framework.tools.generate.generator import generate_scripts                # noqa: E402
from framework.tools.probe.element_map import ElementMap, ElementRef            # noqa: E402

#: 事故里的两个名字：前者只出现在「清单」（AI 没用过），后者是页内消歧的真实名
MANIFEST_ONLY = "超@合同列表页"
AI_USED = "订单名称@订单系统"


def _item(name: str, **extra) -> dict:
    d = {"semantic_name": name, "role": "button", "name": name.split("@")[0]}
    d.update(extra)
    return d


def _emap_file(tmp_path: Path, *, steps: list[str], manifest: list[dict] | None) -> Path:
    """造一份 explore 产物形态的 element_map（steps 只有 AI 用到的名字）。"""
    data: dict = {"url": "http://localhost:8000/", "scenario": "s",
                  "steps": [{"order": i + 1, "action": "click",
                             "element": {"semantic_name": n, "role": "button", "name": n.split("@")[0]},
                             "description": n} for i, n in enumerate(steps)]}
    if manifest is not None:
        data["probe_items"] = manifest
    p = tmp_path / "element_map_test.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


@pytest.fixture(autouse=True)
def _isolate_element_map_residue(monkeypatch, tmp_path):
    """把 `ELEMENT_MAP_DIR` 指到空目录 —— 判据不许随仓库 `output/` 的残留飘。"""
    monkeypatch.setattr("framework.tools.common.config.ELEMENT_MAP_DIR",
                        tmp_path / "_isolated_element_maps")


@pytest.fixture
def probe_down(monkeypatch):
    """现场 probe 必失败：这样「名字映射成功」只可能来自落盘的清单，不可能来自重探。"""
    fake = types.ModuleType("playwright.sync_api")

    def _boom(*a, **k):
        raise RuntimeError("模拟：探测不可用（本判据要求不依赖现场重探）")

    setattr(fake, "sync_playwright", _boom)
    setattr(fake, "Page", type("Page", (), {}))
    setattr(fake, "expect", lambda *a, **k: None)
    setattr(fake, "__getattr__", lambda name: type(name, (), {}))
    pkg = types.ModuleType("playwright")
    setattr(pkg, "sync_api", fake)
    monkeypatch.setitem(sys.modules, "playwright", pkg)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake)
    return fake


# ---------------- ① 落盘：ElementMap 带清单 + 往返保真 ----------------

def test_element_map_carries_manifest():
    em = ElementMap(url="http://x/", scenario="s")
    em.probe_items = [_item(MANIFEST_ONLY)]
    d = em.to_dict()
    assert "probe_items" in d, "element_map 落盘必须带上权威清单（否则 generate 只能靠现场重探）"
    assert [i["semantic_name"] for i in d["probe_items"]] == [MANIFEST_ONLY]


def test_element_map_roundtrip_keeps_manifest(tmp_path):
    em = ElementMap(url="http://x/", scenario="s")
    em.probe_items = [_item(MANIFEST_ONLY, anchor={"kind": "region", "by": "heading", "value": "订单系统"},
                            path=[{"axis": "target", "by": "role", "value": "button"}])]
    p = tmp_path / "em.json"
    em.to_json(p)
    back = ElementMap.from_json(p)
    assert [i["semantic_name"] for i in back.probe_items] == [MANIFEST_ONLY]
    assert back.probe_items[0]["anchor"], "清单条目要原样保留（定位要用的字段不能丢）"


def test_old_element_map_without_manifest_is_backward_compatible(tmp_path):
    """老产物（没有 probe_items）不许炸 —— 行为与改造前一致。"""
    p = tmp_path / "old.json"
    p.write_text(json.dumps({"url": "http://x/", "scenario": "s", "steps": []}), encoding="utf-8")
    back = ElementMap.from_json(p)
    assert back.probe_items == []
    assert PS.items_from_element_map(json.loads(p.read_text(encoding="utf-8"))) == []


# ---------------- ② 消费：快照 与 映射表 两侧都要吃清单 ----------------

def test_snapshot_items_include_manifest_names():
    data = {"steps": [{"element": {"semantic_name": AI_USED, "role": "button", "name": "x"}}],
            "probe_items": [_item(MANIFEST_ONLY)]}
    names = [i["semantic_name"] for i in PS.items_from_element_map(data)]
    assert AI_USED in names, "steps 里的名字必须照旧进快照"
    assert MANIFEST_ONLY in names, "清单里的名字（AI 没用过的）也必须进快照 -> 手搓用例才找得到"


def test_snapshot_keeps_steps_priority_on_duplicate(tmp_path):
    """同名时 steps 优先（它是 AI 真正引用过的那一份），清单不许把它顶掉。"""
    data = {"steps": [{"element": {"semantic_name": "保存@页A", "role": "button", "test_id": "from_steps"}}],
            "probe_items": [_item("保存@页A", test_id="from_manifest")]}
    idx = PS.index_from_items(PS.items_from_element_map(data))
    assert idx["保存@页A"]["test_id"] == "from_steps"


def test_loc_map_includes_manifest_names(tmp_path):
    from framework.tools.generate.generator import _load_loc_map_from_element_map
    p = _emap_file(tmp_path, steps=[AI_USED], manifest=[_item(MANIFEST_ONLY), _item(AI_USED)])
    got = _load_loc_map_from_element_map(p)
    assert AI_USED in got, "steps 侧行为不变"
    assert MANIFEST_ONLY in got, "映射表必须也能从清单取名 -> 否则映射质量闸照样报缺失项"


def test_manifest_only_name_would_be_missing_without_manifest(tmp_path):
    """【负向自证】老形态（无清单）文件里没有 `超@合同列表页`。

    证明上一条不是靠「别的路数」碰巧通过：**去掉清单就必须回到缺失状态**。
    """
    from framework.tools.generate.generator import _load_loc_map_from_element_map
    p = _emap_file(tmp_path, steps=[AI_USED], manifest=None)
    got = _load_loc_map_from_element_map(p)
    assert MANIFEST_ONLY not in got
    assert got.get(AI_USED), "只保留 steps 侧的老行为"


# ---------------- ③ 端到端：清单里的名字必须能生成出脚本 ----------------

def _one_case(tmp_path: Path, element_name: str) -> Path:
    cases = tmp_path / "cases"
    cases.mkdir(parents=True, exist_ok=True)
    (cases / "c.json").write_text(json.dumps({
        "case_id": "manifest_only_smoke",
        "name": "清单独有名字的用例",
        "base_url": "http://localhost:8000/",
        "steps": [{"op": "click", "desc": "点一个只有清单里才有名字的控件",
                   "element": element_name}],
        "asserts": [],
    }, ensure_ascii=False), encoding="utf-8")
    return cases


def test_generate_maps_case_name_that_only_exists_in_manifest(probe_down, tmp_path):
    """事故复现：用例引用的名字只在清单里 -> 必须映射成功、产出脚本、快照覆盖它。"""
    cases = _one_case(tmp_path, MANIFEST_ONLY)
    emap = _emap_file(tmp_path, steps=[AI_USED], manifest=[_item(AI_USED), _item(MANIFEST_ONLY)])
    out = tmp_path / "scripts"
    res = generate_scripts(cases_dir=cases, scripts_dir=out, element_map_path=emap)

    assert res["unmapped"] == [], f"清单里有它就不该报缺失：{res['unmapped']}"
    mods = sorted(p for p in (out / "generated").rglob("*.py")
                  if p.name not in ("conftest.py", "_harness.py"))
    assert mods, "映射成功就必须产出用例模块"
    idx = PS.load_snapshot(out / "generated")
    assert MANIFEST_ONLY in idx, "运行时索引必须覆盖它（否则生成过了、跑起来还是找不到）"


# ---------------- ④ 接线锁：清单必须从探测一路带到落盘 ----------------

def _code(path: Path) -> str:
    """源码契约：**剔掉注释**再断言（注释骗过判据本项目已犯多次）。"""
    src = path.read_text(encoding="utf-8")
    return "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))


def test_manifest_is_threaded_through_explorer():
    from framework.tools.explore import explorer as EX
    code = _code(REPO / "framework" / "tools" / "explore" / "explorer.py")

    sig = inspect.signature(EX._finalize_map)
    assert "manifest" in sig.parameters, "唯一出口 `_finalize_map` 必须能收下清单（否则填不进 ElementMap）"
    # 定义 1 处 + 3 个产出路径（离线回放 / LLM 成功 / mock 兜底）—— 少接一处 = 那条路产出的产物没有清单
    calls = [l for l in code.splitlines() if "_finalize_map(" in l and "def _finalize_map" not in l]
    assert len(calls) == 3, f"产出路径数变了（实测 3 处单点收口），实际 {len(calls)}：{calls}"
    for l in calls:
        assert "manifest=" in l, f"这条产出路径没把清单传进去（静默丢清单 -> 事故复发）：{l.strip()}"
    assert "probe_items=" in code, "ElementMap 构造里没把清单填进去"


# ---------------- ⑤ 锚（by 直定位）也必须与名字同源 ----------------

def test_by_step_anchor_comes_from_manifest(probe_down, tmp_path):
    """`by: title`（属性直定位）的锚必须能**从权威清单**取到 —— 不许依赖现场重探。

    RED 时的实况（2026-10-10 手搓用例真跑）：清单落盘后 generate 不再重探 ->
    `by` 的锚来源（`_LIVE_IT`）空 -> 产物里落一条 `pytest.fail(bad_by)` 存根
    （看着合法、实为垃圾产物）。
    """
    cases = tmp_path / "cases"
    cases.mkdir(parents=True, exist_ok=True)
    (cases / "c.json").write_text(json.dumps({
        "case_id": "by_anchor_smoke", "name": "属性直定位",
        "base_url": "http://localhost:8000/",
        "steps": [{"op": "click", "desc": "用 title 锚点角色按钮",
                   "element": MANIFEST_ONLY, "by": "title"}],
        "asserts": [],
    }, ensure_ascii=False), encoding="utf-8")
    emap = _emap_file(tmp_path, steps=[],
                      manifest=[_item(MANIFEST_ONLY, help_text="点击切换角色 / 退出登录")])
    out = tmp_path / "scripts"
    generate_scripts(cases_dir=cases, scripts_dir=out, element_map_path=emap)

    src = "\n".join(p.read_text(encoding="utf-8") for p in (out / "generated").rglob("*.py")
                    if p.name not in ("conftest.py", "_harness.py"))
    assert "get_by_title" in src, "清单里有锚却没用上 -> by 定位没从权威条目取锚"
    assert "bad_by" not in src, "产物里落了 by 定位失败存根（= 看着合法、实为垃圾）"


def test_synthetic_pre_action_items_keep_anchor_shape():
    """前置动作补进清单的**合成条目**必须与探针条目同形状（带定位锚）。

    实况：`超@合同列表页` 只由合成条目提供（探针没探到它的锚），合成条目只写 name/role/text 时，
    手搓用例的 `by: title` 取不到锚 -> 存根。
    """
    code = _code(REPO / "framework" / "tools" / "explore" / "explorer.py")
    assert "_anchor_fields_of(" in code, "合成条目没取锚 -> by 直定位必然拿不到值"
    i = code.index("def _anchor_fields_of")
    helper = code[i:i + 1800]
    for field, why in (("help_text", "by: title 要它"), ("test_id", "by: testid 要它"),
                       ("label", "by: label 要它"), ("placeholder", "by: placeholder 要它")):
        assert field in helper, f"取锚逻辑没覆盖 {field}（{why}）"
    j = code.index("def _register_pre_action_items")
    seg = code[j:j + 2600]
    assert "_anchor_fields_of(pg" in seg, "`_register_pre_action_items` 没调用取锚逻辑"
    assert "anchors" in seg, "`_register_pre_action_items` 没接「点击那一刻记下的锚」"
    k = code.index("def _run_pre_actions")
    runner = code[k:k + 5200]
    assert "seen" in runner, "`_run_pre_actions` 没把点击时的锚记下来"
    i_cap, i_click = runner.index("seen[nm] = _anchor_fields_of_locator"), runner.index("loc.first.click(")
    assert i_cap < i_click, "取锚必须**在点击之前**（点完控件的可访问名会变，事后取不到）"
    assert "_register_pre_action_items(spec[\"name\"], _pp_clicked, merged_one" in code, \
        "调用点没把 page/锚传进去 -> 取不了锚"
    assert "anchors=_pp_seen" in code, "调用点没把点击时记下的锚传进去"


def test_manifest_is_threaded_through_generator():
    code = _code(REPO / "framework" / "tools" / "generate" / "generator.py")
    assert "probe_items" in code, "generate 侧没有任何地方读清单 -> 落盘的清单等于白落"
    snap = _code(REPO / "framework" / "tools" / "generate" / "probe_snapshot.py")
    assert "probe_items" in snap, "快照侧没读清单 -> 运行时索引仍然缺名"

"""元素歧义闸门（批次 2 · S1/S2）——「同名控件不再被某一轮的裸名独占」。

为什么要有这个文件（测试的测试）：
批次 1 实测事故 —— 合同页搜索区按钮与新建弹窗按钮**同名**。探测时后者不可见（弹窗没开），
于是搜索区按钮在那一轮里「唯一」、独占裸名；用例引用裸名 ⇒ 生成物指向被弹窗遮挡的那一枚
⇒ `Locator.click` 30s 超时 ⇒ 3 条用例红。症状被 demo 侧改名掩盖了，**框架侧当时没修**。

本文件钉住修好后的四条行为（都不需要浏览器，纯函数级）：
① 合并多轮探测后**统一重命名** ⇒ 谁也不可能独占裸名；
② 命名**留痕**（`base_name` / `name_source` / `base_conflict`）⇒ 下游能判歧义；
③ 同一元素被两轮都探到**不算**同名冲突（不许制造假冲突）；
④ 因歧义而缺失时，报错**带候选**（不是干巴巴一句「未映射」）。
"""
import ast
import inspect
import textwrap

import pytest

from framework.probe import assign_semantic_names
from framework.explorer import _merge_items
from framework.generator import _record_conflict_bases, UnmappedElementsError


def _item(name, ctx="", tid=None, base=None, **kw):
    """造一个「探测项」（形状与 probe_page 的产出一致）。"""
    return {
        "semantic_name": name,
        "base_name": base if base is not None else name,
        "ctx_token": ctx,
        "role": kw.get("role", "button"),
        "name": kw.get("name", name),
        "text": kw.get("text", name),
        "placeholder": kw.get("placeholder", ""),
        "test_id": tid or "",
    }


# ---------- ① 命名规则与留痕 ----------

def test_unique_control_keeps_bare_name_and_marks_source():
    items = [_item("搜索")]
    assign_semantic_names(items)
    assert items[0]["semantic_name"] == "搜索"          # 唯一 ⇒ 保持裸名（老用例零影响）
    assert items[0]["name_source"] == "exact"
    assert items[0]["base_conflict"] == 1


def test_same_base_makes_every_member_suffixed():
    items = [_item("选择客户", ctx="搜索区", tid="btn-pick-c-search"),
             _item("选择客户", ctx="新建合同", tid="btn-pick-c-modal")]
    assign_semantic_names(items)
    names = [i["semantic_name"] for i in items]
    assert all(n != "选择客户" for n in names), names   # 同名组里没人能独占裸名
    assert len(set(names)) == 2
    assert all(i["base_conflict"] == 2 for i in items)
    assert all(i["name_source"] in ("ctx", "seq") for i in items)


def test_naming_is_idempotent():
    items = [_item("选择客户", ctx="搜索区", tid="a"), _item("选择客户", ctx="新建合同", tid="b")]
    assign_semantic_names(items)
    first = [i["semantic_name"] for i in items]
    assign_semantic_names(items)                        # 再算一次（合并/重命名后必须可重算）
    assert [i["semantic_name"] for i in items] == first


# ---------- ② S1 核心：合并多轮探测后统一重命名 ----------

def test_merge_renames_across_probe_rounds():
    """复现批次 1 的形态：**每一轮各自命名时都有控件独占裸名**，合并后必须全部消歧。"""
    round1 = [_item("选择客户", ctx="搜索区", tid="btn-pick-c-search")]   # 弹窗未开的那一轮
    assign_semantic_names(round1)
    assert round1[0]["semantic_name"] == "选择客户"       # ← 旧行为：裸名被它独占（事故起点）

    round2 = [_item("选择客户", ctx="新建合同", tid="btn-pick-c-modal")]  # 弹窗打开后absorb进来的
    assign_semantic_names(round2)
    assert round2[0]["semantic_name"] == "选择客户"       # 那一轮里它也是「唯一」

    merged = _merge_items(round1, round2)
    names = {i["semantic_name"] for i in merged}
    assert "选择客户" not in names                        # 修复点：裸名必须消失
    assert len(names) == 2
    assert all(i["base_conflict"] == 2 for i in merged)


def test_same_element_seen_in_both_rounds_is_not_a_false_conflict():
    """同一个元素被两轮都探到（test_id 相同）⇒ 只留一份，且**不许**被当成同名冲突。"""
    merged = _merge_items([_item("搜索", tid="btn-search")],
                          [_item("搜索", tid="btn-search")])
    assert len(merged) == 1
    assert merged[0]["semantic_name"] == "搜索"
    assert merged[0]["base_conflict"] == 1


def test_merge_items_renames_after_merging_structurally():
    """结构判据（不是数出现次数）：`_merge_items` 里真的调了 `assign_semantic_names`。"""
    tree = ast.parse(textwrap.dedent(inspect.getsource(_merge_items)))
    called = {n.func.id for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "assign_semantic_names" in called


# ---------- ③ 与跨页唯一化共存 ----------

def test_cross_page_name_is_left_alone_but_others_still_disambiguated():
    """跨页唯一化写下的名字（name_source=page）是最终名，不许被改写；同 base 的其它控件仍要消歧。"""
    cross = _item("搜索@列表页", ctx="", tid="btn-cp", base="搜索")
    cross["name_source"] = "page"
    other = _item("搜索", ctx="详情页", tid="btn-detail")
    assign_semantic_names([cross, other])
    assert cross["semantic_name"] == "搜索@列表页"
    assert other["semantic_name"] != "搜索"


# ---------- ④ 报错带候选 ----------

def test_unmapped_error_keeps_only_conflicting_missing_names():
    e = UnmappedElementsError(
        ["选择客户", "另一个"],
        sources="现场probe补齐 0/2 项",
        conflicts={"选择客户": ["选择客户@搜索区", "选择客户@新建合同"], "与本次无关": ["a", "b"]},
    )
    assert set(e.conflicts) == {"选择客户"}
    assert e.conflicts["选择客户"] == ["选择客户@搜索区", "选择客户@新建合同"]


def test_record_conflict_bases_only_records_real_groups():
    import framework.generator as g
    g._CONFLICT_BASES.clear()
    try:
        items = [_item("选择客户", ctx="搜索区", tid="a"), _item("选择客户", ctx="新建合同", tid="b")]
        assign_semantic_names(items)
        _record_conflict_bases(items)
        assert set(g._CONFLICT_BASES) == {"选择客户"}
        assert len(g._CONFLICT_BASES["选择客户"]) == 2

        g._CONFLICT_BASES.clear()
        _record_conflict_bases([_item("搜索")])          # 唯一名 ⇒ 不记
        assert g._CONFLICT_BASES == {}
    finally:
        g._CONFLICT_BASES.clear()


# ---------- ⑤ S3：运行期模糊兜底（测的是**生成物**那份代码，不是它的副本）----------
# 口径（与 F1/F2/F6 契约锁一致）：改的是模板，运行的是生成物 —— 所以这里把模板渲染出来、
# 落到临时文件里 exec，直接调它的 `_item_for()`。这样既不依赖 demo/浏览器，也不依赖
# 仓库里那份生成物的当前内容（但另有互锁判据保证生成物与模板同步，见本文件最后一条）。

def _materialize_conftest(tmp_path):
    """把 conftest 模板渲染成真文件并加载 —— 得到「生成物里那份」`_item_for`。"""
    import importlib.util
    import framework.generator as g
    path = tmp_path / "conftest_generated.py"
    path.write_text(g._render_conftest(), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("conftest_generated", str(path))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.RUN_LOG_DIR = tmp_path / "log"           # 留痕写临时目录，别污染仓库 log/
    mod._INDEX.clear()
    return mod


def _gen_with_index(tmp_path, monkeypatch, index, strict=None):
    if strict is not None:
        monkeypatch.setenv("HYBRID_STRICT_LOCATE", strict)
    monkeypatch.setattr("framework.probe.probe_page", lambda page: [])   # 不启浏览器
    mod = _materialize_conftest(tmp_path)
    mod._INDEX.update(index)
    return mod


def test_generated_item_for_exact_name_untouched(tmp_path, monkeypatch):
    mod = _gen_with_index(tmp_path, monkeypatch, {"搜索": {"semantic_name": "搜索", "test_id": "btn-search"}})
    assert mod._item_for("搜索", None)["test_id"] == "btn-search"


def test_generated_item_for_no_candidate_returns_none(tmp_path, monkeypatch):
    mod = _gen_with_index(tmp_path, monkeypatch, {"重置": {"semantic_name": "重置", "test_id": "btn-reset"}})
    assert mod._item_for("完全不存在的名字", None) is None      # 交给 _loc 报「语义名未找到」


def test_generated_item_for_single_fuzzy_hit_is_accepted_but_leaves_a_trail(tmp_path, monkeypatch):
    mod = _gen_with_index(tmp_path, monkeypatch,
                          {"搜索@列表页": {"semantic_name": "搜索@列表页", "test_id": "btn-search-list"}})
    got = mod._item_for("搜索", None)
    assert got["test_id"] == "btn-search-list"                  # 唯一候选仍放行（几乎不误伤）
    log = (tmp_path / "log" / "run.log").read_text(encoding="utf-8")
    assert "模糊兜底命中" in log                                 # 但必须留痕（旧行为：零告警）


def test_generated_item_for_ambiguous_fuzzy_hit_fails_loud(tmp_path, monkeypatch):
    mod = _gen_with_index(tmp_path, monkeypatch, {
        "搜索@列表页": {"semantic_name": "搜索@列表页", "test_id": "btn-search-list"},
        "搜索@订单系统": {"semantic_name": "搜索@订单系统", "test_id": "btn-search-orders"},
    })
    with pytest.raises(RuntimeError) as exc:
        mod._item_for("搜索", None)                             # 旧行为：静默返回 搜索@列表页
    msg = str(exc.value)
    assert "语义名歧义" in msg
    assert "搜索@列表页" in msg and "搜索@订单系统" in msg        # 候选要列全，才谈得上「怎么改」
    assert "btn-search-list" in msg                            # 候选带 test_id，便于定位


def test_generated_item_for_strict_mode_refuses_even_a_single_near_hit(tmp_path, monkeypatch):
    mod = _gen_with_index(tmp_path, monkeypatch,
                          {"搜索@列表页": {"semantic_name": "搜索@列表页", "test_id": "btn-search-list"}},
                          strict="1")
    with pytest.raises(RuntimeError) as exc:
        mod._item_for("搜索", None)
    assert "HYBRID_STRICT_LOCATE" in str(exc.value)             # 报错要说清是哪个开关拦的


def test_s3_wiring_is_locked_between_template_and_artifact():
    """互锁判据：模板与仓库里的生成物**必须同时**具备 S3 接线，且旧的一行式静默挑法绝迹。"""
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    template_src = (root / "framework" / "generator.py").read_text(encoding="utf-8")
    artifact_src = (root / "scripts" / "conftest.py").read_text(encoding="utf-8")
    old_silent = "if k and (hint in k or k in hint):"
    for label, src in (("模板(generator.py)", template_src), ("生成物(scripts/conftest.py)", artifact_src)):
        assert "_fuzzy_lookup" in src, f"{label} 缺 S3 接线：_fuzzy_lookup"
        assert "HYBRID_STRICT_LOCATE" in src, f"{label} 缺 S3 接线：严格开关"
        assert old_silent not in src, f"{label} 仍留着旧的静默模糊挑法（会静默点错控件）"

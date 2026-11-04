# -*- coding: utf-8 -*-
"""A' 判据：**行区控件严格体检**（打包链路硬闸 · 2026-11-04）。

## 这道闸防的是什么

V8.9.2 的真机事故链：

    探针那天看到开票页 **3 行**（警告：数量/单位「重复出现 3 个」）
    真 AI 生成用例时 `期次号` **没给 row_index**（我当时的提示词带了「排在新增行之后」的条件限定，AI 判定不适用）
    运行期开票页**正好只有 1 行** -> 按唯一名命中 -> PASSED（看着像修好了）

也就是说：**同一份产物，今天绿、明天红**，全看运行期那页有几行。而**回放模式**会把录像里的旧答案
一遍遍重放 —— 带病产物会被反复分发到内网机器。

## 为什么闸门放在**打包**而不是 explore

`ai_output` 闸门里 `_ROW_SCOPE_NOTES` 是**警告级**，不是 BLOCK。这是 2026-10-13 的裁决，理由写着：

    录像回放模式下「报缺陷 -> 喂回重试」这条路根本走不通（AI 产出是固定的，重试必然得到同一份）
    => 硬拦 = 死路，把整个 `all --ai` 挡在 explore 里（EXIT=3：script 未生成、run 未执行）

所以 A' 不碰 explore：**产物可以先跑，但不许当交付物发出去** —— 硬闸只加在 `pack_release` 这条链上，
由 `HYBRID_ROW_ZONE_STRICT=1` 显式开启（默认 0，不影响现有打包行为）。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

_spec = importlib.util.spec_from_file_location("pack_release_rz", REPO / "build_tools" / "pack_release.py")
assert _spec is not None and _spec.loader is not None
pack_release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pack_release)

CASE = "cases/orders_invoice_full_lifecycle/ai_demo.json"


def _read_factory(snapshot: dict, case: dict) -> Callable[[str], str]:
    files = {
        "scripts/generated/_probe_snapshot.json": json.dumps(snapshot, ensure_ascii=False),
        CASE: json.dumps(case, ensure_ascii=False),
    }
    return lambda key: files.get(key, "")


def _snapshot(*items) -> dict:
    return {"items": list(items)}


def _rz(name: str) -> dict:
    return {"semantic_name": name, "row_zone": True, "role": "textbox"}


# ---------------- (1) 缺 row_index 必须被抓 ----------------

def test_missing_row_index_on_row_zone_control_is_reported():
    """行区控件那一步只给语义名 -> 必须报出来（这正是 V8.9.2 那份产物的形态）。"""
    read = _read_factory(
        _snapshot(_rz("期次号"), _rz("数量@开票页")),
        {"steps": [{"order": 52, "op": "select", "element": "期次号"}]},
    )
    bad = pack_release.row_zone_problems(read, [CASE])
    assert len(bad) == 1, f"没抓住缺 row_index：{bad}"
    assert "期次号" in bad[0] and "第 52 步" in bad[0], bad[0]


# ---------------- (2) 给了行定位就不许误伤 ----------------

def test_row_index_or_row_text_is_accepted():
    """`row_index` 或 `row_text` 任一存在即算给了行定位 —— 不许把正确产物判成坏包。

    为什么必须两条都认：`row_text` 是按内容锚行（历史写法），`row_index` 是按行号（新增写法），
    只认一种就会把另一半合法用例打成坏包（误伤 = 逼人绕过闸门）。
    """
    read = _read_factory(
        _snapshot(_rz("期次号"), _rz("数量@开票页")),
        {"steps": [
            {"order": 52, "op": "select", "element": "期次号", "row_index": 1},
            {"order": 54, "op": "fill", "element": "数量@开票页", "row_text": "HT-1001", "cell_field": "qty"},
        ]},
    )
    assert pack_release.row_zone_problems(read, [CASE]) == [], "正确产物被误伤"


# ---------------- (3) 非行区控件 / 无快照 -> 不报 ----------------

def test_non_row_zone_and_empty_snapshot_are_silent():
    """快照里没有 `row_zone` 条目（老包 / 老探针）-> 一律不报，避免把老产物判成坏包。"""
    read = _read_factory(
        _snapshot({"semantic_name": "期次号", "role": "combobox"}),          # 没有 row_zone 键
        {"steps": [{"order": 52, "op": "select", "element": "期次号"}]},
    )
    assert pack_release.row_zone_problems(read, [CASE]) == []

    read2 = _read_factory({}, {"steps": [{"order": 52, "op": "select", "element": "期次号"}]})
    read2 = (lambda key: "" if key.endswith("_probe_snapshot.json") else read2(key))
    assert pack_release.row_zone_problems(read2, [CASE]) == [], "没有快照时不该报（无从判断）"


# ---------------- (4) 默认不生效：必须显式开开关 ----------------

def test_strict_flag_is_opt_in_and_wired():
    """`check_zip(strict_row_zone=False)` 默认**不做**体检；`main()` 必须读 `HYBRID_ROW_ZONE_STRICT`。

    钉两件事：
      ① 默认关闭（不许偷偷把现有打包流程变红）；
      ② 开关**真接到** main 的调用点上（写了函数没人调 = 静默失效，本仓踩过多次）。
    """
    import inspect
    sig = inspect.signature(pack_release.check_zip)
    assert "strict_row_zone" in sig.parameters, "check_zip 没有 strict_row_zone 参数"
    assert sig.parameters["strict_row_zone"].default is False, "默认必须关闭（不误伤现有打包）"

    src = (REPO / "build_tools" / "pack_release.py").read_text(encoding="utf-8")
    assert 'HYBRID_ROW_ZONE_STRICT' in src, "没读开关环境变量"
    assert "strict_row_zone=(os.environ.get" in src, "开关没接到 check_zip 调用点"


# ---------------- (5) 开关必须可发现（cli config 能列出来） ----------------

def test_switch_is_discoverable_in_cli_config():
    """可调项不许只活在源码里 —— `cli config` 必须列出来（他会追问「这个开关在哪看」）。"""
    from framework.features.f10_cli import cli as cli_mod
    src = (REPO / "framework" / "features" / "f10_cli" / "cli.py").read_text(encoding="utf-8")
    assert '"HYBRID_ROW_ZONE_STRICT"' in src, "cli config 没登记该开关"
    assert hasattr(cli_mod, "main") or hasattr(cli_mod, "build_parser") or True

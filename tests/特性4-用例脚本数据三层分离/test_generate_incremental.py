"""P20 判据草稿 · 增量生成（**两个触发源**各测一次）。

口径（项目负责人 2026-09-24 定）：
  ① 场景变了 ⇒ 用例 + 脚本都要重新生成（"重新问 AI"由重录拦住 ✓）
  ② 用例变了 ⇒ **只**重做脚本
  ③ demo/页面变了 ⇒ 受影响范围内（逐页指纹 ⇒ 先打印清单）

测试手法：**函数级沙箱**（`generate_scripts(cases_dir=…, scripts_dir=…)` 支持传目录 ✓）
⇒ 不碰仓库里的真产物（一类判据绝不允许改仓库 ✗ —— 这正是 verify_e2e_scenario3_replay 踩过的坑）。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from framework.tools.generate.generator import generate_scripts  # noqa: E402


def _mk_case(cid: str, sid: str, name: str) -> dict:
    return {"case_id": cid, "scenario_id": sid, "name": name, "base_url": "http://localhost:8000",
            "steps": [{"op": "goto", "desc": "打开页面", "url": "http://localhost:8000/default"}],
            "asserts": []}


def _hashes(root: Path) -> dict:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*.py"))}


def _setup(tmp: Path):
    cases = tmp / "cases"
    scripts = tmp / "scripts"
    cases.mkdir(parents=True, exist_ok=True)
    scripts.mkdir(parents=True, exist_ok=True)
    for cid, sid in (("ai_demo_000001", "demo_a"), ("ai_demo_000002", "demo_b"),
                     ("ai_demo_000003", "demo_b")):
        (cases / (cid + ".json")).write_text(
            json.dumps(_mk_case(cid, sid, "用例 " + cid), ensure_ascii=False), encoding="utf-8")
    return cases, scripts


def test_incremental_rewrites_only_the_changed_case(tmp_path):
    """★触发源②：改用例 ⇒ 只有它自己的脚本变，其余**逐字节不变**。"""
    cases, scripts = _setup(tmp_path)
    generate_scripts(cases_dir=cases, scripts_dir=scripts)
    before = _hashes(scripts / "generated")

    target = cases / "ai_demo_000002.json"
    changed = json.loads(target.read_text(encoding="utf-8"))
    changed["name"] = "用例 ai_demo_000002（改过了）"
    target.write_text(json.dumps(changed, ensure_ascii=False), encoding="utf-8")

    generate_scripts(cases_dir=cases, scripts_dir=scripts, changed_only=True)
    after = _hashes(scripts / "generated")
    diff = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
    touched = [k for k in diff if "ai_demo_000002" in k]
    others = [k for k in diff if "ai_demo_000002" not in k]
    assert touched, "✗ 改过的用例脚本没变（增量没生效）⇒ 变化的文件：" + str(sorted(diff))
    assert not others, "✗ 增量却动了别的脚本：" + str(sorted(others)) + "（应逐字节不变）"


def test_incremental_is_idempotent_when_nothing_changed(tmp_path):
    """什么都没改 ⇒ changed_only 再跑一次应**零改动**（否则每次 generate 都在抖）。"""
    cases, scripts = _setup(tmp_path)
    generate_scripts(cases_dir=cases, scripts_dir=scripts)
    before = _hashes(scripts / "generated")
    generate_scripts(cases_dir=cases, scripts_dir=scripts, changed_only=True)
    assert _hashes(scripts / "generated") == before, "✗ 无变更时增量生成动了产物"


def test_index_is_written_and_covers_every_case(tmp_path):
    """index.json 必须写出来且覆盖每条用例（增量生成的唯一依据）。"""
    cases, scripts = _setup(tmp_path)
    generate_scripts(cases_dir=cases, scripts_dir=scripts)
    idx_p = scripts / "generated" / "index.json"
    assert idx_p.is_file(), "✗ 没产出 index.json"
    idx = json.loads(idx_p.read_text(encoding="utf-8"))
    assert set(idx) == {"ai_demo_000001", "ai_demo_000002", "ai_demo_000003"}, "✗ index 覆盖不全：" + str(sorted(idx))

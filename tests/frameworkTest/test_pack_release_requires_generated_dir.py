"""P20 判据草稿 —— 落地时拷进 tests/frameworkTest/（此刻先在仓库外草拟 ✓ 不干扰在跑的验收）。

设计依据：skill 的 `references/design/P20-按id分文件生成脚本与增量生成-方案.md`（口径已获批 ✓）
目标形态：
  cases/<scenario_id>/<case_id>.json
  scripts/generated/<scenario_id>/<case_id>.py      ← 一个用例一个脚本
  scripts/generated/conftest.py
  scripts/generated/index.json                      ← case_id → {script_path, 三种指纹}
  scripts/datasets/<case_id>.json                   ← 已有 ✓ 保持
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PACK = REPO / "build_tools" / "pack_release.py"


def test_pack_release_requires_generated_layout():
    """打包必需项必须覆盖新目录（否则包里缺脚本 ⇒ 交付到 Windows 上跑不起来 ✗）。"""
    t = PACK.read_text(encoding="utf-8")
    assert "scripts/generated" in t or "GENERATED_DIR" in t, (
        "✗ pack_release.py 的必需项没覆盖 scripts/generated/ ⇒ 打出来的包会缺生成脚本")
    assert "index.json" in t, "✗ 必需项没覆盖 scripts/generated/index.json"

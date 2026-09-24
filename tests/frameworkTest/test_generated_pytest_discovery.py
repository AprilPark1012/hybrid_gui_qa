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

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GEN = REPO / "scripts" / "generated"
INDEX = GEN / "index.json"


def test_pytest_really_collects_every_generated_script():
    """★真跑 `pytest scripts/generated/ --collect-only` ⇒ 收集数必须与 index 对得上。

    为什么必须真跑：分文件 + 目录结构会改 pytest 的 rootdir/conftest 解析 ✗
    "脚本写了但收不到"是静默失败（报告会变空、还显示绿）—— 本项目吃过这类亏（L15 教训）。
    """
    assert INDEX.is_file(), f"缺 {INDEX} ⇒ 先跑 generate"
    idx = json.loads(INDEX.read_text(encoding="utf-8"))
    py = str(Path(sys.executable))
    p = subprocess.run([py, "-m", "pytest", str(GEN), "--collect-only", "-q", "-p", "no:cacheprovider"],
                       cwd=str(REPO), capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (p.stdout or "") + (p.stderr or "")
    assert p.returncode == 0, f"✗ 收集失败（exit {p.returncode}）—— 多半是 rootdir/conftest 解析问题：\n{out[-1500:]}"
    collected = [ln for ln in out.splitlines() if "::" in ln]
    assert len(collected) >= len(idx), (
        f"✗ 收集到 {len(collected)} 条 < index 里的 {len(idx)} 条用例 ⇒ 有脚本没被收集到\n{out[-1200:]}")

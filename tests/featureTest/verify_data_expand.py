#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""L1 数据参数化「真展开」· 端到端验证（2026-09-21，服务目标 ① 降人力）。

为什么单独一个脚本、不叫 test_*.py：它要开真浏览器跑真 demo（本机内存紧），
与 `verify_slow_target.py` / `verify_element_ambiguity.py` 同一口径 —— 由 R7 统一入口调。

判据（全真跑）：
  ① **一组数据 = 一条用例**：临时用例（挂在样板场景上，3 组数据）跑出 **3 条独立用例、3 passed**；
  ② **参数名可读**：用例名形如 `test_xxx[编号-1005]`（中文不许被 pytest 转义成 \\uXXXX，
     否则「失败能定位到具体数据集」就废了）；
  ③ ★ **组间隔离**（本项核心价值）：把第 2 组数据改成坏值 ⇒ **只有它 FAILED，另两组仍 PASSED**；
  ④ **单组可跑**：`-k "<cid> and <组id>"` 只跑那一组。
清理：临时用例/数据集全删 + 重跑 generate 复原 `scripts/`（仓库零残留；清理失败会大声报）。

跑法：cd ~/hybrid_gui_qa && .venv/bin/python tests/featureTest/verify_data_expand.py
退出码：0 通过 / 1 失败 / 2 用法 / 3 跳过（内存不足或 demo 不可达 —— **跳过不等于通过**）
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
PY = sys.executable
OK, FAIL, USAGE, SKIP = 0, 1, 2, 3
MIN_MEM_MB = 550                      # 与 run_verifications.sh 同口径（一个 headless Chromium ≈ 515MB）

TMP_CID = "zz_verify_data_expand_tmp"
TMP_CASE = BASE / "cases" / f"{TMP_CID}.json"
def _discover_sample_case() -> Path:
    """按**前缀**发现样例用例（2026-09-24 D3/R10：用例名含生成时间戳，会被重新生成 ⇒ 不许硬编码）。

    口径（R10 触发源②）：用例一变/一换代，引用它的东西必须跟着走 ⇒ 这里用发现而不是写死；
    找不到就直接红，绝不用"随便拿一个"糊过去。
    """
    hits = sorted((BASE / "cases").glob("ai_contracts_search_by_no_*.json"))
    if not hits:
        raise SystemExit(f"❌ 找不到样例用例 ai_contracts_search_by_no_*.json（R10：用例换代号了？"
                         f"请先 `python -m framework.cli explore --ai --scenario-file "
                         f"scenarios/contracts/contracts_search_by_no.yml --llm-cassette`）")
    return hits[-1]


SAMPLE_CASE = _discover_sample_case()
SETS = BASE / "scripts" / "datasets" / f"{TMP_CID}.sets.json"


def force_stdio() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")       # type: ignore[union-attr]
        except Exception:
            pass


def mem_available_mb() -> int:
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) // 1024
    return 10 ** 6


def demo_ok() -> bool:
    try:
        with urllib.request.urlopen("http://localhost:8000/api/health", timeout=4) as r:
            return r.status == 200
    except Exception:
        return False


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(BASE), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def pytest_run(expr: str) -> tuple[int, list[str], list[str]]:
    """跑 -k 表达式，返回 (returncode, passed 用例名, failed 用例名)。"""
    r = run([PY, "-m", "pytest", "scripts/test_cases.py", "-k", expr, "-v", "--no-header",
             "-p", "no:cacheprovider"])
    out = (r.stdout or "") + (r.stderr or "")
    passed = [ln.split("::", 1)[1].split(" ")[0] for ln in out.splitlines() if " PASSED" in ln]
    failed = [ln.split("::", 1)[1].split(" ")[0] for ln in out.splitlines() if " FAILED" in ln]
    return r.returncode, passed, failed


def write_tmp_case() -> None:
    """照样板用例造一条临时用例（同场景、同元素，只有 case_id 不同）。"""
    src = json.loads(SAMPLE_CASE.read_text(encoding="utf-8"))
    src["case_id"] = TMP_CID
    src["name"] = "【验证用】数据参数化端到端（3 组数据 → 3 条用例）"
    TMP_CASE.write_text(json.dumps(src, ensure_ascii=False, indent=2), encoding="utf-8")


def cleanup() -> list[str]:
    """删临时产物 + 重跑 generate 复原；返回残留清单（空 = 干净）。"""
    leftovers: list[str] = []
    for p in (TMP_CASE, SETS, BASE / "scripts" / "datasets" / f"{TMP_CID}.json"):
        if p.exists():
            p.unlink()
    r = run([PY, "-m", "framework.cli", "generate"])
    if r.returncode != 0:
        leftovers.append(f"generate 复原失败（exit {r.returncode}）")
    # ★再删一次（2026-09-24）：上面那次 generate 若因任何原因出错，产物可能被它按旧快照重建；
    #   临时产物**绝不能留在仓库里** —— 一类的产物健康判据会看到它（没 dataset / 有未映射存根）
    #   ⇒ 报出一串看不懂的失败，把下一个人引到错误方向（今天就是这么被带偏的 ✗）。
    for p in (TMP_CASE, SETS, BASE / "scripts" / "datasets" / f"{TMP_CID}.json"):
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass
    for p in (TMP_CASE, SETS, BASE / "scripts" / "datasets" / f"{TMP_CID}.json"):
        if p.exists():
            leftovers.append(f"残留 {p.relative_to(BASE)}")
    if TMP_CID in (BASE / "scripts" / "test_cases.py").read_text(encoding="utf-8"):
        leftovers.append("test_cases.py 里仍残留临时用例")
    return leftovers


def main() -> int:
    force_stdio()
    print("=" * 64)
    print("  L1 数据参数化「真展开」· 端到端验证")
    print(f"  仓库: {BASE}")
    print("=" * 64)

    mem = mem_available_mb()
    if mem < MIN_MEM_MB:
        print(f"  ⏭️  SKIP：MemAvailable {mem}MB < {MIN_MEM_MB}MB —— 内存不足，跳过"
              f"（exit 3，**不是通过**）")
        return SKIP
    print(f"  内存 MemAvailable = {mem}MB")
    if not demo_ok():
        print("  ⏭️  SKIP：demo 不可达（http://localhost:8000/api/health）—— 先 "
              "`python -m demo.app`（exit 3，**不是通过**）")
        return SKIP

    bad: list[str] = []
    try:
        # ---- ① 3 组数据 → 3 条独立用例 ----
        write_tmp_case()
        r = run([PY, "-m", "framework.cli", "generate"])
        if r.returncode != 0:
            print(f"  ❌ generate 失败（exit {r.returncode}）：{(r.stdout or '')[-400:]}")
            return FAIL
        sets = json.loads(SETS.read_text(encoding="utf-8")) if SETS.exists() else []
        print(f"  {'✅' if len(sets) == 3 else '❌'} ① 场景 data 落到 {SETS.name}：{len(sets)} 组")
        generated = (BASE / "scripts" / "test_cases.py").read_text(encoding="utf-8")
        has_deco = f'@pytest.mark.parametrize("ctx", _ds_params({TMP_CID!r})' in generated
        print(f"  {'✅' if has_deco else '❌'} ① 生成的用例带 parametrize(indirect)")
        if len(sets) != 3 or not has_deco:
            bad.append("参数化未生效")

        rc, passed, failed = pytest_run(TMP_CID)
        print(f"  {'✅' if (len(passed) == 3 and not failed) else '❌'} ① 真跑："
              f"{len(passed)} passed / {len(failed)} failed（期望 3/0）")
        if len(passed) != 3 or failed:
            bad.append("3 组数据没跑出 3 条全过用例")

        # ---- ② 参数名可读（中文未被转义）----
        readable = [p for p in passed if "编号-" in p]
        print(f"  {'✅' if len(readable) == 3 else '❌'} ② 参数名可读：{passed or '（无）'}")
        if len(readable) != 3:
            bad.append("参数名被转义或不可读（报告里定位不到数据集）")

        # ---- ③ 组间隔离：把第 2 组改成坏值，只该它红 ----
        good_ids = [p.split("[", 1)[1].rstrip("]") for p in passed if "[" in p]
        tgt = sets[1]
        tgt_id = str(tgt.get("id") or "ds2")
        tgt["期望编号"] = "HT-9999"                    # 不存在的编号 ⇒ 这一组必然失败
        SETS.write_text(json.dumps(sets, ensure_ascii=False, indent=2), encoding="utf-8")
        rc, passed2, failed2 = pytest_run(TMP_CID)
        only_target = len(failed2) == 1 and tgt_id in failed2[0] and len(passed2) == 2
        print(f"  {'✅' if only_target else '❌'} ③ 组间隔离：坏组只有它 FAILED —— "
              f"passed {passed2} / failed {failed2}（期望 2/1，且失败的是 [{tgt_id}]）")
        if not only_target:
            bad.append("坏数据组没有隔离到单行（组间互相污染或定位不准）")

        # ---- ④ 单组可跑 ----
        rc, passed3, failed3 = pytest_run(f"{TMP_CID} and {tgt_id}")
        one_only = len(passed3) + len(failed3) == 1
        print(f"  {'✅' if one_only else '❌'} ④ 单组可跑：-k \"{TMP_CID} and {tgt_id}\" ⇒ "
              f"只跑 1 条（passed {passed3} / failed {failed3}）")
        if not one_only:
            bad.append("单组筛选不可用")
        print(f"  （可读参数名清单：{good_ids}）")
    finally:
        left = cleanup()
        if left:
            print(f"  ❌ 收尾有残留：{left}")
            bad.extend(left)
        else:
            print("  ✅ 收尾：临时用例/数据集已清 + generate 已复原（仓库零残留）")

    print("-" * 64)
    if bad:
        print(f"  ❌ 未通过：{' / '.join(sorted(set(bad)))}")
        return FAIL
    print("  ✅ 全部通过（一组数据 = 一条用例 · 参数名可读 · 坏组只红那一行 · 单组可跑）")
    return OK


# 这里**故意不写** `def test_xxx()` 包装，与其余 8 个 verify 脚本同口径（二类由 R7 统一入口按脚本调）。
# （口径说明：pytest 默认只收集 `test_*.py` / `*_test.py`，本文件叫 verify_*.py 本就不会被一类收；
#   但包装成 test_ 的话，谁哪天改了收集规则 / 手工 -k 选中它，6 分钟的真浏览器端到端就会混进秒级自测
#   —— 本项目踩过「一类被偷偷变成端到端」的坑，所以这里保持 CLI-only。）
if __name__ == "__main__":
    sys.exit(main())

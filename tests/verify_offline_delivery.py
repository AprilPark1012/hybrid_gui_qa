#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""交付形态判据：「两件套」必须打得出来、且各自内部完整（不碰仓库、不联网）。

为什么单独一条：**没有外网的机器**要跑 AI 链路，靠的是「代码包 + 录像包」**两件套**
（代码包里有回放引擎，录像包里有 LLM 的 prompt→回答 数据）。
2026-09-19 之前录像包由一个**仓库外的独立脚本**打 ⇒ 没有任何判据、交付形态全靠人记；
实测后果：把新代码包单独发给团队，对方**根本跑不起来**（缺录像数据），而没人会发现。

判据（每条都在 /tmp 里做，仓库零副作用）：
1. 代码包能打出且包内自检通过，并且**不含录像**（`output/` 永不进包 —— 运行时数据不进交付物）
2. 录像包能打出，且含：录像 `llm_cassettes/*.json` + 用法说明 + 一键脚本 `build_tools/offline_explore_chain.py`
3. 录像包的用法说明里必须写清「端点指黑洞 127.0.0.1:9」（可证伪性：证明真的没联网）
4. `SHA256SUMS.txt` 与目录里**现存包**逐个 sha256 一致（清单不许与事实脱节）

跑法： python tests/verify_offline_delivery.py
      python -m pytest tests/verify_offline_delivery.py -q
退出码：0 通过 / 1 失败 / 2 用法 / 3 跳过（缺录像 ⇒ 不是失败，但要如实说）
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PY = sys.executable
OK, FAIL, USAGE, SKIP = 0, 1, 2, 3


def force_stdio():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")       # type: ignore[union-attr]
        except Exception:
            pass


def main() -> int:
    force_stdio()
    print("=" * 64)
    print("  交付形态判据 · 离线链路「两件套」（代码包 + 录像包）")
    print(f"  仓库: {BASE}")
    print("=" * 64)
    if not (BASE / "build_tools" / "pack_release.py").exists():
        print("  ⏭️ 跳过：找不到 build_tools/pack_release.py")
        return SKIP

    cass = sorted((BASE / "output" / "llm_cassettes").glob("*.json"))
    if not cass:
        print("  ⏭️ 跳过：本机没有录像（output/llm_cassettes 为空）——"
              " 录像要在**有外网**的机器上 `--llm-record` 录；这条跳过**不等于通过**")
        return SKIP

    tmp = Path(tempfile.mkdtemp(prefix="verify_offline_delivery_"))
    bad: list[str] = []
    try:
        r = subprocess.run([PY, "build_tools/pack_release.py", "--out", str(tmp), "--with-cassettes"],
                           cwd=str(BASE), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        out = (r.stdout or "") + (r.stderr or "")
        if r.returncode != 0:
            print(f"  ❌ 打包失败（exit={r.returncode}）：{out[-500:]}")
            return FAIL

        code_zips = [p for p in tmp.glob("hybrid_gui_qa_V*.zip")]
        cas_zips = [p for p in tmp.glob("*llm_cassettes_*.zip")]
        print(f"  {'✅' if code_zips else '❌'} ① 代码包已产出：{[p.name for p in code_zips]}")
        print(f"  {'✅' if cas_zips else '❌'} ① 录像包已产出：{[p.name for p in cas_zips]}")
        if not (code_zips and cas_zips):
            bad.append("两件套没齐")

        if code_zips:
            with zipfile.ZipFile(code_zips[0]) as z:
                names = z.namelist()
                broken = z.testzip()
            leaks = [n for n in names if "llm_cassettes/" in n]
            has_engine = any(n.endswith("framework/tools/explore/llm_cassette.py") for n in names)
            has_helper = any(n.endswith("build_tools/offline_explore_chain.py") for n in names)
            print(f"  {'✅' if not broken else '❌'} ② 代码包 zip 完整（testzip = {broken}）")
            print(f"  {'✅' if has_engine else '❌'} ② 代码包含回放引擎 framework/tools/explore/llm_cassette.py")
            print(f"  {'✅' if has_helper else '❌'} ② 代码包含一键脚本 build_tools/offline_explore_chain.py")
            print(f"  {'✅' if not leaks else '❌'} ③ 代码包**不含录像**（不夹带运行时数据）：命中 {len(leaks)} 条")
            if broken or not has_engine or not has_helper or leaks:
                bad.append("代码包内容不符")

        if cas_zips:
            with zipfile.ZipFile(cas_zips[0]) as z:
                names = z.namelist()
                broken = z.testzip()
                readme = z.read("llm_cassettes_README.md").decode("utf-8") \
                    if "llm_cassettes_README.md" in names else ""
            n_rec = len([n for n in names if n.startswith("llm_cassettes/") and n.endswith(".json")])
            print(f"  {'✅' if not broken else '❌'} ④ 录像包 zip 完整（testzip = {broken}）")
            print(f"  {'✅' if n_rec == len(cass) else '❌'} ④ 录像份数：包内 {n_rec} / 本机 {len(cass)}")
            print(f"  {'✅' if 'offline_explore_chain.py' in ' '.join(names) else '❌'} "
                  f"④ 录像包含一键脚本")
            print(f"  {'✅' if '127.0.0.1:9' in readme else '❌'} ④ 用法说明写明「端点指黑洞」"
                  f"（可证伪性）")
            if broken or n_rec != len(cass) or "127.0.0.1:9" not in readme:
                bad.append("录像包内容不符")

        sums = tmp / "SHA256SUMS.txt"
        if not sums.exists():
            print("  ❌ ⑤ 没有生成 SHA256SUMS.txt")
            bad.append("缺清单")
        else:
            listed = {}
            for line in sums.read_text(encoding="utf-8").splitlines():
                if line.strip() and not line.startswith("#"):
                    h, name = line.split(None, 1)
                    listed[name.strip()] = h
            actual = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp.glob("*.zip")}
            same = listed == actual
            print(f"  {'✅' if same else '❌'} ⑤ 清单与现存包逐个 sha256 一致"
                  f"（清单 {len(listed)} 条 / 现存 {len(actual)} 个）")
            if not same:
                bad.append("清单与包不一致")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("-" * 64)
    if bad:
        print(f"  ❌ 未通过：{' / '.join(bad)}")
        return FAIL
    print("  ✅ 全部通过（代码包 + 录像包都能打、内容齐、清单与事实一致）")
    return OK


def test_offline_delivery_form():          # pytest 入口
    force_stdio()
    assert main() == OK


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""交付形态判据：**一个 zip** 必须打得出来、内容齐、且不夹带运行时证据（不碰仓库、不联网）。

为什么单独一条：**没有外网的机器**要跑 AI 链路，靠的是包里的两样东西 ——
回放引擎（`framework/features/f08_replay/llm_cassette_explore.py`）
+ 录像数据（`output/llm_cassettes/*.json` 的「prompt -> 回答」原件）。
2026-09-19 之前录像由一个**仓库外的独立脚本**打 -> 没有任何判据、交付形态全靠人记；
实测后果：把新代码包单独发给团队，对方**根本跑不起来**（缺录像数据），而没人会发现。

[!] 2026-10-14 口径纠正（用户）：录像本来就住在工程 `output/` 下，
    「整个工程打包」自然要把它带进**同一个** zip ——
    旧的「两件套（代码包 + 独立录像包）」**已废弃**，此处顺带**反向拦截**它复活。

判据（每条都在 /tmp 里做，仓库零副作用）：
1. 打包能出且退出码 0，产出**恰好一个** `hybrid_gui_qa_V*.zip`，
   且**没有**第二个 `*llm_cassettes_*.zip`（防「两件套」偷偷回来）
2. 包内自检通过、zip 完整（testzip），含回放引擎 + 一键脚本 `build_tools/offline_explore_chain.py`
3. **含录像**：`output/llm_cassettes/*.json` 份数与本机一致
4. 包内 `output/llm_cassettes/README.md` 用法说明里写明「端点指黑洞 127.0.0.1:9」
   （可证伪性：证明离线回放真的没联网）
5. `output/` 下只放行 `element_maps/`（最新 1 份）与 `llm_cassettes/`；
   `log/` 与其它运行时证据（traces / verify / archived_* / *_shots）不得进包
6. `SHA256SUMS.txt` 与目录里**现存包**逐个 sha256 一致（清单不许与事实脱节）

跑法： python tests/特性1-混合链路/verify_offline_delivery.py
      python -m pytest tests/特性1-混合链路/verify_offline_delivery.py -q
退出码：0 通过 / 1 失败 / 2 用法 / 3 跳过（缺录像 -> 不是失败，但要如实说）
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent
PY = sys.executable
OK, FAIL, USAGE, SKIP = 0, 1, 2, 3

README_REL = "output/llm_cassettes/README.md"


def force_stdio():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")       # type: ignore[union-attr]
        except Exception:
            pass


def main() -> int:
    force_stdio()
    print("=" * 64)
    print("  交付形态判据 · 离线链路（**一个 zip**：代码 + 回放引擎 + 录像）")
    print(f"  仓库: {BASE}")
    print("=" * 64)
    if not (BASE / "build_tools" / "pack_release.py").exists():
        print("  [skip] 跳过：找不到 build_tools/pack_release.py")
        return SKIP

    cass = sorted((BASE / "output" / "llm_cassettes").glob("*.json"))
    if not cass:
        print("  [skip] 跳过：本机没有录像（output/llm_cassettes 为空）——"
              " 录像要在**有外网**的机器上 `--llm-record` 录；这条跳过**不等于通过**")
        return SKIP

    tmp = Path(tempfile.mkdtemp(prefix="verify_offline_delivery_"))
    bad: list[str] = []
    try:
        # [!] 不再传 `--with-cassettes`：录像**总是**随代码包交付（那个开关已废弃）
        r = subprocess.run([PY, "build_tools/pack_release.py", "--out", str(tmp)],
                           cwd=str(BASE), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        out = (r.stdout or "") + (r.stderr or "")
        if r.returncode != 0:
            print(f"  [NG] 打包失败（exit={r.returncode}）：{out[-500:]}")
            return FAIL

        code_zips = sorted(tmp.glob("hybrid_gui_qa_V*.zip"))
        cas_zips = sorted(tmp.glob("*llm_cassettes_*.zip"))
        print(f"  {'[OK]' if code_zips else '[NG]'} (1) 主包已产出：{[p.name for p in code_zips]}")
        print(f"  {'[OK]' if not cas_zips else '[NG]'} (1) **没有**第二个录像包"
              f"（交付只有一个 zip）：{[p.name for p in cas_zips]}")
        if not code_zips:
            bad.append("主包没打出来")
        if cas_zips:
            bad.append("又出现了独立的录像包（两件套复活）")

        if code_zips:
            with zipfile.ZipFile(code_zips[0]) as z:
                names = z.namelist()
                broken = z.testzip()
                # [!] 包内路径带 tag 前缀（`hybrid_gui_qa_V…/output/llm_cassettes/README.md`），
                #     按**后缀**找 —— 精确名匹配只能命中不带前缀的形态（会把自己判成 NG）。
                _rm = next((n for n in names if n.endswith("/" + README_REL)), None)
                readme = z.read(_rm).decode("utf-8", "replace") if _rm else ""
            has_engine = any(n.endswith("framework/features/f08_replay/llm_cassette_explore.py")
                             for n in names)
            has_helper = any(n.endswith("build_tools/offline_explore_chain.py") for n in names)
            n_rec = len([n for n in names
                         if "/output/llm_cassettes/" in n and n.endswith(".json")])
            leaks = [n for n in names
                     if "/output/" in n and "element_maps/" not in n and "llm_cassettes/" not in n]
            logs = [n for n in names if "/log/" in n or n.endswith("/log")]
            print(f"  {'[OK]' if not broken else '[NG]'} (2) zip 完整（testzip = {broken}）")
            print(f"  {'[OK]' if has_engine else '[NG]'} (2) 含回放引擎 llm_cassette_explore.py")
            print(f"  {'[OK]' if has_helper else '[NG]'} (2) 含一键脚本 offline_explore_chain.py")
            print(f"  {'[OK]' if n_rec == len(cass) else '[NG]'} (3) 录像在**同一个**包里："
                  f"包内 {n_rec} / 本机 {len(cass)}")
            print(f"  {'[OK]' if '127.0.0.1:9' in readme else '[NG]'} (4) 录像用法说明写明"
                  f"「端点指黑洞」（可证伪性）")
            print(f"  {'[OK]' if not logs else '[NG]'} (5) 不含 log/：命中 {len(logs)} 条")
            print(f"  {'[OK]' if not leaks else '[NG]'} (5) output/ 下只放行 element_maps + "
                  f"llm_cassettes：越界 {len(leaks)} 条 {leaks[:3]}")
            if (broken or not has_engine or not has_helper or n_rec != len(cass)
                    or "127.0.0.1:9" not in readme or logs or leaks):
                bad.append("包内容不符")

        sums = tmp / "SHA256SUMS.txt"
        if not sums.exists():
            print("  [NG] (6) 没有生成 SHA256SUMS.txt")
            bad.append("缺清单")
        else:
            listed = {}
            for line in sums.read_text(encoding="utf-8").splitlines():
                if line.strip() and not line.startswith("#"):
                    h, name = line.split(None, 1)
                    listed[name.strip()] = h
            actual = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp.glob("*.zip")}
            same = listed == actual
            print(f"  {'[OK]' if same else '[NG]'} (6) 清单与现存包逐个 sha256 一致"
                  f"（清单 {len(listed)} 条 / 现存 {len(actual)} 个）")
            if not same:
                bad.append("清单与包不一致")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("-" * 64)
    if bad:
        print(f"  [NG] 未通过：{' / '.join(bad)}")
        return FAIL
    print("  [OK] 全部通过（一个 zip：代码 + 回放引擎 + 录像 + 用法说明，清单与事实一致）")
    return OK


def test_offline_delivery_form():          # pytest 入口
    force_stdio()
    assert main() == OK


if __name__ == "__main__":
    sys.exit(main())

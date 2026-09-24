"""AI 用例与场景的**同步**判据（D3 · 2026-09-24 他定）。

**他的原话**：「补一条 AI 用例，但是**如果关联的 scenario 变化了，它就要刷新过来，保证同步**。」

⇒ 机制：每条 AI 用例落盘时记下**它来自哪个场景、以及当时场景文件的内容指纹**。
   场景文件一改（指纹变）⇒ 判据当场红 ⇒ 必须跑一次刷新命令重新生成，才能绿。
   刷新命令（用录像回放，不花 token）：
     `python -m framework.cli explore --ai --scenario-file scenarios/xxx.yml --llm-cassette`
     然后 `python -m framework.cli generate`

判据：
  ① 每条 `cases/ai_*.json` 都要带 `scenario_id` + `scenario_fingerprint`
  ② 指纹必须与**当前**场景文件的内容一致（不一致 ⇒ 场景改过而用例没刷新 ⇒ 红）
  ③ `scenario_id` 必须指向真实存在的场景（与 R7-f 同源，这里只做交叉引用）
  ④ 负向自证：改一个字 ⇒ 指纹必须变（否则判据永远绿、等于没写）
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CASES = REPO / "cases"
SCEN = REPO / "scenarios"


def scenario_files() -> dict[str, Path]:
    return {p.stem: p for p in SCEN.rglob("*.yml")}


def fingerprint(path: Path) -> str:
    """场景文件内容指纹（只跟内容有关，与路径/时间无关）。"""
    data = path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:16]


def ai_cases() -> list[tuple[Path, dict]]:
    out = []
    for p in sorted(CASES.glob("ai_*.json")):
        try:
            out.append((p, json.loads(p.read_text(encoding="utf-8", errors="replace"))))
        except Exception:  # noqa: BLE001
            out.append((p, {}))
    return out


def stale() -> list[str]:
    """返回「场景改过但用例没刷新」的清单（<用例>:<原因>）。"""
    scen = scenario_files()
    bad: list[str] = []
    for p, payload in ai_cases():
        sid = str(payload.get("scenario_id", "")).strip()
        fp = str(payload.get("scenario_fingerprint", "")).strip()
        if not sid:
            bad.append(f"{p.stem}:<缺 scenario_id>")
            continue
        if sid not in scen:
            bad.append(f"{p.stem}:<场景 {sid} 不存在>")
            continue
        if not fp:
            bad.append(f"{p.stem}:<缺 scenario_fingerprint（D3 要求记录场景指纹）>")
            continue
        want = fingerprint(scen[sid])
        if fp != want:
            bad.append(f"{p.stem}:<场景 {sid} 变过（指纹 {fp} → {want}）⇒ 要刷新用例>")
    return bad


def test_ai_cases_record_scenario_fingerprint():
    """★D3 核心：AI 用例必须记下场景指纹（否则"场景变了要刷新"无从判定）。"""
    got = stale()
    assert not got, (
        "这些 AI 用例与场景不同步（D3 要求：场景变了就把用例刷新过来）：\n  - "
        + "\n  - ".join(got)
        + "\n刷新办法：python -m framework.cli explore --ai --scenario-file <场景.yml> --llm-cassette"
          " && python -m framework.cli generate")


def test_sync_helper_detects_change(tmp_path):
    """负向自证：改一个字 ⇒ 指纹必须变（否则判据永远绿）。"""
    f = tmp_path / "s.yml"
    f.write_text("id: a\ntitle: 甲\n", encoding="utf-8")
    h1 = fingerprint(f)
    f.write_text("id: a\ntitle: 乙\n", encoding="utf-8")
    assert fingerprint(f) != h1, "场景内容变了但指纹没变 ⇒ 同步判据失效"
    f.write_text("id: a\ntitle: 甲\n", encoding="utf-8")
    assert fingerprint(f) == h1, "内容改回来指纹应复原（说明只跟内容有关）"

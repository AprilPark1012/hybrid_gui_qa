"""V8.7.17 判据：写进 json 的**仓库相对路径必须用正斜杠**（跨平台一致）。

由来（2026-10-29 用户 Windows 实测，`pytest tests/` 1 failed）：
  `test_index_and_disk_are_bidirectionally_consistent` 报
      「X 磁盘上有 index 不认识的孤儿脚本：['scripts/generated/.../ai_..._161243.py']」
  而断言里两个集合其实是**同一个文件**：
      on_disk  = {'scripts/generated/.../ai_..._161243.py'}     ← as_posix()，正斜杠
      in_index = {'scripts\\generated\\...\\ai_..._161243.py'}  ← str(Path)，反斜杠

  根因：`generator_generate.py` 写 `script_path` 时用 `str(mod.relative_to(BASE))`，
  Windows 上 Path 的字符串形式是反斜杠 -> 存进 index.json 后与判据侧的正斜杠永远对不上
  -> **磁盘其实完全一致，判据却红**（假红，且会让人以为框架生成了孤儿脚本）。

  [!] `test_generated_layout_contract.py` 里 2026-10-07 的注释说明「跨平台修过」，
      但那只修了**读的一侧**（`on_disk` 加 `as_posix()`），**写的一侧没管** ——
      这类「只修半边」是本项目反复踩的坑。

守三件事：
  ① 现存 `index.json` 的 `script_path` 不许含反斜杠；
  ② 现存用例 json 的 `source_scenario` 不许含反斜杠；
  ③ 源码里写这两个字段的地方**必须**调 `as_posix()`（静态钉住，防回退）；
  ④ 判据双向比较的两侧口径必须一致（防止再次「只修半边」）。
"""
from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
GEN = BASE / "scripts" / "generated"
INDEX = GEN / "index.json"
CASES = BASE / "cases"


def _iter_script_paths():
    """现有 index.json 里所有 script_path（没有就返回空）。"""
    if not INDEX.exists():
        return []
    try:
        data = json.loads(INDEX.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    return [str(m.get("script_path") or "") for m in data.values() if isinstance(m, dict)]


def test_index_script_paths_use_forward_slash() -> None:
    """① index.json 里的 script_path 必须是正斜杠。"""
    paths = _iter_script_paths()
    bad = [p for p in paths if "\\" in p]
    assert not bad, (
        f"index.json 里有 {len(bad)} 条 script_path 用了反斜杠（Windows 写出来的），"
        f"与判据侧的 as_posix() 口径不一致 -> 假红孤儿脚本：{bad[:3]}"
    )


def test_case_source_scenario_uses_forward_slash() -> None:
    """② 用例 json 的 source_scenario 同理（它会被读回来拼路径）。"""
    if not CASES.exists():
        return
    bad: list[str] = []
    for f in CASES.rglob("*.json"):
        if f.name in ("index.json",):
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        v = str(d.get("source_scenario") or "")
        if "\\" in v:
            bad.append(f"{f.name}: {v}")
    assert not bad, f"用例里 source_scenario 用了反斜杠（跨平台拼路径会挂）：{bad[:3]}"


def test_generator_writes_script_path_as_posix() -> None:
    """③ 静态钉住：写 script_path 的地方必须 as_posix()，不许裸 str(Path)。"""
    src = (BASE / "framework/features/f02_semantic/generator_generate.py").read_text(encoding="utf-8")
    i = src.find("_mod_path = ")
    assert i > 0, "没找到 _mod_path 赋值处"
    seg = src[i : i + 900]
    assert "as_posix()" in seg, (
        "_mod_path 没走 as_posix() —— Windows 上会存反斜杠，"
        "与 test_generated_layout_contract 的正斜杠口径冲突（2026-10-29 假红复发点）"
    )
    assert "str(mod.relative_to(BASE))" not in seg, "还在用裸 str(relative_to)，Windows 会给反斜杠"


def test_scenario_source_written_as_posix() -> None:
    """④ 静态钉住：`source_scenario` 也必须 as_posix()。"""
    src = (BASE / "framework/features/f02_semantic/scenario_generate.py").read_text(encoding="utf-8")
    i = src.find('extra = {"scenario_id"')
    assert i > 0, "没找到 source_scenario 的写入处"
    seg = src[max(0, i - 700) : i]
    assert "as_posix()" in seg, "source_scenario 没走 as_posix()（Windows 上会存反斜杠）"


def test_layout_contract_compares_same_notation() -> None:
    """⑤ 防「只修半边」：判据双向比较的两侧都用 as_posix()。

    `test_generated_layout_contract.py` 2026-10-07 只给 `on_disk` 加了 `as_posix()`，
    写入侧没动 -> 存量数据仍是反斜杠 -> 依然红。这条钉住「比较的两侧口径一致」。
    """
    src = (BASE / "tests/特性9-质量闸门体系/test_generated_layout_contract.py").read_text(encoding="utf-8")
    i = src.find("on_disk = ")
    assert i > 0, "没找到 on_disk 定义"
    seg = src[i : i + 800]
    assert "as_posix()" in seg, "on_disk 侧没用 as_posix()"
    # 另一侧也要归一化，否则又是「只修半边」
    assert ("in_index" in seg) or ("as_posix" in src[src.find("in_index = ") : src.find("in_index = ") + 400]), (
        "in_index 侧也应当归一化（或写入侧保证正斜杠）—— 否则存量数据仍会让判据假红"
    )

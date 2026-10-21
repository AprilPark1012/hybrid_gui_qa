"""一次性迁移：把老 `element_map` 产物里的步骤键 `action` / `description` 改成 `op` / `desc`。

为什么必须迁移（不是可选清理）
------------------------------
L34-a 把 `TestStep` 的字段名统一成 `op` / `desc`（方案 A）。而 `TestStep.from_dict()`
**对缺键不抛错**（这是刻意的：缺一个展示字段不该让整份产物读不动）。两件事叠在一起就危险：

    老产物只有 `action`/`description` -> `from_dict` 读不到 `op` -> **静默得到空串**
    -> 页面分组（`group_by_page`）、行定位兜底（`apply_row_locator_fallback`）
       全部悄悄不生效 —— 不报错、不放晴，测试照样绿。

所以：**改键名不是收尾清理，是数据迁移**。跑一次就行（幂等，重复跑改 0 个键）。

用法
----
    python build_tools/migrate_element_map_keys.py --dry-run     # 只看会改多少
    python build_tools/migrate_element_map_keys.py               # 真改（原地，带 .bak 备份）
    python build_tools/migrate_element_map_keys.py --check       # 只检查：仍有老键则 exit 1

自证（脚本自己保证）：每个文件改完后逐**步骤**对账 —— 步骤数、每步的键集（只换名字）、
以及每个语义字段的**值**必须一一相同；只有键名允许变。任何一处不等 -> 该文件**不落盘**并报错。
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_DIR = REPO / "output" / "element_maps"

# 老键 -> 新键（唯一权威；不许在这里加「兼容保留」）
RENAME = {"action": "op", "description": "desc"}   # l34a-ok 迁移表本身必须同时写出新旧两个键名（唯一允许两套名字共存的地方）

LEGACY_STEP_KEYS = tuple(RENAME)


# ---------------------------------------------------------------- 纯数据操作
def _iter_maps(data):
    """遍历产物里的每一个 ElementMap 字典（list / 单 map / {pages:[...]} 三种形状都认）。"""
    if isinstance(data, list):
        for x in data:
            if isinstance(x, dict):
                yield x
        return
    if not isinstance(data, dict):
        return
    pages = data.get("pages")
    if isinstance(pages, list):
        for x in pages:
            if isinstance(x, dict):
                yield x
        return
    if "steps" in data:
        yield data


def _rename_step(step: dict) -> int:
    """一步之内改名；保持键顺序。返回改了几个键。

    冲突（`op` 和 `action` 同时存在）不是「随便取一个」的情形：
      · 两者相等 -> 丢老键（幂等重跑会走到这里）；
      · 不等     -> 抛错。说明这份产物被两套口径各写过一半，必须人看。
    """
    n = 0
    items = list(step.items())
    for old in LEGACY_STEP_KEYS:
        if old not in step:
            continue
        new = RENAME[old]
        if new in step:
            if step[new] == step[old]:
                items = [(k, v) for k, v in items if k != old]
                n += 1
                continue
            raise ValueError(f"同一步里 {old!r}={step[old]!r} 与 {new!r}={step[new]!r} 冲突（值不同）")
        items = [(new if k == old else k, v) for k, v in items]
        n += 1
    step.clear()
    step.update(items)
    return n


def migrate_data(data) -> tuple[int, int, int]:
    """原地迁移一份产物，返回 (改的键数, 步数, 地图数)。"""
    keys = steps = maps = 0
    for m in _iter_maps(data):
        maps += 1
        seq = m.get("steps")
        if not isinstance(seq, list):
            continue
        for st in seq:
            if not isinstance(st, dict):
                continue
            steps += 1
            keys += _rename_step(st)
    return keys, steps, maps


# ---------------------------------------------------------------- 自证：只有键名变
def _canon_step(step: dict) -> dict:
    """把一步归一成**新键名**口径，用于改前/改后对比。"""
    return {RENAME.get(k, k): v for k, v in step.items()}


def assert_only_keys_renamed(before, after) -> None:
    """改前（老键）与改后（新键）必须**逐字段相等** —— 只有键名允许不同。"""
    b_maps, a_maps = list(_iter_maps(before)), list(_iter_maps(after))
    assert len(b_maps) == len(a_maps), f"地图数变了：{len(b_maps)} -> {len(a_maps)}"
    for i, (bm, am) in enumerate(zip(b_maps, a_maps)):
        b_steps = bm.get("steps") if isinstance(bm.get("steps"), list) else []
        a_steps = am.get("steps") if isinstance(am.get("steps"), list) else []
        assert len(b_steps) == len(a_steps), f"第 {i} 份地图的步骤数变了：{len(b_steps)} -> {len(a_steps)}"
        # 除 steps 之外的键值必须原样（page / url / scenario / probe_items）
        b_rest = {k: v for k, v in bm.items() if k != "steps"}
        a_rest = {k: v for k, v in am.items() if k != "steps"}
        assert b_rest == a_rest, f"第 {i} 份地图的非步骤字段被改动了"
        for j, (bs, as_) in enumerate(zip(b_steps, a_steps)):
            if not isinstance(bs, dict) or not isinstance(as_, dict):     # 非字典步骤：原样
                assert bs == as_, f"第 {i} 份地图第 {j} 步不是字典且被改动"
                continue
            assert _canon_step(bs) == as_, (
                f"第 {i} 份地图第 {j} 步对账不一致：\n  改前(归一后)={_canon_step(bs)!r}\n  改后={as_!r}"
            )


# ---------------------------------------------------------------- 文件级
def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def dump(p: Path, data) -> None:
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def legacy_hits(data) -> int:
    """还有多少个步骤带着老键（--check 用）。"""
    n = 0
    for m in _iter_maps(data):
        seq = m.get("steps")
        if not isinstance(seq, list):
            continue
        for st in seq:
            if isinstance(st, dict):
                n += sum(1 for k in LEGACY_STEP_KEYS if k in st)
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="迁移 element_map 产物的步骤键：action/description -> op/desc（幂等）")
    ap.add_argument("--dir", default=str(DEFAULT_DIR), help=f"产物目录（默认 {DEFAULT_DIR}）")
    ap.add_argument("--dry-run", action="store_true", help="只报告会改多少键，不写盘")
    ap.add_argument("--check", action="store_true", help="只检查：仍有老键则 exit 1")
    ap.add_argument("--no-backup", action="store_true", help="不写 .bak 备份（默认写）")
    args = ap.parse_args(argv)

    d = Path(args.dir)
    files = sorted(d.glob("*.json")) if d.is_dir() else []
    if not files:
        print(f"[!] {d} 下没有 *.json 产物 -> 无事可做（这是「没产物」，不是「迁移成功」）")
        return 0 if not args.check else 1

    total_keys = total_steps = 0
    changed_files = 0
    legacy_left = 0
    for p in files:
        before = load(p)
        legacy = legacy_hits(before)
        legacy_left += legacy
        working = json.loads(json.dumps(before, ensure_ascii=False))     # 深拷贝：改坏也不污染原件

        if args.check:
            print(f"  {'=' if not legacy else '[!]'} {p.name}: 老键 {legacy} 个")
            continue

        keys, steps, maps = migrate_data(working)
        total_keys += keys
        total_steps += steps
        assert_only_keys_renamed(before, working)          # 先自证，再落盘

        if keys:
            changed_files += 1
            if not args.dry_run:
                if not args.no_backup:
                    shutil.copy2(p, p.with_suffix(p.suffix + ".bak"))
                dump(p, working)
            print(f"  [{'dry' if args.dry_run else 'ok'}] {p.name}: 改 {keys} 个键 / {steps} 步 / {maps} 份地图")
        else:
            print(f"  [=] {p.name}: 已是新键名（0 改，幂等）")

        if not args.dry_run:
            after = load(p)
            assert_only_keys_renamed(before, after)        # 落盘后按**磁盘内容**再对一次
            left = legacy_hits(after)
            if left:
                print(f"  [X] {p.name}: 迁移后仍有 {left} 个老键")
                return 1

    if args.check:
        if legacy_left:
            print(f"[NG] 共 {legacy_left} 个老步骤键未迁移 -> 跑 "
                  f"python build_tools/migrate_element_map_keys.py")
            return 1
        print("[OK] 所有 element map 都已是 op/desc")
        return 0

    verb = "将改" if args.dry_run else "已改"
    print(f"[{'dry-run' if args.dry_run else 'OK'}] {verb} {total_keys} 个键，涉及 "
          f"{changed_files}/{len(files)} 个文件、{total_steps} 个步骤")
    print("  自证：每份产物改前/改后逐步骤对账一致 —— 步骤数、非步骤字段、每个语义值全等，只有键名变")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""[verify] 探测路径一致性：三条探测路径都能拿到「藏在可展开容器里」的控件。

背景（2026-10-08 事故）：
  三条探测路径里，`generator._probe_declared_pages`（generate 现场探测）**漏了「可展开容器」那一步**，
  于是拿不到右上角角色菜单里的「切换为XX管理员」。干净环境（无 element_map 快照）下，
  这直接导致 `映射质量闸拦下 -> 拒绝产出任何产物`（`cli all` 一条产物都不出）。
  修法 = 收敛成唯一入口 `scan_page()`（V8.3.7）。

本脚本验什么（需 demo 在跑）：
  正向：`_probe_declared_pages` 对合同列表页探测的结果里，**包含**角色菜单项（如「切换为订单管理员」）。
  负向：把「可展开容器」那步关掉后，**必须拿不到** —— 证明这两项的来源确实是展开动作，
        而不是页面本来就可见（否则正向断言是空验）。

口径：SKIP 不等于通过；本脚本自己判 demo 是否在跑，不在就 exit 3。
"""
from __future__ import annotations

import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from framework.tools.common.text_io import force_stdio  # noqa: E402

force_stdio()

BASE = "http://localhost:8000"
AUTH_FILE = REPO / "scripts" / "generated" / "_auth.json"
PAGE = ("合同列表页", BASE + "/")


def _reachable() -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(BASE + "/api/health", timeout=5) as r:
            return r.status == 200
    except Exception:                                                # noqa: BLE001
        return False


def _auth() -> dict:
    if AUTH_FILE.is_file():
        try:
            data = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data:
                return next(iter(data.values()))
        except Exception:                                            # noqa: BLE001
            pass
    # 兜底：用场景 yml 里的公开演示凭据
    return {"login_api": "/api/login", "username": "super",
            "password": "super@123", "token_key": "demo_token"}


def _scan_role_menu_items(with_expand: bool) -> list[str]:
    """调真实那条路径（generate 现场探测），返回探测到的「切换为...」控件名。"""
    from framework.tools.generate.generator import _probe_declared_pages
    import framework.tools.probe.page_scan as ps

    saved = ps.expand_and_collect
    if not with_expand:
        ps.expand_and_collect = lambda *a, **kw: []              # 负向：模拟"又漏了 expand"
    try:
        loc_map, _amb, _dup, _itmap = _probe_declared_pages([PAGE], _auth())
    finally:
        ps.expand_and_collect = saved

    names = [n for n in loc_map if "切换为" in n]
    return sorted(names)


def main() -> int:
    if not _reachable():
        print(f"[skip] demo 未就绪（{BASE}/api/health 不可达）-> 本脚本不适用")
        return 3

    print("=" * 68)
    print("探测路径一致性检查（V8.3.7 事故修复的验收）")
    print("=" * 68)

    ok = True

    print("\n[1] 正向：generate 现场探测应拿到角色菜单控件")
    got = _scan_role_menu_items(with_expand=True)
    print(f"     探到: {got}")
    if got:
        print(f"     [OK] 拿到 {len(got)} 个「切换为...」控件")
    else:
        print("     [NG] 一个都没拿到 —— 现场探测的「可展开容器」步骤失效")
        ok = False

    print("\n[2] 负向自证：关掉「可展开容器」后必须拿不到（证明来源确实是展开动作）")
    neg = _scan_role_menu_items(with_expand=False)
    print(f"     探到: {neg}")
    if neg:
        print(f"     [NG] 关掉展开竟仍拿到 {len(neg)} 个 -> 正向断言是空验（页面本就可见？）")
        ok = False
    else:
        print("     [OK] 关掉后为 0 -> 正向那几项确实来自展开动作")

    print("\n" + "=" * 68)
    print(f"结论: {'通过' if ok else '失败'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

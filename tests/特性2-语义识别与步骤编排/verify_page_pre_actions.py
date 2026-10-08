"""二类验证（真跑 demo）：`pages[].pre` 让探针探到「前置后才有」的控件（P22 批 5 缺口(4)(5)）。

真值背景（2026-09-30）：
  订单详情页的行控件（数量/单位/行类型/收入）只在「编辑 + 新增行」之后才存在；
  探针默认"打开页面就看一遍" -> 33 个控件里没有它们 -> AI 拿不到语义名、用例引用不了
  -> 行必填没填 -> 保存无效 -> 提交被拦（状态恒「已新建」）。

判据：
  V1 声明 pre=[编辑, 新增行] -> 清单里**出现** 数量/单位/行类型/收入；
  V2 不声明 pre -> 清单里**没有**它们（负向自证：证明 V1 确实来自前置动作）。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from framework.tools.common.text_io import force_stdio       # noqa: E402

force_stdio()

import os
import sys

# cwd 归位到仓库根（sys.path 上面已按 __file__ 自动定位；这里同样不写死本机路径）
os.chdir(str(Path(__file__).resolve().parents[2]))

from framework.tools.explore.explorer import _collect_pages_context          # noqa: E402

BASE = "http://localhost:8000"
AUTH = {"login_api": "/api/login", "username": "super",
        "password": "super@123", "token_key": "demo_token"}
WANT = ("数量", "单位", "行类型", "收入")


def _names(url: str, pre: list) -> set[str]:
    pages = ([{"name": "订单详情页", "url": url, "pre": pre}]
             if pre else [{"name": "订单详情页", "url": url}])
    merged, _dom, _err, _coll, _rows = _collect_pages_context(pages, [], AUTH)
    return {str(it.get("semantic_name") or "") for it in merged}


def main() -> int:
    fails: list[str] = []
    url = f"{BASE}/order_detail.html?no=SO-1001"

    with_pre = _names(url, ["编辑", "新增行"])
    print(f"V1 带 pre -> 命中 {sorted(n for n in with_pre if any(w in n for w in WANT))}")
    missing = [w for w in WANT if not any(w in n for n in with_pre)]
    if missing:
        fails.append(f"带 pre 仍探不到：{missing}")

    without = _names(url, [])
    hit_wo = sorted(n for n in without if any(w in n for w in WANT))
    print(f"V2 不带 pre -> 命中 {hit_wo}（应为空）")
    if hit_wo:
        print(f"   [info] 注意：不带 pre 也探到了 —— 这些名字可能本来就可见：{hit_wo}")

    if fails:
        print("\n[NG] FAIL")
        for f in fails:
            print("   -", f)
        return 1
    print("\n[OK] PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())

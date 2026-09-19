"""断言类型 · 正/负向端到端验证（2026-09-13 D 项配套）。

为什么单独一个脚本、不叫 test_*.py：
  它会**临时**往 cases/ 写一批故意写错的用例（prefix=neg_tmp_）、跑完清理并重新 generate，
  所以不适合跟主用例套件混在一起跑（避免并发互相干扰）。
  正向的、不需要浏览器的部分在 tests/test_assert_kinds_render.py，那个随主套件跑。

跑法（需要 demo 在 8000 上：python -m demo.app）：
    cd ~/hybrid_gui_qa && source .venv/bin/activate
    python tests/verify_assert_kinds.py          # 期望最后一行：全部符合预期 ✅

判据（防假绿铁律）：**每条断言在「期望值写错」时必须 FAILED**——只有正向全绿不算验证过。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import shutil
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
# 统一 UTF-8：本脚本要跨进程收子进程输出（generate / pytest），口径必须与子进程一致 ——
# 否则 Windows cp936 下会 `UnicodeDecodeError: 'gbk' codec ...`（与 cli.py 同一个坑）。
sys.path.insert(0, str(BASE))
from framework.text_io import UTF8_ENV, force_stdio  # noqa: E402

force_stdio()
_U8 = {**os.environ, **UTF8_ENV}      # 给子进程注入 UTF-8 口径
CASES = BASE / "cases"
DATASETS = BASE / "scripts" / "datasets"
DEMO = "http://localhost:8000"
PREFIX = "neg_tmp_"

CONTRACTS = {"op": "goto", "desc": "打开合同列表页", "url": DEMO}
TODO_GOTO = {"op": "goto", "desc": "打开待办页", "url": f"{DEMO}/todo.html"}


def _fill1005():
    return {"op": "fill", "desc": "关键字 1005",
            "element": "合同编号_名称_管理单元_合同类型_帐套", "value": "1005"}


def _search():
    return {"op": "click", "desc": "点击搜索", "element": "搜索"}


# ---- 每条 = 一个「故意写错」的断言；都必须在实测里 FAILED ----
NEGATIVE = {
    # kind: 错的期望值 / 错的状态
    "text": dict(steps=[CONTRACTS, _fill1005(), _search()],
                 asserts=[{"kind": "text", "expect": "HT-9999", "desc": "不存在的编号"}]),
    "url": dict(steps=[CONTRACTS, _fill1005(), _search()],
                asserts=[{"kind": "url", "expect": "localhost:9999", "desc": "错端口"}]),
    "count": dict(steps=[CONTRACTS, _fill1005(), _search()],
                  asserts=[{"kind": "count", "selector": "#tbody-contracts tr", "expect": 99,
                            "desc": "行数写错"}]),
    "attr": dict(steps=[CONTRACTS, _fill1005(), _search()],
                 asserts=[{"kind": "attr", "selector": "#tbody-contracts td[data-field='contractNo']",
                           "name": "data-field", "expect": "WRONG", "desc": "属性值写错"}]),
    "value": dict(steps=[CONTRACTS, _fill1005(), _search(),
                         {"op": "click", "desc": "点击重置", "element": "重置"}],
                  asserts=[{"kind": "value", "element": "合同编号_名称_管理单元_合同类型_帐套",
                            "expect": "1005", "desc": "重置后仍期望有值（实际已清空）"}]),
    "visible": dict(steps=[CONTRACTS, _fill1005(), _search()],
                    asserts=[{"kind": "visible", "selector": "#modal-new", "desc": "弹窗实际是关的"}]),
    "hidden": dict(steps=[CONTRACTS, _fill1005(), _search()],
                   asserts=[{"kind": "hidden", "selector": "[data-testid='btn-search']",
                             "desc": "搜索按钮实际可见"}]),
    "enabled": dict(steps=[CONTRACTS, _fill1005(), _search()],
                    asserts=[{"kind": "enabled", "selector": "[data-testid='btn-export']",
                              "desc": "导出按钮实际是 disabled"}]),
    "disabled": dict(steps=[CONTRACTS, _fill1005(), _search()],
                     asserts=[{"kind": "disabled", "selector": "[data-testid='btn-search']",
                               "desc": "搜索按钮实际可用"}]),
    "checked": dict(steps=[TODO_GOTO],
                    asserts=[{"kind": "checked", "selector": "li:has-text('写周报') input[type=checkbox]",
                              "desc": "写周报 实际未勾选"}]),
    "unchecked": dict(steps=[TODO_GOTO],
                      asserts=[{"kind": "unchecked", "selector": "li:has-text('买牛奶') input[type=checkbox]",
                                "desc": "买牛奶 实际已勾选"}]),
    # ---- 结构性错误（生成阶段就该 fail，绝不许静默跳过）----
    "unknown_kind": dict(steps=[CONTRACTS],
                         asserts=[{"kind": "color", "expect": "red", "desc": "不存在的断言类型"}]),
    "missing_expect": dict(steps=[CONTRACTS],
                           asserts=[{"kind": "count", "selector": "#tbody-contracts tr",
                                     "desc": "count 缺 expect"}]),
    "missing_name": dict(steps=[CONTRACTS],
                         asserts=[{"kind": "attr", "selector": "#tbody-contracts td", "expect": "x",
                                   "desc": "attr 缺 name"}]),
    "unmapped_element": dict(steps=[CONTRACTS],
                             asserts=[{"kind": "enabled", "element": "根本不存在的控件名",
                                       "desc": "element 拼错 → 不许静默跳过"}]),
}

POSITIVE = ["assert_kinds_search", "assert_kinds_reset", "assert_kinds_modal", "assert_kinds_todo"]


def _demo_up() -> bool:
    try:
        with urllib.request.urlopen(DEMO, timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _write_neg_cases():
    written = []
    for kind, spec in NEGATIVE.items():
        cid = f"{PREFIX}{kind}"
        p = CASES / f"{cid}.json"
        p.write_text(json.dumps({
            "case_id": cid, "name": f"负向验证：{kind} 断言写错必须失败",
            "base_url": DEMO, "steps": spec["steps"], "asserts": spec["asserts"],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        written.append(p)
    return written


def _cleanup(written):
    for p in written:
        p.unlink(missing_ok=True)
        (DATASETS / p.name).unlink(missing_ok=True)
    # 让 scripts/ 回到「只有正式用例」的状态
    # ⚠️ 这里**不能**带 `--allow-unmapped`：收尾要的是干净产物（逃生口只服务负向段的生成）。
    subprocess.run([sys.executable, "-m", "framework.cli", "generate"],
                   cwd=BASE, capture_output=True, text=True, encoding="utf-8", errors="replace",
                   env=_U8)


def _gen(*, allow_unmapped: bool = False):
    """跑 generate；负向段必须带 `--allow-unmapped`。

    ⚠️ 为什么负向段必须带逃生口（2026-09-19 修，与 verify_cross_page.py 当年同一个缺陷类）：
    负向用例里有一个**故意的**「根本不存在的控件名」（就是为了证明「元素名写错 ⇒ 用例 FAILED」），
    而 V7.5.1 的**映射质量闸**会因此把整个 generate 拦成 exit 2 ⇒ 负向段一步都没跑就 return 2，
    脚本自己变成「红」。逃生口只在这里用；`_cleanup()` 收尾不带它，保证 scripts/ 回到干净产物。
    """
    cmd = [sys.executable, "-m", "framework.cli", "generate"]
    if allow_unmapped:
        cmd.append("--allow-unmapped")
    r = subprocess.run(cmd,
                       cwd=BASE, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=_U8)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def _run_node(cid: str):
    """跑单个用例，返回 (exit_code, 摘要行)。"""
    env = {"HYBRID_RUN_ID": "verify_assert_kinds"}
    import os
    e = dict(os.environ, **env)
    node = f"scripts/test_cases.py::test_{cid}"
    r = subprocess.run([sys.executable, "-m", "pytest", node, "-q", "--no-header", "-x"],
                       cwd=BASE, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**e, **UTF8_ENV})
    text = (r.stdout or "") + (r.stderr or "")
    tail = [ln for ln in text.strip().splitlines() if ln.strip()][-1:] or [""]
    return r.returncode, tail[0][:110]


def main() -> int:
    if not _demo_up():
        print(f"❌ 被测 demo 不可达（{DEMO}）——先跑：python -m demo.app")
        return 2

    print("===== 一、正向：4 条 assert_kinds_* 必须 PASSED =====")
    expr = " or ".join(f"test_{c}" for c in POSITIVE)
    r = subprocess.run([sys.executable, "-m", "pytest", "scripts/test_cases.py", "-q", "-k", expr],
                       cwd=BASE, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=_U8)
    pos_ok = r.returncode == 0 and "4 passed" in (r.stdout or "")
    print(f"  {('✅' if pos_ok else '❌')} {' or '.join(POSITIVE)}")
    print(f"     {[l for l in (r.stdout or '').strip().splitlines() if l.strip()][-1]}")

    print("\n===== 二、负向：每条断言写错必须 FAILED（防假绿）=====")
    written = _write_neg_cases()
    bad = []
    try:
        rc, out = _gen(allow_unmapped=True)
        if rc != 0:
            print("  ❌ generate 失败（负向段已带 --allow-unmapped，仍失败 ⇒ 另有真问题）：", out[-400:])
            return 2
        for kind, cid in ((k, f"{PREFIX}{k}") for k in NEGATIVE):
            code, line = _run_node(cid)
            ok = code != 0
            if not ok:
                bad.append(kind)
            print(f"  {('✅' if ok else '❌ 假绿！')} {kind:<16} pytest exit={code}  {line}")
    finally:
        _cleanup(written)

    print("\n===== 结论 =====")
    if pos_ok and not bad:
        print("全部符合预期 ✅（正向 4 passed；负向 15 条全部 FAILED，无假绿）")
        return 0
    print(f"不符合预期 ❌  正向={'OK' if pos_ok else 'FAIL'}，假绿项={bad or '无'}")
    return 1


if __name__ == "__main__":
    sys.exit(main())

"""慢目标闸门 —— 证明「慢机器 / 高并发目标」下用例依然全绿（F4）。

为什么需要这个闸门（2026-09-14 团队演示事故）：
    团队 Windows（16 核 / 16 worker）上 `run all` 红 4 条、`--debug` 全绿。根因是
    ① 页面异步取数而没有"就绪契约"② 有状态被测服务 + 每用例全局复位；
    而本机 `safe_workers()` 恒为 1、目标又快 ⇒ **本地永远复现不出来**。
    这个闸门用"每请求 +delay 的反向代理"把那个环境搬进 CI：同一批用例指向代理，
    必须全绿；修复前它是 5 failed/1 passed（本机 30 秒复现）。

用法：
    python tests/verify_slow_target.py                # 关键 6 条（默认，约 1~2 分钟）
    python tests/verify_slow_target.py --full         # 全部用例（慢，约 5 分钟）
    SLOW_MS=800 python tests/verify_slow_target.py    # 加大延迟（更接近"拥挤机器"）

约定（与其它 verify_*.py 一致）：表格 + 末行结论；失败/不满足前置条件都 **exit 非 0**，
**绝不把"没跑"报成"通过"**（内存不足会明确打 SKIP 并 exit 3）。
"""
from __future__ import annotations

import html
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = str(ROOT / ".venv" / "bin" / "python")
if not Path(PY).exists():
    PY = sys.executable

DEMO_PORT = int(os.environ.get("VERIFY_DEMO_PORT", "8011"))
PROXY_PORT = int(os.environ.get("VERIFY_PROXY_PORT", "8012"))
DELAY_MS = int(os.environ.get("SLOW_MS", "300"))
MIN_MEM_MB = int(os.environ.get("VERIFY_MIN_MEM_MB", "650"))    # 1 个 headless Chromium ≈515MB + 余量

KEY_CASES = [
    "create_bu_a_c1",                         # 弹层选择（客户列表层里选一行）
    "cross_page_detail",                      # 跨页 + 全量断言
    "hand_enter_search",                      # 回车搜索 + 前缀筛选
    "search_customer_fuzzy",                  # 精确计数断言（前缀命中 4 条）
    "ai_contracts_create_and_filter_by_customer_004651",   # AI 生成的用例（新建 + 筛选）
]


# ---------------- 慢代理 ----------------
class _SlowProxy(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    upstream = f"http://127.0.0.1:{DEMO_PORT}"
    delay = DELAY_MS / 1000.0
    seen = 0

    def _proxy(self, method: str):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else None
        type(self).seen += 1
        time.sleep(self.delay)
        req = urllib.request.Request(type(self).upstream + self.path, data=body, method=method)
        for k, v in self.headers.items():
            if k.lower() not in ("host", "content-length", "connection"):
                req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                code, data, ctype = r.status, r.read(), r.headers.get("Content-Type", "text/html")
        except urllib.error.HTTPError as e:
            code, data, ctype = e.code, e.read(), e.headers.get("Content-Type", "text/html")
        except Exception as e:
            code, data, ctype = 502, str(e).encode(), "text/plain"
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(data)
        except Exception:
            pass

    def do_GET(self):
        self._proxy("GET")

    def do_POST(self):
        self._proxy("POST")

    def log_message(self, *a):
        pass


def _mem_available_mb() -> int:
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    except Exception:
        pass
    return 10 ** 6          # 非 Linux（读不到）时不拦 —— 让闸门在 Windows 上也能跑


def _wait_port(port: int, timeout: float = 20.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        with socket.socket() as s:
            s.settimeout(0.4)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.2)
    return False


def _parse_report(run_dirs: list[Path]) -> dict:
    """从 pytest-html 的 data-jsonblob 解析结果（别 grep 页面 —— 会得到假计数）。"""
    out = {"Passed": 0, "Failed": 0, "failed_names": []}
    for p in run_dirs:
        rp = p / "report.html"
        if not rp.exists():
            continue
        m = re.search(r'data-jsonblob="([^"]+)"', rp.read_text(encoding="utf-8", errors="replace"))
        if not m:
            continue
        j = json.loads(html.unescape(m.group(1)))
        for name, tests in j.get("tests", {}).items():
            for t in tests:
                res = t.get("result", "")
                out[res if res in out else "Failed"] = out.get(res if res in out else "Failed", 0) + 1
                if res != "Passed":
                    out["failed_names"].append(name.split("::")[-1])
    return out


def main() -> int:
    full = "--full" in sys.argv
    avail = _mem_available_mb()
    print(f"[gate] 慢目标闸门：代理延迟 {DELAY_MS}ms/请求 · demo:{DEMO_PORT} · 代理:{PROXY_PORT}")
    print(f"[gate] 内存检查：MemAvailable={avail}MB（需要 ≥{MIN_MEM_MB}MB 才能起 1 个 Chromium）")
    if avail < MIN_MEM_MB:
        print(f"[gate] ⛔ SKIP：内存不足，跑起来必 OOM（本机 1.87G 无 swap）。"
              f"这不是通过 —— 等内存释放后重跑。")
        return 3

    selection = [] if full else ["-k", " or ".join(f"test_{c}" for c in KEY_CASES)]
    demo = None
    proxy = None
    rc = 1
    log_dirs = []
    try:
        # 1) 专用 demo 实例（独立端口，不动别人正在跑的 8000）
        env = dict(os.environ)
        env["TARGET_PORT"] = str(DEMO_PORT)
        demo = subprocess.Popen([PY, "-m", "demo.app"], cwd=ROOT, env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        if not _wait_port(DEMO_PORT):
            print("[gate] ❌ demo 没起来（端口未监听）")
            return 1
        print(f"[gate] demo 已起：http://127.0.0.1:{DEMO_PORT}")

        # 2) 慢代理
        proxy = ThreadingHTTPServer(("127.0.0.1", PROXY_PORT), _SlowProxy)
        threading.Thread(target=proxy.serve_forever, daemon=True).start()
        print(f"[gate] 慢代理已起：http://127.0.0.1:{PROXY_PORT} → demo（每请求 +{DELAY_MS}ms）")

        # 3) 用**同一批生成脚本**指向代理跑（HYBRID_BASE_URL 覆盖目标地址）
        run_env = dict(os.environ)
        run_env.update({
            "HYBRID_BASE_URL": f"http://127.0.0.1:{PROXY_PORT}",
            "HYBRID_RESET_URL": f"http://127.0.0.1:{PROXY_PORT}/api/reset",
            "HYBRID_RUN_ID": f"slowgate_{time.strftime('%Y%m%d_%H%M%S')}",
        })
        (ROOT / "log" / run_env["HYBRID_RUN_ID"]).mkdir(parents=True, exist_ok=True)   # pytest-html 不建父目录
        cmd = [PY, "-m", "pytest", "scripts/test_cases.py", "-q", "-p", "no:cacheprovider",
               f"--html=log/{run_env['HYBRID_RUN_ID']}/report.html"] + selection
        print(f"[gate] 执行：{' '.join(cmd)}")
        t0 = time.time()
        r = subprocess.run(cmd, cwd=ROOT, env=run_env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=1800)
        dt = time.time() - t0
        tail = (r.stdout or "").strip().splitlines()[-6:]
        print("[gate] pytest 输出（末几行）:")
        for line in tail:
            print("        " + line)

        log_dirs = [ROOT / "log" / run_env["HYBRID_RUN_ID"]]
        res = _parse_report(log_dirs)
        total = res.get("Passed", 0) + res.get("Failed", 0)
        print(f"[gate] 结果：Passed={res.get('Passed', 0)} Failed={res.get('Failed', 0)}"
              f"（共 {total} 条，{dt:.1f}s）")
        if res.get("failed_names"):
            print("[gate] 失败用例：" + ", ".join(sorted(set(res["failed_names"]))))
        expect = 0 if full else len(KEY_CASES)
        if total == 0:
            print("[gate] ❌ 一条都没跑（选择器写错了？）—— 不算通过")
            rc = 1
        elif res.get("Failed", 0) == 0 and (full or total >= expect):
            print(f"[gate] ✅ 慢目标下全绿（{total} 条）—— F1 就绪契约 + F2 有界等待 生效")
            rc = 0
        else:
            print("[gate] ❌ 慢目标下有用例失败 —— 回归了")
            rc = 1
    except subprocess.TimeoutExpired:
        print("[gate] ❌ 超时（1800s）—— 可能是页面/代理卡住")
        rc = 1
    finally:
        if proxy:
            proxy.shutdown()
        if demo:
            demo.send_signal(signal.SIGTERM)
            try:
                demo.wait(timeout=5)
            except Exception:
                demo.kill()
        print(f"[gate] 收尾：demo/代理已关（证据：log/{os.environ.get('HYBRID_RUN_ID', 'slowgate_*')}）")
    return rc


if __name__ == "__main__":
    sys.exit(main())

"""被测 demo 应用：静态页面 + 内存数据 API。

2026-09-14 改造（AprilPark1012拍板需求②）：合同数据从「列表页 JS 每次刷新临时生成」搬到**服务端**，
让详情页读到的是**同一条真实记录** —— 新建的合同在详情页也能看到正确的客户；
页面刷新不再丢数据（更接近真实系统）。

接口（数据口径的**唯一来源**就是这个文件）：
  GET  /api/customers             6 个客户主数据（名称 + 地址）
  GET  /api/contracts             全部合同（含客户名称 custName）
  GET  /api/contract?no=HT-1005   单条；查不到 → 404 {"error": "未找到该合同: ..."}
  POST /api/contracts             新建 {name,mu,file,type,cust,bu} 全必填 → 201 + 新记录
  POST /api/reset                 数据复位成预置 20 条（**测试用例间隔离**用）

⚠️ 数据现在会**留在服务端**（改造前刷新页面就没了），所以测试侧必须做用例间复位：
   framework 生成的 conftest 会自动 POST /api/reset（见 generator.py 的 _reset_target_data，
   可用 HYBRID_RESET_URL=off 关掉）。不复位的话「列表恢复 20 行」这类断言会被上一条
   用例残留的新建数据打乱，而且失败原因会指向错误的地方。
运行: python -m demo.app   (在 hybrid_gui_qa/ 下)
"""
import http.server
import json
import os
import random
import socketserver
import threading
import urllib.parse

PORT = int(os.environ.get("TARGET_PORT", "8000"))
# 默认被测页面：合同管理系统（也可用 TODO_PAGE=todo.html 切回旧 demo）
DEFAULT_PAGE = os.environ.get("DEFAULT_PAGE", "contracts.html")
DIR = os.path.dirname(os.path.abspath(__file__))

# ========== 客户主数据（6 个客户：名称 + 地址） ==========
CUSTOMERS = [
    {"id": "c1", "name": "北京华信科技有限公司", "addr": "北京市朝阳区建国路88号"},
    {"id": "c2", "name": "上海远东贸易有限公司", "addr": "上海市浦东新区世纪大道100号"},
    {"id": "c3", "name": "广州南方物流有限公司", "addr": "广州市天河区体育西路12号"},
    {"id": "c4", "name": "深圳前海数据服务有限公司", "addr": "深圳市南山区科技园南区1号"},
    {"id": "c5", "name": "北京中科智慧科技有限公司", "addr": "北京市海淀区中关村大街1号"},
    {"id": "c6", "name": "成都天府软件有限公司", "addr": "成都市高新区天府大道中段1号"},
]

MUS = ["0021", "0451", "1031"]
FILES = ["001", "002", "003"]
TYPES = ["合同", "po", "预po"]
BUS = ["bu_a", "bu_b", "bu_c"]

REQUIRED = ("name", "mu", "file", "type", "cust", "bu")

_lock = threading.Lock()          # ThreadingTCPServer：数据要被多线程访问
CONTRACTS: list[dict] = []


def seed() -> list[dict]:
    """预置 20 条合同（口径与改造前一致）。

    客户**按序号确定**（不随机）：HT-1001→c1、HT-1005→c5、HT-1007→c1 … —— 这样
    「客户右模糊」的命中条数是确定的，用例才敢断言条数（随机数据只能断言“有结果”）。
    其余字段仍随机（与改造前一样；用例不依赖它们）。
    """
    rows = []
    for i in range(1, 21):
        rows.append({
            "no": f"HT-{1000 + i}",
            "name": f"合同{i}",
            "mu": random.choice(MUS),
            "file": random.choice(FILES),
            "type": random.choice(TYPES),
            "cust": CUSTOMERS[(i - 1) % len(CUSTOMERS)]["id"],
            "bu": random.choice(BUS),
        })
    return rows


def with_cust_name(row: dict) -> dict:
    """给记录补上 custName（客户名称）—— 页面/接口都直接拿它渲染，不必各自再查一遍。"""
    d = dict(row)
    d["custName"] = next((c["name"] for c in CUSTOMERS if c["id"] == d.get("cust")),
                         d.get("cust", ""))
    return d


def reset_data() -> int:
    """复位成预置 20 条，返回条数（测试用例间隔离用）。"""
    global CONTRACTS
    with _lock:
        CONTRACTS = seed()
    return len(CONTRACTS)


def create_contract(payload: dict) -> tuple[dict, int]:
    """新建合同：校验必填 → 分配编号 → 落库。返回 (响应体, HTTP 状态码)。"""
    missing = [k for k in REQUIRED if not str(payload.get(k) or "").strip()]
    if missing:
        # 提示语与前端保持一致（用例的 assert_guard.forbidden 依赖这句不会被当正常结果）
        return {"error": "请填写全部必填字段", "missing": missing}, 400
    with _lock:
        seq = 2001 + len(CONTRACTS)
        no = f"HT-{seq}"
        while any(r["no"] == no for r in CONTRACTS):
            seq += 1
            no = f"HT-{seq}"
        row = {"no": no, **{k: str(payload[k]).strip() for k in REQUIRED}}
        CONTRACTS.append(row)
        return with_cust_name(row), 201


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=DIR, **kw)

    # ---- 小工具 ----
    def _send_json(self, obj, code: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")   # 测试要读到最新数据，不许缓存
        self.end_headers()
        self.wfile.write(body)

    def _path_only(self) -> str:
        return urllib.parse.urlsplit(self.path).path

    # ---- 路由 ----
    def do_GET(self):
        path = self._path_only()
        if path == "/api/customers":
            return self._send_json(CUSTOMERS)
        if path == "/api/contracts":
            with _lock:
                return self._send_json([with_cust_name(r) for r in CONTRACTS])
        if path == "/api/contract":
            no = (urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("no") or [""])[0]
            with _lock:
                row = next((r for r in CONTRACTS if r["no"] == no), None)
            if row is None:
                return self._send_json({"error": f"未找到该合同: {no}"}, 404)
            return self._send_json(with_cust_name(row))
        if self.path in ("/", ""):
            # 根路径默认服务合同页（避免 SimpleHTTPRequestHandler 列出目录）
            self.path = "/" + DEFAULT_PAGE
        super().do_GET()

    def do_POST(self):
        path = self._path_only()
        if path == "/api/reset":
            return self._send_json({"ok": True, "count": reset_data()})
        if path == "/api/contracts":
            try:
                n = int(self.headers.get("Content-Length") or 0)
                payload = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            except Exception as e:
                return self._send_json({"error": f"请求体不是合法 JSON: {e}"}, 400)
            body, code = create_contract(payload if isinstance(payload, dict) else {})
            return self._send_json(body, code)
        return self._send_json({"error": f"未知接口: {path}"}, 404)

    def log_message(self, fmt, *args):  # 静默，避免刷屏
        pass


def main():
    # 允许重启时复用端口（避免上次退出的 TIME_WAIT 卡住新进程）
    socketserver.TCPServer.allow_reuse_address = True
    # ThreadingTCPServer：并发（pytest-xdist 多 worker）下不再串行排队，避免超时抖动
    class _Server(socketserver.ThreadingTCPServer):
        daemon_threads = True
    n = reset_data()
    with _Server(("", PORT), Handler) as httpd:
        print(f"[demo app] serving {DIR} on http://localhost:{PORT} (page={DEFAULT_PAGE})")
        print(f"[demo app] API: /api/customers /api/contracts /api/contract?no= /api/reset"
              f"（已预置 {n} 条合同）")
        httpd.serve_forever()


if __name__ == "__main__":
    main()

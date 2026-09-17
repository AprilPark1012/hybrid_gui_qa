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
  GET  /api/health                能力探针 {"partitioned": true, "presets": 20}（CLI 据此决定能否并发）
  ⚠️ 分区：所有 /api/* 都接受 `?w=<分区名>`（缺省 default）。同一个分区内数据共享；不同分区互相隔离。
     pytest-xdist 下 conftest 会给每个 worker 注入自己的分区号，因此**并发跑不再互相踩**。

运行: python -m demo.app   (在 hybrid_gui_qa/ 下；端口用 TARGET_PORT 覆盖)
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

# ========== 订单系统主数据（2026-09-17 新增：AprilPark1012需求） ==========
# 订单系统页面（orders.html）是**新 tab**打开的独立页面，数据同样以本文件为唯一来源。
ORDER_TYPES = ["标准销售订单", "退货订单", "服务订单", "电商订单"]
SALESMEN = [
    {"id": "s1", "name": "张伟"},
    {"id": "s2", "name": "李娜"},
    {"id": "s3", "name": "王强"},
    {"id": "s4", "name": "赵敏"},
    {"id": "s5", "name": "陈磊"},
    {"id": "s6", "name": "刘洋"},
]
ORDERS_PER_PAGE = 20          # 每页 20 条
ORDER_PAGE_COUNT = 3          # 默认 3 页
ORDER_PRESETS = ORDERS_PER_PAGE * ORDER_PAGE_COUNT      # 60 = 3 页 × 20 条
REQUIRED_ORDER = ("name", "contract_no", "bu", "mu", "file", "order_type", "cust", "salesman")
# ↑ 必填：订单名称 / 合同 / 业务单元 / 管理单元 / 帐套 / 订单类型 / 客户 / 销售员
#   订单备注（remark）**选填**（唯一非必填项）

# ⚠️ 必须是 RLock（可重入）：`_store()` 自己加锁，而调用方（do_GET/do_POST）通常已持有该锁，
#    普通 Lock 会在第一次请求就**自死锁**（实测踩过：demo 整个卡住、curl 全部挂死）。
_lock = threading.RLock()         # ThreadingTCPServer：数据要被多线程访问
# ⚠️ 2026-09-14（F6）：数据按**分区**存放 —— 一个分区 = 一份独立的 20 条预置数据。
#    pytest-xdist 下每个 worker 用自己的分区（`?w=gw0` / cookie），**并发时互不踩**；
#    不带分区参数时用 "default"，行为与改造前完全一致（老用例/手工调试零影响）。
_STORES: dict[str, list[dict]] = {}
PRESETS = 20
PARTITIONS_ENABLED = os.environ.get("HYBRID_TARGET_PARTITIONED", "1") != "0"


def _part_of(query: str) -> str:
    """从 query string 取分区名（?w=gw0）；缺省 default。"""
    if not PARTITIONS_ENABLED:
        return "default"
    q = urllib.parse.parse_qs(query or "")
    return ((q.get("w") or [""])[0] or "").strip() or "default"


def _store(part: str = "default") -> list[dict]:
    """取（必要时创建）某分区的合同列表。加锁：ThreadingTCPServer 下多线程会同时进。"""
    with _lock:
        lst = _STORES.get(part)
        if lst is None:
            lst = seed()
            _STORES[part] = lst
        return lst


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


def reset_data(part: str = "default") -> int:
    """把**该分区**复位成预置数据（合同 20 条 + 订单 60 条），返回合同条数（测试用例间隔离用）。

    只清自己那份 —— 这是并发安全的关键：A worker 的复位不再抹掉 B worker 正在依赖的数据。
    ⚠️ 2026-09-17：订单数据也在这里一起复位（订单页同样有「共 N 条 / 第一行是新订单」这类断言，
    不复位会被上一条用例残留的新建订单打乱）。
    """
    with _lock:
        _STORES[part] = seed()
        _ORDER_STORES[part] = seed_orders()
        return len(_STORES[part])


def create_contract(payload: dict, part: str = "default") -> tuple[dict, int]:
    """新建合同（写入**该分区**）：校验必填 → 分配编号 → 落库。返回 (响应体, HTTP 状态码)。"""
    missing = [k for k in REQUIRED if not str(payload.get(k) or "").strip()]
    if missing:
        # 提示语与前端保持一致（用例的 assert_guard.forbidden 依赖这句不会被当正常结果）
        return {"error": "请填写全部必填字段", "missing": missing}, 400
    with _lock:
        lst = _STORES.setdefault(part, seed())
        seq = 2001 + len(lst)
        no = f"HT-{seq}"
        while any(r["no"] == no for r in lst):
            seq += 1
            no = f"HT-{seq}"
        row = {"no": no, **{k: str(payload[k]).strip() for k in REQUIRED}}
        lst.append(row)
        return with_cust_name(row), 201


# ========== 订单系统：数据与业务（2026-09-17 新增，AprilPark1012需求） ==========
# 与合同完全同源：内存 store、按分区隔离、编号由服务端分配。
_ORDER_STORES: dict[str, list[dict]] = {}


def seed_orders() -> list[dict]:
    """预置 60 条订单（3 页 × 20 条）。

    **所有字段都按序号确定（不随机）**：这样「某销售员命中 10 条」「业务单元 bu_a 命中 20 条」
    这类断言才有确定的数（合同的 mu/file/bu 是随机的，订单这里刻意收严，便于断言条数与分页）。
    口径：订单编号 SO-1001…SO-1060 · 订单名称 订单1…订单60 ·
    合同编号 = 预置合同 HT-1001…HT-1020 循环（⇒ 点过去一定能看到**真实存在的**合同详情）；
    客户/销售员/订单类型/业务单元/管理单元/帐套 都按 (序号-1) % 选项数 取值。
    """
    rows: list[dict] = []
    for i in range(1, ORDER_PRESETS + 1):
        rows.append({
            "no": f"SO-{1000 + i}",
            "contract_no": f"HT-{1000 + ((i - 1) % PRESETS) + 1}",
            "name": f"订单{i}",
            "mu": MUS[(i - 1) % len(MUS)],
            "salesman": SALESMEN[(i - 1) % len(SALESMEN)]["id"],
            "order_type": ORDER_TYPES[(i - 1) % len(ORDER_TYPES)],
            "bu": BUS[(i - 1) % len(BUS)],
            "file": FILES[(i - 1) % len(FILES)],
            "cust": CUSTOMERS[(i - 1) % len(CUSTOMERS)]["id"],
            "remark": "",
        })
    return rows


def _order_store(part: str = "default") -> list[dict]:
    """取（必要时创建）某分区的订单列表（与合同同一套分区口径）。"""
    with _lock:
        lst = _ORDER_STORES.get(part)
        if lst is None:
            lst = seed_orders()
            _ORDER_STORES[part] = lst
        return lst


def with_order_names(row: dict) -> dict:
    """补 salesmanName / custName —— 页面直接渲染，不必各自再查一遍。"""
    d = dict(row)
    d["salesmanName"] = next((s["name"] for s in SALESMEN if s["id"] == d.get("salesman")),
                             d.get("salesman", ""))
    d["custName"] = next((c["name"] for c in CUSTOMERS if c["id"] == d.get("cust")),
                         d.get("cust", ""))
    return d


def dict_values(kind: str) -> list[str]:
    """「...」选择弹层的候选值：业务单元 / 管理单元 / 帐套（三者选择方式一致）。"""
    return {"bu": list(BUS), "mu": list(MUS), "file": list(FILES)}.get(kind or "", [])


def filter_orders(rows: list[dict], q: dict) -> list[dict]:
    """订单筛选口径（与页面上的提示文字一一对应）：

      · 订单名称  **全模糊**（包含）
      · 销售员    **右模糊**（前缀：姓名前缀 或 销售员编号前缀）
      · 客户      **全模糊**（包含：客户名称 或 客户编号）
      · 业务单元 / 管理单元 / 帐套  **精确**（值来自「...」弹层选择）
    """
    name = (q.get("name") or "").strip().lower()
    salesman = (q.get("salesman") or "").strip().lower()
    cust = (q.get("cust") or "").strip().lower()
    out: list[dict] = []
    for r in rows:
        rr = with_order_names(r)
        if name and name not in (r.get("name") or "").lower():
            continue
        if salesman and not ((rr["salesmanName"] or "").lower().startswith(salesman)
                             or (r.get("salesman") or "").lower().startswith(salesman)):
            continue
        if cust and not ((rr["custName"] or "").lower().find(cust) >= 0
                         or (r.get("cust") or "").lower().find(cust) >= 0):
            continue
        if q.get("bu") and r.get("bu") != q["bu"]:
            continue
        if q.get("mu") and r.get("mu") != q["mu"]:
            continue
        if q.get("file") and r.get("file") != q["file"]:
            continue
        out.append(rr)
    return out


def page_of(rows: list[dict], page: int, size: int) -> dict:
    """分页信息 + 当前页数据（**页码从 1 起**；越界夹到有效范围，不抛错）。"""
    try:
        size = max(1, int(size or ORDERS_PER_PAGE))
    except (TypeError, ValueError):
        size = ORDERS_PER_PAGE
    total = len(rows)
    pages = max(1, (total + size - 1) // size)
    try:
        page = int(page or 1)
    except (TypeError, ValueError):
        page = 1
    page = min(max(1, page), pages)
    start = (page - 1) * size
    return {"page": page, "size": size, "total": total, "pages": pages,
            "items": rows[start:start + size]}


def create_order(payload: dict, part: str = "default") -> tuple[dict, int]:
    """新建销售订单：校验必填 → 分配订单编号 → **插到最前** → 落库。

    ⚠️ 插到最前是需求要求：「点击提交，生成销售订单，回到订单系统页面，列表第一个就是我们新建的订单」
      （列表顺序 = 存储顺序；分页按存储顺序切 ⇒ 第一页第一行就是它）。
    """
    missing = [k for k in REQUIRED_ORDER if not str(payload.get(k) or "").strip()]
    if missing:
        # 提示语与前端一致（用例的 assert_guard.forbidden 依赖这句不会被当正常结果）
        return {"error": "请填写全部必填字段", "missing": missing}, 400
    with _lock:
        lst = _ORDER_STORES.setdefault(part, seed_orders())
        seq = 2001 + len(lst)
        no = f"SO-{seq}"
        while any(r["no"] == no for r in lst):
            seq += 1
            no = f"SO-{seq}"
        row = {"no": no, **{k: str(payload[k]).strip() for k in REQUIRED_ORDER}}
        row["remark"] = str(payload.get("remark") or "").strip()      # 唯一选填项
        lst.insert(0, row)                                            # ← 新订单在最前
        return with_order_names(row), 201


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
        part = self._part()
        if path == "/api/health":
            # 供测试框架/CI 探测「目标是否支持按 worker 分区」—— 支持则并发安全，不支持则该降级为串行
            with _lock:
                return self._send_json({"ok": True, "partitioned": PARTITIONS_ENABLED,
                                        "presets": PRESETS, "partitions": sorted(_STORES.keys()),
                                        "order_presets": ORDER_PRESETS,
                                        "orders_per_page": ORDERS_PER_PAGE,
                                        "order_pages": ORDER_PAGE_COUNT})
        if path == "/api/customers":
            return self._send_json(CUSTOMERS)
        if path == "/api/contracts":
            with _lock:
                return self._send_json([with_cust_name(r) for r in _store(part)])
        if path == "/api/contract":
            no = (urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("no") or [""])[0]
            with _lock:
                row = next((r for r in _store(part) if r["no"] == no), None)
            if row is None:
                return self._send_json({"error": f"未找到该合同: {no}"}, 404)
            return self._send_json(with_cust_name(row))
        # ---- 订单系统（2026-09-17 新增）----
        if path == "/api/orders":
            # 筛选 + 分页（**页码从 1 起**）；筛选口径见 filter_orders
            q = {k: (v[0] if v else "") for k, v in
                 urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).items()}
            with _lock:
                rows = filter_orders(_order_store(part), q)
                return self._send_json(page_of(rows, q.get("page"), q.get("size")))
        if path == "/api/order":
            no = (urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("no") or [""])[0]
            with _lock:
                row = next((r for r in _order_store(part) if r["no"] == no), None)
            if row is None:
                return self._send_json({"error": f"未找到该订单: {no}"}, 404)
            return self._send_json(with_order_names(row))
        if path == "/api/salesmen":
            return self._send_json(SALESMEN)
        if path == "/api/dict":
            # 「...」选择弹层的候选值：kind=bu|mu|file
            kind = (urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("kind") or [""])[0]
            return self._send_json({"kind": kind, "values": dict_values(kind)})
        if self.path in ("/", ""):
            # 根路径默认服务合同页（避免 SimpleHTTPRequestHandler 列出目录）
            self.path = "/" + DEFAULT_PAGE
        super().do_GET()

    def _part(self) -> str:
        return _part_of(urllib.parse.urlsplit(self.path).query)

    def do_POST(self):
        path = self._path_only()
        part = self._part()
        if path == "/api/reset":
            return self._send_json({"ok": True, "count": reset_data(part), "partition": part})
        if path == "/api/contracts":
            try:
                n = int(self.headers.get("Content-Length") or 0)
                payload = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            except Exception as e:
                return self._send_json({"error": f"请求体不是合法 JSON: {e}"}, 400)
            body, code = create_contract(payload if isinstance(payload, dict) else {}, part)
            return self._send_json(body, code)
        if path == "/api/orders":
            # 新建销售订单（必填校验在 create_order 里；订单备注选填）
            try:
                n = int(self.headers.get("Content-Length") or 0)
                payload = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            except Exception as e:
                return self._send_json({"error": f"请求体不是合法 JSON: {e}"}, 400)
            body, code = create_order(payload if isinstance(payload, dict) else {}, part)
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
    n = reset_data("default")
    with _Server(("", PORT), Handler) as httpd:
        print(f"[demo app] serving {DIR} on http://localhost:{PORT} (page={DEFAULT_PAGE})")
        print(f"[demo app] API: /api/customers /api/contracts /api/contract?no= /api/orders /api/order?no= "
              f"/api/salesmen /api/dict?kind= /api/reset /api/health"
              f"（已预置 {n} 条合同 + {ORDER_PRESETS} 条订单；分区={PARTITIONS_ENABLED}，用 ?w=<worker> 取独立分区）")
        print("[demo app] 页面: / (=合同管理) · /contracts.html · /contract_detail.html?no=HT-1005 · "
              "/orders.html (订单系统) · /order_detail.html?no=SO-1001")
        httpd.serve_forever()


if __name__ == "__main__":
    main()

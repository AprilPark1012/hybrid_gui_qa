"""被测 demo 应用：静态页面 + 内存数据 API。

2026-09-14 改造（AprilPark1012拍板需求②）：合同数据从「列表页 JS 每次刷新临时生成」搬到**服务端**，
让详情页读到的是**同一条真实记录** —— 新建的合同在详情页也能看到正确的客户；
页面刷新不再丢数据（更接近真实系统）。

接口（数据口径的**唯一来源**就是这个文件）：
  GET  /api/customers             该分区客户主数据（预置 6 个；可被「弹层内临时新建」追加）
  POST /api/customers             需求③：临时新建客户 {name, addr?} → 201；名称空 → 400；同名 → 409
  GET  /api/salesmen              该分区销售员主数据（预置 6 个；同上可临时新建）
  POST /api/salesmen              需求③：临时新建销售员 {name} → 201；名称空 → 400；同名 → 409
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
import glob
import http.server
import json
import os
import random
import re
import secrets
import shutil
import socketserver
import threading
import time
import urllib.parse

PORT = int(os.environ.get("TARGET_PORT", "8000"))
# ========== 版本标记（2026-09-28 起）==========
# 为什么要有它：demo 改到第几版很难一眼分辨（他就撞过一次「跑的是旧进程/旧包」）⇒
#   · 启动横幅会打印它   · /api/health 里也有 `build` 字段（浏览器直接开…/api/health 就能看）
#   · 打包时把这个值一并写进包里的「怎么跑」说明 ⇒ 三处对得上就是同一版
DEMO_BUILD = "P21-preview-20260928-2238"
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
# 需求⑫（2026-09-28 晚）：订单详情页「编辑 → 保存」允许改的字段。
# 其余（订单编号 no / 合同编号 contract_no / 销售员 salesman / 客户 cust）在页面上是 locked 只读 ⇒ 传了也忽略。
EDITABLE_ORDER = ("name", "order_type", "bu", "mu", "file")
# 需求㉒：新建订单弹层的「更多信息」四项（与订单详情页表单2 同一套）
MORE_ORDER_FIELDS = ("transport", "creator", "carrier", "channel")
# 表单2「更多信息」四项（单独落 extra 子对象，不动订单主字段）
ORDER_MORE_FIELDS = ("transport", "creator", "carrier", "channel")
# ↑ 必填：订单名称 / 合同 / 业务单元 / 管理单元 / 帐套 / 订单类型 / 客户 / 销售员
#   订单备注（remark）**选填**（唯一非必填项）

# ========== 订单详情节（P21.4 · 2026-09-28 需求⑥）==========
TRANSPORT_MODES = ["BY EXPRESS EMS", "BY AIR TRAIN 空客联运", "BY AIR 空运", "BY SEA 海运", "BY TRAIN 客运"]
LINE_TYPES = ["产品订单行", "许可证订单行", "软件订单行"]
CANCEL_REASONS = ["信息输入错误", "客户退货", "合同错误", "重复下单", "客户取消"]
# ---- 状态口径（2026-09-28 晚 · 需求⑧：行状态新增「已关闭」；订单状态由行汇总）----
LINE_STATES = ["已新建", "已挑选", "已出库", "已发货", "已签收", "已关闭"]   # 行的完整流转（需求第 8 条）
AUTO_STATES = ["已挑选", "已出库", "已发货", "已签收"]                      # 提交后**按时钟**自动推进的档位
CLOSED_STATE = "已关闭"                                                     # 只能由「关闭」动作产生（不自动）
FULFILL_STATES = list(AUTO_STATES)      # 兼容旧名（health.fulfill_states = 自动推进的四档）
ORDER_STATES = ["已新建", "履行中", "已关闭"]                               # 订单整体状态（三档汇总，他 09-28 晚拍定）
FULFILL_STEP_SECONDS = 30       # 提交后每 30 秒推进一档 —— 与需求 6.4 的「每 30 秒刷新」同频，
                                # 否则 20 秒推进 + 30 秒轮询会让「已发货」永远跳过（实测：0s 已挑选 → 30s 已出库 → 60s 已签收）。
                                # health 里声明该口径，用例可据此推算期望档位。
MAX_ORDER_LINES = 100           # 一个订单最多 100 行
LINE_UNITS = ["个", "件", "套", "千克"]
REQUIRED_LINE = ("material", "product", "qty", "line_type")   # 物料编码/产品编码/数量/行类型 必填

# ========== 应收发票（P21.5 · 需求⑦ + 晚 需求⑩「去开票」带入）==========
INVOICE_TYPES = ["增值税专用发票", "增值税普通发票", "电子普通发票"]
CURRENCIES = ["CNY", "USD", "EUR", "HKD"]
INVOICE_LINE_TYPES = ["物料行", "服务行", "费用行"]         # 取值由他 2026-09-28 拍定
PERIODS = [str(i) for i in range(1, 13)]                   # 期次号下拉：从 1 开始（1~12）
INVOICE_PRESETS = 30
REQUIRED_INVOICE = ("bu", "invoice_type", "invoice_date", "salesman", "currency", "cust")
# ↑ 发票号（no）**不列入必填**：留空 ⇒ 服务端自动分配（需求⑩「去开票」自动带入就是走这条路）
REQUIRED_INVOICE_LINE = ("period", "line_type", "qty")     # 期次号 / 发票行类型 / 数量

# ⚠️ 必须是 RLock（可重入）：`_store()` 自己加锁，而调用方（do_GET/do_POST）通常已持有该锁，
#    普通 Lock 会在第一次请求就**自死锁**（实测踩过：demo 整个卡住、curl 全部挂死）。
_lock = threading.RLock()         # ThreadingTCPServer：数据要被多线程访问
# ⚠️ 2026-09-14（F6）：数据按**分区**存放 —— 一个分区 = 一份独立的 20 条预置数据。
#    pytest-xdist 下每个 worker 用自己的分区（`?w=gw0` / cookie），**并发时互不踩**；
#    不带分区参数时用 "default"，行为与改造前完全一致（老用例/手工调试零影响）。
_STORES: dict[str, list[dict]] = {}
# 客户 / 销售员主数据也**按分区**（2026-09-18）：它们现在可被「弹层内临时新建」修改 ⇒ 必须与合同同口径隔离，
# 否则 A worker 新建的客户 B worker 也能看到、reset 也复位不掉（并发下用例互相污染）。
_CUST_STORES: dict[str, list[dict]] = {}
_SALE_STORES: dict[str, list[dict]] = {}
PRESETS = 20
PARTITIONS_ENABLED = os.environ.get("HYBRID_TARGET_PARTITIONED", "1") != "0"


def _part_of(query: str) -> str:
    """从 query string 取分区名（?w=gw0）；缺省 default。"""
    if not PARTITIONS_ENABLED:
        return "default"
    q = urllib.parse.parse_qs(query or "")
    return ((q.get("w") or [""])[0] or "").strip() or "default"


# ========== 数据持久化（需求⑯ · 2026-09-28 晚） ==========
# 口径：**新增/修改的数据要留住**（重启进程也不丢），除非用户主动删除或显式 /api/reset。
# 做法：每个分区一份 JSON（demo/.data/state_<分区>.json），**写操作成功后落盘**（Hook 在 _send_json），
#      分区第一次被访问时惰性加载（有文件读文件、没文件才播种预置）。
DATA_DIR = os.path.join(DIR, ".data")
_LOADED: set = set()


def _state_path(part: str = "default") -> str:
    safe = "".join(c for c in (part or "default") if c.isalnum() or c in "-_") or "default"
    return os.path.join(DATA_DIR, f"state_{safe}.json")


def dump_state(part: str = "default") -> None:
    """把该分区全部存储写盘（写操作成功后调用；失败只告警，绝不影响接口返回）。"""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        snapshot = {
            "version": 1, "saved_at": round(time.time(), 3),
            "contracts": _STORES.get(part, []),
            "orders": _ORDER_STORES.get(part, []),
            "lines": _LINE_STORES.get(part, {}),
            "fulfill": _FULFILL_STORES.get(part, {}),
            "customers": _CUST_STORES.get(part, []),
            "salesmen": _SALE_STORES.get(part, []),
            "invoices": _INV_STORES.get(part, []),
            "invoice_lines": _INV_LINE_STORES.get(part, {}),
        }
        tmp = _state_path(part) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False)
        os.replace(tmp, _state_path(part))          # 原子替换：中途崩了也不会留半份
    except Exception as e:                          # noqa: BLE001
        print(f"[demo app] ⚠️ 落盘失败（不影响接口）: {e}")


def _load_state(part: str = "default") -> bool:
    """尝试从盘上加载该分区；成功 ⇒ True。"""
    path = _state_path(part)
    if not os.path.exists(path):
        return False
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        _STORES[part] = d.get("contracts") or seed()
        _ORDER_STORES[part] = d.get("orders") or seed_orders()
        _LINE_STORES[part] = d.get("lines") or {}
        _FULFILL_STORES[part] = d.get("fulfill") or {}
        _CUST_STORES[part] = d.get("customers") or [dict(c) for c in CUSTOMERS]
        _SALE_STORES[part] = d.get("salesmen") or [dict(s) for s in SALESMEN]
        _INV_STORES[part] = d.get("invoices") or seed_invoices()
        _INV_LINE_STORES[part] = d.get("invoice_lines") or {}
        return True
    except Exception as e:                          # noqa: BLE001
        print(f"[demo app] ⚠️ 读取 {path} 失败（改用预置数据）: {e}")
        return False


def _ensure_loaded(part: str = "default") -> None:
    """惰性加载：某分区第一次被访问时读盘（需求⑯：重启不丢数据）。必须在 _lock 内调用。"""
    if part in _LOADED:
        return
    _LOADED.add(part)
    _load_state(part)


def _store(part: str = "default") -> list[dict]:
    """取（必要时创建）某分区的合同列表。加锁：ThreadingTCPServer 下多线程会同时进。"""
    with _lock:
        _ensure_loaded(part)
        lst = _STORES.get(part)
        if lst is None:
            lst = seed()
            _STORES[part] = lst
        return lst


def _cust_store(part: str = "default") -> list[dict]:
    """取（必要时创建）某分区的**客户主数据**（2026-09-18：客户开始按分区存）。

    为什么：需求③允许在弹层里**临时新建**客户 ⇒ 主数据变成可变的；若仍是模块级常量，
    分区隔离就破了（见 _CUST_STORES 的注释）。
    """
    with _lock:
        _ensure_loaded(part)
        lst = _CUST_STORES.get(part)
        if lst is None:
            lst = [dict(c) for c in CUSTOMERS]      # 复制：别让各分区共享同一批可变对象
            _CUST_STORES[part] = lst
        return lst


def _sale_store(part: str = "default") -> list[dict]:
    """取（必要时创建）某分区的**销售员主数据**（同上）。"""
    with _lock:
        _ensure_loaded(part)
        lst = _SALE_STORES.get(part)
        if lst is None:
            lst = [dict(s) for s in SALESMEN]
            _SALE_STORES[part] = lst
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
            "created_by": "",                  # 需求㉑：系统播种的预置数据 ⇒ 创建人 = 系统管理员（不是某个登录账号）
        })
    return rows


def with_cust_name(row: dict, part: str = "default") -> dict:
    """给记录补上 custName（客户名称）—— 页面/接口都直接拿它渲染，不必各自再查一遍。

    ⚠️ 走**该分区**的客户表（临时新建的客户也在里面），不能用模块级常量。
    """
    d = dict(row)
    d["custName"] = next((c["name"] for c in _cust_store(part) if c["id"] == d.get("cust")),
                         d.get("cust", ""))
    return d


def _backup_user_data(part: str = "default") -> str:
    """purge 复位前把当前状态另存一份（`demo/.data/state_<分区>.backup_<时间戳>.json`，只留最近 5 份）。

    起因（2026-09-28）：手工造的演示数据被一次判据复位抹掉过 ⇒ 既然逃不掉"测试要干净基线"，
    那就在清之前先留个可捞的备份，别让用户的数据真没了。
    """
    try:
        src = os.path.join(DIR, ".data", f"state_{part}.json")
        if not os.path.exists(src):
            return ""
        dst = os.path.join(DIR, ".data", f"state_{part}.backup_{time.strftime('%Y%m%d_%H%M%S')}.json")
        shutil.copyfile(src, dst)
        olds = sorted(glob.glob(os.path.join(DIR, ".data", f"state_{part}.backup_*.json")))
        for f in olds[:-5]:
            os.remove(f)
        return dst
    except Exception:
        return ""


def reset_data(part: str = "default", purge: bool = False) -> int:
    """把**该分区**复位成预置数据（合同 20 条 + 订单 60 条），返回合同条数。

    ⚠️ 2026-09-28 改口径（用户手工数据被复位抹掉过）：
      · 默认 `purge=False` ⇒ **只复原预置部分，用户手工新建的合同/订单/发票/客户/销售员原样保留**；
      · `POST /api/reset?purge=1` ⇒ 完全复原成预置（**用例间隔离**用；清之前会先备份一份）。
    只清自己那份 —— 这是并发安全的关键：A worker 的复位不再抹掉 B worker 正在依赖的数据。
    """
    c_nos = {f"HT-{1000 + i}" for i in range(1, PRESETS + 1)}
    o_nos = {f"SO-{1000 + i}" for i in range(1, ORDER_PRESETS + 1)}
    i_nos = {f"INV-{1000 + i}" for i in range(1, INVOICE_PRESETS + 1)}
    c_ids = {c["id"] for c in CUSTOMERS}
    s_ids = {s["id"] for s in SALESMEN}

    def keep(rows, preset_keys, key="no"):
        return [dict(r) for r in (rows or []) if str(r.get(key) or "") not in preset_keys]

    with _lock:
        if purge:
            _backup_user_data(part)
        user_c = [] if purge else keep(_STORES.get(part), c_nos)
        user_o = [] if purge else keep(_ORDER_STORES.get(part), o_nos)
        user_i = [] if purge else keep(_INV_STORES.get(part), i_nos)
        user_cust = [] if purge else keep(_CUST_STORES.get(part), c_ids, "id")
        user_sale = [] if purge else keep(_SALE_STORES.get(part), s_ids, "id")
        old_lines = dict(_LINE_STORES.get(part, {}))
        old_ful = dict(_FULFILL_STORES.get(part, {}))
        old_ilines = dict(_INV_LINE_STORES.get(part, {}))
        _STORES[part] = seed() + user_c
        _ORDER_STORES[part] = seed_orders() + user_o            # 预置在前，用户新建的接在后面
        _CUST_STORES[part] = [dict(c) for c in CUSTOMERS] + user_cust
        _SALE_STORES[part] = [dict(s) for s in SALESMEN] + user_sale
        # 行/履行/发票行：预置的重建，用户那份原样保留（含"已关闭"的行状态与履行进度）
        _LINE_STORES[part] = {r["no"]: old_lines.get(r["no"]) or seed_lines(r["no"]) for r in _ORDER_STORES[part]}
        _FULFILL_STORES[part] = {} if purge else {k: v for k, v in old_ful.items() if k not in o_nos}
        _INV_STORES[part] = seed_invoices() + user_i
        _INV_LINE_STORES[part] = {r["no"]: old_ilines.get(r["no"]) or seed_invoice_lines(r["no"])
                                  for r in _INV_STORES[part]}
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
        row["created_by"] = str((payload.get("_actor") or {}).get("user") or "")   # 需求⑰
        lst.append(row)
        return with_cust_name(row, part), 201


# ========== 订单系统：数据与业务（2026-09-17 新增，AprilPark1012需求） ==========
# 与合同完全同源：内存 store、按分区隔离、编号由服务端分配。
_ORDER_STORES: dict[str, list[dict]] = {}
# 订单行：part -> 订单号 -> [行]；履行状态：part -> 订单号 -> 提交时间戳（P21.4）
_LINE_STORES: dict[str, dict[str, list[dict]]] = {}
_FULFILL_STORES: dict[str, dict[str, float]] = {}


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
            "created_by": "",                  # 需求㉑：系统播种的预置数据 ⇒ 创建人 = 系统管理员（不是某个登录账号）
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


def with_order_names(row: dict, part: str = "default") -> dict:
    """补 salesmanName / custName —— 页面直接渲染，不必各自再查一遍（走该分区的主数据）。"""
    d = dict(row)
    d["salesmanName"] = next((s["name"] for s in _sale_store(part) if s["id"] == d.get("salesman")),
                             d.get("salesman", ""))
    d["custName"] = next((c["name"] for c in _cust_store(part) if c["id"] == d.get("cust")),
                         d.get("cust", ""))
    d["created_by_label"] = creator_label(d.get("created_by"))   # 需求㉑：页面别自己猜创建人
    return d


# ========== 角色与登录（需求⑮ · 2026-09-28 晚） ==========
# 四个角色 + 四个账号（**账号密码各不相同**；登录页把 demo 账号写在提示里，方便演示）
CONTRACT_ADMIN, ORDER_ADMIN, INVOICE_ADMIN, SUPER_ADMIN = (
    "contract_admin", "order_admin", "invoice_admin", "super_admin")
ROLE_LABELS = {CONTRACT_ADMIN: "合同管理员", ORDER_ADMIN: "订单管理员",
               INVOICE_ADMIN: "发票管理员", SUPER_ADMIN: "超级管理员"}
# 角色 → 演示账号名（需求㉑：自动化入口也用演示账号当身份，
# 否则 created_by 会落成 "__test__"、抬头显示「创建人：__test__」）
ROLE_ACCOUNTS = {CONTRACT_ADMIN: "contract", ORDER_ADMIN: "order",
                 INVOICE_ADMIN: "invoice", SUPER_ADMIN: "super"}
ROLES = (CONTRACT_ADMIN, ORDER_ADMIN, INVOICE_ADMIN, SUPER_ADMIN)
ACCOUNTS = {
    "contract": {"pwd": "contract@123", "role": CONTRACT_ADMIN},
    "order": {"pwd": "order@123", "role": ORDER_ADMIN},
    "invoice": {"pwd": "invoice@123", "role": INVOICE_ADMIN},
    "super": {"pwd": "super@123", "role": SUPER_ADMIN},
}
# 权限矩阵（需求⑮ 口径）：
#   · 查看合同/订单/发票 —— **四个角色都有**（读取类接口不设闸，匿名也能读，见 do_POST 收口点说明）
#   · 新建合同 / 新建订单 / 创建发票 —— 只给**对应角色的管理员**（超管要先用头像切到该角色，需求⑮-3）
#   · 新建客户 —— **四个角色都有**（需求⑮-4）
PERMISSIONS = {
    "view_contract": ROLES, "view_order": ROLES, "view_invoice": ROLES,
    "create_contract": (CONTRACT_ADMIN,), "create_order": (ORDER_ADMIN,),
    "create_invoice": (INVOICE_ADMIN,), "create_customer": ROLES,
}
ACTION_LABELS = {"create_contract": "新建合同", "create_order": "新建订单",
                 "create_invoice": "创建发票", "create_customer": "新建客户"}
# 写接口 → 需要的权限（**唯一收口点**：do_POST 开头按这张表统一校验，别在各分支里各写一份）
POST_ACTIONS = {
    "/api/contracts": "create_contract",
    "/api/orders": "create_order",
    "/api/invoices": "create_invoice",
    "/api/customers": "create_customer",
    "/api/salesmen": "create_customer",          # 弹层内新建销售员与客户同权限
}
# **记录级**动作（改/删某一条）：只要求「已登录」，能不能改**这一条**由 `may_edit()` 判 ——
# 需求⑰：创建人 或 对应管理员（超管切到该角色也算）。⇒ 不能再在这里按角色一刀切，
# 否则「切到别的角色后改自己建的那条」永远走不到创建人规则（会被角色闸先拦成 403）。
POST_RECORD_ACTIONS = {
    "/api/order/update": "create_order", "/api/order/lines": "create_order",
    "/api/order/submit": "create_order", "/api/order/lines/close": "create_order",
    "/api/order/cancel": "create_order", "/api/invoice/delete": "create_invoice",
    "/api/invoice/update": "create_invoice",     # 需求⑲：发票详情「编辑→保存」（登录即可，逐条判创建人/发票管理员）
}
_SESSIONS: dict = {}                             # token -> {"user","role","super","source"}


def may_edit(actor, row: dict, admin_role: str, admin_label: str):
    """需求⑰：**谁建的谁能改自己那条** —— 创建人 或 对应管理员（超管切到该角色也算）。

    返回 None = 放行；否则返回 (body, code) 给调用方直接返回。
    """
    if actor is None:
        return {"error": "未登录：请先登录", "login": "/login.html"}, 401
    roles = actor.get("roles") or [actor.get("role")]
    if admin_role in roles:
        return None
    owner = str((row or {}).get("created_by") or "").strip()
    if owner and owner == str(actor.get("user") or "").strip():
        return None
    return {"error": f"这条不是你创建的（创建人：{creator_label(owner)}），"
                     f"只有创建人或者{admin_label}能改", "created_by": owner,
            "role": actor.get("role")}, 403


CREATOR_LABELS = {"contract": "合同管理员", "order": "订单管理员",
                  "invoice": "发票管理员", "super": "超级管理员",
                  "__test__": "自动化测试账号"}   # 兜底：老数据里可能已经落了 __test__


def _with_creator_labels(body):
    """需求㉑：凡是回传里带 `created_by` 的对象，自动补上 `created_by_label`。

    放在 `_send_json` 这个**唯一出口**做兜底 —— 合同/订单/发票各条返回路径一次覆盖，
    页面只管渲染 label，不必各自猜（只补不覆盖：订单/发票的 with_* 出口已带的保持原样）。
    """
    if isinstance(body, dict):
        if "created_by" in body and "created_by_label" not in body:
            body = dict(body)
            body["created_by_label"] = creator_label(body.get("created_by"))
        if isinstance(body.get("items"), list):
            body = dict(body)
            body["items"] = [_with_creator_labels(x) for x in body["items"]]
        return body
    if isinstance(body, list):
        return [_with_creator_labels(x) for x in body]
    return body


def creator_label(value) -> str:
    """把创建人的**账号**翻成**看得懂的名字**（需求㉑）。

    · 空 ⇒ 「系统管理员」（系统播种的预置数据，不是某个登录账号建的）；
    · 已知演示账号 ⇒ 对应角色名；其它 ⇒ 原样返回（不吞信息）。
    """
    v = str(value or "").strip()
    if not v or v in ("system", "system_admin"):
        return "系统管理员"
    return CREATOR_LABELS.get(v, v)


def me_payload(sess: dict) -> dict:
    """当前身份 + 能做什么（页面拿它渲染头像与按钮可用性）。"""
    role = (sess or {}).get("role")
    return {
        "user": (sess or {}).get("user", ""),
        "role": role, "role_label": ROLE_LABELS.get(role, role or "未登录"),
        "is_super": bool((sess or {}).get("super")),
        "source": (sess or {}).get("source", ""),
        "viewing_as": (sess or {}).get("viewing_as") or "",
        "can": {a: any(x in allowed for x in ((sess or {}).get("roles") or [role]))
                for a, allowed in PERMISSIONS.items()},
        # 需求⑮-3：只有超管看得到「可切换的角色」清单
        "switchable": [r for r in ROLES if r != SUPER_ADMIN] if (sess or {}).get("super") else [],
    }


def login(payload: dict) -> tuple[dict, int]:
    """登录：账号密码对 ⇒ 发 token（内存会话；重启 demo 即失效，demo 够用）。"""
    u = str(payload.get("username") or "").strip()
    p = str(payload.get("password") or "")
    acc = ACCOUNTS.get(u)
    if not acc or acc["pwd"] != p:
        return {"error": "账号或密码不对（demo 账号见登录页提示）"}, 401
    tok = secrets.token_urlsafe(16)
    _SESSIONS[tok] = {"user": u, "role": acc["role"],
                      "super": acc["role"] == SUPER_ADMIN, "source": "session"}
    return {"token": tok, **me_payload(_SESSIONS[tok])}, 200


def logout(tok: str) -> tuple[dict, int]:
    _SESSIONS.pop(tok or "", None)
    return {"ok": True}, 200


def switch_role(tok: str, sess, payload: dict) -> tuple[dict, int]:
    """需求⑮-3：**只有超级管理员**能把当前会话切到 合同/订单/发票管理员，去干那些活。"""
    if sess is None:
        return {"error": "未登录：请先登录", "login": "/login.html"}, 401
    # ⚠️ 判据是 **is_super（超管身份）**，不是「当前扮演的角色」——
    #    否则超管一旦切到订单管理员，就再也切不回来/切不到别的角色（切角色当场把自己锁死）。
    if not sess.get("super"):
        return {"error": f"只有{ROLE_LABELS[SUPER_ADMIN]}可以切换角色"
                         f"（当前：{ROLE_LABELS.get(sess.get('role'), '未登录')}）"}, 403
    if sess.get("source") != "session" or not tok or tok not in _SESSIONS:
        return {"error": "切换角色需要真实登录会话（测试角色头不支持切换）"}, 400
    role = str(payload.get("role") or "").strip()
    if role not in ROLES:
        return {"error": "只能切到：合同管理员 / 订单管理员 / 发票管理员（或切回超级管理员）"}, 400
    _SESSIONS[tok]["role"] = role                # 超管身份保留（is_super 不变），只是「以该角色行事」
    _SESSIONS[tok]["viewing_as"] = "" if role == SUPER_ADMIN else role
    return {"ok": True, **me_payload(_SESSIONS[tok])}, 200


# ========== 应收发票：数据与业务（P21.5 · 2026-09-28） ==========
_INV_STORES: dict[str, list[dict]] = {}
_INV_LINE_STORES: dict[str, dict[str, list[dict]]] = {}


def seed_invoices() -> list[dict]:
    """预置 30 张应收发票。**全部字段按序号确定（不随机）** ⇒ 「某业务单元命中 10 张」这类断言有确定的数。

    口径：发票号 INV-1001…INV-1030 · 合同编号 = 预置合同 HT-1001…HT-1020 循环 ·
    业务单元/发票类型/销售员/币种/客户 都按 (序号-1) % 选项数 取值；发票日期 = 2026-09-01~09-28 循环。
    """
    rows: list[dict] = []
    for i in range(1, INVOICE_PRESETS + 1):
        rows.append({
            "no": f"INV-{1000 + i}",
            "contract_no": f"HT-{1000 + ((i - 1) % PRESETS) + 1}",
            "bu": BUS[(i - 1) % len(BUS)],
            "invoice_type": INVOICE_TYPES[(i - 1) % len(INVOICE_TYPES)],
            "invoice_date": f"2026-09-{(i - 1) % 28 + 1:02d}",
            "salesman": SALESMEN[(i - 1) % len(SALESMEN)]["id"],
            "currency": CURRENCIES[(i - 1) % len(CURRENCIES)],
            "cust": CUSTOMERS[(i - 1) % len(CUSTOMERS)]["id"],
        })
    return rows


def seed_invoice_lines(no: str) -> list[dict]:
    """预置发票行（1 行；表头口径 = 期次号 / 发票行类型 / 数量 / 单位）。"""
    return [{"line_no": 1, "period": "1", "line_type": "物料行", "qty": "10", "unit": "个"}]


def _inv_store(part: str = "default") -> list[dict]:
    """取（必要时创建）某分区的发票列表（与合同/订单同一套分区口径）。"""
    with _lock:
        lst = _INV_STORES.get(part)
        if lst is None:
            lst = seed_invoices()
            _INV_STORES[part] = lst
        return lst


def _inv_lines_of(part: str, no: str) -> list[dict]:
    with _lock:
        return _INV_LINE_STORES.setdefault(part, {}).setdefault(no, seed_invoice_lines(no))


def with_invoice_names(row: dict, part: str = "default") -> dict:
    """补 salesmanName / custName（走该分区主数据）。"""
    d = dict(row)
    d["salesmanName"] = next((s["name"] for s in _sale_store(part) if s["id"] == d.get("salesman")),
                             d.get("salesman", ""))
    d["custName"] = next((c["name"] for c in _cust_store(part) if c["id"] == d.get("cust")),
                         d.get("cust", ""))
    d["line_count"] = len(_inv_lines_of(part, d["no"]))
    d["created_by_label"] = creator_label(d.get("created_by"))   # 需求㉑：页面别自己猜创建人
    return d


def next_invoice_no(part: str = "default") -> str:
    """下一个可用发票号（新建/「去开票」自动带入用）：INV-2001 起，避开已有号。"""
    with _lock:
        lst = _inv_store(part)
        seq = 2001 + len(lst)
        no = f"INV-{seq}"
        while any(r["no"] == no for r in lst):
            seq += 1
            no = f"INV-{seq}"
        return no


def filter_invoices(rows: list[dict], q: dict, part: str = "default") -> list[dict]:
    """发票筛选口径（与页面提示一一对应）：

      · 业务单元  **精确**（值来自下拉/弹层选择）
      · 发票号    **全模糊**（包含）
      · 合同编号  **全模糊**（包含）
    """
    no = (q.get("no") or "").strip().lower()
    contract = (q.get("contract_no") or "").strip().lower()
    out: list[dict] = []
    for r in rows:
        if no and no not in (r.get("no") or "").lower():
            continue
        if contract and contract not in (r.get("contract_no") or "").lower():
            continue
        if q.get("bu") and r.get("bu") != q["bu"]:
            continue
        out.append(with_invoice_names(r, part))
    return out


def create_invoice(payload: dict, part: str = "default") -> tuple[dict, int]:
    """新建应收发票：**校验来源订单已关闭（需求⑪）** + 校验必填（发票号可留空 ⇒ 服务端分配）
    + 校验发票行 ⇒ **插到最前** → 落库。"""
    # 需求⑪（2026-09-28 晚）：**只有「已关闭」的订单才能开票**。
    # 客户端那道闸（订单页按钮 / 开票页直链）都可被绕开（直接 POST）⇒ 服务端按同一口径复核，且这是权威判定。
    src = str(payload.get("from_order") or "").strip()
    if src:
        if not _order_exists(part, src):
            return {"error": f"未找到来源订单: {src}"}, 404
        st = order_status(part, src)
        if st != CLOSED_STATE:
            return {"error": f"订单 {src} 当前状态为「{st}」，只有「{CLOSED_STATE}」的订单才能开票",
                    "order_status": st}, 400
        # 需求⑳：**已开票的订单不允许再次开票**（发票删除后自动解锁，见 order_invoiced）
        _inv_no = order_invoiced(part, src)
        if _inv_no:
            return {"error": f"订单 {src} 已开票（发票号 {_inv_no}），不允许再次开票",
                    "invoice_no": _inv_no, "invoiced": True}, 400
    missing = [k for k in REQUIRED_INVOICE if not str(payload.get(k) or "").strip()]
    if missing:
        return {"error": "请填写全部必填字段", "missing": missing}, 400
    lines = payload.get("lines")
    if lines is None:
        lines = []
    if not isinstance(lines, list):
        return {"error": "lines 必须是数组"}, 400
    clean: list[dict] = []
    for i, ln in enumerate(lines, start=1):
        if not isinstance(ln, dict):
            return {"error": "行格式不正确"}, 400
        bad = [k for k in REQUIRED_INVOICE_LINE if not str(ln.get(k) or "").strip()]
        if bad:
            return {"error": "行必填项未填全", "missing": bad, "line_no": i}, 400
        period = str(ln.get("period")).strip()
        if period not in PERIODS:
            return {"error": f"期次号必须是 {PERIODS[0]}~{PERIODS[-1]}", "line_no": i, "period": period}, 400
        clean.append({"line_no": i, "period": period,
                      "line_type": str(ln.get("line_type")).strip(),
                      "qty": str(ln.get("qty")).strip(),
                      "unit": str(ln.get("unit") or LINE_UNITS[0]).strip()})
    with _lock:
        lst = _INV_STORES.setdefault(part, seed_invoices())
        no = str(payload.get("no") or "").strip()
        if not no:
            no = next_invoice_no(part)
        elif any(r["no"] == no for r in lst):
            return {"error": f"发票号已存在: {no}"}, 409
        row = {"no": no, **{k: str(payload[k]).strip() for k in REQUIRED_INVOICE}}
        row["contract_no"] = str(payload.get("contract_no") or "").strip()
        # 「去开票」带上来的来源订单号（可追溯；选填）
        row["from_order"] = str(payload.get("from_order") or "").strip()
        row["created_by"] = str((payload.get("_actor") or {}).get("user") or "")   # 需求⑰
        lst.insert(0, row)                                   # ← 新发票在最前（列表第一条就是它）
        _INV_LINE_STORES.setdefault(part, {})[no] = clean
        return {**with_invoice_names(row, part), "lines": clean}, 201


def update_invoice(payload: dict, part: str = "default", actor=None) -> tuple[dict, int]:
    """**保存发票**（需求⑲：发票详情页「编辑 → 保存」）—— 基础信息 + 发票行一起落库。

    口径：
      · 基础信息只认 REQUIRED_INVOICE 那六项（发票号 no 是主键、不支持改；合同编号 contract_no 可跟着改）；
      · 行：整组替换（与发票创建同口径），每行必填 期次号/发票行类型/数量，期次号必须在 1~12；
      · 合并后仍要满足必填，否则 400 且**不落库**；
      · 权限（需求⑰/⑲）：创建人 或 发票管理员（超管切到该角色也算）。
    """
    no = str(payload.get("no") or "").strip()
    fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else {}
    lines = payload.get("lines")
    with _lock:
        lst = _inv_store(part)
        row = next((r for r in lst if r["no"] == no), None)
        if row is None:
            return {"error": f"未找到该发票: {no}"}, 404
        _denied = may_edit(actor, row, INVOICE_ADMIN, ROLE_LABELS[INVOICE_ADMIN])   # 需求⑰/⑲
        if _denied:
            return _denied
        merged = {k: (str(fields[k]).strip() if k in fields else str(row.get(k) or ""))
                  for k in REQUIRED_INVOICE}
        missing = [k for k in REQUIRED_INVOICE if not merged[k]]
        if missing:
            return {"error": "请填写全部必填字段", "missing": missing}, 400
        clean: list[dict] = []
        if isinstance(lines, list):
            for i, ln in enumerate(lines, start=1):
                if not isinstance(ln, dict):
                    return {"error": "行格式不正确"}, 400
                bad = [k for k in REQUIRED_INVOICE_LINE if not str(ln.get(k) or "").strip()]
                if bad:
                    return {"error": "行必填项未填全", "missing": bad, "line_no": i}, 400
                period = str(ln.get("period")).strip()
                if period not in PERIODS:
                    return {"error": f"期次号必须是 {PERIODS[0]}~{PERIODS[-1]}", "line_no": i}, 400
                clean.append({"line_no": i, "period": period,
                              "line_type": str(ln.get("line_type")).strip(),
                              "qty": str(ln.get("qty")).strip(),
                              "unit": str(ln.get("unit") or LINE_UNITS[0]).strip()})
        for k in REQUIRED_INVOICE:
            if k in fields:
                row[k] = merged[k]
        if "contract_no" in fields:
            row["contract_no"] = str(fields.get("contract_no") or "").strip()
        if isinstance(lines, list):
            _INV_LINE_STORES.setdefault(part, {})[no] = clean
            row["line_count"] = len(clean)
        snapshot = dict(row)
        out_lines = clean if isinstance(lines, list) else _INV_LINE_STORES.get(part, {}).get(no, [])
    return {**with_invoice_names(snapshot, part), "lines": out_lines}, 200


def delete_invoice(part: str, no: str) -> tuple[dict, int]:
    """删除发票（列表页操作区「删除」）。"""
    with _lock:
        lst = _inv_store(part)
        row = next((r for r in lst if r["no"] == no), None)
        if row is None:
            return {"error": f"未找到该发票: {no}"}, 404
        lst.remove(row)
        _INV_LINE_STORES.setdefault(part, {}).pop(no, None)
        return {"ok": True, "no": no, "remaining": len(lst)}, 200


def dict_values(kind: str) -> list[str]:
    """字典候选值：业务单元/管理单元/帐套（「...」弹层）+ 订单行类型/运输方式/订单类型（P21.4 联想下拉）。"""
    return {"bu": list(BUS), "mu": list(MUS), "file": list(FILES),
            "line_type": list(LINE_TYPES), "transport": list(TRANSPORT_MODES),
            "order_type": list(ORDER_TYPES),
            # P21.5 发票字典：发票行类型 / 发票类型 / 币种 / 期次号
            "invoice_line_type": list(INVOICE_LINE_TYPES),
            "invoice_type": list(INVOICE_TYPES),
            "currency": list(CURRENCIES),
            "period": list(PERIODS)}.get(kind or "", [])


# ---------- 订单详情节：行 / 履行状态 / 取消（P21.4）----------
def seed_lines(no: str) -> list[dict]:
    """预置订单的示例行（2 行）—— 让详情页首次打开就有行可断言。"""
    return [
        {"line_no": 1, "material": "M-1001", "product": "P-1001", "qty": "10",
         "unit": "个", "line_type": "产品订单行", "revenue": "1000", "closed": False},
        {"line_no": 2, "material": "M-1002", "product": "P-1002", "qty": "5",
         "unit": "件", "line_type": "许可证订单行", "revenue": "500", "closed": False},
    ]


def _lines_of(part: str, no: str) -> list[dict]:
    """取（必要时创建）某订单的行列表。"""
    with _lock:
        return _LINE_STORES.setdefault(part, {}).setdefault(no, seed_lines(no))


def _order_exists(part: str, no: str) -> bool:
    return any(r["no"] == no for r in _order_store(part))


def _line_status(part: str, no: str, ln: dict) -> str:
    """**行状态**（需求⑧完整流转）：已关闭（手工，优先于时钟）> 已新建（未提交）> 已挑选/已出库/已发货/已签收（按时钟推进）。"""
    if ln.get("closed"):
        return CLOSED_STATE
    ts = _FULFILL_STORES.get(part, {}).get(no)
    if not ts:
        return LINE_STATES[0]                      # 已新建
    elapsed = max(0.0, time.time() - ts)
    idx = min(len(AUTO_STATES) - 1, int(elapsed // FULFILL_STEP_SECONDS))
    return AUTO_STATES[idx]


def order_invoiced(part: str = "default", order_no: str = "") -> str:
    """该订单**是否已开票**（需求⑳）—— 返回发票号；未开票返回 ""。

    关联口径：发票上记的 `from_order`（「去开票」带过来的来源订单号）即关联关系。
    发票被删除后，这里自然回到「未开票」（每次现算，不另存状态位）⇒ 不会出现"删了发票还锁着"的脏状态。
    """
    if not order_no:
        return ""
    for r in _inv_store(part):
        if str(r.get("from_order") or "").strip() == order_no:
            return r.get("no") or ""
    return ""


def _lines_with_status(part: str, no: str) -> list[dict]:
    """带「状态」的行列表（计算值，不落库 —— 避免状态被写进存储后与时钟脱钩）。"""
    out = []
    for ln in _lines_of(part, no):
        d = dict(ln)
        d["status"] = _line_status(part, no, ln)
        out.append(d)
    return out


def order_status(part: str, no: str) -> str:
    """**订单整体状态**（三档汇总，他 2026-09-28 晚拍定）：

      · 所有行都已关闭  ⇒ 已关闭
      · 已提交且未全关  ⇒ 履行中
      · 其余（未提交）  ⇒ 已新建
    """
    lines = _lines_of(part, no)
    if lines and all(ln.get("closed") for ln in lines):
        return "已关闭"
    if _FULFILL_STORES.get(part, {}).get(no):
        return "履行中"
    return "已新建"


def close_order_lines(part: str, no: str, line_nos=None, actor=None) -> tuple[dict, int]:
    """**关闭订单行**（需求⑧：手工动作，不是时钟推进；line_nos 空/缺省 ⇒ 全部关闭）。

    关掉的行状态固定为「已关闭」，不再随提交后的时钟变化；全部行关闭 ⇒ 订单状态变「已关闭」。
    """
    with _lock:
        row = next((r for r in _order_store(part) if r["no"] == no), None)
        if row is None:
            return {"error": f"未找到该订单: {no}"}, 404
        _denied = may_edit(actor, row, ORDER_ADMIN, ROLE_LABELS[ORDER_ADMIN])   # 需求⑰
        if _denied:
            return _denied
        lines = _lines_of(part, no)
        if not lines:
            return {"error": "该订单没有可关闭的行"}, 400
        want = None
        if line_nos:
            try:
                want = {int(x) for x in line_nos}
            except (TypeError, ValueError):
                return {"error": "line_nos 必须是行号数组"}, 400
            bad = sorted(n for n in want if n < 1 or n > len(lines))
            if bad:
                return {"error": "行号超出范围", "line_nos": bad}, 400
        for i, ln in enumerate(lines, start=1):
            if want is None or i in want:
                ln["closed"] = True
        closed = [i for i, ln in enumerate(lines, start=1) if ln.get("closed")]
        return {"no": no, "closed_lines": closed, "all_closed": len(closed) == len(lines),
                "order_status": order_status(part, no), "lines": _lines_with_status(part, no)}, 201


def save_order_lines(part: str, no: str, lines, actor=None) -> tuple[dict, int]:
    """保存订单行：校验必填（物料编码/产品编码/数量/行类型）+ 上限 100 行；行号服务端按序重编。"""
    if not isinstance(lines, list):
        return {"error": "lines 必须是数组"}, 400
    if len(lines) > MAX_ORDER_LINES:
        return {"error": f"一个订单最多 {MAX_ORDER_LINES} 行", "max": MAX_ORDER_LINES}, 400
    with _lock:
        row = next((r for r in _order_store(part) if r["no"] == no), None)
        if row is None:
            return {"error": f"未找到该订单: {no}"}, 404
        _denied = may_edit(actor, row, ORDER_ADMIN, ROLE_LABELS[ORDER_ADMIN])   # 需求⑰
        if _denied:
            return _denied
        out: list[dict] = []
        for i, ln in enumerate(lines, start=1):
            if not isinstance(ln, dict):
                return {"error": "行格式不正确"}, 400
            missing = [k for k in REQUIRED_LINE if not str(ln.get(k) or "").strip()]
            if missing:
                return {"error": "行必填项未填全", "missing": missing, "line_no": i}, 400
            out.append({"line_no": i,
                        "material": str(ln.get("material") or "").strip(),
                        "product": str(ln.get("product") or "").strip(),
                        "qty": str(ln.get("qty") or "").strip(),
                        "unit": str(ln.get("unit") or "").strip(),
                        "line_type": str(ln.get("line_type") or "").strip(),
                        "revenue": str(ln.get("revenue") or "").strip(),
                        "closed": bool(ln.get("closed"))})     # 保存要保住「已关闭」，否则关过的行又被时钟推回去
        _LINE_STORES.setdefault(part, {})[no] = out
        return {"no": no, "lines": _lines_with_status(part, no), "saved": len(out),
                "max": MAX_ORDER_LINES, "order_status": order_status(part, no)}, 201


def submit_fulfill(part: str, no: str, actor=None) -> tuple[dict, int]:
    """提交订单履行：只记录提交时间 —— 状态由 fulfill_of 按「经过秒数」推进（可测、不随机）。"""
    with _lock:
        row = next((r for r in _order_store(part) if r["no"] == no), None)
        if row is None:
            return {"error": f"未找到该订单: {no}"}, 404
        _denied = may_edit(actor, row, ORDER_ADMIN, ROLE_LABELS[ORDER_ADMIN])   # 需求⑰
        if _denied:
            return _denied
        ts = time.time()
        _FULFILL_STORES.setdefault(part, {})[no] = ts
        return {"no": no, "submitted": True, "submitted_at": round(ts, 3),
                "step_seconds": FULFILL_STEP_SECONDS, "states": list(FULFILL_STATES)}, 201


def fulfill_of(part: str, no: str) -> dict:
    """订单履行状态（行「状态」列用它）：未提交 ⇒ status 空；已提交 ⇒ 每 FULFILL_STEP_SECONDS 秒推进一档。"""
    with _lock:
        ts = _FULFILL_STORES.get(part, {}).get(no)
        lines = _lines_with_status(part, no)
        base = {"no": no, "states": list(FULFILL_STATES), "step_seconds": FULFILL_STEP_SECONDS,
                "lines": lines, "max": MAX_ORDER_LINES, "line_types": list(LINE_TYPES),
                "line_states": list(LINE_STATES), "order_status": order_status(part, no),
                "closed_lines": [ln["line_no"] for ln in lines if ln.get("closed")]}
        if not ts:
            return {**base, "submitted": False, "elapsed": 0, "state": ""}
        elapsed = max(0.0, time.time() - ts)
        idx = min(len(AUTO_STATES) - 1, int(elapsed // FULFILL_STEP_SECONDS))
        return {**base, "submitted": True, "elapsed": round(elapsed, 1),
                "state": AUTO_STATES[idx]}
        # 注：行「状态」列按同一时钟逐行计算（见 _lines_with_status）；已关闭的行不跟随时钟


def cancel_order(part: str, no: str, reason, actor=None) -> tuple[dict, int]:
    """取消订单（= **删除**）：必须先填「取消原因」，原因空 ⇒ 400。"""
    reason = str(reason or "").strip()
    if not reason:
        return {"error": "请填写取消原因"}, 400
    with _lock:
        lst = _order_store(part)
        row = next((r for r in lst if r["no"] == no), None)
        if row is None:
            return {"error": f"未找到该订单: {no}"}, 404
        _denied = may_edit(actor, row, ORDER_ADMIN, ROLE_LABELS[ORDER_ADMIN])   # 需求⑰
        if _denied:
            return _denied
        lst.remove(row)
        _LINE_STORES.setdefault(part, {}).pop(no, None)
        _FULFILL_STORES.setdefault(part, {}).pop(no, None)
        return {"ok": True, "no": no, "reason": reason, "remaining": len(lst)}, 200


def filter_orders(rows: list[dict], q: dict, part: str = "default") -> list[dict]:
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
        rr = with_order_names(r, part)
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
        rr["status"] = order_status(part, r["no"])     # 需求⑨：订单列表新增「状态」列
        rr["invoiced"] = bool(order_invoiced(part, r["no"]))       # 需求⑳：是否开票（列表新增一列）
        rr["invoice_no"] = order_invoiced(part, r["no"])
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
    """新建销售订单：校验必填 → 分配订单编号 → **插到最前** → 落库（可选带「更多信息」+ 订单行，需求㉒）。

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
        row["created_by"] = str((payload.get("_actor") or {}).get("user") or "")   # 需求⑰
        row["remark"] = str(payload.get("remark") or "").strip()      # 唯一选填项
        more = payload.get("more") if isinstance(payload.get("more"), dict) else None
        if more:                                                      # 需求㉒：更多信息四项落 extra
            row["extra"] = {k: str(more.get(k) or "").strip() for k in MORE_ORDER_FIELDS}
        lst.insert(0, row)                                            # ← 新订单在最前
    # 需求㉒：新建时就能录订单行 —— 在锁外调 save_order_lines（它自己会加锁）；
    #         行不合法 ⇒ **整单回滚**，绝不留「订单建了但行没落」的半成品
    lines = payload.get("lines")
    if isinstance(lines, list) and lines:
        body, code = save_order_lines(part, no, lines, payload.get("_actor"))
        if code >= 400:
            with _lock:
                store = _order_store(part)
                if row in store:
                    store.remove(row)
            return body, code
        return {**with_order_names(row, part), "lines": body.get("lines", []), "saved": body.get("saved"),
                "order_status": body.get("order_status")}, 201
    return with_order_names(row, part), 201


def update_order(payload: dict, part: str = "default", actor=None) -> tuple[dict, int]:
    """**保存订单字段**（需求⑫：订单详情页「编辑 → 保存」= 表单1 + 表单2 + 表单3）。

    口径（与页面按钮一一对应）：
      · 表单1 只允许改 `EDITABLE_ORDER` —— 订单编号/合同编号/销售员/客户在页面是 locked 只读，
        传上来了也**忽略**（不报错，静默按只读处理）；
      · 表单2 四项（运输方式/创建人/承运商/销售渠道）落 `extra` 子对象；
      · 合并后**仍必须满足 REQUIRED_ORDER**（必填不许被清空）⇒ 否则 400「请填写全部必填字段」且**不落库**；
      · 表单3 的订单行不走这里，仍走 POST /api/order/lines（页面「保存」会两次调用，同一个 no）。
    """
    no = str(payload.get("no") or "").strip()
    fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else {}
    more = payload.get("more") if isinstance(payload.get("more"), dict) else {}
    with _lock:
        row = next((r for r in _order_store(part) if r["no"] == no), None)
        if row is None:
            return {"error": f"未找到该订单: {no}"}, 404
        _denied = may_edit(actor, row, ORDER_ADMIN, ROLE_LABELS[ORDER_ADMIN])   # 需求⑰
        if _denied:
            return _denied
        # 先合并且**校验必填**，通过了才动数据（保证「报错就不落库」）
        merged = {k: (str(fields[k]).strip() if k in fields else str(row.get(k) or ""))
                  for k in REQUIRED_ORDER}
        missing = [k for k in REQUIRED_ORDER if not merged[k]]
        if missing:
            return {"error": "请填写全部必填字段", "missing": missing}, 400
        for k in EDITABLE_ORDER:
            if k in fields:
                row[k] = merged[k]
        extra = dict(row.get("extra") or {})
        for k in ORDER_MORE_FIELDS:
            if k in more:
                extra[k] = str(more[k] or "").strip()
        if extra:
            row["extra"] = extra
        snapshot_row = dict(row)
    # ⚠️ 出锁再拼名字（with_order_names 会碰主数据仓；与 create_order 同一写法）
    return {**with_order_names(snapshot_row, part), "order_status": order_status(part, no)}, 200


def create_customer(payload: dict, part: str = "default") -> tuple[dict, int]:
    """需求③：弹层内**临时新建客户** → 落该分区主数据（后续搜索能搜到、订单能引用）。

    口径：客户名称必填；**同名拒绝**（409）—— 「搜不到才新建」的场景下同名说明已存在，
    允许重名只会让人分不清选的是哪一条；地址选填。id 由服务端分配（c7、c8…）。
    """
    name = str(payload.get("name") or "").strip()
    if not name:
        return {"error": "客户名称不能为空", "missing": ["name"]}, 400
    with _lock:
        lst = _cust_store(part)
        if any(c["name"] == name for c in lst):
            return {"error": f"客户已存在: {name}"}, 409
        seq = len(lst) + 1
        cid = f"c{seq}"
        while any(c["id"] == cid for c in lst):
            seq += 1
            cid = f"c{seq}"
        rec = {"id": cid, "name": name, "addr": str(payload.get("addr") or "").strip(),
               "created_by": str((payload.get("_actor") or {}).get("user") or "")}   # 需求⑰
        lst.append(rec)
        return dict(rec), 201


def create_salesman(payload: dict, part: str = "default") -> tuple[dict, int]:
    """需求③：弹层内**临时新建销售员** → 落该分区主数据。姓名必填，同名拒绝（409）。"""
    name = str(payload.get("name") or "").strip()
    if not name:
        return {"error": "销售员姓名不能为空", "missing": ["name"]}, 400
    with _lock:
        lst = _sale_store(part)
        if any(s["name"] == name for s in lst):
            return {"error": f"销售员已存在: {name}"}, 409
        seq = len(lst) + 1
        sid = f"s{seq}"
        while any(s["id"] == sid for s in lst):
            seq += 1
            sid = f"s{seq}"
        rec = {"id": sid, "name": name}
        lst.append(rec)
        return dict(rec), 201


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        """需求㉓（2026-09-28）：**静态页面也禁缓存**。

        起因：用户反馈「点订单编号 / 订单名称，有些订单进去还是老的订单详情页」——
        静态页走 SimpleHTTPRequestHandler 默认带缓存（浏览器可能拿旧版 order_detail.html），
        同一个 URL 却在缓存里是旧实现 ⇒ 看起来就像「部分订单用了老页面」。
        加这三个头 + 让静态资源也不缓存，F5 / 重新点链接一定拿到当前文件。
        """
        if self._path_only().endswith((".html", ".js", ".css")):
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
        super().end_headers()

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=DIR, **kw)

    # ---- 小工具 ----
    def _send_json(self, obj, code=200):
        # 需求⑯：**写操作成功就落盘**（唯一 Hook，含 /api/reset 之后的状态）⇒ 重启不丢数据
        if code < 400 and self.command == "POST" and self._path_only() != "/api/login":
            dump_state(self._part())
        obj = _with_creator_labels(obj)     # 需求㉑：创建人显示口径统一在出口兜底
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")   # 测试要读到最新数据，不许缓存
        self.end_headers()
        self.wfile.write(body)

    def _path_only(self) -> str:
        return urllib.parse.urlsplit(self.path).path

    def _body(self) -> tuple[dict, dict | None]:
        """读并解析 JSON 请求体 → (payload, err)；err 非 None 时直接回 400。"""
        try:
            n = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except Exception as e:
            return {}, {"error": f"请求体不是合法 JSON: {e}"}
        payload = payload if isinstance(payload, dict) else {}
        payload["_actor"] = self._auth()      # 需求⑰：把当前身份挂进来，供创建人/编辑权限判定
        return payload, None

    # ---- 角色与登录（需求⑮）----
    def _token(self) -> str:
        t = (self.headers.get("X-Demo-Token") or "").strip()
        if t:
            return t
        return (urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("token") or [""])[0].strip()

    def _auth(self):
        """身份解析：① 页面登录的 session token（header 或 ?token=）

        ② （**测试专用**）`X-Demo-Role` 头 / `?demo_role=` —— 给自动化直连用（框架 / 用例 / 二类脚本
           不必走登录页）。页面上**没有**任何入口能下发这个头；它的存在是为了不把自动化链路全锁在登录页后面。
        """
        tok = self._token()
        if tok and tok in _SESSIONS:
            return {**_SESSIONS[tok], "token": tok, "source": "session"}
        r = (self.headers.get("X-Demo-Role") or "").strip() or \
            (urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("demo_role") or [""])[0].strip()
        # 支持多角色（逗号/竖线分隔）：自动化常要跨角色（例：关订单行=订单管理员 → 开票=发票管理员）
        roles = [x.strip() for x in re.split(r"[,\|]", r) if x.strip() in ROLES]
        if roles:
            return {"user": ROLE_ACCOUNTS.get(roles[0], "__test__"), "role": roles[0], "roles": roles,
                    "super": SUPER_ADMIN in roles, "source": "test-header"}
        return None

    def _require(self, action: str):
        """写接口权限闸：放行 ⇒ None；否则返回 (body, code)，调用方直接 `_send_json(*x)`。"""
        sess = self._auth()
        if sess is None:
            return {"error": f"未登录：「{ACTION_LABELS.get(action, action)}」需要先登录（对应角色的管理员）",
                    "login": "/login.html", "action": action}, 401
        roles = sess.get("roles") or [sess.get("role")]
        if not any(x in PERMISSIONS.get(action, ()) for x in roles):
            hint = "，可用右上角头像切换角色后再试" if sess.get("super") or sess["role"] == SUPER_ADMIN else ""
            return {"error": f"当前角色「{ROLE_LABELS.get(sess['role'], sess['role'])}」"
                             f"没有「{ACTION_LABELS.get(action, action)}」权限{hint}",
                    "role": sess["role"], "role_label": ROLE_LABELS.get(sess["role"]),
                    "action": action}, 403
        return None

    # ---- 路由 ----
    def do_GET(self):
        path = self._path_only()
        part = self._part()
        _ensure_loaded(part)          # 需求⑯：该分区第一次被访问 ⇒ 从盘上加载（没有盘文件才播种）
        if path == "/api/health":
            # 供测试框架/CI 探测「目标是否支持按 worker 分区」—— 支持则并发安全，不支持则该降级为串行
            with _lock:
                return self._send_json({"ok": True, "partitioned": PARTITIONS_ENABLED,
                                        "presets": PRESETS, "partitions": sorted(_STORES.keys()),
                                        "order_presets": ORDER_PRESETS,
                                        "orders_per_page": ORDERS_PER_PAGE,
                                        "order_pages": ORDER_PAGE_COUNT,
                                        # 能力声明：弹层内可临时新建客户/销售员（2026-09-18 需求③）
                                        "cust_create": True, "salesman_create": True,
                                        # P21.4 订单详情能力声明（框架/用例可据此判断目标形态）
                                        "order_lines": True, "max_order_lines": MAX_ORDER_LINES,
                                        "fulfill_states": list(FULFILL_STATES),
                                        "fulfill_step_seconds": FULFILL_STEP_SECONDS,
                                        "line_types": list(LINE_TYPES),
                                        "line_units": list(LINE_UNITS),
                                        "transport_modes": list(TRANSPORT_MODES),
                                        "cancel_reasons": list(CANCEL_REASONS),
                                        # 2026-09-28 晚 需求⑧⑨⑩：状态口径 + 发票能力声明
                                        "line_states": list(LINE_STATES),
                                        "order_states": list(ORDER_STATES),
                                        "closed_state": CLOSED_STATE,
                                        "order_status_column": True,     # 订单列表有「状态」列
                                        "order_update": True,            # 需求⑫：订单详情「编辑→保存」有落库接口
                                        "order_to_invoice": True,        # 订单页有「去开票」
                                        "invoice": True, "invoice_presets": INVOICE_PRESETS,
                                        "invoice_types": list(INVOICE_TYPES),
                                        "currencies": list(CURRENCIES),
                                        "invoice_line_types": list(INVOICE_LINE_TYPES),
                                        "periods": list(PERIODS),
                                        "invoice_required": list(REQUIRED_INVOICE),
                                        "invoice_update": True,          # 需求⑲：发票详情可编辑保存
                                        "order_invoiced_column": True,   # 需求⑳：订单列表有「是否开票」列
                                        "reset_keeps_user_data": True,     # 复位默认不抹用户手工数据（?purge=1 才清）
                                        "new_order_three_sections": True,  # 需求㉒：新建订单 = 3 区域 + 保存/取消
                                        "order_create_with_lines": True,   # 需求㉒：新建时可带订单行（一条请求落库）
                                        "one_invoice_per_order": True,   # 需求⑳：已开票的订单不允许再次开票
                                        # 需求⑪：开票前置条件 —— 只有「已关闭」(closed_state) 的订单能开票
                                        "invoice_requires_closed": True,
                                        # 需求⑮：登录与角色系统（矩阵给框架/用例判断用，不含密码）
                                        "auth": True, "roles": list(ROLES), "role_labels": ROLE_LABELS,
                                        "permissions": {k: list(v) for k, v in PERMISSIONS.items()},
                                        "write_actions": POST_ACTIONS,
                                        "record_actions": POST_RECORD_ACTIONS,   # 需求⑰：登录即可，逐条判创建人
                                        "anonymous_write": False,   # 写接口匿名一律 401
                                        "invoice_line_required": list(REQUIRED_INVOICE_LINE),
                                        # 版本标记（识别「跑的是哪一版 demo」，见 DEMO_BUILD 注释）
                                        "build": DEMO_BUILD})
        if path == "/api/roles":
            # 登录页/页面用来渲染角色清单与权限矩阵（不含密码）
            return self._send_json({"roles": [{"id": r, "label": ROLE_LABELS[r]} for r in ROLES],
                                    "permissions": {k: list(v) for k, v in PERMISSIONS.items()},
                                    "actions": ACTION_LABELS})
        if path == "/api/me":
            sess = self._auth()
            if sess is None:
                return self._send_json({"error": "未登录", "login": "/login.html"}, 401)
            return self._send_json(me_payload(sess))
        if path == "/api/customers":
            with _lock:
                return self._send_json([dict(c) for c in _cust_store(part)])
        if path == "/api/contracts":
            with _lock:
                return self._send_json([with_cust_name(r, part) for r in _store(part)])
        if path == "/api/contract":
            no = (urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("no") or [""])[0]
            with _lock:
                row = next((r for r in _store(part) if r["no"] == no), None)
            if row is None:
                return self._send_json({"error": f"未找到该合同: {no}"}, 404)
            return self._send_json(with_cust_name(row, part))
        # ---- 订单系统（2026-09-17 新增）----
        if path == "/api/orders":
            # 筛选 + 分页（**页码从 1 起**）；筛选口径见 filter_orders
            q = {k: (v[0] if v else "") for k, v in
                 urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).items()}
            with _lock:
                rows = filter_orders(_order_store(part), q, part)
                return self._send_json(page_of(rows, q.get("page"), q.get("size")))
        if path == "/api/order":
            no = (urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("no") or [""])[0]
            with _lock:
                row = next((r for r in _order_store(part) if r["no"] == no), None)
            if row is None:
                return self._send_json({"error": f"未找到该订单: {no}"}, 404)
            d = with_order_names(row, part)
            d["status"] = order_status(part, no)          # 需求⑧/⑨：订单整体状态（详情页也展示）
            d["invoiced"] = bool(order_invoiced(part, no))             # 需求⑳：开票页直链要判它
            d["invoice_no"] = order_invoiced(part, no)
            return self._send_json(d)
        if path == "/api/salesmen":
            with _lock:
                return self._send_json([dict(s) for s in _sale_store(part)])
        if path == "/api/order/lines":
            no = (urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("no") or [""])[0]
            with _lock:
                if not _order_exists(part, no):
                    return self._send_json({"error": f"未找到该订单: {no}"}, 404)
                return self._send_json({"no": no, "lines": _lines_with_status(part, no),
                                        "max": MAX_ORDER_LINES, "line_states": list(LINE_STATES),
                                        "order_status": order_status(part, no)})
        if path == "/api/order/fulfill":
            no = (urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("no") or [""])[0]
            with _lock:
                if not _order_exists(part, no):
                    return self._send_json({"error": f"未找到该订单: {no}"}, 404)
            return self._send_json(fulfill_of(part, no))
        if path == "/api/order/cancel_reasons":
            return self._send_json({"reasons": list(CANCEL_REASONS)})
        if path == "/api/transport_modes":
            return self._send_json({"values": list(TRANSPORT_MODES)})
        # ---- 应收发票（P21.5）----
        if path == "/api/invoices":
            q = {k: (v[0] if v else "") for k, v in
                 urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).items()}
            with _lock:
                rows = filter_invoices(_inv_store(part), q, part)
                return self._send_json(page_of(rows, q.get("page"), q.get("size") or INVOICE_PRESETS))
        if path == "/api/invoice":
            no = (urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("no") or [""])[0]
            with _lock:
                row = next((r for r in _inv_store(part) if r["no"] == no), None)
                if row is None:
                    return self._send_json({"error": f"未找到该发票: {no}"}, 404)
                return self._send_json({**with_invoice_names(row, part),
                                        "lines": _inv_lines_of(part, no)})
        if path == "/api/invoice/next_no":
            with _lock:
                return self._send_json({"no": next_invoice_no(part)})
        if path == "/api/invoice/lines":
            no = (urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("no") or [""])[0]
            with _lock:
                if not any(r["no"] == no for r in _inv_store(part)):
                    return self._send_json({"error": f"未找到该发票: {no}"}, 404)
                return self._send_json({"no": no, "lines": _inv_lines_of(part, no),
                                        "line_types": list(INVOICE_LINE_TYPES),
                                        "periods": list(PERIODS), "units": list(LINE_UNITS)})
        if path == "/api/dict":
            # 「...」选择弹层的候选值：kind=bu|mu|file|line_type|transport|order_type
            kind = (urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("kind") or [""])[0]
            return self._send_json({"kind": kind, "values": dict_values(kind)})
        if path == "/favicon.ico":
            # 浏览器自动请求的图标：给 204 空响应 ⇒ 免掉控制台「Failed to load resource: 404」噪音。
            # ⚠️ 必须放在 `super().do_GET()`（SimpleHTTP 静态服务）**之前** —— 它一旦处理就没法回头。
            # 纯静态兜底，不改任何 /api/* 语义。
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.path in ("/", ""):
            # 根路径默认服务合同页（避免 SimpleHTTPRequestHandler 列出目录）
            self.path = "/" + DEFAULT_PAGE
        super().do_GET()

    def _part(self) -> str:
        return _part_of(urllib.parse.urlsplit(self.path).query)

    def do_POST(self):
        path = self._path_only()
        part = self._part()
        _ensure_loaded(part)          # 需求⑯：同上
        if path == "/api/reset":
            # 默认只复原预置（保留用户手工数据）；测试要干净基线就 ?purge=1
            _purge = str((urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                          .get("purge") or ["0"])[0]).lower() in ("1", "true", "yes", "on")
            return self._send_json({"ok": True, "count": reset_data(part, purge=_purge),
                                    "partition": part, "purge": _purge,
                                    "note": "默认保留手工新建的数据；?purge=1 才完全复原"})
        # ---- 需求⑮：登录 / 登出 / 超管切换角色 ----
        if path == "/api/login":
            payload, err = self._body()
            if err:
                return self._send_json(err, 400)
            return self._send_json(*login(payload if isinstance(payload, dict) else {}))
        if path == "/api/logout":
            payload, err = self._body()
            if err:
                return self._send_json(err, 400)
            tok = str((payload or {}).get("token") or self._token())
            return self._send_json(*logout(tok))
        if path == "/api/switch_role":
            payload, err = self._body()
            if err:
                return self._send_json(err, 400)
            return self._send_json(*switch_role(self._token(), self._auth(),
                                                payload if isinstance(payload, dict) else {}))
        # ---- 需求⑮：写接口统一过权限闸（唯一收口点）----
        #   · 匿名 ⇒ 401（读接口不设闸 ⇒ 「任何管理员都能查看」；自动化直连读取不受影响）
        #   · 角色不符 ⇒ 403（带 role/action，页面据此提示；超管会多一句「切角色」指引）
        #   · 自动化如需扮演某角色：带测试头 X-Demo-Role（或 ?demo_role=），见 Handler._auth
        _action = POST_ACTIONS.get(path)
        if _action:
            _denied = self._require(_action)
            if _denied:
                return self._send_json(*_denied)
        # 记录级动作：只查登录态；「这一条能不能改」留给各业务函数里的 may_edit()（需求⑰）
        if path in POST_RECORD_ACTIONS and self._auth() is None:
            return self._send_json({"error": "未登录：请先登录", "login": "/login.html"}, 401)
        if path == "/api/contracts":
            try:
                n = int(self.headers.get("Content-Length") or 0)
                payload = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            except Exception as e:
                return self._send_json({"error": f"请求体不是合法 JSON: {e}"}, 400)
            body, code = create_contract({**(payload if isinstance(payload, dict) else {}),
                              "_actor": self._auth()}, part)          # 需求⑰：带上当前身份
            return self._send_json(body, code)
        if path == "/api/orders":
            # 新建销售订单（必填校验在 create_order 里；订单备注选填）
            try:
                n = int(self.headers.get("Content-Length") or 0)
                payload = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            except Exception as e:
                return self._send_json({"error": f"请求体不是合法 JSON: {e}"}, 400)
            body, code = create_order({**(payload if isinstance(payload, dict) else {}),
                              "_actor": self._auth()}, part)          # 需求⑰：带上当前身份
            return self._send_json(body, code)
        # ---- 需求③：弹层内临时新建（落该分区主数据）----
        if path == "/api/customers":
            payload, err = self._body()
            if err:
                return self._send_json(err, 400)
            body, code = create_customer(payload, part)
            return self._send_json(body, code)
        if path == "/api/salesmen":
            payload, err = self._body()
            if err:
                return self._send_json(err, 400)
            body, code = create_salesman(payload, part)
            return self._send_json(body, code)
        # ---- 订单详情节（P21.4）----
        if path == "/api/order/lines":
            payload, err = self._body()
            if err:
                return self._send_json(err, 400)
            body, code = save_order_lines(part, str(payload.get("no") or ""), payload.get("lines"),
                                          payload.get("_actor"))
            return self._send_json(body, code)
        if path == "/api/order/update":
            # 需求⑫：订单详情页「编辑 → 保存」（表单1 + 表单2 的字段）
            payload, err = self._body()
            if err:
                return self._send_json(err, 400)
            body, code = update_order(payload if isinstance(payload, dict) else {}, part,
                                      payload.get("_actor"))
            return self._send_json(body, code)
        if path == "/api/order/submit":
            payload, err = self._body()
            if err:
                return self._send_json(err, 400)
            body, code = submit_fulfill(part, str(payload.get("no") or ""), payload.get("_actor"))
            return self._send_json(body, code)
        if path == "/api/order/cancel":
            payload, err = self._body()
            if err:
                return self._send_json(err, 400)
            body, code = cancel_order(part, str(payload.get("no") or ""), payload.get("reason"),
                                      payload.get("_actor"))
            return self._send_json(body, code)
        if path == "/api/order/lines/close":
            # 需求⑧：手工关闭订单行（line_nos 省略/为空 ⇒ 全部关闭）
            payload, err = self._body()
            if err:
                return self._send_json(err, 400)
            body, code = close_order_lines(part, str(payload.get("no") or ""), payload.get("line_nos"),
                                           payload.get("_actor"))
            return self._send_json(body, code)
        # ---- 应收发票（P21.5）----
        if path == "/api/invoices":
            payload, err = self._body()
            if err:
                return self._send_json(err, 400)
            body, code = create_invoice({**payload, "_actor": self._auth()}, part)   # 需求⑰：带当前身份
            return self._send_json(body, code)
        if path == "/api/invoice/update":
            # 需求⑲：发票详情页「保存」（基础信息 + 发票行）
            payload, err = self._body()
            if err:
                return self._send_json(err, 400)
            body, code = update_invoice(payload if isinstance(payload, dict) else {}, part,
                                        payload.get("_actor"))
            return self._send_json(body, code)
        if path == "/api/invoice/delete":
            payload, err = self._body()
            if err:
                return self._send_json(err, 400)
            body, code = delete_invoice(part, str(payload.get("no") or ""))
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
    n = len(_store("default"))     # 需求⑯：启动**加载盘上数据**（只有没有盘文件时才播种预置）
    with _Server(("", PORT), Handler) as httpd:
        print(f"[demo app] serving {DIR} on http://localhost:{PORT} (page={DEFAULT_PAGE})")
        print(f"[demo app] build = {DEMO_BUILD}   ← 版本标记（/api/health 里也有 build 字段，可核对）")
        print(f"[demo app] API: /api/customers /api/contracts /api/contract?no= /api/orders /api/order?no= "
              f"/api/salesmen /api/dict?kind= /api/order/lines?no= /api/order/fulfill?no= "
              f"/api/order/cancel_reasons /api/transport_modes /api/order/lines|update|submit|cancel|lines/close "
              f"/api/invoices /api/invoice?no= /api/invoice/next_no /api/invoice/lines /api/invoice/delete "
              f"/api/reset /api/health /api/login /api/logout /api/me /api/switch_role /api/roles"
              f"（已预置 {n} 条合同 + {ORDER_PRESETS} 条订单 + {INVOICE_PRESETS} 张发票；"
              f"分区={PARTITIONS_ENABLED}，用 ?w=<worker> 取独立分区）")
        print("[demo app] 页面: / (=合同管理) · /contracts.html · /contract_detail.html?no=HT-1005 · "
              "/orders.html (订单系统) · /order_detail.html?no=SO-1001 · "
              "/invoice_list.html (应收发票列表) · /invoice_create.html (应收发票创建)")
        httpd.serve_forever()


if __name__ == "__main__":
    main()

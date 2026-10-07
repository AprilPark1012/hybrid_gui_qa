# hybrid_gui_qa V8.3.1 升级说明（2026-10-07）

> 本版**不含框架特性实现的变更** —— 是**测试体系与验证机制的升级**：
> 把 `tests/` 按框架的 **9 个特性**分文件夹，让「**哪条特性在验证、哪条是空的**」一眼可见；
> 并新增**特性验证闭环**（R7-g / R7-h）：特性一变更就必须同步判据、每次交付邮件必带「特性 × 验证结果」表。
> 顺带**修掉 4 条"看着绿、实则空转"的失效判据**。

## 一、为什么要改（真实现象）

| 现象 | 真值 |
|---|---|
| 说不清「哪条特性被验证」 | 测试按「一类/二类」两目录组织 ⇒ 文件夹**不体现框架有多少特性**，只能靠人脑记 |
| 判据**空转**却全绿 | `test_docs_sync` 找的目录串在重组后**已不存在** ⇒ 恒真；`test_path_join_contract` 的 `NAMES` 写死旧目录名 ⇒ 恒过 |
| 判据**守着旧结构** | `test_test_layout_contract` 的断言写死 `frameworkTest`/`featureTest`；判据名字本身就叫 `test_framework_tests_live_in_frameworkTest` |
| 新写的脚本自身不合规 | 新脚本 `subprocess.run(text=True)` **漏 `encoding=`** ⇒ Windows（cp936）会 `UnicodeDecodeError` |
| 「有实现、没判据」被淹没 | 特性 5「自愈闭环 Healer」**零判据**，但没有任何地方显式说出来 |

## 二、本版改动

### ① `tests/` 按框架 9 个特性重组（一类与二类**同住一个特性夹**）

```
tests/
├── 特性1-混合链路/ … 特性9-CLI帮助契约/    9 个特性夹
│     ├── test_*.py    一类判据（秒级、不需 demo/浏览器）
│     └── verify_*.py  二类验证（端到端、需 demo、含负向）
├── _helpers/    公共模块：repo_files · artifacts · testid_policy · demo_freshness · _gen_layout
├── _runner/     入口与工具：run_verifications.py · run_acceptance.py · rerecord_cassettes.py · fixtures/
└── conftest.py  统一把 _helpers 补进 sys.path
```

- 9 个特性名**取自 `docs/training.html` 第 7 章**（唯一命名来源，不另立清单）；
- runner 收录口径 = **递归** `tests/**/verify_*.py`（新增脚本自动被收录，**不许手写清单**）；
- **有实现、零判据的特性必须显式标记**：该特性夹里放 `UNVERIFIED.md`
  （现存 `tests/特性5-自愈闭环Healer/UNVERIFIED.md`，对应遗留 L11）。

### ② 场景 2（手搓链路）常驻样例 + E2E 验证脚本

- `cases/manual/manual_order_create_smoke.json`（15 步 / 2 断言）+ 生成物；
  ⚠️ 手搓用例**必须自带 `auth` 段**（生成器原生支持「用例自带 auth 优先于场景声明」）——
  不带 ⇒ 没有登录前置 ⇒ 报 `元素语义未找到: 超@合同列表页`（**看着像定位问题，其实是登录前置缺失**）。
- `tests/特性1-混合链路/verify_e2e_scenario2_handwritten.py`（7 条判据）：
  **离线可证伪** —— 跑生成与执行时把 `DEEPSEEK_BASE_URL` 指黑洞 `127.0.0.1:9` 并清空 key，
  **跑通本身即证明这条链没碰 AI**；含**负向自证**（"页面打不开 ⇒ 执行必红"）+ **零残留**。

### ③ 「特性 × 验证结果」报告

- `tests/_runner/feature_verification_report.py`：特性来源 = 特性夹目录名；一类走 junitxml 分组、
  二类读 runner 日志；有 `UNVERIFIED.md` 的特性标 ⏭️。
- 本版报告随包附上：`docs/feature_verification_report.md`。

### ④ 项目原则 R7 刷新（验证纪律）

| 小节 | 变更 |
|---|---|
| **R7-a** | 目录分工 → 9 特性结构；新增「**对不上 9 特性的存量 test = 失效 test**，要审视内容后删/改」 |
| **R7-b** | 命令口径更新（`pytest tests/` / `tests/_runner/run_verifications.py --jobs 1`）|
| **R7-e** | 三场景表加「**双环境**」列：**日常 = 场景2 + 场景3**（都不碰外网/key ⇒ 云主机与**内网 Windows 都能跑通**）；场景1 只在发版前、有 key 的云主机跑 |
| **R7-g**（新增） | **特性验证闭环 5 步**：一类先行（钉住能力）→ 二类日常 → 发版前场景1 → 双环境 → 标记未验证特性；并规定**每次交付邮件必带「特性 × 验证结果」表** |
| **R7-g 第 0 步** | **跑 test 之前必须先过 demo 新鲜度闸门**（`demo_freshness.py --ensure`）—— 避免 demo 改了没重启、验证跑在旧页面上（历史假绿同源）|
| **R7-h**（新增） | **特性 ↔ test 用例同步**：新增特性 ⇒ 一类/二类各至少加一条；修改特性 ⇒ 改对应判据；删除特性 ⇒ 删对应判据 |
| **两版跑法** | **日常版**（一类 + 场景2+3）与 **发版版**（一类 + 二类全量 + 场景1）—— **两版都 ≤30 分钟** |
| **demo 变化规则** | **demo 一变** ⇒ 日常先跑一次场景1 并**当场重录 LLM 录像**，之后日常回到场景2+3（录像键 = sha256(场景文案 + 控件骨架)，不重录则内网场景3 直接跑不了）|

## 三、修掉的 4 条失效判据（都是"审视内容"抓出来的）

| 判据 | 毛病 | 修法 |
|---|---|---|
| `test_test_layout_contract.py` | 断言写死旧目录名 | 按 9 特性结构**重写**，并新增「零判据必须标 UNVERIFIED」 |
| `test_docs_sync.py` | 找的目录串已不存在 + 父节点匹配恒空 ⇒ **空转** | 改按目录名匹配；负向样本改成真实结构 |
| `test_path_join_contract.py` | `NAMES` 写死旧目录名 ⇒ **恒过** | 改成**动态取 `tests/` 下真实目录名**——修好后**立刻**又抓到真问题 |
| `test_utf8_io.py` | 新脚本漏 `encoding=` | 补齐（**Windows cp936 会炸**，是跨平台硬要求）|

另修：`_gen_layout.py` 归位 `_helpers/`；`verify_cross_page.py` 在 import 前补路径
（独立脚本不经过 conftest，也**不能依赖 runner 主进程的 sys.path —— 子进程不继承**）。

## 四、验证真值（本机实测）

| 通道 | 命令 | 结果 | 耗时 |
|---|---|---|---|
| 一类 | `python -m pytest tests/ -q` | **677 passed / 0 failed / 1 skipped** | 27.8s |
| 二类（日常版）| `python tests/_runner/run_verifications.py --jobs 1` | **15 通过 / 1 失败（L22）** | ~11 min |
| 场景2 E2E | `verify_e2e_scenario2_handwritten.py` | **6/6 通过**（离线可证伪）| — |
| **合计** | | | **≈12 分钟**（上限 **30 分钟** ✓）|

## 五、遗留项（如实列出，不藏）

| 项 | 说明 |
|---|---|
| **L22** | 慢目标下行区**就绪信号缺失** ⇒ `verify_slow_target` 是唯一红（1 条）|
| **特性 5** | 自愈闭环 Healer **零判据**（有实现 `framework/tools/run/healer.py`、无任何行为判据）⇒ `UNVERIFIED.md` |
| **场景 1** | 本版未跑（demo 未变）⇒ 按 R7-e **发版前补**；若 demo 有变，则日常先跑 + 重录录像 |

## 六、升级与验证方式

1. 解压交付包；
2. 环境：Python 3.11 + `pip install -r requirements`（见包内 README，含 `cli setup` 一条命令）；
3. 起 demo：`python -m demo.app`（http://localhost:8000）；
4. **跑 test 前先过新鲜度闸门**：`python tests/_helpers/demo_freshness.py --ensure --start-if-missing`；
5. 日常验证（**不需外网/key**）：
   ```
   python -m pytest tests/ -q
   python tests/_runner/run_verifications.py --jobs 1
   ```
6. 报告：`python tests/_runner/feature_verification_report.py --class2-log <二类日志>` ⇒ 输出「特性 × 验证结果」表。

# hybrid_gui_qa V7.4 发布说明

> ## 补丁 V7.4.1（2026-09-14）— 空目录根因清理
> **现象**：仓库里出现空目录残留（`generated_tests/` · `output/plans/`）。
> **根因**：不是「忘了 rmdir」，而是 `config.py` **声明了没人使用的目录** —— 唯一"效果"就是被
> `ensure_dirs()` 每次启动建出来（删掉也会复活）。
> **修复**：删 4 个死概念常量（`PLAN_DIR` / `GENERATED_TESTS_DIR` / `TEST_SCENARIO_DIR` / `DATASETS_DIR`）
> + 收窄 `ensure_dirs()` 急切创建范围（`output/` `output/element_maps/` `log/` `scripts/` `cases/`；
> `heals/` `traces/` 改由写入方使用前自建）+ 新增防复发测试
> `tests/test_cli_exit_codes.py::test_ensure_dirs_only_declares_used_dirs`。
> **验证**：框架自测 **87 passed**（原 86 + 1）｜端到端 `cli all` **16 Passed / 0 Failed / exit 0**｜
> 运行后 `find -type d -empty` 复查为空。**功能与用例集不变**，本文件以下正文仍为 V7.4 发布内容。

    版本      V7.4
    日期      2026-09-14
    上一版    V7.3（2026-09-13，统一 UTF-8）
    测试基线  16 条用例全绿（12 条手写 + 4 条 AI）· 框架自测 86 条 · 三个端到端验证脚本全过

---

## 一、本次重点（按重要性）

### 1. 客户字段改造：下拉框 → 弹层列表里选一行
- 新建弹窗的客户 = 只读输入框「请选择客户」+ 按钮「选择客户」→ 点按钮弹出**客户列表层**
  （两列：客户名称 / 客户地址），点该行「选择」按钮回填并关层。
- 列表页的客户筛选 = **输入框 + 右模糊（前缀）匹配**（客户名称前缀或客户编号前缀；
  输入「华信」这种非前缀**不命中**，用来证明是右模糊而不是包含匹配）。
- **语义名契约**：弹层里 6 个「选择」按钮文字完全相同，只能按所在行区分 ⇒
  探测后语义名形如 `选择@北京华信科技有限公司`，用例里写这个名字才能定位。

### 2. 被测 demo 的数据搬到服务端（单一数据源）
`demo/app.py` 现在既是静态服务器也是数据 API：

| 接口 | 说明 |
|---|---|
| `GET /api/customers` | 6 个客户主数据（名称 + 地址） |
| `GET /api/contracts` | 全部合同（含客户名称） |
| `GET /api/contract?no=HT-1005` | 单条；查不到 → 404（`未找到该合同`） |
| `POST /api/contracts` | 新建（6 项必填校验；**编号由服务端分配**） |
| `POST /api/reset` | 复位成预置 20 条（测试用例间隔离用） |

收益：列表页与详情页读的是**同一条记录** —— 预置数据的七个字段跨页完全一致（可硬断言）；
**新建的合同在详情页也能看到正确的客户**（改造前详情页按编号序号推导，新建合同的客户在详情页是错的）；
查不到的编号**如实报「未找到」**，不再给任何编号编一份数据出来。

### 3. 用例间数据复位（数据留在服务端的必要配套）
生成的 `conftest.py` 为每条用例开始前 `POST /api/reset`（autouse fixture `_reset_target_data`）。
不复位时，新建用例写进服务端的数据会打乱「列表恢复 20 行」这类断言 —— 用例互相污染比用例失败更难查。
口径：`HYBRID_RESET_URL` 可覆盖默认值，设为 `off`/`0`/空 则不复位；成功/失败都打印 `[setup] 数据复位 …`。

### 4. 用例级看门狗（防「挂死」比防「失败」更要紧）
Playwright 驱动内部崩溃时，其同步 API 会一直等一个永远不来的响应 ⇒ Python 侧 100% CPU 空转、
**永不退出**（实测卡了 11 分钟，只能手工 kill）。CI 里这意味着一直挂着且没人知道卡在哪。
现在每条用例有硬超时（`HYBRID_CASE_TIMEOUT`，默认 120s）：超时把**所有线程调用栈**写进
`log/<run_id>/watchdog.txt` 再退出。

### 5. 弹层（picker）探测：generate 与 explore 同源 + 有界轮询
- 两个入口共用 `explorer._try_collect_modal_items`（含嵌套 picker 层，探完逐层关掉）。
- 点开一层后不再固定 `sleep(300)`，改为每 200ms 重探、**探到就走**，最坏 2.5s。
- 页面/渲染进程失效（崩溃 / 被 OOM 杀）时明说「环境事故，不是页面没有弹层」，不把环境问题说成业务结论。

### 6. 统一 UTF-8（V7.3 起的铁律，本次沿用）
凡跨进程 / 落盘文本一律显式 UTF-8：`framework/text_io.py` 是唯一入口
（`utf8_env()` / `force_stdio()` / `run_capture()`）；`tests/test_utf8_io.py` 用 `zh_CN.gbk` locale
精确复现过 `'gbk' codec can't decode byte 0xbb in position 13`，并有 AST 全仓扫描拦住「靠系统默认编码」的新写法。

---

## 二、怎么跑（Linux / macOS / Windows 通用）

```bash
cd hybrid_gui_qa
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt && playwright install chromium
python -m demo.app                                     # 终端1：被测应用（8000，含数据 API）

python -m framework.cli all                            # 终端2：probe + generate + run 一条龙
python -m framework.cli run --debug                    # 调试：有屏幕弹浏览器；没屏幕录视频+逐步截图
python -m framework.cli explore --ai --scenario-dir scenarios/ --tag smoke   # AI 场景批量（需 DeepSeek key）
```

自测与验证（后三个需要 demo 在跑）：

```bash
python -m pytest tests/ -q              # 框架自测 86 条
python tests/verify_assert_kinds.py     # 断言 11 种：正向 4 passed + 负向 15/15 FAILED（防假绿）
python tests/verify_cross_page.py       # 跨页四段（含「新建→详情页读同一条记录」）
python tests/verify_picker_layer.py     # 弹层 picker 回归（6 个同名「选择」按行命名 + 探完关窗）
```

---

## 三、已知边界（诚实清单）

- AI 给「返回列表」产的 `url` 断言有时只是 host（两页 URL 都含 ⇒ 等于没验换页）；计划给质量闸加静态检查，
  回到列表页建议改用「列表页独有元素可见」这类断言。
- 场景文件的 `data` 参数化**只解析不展开**（二期做 pytest parametrize）。
- 跨页面流程仍不完整（新建→跳列表→核验 这类链路只能用「点编号进详情」的方式覆盖）。
- 生成物 `scripts/conftest.py` 会 `import framework.data_driven / framework.healer` ⇒
  **需要在项目内运行**（或把 `framework/` 一起带上），不是「拷到哪儿都能独立跑」。
- Chromium 启动参数实测**不降低内存占用**；真正保命的是按可用内存自动降级并发（`framework/limits.py`）。
- `runner.py` 的 ElementMap 场景引擎仍只支持 `expect_text`；主链路的断言在生成的脚本里（已扩展到 11 种）。

---

## 四、目录速览

    framework/   probe · explorer · generator · runner · locator_bridge · healer · limits · text_io · cli
    demo/        被测应用（app.py 静态页 + 数据 API / contracts.html / contract_detail.html / todo.html）
    cases/       自然语言用例（手写 + explore --ai 产出的 ai_*.json）
    scenarios/   AI 场景库（一文件=一场景，YAML）
    scripts/     generate 产物（pytest 脚本 + scripts/datasets 抽离数据）
    tests/       框架自测 + verify_*.py 端到端验证脚本
    docs/        设计与方案文档；training.html 是新员工培训页（build_html.py 生成）

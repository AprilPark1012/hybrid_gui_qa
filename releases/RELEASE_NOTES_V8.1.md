# hybrid_gui_qa V8.1 升级说明（2026-09-22）

> 版本号单一来源：`build_tools/build_html.py` 顶部 `VERSION` / `VERSION_DATE` / `CHANGELOG`
> （`python -m framework.cli --version` 读同一处；**路径只定义在** `framework/tools/common/config.py::VERSION_SOURCE`）。
> 本文件随交付包一起发。
> 上一版：V8.0（`framework/` 按业务流程分层 · **破坏性变更**，升级请先读 V8.0 的「升级须知」）。

## 一句话

给两类「只增不减」的自动产物目录（`log/<run_id>/` 与 `output/verify/`）加**归档保留策略**：
保留**最近 30 个 run ∪ 7 天**；超龄的 run **分级处理** —— 只有**能证明成功**的才整删，
历史与失败**只瘦身**（删 traces 录像，保留日志与报告）。CLI 参数 / 用例格式 / 报告形态**零变化**。

## 一、为什么（先看这条）

`log/` 实测 **281 个目录 / 212 MB，其中 103 MB 是 `traces/*.zip` 录像**（Playwright 可交互回放）。
这些录像正是**排查疑难用例时最想看的证据** —— 于是过去一直"谁都不敢删"，只能看着它涨。

所以本版**不是"加个定时清理"**，而是把「证据价值 vs 空间」这件事做成规则：

| 分类 | 判定依据 | 处理 |
|---|---|---|
| **能证明成功** | `summary.json` 存在，且 `exit_code == 0` 且 `failed_cases == 0` | 超龄后**整目录删**（其 `.log` 只是流水，报告可重跑）|
| **历史（无 `summary.json`）** | 旧版本跑出来的，无法证明成功 | 超龄后**只瘦身**：删录像，留 `.log` + `report.html` |
| **失败 / 超时** | `summary.json` 里 `exit_code != 0` 或 `failed_cases > 0` | 同上，**只瘦身**（失败证据必须留得住）|

⇒ 回收空间的同时，**证据的"摘要"一份都不丢**（`.log` + `report.html` + `summary.json` 永久保留）。

## 二、怎么用

```bash
# 预演（只打印将做什么，不动磁盘）—— 建议第一次先跑这个
python -m framework.cli prune --runs --dry-run

# 实际清理 run / verify（快照也一起清）
python -m framework.cli prune --all

# 只清 run / verify，不动快照
python -m framework.cli prune --runs

# 调参
python -m framework.cli prune --runs --keep-runs 50 --keep-days 14 --max-delete 10

# 快照清理（旧行为，不带 --runs/--all 时行为与 V8.0 完全一致）
python -m framework.cli prune --keep 20 --dry-run
```

环境变量：`HYBRID_KEEP_RUNS`（默认 30）· `HYBRID_KEEP_RUN_DAYS`（默认 **7**）·
`HYBRID_MAX_DELETE_PER_PRUNE`（默认 20）· `HYBRID_MAX_FREE_MB`（默认 100）·
`HYBRID_NO_AUTO_PRUNE=1`（关掉 `run` / `generate` 结束时的自动清理 —— **正在排查现场时用这个**）。

自动清理：`cli run` 与 `cli generate` 结束时各跑一次（静默，无可清理就不打印）。

## 三、保护规则（**优先级高于任何旋钮**）

1. **最近一次全绿 / 全红各保一个** —— 无论数量与天数；
2. **`log/.protected_runs` 登记过的完全不碰**（连录像都不删）—— 台账、发行说明、交付邮件引用过某个 run 时，
   往这里登记一行（`run_id  # 理由`）。框架**只读仓库内文件**，不读 skill / 门禁路径（守 R1）；
3. **不认识的命名一律不动** —— 只处理 `YYYYMMDD_HHMMSS`（含 `slowgate_*`）形态的目录，用户手工放的东西绝不误删；
4. **未超龄的 run 一个文件都不动**（连大录像也不删 —— 新鲜证据必须完整）；
5. **单次删除上限**：20 个目录 / 100 MB —— 防「策略写错、一夜清空」，到顶即停、余量留到下次；
6. **处置失败即停**：任何一步出错就如实报并中止（fail-safe，不 fail-open）。

## 四、新增产物：`summary.json`

`cli run` 收尾时写进本次 run 目录：

```json
{
  "run_id": "20260922_120000",
  "ended": "20260922_121530",
  "exit_code": 0,
  "case_logs": 19,
  "failed_cases": 0,
  "traces_bytes": 6612345,
  "note": "failed_cases 由用例日志里的 ✗ / Traceback 计数；exit_code = pytest 退出码"
}
```

两点设计说明：
- **写在退出码判断之前** ⇒ 失败 run 也会留下 summary.json（否则"最近一次全红"保不住、失败证据也可能被当成成功删掉）；
- **失败数从用例日志里数**（`✗` 是 runner 执行失败时打印的，另有 Python traceback 兜底），
  不去解析 pytest 的文本输出 —— 日志是框架自己的产物、口径稳定，pytest 输出格式会随版本变。
  误判方向是**安全**的：多算失败 ⇒ 更保守（只瘦身）。

## 五、本机实测（真值）

| 项 | 结果 |
|---|---|
| 首次实际执行 | 回收 **66.2 MB**：`log/` **213 MB → 146 MB**（瘦身 34 个 run / 281 个录像文件 · **整删 0** · 清 45 个老 verify 日志）|
| 为什么整删 0 | 当时 `log/` 里全是历史数据（无 `summary.json`，不可证明成功）⇒ 按保守口径一律只瘦身。新跑出来的 run 有 summary.json，随超龄会开始走整删 |
| 证据完整性 | 抽查：被瘦身 run 的 `.log` / `report.html` / `summary.json` 全部在位 |
| 保护清单 | 3 个被设计文档 / 台账引用的 run 登记后**完全不碰**（连录像都不删）|
| 框架自测（一类） | `pytest tests/ -q` ⇒ **292 passed**（含本版新增 14 条，其中 7 条负向自证）|
| 特性验证（二类） | `bash tests/run_verifications.sh` ⇒ 13 个脚本（含新增 `verify_retention_runs.py`）|
| 真 CLI 预演 | `prune --runs --dry-run` 连跑两次 ⇒ 真 `log/` 目录树逐字节一致（dry-run 确实不动）|

> 本版验收过程中二类**抓到一个一类抓不到的真 bug**（`cli run` 写 summary 的 helper 用了 `json` 却没 import
> ⇒ 只有真跑才炸），随后补了一条一类判据把该契约钉住 —— 「自己的狗粮自己吃」在起作用。

## 六、兼容性与注意事项

- ✅ **零破坏**：不带 `--runs/--all` 时 `prune` 行为与 V8.0 一致（只清快照）；`--keep` 语义不变；
  用例格式 / 报告形态 / CLI 既有参数**全部不变**。
- ⚠️ `--keep-days` **默认 7 天**（不是 14）—— 首次执行会动到 7 天前的老录像（日志与报告保留）。
  想更保守就 `--keep-days 30`，或排查期间设 `HYBRID_NO_AUTO_PRUNE=1`。
- ⚠️ 被瘦身的 run**录像找不回来**（这正是策略的目的）；但失败 run 的日志、报告与 `summary.json` 一定还在。
- `log/` 依旧**不进交付包**（打包器自检包含「不含 output/log/.env」）；新增的 `log/.protected_runs` 同样排除。

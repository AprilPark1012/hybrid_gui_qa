# V8.6 发行说明（2026-10-13）

> 上游路径：`releases/RELEASE_NOTES_V8.6.md`（交付时随代码包一并发出）

## 一句话

**收敛成一条链路**：手搓链路（probe 驱动的确定性链路）整条删除，框架只剩**真 AI 链路**；
同时把 `tests/` / `README.md` / `docs/training.html` 与 framework 代码**逐条对齐**，失效内容删除。

## 升级须知（会改变你的用法）

| 项 | 变化 |
|---|---|
| `python -m framework.cli all`（不带 `--ai`） | **原来走手搓链路，现在显式报错 exit 2**。请改用 `all --ai --scenario-file …` |
| `python -m framework.cli probe` | **子命令已删除**（不确定参数时会提示「是不是想写 prune」） |
| `cases/manual/*.json` | **不再支持**（手搓链路的输入）。用例来源只有 AI 产出：`cases/<场景id>/ai_*.json` |
| `scripts/generated/manual/` | 不再产出 |

## 改了什么

### 1. 删除手搓链路（14 处触点 + 3 处产物 + 5 处测试）
- `cli.py`：`cmd_probe` 函数本体（含 docstring）、`cmd_all` 的手搓分支、`main()` 分发、
  `_CMD_FUNCS` 注册表、`CMD_FLAGS['probe']`、浏览器预检名单里的 `probe`、模块 docstring 的
  `cli probe` 示例；以及首轮漏掉的 `rc = cmd_probe(rest)` 一行。
- **不再隐式降级**：`all` 不带 `--ai` 时显式报错 exit 2 —— 静默兜底 = 造假。
  `--ai` 不再是「区分两条链路」的开关，而是唯一入口的必需参数。
- 三处产物**同删**（只删一处会让「用例↔数据集一一对应」判据变红）：
  `cases/manual/…`、`scripts/datasets/manual_…`、`scripts/generated/manual/…`。
- 删测试：`verify_e2e_scenario2_handwritten.py`（整文件）、`test_target_reachability` 2 条、
  `test_browser_preflight` 1 条、`test_cli_flags` 3 条、`test_tunables_exposed_as_flags` 1 条。
- **规格先行**：先改 `feature_spec.py`（特性 1 的 goal 与 1.1 的 class2）再删脚本。

### 2. 修 9 类「与手搓无关」的文档真错
详见 `docs/training.html` 的 V8.6 条目。要点：
- 文档长期称 framework 是 `features/f01..f11` 且「每特性 `api.py` 是唯一入口」——
  实测**无 f01、全仓无 api.py**，真实结构是 `features/f02..f11` + `shared/` + `tools/spec/`；
- 培训页第 2 章 framework 树停在 **V8.0 旧画像**（`tools/{common,probe,explore,generate,run}`）；
- 断言表只列 9 种（代码真值 **13 种**，漏 `wait_text`）、`first_row` 口径写成 `selector`
  （实为 **`row_field`** 列名）；
- `cases/manual` 树列 4 个不存在的文件、`scenarios` 树写不存在的 `contracts/*.yml`、
  `demo/` 树漏 8 个真实文件；
- 两处仍写已删除的 `--mock-fallback`；两处让跑 `pytest tests/_helpers/`（该目录无 `test_*`）；
- README 计数过期（test 121→122、verify 24→23、判据 1124/1→1123/3、子特性 49→50）；
- Windows 激活命令 `.venv\Scriptsctivate` 缺字（应为 `.venv\Scripts\activate`）。

### 3. 判据同步（19 项）+ 新增 10.7
- `test_ai_first_docs.py` 按新口径重写（不再要求「两条链路」、不再要求 `cases/` 是手写）。
- `test_docs_sync.py` 的 `MUST_BE_DOCUMENTED` **长期在找 V8.0 的旧模块名**
  （`explorer.py`/`locator_bridge.py`/`generator.py`…）—— 那些文件按特性重组后已改名，
  判据**长期空转**；现对着 `find framework -name '*.py'` 逐条校准。
- **新增判据 10.7「文档结构真值契约」**：文档登记的特性夹都要真实存在、磁盘上的特性夹都要登记、
  正文区不许声称有 `f01` 或每特性 `api.py`，并**反向自证**「现在确实没有 api.py」。

### 4. 交付包口径
- `output/element_maps/` 的 elementMap **最新 1 份随代码包交付**（它是交付生成物之一）；
- `log/` 与录像都**不进代码包**（录像走「两件套」的录像包）；
- README 补上交付包内容口径，并改掉把 `output/` 笼统写成「运行时证据…可清」的旧表述。

## 验证真值（2026-10-13 本机实测）

| 项 | 结果 |
|---|---|
| 全链 E2E（清环境 + 重启 demo + `all --ai`） | **EXIT=0**，`1 passed in 219.52s` |
| 五类产物 | case / elementMap / script / llm_cassettes / log **全部齐** |
| 全量判据 | `1127 passed / 3 skipped / 0 failed` |
| 版本号单一来源 | `hybrid_gui_qa v8.6 (2026-10-13)` |

## 已知遗留

- `tests/_runner/run_acceptance.py` 里「场景 2」的占位与注释仍按旧口径写着（本次未动，
  它的判据 `test_acceptance_skip_policy.py` 仍绿 —— 手搓删除后这段注释自然成真，下次一并清理）。
- `log/*/traces/*.zip` 实测含明文凭据（`trace.trace` 记 fill 值 + 登录页快照），
  口径仍是「**log 尤其 traces 永不外发**」；「录制前脱敏」能力尚未做。

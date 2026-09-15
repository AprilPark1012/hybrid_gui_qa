# hybrid_gui_qa V7.5.1 交付说明（2026-09-15）

> 一句话：**V7.5 的交付包夹带了坏产物**（包里 `scripts/test_cases.py` 有 100 处「元素未映射」存根），
> 本版把根因修成机制（拿不到定位就不产出产物）并加了**交付前自检**，`scripts/test_cases.py` 已替换为正确产物。

---

## 一、先说清楚 V7.5 的缺陷（不遮）

| 项 | 实情 |
|---|---|
| 现象 | Windows 上跑验收第 3 条 `python tests/verify_slow_target.py` → **5 failed / 1 passed** |
| 真因 | 包内 `scripts/test_cases.py` 是**陈旧坏产物**：50 个 `pytest.fail("元素未映射：…")` 存根（`sha256=10afa0ef18e2`），与 git 提交里那份完全相同；正确产物 `sha256=55d85d50ae43` |
| 为什么会产生 | `generate` 在**现场探测不可用**时只打一句警告就继续落盘、且 **exit 0** ⇒ 产出「16 个用例、每步都是 fail 存根」的假脚本；它被提交、被打包、被交付 |
| 影响面 | 任何**直接用包内 `scripts/test_cases.py`** 跑（`pytest scripts/test_cases.py` / 慢目标闸门）的人都会看到一堆 `元素未映射`；而 `python -m framework.cli all` 会重新 probe+generate，所以**跑 all 的人不受影响**（这也解释了为什么 all 全绿、闸门却红） |
| 为什么交付时没发现 | 打包时没人检查过包内产物；而且那次「检查」还是**假绿**——本机没装 `unzip`，`unzip -p … \| grep -c` 收到**空输入**数成 0 命中，被当成「包是干净的」 |

---

## 二、本版修了什么（G1–G5，全部本机实测 + Windows 复验）

| 编号 | 修复 | 关键点 |
|---|---|---|
| **G1** | **映射质量闸**（根因） | `generate` 算完映射仍有语义名对不上 ⇒ 抛 `UnmappedElementsError`、**一个文件都不写**、CLI **exit 2**，并打印「缺哪些 / 真因（可达性预检结论）/ 下一步」；调试逃生口 `--allow-unmapped` |
| **G2** | **目标可达性预检** | `target_probe.reachability()` 区分「连不上（给出『先起 `python -m demo.app`』）」「有响应但无 `/api/health`（老目标，算活）」「可达」；`cli probe` 预检不过就 exit 2 + 人话，**不再甩一屏 Playwright traceback**；顺手统一 `TARGET_URL` ⇄ `HYBRID_BASE_URL` |
| **G3** | **verify 脚本统一 UTF-8** | `verify_slow_target.py` / `verify_picker_layer.py` 补 `force_stdio()` —— 之前中文 Windows 控制台上中文显示成乱码（`Failed: Ԫ��δӳ��` 就是这个）；加了「`verify_*.py` 一个都不许漏」的源码级判据 |
| **G4** | **交付前自检** | ① `tests/test_artifacts_health.py`：未映射=0 · 无裸 `page.goto` · conftest 接线齐 · cases↔datasets 一一对应 · `scripts/` 无杂物；② `tools/pack_release.py`：打包 + **标准库 `zipfile`** 复扫包内产物，不达标就删包 + exit 2（`--check <zip>` 可审计任何历史包） |
| **G5** | **跨平台 GBK guard** | 旧判据用 POSIX 专有 `locale -a` ⇒ 三条 GBK 精确复现用例在**中文 Windows（事故原发环境）上永远跳过**；现在 Windows 分支读系统 ANSI 代码页（中文系统 = 936），断言放宽成「GBK 家族」 |

**防复发（这才是重点）**：这三道闸门现在都会在**问题产物产生的那一刻**就拦住 ——
生成期（G1）· 打包期（G4）· 仓库产物健康度（G4 的测试，能进 CI）。

---

## 三、自测与验证证据

| 验证 | 结果 |
|---|---|
| `python -m pytest tests/ -q`（本机） | **130 passed** |
| 同一条命令、受限环境（无 `locale` / 无 `git`） | **127 passed + 3 skipped**（skip 的正是三条 GBK 复现，POSIX 上真没 GBK 时跳过是正当的） |
| 负向对照：把坏产物放回 `scripts/` | 健康度闸门**当场变红**（`assert 100 == 0`） |
| 负向对照：用 `pack_release.py --check` 审计 **V7.5 那个包** | **抓出 100 处未映射** + exit 2 |
| 真实 CLI 反证：`TARGET_URL=http://127.0.0.1:9 python -m framework.cli probe` | 一句话人话 + **exit 2**，**无 traceback**、不启动浏览器 |
| AprilPark1012 Windows 实测（2026-09-15 晚） | `cli all --workers 16` **全绿**；生成物刷新后 `verify_slow_target.py` **全绿** ⇒ 证明探测/generate/并发链路在 Windows 上本身没问题，问题只在「包里那份陈旧产物」 |

---

## 四、验收（建议按顺序，共 5 步）

| 步 | 命令 | 期望 |
|---|---|---|
| 0 | 另开一个窗口：`python -m demo.app`（保持不关） | 浏览器打开 `http://localhost:8000` 有合同列表；`/api/health` 返回含 `"partitioned": true` |
| 1 | `python -m pytest tests/ -q` | **130 passed**（V7.5 时的 3 skipped 应消失） |
| 2 | `python -m framework.cli all --workers 16` | **16 passed / exit 0**；留意「并发隔离」那行应显示 `partitioned=true → 保持 16 worker` |
| 3 | `python tests/verify_slow_target.py` | **全绿**（自起 demo:8011 + 代理:8012，不占 8000、不用手工起 demo；控制台**不再乱码**） |
| 4 | 反证 A：停掉 demo 后 `python -m framework.cli probe` | 一句人话 + **exit 2**（不是 traceback） |
| 5 | 反证 B：停掉 demo 后 `python -m framework.cli generate` | **exit 2 且 `scripts/test_cases.py` 不被覆盖**（旧行为：落一份 100 处 fail 的垃圾） |

> 包校验：zip 的 `sha256` 以交付消息里打印的为准（`tools/pack_release.py` 每次打包都会打印）。

---

## 五、已知遗留（如实记档）

1. **F5 未完成**：`cases/cross_page_detail.json` 的「列表恢复全量 20 行」（`count expect=20`）仍是脆弱断言，
   需要目标在跑 + 真浏览器才能改完并验证 ⇒ 排下一版。
2. **CI 落点未做**：`.github/workflows/ci.yml`（起 demo → 自测 → 16 用例 → 三个 verify）还没落；
   注意推 workflow 文件需要 token 带 `workflow` 权限（当前 fine-grained token 只有 `Contents: R/W`）。
3. **不可达退出码 = 2**（与「参数/用法错误」同码）：CI 若要区分环境类失败，后续可拆独立码。

---

## 六、改动文件清单

```
framework/generator.py     映射质量闸（UnmappedElementsError + allow_unmapped + 结果带 unmapped/probe_error）
framework/cli.py           预检接线 · --allow-unmapped（FLAG_SPECS/CMD_FLAGS）· _report_unmapped 人话
framework/target_probe.py  reachability() · probe_partitioned 归因纠偏
framework/config.py        TARGET_URL ⇄ HYBRID_BASE_URL 统一
tests/test_generate_quality_gate.py   新增 4 条（闸门正/负向 + CLI exit 2）
tests/test_target_reachability.py     新增 7 条（可达性三分 + 不启 Playwright 的陷阱）
tests/test_artifacts_health.py        新增 5 条（生成物健康度）
tests/test_pack_release.py            新增 5 条（打包自检的「测试的测试」）
tests/test_utf8_io.py                 GBK guard 跨平台 + verify 脚本 force_stdio 判据
tests/verify_slow_target.py · tests/verify_picker_layer.py   补 force_stdio()
tools/pack_release.py      新增（打包 + zipfile 自检）
scripts/test_cases.py      替换为正确产物（未映射 0 / 32 处 _goto）
build_html.py · training.html        版本号与 CHANGELOG 同步（V7.5.1）
docs/P5-交付修复-V7.5.1-方案.md       方案 + 证据 + 进度
```

# V8.7.8 发布说明（2026-10-27）

> 上一版：V8.7.7（2026-10-27）· 版本号单一来源 = `build_tools/build_html.py:VERSION`

## 一句话

**verify 跑过了，run 还要再跑一遍吗？** —— 你问得对：那条用例确实被跑了两次。
顺手还发现 verify 是**串行**跑的，多场景时它才是真正的瓶颈。

---

## 你的问题与我查到的

**问题**：「verify 跑通过以后，还需要 run 一遍吗？确认下这个逻辑是否合理？」

`all --ai` 的三步：

| 步骤 | 跑哪些用例 | 目的 |
|---|---|---|
| `explore --verify` | **本轮新产出的**（`done`） | 验证 AI 产出合格否；不合格带原因重生成 |
| `generate` | — | 用例 → 脚本（无变化则跳过） |
| `run` | **`scripts/generated` 全量** | 正式报告 + 并发 + 跑其他场景 |

**查证过程中的一次自我纠正**：我一开始怀疑 `explore --verify` 会跑「磁盘上所有历史 AI 用例」
（因为 `_ai_cases_on_disk()` 是扫全部），查下来发现那是 `cli verify` 独立入口用的；
`explore --verify` 用的是 `done`（第 817 行 `done.append(...)`）= **本轮新产出**。这一层逻辑是对的。

**所以重复的确切范围**：

- **多场景**：run 跑全部 N 条，其中**本轮那 1 条重复**，其余 N-1 条是 run 的正当工作
- **单场景**（你现在的情况）：run 跑的就是那 1 条 → **100% 重复**，唯一新增物是 `report.html`

**结论：部分合理，有一处明确浪费。**

---

## A. verify 串行改并发

**问题**：`_verify_cases_detailed` 是

```python
for label, name in entries:
    r = run_capture([... "pytest", node, "-v", "-s" ...])
```

一条一个 pytest 子进程、**串行**等。单条全链路用例 200~400s，
**10 个场景 = 30 分钟以上纯等待** —— 而 run 阶段同一批用例 `-n 16` 只要几分钟。

**改法**：`ThreadPoolExecutor` + `safe_workers()`（**与 run 同一套内存预检**，不另造一份）。

```python
nw = max(1, min(safe_workers(None)[0], len(todo)))
```

**并发粒度仍是「每条一个独立 pytest 进程」**，没用 `pytest -n`：

| | 独立进程（采用） | `pytest -n` |
|---|---|---|
| 日志 | 每条一个 `output/verify/<case>_<ts>.log` | 混在一起，分不清 |
| 超时 | 各自独立，一条卡住只判它失败 | 拖累整批 |
| **失败归因** | 精确到「哪条、哪一步」 | 拆不开 —— 而这正是 AI 重试最需要的 |

细节：打印走锁（`threading.Lock`），否则多行输出会互相插进对方中间；
预检不可用 / 只有 1 条时**干净退回串行**。

---

## B. 新增 `all --skip-verified`

run 用 pytest 的 `--deselect` 精确跳过本轮 verify 已实测通过的用例：

```bash
python -m framework.cli all --ai --verify --skip-verified --scenario-file xxx.yml
```

**默认关闭**，理由：跳过的那条**不会出现在 `report.html` 里** —— 报告不再自证。
证据仍在 `output/verify/` 的校验日志，但报告本身缺了这一条。所以只在明确要「快」时开。

### 两个必须守住的口径

**① 全部跳过时 pytest 返回 5（no tests ran），那不算失败。**

必须与「`--case` 名字写错」严格区分，否则用户一开开关就被判红、开关等于不能用。
`summary.json` 也记 0 —— 否则归档策略会把这次当**失败 run**，可能误删能证明成功的产物。

**② 「本轮已验证」只存进程内（`_VERIFIED_OK`），绝不落盘。**

落盘的话下次跑会读到上一次的记录，把**新用例**当「已验证」跳过 = **假绿**。
进程内的生命周期天然只覆盖「本轮」；用户单独跑 `run --skip-verified` 读到空集，
会**明确提示「无效果」**而不是静默什么都不做（静默会让人以为省了时间，其实没省）。

---

## 顺手堵一个假绿口子

verify 里「`index.json` 取不到脚本」原来是 `continue`：

```python
except Exception as _e:
    print(f"      [!] 取不到 {name} 的脚本路径…")
    continue          # ← 不影响 all_ok，等于「没验过」被当成「验过了」
```

现改为 **判失败**（`ok is None` 时 `all_ok = False`）。
被 verify 的用例如果连脚本都取不到，说明用例/脚本不配套 —— 那本来就不是「通过」。

---

## 判据（新增 15 条）

`tests/特性11-交付即验证/test_verify_concurrent_and_skip.py`

### 旧判据抓到我改坏的地方（如实记录）

并发化时我把 V8.7.6 加的这句提示**顺手删掉了**：

```
提示：这类全链路用例常含「等订单状态流转」的有界等待（最长约 160s），
整体 3~10 分钟属正常；想看实时进度去 log/ 下最新的 run 目录
```

全量回归里 `test_verify_announces_trial_run_step` 立刻变红 ——
这条判据要求的正是「试跑前告诉用户要等多久、进度去哪看」，
而那句话是**用户当初报「卡住了」的直接修复**。删掉等于把那个修复又退回去了。

**已恢复**（并补上 `output/verify/` 也给逐条校验日志）。

另一条 `test_verify_flush_true_on_progress_prints` 红在：打印从 `print(..., flush=True)`
改成了走 `_p()`（内部才 flush）。这条判据**没有弱化**，反而收紧了：

| 改前 | 改后（更严） |
|---|---|
| `[2/2]` 后 1200 字符内 `flush=True` 出现 ≥2 次 | `_p` 定义里必须有 `print(msg, flush=True)` **且** 进度必须走 `_p`、**不许绕过锁直接 print**（并发下会交错成乱码） |

| 组 | 钉住什么 |
|---|---|
| verify 并发 | 必须用 `ThreadPoolExecutor` + `as_completed`（先完成先报，进度可见） |
| 复用口径 | 必须 `from ...limits import safe_workers`，**不许自造一份并发策略** |
| 兜底 | 默认 `nw = 1`；并发数不超用例数；`if nw <= 1:` 串行分支必须在 |
| **不许用 xdist** | verify 里不许出现 `"-n"` —— 多条揉进一个 pytest 就没法归因 |
| 打印锁 | 必须 `threading.Lock()` + `with _out_lock:` |
| **取不到脚本=失败** | 不许退化成 `continue` |
| 独立超时 | 每条仍用 `verify_timeout_s()`，`TimeoutExpired` 单独捕获 |
| **不落盘** | 整份源码里任何含 `_VERIFIED_OK` 的行都不许有 `write_text` / `json.dump` |
| **exit 5 不算失败** | 必须有 `_skip_all`；`not _skip_all` 才 raise；summary 记 0 |
| deselect | 必须 `["--deselect", _node]` + 从 `index.json` 的 `script_path` 拼 node id |
| 无记录要提示 | 必须出现「无效果」字样 |
| **双处登记** | 必须同时在 `FLAG_SPECS`（权威）与 `CMD_FLAGS["all"]`（提示）里 |
| 透传 | `cmd_all` 签名 + `cmd_run(... skip_verified=skip_verified)` + 分发层从 `rest` 读 |

**踩过的坑（值得记）**：只往 `CMD_FLAGS` 里加 `--skip-verified` 是没用的 ——
真正把关的是 `FLAG_SPECS`，漏了会报「不认识的参数：--skip-verified」
并给出**误导性建议**「是不是想写 --no-verify ？」。判据因此钉住「两处都要登记」。

---

## 升级检查清单

**先分清你是哪个阶段** —— 这是比 `--skip-verified` 更实用的一条：

| 阶段 | 命令 | 为什么 |
|---|---|---|
| **开发期**（调 AI 产出、反复跑） | `explore --ai --scenario-file xxx.yml` | 默认就带 verify（`do_verify = "--no-verify" not in rest`），**生成用例 + 生成脚本 + 实跑验证，但不跑 run** —— 省掉整个 run 阶段 |
| **交付期**（要报告） | `all --ai --scenario-file xxx.yml` | 多出 `report.html` + 并发正式执行 |

**开发期跑 `all --ai` 等于每次都走一遍交付流程**，那 200 秒的 run 对调 AI 产出没有任何帮助。

```bash
# 开发期（推荐）
python -m framework.cli explore --ai --scenario-file scenarios/orders/orders_invoice_full_lifecycle.yml

# 交付期
python -m framework.cli all --ai --scenario-file scenarios/orders/orders_invoice_full_lifecycle.yml

# 交付期但想快一点（跳过本轮 verify 已通过的；报告会有缺口）
python -m framework.cli all --ai --verify --skip-verified --scenario-file ...
```

---

## 兼容性

- **默认行为完全不变**：`--skip-verified` 不传就是原来的两遍。
- 新增 `--skip-verified` 参数（`all` 专用）。
- **行为加固**：verify 里取不到脚本从「跳过」改为「判失败」—— 若你的环境存在
  「cases 有、index.json 没有」的历史残留，现在会被判红（这是对的，但要知道）。
- verify 的打印顺序变了（并发下按完成先后报，不再按用例声明顺序）。

---

## 还没解决的

- **verify + run 的双跑**只在 `--skip-verified` 下才省掉；默认仍跑两遍（为了报告自证）。
- 若你愿意接受「报告注明来源」，我可以把它设成默认并加 `--full-run` 反向开关 —— 需要你定。
- **`[SLOW]` 那 150s 的业务等待**（占整条用例 73%）框架侧动不了，得被测系统提供
  「直接置状态」的测试接口 —— 但那同样是测试专用开关，接真实系统用不了。

# V8.7.9 发布说明（2026-10-28）

> 上一版：V8.7.8（2026-10-27）· 版本号单一来源 = `build_tools/build_html.py:VERSION`

## 一句话

**开发期要的是效率，不是报告。** 新增 `all --ai --no-run`：跑到 verify 为止，不跑 run。

---

## 你的定调

> 「现在要解决的是开发期效率低的问题，还没有进入交付期可以不跑 run」

在 V8.7.8 之前，开发期调 AI 产出只能用 `all --ai` —— **每次都把交付期的 run 也跑一遍**：

- 本轮那条已经被 verify 实跑验证过的用例，run 又跑一次（实测 ~200s/次）
- 而 run 的产出（`report.html` + traces）**开发期根本没人看**

---

## 一个被判据当场拦下的错误建议（如实记录）

我第一版给的建议是「开发期改用 `explore --ai`」，并把它写进了 README。

**全量回归立刻红在 `test_j2_no_explore_ai_as_runnable_command`** —— 那条判据钉的是你
**2026-10-11** 定的口径：

> 「两条链路统一成 `python -m framework.cli all`，真 AI 链路用 `--ai` 区分，**不另开命令**」

**判据是对的，我错了。** 我犯的正是这个项目反复强调的毛病：为了省事开第二个入口。

所以最终能力开在 `all` 上（与已有的 `--no-verify` / `--no-cases` 同族），**入口仍然只有一个**。

---

## `--no-run` 留下了什么、省掉什么

| | 内容 |
|---|---|
| **留下** | 用例已生成（`cases/`）、脚本已生成（`scripts/generated/`，verify 内部会 generate 一次）、**已实跑验证过** |
| **省掉** | run 阶段的正式执行（并发 worker + `report.html` + traces） |

「已实跑验证过」这条是有依据的：`explore --ai` **默认就带 verify**
（`do_verify = "--no-verify" not in rest`，`cli.py:572`），不需要显式写 `--verify`。

---

## 必须说清的代价

跑完会**明确打印**：

```
[all] --no-run：跳过 run 阶段 —— 用例/脚本/实测验证都已完成，**本次没有 report.html**（交付期请去掉 --no-run）
[all]   实测记录见 output/verify/ 下的校验日志（每条用例一个）
```

不说这一句，用户会去某个目录里找半天报告。**代价就是没有正式的交付报告**，交付期去掉 `--no-run` 即可。

---

## 用法

```bash
# 开发期（调 AI 产出，反复跑）—— 省掉整个 run 阶段
python -m framework.cli all --ai --no-run --scenario-file scenarios/orders/orders_invoice_full_lifecycle.yml

# 交付期（要 report.html）—— 和以前完全一样
python -m framework.cli all --ai --scenario-file scenarios/orders/orders_invoice_full_lifecycle.yml
```

---

## 判据（新增 6 条）

`tests/特性10-CLI帮助契约/test_all_no_run_switch.py`

| 钉住什么 |
|---|
| `cmd_all` 必须接受 `no_run` 且**默认 False**（不加开关就是原来的三段全跑） |
| `no_run=True` 必须**在调 `cmd_run` 之前 `return`**（不能只是打印后继续跑） |
| 必须**明说本次没有 `report.html`**，并指出实测记录在 `output/verify/` |
| 必须同时登记 `FLAG_SPECS`（权威规格）与 `CMD_FLAGS["all"]`（可用列表） |
| 分发层必须从 `rest` 读 `--no-run` 并传给 `cmd_all` |
| **README 的引导行必须是 `all --ai --no-run`**，且不许出现可照敲的 `framework.cli explore --ai` |

最后那条是与 `test_j2_no_explore_ai_as_runnable_command` 同向的补充钉：**引导行也得守统一入口口径**。

---

## 兼容性

- **默认行为完全不变**：不加 `--no-run` 就是原来的 `explore(--verify) → generate → run`。
- 新增 `--no-run` 参数（`all` 专用）。
- 与 `--skip-verified` 的关系：`--no-run` 更彻底（整个 run 都不跑）；两者可以同时给，
  但那时 `--skip-verified` 没有意义（run 都没了）—— 不会报错，只是没作用。

---

## 还剩的待定项

1. **`--skip-verified` 要不要设默认**：现在默认关（保报告自证），建议保持 —— 它是交付期用的。
2. **多场景并发数实测**：你 Windows 上跑一次多场景，日志会打 `并发试跑 N 条（M 路并行）`，
   把 M 发我看要不要调 `HYBRID_MB_PER_WORKER`（我这边内存太小测不出）。
3. **推 GitHub**：V8.7.5~V8.7.9 累积未提交，等你点头。

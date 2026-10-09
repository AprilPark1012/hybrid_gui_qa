# 框架特性与子特性映射表

> 本文件由 `build_tools/build_feature_map.py` 从 `framework/feature_spec.py` **自动生成**，请勿手改。
> 加特性 / 子特性：改规格文件后重跑生成器。

## 总览

- 大特性 **10** 个 · 子特性 **45** 条
- 一类用例文件 **101** 个 / 用例函数 **807** 条
- 二类验证文件 **21** 个

| 特性 | 名称 | 子特性数 | 一类文件 | 二类文件 |
|---|---|---:|---:|---:|
| 1 | 混合链路 | 3 | 4 | 3 |
| 2 | 语义识别与步骤编排 | 4 | 21 | 4 |
| 3 | 分层定位与控件识别 | 7 | 13 | 5 |
| 4 | 选错控件兜底 | 4 | 4 | 2 |
| 5 | 用例脚本数据三层分离 | 5 | 8 | 0 |
| 6 | 自愈闭环 Healer | 1 | 0 | 0 |
| 7 | 并发与资源安全 | 4 | 3 | 1 |
| 8 | 离线回放 | 4 | 6 | 3 |
| 9 | 质量闸门体系 | 8 | 36 | 4 |
| 10 | CLI 帮助契约 | 5 | 6 | 0 |

## 特性 1 · 混合链路

**目标**：三种链路（AI 生成 / 手搓 / 离线回放）都能跑通，且有一条统一验收入口

**目录**：`tests/特性1-混合链路/`

| 子特性 | 名称 | 目标 | 一类（用例数）| 二类 |
|---|---|---|---|---|
| 1.1 | 三种链路可切换 | AI 生成链路、手搓用例链路、离线回放链路三条路各自可独立跑通 | `test_acceptance_entry.py`(8)、`test_offline_chain_python.py`(9) | `verify_e2e_scenario1_online.py`、`verify_e2e_scenario2_handwritten.py` |
| 1.2 | 统一验收入口 | 四条验收原则能用一条命令跑完；跳过策略（如 --skip-ai）必须显式留痕，不许静默少跑 | `test_acceptance_entry.py`(8)、`test_acceptance_skip_policy.py`(6) | - |
| 1.3 | 交付两件套 | 无外网机器靠「代码包 + LLM 录像包」即可跑 AI 链路 | `test_render_entrypoint.py`(2) | `verify_offline_delivery.py` |

## 特性 2 · 语义识别与步骤编排

**目标**：把「人的自然语言」变成「可执行的步骤序列」—— 面向生成，对人友好也对机器友好

**目录**：`tests/特性2-语义识别与步骤编排/`

| 子特性 | 名称 | 目标 | 一类（用例数）| 二类 |
|---|---|---|---|---|
| 2.1 | 语义名生成与对齐 | AI 产出的语义名能落到真实控件上；宁可不映射（大声告警）也不许错映射（静默点错） | `test_name_alignment.py`(11) | - |
| 2.2 | 自然语言步骤编排 | 场景 yml 的自然语言 → 步骤序列；步骤能直接声明定位方式（by+value）而不依赖探测清单 | `test_step_direct_locator.py`(15)、`test_ai_scenario_preconditions.py`(10)、`test_ai_retry_loop.py`(10)、`test_ai_incomplete_output_retries.py`(3)、`test_ai_retry_same_cause.py`(5)、`test_ai_no_hardcoded_row_values.py`(5)、`test_semantic_mismatch_blocks.py`(3)、`test_llm_tool_choice_unsupported.py`(3)、`test_production_defects_gate_l1.py`(3)、`test_ai_can_express_row_checkbox.py`(14)、`test_required_field_coverage.py`(8)、`test_retry_leaves_no_stale_notes.py`(4)、`test_required_fields_hard_checklist.py`(5)、`test_prompt_list_clipping_is_general.py`(15) | `verify_role_switch_click.py` |
| 2.3 | 步骤到定位的合成 | 步骤里的语义名/属性如何合成可执行定位表达式 | `test_scope_locate_expr.py`(17)、`test_locate_by_title.py`(8) | `verify_scope_locate.py` |
| 2.4 | 场景声明契约 | 人写的那部分：pages / pre / auth / data / probe_url —— 声明必须由场景提供，框架不懂具体系统 | `test_scenario_auth_spec.py`(8)、`test_page_pre_actions.py`(3)、`test_probe_url_and_occurrence.py`(6)、`test_login_priming_coverage.py`(4) | `verify_login_priming.py`、`verify_page_pre_actions.py` |

## 特性 3 · 分层定位与控件识别

**目标**：在生产系统的复杂页面上仍能唯一定位到目标控件 —— 面向执行

**目录**：`tests/特性3-分层定位与控件识别/`

| 子特性 | 名称 | 目标 | 一类（用例数）| 二类 |
|---|---|---|---|---|
| 3.1 | 顶层锚点加容器内下钻 | 真实系统只有顶层元素有 testid；子元素靠「锚点 + 容器内相对语义路径」定位 | `test_element_anchor_path.py`(17)、`test_row_fields_cover_all_columns.py`(5)、`test_row_columns_are_named_items.py`(4) | `verify_scope_locate.py` |
| 3.2 | 多层嵌套容器 | 容器套容器（区域内表格、表单里分组）时路径仍能唯一 | `test_element_anchor_path.py`(17) | - |
| 3.3 | 弹出层与可展开容器 | 藏在 display:none 菜单里、或点开才出现的弹层控件能被探到并用起来 | `test_expandable_menu_discovery.py`(6)、`test_probe_single_entry.py`(13)、`test_probe_page_scope.py`(8)、`test_probe_incremental.py`(7) | `verify_expandable_menu.py`、`verify_probe_path_parity.py` |
| 3.4 | 跨页面元素 | 多页面场景下元素跨页可用；同名元素改 `原名@页名` 消歧 | `test_runtime_name_source_is_explore_snapshot.py`(12) | `verify_cross_page.py` |
| 3.5 | 属性直定位 | 探测清单兜不住时，用属性（by+value）直接定位；select 的 index 语义 = 第 N 个非空选项（跳过 placeholder） | `test_select_by_index.py`(3)、`test_select_without_value.py`(3)、`test_text_assert_prefers_visible.py`(3) | `verify_select_index_skips_placeholder.py` |
| 3.6 `[未实现]` | iframe 内控件 | [!] 未实现（缺口）：iframe 内以及跨 iframe 的控件识别与操作 | - | - |
| 3.7 | 行内单元格定位 | 行锚 + 单元格：列的指定方式（多列 by）与支持的 op（不只 click） | `test_row_cell_col_by.py`(12)、`test_row_cell_ops.py`(5) | - |

## 特性 4 · 选错控件兜底

**目标**：同名/同区域控件不许被选错；选不准就大声失败，绝不静默点到错的

**目录**：`tests/特性4-选错控件兜底/`

| 子特性 | 名称 | 目标 | 一类（用例数）| 二类 |
|---|---|---|---|---|
| 4.1 | 同名歧义闸门 | 同名控件各有唯一名字（后缀消歧）并留痕；用例引用裸名会被质量闸拦下（fail loud） | `test_element_ambiguity_gate.py`(15)、`test_container_narrowing.py`(12) | `verify_element_ambiguity.py` |
| 4.2 | 全页序号定位 | 不锚容器时的整页 nth —— 处理同名按钮分布在不同区域 | `test_page_scope_nth.py`(4) | - |
| 4.3 | 行锚选取 | 从「整行文本」改成「整表内唯一的最短单元格文本」作行锚 | `test_row_anchor_selection.py`(5) | - |
| 4.4 | 行内字段定位信号 | 锚点内表单字段的 target 步不能落到 get_by_text（会选到标签而不是输入框） | - | `verify_row_field_signal.py` |

## 特性 5 · 用例脚本数据三层分离

**目标**：用例（意图）/ 脚本（可执行）/ 数据（多变）三层各司其职，数据变了不用改用例

**目录**：`tests/特性5-用例脚本数据三层分离/`

| 子特性 | 名称 | 目标 | 一类（用例数）| 二类 |
|---|---|---|---|---|
| 5.1 | 三层职责边界 | 同一场景多组数据 -> 产出多条独立用例，报告独立一行、失败可定位 | `test_data_expand.py`(12)、`test_waiting_semantics_maps_to_wait_text.py`(4)、`test_row_column_carried_through.py`(5) | - |
| 5.2 | 数据驱动不静默退化 | 占位符没被替换时必须报错，不许把 `{占位符}` 原样当字面量跑 | `test_data_driven_placeholders.py`(4)、`test_goto_url_parameterization.py`(3) | - |
| 5.3 | 生成物转义安全 | 数据里的换行/引号等特殊字符不能破坏生成的 Python 源码 | `test_generator_escaping.py`(4) | - |
| 5.4 | 增量生成 | 场景变了要重新生成；两个触发源都要认 | `test_generate_incremental.py`(3) | - |
| 5.5 | 可选字段的渲染健壮性 | 步骤缺可选字段（如 select 不给 value）时脚本照样生成，绝不因单个字段缺失崩掉整批 | `test_render_step_without_value.py`(3) | - |

## 特性 6 · 自愈闭环 Healer `[规划中（零判据）]`

**目标**：定位失败时能自动修复并留痕（当前无判据，属规划中）

**目录**：`tests/特性6-自愈闭环Healer/`

| 子特性 | 名称 | 目标 | 一类（用例数）| 二类 |
|---|---|---|---|---|
| 6.1 `[规划中]` | 失败自愈 | [!] 待定：主定位失败时尝试候选并记录自愈过程 | - | - |

## 特性 7 · 并发与资源安全

**目标**：并行跑验证不许把内存打爆；资源闸门不许支配一类自测

**目录**：`tests/特性7-并发与资源安全/`

| 子特性 | 名称 | 目标 | 一类（用例数）| 二类 |
|---|---|---|---|---|
| 7.1 | 二类调度 | 预算 1200s + 并发 + 内存闸的调度策略 | `test_run_verifications_plan.py`(17) | - |
| 7.2 | 内存闸不支配一类 | 一类的红绝不能由二类的资源闸门造成（否则一类红灯失去可信度） | `test_class1_no_mem_gate_coupling.py`(9) | - |
| 7.3 | runner 能起来 | 二类 runner 冒烟；环境不满足时跳过并说明，而不是假红 | `test_runner_smoke.py`(4) | - |
| 7.4 | 慢目标闸门 | 慢机器/高并发目标下用例依然全绿（下行区就绪信号） | - | `verify_slow_target.py` |

## 特性 8 · 离线回放

**目标**：没有外网的机器也能跑 AI 链路 —— 靠 LLM 录像

**目录**：`tests/特性8-离线回放/`

| 子特性 | 名称 | 目标 | 一类（用例数）| 二类 |
|---|---|---|---|---|
| 8.1 | 录像键两级策略 | 严格级（逐字一致）+ 宽松级的匹配分工 | `test_cassette_strict_policy.py`(3)、`test_cassette_key_stability.py`(9)、`test_cassette_fuzzy_fallback.py`(9) | - |
| 8.2 | 录像体检 | 场景段抠取 + 覆盖判定；缺录像要能报出来 | `test_check_cassettes_block.py`(6) | - |
| 8.3 | 录制与回放契约 | 录像能录、能放、放得对（不联网、不要 key） | `test_llm_cassette.py`(30) | `verify_e2e_scenario3_cassette.py`、`verify_e2e_scenario3_replay.py` |
| 8.4 | LLM 抖动重试 | LLM 偶发失败要退避重试，不许把抖动当失败 | `test_llm_retry.py`(3) | `verify_offline_chain_deps.py` |

## 特性 9 · 质量闸门体系

**目标**：框架自己守自己：布局/命名/环境/交付/就绪/安全六类契约，坏了就红

**目录**：`tests/特性9-质量闸门体系/`

| 子特性 | 名称 | 目标 | 一类（用例数）| 二类 |
|---|---|---|---|---|
| 9.1 | 布局与命名契约 | tests/ 与生成物的布局、路径拼接（跨平台）、命名空间契约 | `test_test_layout_contract.py`(13)、`test_generated_layout_contract.py`(5)、`test_path_join_contract.py`(2)、`test_case_scenario_contract.py`(6)、`test_click_then_ready_contract.py`(7)、`test_assert_kinds_render.py`(11)、`test_wait_text_kind.py`(6)、`test_demo_testid_policy.py`(12) | - |
| 9.2 | 质量闸 | 用例质量 / 生成质量 / demo 新鲜度 / AI 用例与场景同步，**且不许误伤** | `test_case_quality_gate.py`(13)、`test_generate_quality_gate.py`(5)、`test_demo_freshness_gate.py`(35)、`test_ai_case_scenario_sync.py`(2)、`test_daily_skip_marker.py`(4)、`test_no_false_positive_blocks_ai.py`(9) | `verify_demo_freshness.py` |
| 9.3 | 环境与编码适配 | 跨平台路径/内存探测/UTF-8 与 cp936 —— 源码不许出现 GBK 编不了的字符 | `test_env_adaptation.py`(18)、`test_utf8_io.py`(21)、`test_browser_preflight.py`(5)、`test_no_stale_paths.py`(9) | - |
| 9.4 | 交付包与文档同步 | 打包内容完整（含运行期必需文件）、文档与代码一致、只留一份 README | `test_pack_release.py`(19)、`test_pack_release_requires_generated_dir.py`(1)、`test_readme_structure.py`(16)、`test_docs_sync.py`(10)、`test_build_html_hl.py`(9) | `verify_html_sync.py` |
| 9.5 | 保留与产物健康 | 日志/产物保留策略与健康检查 | `test_retention_runs.py`(14)、`test_artifacts_health.py`(9) | `verify_retention_runs.py` |
| 9.6 | 就绪与等待契约 | 点击后等就绪、等文本刷新策略、选择器生效 | `test_ready_and_locate.py`(12)、`test_wait_text_refresh_policy.py`(3)、`test_wait_text_selector.py`(2)、`test_import_targets.py`(4)、`test_generated_pytest_discovery.py`(1)、`test_case_imports_cover_helpers.py`(1)、`test_scenario_case_script_hygiene.py`(5)、`test_target_reachability.py`(7) | `verify_wait_text.py` |
| 9.7 | 替换安全与闸门解耦 | 用例替换不许破坏结构；闸门自身不许互相耦合 | `test_case_replacement_safety.py`(6)、`test_no_gate_coupling.py`(2) | - |
| 9.8 | 特性规格契约 | 特性/子特性/用例归属的规格（feature_spec）与磁盘**双向一致**：规格里列的文件必须存在、磁盘上的用例必须有归属、编号规范、目录不漂移、文档与规格同步 | `test_feature_spec_contract.py`(8) | - |

## 特性 10 · CLI 帮助契约

**目标**：命令行对新手友好：帮助自动覆盖、参数错必报错、退出码能区分好坏

**目录**：`tests/特性10-CLI帮助契约/`

| 子特性 | 名称 | 目标 | 一类（用例数）| 二类 |
|---|---|---|---|---|
| 10.1 | 退出码契约 | 成功 0 / 有用例失败 1 / 没匹配到 5 / 环境问题其它 —— 绝不静默成功 | `test_cli_exit_codes.py`(8) | - |
| 10.2 | 参数契约 | 未知/错位参数一律报错 + 非 0 退出，绝不静默忽略 | `test_cli_flags.py`(10) | - |
| 10.3 | 帮助自动覆盖 | 新增子命令/参数必须自动出现在 --help 总览里 | `test_cli_help_coverage.py`(8) | - |
| 10.4 | setup 与分发采纳 | `setup --check` 退出码能区分环境好坏 | `test_cli_setup.py`(10) | - |
| 10.5 | 推荐路径口径 | 文档/提示/培训页的主推路径 = AI 链路；手搓用例降级为调试与回归辅助（历史版本记录不改） | `test_ai_first_docs.py`(6)、`test_tunables_exposed_as_flags.py`(6) | - |


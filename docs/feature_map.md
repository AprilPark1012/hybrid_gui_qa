# 框架特性与子特性映射表

> 本文件由 `build_tools/build_feature_map.py` 从 `framework/features/f09_gate/feature_spec.py` **自动生成**，请勿手改。
> 加特性 / 子特性：改规格文件后重跑生成器。

## 总览

- 大特性 **11** 个 · 子特性 **65** 条
- 一类用例文件 **169** 个 / 用例函数 **1466** 条
- 二类验证文件 **25** 个

| 特性 | 名称 | 子特性数 | 一类文件 | 二类文件 |
|---|---|---:|---:|---:|
| 1 | AI 链路与离线回放 | 4 | 5 | 2 |
| 2 | 语义识别与步骤编排 | 5 | 43 | 5 |
| 3 | 分层定位与控件识别 | 13 | 33 | 6 |
| 4 | 选错控件兜底 | 4 | 4 | 2 |
| 5 | 用例脚本数据三层分离 | 5 | 8 | 0 |
| 6 | 自愈闭环 Healer | 2 | 1 | 0 |
| 7 | 并发与资源安全 | 4 | 3 | 1 |
| 8 | 离线回放 | 5 | 8 | 3 |
| 9 | 质量闸门体系 | 8 | 43 | 6 |
| 10 | CLI 帮助契约 | 10 | 15 | 0 |
| 11 | 交付即验证 | 5 | 6 | 0 |

## 特性 1 · AI 链路与离线回放

**目标**：只剩真 AI 链路（all --ai）与离线回放两种运行形态：都能跑通，且有一条统一验收入口

**目录**：`tests/特性1-混合链路/`

| 子特性 | 名称 | 目标 | 一类（用例数）| 二类 |
|---|---|---|---|---|
| 1.1 | AI 链路与离线回放 | 真 AI 链路（all --ai）与离线回放（录像）各自可独立跑通（不含已删除的手搓链路） | `test_acceptance_entry.py`(10)、`test_offline_chain_python.py`(9) | `verify_e2e_scenario1_online.py` |
| 1.2 | 统一验收入口 | 四条验收原则能用一条命令跑完（run_acceptance）。[!] 跳过策略（如 --skip-ai 必须显式留痕、SKIP != 通过）的判据物理住在 tests/特性9-质量闸门体系/，按「登记目录 == 物理目录」登记在 9.2 | `test_acceptance_entry.py`(10) | - |
| 1.3 | 单包即离线可跑 | 无外网机器解压交付包即可离线跑通 AI 链路（录像随代码包一起发，只有一个 zip） | `test_render_entrypoint.py`(2) | `verify_offline_delivery.py` |
| 1.4 | 目标地址覆盖对全链路生效 | `HYBRID_BASE_URL` 必须同时作用于**业务步骤、登录流、场景身份前置**三条导航路径（改写走唯一入口 `_rewrite_base`）；否则同一个包在用户内网/慢代理上会「一半打新地址、一半打写死地址」—— 会话 cookie 互不通用，第一个业务步就等不到元素。**跨 origin（V8.10.0）**：合同/订单/发票是不同业务系统时，只有**声明过的** origin 才按 `HYBRID_ORIGIN_MAP` 换，其余原样（不许压平）；会话由 `_spread_session` 铺到各 origin | `test_base_url_override_login.py`(8)、`test_cross_origin.py`(11) | - |

## 特性 2 · 语义识别与步骤编排

**目标**：把「人的自然语言」变成「可执行的步骤序列」—— 面向生成，对人友好也对机器友好

**目录**：`tests/特性2-语义识别与步骤编排/`

| 子特性 | 名称 | 目标 | 一类（用例数）| 二类 |
|---|---|---|---|---|
| 2.1 | 语义名生成与对齐 | AI 产出的语义名能落到真实控件上；宁可不映射（大声告警）也不许错映射（静默点错） | `test_name_alignment.py`(11) | - |
| 2.2 | 自然语言步骤编排 | 场景 yml 的自然语言 → 步骤序列；步骤能直接声明定位方式（by+value）而不依赖探测清单；**AI 产出的有界重试口径**也归这里（产出侧被闸门拦下 -> 带原因重生成、上一轮缺陷记账不许留给下一轮；实跑档失败 -> 带原因整轮重来）—— 原登记在特性11，V8.6.3 按「登记目录 == 物理目录」改挂此处 | `test_step_direct_locator.py`(15)、`test_ai_scenario_preconditions.py`(10)、`test_prompt_no_demo_literals.py`(2)、`test_ai_no_hardcoded_row_values.py`(5)、`test_semantic_mismatch_blocks.py`(3)、`test_llm_tool_choice_unsupported.py`(4)、`test_ai_can_express_row_checkbox.py`(14)、`test_required_field_coverage.py`(8)、`test_required_fields_hard_checklist.py`(5)、`test_prompt_list_clipping_is_general.py`(15)、`test_prompt_dom_facts_merged.py`(11)、`test_prompt_wait_page_rule_compact.py`(6)、`test_production_defects_gate_l1.py`(3)、`test_ai_incomplete_output_retries.py`(3)、`test_retry_feedback_contract.py`(13)、`test_ai_retry_contract.py`(11)、`test_ai_retry_same_cause.py`(5)、`test_no_dual_step_field_names.py`(8)、`test_llm_null_and_timeout.py`(15)、`test_llm_doctor_vendor_and_bigprobe.py`(11)、`test_step_timing_and_reset_default.py`(12)、`test_got_none_diagnosis_honesty.py`(4)、`test_content_channel_fallback.py`(5)、`test_content_fallback_unit.py`(5)、`test_row_column_precheck_warns_only.py`(5)、`test_first_row_column_header_fallback.py`(7)、`test_row_fields_cross_page_coverage.py`(6)、`test_row_fields_reach_ai.py`(11)、`test_prompt_points_to_cell_field.py`(5)、`test_row_column_page_scoped.py`(13)、`test_login_goto_never_uses_element.py`(5)、`test_login_no_nested_playwright.py`(10)、`test_modal_probe_never_navigates.py`(6) | `verify_role_switch_click.py` |
| 2.3 | 步骤到定位的合成 | 步骤里的语义名/属性如何合成可执行定位表达式（`verify_scope_locate.py` 物理住在 tests/特性3-分层定位与控件识别/，按「登记目录 == 物理目录」只挂 3.1） | `test_scope_locate_expr.py`(17)、`test_locate_by_title.py`(8) | - |
| 2.4 | 场景声明契约 | 人写的那部分：pages / pre / auth / data / probe_url —— 声明必须由场景提供，框架不懂具体系统 | `test_login_stepwise_contract.py`(8)、`test_scenario_auth_spec.py`(8)、`test_page_pre_actions.py`(3)、`test_probe_pre_consistency.py`(10)、`test_probe_url_and_occurrence.py`(6)、`test_login_priming_coverage.py`(4) | `verify_login_priming.py`、`test_page_pre_actions_force_fallback.py`、`test_scenario_probe_pre.py`、`verify_page_pre_actions.py` |
| 2.5 | 断言步骤可用性对齐 | **AI 能写的断言，框架都必须真的执行**：`ASSERT_OPS` 三个动作在登录链路与业务链路**走同一个执行入口**（`_exec_assert`），登录段不许再把断言丢掉；行断言失败时必须给出**该页实际列**（只说「没有这一列」等于让人重新猜） | `test_assert_step_availability.py`(14) | - |

## 特性 3 · 分层定位与控件识别

**目标**：在生产系统的复杂页面上仍能唯一定位到目标控件 —— 面向执行

**目录**：`tests/特性3-分层定位与控件识别/`

| 子特性 | 名称 | 目标 | 一类（用例数）| 二类 |
|---|---|---|---|---|
| 3.1 | 顶层锚点加容器内下钻 | 真实系统只有顶层元素有 testid；子元素靠「锚点 + 容器内相对语义路径」定位 | `test_element_anchor_path.py`(17)、`test_row_fields_cover_all_columns.py`(5)、`test_row_columns_are_named_items.py`(5)、`test_row_container_singleton_hint.py`(5)、`test_row_container_noise_budget.py`(7)、`test_collision_report_noise_budget.py`(6)、`test_div_grid_row_fields.py`(10)、`test_grid_attr_inference.py`(14)、`test_row_id_locator.py`(13) | `verify_scope_locate.py` |
| 3.2 | 多层嵌套容器 | 容器套容器（区域内表格、表单里分组）时路径仍能唯一 | `test_element_anchor_path.py`(17) | - |
| 3.3 | 弹出层与可展开容器 | 藏在 display:none 菜单里、点开才出现的弹层控件、以及**只在编辑态/动态新增之后才存在**的控件都能被探到并用起来（框架开的必须由框架关）；探到的「藏在哪个入口后面」必须**告诉 AI**（`requires_open` + 规则 1c），否则生成的用例会直接点未展开的弹层控件 -> `element is not visible` 超时 | `test_expandable_menu_discovery.py`(6)、`test_probe_single_entry.py`(15)、`test_probe_page_scope.py`(8)、`test_probe_incremental.py`(7)、`test_editable_state_probe.py`(12)、`test_requires_open_hint.py`(22) | `verify_expandable_menu.py`、`verify_probe_path_parity.py`、`verify_editable_state_probe.py` |
| 3.4 | 跨页面元素 | 多页面场景下元素跨页可用；同名元素改 `原名@页名` 消歧；explore 期喂给 AI 的**完整清单**必须落盘，作为映射表与运行时快照的**唯一名字来源** | `test_runtime_name_source_is_explore_snapshot.py`(12)、`test_elementmap_list_contract.py`(9)、`test_explore_manifest_authoritative.py`(13)、`test_page_identity_contract.py`(9) | `verify_cross_page.py` |
| 3.5 | 属性直定位 | 探测清单兜不住时，用属性（by+value）直接定位；select 的 index 语义 = 第 N 个非空选项（跳过 placeholder） | `test_select_by_index.py`(3)、`test_select_without_value.py`(3)、`test_text_assert_prefers_visible.py`(3) | `verify_select_index_skips_placeholder.py` |
| 3.6 `[未实现]` | iframe 内控件 | [!] 未实现（缺口）：iframe 内以及跨 iframe 的控件识别与操作 | - | - |
| 3.7 | 行内单元格定位 | 行锚 + 单元格：列的指定方式（多列 by）与支持的 op（不只 click） | `test_row_cell_col_by.py`(12)、`test_row_cell_ops.py`(10) | - |
| 3.8 | 重复控件信号与行定位闸门 | 同一容器内重复出现的控件（表格每行一个）收敛成一条并标 `multi_match`，AI 据此给行定位（`row_index`）；生成期拦下「引用重复控件却没给行定位」的步骤。**框架确定性兜底（V8.4.6）**：模型不写也不阻塞 —— 能由用例结构判死的（刚新增行 -> `row_index=-1`）由 `apply_row_locator_fallback()` 补上（只认精确键、宁漏不误伤、出现行锚后不再兜底），判不出来的照旧报红；字段口径只有一处（`ROW_LOCATOR_FIELDS` + `has_row_locator()`）**行内定位走多命中（V8.4.6）**：`_act_row` 不再先走要求语义唯一的 `_loc()`（行内同名列控件必然多个 -> 会被判死），改走探测期录下的「锚点 + 容器内相对语义」（`scope_locate`）拿多命中 locator 再 `.nth(行号)`；行内 `select` 未给 value 时与非行内**同口径**（选第一个真选项、留痕、无选项才报错） | `test_multi_match_signal.py`(18)、`test_row_locate_uses_scope.py`(4)、`test_row_index_lands_in_case.py`(5)、`test_elementmap_readers_accept_list_form.py`(3) | - |
| 3.9 | 元素自身 id 定位档 | 元素**自身**带稳定 `id` 时，给定位链多一档：`test_id` > `element_id` > 锚点下钻 > `role+name` ——有些控件的祖先链里**没有任何可锚容器**（容器是裸 `<div>`），若它又与别的控件同名，`role+name` **必然歧义**；此时 `id` 是唯一可用的稳定身份（实测：订单详情页底部那个「保存」与行工具栏「保存」撞名，而它自身 id 唯一 -> 靠这一档定住）。口径：采集进条目 -> 进运行时快照白名单 -> 定位链一档；**不进 AI 提示词、也不进录像结构键**（省 token 且不让录像失效）；改回任何一环都会被判据抓住（含「白名单静默丢弃」这个最隐蔽的坑） | `test_element_id_is_captured_and_used.py`(7) | - |
| 3.10 | 可点击性补探 | 默认选择器看不见、但实测能点的元素（裸 div onclick / 无 href 的 a / canvas / img 等）也要进清单 —— 显式事件处理器直接采信，纯样式信号（cursor:pointer / tabindex / contenteditable）需两条互相印证；宁可漏补也不制造假控件（噪音 = 没提示） | `test_clickable_probe_signals.py`(11) | - |
| 3.11 | 视觉 grounding 兜底 | 确定性定位（语义 + a11y + 可点击性补探）都失败时，用截图向多模态模型要 0-1000 归一化坐标 -> 按截图实际尺寸换算像素 -> 点击 -> **校验有没有生效**（签名没变就报 no-effect，绝不报成功）；空回复做一次收紧重试（国产模型思考模式会吃光 token 预算）；失败只报原因不抛；不是主路径，只在兜底时调用。真机实测：同一页 4 个同名按钮中定位指定那一行，偏差 8.5 px、命中；定位单按钮偏差 0.8 px | `test_visual_grounding.py`(18) | - |
| 3.12 | 行区信号 row_zone | 「探测时唯一」不等于「运行时唯一」：只要该容器里有『新增行』这类行增删动作，这个区**必然会长多行**（与当前行数无关）。探针据此给区内**当前唯一的输入类**控件标 `row_zone`，① 提示词专门一段要求「排在新增行之后必须给 row_index」② 框架兜底在「前文确有新增行 + 无行锚」时补 `row_index=-1`。口径三条：只标输入类（按钮随行增长也不会变成第几行的保存＝误伤）、只标当前唯一的（multi_match>1 已有更强信号）、不动 multi_match（写它会让质量闸在单行场景误拦）。跨页同名控件不给纯基名（会补错页）。来历：真 AI 链路开票页探测 1 行、用例自己点新增行 -> 运行期 2 个同名匹配 -> 第 1 轮 424.9s 白跑，靠带原因重试才通 | `test_row_zone_signal.py`(18) | - |
| 3.13 | 意图复验阈值单一口径 | `INTENT_MIN_SIM` 只能有**一个来源**：判定处必须引用常量，不许再写字面量（否则「改常量只生效一半」，部分生效最难查）；**改常量必须真的改变行为**（行为判据，不是只 assert 字符串） | `test_intent_threshold_single_source.py`(4) | - |

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

## 特性 6 · 自愈闭环 Healer

**目标**：定位失败时按**放宽阈值**重定位并留痕；real_bug 时**绝不返回 locator**（自愈不许掩盖真 bug）

**目录**：`tests/特性6-自愈闭环Healer/`

| 子特性 | 名称 | 目标 | 一类（用例数）| 二类 |
|---|---|---|---|---|
| 6.1 | 失败自愈（A 级） | 放宽阈值（阈值×0.75 / MINGAP×0.6）再定位一次；无用元素（goto/expect_text/无 element）直接早退且**不记事件**；B 级 LLM 重猜是**未实现的骨架**且必须如实说明（不许误导去配 key） | `test_healer_behavior.py`(5) | - |
| 6.2 | 三态裁决与可审 diff | recovered / real_bug / failed 各自判对；业务断言不通过或抛异常一律 real_bug 且 **locator 置空**；heals json+md 留下「原语义 -> 新 locator -> 置信度 -> 结果」 | `test_healer_behavior.py`(5) | - |

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
| 8.1 | 录像键两级策略 | 严格级（逐字一致）+ 宽松级的匹配分工 | `test_cassette_strict_policy.py`(3)、`test_cassette_key_stability.py`(9)、`test_cassette_fuzzy_fallback.py`(9)、`test_cassette_picks_latest_on_struct_tie.py`(4) | - |
| 8.2 | 录像体检 | 场景段抠取 + 覆盖判定；缺录像要能报出来 | `test_check_cassettes_block.py`(6) | - |
| 8.3 | 录制与回放契约 | 录像能录、能放、放得对（不联网、不要 key） | `test_llm_cassette.py`(30) | `verify_e2e_scenario3_cassette.py`、`verify_e2e_scenario3_replay.py` |
| 8.4 | LLM 抖动重试 | LLM 偶发失败要退避重试，不许把抖动当失败 | `test_llm_retry.py`(3) | `verify_offline_chain_deps.py` |
| 8.5 | 回放的重试轮推进 | 回放遇到「产出校验不合格 / 实跑失败」不许直接放弃：下一轮 prompt 因带失败原因而不同，录像录了那一轮就继续推进；缺那一轮则 fail loud 报缺（exit 2 + 明话），绝不静默降级、也绝不抛未捕获 traceback | `test_replay_allows_retry_rounds.py`(3) | - |

## 特性 9 · 质量闸门体系

**目标**：框架自己守自己：布局/命名/环境/交付/就绪/安全六类契约，坏了就红

**目录**：`tests/特性9-质量闸门体系/`

| 子特性 | 名称 | 目标 | 一类（用例数）| 二类 |
|---|---|---|---|---|
| 9.1 | 布局与命名契约 | tests/ 与生成物的布局、路径拼接（跨平台）、命名空间契约 | `test_test_layout_contract.py`(13)、`test_generated_layout_contract.py`(7)、`test_path_join_contract.py`(2)、`test_click_then_ready_contract.py`(8)、`test_assert_kinds_render.py`(11)、`test_demo_testid_policy.py`(12) | - |
| 9.2 | 质量闸 | 用例质量 / 生成质量 / demo 新鲜度，**且不许误伤**；**闸门统一契约 + 全量注册表**（B′：实现跟特性走、登记进 core/gates.py）；**验收入口的跳过策略**同归此（跳过必须显式留痕、SKIP != 通过、失败优先于跳过 —— `test_acceptance_skip_policy.py` 物理住本目录） | `test_case_evidence_gate.py`(13)、`test_generate_quality_gate.py`(5)、`test_gate_protocol_registry.py`(8)、`test_assertion_echo_gate.py`(6)、`test_demo_freshness_gate.py`(35)、`test_daily_skip_marker.py`(4)、`test_acceptance_skip_policy.py`(6)、`test_no_false_positive_blocks_ai.py`(12) | `verify_demo_freshness.py` |
| 9.3 | 环境与编码适配 | 跨平台路径/内存探测/UTF-8 与 cp936 —— 源码不许出现 GBK 编不了的字符；**源码不许有未绑定名**（拷代码漏作用域会被 except 兜成静默降级） | `test_env_adaptation.py`(18)、`test_utf8_io.py`(21)、`test_browser_preflight.py`(4)、`test_venv_python_single_entry.py`(8)、`test_repo_relative_paths_use_forward_slash.py`(5)、`test_no_stale_paths.py`(9)、`test_no_undefined_names.py`(3) | `verify_undefined_names.py` |
| 9.4 | 交付包与文档同步 | 打包内容完整（含运行期必需文件）、文档与代码一致、只留一份 README；`HYBRID_ROW_ZONE_STRICT=1` 时行区控件缺行定位的产物**拒绝出包**（A' 严格体检） | `test_pack_release.py`(23)、`test_pack_release_requires_generated_dir.py`(1)、`test_row_zone_pack_strict.py`(6)、`test_pack_dotenv_never_shipped.py`(5)、`test_readme_structure.py`(16)、`test_docs_sync.py`(16)、`test_build_html_hl.py`(12)、`test_architecture_doc_contract.py`(4) | `verify_html_sync.py` |
| 9.5 | 保留与产物健康 | 日志/产物保留策略与健康检查 | `test_retention_runs.py`(14)、`test_artifacts_health.py`(9) | `verify_retention_runs.py` |
| 9.6 | 就绪与等待契约 | 点击后等就绪、等文本刷新策略、选择器生效、**等待式断言 `wait_text` 的渲染契约**（三合一后整条归此）、**动作后置校验（做了 != 生效了）**、**`cases` <-> `scenarios` 三目录新陈代谢**：孤儿 AI 用例 / `source_scenario` 可解析 / 场景指纹同步 / 防空转哨兵（V8.6.4 第二批 · 组 2 把原 9.1 `test_case_scenario_contract.py` 与 9.2 `test_ai_case_scenario_sync.py` 两条同源判据**整文件删**、迁进 `test_scenario_case_script_hygiene.py` —— 三者同源，只留一处口径） | `test_ready_and_locate.py`(12)、`test_wait_text_render_contract.py`(11)、`test_import_targets.py`(4)、`test_generated_pytest_discovery.py`(1)、`test_case_imports_cover_helpers.py`(1)、`test_scenario_case_script_hygiene.py`(9)、`test_target_reachability.py`(5)、`test_declared_wait_budget.py`(24)、`test_action_effect_check.py`(12) | `verify_wait_text.py`、`verify_action_effect_check.py` |
| 9.7 | 替换安全与闸门解耦 | 用例替换不许破坏结构；闸门自身不许互相耦合 | `test_case_replacement_safety.py`(6)、`test_no_gate_coupling.py`(2) | - |
| 9.8 | 特性规格契约 | 特性/子特性/用例归属的规格（feature_spec）与磁盘**双向一致**：规格里列的文件必须存在、磁盘上的用例必须有归属、编号规范、目录不漂移、文档与规格同步 | `test_feature_spec_contract.py`(10) | - |

## 特性 10 · CLI 帮助契约

**目标**：命令行对新手友好：帮助自动覆盖、参数错必报错、退出码能区分好坏

**目录**：`tests/特性10-CLI帮助契约/`

| 子特性 | 名称 | 目标 | 一类（用例数）| 二类 |
|---|---|---|---|---|
| 10.1 | 退出码契约 | 成功 0 / 有用例失败 1 / 没匹配到 5 / 环境问题其它 —— 绝不静默成功 | `test_cli_exit_codes.py`(8) | - |
| 10.2 | 参数契约 | 未知/错位参数一律报错 + 非 0 退出，绝不静默忽略 | `test_cli_flags.py`(11)、`test_debug_two_state.py`(5) | - |
| 10.3 | 帮助自动覆盖 | 新增子命令/参数必须自动出现在 --help 总览里 | `test_cli_help_coverage.py`(11) | - |
| 10.4 | setup 与分发采纳 | `setup --check` 退出码能区分环境好坏 | `test_cli_setup.py`(10) | - |
| 10.5 | 推荐路径口径 | 文档/提示/培训页的主推路径 = 真 AI 链路（V8.6 起是唯一链路）；不许把手搓链路写成可用入口（历史版本记录不改） | `test_ai_first_docs.py`(6)、`test_tunables_exposed_as_flags.py`(6) | - |
| 10.6 | 文档真值契约 | 文档说的必须和代码做的是同一回事：引用的路径存在、主线命令统一 all --ai、配置表不虚报条数、关键数字对齐代码真值 | `test_docs_truth_contract.py`(7)、`test_all_no_run_switch.py`(7)、`test_no_hardcoded_case_id.py`(2) | - |
| 10.7 | 文档结构真值契约 | 培训页/README 画的目录结构必须与磁盘一致：登记的特性夹都要真实存在、磁盘上的特性夹都要登记、不许声称有 f01 或每特性 api.py | `test_docs_structure_truth.py`(4) | - |
| 10.8 | 通用 LLM 入口 | 一个开关接所有 OpenAI 兼容服务（GLM / Kimi / 通义 / 豆包 / 本地 vLLM）—— 必须走 function calling、优先级最高、可被 cli config 发现、密钥不外泄 | `test_llm_provider_switch.py`(8) | - |
| 10.9 | LLM 体检 + 思考档位 | 换模型前先体检：`cli llm-doctor` 真发 2 次请求，报「连通 / function calling 通不通 / 端点在用哪档思考」，并区分「不可用」与「能用但打折（thinking 模式拒 tool_choice）」。配套 `LLM_REASONING_EFFORT` 旋钮压思考强度；旋钮必须真进请求体（断言产出而非调用）、不污染默认、可发现 | `test_llm_doctor.py`(13)、`test_reasoning_effort_advice_consistency.py`(2) | - |
| 10.10 | 思考模式端点兼容 | 思考模式端点拒「指名函数」tool_choice 时**有界降级**为 auto：只认特征明确的错（别的照抛）、只重试一次并记住端点特性、降级真发 auto 且不丢 reasoning_effort、留痕不静默；拿不到 tool_calls 如实抛错不许假装成功 | `test_llm_tool_choice_fallback.py`(10) | - |

## 特性 11 · 交付即验证

**目标**：两档验证：① 产出物被闸门拦下 -> 带具体原因让 AI 重生成；② 生成脚本后真跑一次 -> 失败带原因整轮重来。两档都有界（HYBRID_AI_RETRY 默认 2 / 上界 5）、回放同样可带失败原因推进重试轮（缺录像 exit 2 报缺）、退出码可区分（2 产出侧 / 3 实跑侧）

**目录**：`tests/特性11-交付即验证/`

| 子特性 | 名称 | 目标 | 一类（用例数）| 二类 |
|---|---|---|---|---|
| 11.1 | 验证入口契约（两档重试口径） | `cli verify` 独立入口的契约（能单独重跑，不必再走一遍 explore）；两档重试的能力口径：① 产出物被质量闸拦下（写死行数据 / 严重误选 / 必填未编排 / 行定位缺失）-> 带原因重生成；② 生成脚本后真跑一次 -> 失败带原因整轮重来。两档都有界（HYBRID_AI_RETRY 默认 2 / 上界 5）、回放同样可带失败原因推进重试轮、退出码可区分（2 产出侧 / 3 实跑侧）。[!] V8.6.3：本特性**只挂物理住在本目录的判据**；两档重试的其余判据物理住在 tests/特性2-语义识别与步骤编排/（登记在 2.2），按「登记目录 == 物理目录」不在此重复挂。[!] V8.6.4：原 `test_retry_is_bounded`（被特性2 严格覆盖）、原只查「全文 >= 1 次」的 `test_replay_mode_does_not_retry`（删任一档都不红）已删。[!] V8.7.2（契约变更）：回放**不再**一刀切跳过重试 —— 重试会把失败原因写进 prompt，下一轮 prompt 就不是「同一份录像」；录像若录了那一轮就该推进（否则「失败→修复」永远不可离线复演）。强判据由此改名并改契约：`test_replay_advances_to_next_round_in_both_retry_paths` 钉「两档各自都允许推进」+「分支体不许是 break / exit 3」+「缺录像必须 exit 2 报缺」；「白转」防线改由 `_should_retry_again` 有界约束 + 缺录像 fail loud 覆盖 | `test_verify_entry_contract.py`(5)、`test_verify_observability.py`(10)、`test_verify_concurrent_and_skip.py`(15) | - |
| 11.2 `[判据住特性2]` | 实跑档重试（判据住特性2） | 实跑档（generate + 逐条实跑）失败 -> 带原因整轮重来；回放同样带失败原因推进（缺录像 exit 2 报缺）；实跑未过 exit 3 —— 能力口径保留在本条；其判据（test_ai_retry_contract / test_ai_retry_same_cause，前者 V8.6.4 第二批由 test_ai_retry_loop 改名 —— 它守的是「上限 / 回炉 / 接线」契约）物理住在 tests/特性2-语义识别与步骤编排/，按「登记目录 == 物理目录」登记在 2.2 | - | - |
| 11.3 | 失败取证（CDP 证据包） | 失败时能拿出客观证据而不是一段 AI 的理由：CDP 抓 console / 异常 / network / 性能指标 / 无障碍树摘要，落成证据包；非 Chromium 系降级为 supported=False + 原因（绝不报错、也不假装拿到数据）；事件条数有上限且截断留痕；证据包里的敏感头（Authorization / Cookie / Set-Cookie / X-Api-Key 等）必须脱敏—— 证据包会被转发，脱敏是交付安全的一部分 | `test_failure_evidence_cdp.py`(12) | - |
| 11.4 | 试跑超时留现场 | 试跑超时时**不许只剩一句「真卡住」**：① 把 `TimeoutExpired` 里**本就捕获着**的输出带回来，揪出最后一条 `[step N]` 说「停在哪儿」（抓不到就明说卡在用例开始之前）；② 杀掉**整棵进程树**（`subprocess.run(timeout=)` 只杀 pytes t，它拉起的 Chromium 还占着被测服务 -> 会连带让重试轮也超时）；③ 区分「watchdog.txt 有栈」与「watchdog 压根没装上」，把这两种归因分开说，别把人往「某一步等不到」带偏 | `test_verify_timeout_forensics.py`(16) | - |
| 11.5 | 有界等待的每轮成本 | 「等状态流转」这类有界等待里，**每轮成本必须被限住、慢轮必须自己说出来**：① 每轮都要做的「重放搜索」走快速窗口（2s），否则慢目标下一次重放吃掉几十秒 -> 160s 的业务等待只够轮询 3 轮，业务值一变就卡在临界（第 1 轮红、第 2 轮才绿，白烧一轮生成 + 一轮试跑）；② 慢轮逐条打印「轮询第 N 轮花了 X.Xs（读到 …）」，别让人从「轮询 3 轮」里猜是业务没流转还是轮询太慢；③ 窗口必须**自己还原**，不许把页面默认超时留在小值上污染后续动作 | `test_bounded_wait_round_cost.py`(5) | - |


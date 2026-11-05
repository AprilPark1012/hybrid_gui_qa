"""框架特性规格（单一来源）。

特性 / 子特性 / 用例归属的唯一权威定义。文档由 build_tools/build_feature_map.py 生成，
判据（tests/特性9-质量闸门体系/test_feature_spec_contract.py）校验它与磁盘双向一致。

加特性或子特性：**只改本文件**，然后跑 `python build_tools/build_feature_map.py`。
"""

FEATURES = [
    dict(
        no=1, key="mixed_chain", name="AI 链路与离线回放",
        goal="只剩真 AI 链路（all --ai）与离线回放两种运行形态：都能跑通，且有一条统一验收入口",
        dir="特性1-混合链路",
        subs=[
            dict(no="1.1", name="AI 链路与离线回放", goal="真 AI 链路（all --ai）与离线回放（录像）各自可独立跑通（不含已删除的手搓链路）",
                 class1=["test_acceptance_entry.py", "test_offline_chain_python.py"],
                 class2=["verify_e2e_scenario1_online.py"]),
            dict(no="1.2", name="统一验收入口", goal="四条验收原则能用一条命令跑完（run_acceptance）。"
                                             "[!] 跳过策略（如 --skip-ai 必须显式留痕、SKIP != 通过）的判据物理住在 "
                                             "tests/特性9-质量闸门体系/，按「登记目录 == 物理目录」登记在 9.2",
                 class1=["test_acceptance_entry.py"],
                 class2=[]),
            dict(no="1.3", name="单包即离线可跑", goal="无外网机器解压交付包即可离线跑通 AI 链路（录像随代码包一起发，只有一个 zip）",
                 class1=["test_render_entrypoint.py"],
                 class2=["verify_offline_delivery.py"]),
            dict(no="1.4", name="目标地址覆盖对全链路生效",
                 goal="`HYBRID_BASE_URL` 必须同时作用于**业务步骤、登录流、场景身份前置**三条导航路径"
                      "（改写走唯一入口 `_rewrite_base`）；否则同一个包在用户内网/慢代理上会"
                      "「一半打新地址、一半打写死地址」—— 会话 cookie 互不通用，第一个业务步就等不到元素",
                 class1=["test_base_url_override_login.py"],
                 # 二类证据就是 7.4 的 verify_slow_target.py（物理住在 特性7-并发与资源安全，
                 # 「登记目录 == 物理目录」闸门要求不许在这里重复登记）
                 class2=[]),
        ],
    ),

    dict(
        no=2, key="semantic", name="语义识别与步骤编排",
        goal="把「人的自然语言」变成「可执行的步骤序列」—— 面向生成，对人友好也对机器友好",
        dir="特性2-语义识别与步骤编排",
        subs=[
            dict(no="2.1", name="语义名生成与对齐", goal="AI 产出的语义名能落到真实控件上；宁可不映射（大声告警）也不许错映射（静默点错）",
                 class1=["test_name_alignment.py"],
                 class2=[]),
            dict(no="2.2", name="自然语言步骤编排", goal="场景 yml 的自然语言 → 步骤序列；步骤能直接声明定位方式（by+value）而不依赖探测清单；"
                                                        "**AI 产出的有界重试口径**也归这里（产出侧被闸门拦下 -> 带原因重生成、上一轮缺陷记账不许留给下一轮；"
                                                        "实跑档失败 -> 带原因整轮重来）—— 原登记在特性11，V8.6.3 按「登记目录 == 物理目录」改挂此处",
                 class1=["test_step_direct_locator.py", "test_ai_scenario_preconditions.py", "test_prompt_no_demo_literals.py", "test_ai_no_hardcoded_row_values.py",
                          "test_semantic_mismatch_blocks.py", "test_llm_tool_choice_unsupported.py", "test_ai_can_express_row_checkbox.py",
                          "test_required_field_coverage.py", "test_required_fields_hard_checklist.py",
                          "test_prompt_list_clipping_is_general.py", "test_prompt_dom_facts_merged.py",
                          # C3/C4（2026-10-16）：提示词的两条「少说废话/别重复犯错」纪律 ——
                          #   段要紧凑（只留约束）、质量警告要回炉进下一轮（同一个错不许连犯三轮）
                          "test_prompt_wait_page_rule_compact.py",
                          # V8.6.3：这 5 条原挂在特性11（11.1/11.2），物理目录一直是特性2 -> 登记改挂此处
                          # V8.6.4：本文件删掉 1 条假绿兜底 `test_quality_gate_not_weakened`
                          #   （`or "SystemExit(2)" in src` 在全文 20 处命中下恒真）；
                          #   语义由特性11 `test_verify_failure_exit_codes_are_distinct` 完整接手
                          # V8.6.4（第二批 · 组 3）：`test_quality_warnings_feed_next_round.py`
                          #   与 `test_retry_leaves_no_stale_notes.py` **两条判据合一**并改名 ->
                          #   `test_retry_feedback_contract.py`（守的是**同一条跨轮反馈通道**的两端：
                          #   上一轮记账不许跨轮残留 + 记的账必须真递给 AI），登记合成本行一处
                          # V8.6.4（第二批 · 组 1 遗留）：`test_ai_retry_loop.py` -> 改名
                          #   `test_ai_retry_contract.py`（它守的是「上限 / 回炉 / 接线」契约）；
                          #   「同因不重试」那条下放给更强的 `test_ai_retry_same_cause.py`
                          "test_production_defects_gate_l1.py", "test_ai_incomplete_output_retries.py",
                          "test_retry_feedback_contract.py", "test_ai_retry_contract.py",
                          "test_ai_retry_same_cause.py",
                          # L34-a（2026-10-21）：步骤字段命名只许一套 `op` / `desc` ——
                          #   源码/产物/映射表三面守，外加负向自证（判据自己的样例不许被误伤）
                          "test_no_dual_step_field_names.py",
                          # V8.7.3（2026-10-26 · GLM 实测事故）：换 OpenAI 兼容端点才暴露的两件事 ——
                          #   ① GLM 给「没填的字段」发 `null`，DeepSeek 是**省略该键**；Pydantic 的
                          #      `default=` 只认后者 -> GLM 走结构化输出时 16 个步骤全部
                          #      `semantic_name=null` -> 每轮必挂（不是"答得差"，是没兼容它的习惯）；
                          #   ② LLM 客户端 `timeout=None` 在 httpx 里是**禁用超时**（不是用默认值）
                          #      -> 第 2 次重试遇到端点不回包就永久挂住，日志停在「第 1/3 次失败」。
                          #   判据同时钉住「放宽 null 但错类型仍须报错」与「走真入口验到底层客户端」。
                          "test_llm_null_and_timeout.py",
                          # V8.7.5（2026-10-27 · 用户实测两问）：① `llm-doctor` 打印
                          #   `provider deepseek` 而端点明明是 GLM（`ChatOpenAICompatible` 继承
                          #   `ChatDeepSeek`，带着实现类写死的 provider 字段）-> 体检必须报
                          #   「端点归属的厂商」+ 单独标注实现类，否则用户以为配错；
                          #   ② 体检只发两次**极小 schema** 请求就下「可以用」结论 -> 假保证：
                          #   真实 prompt 是 11 万字符级别，`high` 档实测 175.9s / 39 步，
                          #   而默认 180s 超时只差 4 秒。于是新增**大 prompt 实探**（走框架自己的
                          #   `_build_planner_prompt`）并让它的失败**阻断**「可以用」结论。
                          #   判据同时钉住「缺 tool_calls 时必须点破 effort 太低」与
                          #   「.env.example 必须登记这几项」（可调项可发现）。
                          "test_llm_doctor_vendor_and_bigprobe.py",
                          # V8.7.7（2026-10-27 · 用户追问「200+ 步不是更久？怎么提效」）：
                          #   ① 61 步用例 verify 试跑 397.3s、run 只用 201.4s（同脚本同断言），
                          #     而 run 是 -n 16（16 套浏览器）反而快一倍 -> 说明 verify 那段在**等**，
                          #     但日志**没有每步耗时**，只能猜（我还误判成「脏数据」，被用户当场否掉：
                          #     他每次跑前删了 demo/.data，且 explore 探测只点击不提交）。
                          #     -> 在 `_log`（唯一步骤日志入口）量每步耗时 + step 计数 + [SLOW] 标记；
                          #     判据钉住「必须挂在唯一入口、不许分散埋点」。
                          #   ② reset 默认值原本写死 demo 的 localhost:8000/api/reset?purge=1 ——
                          #     真实系统没有该端点（白等 5s），且**框架不该假设被测应用能清库**
                          #     （生产环境没这开关，有些测试数据本该保留）。-> 默认改 off，
                          #     新增 auto 从 TARGET_URL 推导；判据钉住「默认 off + 每次现读不缓存」。
                          "test_step_timing_and_reset_default.py",
                          # V8.7.12（2026-10-28 用户实测纠正）：`got none` 的诊断原先**硬编码**断言
                          #   「这多半不是模型不稳定，而是 reasoning_effort 太低」。实证相反：
                          #   用户 effort=high + 登录页只有 3 条清单（极小 prompt）也报同一错误，重试即过
                          #   => 根因是「模型偶发不调工具」，与 prompt 大小、effort 档位都无关。
                          #   判据钉住：必须读 LLM_REASONING_EFFORT 再分流，且 effort 已高时
                          #   不许再给「档位太低/改 high」的误导结论（只查非注释代码，注释里的反面教材合法）。
                          "test_got_none_diagnosis_honesty.py",
                          # V8.7.14（2026-10-28 实测定位）：模型把结构化结果写进 content 通道时
                          #   上游直接抛 got none 并把 content 丢掉 -> 框架把「成功」判成「失败」去重试。
                          #   test_content_channel_fallback.py = 接线与判定口径（静态）；
                          #   test_content_fallback_unit.py   = mock 上游响应，覆盖兜底 5 条分支（行为）。
                          "test_content_channel_fallback.py",
                          "test_content_fallback_unit.py",
                          # V8.7.15（2026-10-29 用户实测）：expect_first_row 的 cell_field
                          #   可能压根不在页面上 -> 实跑 715s 才报「没有这一列」。生成阶段已有
                          #   探测到的列清单却没校验。判据钉住：只警告不拦（跨页会误报，
                          #   用户定「宁漏不误伤」）。
                          "test_row_column_precheck_warns_only.py",
                          # V8.7.16（2026-10-29 二次实测）：AI **同一场景同一起点**两次结果不同
                          #   （一次第 2 轮改对了、一次两轮都写中文表头）=> 非确定性，不能赌它
                          #   下次会改对。header->field 唯一反查补正（多义不猜）。
                          "test_first_row_column_header_fallback.py",
                          # V8.7.18（2026-10-29 用户实测）：列清单预检要覆盖**所有探测过的页**。
                          #   第 63 步在发票列表页要查「合同编号」（该页确实有），而清单是订单
                          #   列表页的 -> 报「不在探测到的列里」= 假阳性。改用 _ALL_ROW_FIELDS。
                          "test_row_fields_cross_page_coverage.py",
                         # V8.7.22（2026-10-29 真链路两次失败）：AI 想写 expect_first_row 验
                         #   「搜到了刚建的发票」，但 cell_field 是 td[data-field] 的值
                         #   （orderName）而不是表头文案（订单名称），探针有映射却没落盘
                         #   -> 错误信息给不出候选 -> AI 两轮写同样 -> 卡死。
                         "test_row_fields_reach_ai.py",
                         # V8.7.23（2026-10-29 用户拍板「不要吝啬重录录像的 token」）：
                         #   AI 只会用 expect_text 断言自己 fill 的值 -> 被假绿闸门拦死。
                         #   把「验记录建出来 -> 唯一正确写法 expect_first_row」升到系统提示，
                         #   并指明 cell_field 只能从行内列清单的 field 抄（不是表头文案）。
                         "test_prompt_points_to_cell_field.py",
                         # V8.7.24（2026-10-29 第二次真机实测）：AI 改用 expect_first_row 了，
                         #   但拿订单页的 orderName 去断发票列表页（该页没这列）-> 735s FAILED。
                         #   列清单按页分组渲染 + 按页校验 cell_field（警告里列出该页可用列）。
                         "test_row_column_page_scoped.py",
                         # V8.7.25（2026-10-30 V8.7.24 真机日志揪出）：登录步骤的 goto 拿 element 顶 URL
                         #   -> Page.goto: Cannot navigate to invalid URL -> 登录前置整条中断。
                         "test_login_goto_never_uses_element.py",
                         # V8.7.28（2026-10-30 清 output/ 后首次跑必炸）：登录链路里
                         #   `_probe_login_page` 自己 `with sync_playwright()`（调用方 scan_pages 已开 ctx）
                         #   + `plan_login` 里裸 asyncio.run -> 与 Playwright Sync API 互斥 -> 登录前置失败
                         #   -> 探测照常跑、7 页全被重定向成登录页、每页探到 login-accounts 的 3 条空列。
                         "test_login_no_nested_playwright.py",
                         # V8.7.30（2026-10-31 真机日志揪出）：弹窗补充把「创建」当成开弹窗，
                         #   而发票列表页的「创建」是**整页跳转** -> 探测所在页面被带跑 ->
                         #   该页真表 11 列一条都探不到（AI 只能猜列名）。点完比 URL 判导航。
                         "test_modal_probe_never_navigates.py"],
                 class2=["verify_role_switch_click.py"]),
            dict(no="2.3", name="步骤到定位的合成", goal="步骤里的语义名/属性如何合成可执行定位表达式"
                                                       "（`verify_scope_locate.py` 物理住在 tests/特性3-分层定位与控件识别/，"
                                                       "按「登记目录 == 物理目录」只挂 3.1）",
                 class1=["test_scope_locate_expr.py", "test_locate_by_title.py"],
                 class2=[]),
            dict(no="2.4", name="场景声明契约", goal="人写的那部分：pages / pre / auth / data / probe_url —— 声明必须由场景提供，框架不懂具体系统",
                 class1=["test_login_stepwise_contract.py", "test_scenario_auth_spec.py", "test_page_pre_actions.py", "test_probe_pre_consistency.py",
                         "test_probe_url_and_occurrence.py", "test_login_priming_coverage.py"],
                 class2=["verify_login_priming.py", "test_page_pre_actions_force_fallback.py", "test_scenario_probe_pre.py", "verify_page_pre_actions.py"]),
            dict(no="2.5", name="断言步骤可用性对齐",
                 goal="**AI 能写的断言，框架都必须真的执行**：`ASSERT_OPS` 三个动作在登录链路与业务链路"
                      "**走同一个执行入口**（`_exec_assert`），登录段不许再把断言丢掉；"
                      "行断言失败时必须给出**该页实际列**（只说「没有这一列」等于让人重新猜）",
                 class1=["test_assert_step_availability.py"], class2=[]),
        ],
    ),

    dict(
        no=3, key="locate", name="分层定位与控件识别",
        goal="在生产系统的复杂页面上仍能唯一定位到目标控件 —— 面向执行",
        dir="特性3-分层定位与控件识别",
        subs=[
            dict(no="3.1", name="顶层锚点加容器内下钻", goal="真实系统只有顶层元素有 testid；子元素靠「锚点 + 容器内相对语义路径」定位",
                 class1=["test_element_anchor_path.py", "test_row_fields_cover_all_columns.py",
                         "test_row_columns_are_named_items.py",
                         # V8.7.18（2026-10-29 用户实测）：行容器里的**单实例**控件也要提示
                         #   给 row_index。实测「期次号@开票页」探测时只有 1 个 -> 不提示 ->
                         #   实跑到那步已 2 行 -> 2 个同名匹配 -> 434s 白跑（探测≠运行）。
                         "test_row_container_singleton_hint.py",
                         # V8.7.21（2026-10-29 用户两次真机实测 53 条稳定复现）：
                         #   V8.7.18 的「容器内一个重复 -> 整区逐个提示」是纯噪音：
                         #   登录页 18 条（4 个快捷登录链接牵连账号/密码/登录）、
                         #   订单详情页 35 条（15 条是空名字的表格单元格）。
                         #   A' 判据：重复控件种类 >= 2 才算真行容器；A 汇总：只打一行。
                         "test_row_container_noise_budget.py",
                         # V8.7.27（2026-10-30）：跨页同名元素刷 100+ 行 -> 同前缀合并成一行汇总
                         "test_collision_report_noise_budget.py",
                         # V8.7.29（2026-10-31 实测）：订单详情页的明细行是 **div 网格**
                         #   （`<div class="cell" data-field="lineNo">`），而 probe_row_fields
                         #   只扫 `table` -> 该页 0 列 -> AI 永远看不到 lineNo/lineStatus。
                         "test_div_grid_row_fields.py",
                         # V8.8.0 P0-A：行内列标识**不许写死属性名**。真实生产系统用
                         #   `td[data-colid="col_57"]`（框架生成的列契约，值稳定），第三方
                         #   框架可能叫 data-colx —— 写死 data-field 等于只支持一家。
                         #   改成按「值分布」推断：行=每行不同，列=同列跨行相同。
                         "test_grid_attr_inference.py",
                         # V8.8.0 P0-C：行按**唯一标识**定位（`tr[data-rowid="row_1"]`）。
                         #   原来只有 row_text / row_index 两档：前者行内文本重复就歧义，
                         #   后者行序一变就指错行。生产系统的行标识值稳定、与行序无关 -> 最稳。
                         #   优先级 row_id > row_text > row_index；属性名同样不写死。
                         "test_row_id_locator.py"],
                 class2=["verify_scope_locate.py"]),
            dict(no="3.2", name="多层嵌套容器", goal="容器套容器（区域内表格、表单里分组）时路径仍能唯一",
                 class1=["test_element_anchor_path.py"],
                 class2=[]),
            dict(no="3.3", name="弹出层与可展开容器", goal="藏在 display:none 菜单里、点开才出现的弹层控件、"
                                                     "以及**只在编辑态/动态新增之后才存在**的控件都能被探到并用起来"
                                                     "（框架开的必须由框架关）；"
                                                     "探到的「藏在哪个入口后面」必须**告诉 AI**（`requires_open` + 规则 1c），"
                                                     "否则生成的用例会直接点未展开的弹层控件 -> `element is not visible` 超时",
                 class1=["test_expandable_menu_discovery.py", "test_probe_single_entry.py",
                         "test_probe_page_scope.py", "test_probe_incremental.py",
                         "test_editable_state_probe.py", "test_requires_open_hint.py"],
                 class2=["verify_expandable_menu.py", "verify_probe_path_parity.py",
                         "verify_editable_state_probe.py"]),
            dict(no="3.4", name="跨页面元素", goal="多页面场景下元素跨页可用；同名元素改 `原名@页名` 消歧；"
                                                     "explore 期喂给 AI 的**完整清单**必须落盘，作为映射表与运行时快照的**唯一名字来源**",
                 class1=["test_runtime_name_source_is_explore_snapshot.py", "test_elementmap_list_contract.py",
                         "test_explore_manifest_authoritative.py", "test_page_identity_contract.py"],
                 class2=["verify_cross_page.py"]),
            dict(no="3.5", name="属性直定位", goal="探测清单兜不住时，用属性（by+value）直接定位；select 的 index 语义 = 第 N 个非空选项（跳过 placeholder）",
                 class1=["test_select_by_index.py", "test_select_without_value.py", "test_text_assert_prefers_visible.py"],
                 class2=["verify_select_index_skips_placeholder.py"]),
            dict(no="3.6", name="iframe 内控件", goal="[!] 未实现（缺口）：iframe 内以及跨 iframe 的控件识别与操作",
                 class1=[], class2=[], status="未实现"),
            dict(no="3.7", name="行内单元格定位", goal="行锚 + 单元格：列的指定方式（多列 by）与支持的 op（不只 click）",
                 class1=["test_row_cell_col_by.py", "test_row_cell_ops.py"],
                 class2=[]),
            dict(no="3.8", name="重复控件信号与行定位闸门",
                 goal="同一容器内重复出现的控件（表格每行一个）收敛成一条并标 `multi_match`，"
                      "AI 据此给行定位（`row_index`）；生成期拦下「引用重复控件却没给行定位」的步骤。"
                      "**框架确定性兜底（V8.4.6）**：模型不写也不阻塞 —— 能由用例结构判死的"
                      "（刚新增行 -> `row_index=-1`）由 `apply_row_locator_fallback()` 补上"
                      "（只认精确键、宁漏不误伤、出现行锚后不再兜底），判不出来的照旧报红；"
                      "字段口径只有一处（`ROW_LOCATOR_FIELDS` + `has_row_locator()`）"
                      "**行内定位走多命中（V8.4.6）**：`_act_row` 不再先走要求语义唯一的 `_loc()`"
                      "（行内同名列控件必然多个 -> 会被判死），改走探测期录下的"
                      "「锚点 + 容器内相对语义」（`scope_locate`）拿多命中 locator 再 `.nth(行号)`；"
                      "行内 `select` 未给 value 时与非行内**同口径**（选第一个真选项、留痕、无选项才报错）",
                 class1=["test_multi_match_signal.py", "test_row_locate_uses_scope.py", "test_row_index_lands_in_case.py", "test_elementmap_readers_accept_list_form.py"],
                 class2=[]),
            dict(no="3.9", name="元素自身 id 定位档",
                 goal="元素**自身**带稳定 `id` 时，给定位链多一档："
                      "`test_id` > `element_id` > 锚点下钻 > `role+name` ——"
                      "有些控件的祖先链里**没有任何可锚容器**（容器是裸 `<div>`），"
                      "若它又与别的控件同名，`role+name` **必然歧义**；此时 `id` 是唯一可用的稳定身份"
                      "（实测：订单详情页底部那个「保存」与行工具栏「保存」撞名，"
                      "而它自身 id 唯一 -> 靠这一档定住）。"
                      "口径：采集进条目 -> 进运行时快照白名单 -> 定位链一档；"
                      "**不进 AI 提示词、也不进录像结构键**（省 token 且不让录像失效）；"
                      "改回任何一环都会被判据抓住（含「白名单静默丢弃」这个最隐蔽的坑）",
                 class1=["test_element_id_is_captured_and_used.py"],
                 class2=[]),
            dict(no="3.10", name="可点击性补探", goal="默认选择器看不见、但实测能点的元素（裸 div onclick / 无 href 的 a / "
                                                     "canvas / img 等）也要进清单 —— 显式事件处理器直接采信，纯样式信号"
                                                     "（cursor:pointer / tabindex / contenteditable）需两条互相印证；"
                                                     "宁可漏补也不制造假控件（噪音 = 没提示）",
                 class1=["test_clickable_probe_signals.py"],
                 class2=[]),

            dict(no="3.11", name="视觉 grounding 兜底", goal="确定性定位（语义 + a11y + 可点击性补探）都失败时，"
                                                     "用截图向多模态模型要 0-1000 归一化坐标 -> 按截图实际尺寸换算像素 -> 点击 -> "
                                                     "**校验有没有生效**（签名没变就报 no-effect，绝不报成功）；"
                                                     "空回复做一次收紧重试（国产模型思考模式会吃光 token 预算）；"
                                                     "失败只报原因不抛；不是主路径，只在兜底时调用。"
                                                     "真机实测：同一页 4 个同名按钮中定位指定那一行，偏差 8.5 px、命中；"
                                                     "定位单按钮偏差 0.8 px",
                 class1=["test_visual_grounding.py"],
                 class2=[]),

            dict(no="3.12", name="行区信号 row_zone",
                 goal="「探测时唯一」不等于「运行时唯一」：只要该容器里有『新增行』这类行增删动作，"
                      "这个区**必然会长多行**（与当前行数无关）。探针据此给区内**当前唯一的输入类**控件"
                      "标 `row_zone`，① 提示词专门一段要求「排在新增行之后必须给 row_index」"
                      "② 框架兜底在「前文确有新增行 + 无行锚」时补 `row_index=-1`。"
                      "口径三条：只标输入类（按钮随行增长也不会变成第几行的保存＝误伤）、"
                      "只标当前唯一的（multi_match>1 已有更强信号）、不动 multi_match"
                      "（写它会让质量闸在单行场景误拦）。跨页同名控件不给纯基名（会补错页）。"
                      "来历：真 AI 链路开票页探测 1 行、用例自己点新增行 -> 运行期 2 个同名匹配 -> "
                      "第 1 轮 424.9s 白跑，靠带原因重试才通",
                 class1=["test_row_zone_signal.py"],
                 class2=[]),
        ],
    ),

    dict(
        no=4, key="ambiguity", name="选错控件兜底",
        goal="同名/同区域控件不许被选错；选不准就大声失败，绝不静默点到错的",
        dir="特性4-选错控件兜底",
        subs=[
            dict(no="4.1", name="同名歧义闸门", goal="同名控件各有唯一名字（后缀消歧）并留痕；用例引用裸名会被质量闸拦下（fail loud）",
                 class1=["test_element_ambiguity_gate.py", "test_container_narrowing.py"],
                 class2=["verify_element_ambiguity.py"]),
            dict(no="4.2", name="全页序号定位", goal="不锚容器时的整页 nth —— 处理同名按钮分布在不同区域",
                 class1=["test_page_scope_nth.py"],
                 class2=[]),
            dict(no="4.3", name="行锚选取", goal="从「整行文本」改成「整表内唯一的最短单元格文本」作行锚",
                 class1=["test_row_anchor_selection.py"],
                 class2=[]),
            dict(no="4.4", name="行内字段定位信号", goal="锚点内表单字段的 target 步不能落到 get_by_text（会选到标签而不是输入框）",
                 class1=[],
                 class2=["verify_row_field_signal.py"]),

        ],
    ),

    dict(
        no=5, key="layers", name="用例脚本数据三层分离",
        goal="用例（意图）/ 脚本（可执行）/ 数据（多变）三层各司其职，数据变了不用改用例",
        dir="特性5-用例脚本数据三层分离",
        subs=[
            dict(no="5.1", name="三层职责边界", goal="同一场景多组数据 -> 产出多条独立用例，报告独立一行、失败可定位",
                 class1=["test_data_expand.py", "test_waiting_semantics_maps_to_wait_text.py", "test_row_column_carried_through.py"],
                 class2=[]),
            dict(no="5.2", name="数据驱动不静默退化", goal="占位符没被替换时必须报错，不许把 `{占位符}` 原样当字面量跑",
                 class1=["test_data_driven_placeholders.py", "test_goto_url_parameterization.py"],
                 class2=[]),
            dict(no="5.3", name="生成物转义安全", goal="数据里的换行/引号等特殊字符不能破坏生成的 Python 源码",
                 class1=["test_generator_escaping.py"],
                 class2=[]),
            dict(no="5.4", name="增量生成", goal="场景变了要重新生成；两个触发源都要认",
                 class1=["test_generate_incremental.py"],
                 class2=[]),
            dict(no="5.5", name="可选字段的渲染健壮性", goal="步骤缺可选字段（如 select 不给 value）时脚本照样生成，绝不因单个字段缺失崩掉整批",
                 class1=["test_render_step_without_value.py"],
                 class2=[]),
        ],
    ),

    dict(
        no=6, key="healer", name="自愈闭环 Healer",
        goal="定位失败时按**放宽阈值**重定位并留痕；real_bug 时**绝不返回 locator**（自愈不许掩盖真 bug）",
        dir="特性6-自愈闭环Healer",
        subs=[
            dict(no="6.1", name="失败自愈（A 级）",
                 goal="放宽阈值（阈值×0.75 / MINGAP×0.6）再定位一次；无用元素（goto/expect_text/无 element）"
                      "直接早退且**不记事件**；B 级 LLM 重猜是**未实现的骨架**且必须如实说明（不许误导去配 key）",
                 class1=["test_healer_behavior.py"], class2=[]),
            dict(no="6.2", name="三态裁决与可审 diff",
                 goal="recovered / real_bug / failed 各自判对；业务断言不通过或抛异常一律 real_bug 且 **locator 置空**；"
                      "heals json+md 留下「原语义 -> 新 locator -> 置信度 -> 结果」",
                 class1=["test_healer_behavior.py"], class2=[]),
        ],
    ),

    dict(
        no=7, key="concurrency", name="并发与资源安全",
        goal="并行跑验证不许把内存打爆；资源闸门不许支配一类自测",
        dir="特性7-并发与资源安全",
        subs=[
            dict(no="7.1", name="二类调度", goal="预算 1200s + 并发 + 内存闸的调度策略",
                 class1=["test_run_verifications_plan.py"], class2=[]),
            dict(no="7.2", name="内存闸不支配一类", goal="一类的红绝不能由二类的资源闸门造成（否则一类红灯失去可信度）",
                 class1=["test_class1_no_mem_gate_coupling.py"], class2=[]),
            dict(no="7.3", name="runner 能起来", goal="二类 runner 冒烟；环境不满足时跳过并说明，而不是假红",
                 class1=["test_runner_smoke.py"], class2=[]),
            dict(no="7.4", name="慢目标闸门", goal="慢机器/高并发目标下用例依然全绿（下行区就绪信号）",
                 class1=[], class2=["verify_slow_target.py"]),
        ],
    ),

    dict(
        no=8, key="replay", name="离线回放",
        goal="没有外网的机器也能跑 AI 链路 —— 靠 LLM 录像",
        dir="特性8-离线回放",
        subs=[
            dict(no="8.1", name="录像键两级策略", goal="严格级（逐字一致）+ 宽松级的匹配分工",
                 class1=["test_cassette_strict_policy.py", "test_cassette_key_stability.py", "test_cassette_fuzzy_fallback.py", "test_cassette_picks_latest_on_struct_tie.py"], class2=[]),
            dict(no="8.2", name="录像体检", goal="场景段抠取 + 覆盖判定；缺录像要能报出来",
                 class1=["test_check_cassettes_block.py"], class2=[]),
            dict(no="8.3", name="录制与回放契约", goal="录像能录、能放、放得对（不联网、不要 key）",
                 class1=["test_llm_cassette.py"],
                 class2=["verify_e2e_scenario3_cassette.py", "verify_e2e_scenario3_replay.py"]),
            dict(no="8.4", name="LLM 抖动重试", goal="LLM 偶发失败要退避重试，不许把抖动当失败",
                 class1=["test_llm_retry.py"], class2=["verify_offline_chain_deps.py"]),
            # V8.7.2（2026-10-25）：回放不再在「校验失败/实跑失败」处一刀切放弃。
            #   录制期必然先失败一轮、第 2 轮才修好（orders_invoice_full_lifecycle 实测），
            #   而重试会把失败原因写进 prompt -> 下一轮 prompt 与录制那轮**不同**；
            #   录像包若录了那一轮（正是「失败→修复」闭环），就该继续推进。
            #   缺录像必须优雅报缺（CassetteError 与 AiExploreError 是兄弟类，原本只会 traceback）。
            dict(no="8.5", name="回放的重试轮推进",
                 goal="回放遇到「产出校验不合格 / 实跑失败」不许直接放弃：下一轮 prompt 因带失败原因而不同，"
                      "录像录了那一轮就继续推进；缺那一轮则 fail loud 报缺（exit 2 + 明话），"
                      "绝不静默降级、也绝不抛未捕获 traceback",
                 class1=["test_replay_allows_retry_rounds.py"], class2=[]),
        ],
    ),

    dict(
        no=9, key="gate", name="质量闸门体系",
        goal="框架自己守自己：布局/命名/环境/交付/就绪/安全六类契约，坏了就红",
        dir="特性9-质量闸门体系",
        subs=[
            dict(no="9.1", name="布局与命名契约", goal="tests/ 与生成物的布局、路径拼接（跨平台）、命名空间契约",
                 class1=["test_test_layout_contract.py", "test_generated_layout_contract.py",
                         "test_path_join_contract.py",
                         # V8.6.4（第二批 · 组 2）：`test_case_scenario_contract.py` **整文件删** ->
                         #   `source_scenario` 字段级校验 + `_YML_REF` 正则迁进 9.6 的
                         #   `test_scenario_case_script_hygiene.py`（三者同源：都是「用例 <-> 场景」对账）
                         "test_click_then_ready_contract.py", "test_assert_kinds_render.py",
                         # V8.6.4：`test_wait_text_kind.py` 摘走（三合一后整条落 9.6 ——
                         #   它守的是「等待式断言的渲染契约」，不是布局/命名）
                         "test_demo_testid_policy.py"],
                 class2=[]),
            dict(no="9.2", name="质量闸", goal="用例质量 / 生成质量 / demo 新鲜度，**且不许误伤**；"
                                                     "**闸门统一契约 + 全量注册表**（B′：实现跟特性走、登记进 core/gates.py）；"
                                                     "**验收入口的跳过策略**同归此（跳过必须显式留痕、SKIP != 通过、失败优先于跳过 —— "
                                                     "`test_acceptance_skip_policy.py` 物理住本目录）",
                 class1=[  # V8.6.4：`test_case_quality_gate.py` -> `test_case_evidence_gate.py`
                           #   （名实相符：它只守**换页证据**那一类，不是整个用例质量闸）
                           "test_case_evidence_gate.py", "test_generate_quality_gate.py", "test_gate_protocol_registry.py",
                         # L36 (V8.7.1)：断言输入回显 = 硬红线（含 first_row 豁免 / 场景显式豁免 / 提示词告知）
                         "test_assertion_echo_gate.py",
                         "test_demo_freshness_gate.py",
                         # V8.6.4（第二批 · 组 2）：`test_ai_case_scenario_sync.py` **整文件删** ->
                         #   场景指纹同步 + 它的负向自证迁进 9.6 的
                         #   `test_scenario_case_script_hygiene.py`（「AI 用例与场景同步」这一面随判据走）
                         "test_daily_skip_marker.py",
                         # V8.6.3：原登记在 1.2（特性1），物理目录一直是特性9 -> 登记改挂此处
                         "test_acceptance_skip_policy.py",
                         # V8.4.3：Windows 实测两次误拦（语义校准漏 help_text / 写死检测不对照场景原文）
                         "test_no_false_positive_blocks_ai.py"],
                 class2=["verify_demo_freshness.py"]),
            dict(no="9.3", name="环境与编码适配", goal="跨平台路径/内存探测/UTF-8 与 cp936 —— 源码不许出现 GBK 编不了的字符；"
                                                      "**源码不许有未绑定名**（拷代码漏作用域会被 except 兜成静默降级）",
                 class1=["test_env_adaptation.py", "test_utf8_io.py", "test_browser_preflight.py",
                         # V8.7.20（2026-10-29 用户 Windows 实测 6 skipped vs 本机 3 skipped）：
                         #   venv 解释器定位全仓 3 份实现、只有 1 份认 Windows。
                         #   `Path(REPO)/".venv"/"bin"/"python"` 在 Windows 永不存在 -> 判据永远 skip（假绿）。
                         "test_venv_python_single_entry.py",
                         # V8.7.17（2026-10-29 用户 Windows 实测 1 failed）：写进 json 的仓库相对
                         #   路径必须正斜杠。Windows 上 str(Path) 给反斜杠，与判据侧 as_posix()
                         #   口径不同 -> 同一文件两个格式 -> 假红「孤儿脚本」。
                         #   [!] 2026-10-07 只修了读的一侧（只修半边），这次写入+读取+拼路径三处都归一化。
                         "test_repo_relative_paths_use_forward_slash.py",
                         "test_no_stale_paths.py", "test_no_undefined_names.py"],
                 class2=["verify_undefined_names.py"]),
            dict(no="9.4", name="交付包与文档同步",
                 goal="打包内容完整（含运行期必需文件）、文档与代码一致、只留一份 README；"
                      "`HYBRID_ROW_ZONE_STRICT=1` 时行区控件缺行定位的产物**拒绝出包**（A' 严格体检）",
                 class1=["test_pack_release.py", "test_pack_release_requires_generated_dir.py",
                         # A'（2026-11-04）：行区控件缺 row_index 的产物**不许当交付物发出去**。
                         #   闸门只加在打包链路（explore 那道仍是警告级，回放模式下硬拦会把主推命令挡死）。
                         "test_row_zone_pack_strict.py",
                         # V8.7.19（2026-10-29 用户 Windows 实测 1 failed）：交付包绝不许带含凭据的 `.env`。
                         #   根因 `Path(".env").suffix == ""` 落不进 EXCLUDE_SUFFIX；git 分支靠 .gitignore
                         #   侥幸排除，**非 git 目录（交付包解压后）走 rglob 全收** -> 用户手工建的 .env 会被打进包。
                         "test_pack_dotenv_never_shipped.py",
                         "test_readme_structure.py", "test_docs_sync.py", "test_build_html_hl.py", "test_architecture_doc_contract.py"],
                 class2=["verify_html_sync.py"]),
            dict(no="9.5", name="保留与产物健康", goal="日志/产物保留策略与健康检查",
                 class1=["test_retention_runs.py", "test_artifacts_health.py"],
                 class2=["verify_retention_runs.py"]),
            dict(no="9.6", name="就绪与等待契约", goal="点击后等就绪、等文本刷新策略、选择器生效、"
                                                     "**等待式断言 `wait_text` 的渲染契约**（三合一后整条归此）、"
                                                     "**动作后置校验（做了 != 生效了）**、"
                                                     "**`cases` <-> `scenarios` 三目录新陈代谢**：孤儿 AI 用例 / "
                                                     "`source_scenario` 可解析 / 场景指纹同步 / 防空转哨兵"
                                                     "（V8.6.4 第二批 · 组 2 把原 9.1 `test_case_scenario_contract.py` "
                                                     "与 9.2 `test_ai_case_scenario_sync.py` 两条同源判据**整文件删**、"
                                                     "迁进 `test_scenario_case_script_hygiene.py` —— 三者同源，只留一处口径）",
                 class1=["test_ready_and_locate.py",
                         # V8.6.4：`test_wait_text_refresh_policy.py` + `test_wait_text_selector.py`
                         #   + 9.1 摘过来的 `test_wait_text_kind.py` -> 合并成这一条（渲染契约三合一）
                         "test_wait_text_render_contract.py", "test_import_targets.py",
                         "test_generated_pytest_discovery.py", "test_case_imports_cover_helpers.py",
                         # V8.6.4（第二批 · 组 2）：本条 = 三者合一后的「用例 <-> 场景来源」对账
                         #   （保名：它已含防空转守卫 + 覆盖告警，是三者里最全的）
                         "test_scenario_case_script_hygiene.py", "test_target_reachability.py",
                         "test_declared_wait_budget.py", "test_action_effect_check.py"],
                 class2=["verify_wait_text.py", "verify_action_effect_check.py"]),
            dict(no="9.7", name="替换安全与闸门解耦", goal="用例替换不许破坏结构；闸门自身不许互相耦合",
                 class1=["test_case_replacement_safety.py", "test_no_gate_coupling.py"],
                 class2=[]),
            dict(no="9.8", name="特性规格契约", goal="特性/子特性/用例归属的规格（feature_spec）与磁盘**双向一致**："
                                                     "规格里列的文件必须存在、磁盘上的用例必须有归属、编号规范、目录不漂移、文档与规格同步",
                 class1=["test_feature_spec_contract.py"],
                 class2=[]),
        ],
    ),

    dict(
        no=10, key="cli", name="CLI 帮助契约",
        goal="命令行对新手友好：帮助自动覆盖、参数错必报错、退出码能区分好坏",
        dir="特性10-CLI帮助契约",
        subs=[
            dict(no="10.1", name="退出码契约", goal="成功 0 / 有用例失败 1 / 没匹配到 5 / 环境问题其它 —— 绝不静默成功",
                 class1=["test_cli_exit_codes.py"], class2=[]),
            dict(no="10.2", name="参数契约", goal="未知/错位参数一律报错 + 非 0 退出，绝不静默忽略",
                 class1=["test_cli_flags.py"], class2=[]),
            dict(no="10.3", name="帮助自动覆盖", goal="新增子命令/参数必须自动出现在 --help 总览里",
                 class1=["test_cli_help_coverage.py"], class2=[]),
            dict(no="10.4", name="setup 与分发采纳", goal="`setup --check` 退出码能区分环境好坏",
                 class1=["test_cli_setup.py"], class2=[]),
            dict(no="10.5", name="推荐路径口径", goal="文档/提示/培训页的主推路径 = 真 AI 链路（V8.6 起是唯一链路）；不许把手搓链路写成可用入口（历史版本记录不改）",
                 class1=["test_ai_first_docs.py", "test_tunables_exposed_as_flags.py"], class2=[]),
            dict(no="10.6", name="文档真值契约", goal="文档说的必须和代码做的是同一回事：引用的路径存在、" \
                                                      "主线命令统一 all --ai、配置表不虚报条数、关键数字对齐代码真值",
                 class1=["test_docs_truth_contract.py",
                         # V8.7.9（2026-10-28 · 用户「开发期效率低，还没进交付期可以不跑 run」）：
                         #   新增 `all --ai --no-run`（开发期到 verify 为止）。
                         #   [!] 助手第一版建议「开发期改用 explore --ai」被
                         #   test_j2_no_explore_ai_as_runnable_command 当场判红 ——
                         #   用户 2026-10-11 定过「两条链路统一成 all，不另开命令」。
                         #   所以能力开在 all 上，入口仍只有一个；判据额外钉住 README 引导行
                         #   也必须是 all --ai --no-run、不许出现可照敲的 explore --ai。
                         "test_all_no_run_switch.py",
                         # V8.7.11（2026-10-28 · 用户「B、可以加一条判据」）：
                         #   cli --help 里 `--case contracts_search_by_no` 那个 case **仓库里不存在**，
                         #   且真实 case id 带时间戳、每次生成都变 所以 写死任何具体 id 都注定过时。
                         #   判据 = 示例值必须真实存在且不带时间戳（宁漏不误伤：中文说明/单字母/占位符放过）
                         #   + 正向自证（必须有 <case_id> 式说明，防「删光示例糊弄判据」）。
                         "test_no_hardcoded_case_id.py"], class2=[]),
            dict(no="10.7", name="文档结构真值契约", goal="培训页/README 画的目录结构必须与磁盘一致：" \
                                                          "登记的特性夹都要真实存在、磁盘上的特性夹都要登记、" \
                                                          "不许声称有 f01 或每特性 api.py",
                 class1=["test_docs_structure_truth.py"], class2=[]),
            dict(no="10.8", name="通用 LLM 入口", goal="一个开关接所有 OpenAI 兼容服务（GLM / Kimi / " \
                                                        "通义 / 豆包 / 本地 vLLM）—— 必须走 function calling、" \
                                                        "优先级最高、可被 cli config 发现、密钥不外泄",
                 class1=["test_llm_provider_switch.py"], class2=[]),
            dict(no="10.9", name="LLM 体检 + 思考档位", goal="换模型前先体检：`cli llm-doctor` 真发 2 次请求，" \
                                                          "报「连通 / function calling 通不通 / 端点在用哪档思考」，" \
                                                          "并区分「不可用」与「能用但打折（thinking 模式拒 tool_choice）」。"
                                                          "配套 `LLM_REASONING_EFFORT` 旋钮压思考强度；"
                                                          "旋钮必须真进请求体（断言产出而非调用）、不污染默认、可发现",
                 class1=["test_llm_doctor.py", "test_reasoning_effort_advice_consistency.py"], class2=[]),
            dict(no="10.10", name="思考模式端点兼容", goal="思考模式端点拒「指名函数」tool_choice 时**有界降级**为 auto：" \
                                                          "只认特征明确的错（别的照抛）、只重试一次并记住端点特性、"
                                                          "降级真发 auto 且不丢 reasoning_effort、留痕不静默；"
                                                          "拿不到 tool_calls 如实抛错不许假装成功",
                 class1=["test_llm_tool_choice_fallback.py"], class2=[]),
        ],
    ),

    dict(
        no=11, key="verify", name="交付即验证",
        goal="两档验证：① 产出物被闸门拦下 -> 带具体原因让 AI 重生成；② 生成脚本后真跑一次 -> 失败带原因整轮重来。"
             "两档都有界（HYBRID_AI_RETRY 默认 2 / 上界 5）、回放同样可带失败原因推进重试轮（缺录像 exit 2 报缺）、"
             "退出码可区分（2 产出侧 / 3 实跑侧）",
        dir="特性11-交付即验证",
        subs=[
            dict(no="11.1", name="验证入口契约（两档重试口径）",
                 goal="`cli verify` 独立入口的契约（能单独重跑，不必再走一遍 explore）；"
                      "两档重试的能力口径：① 产出物被质量闸拦下（写死行数据 / 严重误选 / 必填未编排 / 行定位缺失）"
                      "-> 带原因重生成；② 生成脚本后真跑一次 -> 失败带原因整轮重来。"
                      "两档都有界（HYBRID_AI_RETRY 默认 2 / 上界 5）、回放同样可带失败原因推进重试轮、"
                      "退出码可区分（2 产出侧 / 3 实跑侧）。"
                      "[!] V8.6.3：本特性**只挂物理住在本目录的判据**；"
                      "两档重试的其余判据物理住在 tests/特性2-语义识别与步骤编排/（登记在 2.2），"
                      "按「登记目录 == 物理目录」不在此重复挂。"
                      "[!] V8.6.4：原 `test_retry_is_bounded`（被特性2 严格覆盖）、"
                      "原只查「全文 >= 1 次」的 `test_replay_mode_does_not_retry`（删任一档都不红）已删。"
                      "[!] V8.7.2（契约变更）：回放**不再**一刀切跳过重试 —— 重试会把失败原因写进 prompt，"
                      "下一轮 prompt 就不是「同一份录像」；录像若录了那一轮就该推进（否则「失败→修复」"
                      "永远不可离线复演）。强判据由此改名并改契约："
                      "`test_replay_advances_to_next_round_in_both_retry_paths` 钉「两档各自都允许推进」"
                      "+「分支体不许是 break / exit 3」+「缺录像必须 exit 2 报缺」；"
                      "「白转」防线改由 `_should_retry_again` 有界约束 + 缺录像 fail loud 覆盖",
                 class1=["test_verify_entry_contract.py",
                         "test_verify_observability.py",
                          # V8.7.8（2026-10-27 · 用户问「verify 跑通过以后，还需要 run 一遍吗？
                          #   确认下这个逻辑是否合理」）：查证后确认 `explore --verify` 跑的是
                          #   `done`（本轮新产出，逻辑正确），但 run 又会把本轮那条重跑一遍；
                          #   单场景时这一遍就是整个 run 的时间（实测 ~200s）。同时发现 verify 是
                          #   **逐条串行**（一条一个 pytest 串行等），多场景下 10 条 = 30 分钟纯等待。
                          #   -> A: verify 串行改并发（每条仍独立进程，日志/超时/归因各自独立，
                          #      并发数复用 run 的 safe_workers 不另造一份）；
                          #      B: 新增 `all --skip-verified`（默认关）用 --deselect 跳过本轮已验的；
                          #      全部跳过时 pytest 退出码 5 **不算失败**（否则开关一开就判红）。
                          #   判据同时钉住「取不到脚本必须算失败」——原实现 continue 等于把
                          #   「没验过」当「验过了」；以及「_VERIFIED_OK 绝不落盘」（落盘下次会假绿）。
                          "test_verify_concurrent_and_skip.py"],
                 class2=[]),
            dict(no="11.2", name="实跑档重试（判据住特性2）",
                 goal="实跑档（generate + 逐条实跑）失败 -> 带原因整轮重来；回放同样带失败原因推进（缺录像 exit 2 报缺）；实跑未过 exit 3 —— "
                      "能力口径保留在本条；其判据（test_ai_retry_contract / test_ai_retry_same_cause，"
                      "前者 V8.6.4 第二批由 test_ai_retry_loop 改名 —— 它守的是「上限 / 回炉 / 接线」契约）"
                      "物理住在 tests/特性2-语义识别与步骤编排/，按「登记目录 == 物理目录」登记在 2.2",
                 class1=[], class2=[], status="判据住特性2"),
            dict(no="11.3", name="失败取证（CDP 证据包）",
                 goal="失败时能拿出客观证据而不是一段 AI 的理由：CDP 抓 console / 异常 / network / "
                      "性能指标 / 无障碍树摘要，落成证据包；非 Chromium 系降级为 supported=False + 原因"
                      "（绝不报错、也不假装拿到数据）；事件条数有上限且截断留痕；"
                      "证据包里的敏感头（Authorization / Cookie / Set-Cookie / X-Api-Key 等）必须脱敏"
                      "—— 证据包会被转发，脱敏是交付安全的一部分",
                 class1=["test_failure_evidence_cdp.py"],
                 class2=[]),

            dict(no="11.4", name="试跑超时留现场",
                 goal="试跑超时时**不许只剩一句「真卡住」**：① 把 `TimeoutExpired` 里**本就捕获着**的"
                      "输出带回来，揪出最后一条 `[step N]` 说「停在哪儿」（抓不到就明说卡在用例开始之前）；"
                      "② 杀掉**整棵进程树**（`subprocess.run(timeout=)` 只杀 pytes t，它拉起的 Chromium "
                      "还占着被测服务 -> 会连带让重试轮也超时）；③ 区分「watchdog.txt 有栈」与"
                      "「watchdog 压根没装上」，把这两种归因分开说，别把人往「某一步等不到」带偏",
                 class1=["test_verify_timeout_forensics.py"],
                 class2=[]),

            dict(no="11.5", name="有界等待的每轮成本",
                 goal="「等状态流转」这类有界等待里，**每轮成本必须被限住、慢轮必须自己说出来**："
                      "① 每轮都要做的「重放搜索」走快速窗口（2s），否则慢目标下一次重放吃掉几十秒 "
                      "-> 160s 的业务等待只够轮询 3 轮，业务值一变就卡在临界（第 1 轮红、第 2 轮才绿，"
                      "白烧一轮生成 + 一轮试跑）；② 慢轮逐条打印「轮询第 N 轮花了 X.Xs（读到 …）」，"
                      "别让人从「轮询 3 轮」里猜是业务没流转还是轮询太慢；③ 窗口必须**自己还原**，"
                      "不许把页面默认超时留在小值上污染后续动作",
                 class1=["test_bounded_wait_round_cost.py"],
                 class2=[]),

        ],
    ),
]


def all_subfeatures():
    """展平所有子特性：(特性no, 特性name, 子特性dict, 特性dict)。"""
    for f in FEATURES:
        for s in f.get("subs", []):
            yield f["no"], f["name"], s, f


def owner_index():
    """文件 -> [子特性编号] 的索引（同一文件可服务多个子特性）。"""
    idx = {}
    for _n, _fn, s, _f in all_subfeatures():
        for kind, key in (("class1", "class1"), ("class2", "class2")):
            for fn in s.get(key) or []:
                idx.setdefault(fn, []).append(s["no"])
    return idx

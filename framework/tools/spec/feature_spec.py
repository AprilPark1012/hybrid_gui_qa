"""框架特性规格（单一来源）。

特性 / 子特性 / 用例归属的唯一权威定义。文档由 build_tools/build_feature_map.py 生成，
判据（tests/特性9-质量闸门体系/test_feature_spec_contract.py）校验它与磁盘双向一致。

加特性或子特性：**只改本文件**，然后跑 `python build_tools/build_feature_map.py`。
"""

FEATURES = [
    dict(
        no=1, key="mixed_chain", name="混合链路",
        goal="三种链路（AI 生成 / 手搓 / 离线回放）都能跑通，且有一条统一验收入口",
        dir="特性1-混合链路",
        subs=[
            dict(no="1.1", name="三种链路可切换", goal="AI 生成链路、手搓用例链路、离线回放链路三条路各自可独立跑通",
                 class1=["test_acceptance_entry.py", "test_offline_chain_python.py"],
                 class2=["verify_e2e_scenario1_online.py", "verify_e2e_scenario2_handwritten.py"]),
            dict(no="1.2", name="统一验收入口", goal="四条验收原则能用一条命令跑完；跳过策略（如 --skip-ai）必须显式留痕，不许静默少跑",
                 class1=["test_acceptance_entry.py", "test_acceptance_skip_policy.py"],
                 class2=[]),
            dict(no="1.3", name="交付两件套", goal="无外网机器靠「代码包 + LLM 录像包」即可跑 AI 链路",
                 class1=["test_render_entrypoint.py"],
                 class2=["verify_offline_delivery.py"]),
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
            dict(no="2.2", name="自然语言步骤编排", goal="场景 yml 的自然语言 → 步骤序列；步骤能直接声明定位方式（by+value）而不依赖探测清单",
                 class1=["test_step_direct_locator.py", "test_ai_scenario_preconditions.py", "test_ai_retry_loop.py", "test_ai_incomplete_output_retries.py", "test_ai_retry_same_cause.py", "test_ai_no_hardcoded_row_values.py",
                          "test_semantic_mismatch_blocks.py", "test_llm_tool_choice_unsupported.py", "test_production_defects_gate_l1.py", "test_ai_can_express_row_checkbox.py"],
                 class2=["verify_role_switch_click.py"]),
            dict(no="2.3", name="步骤到定位的合成", goal="步骤里的语义名/属性如何合成可执行定位表达式",
                 class1=["test_scope_locate_expr.py", "test_locate_by_title.py"],
                 class2=["verify_scope_locate.py"]),
            dict(no="2.4", name="场景声明契约", goal="人写的那部分：pages / pre / auth / data / probe_url —— 声明必须由场景提供，框架不懂具体系统",
                 class1=["test_scenario_auth_spec.py", "test_page_pre_actions.py",
                         "test_probe_url_and_occurrence.py", "test_login_priming_coverage.py"],
                 class2=["verify_login_priming.py", "verify_page_pre_actions.py"]),
        ],
    ),

    dict(
        no=3, key="locate", name="分层定位与控件识别",
        goal="在生产系统的复杂页面上仍能唯一定位到目标控件 —— 面向执行",
        dir="特性3-分层定位与控件识别",
        subs=[
            dict(no="3.1", name="顶层锚点加容器内下钻", goal="真实系统只有顶层元素有 testid；子元素靠「锚点 + 容器内相对语义路径」定位",
                 class1=["test_element_anchor_path.py", "test_row_fields_cover_all_columns.py", "test_row_columns_are_named_items.py"],
                 class2=["verify_scope_locate.py"]),
            dict(no="3.2", name="多层嵌套容器", goal="容器套容器（区域内表格、表单里分组）时路径仍能唯一",
                 class1=["test_element_anchor_path.py"],
                 class2=[]),
            dict(no="3.3", name="弹出层与可展开容器", goal="藏在 display:none 菜单里、或点开才出现的弹层控件能被探到并用起来",
                 class1=["test_expandable_menu_discovery.py", "test_probe_single_entry.py",
                         "test_probe_page_scope.py", "test_probe_incremental.py"],
                 class2=["verify_expandable_menu.py", "verify_probe_path_parity.py"]),
            dict(no="3.4", name="跨页面元素", goal="多页面场景下元素跨页可用；同名元素改 `原名@页名` 消歧",
                 class1=[],
                 class2=["verify_cross_page.py"]),
            dict(no="3.5", name="属性直定位", goal="探测清单兜不住时，用属性（by+value）直接定位；select 的 index 语义 = 第 N 个非空选项（跳过 placeholder）",
                 class1=["test_select_by_index.py", "test_select_without_value.py", "test_text_assert_prefers_visible.py"],
                 class2=["verify_select_index_skips_placeholder.py"]),
            dict(no="3.6", name="iframe 内控件", goal="[!] 未实现（缺口）：iframe 内以及跨 iframe 的控件识别与操作",
                 class1=[], class2=[], status="未实现"),
            dict(no="3.7", name="行内单元格定位", goal="行锚 + 单元格：列的指定方式（多列 by）与支持的 op（不只 click）",
                 class1=["test_row_cell_col_by.py", "test_row_cell_ops.py"],
                 class2=[]),
        ],
    ),

    dict(
        no=4, key="ambiguity", name="选错控件兜底",
        goal="同名/同区域控件不许被选错；选不准就大声失败，绝不静默点到错的",
        dir="特性4-选错控件兜底",
        subs=[
            dict(no="4.1", name="同名歧义闸门", goal="同名控件各有唯一名字（后缀消歧）并留痕；用例引用裸名会被质量闸拦下（fail loud）",
                 class1=["test_element_ambiguity_gate.py"],
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
                 class1=["test_data_expand.py", "test_waiting_semantics_maps_to_wait_text.py"],
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
        goal="定位失败时能自动修复并留痕（当前无判据，属规划中）",
        dir="特性6-自愈闭环Healer",
        status="规划中（零判据）",
        subs=[
            dict(no="6.1", name="失败自愈", goal="[!] 待定：主定位失败时尝试候选并记录自愈过程",
                 class1=[], class2=[], status="规划中"),
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
                 class1=["test_cassette_strict_policy.py", "test_cassette_key_stability.py", "test_cassette_fuzzy_fallback.py"], class2=[]),
            dict(no="8.2", name="录像体检", goal="场景段抠取 + 覆盖判定；缺录像要能报出来",
                 class1=["test_check_cassettes_block.py"], class2=[]),
            dict(no="8.3", name="录制与回放契约", goal="录像能录、能放、放得对（不联网、不要 key）",
                 class1=["test_llm_cassette.py"],
                 class2=["verify_e2e_scenario3_cassette.py", "verify_e2e_scenario3_replay.py"]),
            dict(no="8.4", name="LLM 抖动重试", goal="LLM 偶发失败要退避重试，不许把抖动当失败",
                 class1=["test_llm_retry.py"], class2=["verify_offline_chain_deps.py"]),
        ],
    ),

    dict(
        no=9, key="gate", name="质量闸门体系",
        goal="框架自己守自己：布局/命名/环境/交付/就绪/安全六类契约，坏了就红",
        dir="特性9-质量闸门体系",
        subs=[
            dict(no="9.1", name="布局与命名契约", goal="tests/ 与生成物的布局、路径拼接（跨平台）、命名空间契约",
                 class1=["test_test_layout_contract.py", "test_generated_layout_contract.py",
                         "test_path_join_contract.py", "test_case_scenario_contract.py",
                         "test_click_then_ready_contract.py", "test_assert_kinds_render.py",
                         "test_wait_text_kind.py", "test_demo_testid_policy.py"],
                 class2=[]),
            dict(no="9.2", name="质量闸", goal="用例质量 / 生成质量 / demo 新鲜度 / AI 用例与场景同步",
                 class1=["test_case_quality_gate.py", "test_generate_quality_gate.py",
                         "test_demo_freshness_gate.py", "test_ai_case_scenario_sync.py",
                         "test_daily_skip_marker.py"],
                 class2=["verify_demo_freshness.py"]),
            dict(no="9.3", name="环境与编码适配", goal="跨平台路径/内存探测/UTF-8 与 cp936 —— 源码不许出现 GBK 编不了的字符",
                 class1=["test_env_adaptation.py", "test_utf8_io.py", "test_browser_preflight.py",
                         "test_no_stale_paths.py"],
                 class2=[]),
            dict(no="9.4", name="交付包与文档同步", goal="打包内容完整（含运行期必需文件）、文档与代码一致、只留一份 README",
                 class1=["test_pack_release.py", "test_pack_release_requires_generated_dir.py",
                         "test_readme_structure.py", "test_docs_sync.py", "test_build_html_hl.py"],
                 class2=["verify_html_sync.py"]),
            dict(no="9.5", name="保留与产物健康", goal="日志/产物保留策略与健康检查",
                 class1=["test_retention_runs.py", "test_artifacts_health.py"],
                 class2=["verify_retention_runs.py"]),
            dict(no="9.6", name="就绪与等待契约", goal="点击后等就绪、等文本刷新策略、选择器生效",
                 class1=["test_ready_and_locate.py", "test_wait_text_refresh_policy.py",
                         "test_wait_text_selector.py", "test_import_targets.py",
                         "test_generated_pytest_discovery.py", "test_case_imports_cover_helpers.py",
                         "test_scenario_case_script_hygiene.py", "test_target_reachability.py"],
                 class2=["verify_wait_text.py"]),
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
            dict(no="10.5", name="推荐路径口径", goal="文档/提示/培训页的主推路径 = AI 链路；手搓用例降级为调试与回归辅助（历史版本记录不改）",
                 class1=["test_ai_first_docs.py", "test_tunables_exposed_as_flags.py"], class2=[]),
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

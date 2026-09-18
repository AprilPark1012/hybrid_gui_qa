# hybrid_gui_qa V7.7 升级说明（2026-09-18）

> 版本号单一来源：`build_html.py` 顶部 `VERSION` / `VERSION_DATE` / `CHANGELOG`
> （`python -m framework.cli --version` 读同一处）。本文件随交付包一起发。
> 上一版：V7.6（跨 tab 端到端 · 行内定位 · 首行断言）。

## 一句话
本版有两条主线：**① 元素歧义闸门** —— 把「名字能对上就用」这条会**静默点错控件**的路堵死（服务「AI 语义准」）；
**② 离线 AI 链路（LLM 录像回放）** —— 让**连不上外网 LLM 的机器**也能跑完 explore → generate → run。

## 一、元素歧义闸门（批次 2）

### 事故形态（本版要根治的东西）
同一个基础名落在**两处**（例：搜索区一枚按钮、新建弹窗里一枚按钮，文案相同），而探测是**分轮**做的
（先探基础页，再点开弹窗探一层）。每一轮各自命名时，只要本轮里这个名字只有一个，它就**独占裸名** ——
于是「裸名归谁」取决于**探测那一刻谁可见**。用例引用裸名，就可能被映射到**另一个**控件上；
实测后果：生成的 locator 指向被弹窗遮挡的那枚按钮 ⇒ `Locator.click` 30 秒超时。

### 复盘出的四条路径（逐条按根因修）
| 编号 | 路径 | 修法 |
|---|---|---|
| R1 | 唯一化在**每轮探测内部**做 ⇒ 两个控件都拿裸名 | 合并多轮结果后**统一重命名**（见 S1） |
| R2 | 合并按 `semantic_name` **字符串**去重，不做 base 名冲突检测 | `_merge_items()` 改为按 test_id 去重 + 合并后重算命名 |
| R3 | 同页唯一化 `pop` 掉命名依据、**不留痕**（跨页那条却有 `original_name`） | 留痕字段 `base_name / ctx_token / name_source / base_conflict`，两套口径统一 |
| R4 | 运行期**包含关系模糊兜底**：命中多个时按 dict 顺序取，零告警 | 候选唯一才接受且写日志；≥2 抛错并列候选；严格开关全禁 |

### 落地（S1 / S2 / S3）
- **S1**：`probe.assign_semantic_names()`（可重复调用、留痕）+ `explorer._merge_items()`
  「先按 test_id 去重 → 再在**合并后的全量清单**上重算命名」⇒ 同名控件不可能被某一轮独占裸名。
  四个调用点同源：`cli probe` / `explorer` 单页 / `explorer` 跨页 / `generator`（单页 + 声明页）。
- **S2**：缺失名若正是某个同名冲突组的 base 名，报错**直接给候选**
  （`UnmappedElementsError.conflicts` + CLI 一段人话：「该名字对应 ≥2 个控件，请改用下列候选之一」）。
- **S3**：生成物 `_item_for()` 的模糊兜底收敛（见上表 R4）；`HYBRID_STRICT_LOCATE=1` 连唯一候选也不兜。

### 验证（都是真跑，可复现）
```
python -m pytest tests/ -q                 # 202 passed（含 tests/test_element_ambiguity_gate.py 15 条）
python tests/verify_element_ambiguity.py   # exit 0：用 tests/fixtures/ambiguous_page.html 造出事故形态
                                           #   旧算法裸名仍在（复现）；新算法裸名消失（fail loud）
python -m framework.cli run --workers 1    # 17 passed / exit 0；运行日志里模糊兜底 0 次触发（零误伤）
```
> `verify_element_ambiguity.py` 有内存闸：本机可用内存 < 550MB 时它会 **SKIP（exit 3）** ——
> **跳过不等于通过**，请在有内存的机器上跑。

## 二、离线 AI 链路（LLM 录像回放）

### 为什么
受管网络的工作电脑连不上 `api.deepseek.com` ⇒ `explore --ai` 必然失败（这是**对的**：框架口径是
「绝不静默用 mock 冒充 AI 产物」）。录像把「prompt → LLM 回答」落盘：有网机器录一次，离线机器回放。

### 怎么用（录像包里的 `offline_explore_chain.py` 一条命令）
```bash
# 0) 把录像包里的 llm_cassettes/ 放到仓库根的 output/ 下；另开窗口起 demo：python -m demo.app
python offline_explore_chain.py --repo . --run
#   依次做：前置体检 → explore --ai --llm-cassette 回放识别 → generate 生成脚本 → run 试跑
#   只跑指定场景：--scenario scenarios/contracts/contracts_search_by_no.yml
```
手动三步等价写法：
```bash
python -m framework.cli explore --ai --scenario-file scenarios/contracts/contracts_search_by_no.yml --llm-cassette
python -m framework.cli generate
python -m framework.cli run --workers 1
```

### 三条铁律（不满足就跑不起来，但报错会告诉你差在哪）
1. **代码必须是含 `--llm-cassette` 的版本**（本版起）。老版本没有这个参数，录像包单独放进去没用。
2. **demo 与场景文件必须与录制时同版本**：回放键包含场景文案、页面清单（含地址与端口）、
   以及每个控件的骨架（`semantic_name / role / name / label / placeholder / test_id / opens_new_tab / page`）。
   ⚠️ 本版就亲自踩过：只改了「唯一化时机」，某个按钮的语义名从 `取消` 变成 `取消@新建合同`，
   45 个控件只差 1 个，结构键整份对不上 ⇒ **改命名逻辑 / demo 页面 / 场景文案后必须重录、重打包**。
3. **数据值不同没关系，结构必须一致**：demo 预置数据随机、`/api/reset` 也会重随机 ⇒ 先试**严格键**、
   再用**结构键**兜底，命中结构键时会**大声告警**（步骤是录制当时针对那批数据做的判断，请核对再用）；
   只认逐字一致时加 `--llm-cassette-strict`（宁可不跑也不含糊）。

### 怎么确认「这次 AI 判断是回放来的」
- CLI 打印 `LLM 模式：离线回放（非实时 AI）`
- 产出用例 json 里带 `llm_source: cassette:<键>`

### 重录（在有外网的机器上）
```bash
python -m framework.cli explore --ai --scenario-file <场景.yml> --llm-record --no-cases --no-verify
python -m framework.cli explore --ai --scenario-dir scenarios/   --llm-record --no-cases --no-verify   # 全部
```

## 三、其他（随本版一起交付）
- 合同页搜索区改为「输入框 + 弹层按钮」，**弹层选中与手工输入两种都支持**（弹层选中=精确命中、
  手工输入=右模糊，既有语义零破坏）；客户/销售员弹层内新增「+ 新建」叠层并回填当前字段。
- 新增测试：`tests/test_element_ambiguity_gate.py`（15 条，含**模板 ⇄ 生成物互锁**）、
  `tests/verify_element_ambiguity.py`、`tests/verify_order_pick_create.py`、`tests/fixtures/ambiguous_page.html`。
- 设计文档：`docs/P8-元素歧义闸门-方案.md`（含根因表、实施进度、验收判据、迁移影响）。
- 归档纪律：回放/AI 产生的用例与数据集一律移入 `output/archived_cases_<日期>/`，用例库基线保持 **17 条**。

## 四、升级到本版时要注意
1. **重跑 `generate`**：命名逻辑改了（合并后统一重命名），生成脚本与 `scripts/conftest.py` 需重新产出；
   有语义名对不上时 `generate` 会**拒绝落产物**（exit 2）并给出候选清单，按提示改用准确名即可。
2. **`--allow-unmapped` 只用于调试**：它放行的产物永不允许进交付。
3. **严格定位开关**：CI 上想要「名字不精确就失败」可设 `HYBRID_STRICT_LOCATE=1`。
4. 依赖与运行方式未变（`uv venv .venv --python 3.11` + `playwright install chromium`）。

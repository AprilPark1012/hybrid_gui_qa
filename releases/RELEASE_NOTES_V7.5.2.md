# hybrid_gui_qa V7.5.2 交付说明（2026-09-16）

> 一句话：**流程收敛版** —— 树内最后一处内部组织缩写已清（复扫 0 命中）、交付包从 `/tmp` 搬进仓库内
> `releases/`（并挡住它不进包）、pre-push 敏感信息闸门的环境依赖修好（不再把环境问题误报成「有残留」）。
> 功能行为与本版无关的改动为零，升级只需替换代码。

---

## 一、本版修了什么（三件，都与"交付流程"有关）

| 编号 | 修复 | 关键点 |
|---|---|---|
| **H1** | **树内脱敏清零** | 删掉 `docs/BACKLOG-下一步优化.md` 里唯一一处内部组织缩写（三个字母的部门代码），改成不含敏感词的描述；复扫 **HEAD tree = 0 命中** |
| **H2** | **交付包落库到仓库内 `releases/`** | `tools/pack_release.py` 的 `--out` **默认从 `/tmp/pkg` 改为 `<仓库>/releases`**。此前交付包是**唯一副本却躺在 `/tmp`**（重启即可能丢）——本版按根因修，不再靠"记得搬" |
| **H3** | **闸门可移植性** | `.git/hooks/pre-push` 原来写死 `python3` 解释器；在 `python3 = 3.6` 的机器上扫描脚本会 `TypeError` ⇒ **闸门把环境问题误报成「有残留」而拦下推送**。现在自动探测 ≥3.7（含 `.venv/bin/python`），都找不到就明确说"本次不拦，请手动跑" |

**H2 的两个硬约束（不守住就会自伤）**：
- `.gitignore` 必须含 `/releases/`：打包脚本按「已跟踪 + 未跟踪但不被忽略」收文件，漏挡会把**发布包套进发布包**；
- `pack_release.py` 的 `EXCLUDE_DIRS` 也必须含 `releases`：防 git 不可用时走**遍历退化路径**又把它收进来。

---

## 二、自测与验证证据（全部本机实测）

| 验证 | 结果 |
|---|---|
| `python -m pytest tests/ -q` | **130 passed** |
| `git ls-files --cached --others --exclude-standard \| grep -c '^releases/'` | **0**（包库不进包） |
| 生成包内 `releases/` 条目数 | **0** |
| `tools/pack_release.py --check <包>` | ✅ 包内产物自检通过 |
| 敏感信息复扫（HEAD tree） | **0 命中** |

---

## 三、验收（3 步）

| 步 | 命令 | 期望 |
|---|---|---|
| 1 | `python -m pytest tests/ -q` | **130 passed** |
| 2 | `python -m framework.cli --version` | `hybrid_gui_qa v7.5.2 (2026-09-16)` |
| 3 | `python tools/pack_release.py` | 输出到**仓库内 `releases/`**（不再 `/tmp/pkg`），并打印包内自检 ✅ + sha256 |

> 包校验：zip 的 `sha256` 以交付消息里打印的为准（`pack_release.py` 每次打包都会打印；包里不写自己的 sha，否则改一次内容 sha 就变）。

---

## 四、已知遗留（如实记档，不假绿）

1. **对象级残留未清**：2 个**已推送**历史里的旧 blob 仍含那处内部组织缩写。`force-push` 不能让远端对象消失 ⇒
   彻底清零需要 **重写历史 + 删仓重建**（或走平台支持请求清除不可达对象）。本版只做到**树级 + 新提交级**干净。
2. **F5 未完成**：`cases/cross_page_detail.json` 的「列表恢复全量 20 行」（`count expect=20`）仍是脆弱断言，
   需要目标在跑 + 真浏览器才能改完并验证 ⇒ 排下一版。
3. **CI 落点未做**：`.github/workflows/ci.yml` 还没落；推 workflow 文件需要 token 带 `workflow` 权限。

---

## 五、改动文件清单

```
build_html.py               VERSION 7.5.2 + CHANGELOG（7.5.1 的 tag 改为「上一版本」）
RELEASE_NOTES_V7.5.2.md     本文件（新增）
README.md                   版本行改 V7.5.2 + 新增本节变更要点
.gitignore                  加 /releases/（交付包库挡在版本控制外）
tools/pack_release.py       --out 默认 → <仓库>/releases；EXCLUDE_DIRS 加 releases
docs/BACKLOG-下一步优化.md  脱敏措辞（唯一树内命中）+ 交付物路径改 releases/…
.git/hooks/pre-push         解释器探测 ≥3.7（hook 不入库，属本机实装）
training.html               build_html.py 重新生成（版本号与 CHANGELOG 同步）
```

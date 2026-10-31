# V8.7.19 发布说明（2026-10-29）

> 上一版：V8.7.18 · 版本号单一来源 = `build_tools/build_html.py:VERSION`

## 一句话

**交付包绝不许带凭据** —— 非 git 目录下 `.env` 会被收进包。

---

## 一、你报的问题

```
FAILED tests/特性9-质量闸门体系/test_pack_release.py::
       test_collect_files_keeps_sources_and_drops_runtime_cruft
       AssertionError: 包里有不该发的内容：['.env']
1 failed, 1377 passed, 6 skipped, 16 warnings in 93.56s
```

**你的操作是标准的**：拿包 → 解压 → 从 `.env.example` 手工建 `.env` → 填 GLM 配置 → 跑测试。

**而判据测的正是「我这台机器打包会收什么」** —— 目录里有了 `.env`，它就报。

---

## 二、根因（两层，缺一不可）

### ① `Path(".env").suffix == ""`

实测：

```python
Path(".env").suffix        # ''      ← 空！隐藏文件没有后缀
Path(".env.local").suffix  # '.local'
Path("a.env").suffix       # '.env'
Path(".env.example").suffix# '.example'
```

而排除清单是：

```python
EXCLUDE_SUFFIX = {".zip", ".tar.gz", ".pyc", ".pyo"}
```

**空串不在里面** → `.env` 一路畅通。

### ② `collect_files()` 有两条分支，行为不同

```python
r = run_capture(["git", "ls-files", "--cached", "--others", "--exclude-standard"])
if r is not None and r.returncode == 0 and r.stdout.strip():
    ...                                  # git 仓库：走这条
else:
    for p in REPO.rglob("*"):            # 非 git：全遍历
        ...
```

| 环境 | 走哪条 | `.env` 结果 |
|---|---|---|
| **git 仓库**（我打包的机器）| `git ls-files --exclude-standard` | `.gitignore` 帮忙排除 → **不进包** ✅ |
| **解压目录（非 git）**（你的机器）| **`rglob("*")` 全遍历** | **会被收集** ❌ |

而 `collect_files()` 的返回值**直接进 zip，没有二次过滤**：

```python
files = collect_files()
with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
    for p in files:
        z.write(p, arcname=f"{tag}/{p.relative_to(REPO).as_posix()}")
```

**所以准确的结论是**：

- **我打给你的包**：**安全**（永远是 `.env.example`）—— 你说的对，我之前说「会被打进包」是说错了
- **你在解压目录里跑 `pack_release.py`**：**你的 `.env`（含 GLM key）会被打成包** ← 这个隐患是真的

**「开发机绿、交付包解压后红」** —— 正好撞在本项目「一类自测必须与 git / 非 git 无关」那条铁律上。

---

## 三、修法

新增 `_is_env_secret()`：

```python
_ENV_ALLOW = {".env.example", ".env.sample", ".env.template", ".env.dist"}

def _is_env_secret(name: str) -> bool:
    n = str(name or "").strip().lower()
    if not n:
        return False
    if n in _ENV_ALLOW:
        return False
    return n == ".env" or n.startswith(".env.") or n.endswith(".env")
```

放在**两条分支汇合后的公共过滤循环**里：

```python
for p in files:
    ...
    if p.suffix in EXCLUDE_SUFFIX or p.name.endswith(".tar.gz"):
        continue
    if _is_env_secret(p.name):
        continue          # 含凭据的 env 文件绝不进包
    out.append(p)
```

**为什么不塞进 `EXCLUDE_SUFFIX`**：后缀匹配对 `.env` 天然失效（suffix 是空串），必须按**文件名**判。

**为什么放汇合处而不是 git 分支里**：放在某一分支里就是「只修半边」，换个环境又漏。

---

## 四、顺带修掉一个诚实性问题

之前的状态：

```
scripts/generated/index.json   →  template_fingerprint = bd376801…（新）
generate 输出                  →  重写 0 · 跳过（无变化）1
```

**也就是说：index 记着新模板指纹，但脚本本体还是旧模板生成的。** 这是我自己改 `generator_generate.py` 后没重跑生成的遗留。

本次 `generate --force` → **`重写 1`**，两者真正一致。

> 补一句口径：`template_fingerprint` 的语义是「**生成这个脚本时用的渲染器指纹**」。
> 它变了就意味着产物过期，必须重写 —— 不能靠改 index 糊过去。

---

## 五、验证

| 手段 | 结果 |
|---|---|
| `test_pack_env_secret_excluded.py` | **16 passed** |
| 反向验证：去掉 env 过滤 | **2 条变红** ✅（`drops_env_in_non_git_branch` + `filter_is_shared_by_both_branches`）|
| 恢复后 | **16 passed** |

判据覆盖 5 件事：

1. `.env` / `.env.local` / `.env.production` / `a.env` / `.ENV` **都判为凭据**
2. `.env.example` / `.env.sample` / `.env.template` / `.env.dist` **必须放行**（模板要随包交付）
3. **非 git 分支**（`rglob`）下 `.env` 不许进包 —— **用 `tmp_path` 模拟你的场景**
4. 过滤必须在**两分支汇合处**（静态钉住，防只修半边）
5. 端到端：最近打出的 zip 里不许有 `.env`

> 写判据时踩了一次：只 `monkeypatch(REPO)` 不够，因为 `CASSETTE_SRC` 是**模块级常量**，
> 指向真仓库的 `output/llm_cassettes/`，函数末尾 `out.extend(CASSETTE_SRC.rglob(...))`
> 会把真路径塞进来，随后 `relative_to(tmp_path)` 抛 `ValueError`。两个常量都得 patch。

---

## 六、怎么验

```powershell
# 1) 你机器上（解压目录有你自己建的 .env）
.venv\Scripts\python -m pytest tests\特性9-质量闸门体系\test_pack_env_secret_excluded.py -v
# 预期 16 passed

# 2) 全量
.venv\Scripts\python -m pytest tests\ -q
# 预期 0 failed

# 3) 想确认打包不会再带 .env
.venv\Scripts\python -c "from build_tools import pack_release as pr; print([p.name for p in pr.collect_files() if 'env' in p.name])"
# 预期只看到 .env.example
```

---

## 七、提交状态

V8.7.14 ~ 19 全部等你验完点头再提交，push 一律等你点头。

—— AprilPark1012

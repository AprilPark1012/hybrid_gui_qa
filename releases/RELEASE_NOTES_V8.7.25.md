# V8.7.25 发布说明（2026-10-30）

> 上一版：V8.7.24 · 版本号单一来源 = `build_tools/build_html.py:VERSION`

## 一句话

**PASSED 之后揪出的新 bug** —— 登录步骤的 `goto` 拿元素对象当 URL。

---

## 一、先说好消息：V8.7.24 的修复真生效了

你那次 `all --ai` **PASSED**。我逐条核了三个点：

| 检查项 | 结果 |
|---|---|
| 第 60 步 `expect_first_row` 用的是哪个列 | **「订单编号」= `fromOrder`，发票列表页真实存在的列** ✅ |
| 跨页列警告条数 | **0 条** ✅（AI 一次就写对了） |
| 行容器提示 | 恢复正常，没有 V8.7.18 那种 53 条刷屏 |

**跨页串用问题解决。** V8.7.24 的两道闸门（提示词按页分组 + 按页校验）都起了作用。

---

## 二、但日志里有个被 PASSED 掩盖的真 bug

**第 18 行和第 196 行**（两轮都有）：

```
[explore] [key] 登录前置：[!] 失败
-> Error: Page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
Call log:
  - navigating to "ElementRef(semantic_name='账号', role='textbox', name='账号',
     label=None, placeholder='请输入账号', test_id='', element_id=None, text='账号', ...)"
```

**`Page.goto` 收到的"URL"是一个 `ElementRef` 对象的完整 repr。**

### 真因

`framework/features/f02_semantic/login_flow_explore.py` 的 `run_login_steps`：

```python
if op == "goto":
    target = str(st.value or st.element or "").strip()   # <-- 这行
    page.goto(target, wait_until="domcontentloaded")
```

`value`（URL）为空、`element` 有值时，`str(ElementRef对象)` 就成了"URL"。

### 为什么比普通 bug 更糟

它**看起来像兜底**（"没给 URL 就用 element 呗"），实际是**静默降级**：

- 真正该做的是 **报「goto 没有地址」让 AI 重生成**
- 而不是拿一个语义对象去顶 URL 位置

结果：登录前置整条中断，但错误信息是 **`Cannot navigate to invalid URL`** —— 看不出是"AI 把 goto 和 click 写混了"。

---

## 三、修法

```python
if op == "goto":
    target = str(getattr(st, "value", "") or "").strip()
    if not target:
        _el = getattr(st, "element", None) or {}
        _elname = (_el.get("semantic_name") if isinstance(_el, dict)
                   else getattr(_el, "semantic_name", None))
        raise RuntimeError(
            f"登录第 {st.order} 步 goto 没有地址（value 为空"
            + (f"；该步还带了元素 {_elname!r}，可能是把 goto 和 click 写混了" if _elname else "")
            + "）—— element 不能当 URL 用"
        )
    page.goto(target, wait_until="domcontentloaded")
```

**报错信息直接说清三件事**：哪一步、为什么、以及「可能是写混了」。

### 顺带核了对侧

`generator_generate.py` 那边是：

```python
page.goto(str(st.get("value") or login_url), ...)     # 用 login_url 兜底，安全
```

**安全**，但两侧口径不统一。判据里一并钉住了。

### 全仓扫描

`str(st.value or st.element)` 这种把语义对象当 URL 的兜底，**全仓只有这一处**（已修）。

---

## 四、验证

| 手段 | 结果 |
|---|---|
| `test_login_goto_never_uses_element.py`（新，5 条） | **5 passed** |
| 反向验证：退回 `str(st.value or st.element or "")` | **3 条变红**（`goto_without_value_raises` / `goto_error_hints_mixed_op` / `no_element_as_url_fallback_anywhere`） |
| 恢复后 | **5 passed** |
| GBK 闸门 | **21 passed** |

### 判据覆盖的五件事

1. `goto` 的 value 为空 → **必须抛错**，且**不许真的调 `page.goto`**
2. 该步还带 element 时，错误里要提示「可能把 goto 和 click 写混了」+ 指出元素名
3. 正常 goto（value 有值）**不许被误拦**
4. 全仓不许再有 `value or ... element` 这类兜底（**扫描时排除注释行**——我注释里记的教训不算违规）
5. generate 侧兜底必须是 `login_url`

### 写判据时我自己踩的坑

- 第一版传 `element={"semantic_name": ...}`（dict）给 `TestStep`，而 `to_dict()` 会对 element 调 `.to_dict()` → **判据自己炸 `AttributeError`**。改用真实 `ElementRef` 对象。
- 第④条静态扫描**把我自己写的注释也扫进去了**（注释里记着那个坏模式的原文）→ 改成只看 `#` 之前的代码部分。

---

## 五、日志里另外两个现象（核过了，不是 bug）

### ① `有 40 个操作步骤没有绑定元素（element 为空）`

第 1 轮的质量警告。**这是 L1 机制正常工作**：AI 第一轮产出不完整 → 被质量闸拦下 → 带原因重生成 → 第 2 轮修好。

日志第 193 行写得很清楚：

```
[explore] -> [L1 实跑档] 带**实跑失败原因**让 AI 重新生成（L1 第 2/3 轮 · 累计第 1 次重试）
```

### ② 登录前置失败后，探测还是探到了全部 8 个页面

**这个我核过代码**：`ensure_logged_in` 失败只**打印警告并继续**（`explorer_explore.py:414`），不中断。

这次之所以没被踢到登录页，是因为 demo 的 `auth.js` 对这个环境不严格。**但这不是可以依赖的行为** —— 换个校验严格的系统就会探到一堆登录页控件，然后 AI"看着规划得挺好、其实什么都没探到"。

**V8.7.25 修好后，登录会真正执行，探测质量才有保证。**

---

## 六、怎么验

```powershell
# 只看这次的
.venv\Scripts\python -m pytest tests\特性2-语义识别与步骤编排\test_login_goto_never_uses_element.py -v
# 预期 5 passed

# 全量
.venv\Scripts\python -m pytest tests\ -q
```

**真链路**（删四目录 + `.data` → 重启 demo → `all --ai`）：

**关键观察点**：登录前置那行应该是

```
[explore] [key] 登录前置：ok
```

**不再是** `[!] 失败 -> ... Cannot navigate to invalid URL`。

如果还失败，错误信息会变成人能看懂的样子：

```
登录第 1 步 goto 没有地址（value 为空；该步还带了元素 '账号'，可能是把 goto 和 click 写混了）—— element 不能当 URL 用
```

---

## 七、提交状态

V8.7.14 ~ 25 全部等你验完点头再提交，push 一律等你点头。

—— AprilPark1012

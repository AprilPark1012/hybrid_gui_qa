# V8.5.1 发布说明 · 登录步骤化（P23）

发布日期：2026-10-12
上一版：V8.5

---

## 一句话

**登录从"运行期读隐藏文件的隐形前置"变成"场景声明、框架展开、写在用例里的可见步骤"。**

交付包里**不再有任何运行期必需的隐藏文件** —— 包里有什么，跑的就是什么。

---

## 为什么要改（旧机制的致命点）

V8.5 及以前：`generate` 会把场景的 `auth:` 段写进 `scripts/generated/_auth.json`，
生成物的 harness 在 `page` fixture 里读它、把 token 注入 localStorage。

问题在于：**该文件被 `.gitignore` 忽略** ⇒ `pack_release`（走 `git ls-files --exclude-standard`）
**不会把它打进交付包** ⇒ 收包方执行 `run` 时登录前置**静默失效**。

失效的表现极具误导性：报错是「元素语义未找到」，而真因是**整条用例都跑在登录页上**
（V8.3 现场就是这么被带偏的）。而且因为它是"隐形前置"，跑挂了看不出卡在登录这一步。

---

## 新机制

```yaml
# 场景里声明（这是唯一权威）
login:
  url: /login.html
  steps:
    - {op: fill,  by: {id: login-user}, value: super}
    - {op: fill,  by: {id: login-pwd},  value: super@123}
    - {op: click, by: {id: btn-login}}
  wait: {url_not: login.html}        # 可观测成功条件，不许固定 sleep
```

执行 `generate` 时，框架把这套动作**展开成用例的前导步骤**：

```python
_goto(page, 'http://localhost:8000/login.html')
# ---- 登录（V8.5.1 步骤化：场景声明 -> 框架展开，不交给 AI）----
_login_do(page, 'fill', {'id': 'login-user'}, value='super')
_login_do(page, 'fill', {'id': 'login-pwd'}, value='super@123')
_login_do(page, 'click', {'id': 'btn-login'})
_login_wait(page, {'url_not': 'login.html'})
```

### 四条设计口径

| 口径 | 理由 |
|---|---|
| **不交给 AI 生成** | 历史上 AI 自造过 4 步手工登录，还把用户名当密码填过。登录是确定性的，声明一次、框架展开更可靠 |
| **动作展开进用例（可见）** | 跑挂了能直接看到"卡在登录"，排查方向不会被带偏 |
| **框架层零业务词** | 框架不认识"账号/密码"，只认"声明了一个 `by` 表达式 + 一个动作"。登录页重构只改场景 |
| **成功判定必须可观测** | `url` / `url_not` / `selector` / `text` 四选一；空 `wait` 或缺条件**生成期就报错**，不许固定 sleep |

口令口径：demo 明文（公开演示凭据）；真实系统写 `{{env:NAME}}`，生成物只留引用、**值不落盘**。

---

## 删掉的东西（四处一起删，不留"两条路"）

1. `generator` 里 `_auth.json` 的**写入**
2. harness 模板里 `_AUTH_TABLE` 的读取
3. `_install_login()` 及其调用点
4. `.gitignore` 里 `scripts/generated/_auth.json` 那条

配套：`releases` 打包的出厂闸门会检查"运行期读到的文件集合 ⊆ 打包清单"。

---

## 判据（先落红态，再实现，最后转绿）

新增 `tests/特性2-语义识别与步骤编排/test_login_stepwise_contract.py`（J1~J6）：

| 判据 | 守什么 |
|---|---|
| J1 | 声明了登录 ⇒ 生成脚本里出现前导步骤，顺序 goto→fill→fill→click→wait |
| J2 | **负向**：没声明 ⇒ **零**前导步骤（向后兼容，用**行为**验证而不是查字面串） |
| J3 | **负向**：声明不全（缺 steps / op 不认识 / fill 缺 value / wait 不可观测 / 步骤缺 by）⇒ **生成期大声报错** |
| J4 | 出厂闸门：运行期要读的文件必须在打包清单里（防"不入包却运行必需"复发） |
| J5 | 机制移除守门：全仓无 `_auth.json` 读写、`.gitignore` 无该条 |
| J6 | 卡在登录页时，报错必须直说「当前在登录页 —— 登录步骤未执行/失败」 |

实测：5 类负例**全部如实报错，漏报 0**。

---

## 验证

| 项 | 结果 |
|---|---|
| 全量判据 | 1114+ passed / 0 failed（见交接记录的真值） |
| **真跑** | 2 passed · pytest 退出码 0 |
| **登录真的执行了**（不是"看着绿"） | 运行日志出现 `[TEST] login_step: fill ['id']` ×2 |
| 产物 | `scripts/generated/_auth.json` **不再生成** |

⚠️ **本轮排故的一个关键发现**：第一次真跑"通过"其实是**不可信的** ——
生成脚本里一行登录步骤都没有，仅仅因为 demo 未登录也能操作。
若只看"绿了"就收工，这版就是"看着做了、其实没生效"。**结论必须有真值支撑。**

---

## 未完成（如实标注）

- **探针侧**（`explore` / `generate` 的现场探测）当前**仍走** `framework/shared/login.py` 里的
  接口登录（`login_token` / `install_token` / `ensure_logged_in`）。**运行期的隐藏依赖已彻底清除**
  （这是本次要根治的），但"探测期与执行期共用同一份 `perform_login`"是下一小步，尚未完成。
- 因此 `test_login_priming_coverage.py` 里 **(1)(2)(3) 三条探针路径判据保留**，(4) 执行侧判据已按新口径改写。

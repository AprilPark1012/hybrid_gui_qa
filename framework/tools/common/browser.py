"""Chromium 启动参数【唯一事实来源】—— 稳定性 / 一致性 / 低内存环境适配。

为什么需要这个文件
------------------
本机实测（2026-09-11，多轮重复）：
  - 1 个 headless Chromium 实例（playwright driver + chromium 全树）**≈ 515 MB / 7 进程**
    （单次最低读到 383MB，最高 516MB ⇒ RSS 含可共享的 file-backed 映射，波动大）
  - 机器 MemTotal 1.87 GB、**Swap = 0**、MemAvailable 仅 ~700 MB，Hermes 自身占 ~828 MB
  ⇒ 并发 2 个实例（~1030 MB）必然触发内核 **global OOM**，渲染进程被杀
    （Playwright 报 `Target crashed`），并**连带杀掉 hermes-gateway-<profile>**。

在此之前 8 处裸 `launch()` 各写各的、且全无参数。现统一收敛到本模块。

⚠️ 诚实声明：实测表明本组参数**并不降低 RSS**（裸参与全参数版本同为 513~516MB，
在测量噪声内）。它们解决的是**稳定性与一致性**（禁扩展下载、无 GPU 路径、shm 落盘、
子进程数受限）。**真正的保命机制是 `limits.safe_workers()` 的并发降级**，别把本文件
当成省内存手段。

用法
----
    from framework.tools.common.browser import launch_opts
    browser = p.chromium.launch(**launch_opts(headless=True))

生成物（scripts/conftest.py）不 import 本模块 —— generator.py 会把
CHROMIUM_ARGS **内联**进模板，保证生成物自包含、可单独拷走（见 generator.py）。

可选环境变量
------------
    HYBRID_JS_HEAP_MB=384   限制渲染进程 V8 堆上限（默认**不开**：重业务页压太狠会把 tab 顶崩）
"""
from __future__ import annotations
import os

# 基础参数：稳定性/一致性（**实测不降 RSS**，勿当成省内存手段；真正的保命机制是 worker 降级）
CHROMIUM_ARGS: list[str] = [
    "--disable-dev-shm-usage",              # 共享内存改落 /tmp（本机 /tmp 在 ext4；容器里 /dev/shm 常只有 64MB）
    "--disable-gpu",                        # 无头无需 GPU
    "--disable-extensions",                 # 不加载扩展（browser-use 默认会下扩展卡网）
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-background-networking",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--renderer-process-limit=1",           # 限制子进程数（2 实例曾达 12 进程）
]


def launch_opts(headless: bool = True) -> dict:
    """返回 `p.chromium.launch(**launch_opts(headless=...))` 的参数字典。

    headless=False ⇒ 有头（显示浏览器）—— 由 `cli run --debug`（调试开关，默认关）在"有图形显示"时使用；
    没有图形显示时调试开关改为录制模式（视频 + 逐步截图），仍是 headless=True。
    HYBRID_SLOWMO=<毫秒> ⇒ 每个动作后停一下，方便肉眼看用例一步步走（cli run --slowmo N）。
    """
    args = list(CHROMIUM_ARGS)
    heap = os.environ.get("HYBRID_JS_HEAP_MB")
    if heap and heap.isdigit():
        args.append(f"--js-flags=--max-old-space-size={int(heap)}")
    opts = {"headless": headless, "args": args}
    slow = os.environ.get("HYBRID_SLOWMO")
    if slow and slow.isdigit() and int(slow) > 0:
        opts["slow_mo"] = int(slow)
    return opts


# ============ 浏览器可用性预检（2026-09-23 新增，V8.2.2）============
# 为什么加：实测事故 —— 在新机器（Windows/首次部署）上跑 explore/generate/run 时，
# Playwright 的浏览器**没装**（或装了另一个版本的），三条命令各炸一次，每次都抛原始异常栈：
#     BrowserType.launch: Executable doesn't exist at
#       C:\Users\<user>\AppData\Local\ms-playwright\chromium_headless_shell-1243\chrome-headless-shell-win64\chrome-headless-shell.exe
# 新人看不懂、也搜不到该跑哪条命令 ⇒ 违反「开箱即用 / 提示说人话」的口径。
# 现在：**开跑前先探一次**，缺了就当场给「一行修复命令」，exit 2。
#
# 版本对应的 revision 会变：playwright 1.62.0 ⇒ revision 1234；新版 ⇒ 1243 …
# 所以**不能**把路径写死，靠真实 launch 探（探到的异常里带实际期望路径，直接转述给人）。
def ensure_browser_installed() -> None:
    """跑任何需要浏览器的命令前调用：确认 chromium 能起来，否则抛人话异常。

    跳过（只在已确认浏览器可用时用）：环境变量 `HYBRID_SKIP_BROWSER_CHECK=1`。
    """
    if os.environ.get("HYBRID_SKIP_BROWSER_CHECK") == "1":
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:  # 连 playwright 都没装
        raise BrowserNotInstalledError(
            "❌ 没装 playwright —— 框架需要它才能探测页面 / 跑用例。\n"
            "   一行修好：\n"
            "       pip install -r requirements.txt\n"
            f"   （原始报错：{e}）"
        ) from None
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(**launch_opts(headless=True))
            b.close()
    except Exception as e:  # noqa: BLE001 —— 要把 Playwright 的原话转成人话
        msg = str(e)
        if "Executable doesn't exist" in msg or "playwright install" in msg.lower():
            raise BrowserNotInstalledError(_browser_missing_message(msg)) from None
        raise


class BrowserNotInstalledError(RuntimeError):
    """Playwright 浏览器缺失 / 版本对不上 ⇒ 拒绝硬跑（给一行修复命令后 exit 2）。"""


def _browser_missing_message(raw: str) -> str:
    """把 Playwright 的原始报错，翻成「缺什么 + 装哪条命令」的人话。"""
    path = ""
    for line in raw.splitlines():
        if "Executable doesn't exist" in line:
            path = line.split("at ", 1)[-1].strip().rstrip(";") if "at " in line else line.strip()
            break
    ver = ""
    try:
        import importlib.metadata as md
        ver = md.version("playwright")
    except Exception:  # noqa: BLE001
        pass
    lines = ["❌ 没找到 Playwright 的浏览器（chromium / chromium-headless-shell），框架需要它才能探测页面、跑用例。"]
    if path:
        lines.append(f"   期望位置：{path}")
    if ver:
        lines.append(f"   当前 playwright 版本：{ver}")
    lines += [
        "   一条命令搞定（推荐；会装依赖 + 浏览器，再自检一遍）：",
        "       python -m framework.cli setup",
        "   或只装浏览器：",
        "       python -m playwright install chromium",
        "   说明：这条命令会同时装 chromium 与无头模式用的 chromium-headless-shell；",
        "         若刚升级过 playwright（报错里的 revision 号变了），用 --force 强制重下：",
        "       python -m playwright install --force chromium",
        "   只想补无头壳：",
        "       python -m playwright install chromium-headless-shell",
    ]
    return "\n".join(lines)

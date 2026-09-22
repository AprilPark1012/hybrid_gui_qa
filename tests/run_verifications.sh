#!/usr/bin/env bash
# 特性验证统一入口（R7 两类验证之②）—— **薄包装**：唯一实现在 `tests/run_verifications.py`。
#
# 为什么是包装（2026-09-22 使用者现场反馈）：Windows PowerShell 里**没有 bash**
# （现场报 `无法将“bash”项识别为 cmdlet…`，机器上没装 Git Bash / WSL）⇒ 只有 .sh 的话，
# 二类验证对 Windows 用户等于**不存在**，而本框架的现场恰恰是 Windows。
# 口径：逻辑只留一处（Python 版），本文件只负责转发 —— 避免「改了一处忘了另一处」的静默不一致。
#
# 用法（参数原样透传给 Python 版，含义见它的 --help）：
#   bash tests/run_verifications.sh                 # 全量（需要 demo：脚本会自动起/停）
#   bash tests/run_verifications.sh --list          # 只列出会跑哪些
#   bash tests/run_verifications.sh --only <子串>   # 只跑名字含该子串的
#   bash tests/run_verifications.sh --no-demo       # 不起 demo（只跑自包含的验证）
# Windows / PowerShell 直接用：python tests/run_verifications.py（参数完全一样）
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PY="$REPO/.venv/bin/python"; [ -x "$PY" ] || PY=python3
exec "$PY" "$REPO/tests/run_verifications.py" "$@"

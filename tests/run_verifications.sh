#!/usr/bin/env bash
# 特性验证统一入口（R7 两类验证之②）—— 逐个跑 tests/verify_*.py，汇总结果。
#
# 用法：
#   bash tests/run_verifications.sh                # 全量（需要 demo：脚本会自动起/停）
#   bash tests/run_verifications.sh --only ambiguity   # 只跑名字含该子串的
#   bash tests/run_verifications.sh --no-demo      # 不起 demo（只跑自包含的验证）
#   bash tests/run_verifications.sh --list         # 只列出会跑哪些
#
# 退出码：0 = 全通过（跳过项会如实列出）· 1 = 有失败 · 3 = 内存不足整体 SKIP（不算通过）
# ⭐ 口径：SKIP 不是绿灯 —— 内存不够时如实报 exit 3，绝不假装通过。
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO" || exit 2
PY="$REPO/.venv/bin/python"; [ -x "$PY" ] || PY=python3
MIN_MEM="${VERIFY_MIN_MEM_MB:-550}"
BASE="${HYBRID_BASE_URL:-http://127.0.0.1:8000}"

ONLY=""; USE_DEMO=1; LIST_ONLY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --only) ONLY="${2:-}"; shift 2 ;;
    --no-demo) USE_DEMO=0; shift ;;
    --list) LIST_ONLY=1; shift ;;
    *) echo "未知参数: $1（见脚本头部用法）"; exit 2 ;;
  esac
done

mem_mb=$(awk '/MemAvailable/{printf "%d", $2/1024}' /proc/meminfo)
mapfile -t SCRIPTS < <(ls tests/verify_*.py 2>/dev/null | sort)
[ -n "$ONLY" ] && mapfile -t SCRIPTS < <(printf '%s\n' "${SCRIPTS[@]}" | grep -- "$ONLY")

echo "================================================================"
echo " 特性验证统一入口 · $(TZ='Asia/Shanghai' date '+%F %H:%M:%S')"
echo " 仓库: $REPO"
echo " 内存: MemAvailable ${mem_mb}MB（阈值 ${MIN_MEM}MB）"
echo " 将跑: ${#SCRIPTS[@]} 个 verify 脚本${ONLY:+（过滤: $ONLY）}"
echo "================================================================"
[ "$LIST_ONLY" -eq 1 ] && { printf '  %s\n' "${SCRIPTS[@]}"; exit 0; }

if [ "$mem_mb" -lt "$MIN_MEM" ]; then
  echo "⏭️  SKIP：MemAvailable ${mem_mb}MB < ${MIN_MEM}MB —— 内存不足，跳过全部验证（exit 3，不是通过）"
  echo "    腾内存后可重跑：pkill -f \"[p]yright\"；或调低阈值 VERIFY_MIN_MEM_MB=<n>"
  exit 3
fi

# --- demo 新鲜度闸门（R7 前置）--------------------------------------------------
# 为什么必须先过这道：demo 是**常驻进程**，下面的分支会「已在跑就复用」。
# 若改过 demo/app.py 或 demo/*.html 却没重启 ⇒ 后面所有端到端验证都跑在**旧页面**上：
# 用例白跑，而且给出的还是「看起来通过/失败」的结论（2026-09-21 反馈）。
# 口径：不新鲜 ⇒ 自动重启并等到就绪；重启后仍不新鲜 ⇒ 直接停手（exit 2），绝不在旧版本上继续跑。
if [ "$USE_DEMO" -eq 1 ] && [ "$LIST_ONLY" -eq 0 ]; then
  echo "· demo 新鲜度闸门（改了 demo 就必须重启，否则验证白跑）…"
  "$PY" tests/demo_freshness.py --ensure --start-if-missing
  frc=$?
  case "$frc" in
    0) : ;;
    *) echo "❌ demo 新鲜度闸门未过（exit $frc）⇒ 停手：不在旧版本 demo 上跑验证"; exit 2 ;;
  esac
fi

# --- demo 就绪 ---
DEMO_PID=""
demo_up() { "$PY" - "$BASE" <<'PYEOF' 2>/dev/null
import sys, urllib.request
try:
    urllib.request.urlopen(sys.argv[1].rstrip('/') + "/api/health", timeout=3)
    sys.exit(0)
except Exception:
    sys.exit(1)
PYEOF
}
if [ "$USE_DEMO" -eq 1 ]; then
  if demo_up; then
    echo "· demo 已在跑（复用，跑完不关；新鲜度已由上面的闸门保证）"
  else
    echo "· 启动 demo（$BASE）…"
    ( "$PY" -m demo.app >/tmp/run_verifications_demo.log 2>&1 & echo $! > /tmp/run_verifications_demo.pid )
    DEMO_PID="$(cat /tmp/run_verifications_demo.pid 2>/dev/null)"
    for _ in $(seq 1 20); do sleep 1; demo_up && break; done
    demo_up || { echo "❌ demo 起不来（见 /tmp/run_verifications_demo.log）"; [ -n "$DEMO_PID" ] && kill "$DEMO_PID" 2>/dev/null; exit 2; }
    echo "· demo 就绪（pid $DEMO_PID）"
  fi
fi

# --- 逐个跑 ---
declare -a NAMES CODES
fail=0; skip=0; ok=0
for s in "${SCRIPTS[@]}"; do
  name="$(basename "$s")"
  printf '\n———— %s ————\n' "$name"
  start=$SECONDS
  timeout 600 "$PY" "$s" 2>&1 | tail -12
  rc=${PIPESTATUS[0]}
  dur=$((SECONDS - start))
  NAMES+=("$name"); CODES+=("$rc")
  case "$rc" in
    0) ok=$((ok+1));   echo "  ✅ exit 0（${dur}s）" ;;
    3) skip=$((skip+1)); echo "  ⏭️  exit 3 跳过（${dur}s）—— 不是通过" ;;
    *) fail=$((fail+1)); echo "  ❌ exit $rc（${dur}s）" ;;
  esac
done

# --- 收尾 ---
[ -n "$DEMO_PID" ] && { kill "$DEMO_PID" 2>/dev/null; rm -f /tmp/run_verifications_demo.pid; echo -e "\n· 已停自起的 demo"; }

echo
echo "================================================================"
printf ' 汇总（通过 %d · 跳过 %d · 失败 %d）\n' "$ok" "$skip" "$fail"
for i in "${!NAMES[@]}"; do printf '   %-40s exit %s\n' "${NAMES[$i]}" "${CODES[$i]}"; done
echo "=================================================================="
if [ "$fail" -gt 0 ]; then echo "❌ 有失败 —— 先修再提交（R7）"; exit 1; fi
[ "$skip" -gt 0 ] && echo "⚠️ 有跳过项（不是通过）：$skip 个" 
echo "✅ 特性验证全通过"
exit 0

#!/bin/sh
# 供 post-merge / post-commit / post-rewrite 调用：重建生成物（状态 / 需求索引 / 审计视图）。
# 铁律：**任何失败都不能阻塞 git** —— 汇总挂了顶多视图过期，合并必须继续。
[ -n "$AIDLC_SUMMARY" ] && exit 0

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
HERE="$(cd "$(dirname "$0")" && pwd)"
SUM=""
for cand in "$HERE/../汇总.py" "$ROOT/开发文档/工具/汇总.py" "$ROOT/scripts/汇总.py"; do
  [ -f "$cand" ] && { SUM="$cand"; break; }
done
[ -z "$SUM" ] && { echo "[aidlc] 找不到汇总脚本，跳过（视图可能过期）"; exit 0; }

# 找 python：先 PATH（通用），再各 IDE 自带的内置解释器（WorkBuddy / CodeBuddy 是当前已知的）
#
# 两个坑（CR-16102604）：
#   1. 顺序 —— 可用的解释器可能排在后面，不能被前面「存在但不可用」的东西挡住；
#   2. 只验存在不够 —— Windows 上 `python3.exe` / `python.exe` 常是 Microsoft Store 的
#      「应用执行别名」存根，`command -v` 能找到，真执行只会弹安装提示。
# 所以：候选顺序 python → py → python3，且命中后必须实测能启动（`-c ""` 跑通）才算数。
PY="${AIDLC_PYTHON:-}"
if [ -n "$PY" ]; then
  if ! "$PY" -c "" >/dev/null 2>&1; then
    echo "[aidlc] AIDLC_PYTHON 指向的解释器不可用：$PY，改为自动探测"
    PY=""
  fi
fi
if [ -z "$PY" ]; then
  for c in python py python3; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c "" >/dev/null 2>&1; then PY="$c"; break; fi
  done
fi
if [ -z "$PY" ]; then
  for p in \
    "$HOME"/.workbuddy/binaries/python/versions/*/python.exe \
    "$HOME"/.codebuddy/binaries/python/versions/*/python.exe \
    /usr/bin/python3 /usr/local/bin/python3; do
    [ -x "$p" ] && { PY="$p"; break; }
  done
fi
if [ -z "$PY" ]; then
  echo "[aidlc] 没找到 python，跳过汇总；文档视图可能过期（手动：python scripts/汇总.py）"
  exit 0
fi

AIDLC_SUMMARY=1 "$PY" "$SUM" \
  || echo "[aidlc] 汇总失败（已忽略，不阻塞 git）；手动重试：python scripts/汇总.py"

# 若项目在 `00规则/团队配置.md` 里声明了「构建命令」，合并后一并执行。
#
# 为什么不写死具体构建器：AIDLC 适用于前端 / 后端 / CLI / 纯文档等各种项目，
# 构建方式从 `npm run build` 到 `cargo build` 到根本没有构建，技能不该猜。
# 原则：**项目声明什么就执行什么，没声明就跳过**。
CONF="$ROOT/开发文档/00规则/团队配置.md"
if [ -f "$CONF" ]; then
  BUILD_CMD="$(sed -n 's/^- 构建命令[：:][[:space:]]*//p' "$CONF" | head -1)"
  if [ -n "$BUILD_CMD" ]; then
    ( cd "$ROOT" && sh -c "$BUILD_CMD" ) >/dev/null 2>&1 \
      || echo "[aidlc] 构建命令失败（已忽略，不阻塞 git）：$BUILD_CMD"
  fi
fi
exit 0

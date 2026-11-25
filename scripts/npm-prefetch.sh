#!/usr/bin/env sh
# 有网时把 web/ 依赖预取到本机 npm cache；之后可断网执行 npm ci --offline。
# 用法：sh scripts/npm-prefetch.sh [cache-dir]
# 仓库不内置 vendor/npm tgz；离线安装依赖这台机器事先完成过预取。
set -eu

repo="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
web="$repo/web"

if ! command -v npm >/dev/null 2>&1; then
  echo "slc: 找不到 npm；请先安装 Node 24.x" >&2
  exit 3
fi

if [ ! -f "$web/package-lock.json" ]; then
  echo "slc: 缺少 $web/package-lock.json；先检出 web 依赖清单" >&2
  exit 3
fi

if [ "${1:-}" != "" ]; then
  npm_config_cache="$1"
  export npm_config_cache
fi

if ! (cd "$web" && npm ci --no-audit --no-fund); then
  echo "slc: npm ci 预取失败；检查网络后重试" >&2
  exit 3
fi

echo "slc: 依赖已预取到 npm cache（${npm_config_cache:-$(npm config get cache)}）"
echo "slc: 断网后可在 web/ 执行 npm ci --offline"

#!/usr/bin/env sh
# 从 vendor/npm/*.tgz 填充本机 npm cache。不联网，不安装依赖。
# 用法：sh scripts/npm-offline.sh
# 之后在 web/ 下执行：npm ci --offline（P3 起 web/package.json 存在时）。
set -eu

repo="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
vendor="$repo/vendor/npm"

if ! command -v npm >/dev/null 2>&1; then
  echo "rvgen: 找不到 npm；请先安装 Node 24.x" >&2
  exit 3
fi

if [ ! -d "$vendor" ]; then
  echo "rvgen: 缺少 $vendor；离线包尚未生成" >&2
  exit 3
fi

count=0
for tgz in "$vendor"/*.tgz; do
  [ -e "$tgz" ] || continue
  npm cache add "$tgz"
  count=$((count + 1))
done

if [ "$count" -eq 0 ]; then
  echo "rvgen: vendor/npm 为空；P0 无 web/package.json，离线 npm 包留待 P3 生成"
  exit 0
fi

echo "rvgen: 已向 npm cache 注入 $count 个 tgz"

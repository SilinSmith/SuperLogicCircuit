#!/usr/bin/env sh
# 把 scripts/hooks/* 安装到当前仓库的 .git/hooks（不覆盖已存在的非 rvgen hook）。
set -eu

repo="$(git rev-parse --show-toplevel)"
src="$repo/scripts/hooks"
dst="$(git rev-parse --git-dir)/hooks"
mkdir -p "$dst"

for hook in post-commit post-checkout; do
  cp "$src/$hook" "$dst/$hook"
  chmod +x "$dst/$hook"
  echo "installed $dst/$hook"
done

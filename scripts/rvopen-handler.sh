#!/bin/sh
# rvgen:// 的 macOS/Linux 处理器：解析 file/line，优先用 VS Code 打开。
set -eu

url="${1:?用法: rvopen-handler.sh 'rvgen://open?file=rvgen.yaml&line=1'}"
query="${url#*\?}"
file=""
line=""

old_ifs=$IFS
IFS='&'
for pair in $query; do
  key="${pair%%=*}"
  value="${pair#*=}"
  value="$(python3 -c 'import sys, urllib.parse; print(urllib.parse.unquote(sys.argv[1]))' "$value")"
  case "$key" in
    file) file="$value" ;;
    line) line="$value" ;;
  esac
done
IFS=$old_ifs

if [ -z "$file" ]; then
  echo "rvgen:// 缺少 file 参数：$url" >&2
  exit 1
fi

target="$file"
[ -n "$line" ] && target="$file:$line"

if command -v code >/dev/null 2>&1; then
  exec code --goto "$target"
fi

if command -v open >/dev/null 2>&1; then
  exec open "$file"
fi

if command -v xdg-open >/dev/null 2>&1; then
  exec xdg-open "$file"
fi

echo "未找到 code/open/xdg-open；请手动打开：$target" >&2
exit 1

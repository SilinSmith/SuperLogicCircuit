#!/bin/sh
# 在 macOS 上注册 rvgen://（生成 ~/Applications/rvgen-open.app 并刷新 LaunchServices）。
# 未在 macOS 实机验证；注册后用 `open 'rvgen://open?file=rvgen.yaml&line=1'` 测试。
set -eu

here="$(cd "$(dirname "$0")" && pwd)"
handler="$here/rvopen-handler.sh"
chmod +x "$handler"
app="$HOME/Applications/rvgen-open.app"

mkdir -p "$HOME/Applications"
rm -rf "$app"
osacompile -o "$app" \
  -e "on open location theURL" \
  -e "do shell script quoted form of \"$handler\" & \" \" & quoted form of theURL" \
  -e "end open location"

plutil -replace CFBundleURLTypes -json \
  '[{"CFBundleURLName":"rvgen","CFBundleURLSchemes":["rvgen"]}]' \
  "$app/Contents/Info.plist"

/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$app"

echo "已注册 rvgen:// → $app"
echo "测试：open 'rvgen://open?file=rvgen.yaml&line=1'"

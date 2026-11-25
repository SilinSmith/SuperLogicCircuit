#!/bin/sh
# 在 macOS 上注册 slc://（生成 ~/Applications/slc-open.app 并刷新 LaunchServices）。
# 未在 macOS 实机验证；注册后用 `open 'slc://open?file=slc.yaml&line=1'` 测试。
set -eu

here="$(cd "$(dirname "$0")" && pwd)"
handler="$here/rvopen-handler.sh"
chmod +x "$handler"
app="$HOME/Applications/slc-open.app"

mkdir -p "$HOME/Applications"
rm -rf "$app"
osacompile -o "$app" \
  -e "on open location theURL" \
  -e "do shell script quoted form of \"$handler\" & \" \" & quoted form of theURL" \
  -e "end open location"

plutil -replace CFBundleURLTypes -json \
  '[{"CFBundleURLName":"slc","CFBundleURLSchemes":["slc"]}]' \
  "$app/Contents/Info.plist"

/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$app"

echo "已注册 slc:// → $app"
echo "测试：open 'slc://open?file=slc.yaml&line=1'"

#!/bin/sh
# 在 Linux 桌面注册 slc://（写入 ~/.local/share/applications 并设为默认）。
set -eu

here="$(cd "$(dirname "$0")" && pwd)"
handler="$here/rvopen-handler.sh"
chmod +x "$handler"

desktop="$HOME/.local/share/applications/slc-url.desktop"
mkdir -p "$(dirname "$desktop")"

cat > "$desktop" <<EOF
[Desktop Entry]
Type=Application
Name=slc URL Handler
Comment=Open slc:// links in the editor
Exec=sh "$handler" %u
MimeType=x-scheme-handler/slc;
NoDisplay=true
Terminal=false
EOF

update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
xdg-mime default slc-url.desktop x-scheme-handler/slc

echo "已注册 slc:// → $desktop"
echo "测试：xdg-open 'slc://open?file=slc.yaml&line=1'"

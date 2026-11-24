#!/bin/sh
# 在 Linux 桌面注册 rvgen://（写入 ~/.local/share/applications 并设为默认）。
set -eu

here="$(cd "$(dirname "$0")" && pwd)"
handler="$here/rvopen-handler.sh"
chmod +x "$handler"

desktop="$HOME/.local/share/applications/rvgen-url.desktop"
mkdir -p "$(dirname "$desktop")"

cat > "$desktop" <<EOF
[Desktop Entry]
Type=Application
Name=rvgen URL Handler
Comment=Open rvgen:// links in the editor
Exec=sh "$handler" %u
MimeType=x-scheme-handler/rvgen;
NoDisplay=true
Terminal=false
EOF

update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
xdg-mime default rvgen-url.desktop x-scheme-handler/rvgen

echo "已注册 rvgen:// → $desktop"
echo "测试：xdg-open 'rvgen://open?file=rvgen.yaml&line=1'"

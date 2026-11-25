# slc:// 的 Windows 处理器：解析 file/line，优先用 VS Code 打开。
param([Parameter(Mandatory = $true)][string]$Uri)

$file = $null
$line = $null
if ($Uri -match '^slc://open\?(.*)$') {
  foreach ($pair in $matches[1].Split('&')) {
    if (-not $pair) { continue }
    $kv = $pair.Split('=', 2)
    $key = [uri]::UnescapeDataString($kv[0])
    $value = if ($kv.Length -gt 1) { [uri]::UnescapeDataString($kv[1]) } else { "" }
    if ($key -eq 'file') { $file = $value }
    if ($key -eq 'line') { $line = $value }
  }
}

if (-not $file) {
  Write-Error "slc:// 缺少 file 参数：$Uri"
  exit 1
}

$target = if ($line) { "${file}:$line" } else { $file }
if (Get-Command code -ErrorAction SilentlyContinue) {
  & code --goto $target
  exit $LASTEXITCODE
}

Write-Host "未找到 code；请手动打开：code --goto $target"

# 注册 slc:// 协议到当前用户（HKCU，无需管理员）。
# 用法：
#   powershell -ExecutionPolicy Bypass -File scripts/register-rvopen-windows.ps1
#   powershell -ExecutionPolicy Bypass -File scripts/register-rvopen-windows.ps1 -Uninstall
param([switch]$Uninstall)

$scheme = "slc"
$base = "HKCU:\Software\Classes\$scheme"

if ($Uninstall) {
  if (Test-Path $base) { Remove-Item $base -Recurse -Force }
  Write-Host "已移除 slc:// 协议注册"
  exit 0
}

$handler = Join-Path $PSScriptRoot "rvopen-handler.ps1"
if (-not (Test-Path $handler)) { Write-Error "找不到 $handler"; exit 1 }

New-Item -Path $base -Force | Out-Null
Set-ItemProperty -Path $base -Name "(default)" -Value "URL:slc Protocol"
New-ItemProperty -Path $base -Name "URL Protocol" -Value "" -PropertyType String -Force | Out-Null

$command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$handler`" `"%1`""
New-Item -Path "$base\shell\open\command" -Force | Out-Null
Set-ItemProperty -Path "$base\shell\open\command" -Name "(default)" -Value $command

Write-Host "已注册 slc:// → $handler"
Write-Host "测试：Start-Process 'slc://open?file=slc.yaml&line=1'"

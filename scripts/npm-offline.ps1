# 从 vendor/npm/*.tgz 填充本机 npm cache。不联网，不安装依赖。
# 用法：powershell -File scripts/npm-offline.ps1
# 之后在 web/ 下执行：npm ci --offline（P3 起 web/package.json 存在时）。
$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent $PSScriptRoot
$vendor = Join-Path $repo 'vendor\npm'

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Error 'rvgen: 找不到 npm；请先安装 Node 24.x'
    exit 3
}

if (-not (Test-Path -LiteralPath $vendor -PathType Container)) {
    Write-Error "rvgen: 缺少 $vendor；离线包尚未生成"
    exit 3
}

$tgzs = @(Get-ChildItem -LiteralPath $vendor -Filter '*.tgz' -File -ErrorAction SilentlyContinue)
if ($tgzs.Count -eq 0) {
    Write-Host 'rvgen: vendor/npm 为空；P0 无 web/package.json，离线 npm 包留待 P3 生成'
    exit 0
}

foreach ($tgz in $tgzs) {
    npm cache add $tgz.FullName
    if ($LASTEXITCODE -ne 0) {
        Write-Error "rvgen: npm cache add 失败：$($tgz.FullName)"
        exit 3
    }
}

Write-Host "rvgen: 已向 npm cache 注入 $($tgzs.Count) 个 tgz"
exit 0

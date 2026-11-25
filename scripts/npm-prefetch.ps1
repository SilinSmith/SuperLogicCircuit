# 有网时把 web/ 依赖预取到本机 npm cache；之后可断网执行 npm ci --offline。
# 用法：powershell -File scripts/npm-prefetch.ps1 [-Cache <dir>]
# 仓库不内置 vendor/npm tgz；离线安装依赖这台机器事先完成过预取。
param(
    [string]$Cache
)
$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent $PSScriptRoot
$web = Join-Path $repo 'web'

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Error 'slc: 找不到 npm；请先安装 Node 24.x'
    exit 3
}

if (-not (Test-Path -LiteralPath (Join-Path $web 'package-lock.json'))) {
    Write-Error "slc: 缺少 $web\package-lock.json；先检出 web 依赖清单"
    exit 3
}

if ($Cache) {
    $env:npm_config_cache = $Cache
}

Push-Location $web
try {
    npm ci --no-audit --no-fund
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}

if ($code -ne 0) {
    Write-Error 'slc: npm ci 预取失败；检查网络后重试'
    exit 3
}

$cachePath = if ($Cache) { $Cache } else { npm config get cache }
Write-Host "slc: 依赖已预取到 npm cache（$cachePath）"
Write-Host 'slc: 断网后可在 web/ 执行 npm ci --offline'
exit 0

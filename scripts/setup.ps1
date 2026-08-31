#Requires -Version 5.1
<#
.SYNOPSIS
  Bootstrap local Project Zomboid modding workspace (Windows).
#>

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $Root "tools"))) {
    $Root = $PSScriptRoot
}
Set-Location $Root

Write-Host "== PZ workspace setup ==" -ForegroundColor Cyan
Write-Host "Root: $Root"

$dirs = @(
    ".cache\workshop",
    ".cache\steamcmd_logs",
    "src\mods",
    "src\modpacks",
    "steamcmd",
    "dist"
)
foreach ($d in $dirs) {
    $path = Join-Path $Root $d
    if (-not (Test-Path $path)) {
        New-Item -ItemType Directory -Path $path -Force | Out-Null
        Write-Host "  created $d"
    } else {
        Write-Host "  ok      $d"
    }
}

if (-not (Test-Path (Join-Path $Root ".env"))) {
    if (Test-Path (Join-Path $Root ".env.example")) {
        Copy-Item (Join-Path $Root ".env.example") (Join-Path $Root ".env")
        Write-Host "  created .env from .env.example"
    }
}

Write-Host ""
Write-Host "-- Python --" -ForegroundColor Yellow
function Test-RealPython {
    param([string]$Exe)
    if (-not $Exe) { return $false }
    if ($Exe -match "WindowsApps\\python") { return $false }
    try {
        $out = & $Exe --version 2>&1 | Out-String
        return ($LASTEXITCODE -eq 0 -and $out -match "Python 3\.")
    } catch {
        return $false
    }
}

$pythonExe = $null
foreach ($candidate in @("python", "python3")) {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($cmd -and (Test-RealPython $cmd.Source)) {
        $pythonExe = $cmd.Source
        break
    }
}
if (-not $pythonExe) {
    $local = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe"
    )
    foreach ($p in $local) {
        if (Test-Path $p) { $pythonExe = $p; break }
    }
}

if ($pythonExe) {
    Write-Host "  $(& $pythonExe --version)"
    Write-Host "  using $pythonExe"
    & $pythonExe -m pip install -r (Join-Path $Root "tools\requirements.txt") --quiet
    Write-Host "  tools/requirements.txt applied"
} else {
    Write-Host "  Real Python 3.10+ not found (Windows Store stub does not count)." -ForegroundColor Red
    Write-Host "  Install: winget install -e --id Python.Python.3.12" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "-- Optional tools --" -ForegroundColor Yellow

# Ensure luarocks-installed tools are visible in this session
$luacheckBin = Join-Path $env:APPDATA "luarocks\bin"
$luaBin = "C:\Users\zvaa\AppData\Local\Programs\Lua\bin"
if (Test-Path $luacheckBin) { $env:Path = "$luacheckBin;" + $env:Path }
if (Test-Path $luaBin) { $env:Path = "$luaBin;" + $env:Path }
if (-not $env:LUA_PATH -and (Test-Path (Join-Path $env:APPDATA "luarocks\share\lua\5.4"))) {
    $env:LUA_PATH = "$env:APPDATA\luarocks\share\lua\5.4\?.lua;$env:APPDATA\luarocks\share\lua\5.4\?\init.lua;;"
    $env:LUA_CPATH = "$env:APPDATA\luarocks\lib\lua\5.4\?.dll;;"
}

foreach ($cmd in @("lua", "luacheck", "steamcmd")) {
    $found = Get-Command $cmd -ErrorAction SilentlyContinue
    if ($found) {
        Write-Host "  found $cmd -> $($found.Source)"
    } else {
        Write-Host "  missing $cmd (optional for now)"
    }
}

$cursorExt = $null
if (Get-Command cursor -ErrorAction SilentlyContinue) {
    $cursorExt = & cursor --list-extensions 2>$null | Where-Object { $_ -eq "sumneko.lua" }
}
if ($cursorExt) {
    Write-Host "  found Cursor extension sumneko.lua"
} else {
    Write-Host "  missing Cursor extension sumneko.lua"
    Write-Host "    Install: cursor --install-extension sumneko.lua"
}

$steamLocal = Join-Path $Root "steamcmd\steamcmd.exe"
if (Test-Path $steamLocal) {
    Write-Host "  found local SteamCMD: $steamLocal"
} else {
    Write-Host "  SteamCMD not in ./steamcmd/"
    Write-Host "  Download: https://developer.valvesoftware.com/wiki/SteamCMD"
}

Write-Host ""
Write-Host "-- Smoke checks --" -ForegroundColor Yellow
if ($pythonExe) {
    & $pythonExe (Join-Path $Root "tools\pack_merger.py") --help | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-Host "  pack_merger.py OK" } else { Write-Host "  pack_merger.py FAILED" -ForegroundColor Red }
    & $pythonExe (Join-Path $Root "tools\uploader.py") --help | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-Host "  uploader.py OK" } else { Write-Host "  uploader.py FAILED" -ForegroundColor Red }
    & $pythonExe (Join-Path $Root "tools\workshop_downloader.py") --help | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-Host "  workshop_downloader.py OK" } else { Write-Host "  workshop_downloader.py FAILED" -ForegroundColor Red }
} else {
    Write-Host "  skipped (no Python)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Next:" -ForegroundColor Green
if (-not $cursorExt) {
    Write-Host "  - Install Cursor extension: cursor --install-extension sumneko.lua"
}
if (-not (Get-Command luacheck -ErrorAction SilentlyContinue)) {
    Write-Host "  - Install luacheck via luarocks (see docs/setup.md)"
}
Write-Host "  See docs/setup.md"
Write-Host "Done."

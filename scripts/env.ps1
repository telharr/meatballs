# Optional: load Lua / luacheck into the current PowerShell session.
# Prefer a new terminal after install (User PATH is already updated).

$luaBin = "C:\Users\zvaa\AppData\Local\Programs\Lua\bin"
$luacheckBin = Join-Path $env:APPDATA "luarocks\bin"

if (Test-Path $luaBin) {
    $env:Path = "$luacheckBin;$luaBin;" + $env:Path
}

if (-not $env:LUA_PATH) {
    $env:LUA_PATH = "$env:APPDATA\luarocks\share\lua\5.4\?.lua;$env:APPDATA\luarocks\share\lua\5.4\?\init.lua;;"
}
if (-not $env:LUA_CPATH) {
    $env:LUA_CPATH = "$env:APPDATA\luarocks\lib\lua\5.4\?.dll;;"
}

Write-Host "lua:" -NoNewline; if (Get-Command lua -ErrorAction SilentlyContinue) { lua -v } else { Write-Host " missing" }
Write-Host "luacheck:" -NoNewline
if (Get-Command luacheck -ErrorAction SilentlyContinue) {
    luacheck --version | Select-Object -First 1
} else {
    Write-Host " missing (open a new terminal or re-run scripts/setup.ps1)"
}

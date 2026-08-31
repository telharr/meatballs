#Requires -Version 5.1
<#
.SYNOPSIS
  Create desktop shortcut for PZ Server Control Panel.
#>

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "MEATBALLS PZ Panel.lnk"
$IconPath = Join-Path $Root "panel\static\assets\icon.ico"
$Target = Join-Path $Root "launch_panel.bat"

$python = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
if (-not (Test-Path $python)) {
    $python = (Get-Command python -ErrorAction SilentlyContinue).Source
}
if (-not (Test-Path $Target)) {
    @"
@echo off
cd /d "%~dp0"
python run_panel.py
"@ | Set-Content -Path $Target -Encoding ASCII
}

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $Target
$Shortcut.WorkingDirectory = $Root
$Shortcut.WindowStyle = 7
$Shortcut.Description = "MEATBALLS - Project Zomboid Server Panel (FTP + RCON)"
if (Test-Path $IconPath) {
    $Shortcut.IconLocation = "$IconPath,0"
}
$Shortcut.Save()

Write-Host "Shortcut created: $ShortcutPath"
Write-Host "Icon: $IconPath"

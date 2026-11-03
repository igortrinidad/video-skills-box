<#
Links every skill in .\skills into ~/.claude/skills as a directory junction,
so the repo stays the single source of truth (edits in either place are the same files).

An existing real directory with the same name is moved to ~/.claude/skills/.trash/<name>-<timestamp>
before linking. Existing junctions are re-pointed. Run again after adding a skill.

Usage: powershell -ExecutionPolicy Bypass -File install.ps1 [-Target <dir>]
#>
param([string]$Target = (Join-Path $HOME ".claude\skills"))

$ErrorActionPreference = "Stop"
$src = Join-Path $PSScriptRoot "skills"
New-Item -ItemType Directory -Force $Target | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"

foreach ($skill in Get-ChildItem $src -Directory) {
    if (-not (Test-Path (Join-Path $skill.FullName "SKILL.md"))) { continue }
    $dest = Join-Path $Target $skill.Name
    $item = Get-Item $dest -Force -ErrorAction SilentlyContinue
    if ($item) {
        if ($item.LinkType) {
            $item.Delete()
        } else {
            $trash = Join-Path $Target ".trash"
            New-Item -ItemType Directory -Force $trash | Out-Null
            $backup = Join-Path $trash "$($skill.Name)-$stamp"
            Move-Item $dest $backup
            Write-Host "  backup: $dest -> $backup"
        }
    }
    New-Item -ItemType Junction -Path $dest -Target $skill.FullName | Out-Null
    Write-Host "  linked: $dest -> $($skill.FullName)"
}

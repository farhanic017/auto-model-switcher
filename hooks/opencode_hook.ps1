# =============================================================================
#  Auto Model Switcher - OpenCode Pre-Execution Hook
#  Copyright (c) 2026 Farhan Dhrubo  <farhaiee123@gmail.com>
#  License: GPL-3.0 - https://github.com/farhanic017/auto-model-switcher
#
#  This program is free software. You may NOT remove this notice,
#  re-distribute as your own work, or sell without attribution.
# =============================================================================

# Place in your PowerShell profile or run before opencode.
#
# Usage:
#   . .\hooks\opencode_hook.ps1
#   opencode

$Switcher = Join-Path (Join-Path $PSScriptRoot "..") "switcher.py"
$StateFile = Join-Path $HOME ".auto-model-switcher\state.json"

if (-not (Test-Path $Switcher)) {
    Write-Host "[switcher] Not found: $Switcher" -ForegroundColor Red
    return
}

$state = $null
if (Test-Path $StateFile) {
    try {
        $state = Get-Content $StateFile -Raw | ConvertFrom-Json
    } catch {
        $state = $null
    }
}

$active = $null
if ($state -and $state.active) {
    $active = $state.active.opencode
}

if (-not $active) {
    Write-Host "[switcher] No active model - scanning..." -ForegroundColor Yellow
    python "$Switcher" switch
    return
}

$activeDepleted = $false
if ($state.depleted) {
    $activeDepleted = [bool]($state.depleted | Get-Member -Name $active -MemberType NoteProperty)
}

if ($activeDepleted) {
    Write-Host "[switcher] Model $active depleted - switching..." -ForegroundColor Yellow
    python "$Switcher" switch
}

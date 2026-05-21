# Auto Model Switcher — Universal CLI Wrapper
# =============================================
# Usage: dot-source this in your PowerShell profile, then:
#   opencode <args>     # auto-switches before running
#   claude <args>       # auto-switches before running
#   cursor <args>       # auto-switches before running
#
# Or run a single command with auto-switch:
#   .\auto-switch.ps1 opencode --version

param(
    [Parameter(Position=0, Mandatory=$false)]
    [string]$TargetCli = "",

    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$CliArgs = @()
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Switcher = Join-Path $ScriptDir "switcher.py"
$StateFile = "$HOME\.auto-model-switcher\state.json"

# ─── Health Check ────────────────────────────────────────────────────────────
function Test-ModelHealth {
    if (-not (Test-Path $StateFile)) { return $false }
    try {
        $state = Get-Content $StateFile -Raw | ConvertFrom-Json
        $active = $state.active.opencode
        $depleted = $state.depleted
        if (-not $active) { return $false }
        if ($depleted -and $depleted.$active) { return $false }
        return $true
    } catch { return $false }
}

# ─── Auto-Switch ─────────────────────────────────────────────────────────────
function Invoke-AutoSwitch {
    Write-Host "[auto-switch] Checking model health..." -ForegroundColor Cyan
    $result = python "$Switcher" switch 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[auto-switch] Ready" -ForegroundColor Green
    } else {
        Write-Host "[auto-switch] WARNING: $result" -ForegroundColor Yellow
    }
}

# ─── Main ────────────────────────────────────────────────────────────────────
if (-not (Test-ModelHealth)) {
    Invoke-AutoSwitch
}

# ─── Functions for dot-sourcing ──────────────────────────────────────────────
function global:opencode { . "$ScriptDir\auto-switch.ps1; python $Switcher switch --silent; & 'C:\Users\Farhan\AppData\Local\Programs\@opencode-aidesktop\OpenCode.exe' @args }
function global:claude { . "$ScriptDir\auto-switch.ps1; python $Switcher switch --silent; & claude @args }
function global:cursor { . "$ScriptDir\auto-switch.ps1; python $Switcher switch --silent; & cursor @args }
function global:aider { . "$ScriptDir\auto-switch.ps1; python $Switcher switch --silent; & aider @args }

# If a specific CLI was requested, run it now
if ($TargetCli) {
    $cliPath = switch ($TargetCli.ToLower()) {
        "opencode" { "C:\Users\Farhan\AppData\Local\Programs\@opencode-aidesktop\OpenCode.exe" }
        "claude"   { "claude.exe" }
        "cursor"   { "cursor.exe" }
        "aider"    { "aider.exe" }
        default    { $TargetCli }
    }
    if ($CliArgs) {
        & $cliPath @CliArgs
    } else {
        & $cliPath
    }
}

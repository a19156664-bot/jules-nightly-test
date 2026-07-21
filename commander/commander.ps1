# ===== Config =====
$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
$RepoRoot = $PSScriptRoot | Split-Path -Parent
$Model    = "claude-opus-4-8"
$Repo     = "a19156664-bot/jules-nightly-test"
Set-Location $RepoRoot
$Python = "C:\Users\user\AppData\Local\Programs\Python\Python313\python.exe"
$Gh     = "C:\Program Files\GitHub CLI\gh.exe"
$Claude = "C:\Users\user\.local\bin\claude.exe"
try {
    $LogDir = Join-Path $PSScriptRoot "logs"
    if (-not (Test-Path -Path $LogDir)) {
        New-Item -ItemType Directory -Path $LogDir | Out-Null
    }
    # ===== Stage 0: pre-checks without LLM =====
    $ShouldStop = & $Python -m commander.state_manager --should-stop
    if ($ShouldStop -like "True*") {
        & $Python -m commander.state_manager --record-wakeup "stopped"
        exit 0
    }
    $openPRs = (& $Gh pr list -R $Repo --state open --json number --jq 'length')
    $alertOpen = (& $Gh issue list -R $Repo --label loop-alert --state open --json number --jq 'length')
    $turnDue = & $Python -m commander.state_manager --check-turn-due
    $turn = & $Python -m commander.state_manager --get turn
    if ($openPRs -eq 0 -and $turnDue -like "False*" -and $turn -notlike "complete*") {
        if ($alertOpen -gt 0) {
            & $Python -m commander.state_manager --record-wakeup "alert-pending-human"
        } else {
            & $Python -m commander.state_manager --record-wakeup "no-work"
        }
        exit 0
    }
    # ===== Budget check (soft skip) =====
    $CanCallLLM = & $Python -m commander.state_manager --can-call-llm
    if ($CanCallLLM -like "False*") {
        & $Python -m commander.state_manager --record-wakeup "budget-deferred"
        exit 0
    }
    & $Python -m commander.state_manager --record-wakeup "has-work"
    # ===== Stage 1: LLM call =====
    $PromptFile = Join-Path $PSScriptRoot "current-prompt.txt"
    & $Python -m commander.build_prompt --alert-count $alertOpen --output $PromptFile
    if (-not (Test-Path -Path $PromptFile)) {
        Write-Host "[SKIP] build_prompt.py failed to produce prompt file"
        exit 0
    }
    $Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $LogFile = Join-Path $LogDir "commander-$Timestamp.log"
    $PromptContent = Get-Content -Path $PromptFile -Raw -Encoding UTF8
    & $Claude -p $PromptContent --model $Model 2>&1 | Out-File -FilePath $LogFile -Encoding utf8
    & $Python -m commander.state_manager --record-llm-call
    & $Python -m commander.parse_output $LogFile
} catch {
    $ErrorMessage = $_.Exception.Message
    $Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $LogDir = Join-Path $PSScriptRoot "logs"
    if (-not (Test-Path -Path $LogDir)) {
        New-Item -ItemType Directory -Path $LogDir | Out-Null
    }
    $LogFile = Join-Path $LogDir "commander-error-$Timestamp.log"
    $ErrorMessage | Out-File -FilePath $LogFile -Encoding utf8
    & $Python -m commander.create_alert_issue --alert-type "runtime-error" --summary "commander.ps1 crashed" --detail "$ErrorMessage"
    exit 1
}

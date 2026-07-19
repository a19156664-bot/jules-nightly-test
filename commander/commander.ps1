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
    $ShouldStop = & $Python "$PSScriptRoot\state_manager.py" --should-stop
    if ($ShouldStop -like "True*") {
        & $Python "$PSScriptRoot\state_manager.py" --record-wakeup "stopped"
        exit 0
    }
    $openPRs = (& $Gh pr list -R $Repo --state open --json number --jq 'length')
    $alertOpen = (& $Gh issue list -R $Repo --label loop-alert --state open --json number --jq 'length')
    $turnDue = & $Python "$PSScriptRoot\state_manager.py" --check-turn-due
    if ($openPRs -eq 0 -and $turnDue -like "False*") {
        if ($alertOpen -gt 0) {
            & $Python "$PSScriptRoot\state_manager.py" --record-wakeup "alert-pending-human"
        } else {
            & $Python "$PSScriptRoot\state_manager.py" --record-wakeup "no-work"
        }
        exit 0
    }
    # ===== Budget check (soft skip) =====
    $CanCallLLM = & $Python "$PSScriptRoot\state_manager.py" --can-call-llm
    if ($CanCallLLM -like "False*") {
        & $Python "$PSScriptRoot\state_manager.py" --record-wakeup "budget-deferred"
        exit 0
    }
    & $Python "$PSScriptRoot\state_manager.py" --record-wakeup "has-work"
    # ===== Stage 1: LLM call =====
    $CommanderPath = Join-Path $RepoRoot ".nightly\COMMANDER.MD"
    if (-not (Test-Path -Path $CommanderPath)) {
        Write-Host "[SKIP] COMMANDER.MD not found"
        exit 0
    }
    $StatePath = Join-Path $PSScriptRoot "state.yml"
    $SuffixPath = Join-Path $PSScriptRoot "prompt-suffix.txt"
    $Prompt = Get-Content -Path $CommanderPath -Raw -Encoding UTF8
    if (Test-Path -Path $StatePath) {
        $Prompt += "`n---`n## state.yml:`n" + (Get-Content -Path $StatePath -Raw -Encoding UTF8)
    }
    if (Test-Path -Path $SuffixPath) {
        $Prompt += "`n" + (Get-Content -Path $SuffixPath -Raw -Encoding UTF8)
    }
    $PromptFile = Join-Path $PSScriptRoot "current-prompt.txt"
    $Prompt | Out-File -FilePath $PromptFile -Encoding UTF8
    $Result = & $Claude -p (Get-Content -Path $PromptFile -Raw -Encoding UTF8) --model $Model
    & $Python "$PSScriptRoot\state_manager.py" --record-llm-call
    $Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $LogFile = Join-Path $LogDir "commander-$Timestamp.log"
    $Result | Out-File -FilePath $LogFile -Encoding utf8
    & $Python "$PSScriptRoot\parse_output.py" $LogFile
    } catch {
    $ErrorMessage = $_.Exception.Message
    $Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $LogDir = Join-Path $PSScriptRoot "logs"
    if (-not (Test-Path -Path $LogDir)) {
        New-Item -ItemType Directory -Path $LogDir | Out-Null
    }
    $LogFile = Join-Path $LogDir "commander-error-$Timestamp.log"
    $ErrorMessage | Out-File -FilePath $LogFile -Encoding utf8
    & $Python "$PSScriptRoot\create_alert_issue.py" --alert-type "runtime-error" --summary "commander.ps1 crashed" --detail "$ErrorMessage"
    exit 1
}
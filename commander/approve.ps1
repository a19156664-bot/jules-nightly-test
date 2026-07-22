#requires -Version 5.1
<#
.SYNOPSIS
    Approve a commander proposal and start the corresponding nightly turn.

.DESCRIPTION
    Copies commander/proposals/<Night>/ files to .nightly/ and
    performs git commit / push. When night_date_now() disagrees with
    the proposal night, offers to dispatch turn-switch.yml with
    force_date so that start-night fires immediately.

    Human responsibilities before running:
      - Reviewed the proposal content by opening the files (this
        script does not open an editor).
      - On the main branch with no unrelated modifications.

    This script does NOT touch:
      - commander/state.yml (commander's internal state).
      - Content validation (validate_proposal.py runs from commander.ps1).

.PARAMETER Night
    The proposal date (YYYY-MM-DD). Matches commander/proposals/<Night>/.

.EXAMPLE
    .\commander\approve.ps1 -Night 2026-07-23

.EXAMPLE
    .\commander\approve.ps1 2026-07-23
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidatePattern('^\d{4}-\d{2}-\d{2}$')]
    [string]$Night
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# ---------------------------------------------------------------- helpers
function Write-Step($msg) { Write-Host ("==> " + $msg) -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host ("    OK: " + $msg) -ForegroundColor Green }
function Write-Warn2($msg){ Write-Host ("    WARN: " + $msg) -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host ("    ERR: " + $msg) -ForegroundColor Red }

function Get-NightDateNow {
    # Same definition as nightly.py: JST now shifted by -12 hours.
    $jstNow = [DateTime]::UtcNow.AddHours(9)
    $shifted = $jstNow.AddHours(-12)
    return $shifted.ToString('yyyy-MM-dd')
}

# ---------------------------------------------------------------- Phase 0: pre-checks
Write-Step "Phase 0: pre-checks"

# Resolve the repo root relative to this script.
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
Set-Location $repoRoot
Write-Ok ("repo root: " + $repoRoot)

# Proposal directory presence.
$proposalDir = Join-Path $repoRoot ("commander\proposals\" + $Night)
if (-not (Test-Path $proposalDir)) {
    Write-Err ("proposal directory not found: " + $proposalDir)
    exit 1
}
$srcTasks = Join-Path $proposalDir 'tasks.yml'
$srcT1    = Join-Path $proposalDir 'T1-01.md'
$srcT2    = Join-Path $proposalDir 'T2-01.md'
foreach ($f in @($srcTasks, $srcT1, $srcT2)) {
    if (-not (Test-Path $f)) {
        Write-Err ("required file missing: " + $f)
        exit 1
    }
}
Write-Ok "proposal files (tasks.yml, T1-01.md, T2-01.md) present"

# On main?
$currentBranch = (git rev-parse --abbrev-ref HEAD).Trim()
if ($currentBranch -ne 'main') {
    Write-Err ("current branch is not main: " + $currentBranch)
    exit 1
}
Write-Ok "branch: main"

# Working tree must be clean (ignoring local backups / obsolete files).
$dirty = git status --porcelain | Where-Object {
    $line = $_
    ($line -notmatch '\.bak-') -and ($line -notmatch '\.obsolete$')
}
if ($dirty) {
    Write-Err "working tree has unrelated changes:"
    $dirty | ForEach-Object { Write-Host ("      " + $_) -ForegroundColor Red }
    exit 1
}
Write-Ok "working tree clean (excluding *.bak- / *.obsolete)"

# Sync with origin/main.
Write-Step "Phase 0.5: pull origin/main"
git pull --ff-only origin main | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Err "git pull --ff-only origin main failed"
    exit 1
}
Write-Ok "in sync with origin/main"

# ---------------------------------------------------------------- Phase 1: backup and obsolete
Write-Step "Phase 1: backup and obsolete"

$stamp = (Get-Date).ToString('yyyyMMdd-HHmmss')
$tasksBackup = ".nightly\tasks.yml.bak-before-" + $Night + "-" + $stamp
Copy-Item .nightly\tasks.yml $tasksBackup
Write-Ok ("backup: " + $tasksBackup)

$dstT1 = ".nightly\prompts\" + $Night + "-T1-01.md"
$dstT2 = ".nightly\prompts\" + $Night + "-T2-01.md"
foreach ($dst in @($dstT1, $dstT2)) {
    if (Test-Path $dst) {
        $obsolete = $dst + ".obsolete"
        Move-Item $dst $obsolete -Force
        Write-Ok ("moved existing to: " + $obsolete)
    }
}

# ---------------------------------------------------------------- Phase 2: apply
Write-Step "Phase 2: apply proposal to .nightly/"

Copy-Item $srcTasks .nightly\tasks.yml -Force
Write-Ok ".nightly\tasks.yml updated"
Copy-Item $srcT1 $dstT1
Write-Ok ($dstT1 + " created")
Copy-Item $srcT2 $dstT2
Write-Ok ($dstT2 + " created")

# ---------------------------------------------------------------- Phase 3: git commit and push
Write-Step "Phase 3: git commit and push"

git add .nightly/tasks.yml .nightly/prompts/ commander/proposals/ | Out-Null

# Read task titles via a temp Python script (avoid PowerShell here-string quirks).
$python = "C:\Users\user\AppData\Local\Programs\Python\Python313\python.exe"
$pyTmp = Join-Path $env:TEMP ("approve-read-titles-" + $stamp + ".py")
$pyLines = @(
    "import yaml, json",
    "d = yaml.safe_load(open('.nightly/tasks.yml', encoding='utf-8'))",
    "print(json.dumps({'t1': d['turn1'][0]['title'], 't2': d['turn2'][0]['title']}, ensure_ascii=False))"
)
$pyLines -join "`r`n" | Set-Content -Path $pyTmp -Encoding UTF8

try {
    $titlesJson = & $python $pyTmp
} finally {
    if (Test-Path $pyTmp) { Remove-Item $pyTmp -Force }
}
$titles = $titlesJson | ConvertFrom-Json
$msgTitle = "nightly: approve " + $Night + " (" + $titles.t1 + " / " + $titles.t2 + ")"

git commit -m $msgTitle | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Err "git commit failed"
    exit 1
}
Write-Ok ("commit: " + $msgTitle)

git push origin main | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Err "git push failed"
    exit 1
}
Write-Ok "pushed to origin/main"

# ---------------------------------------------------------------- Phase 4: workflow_dispatch (if needed)
Write-Step "Phase 4: night-date consistency check"

$nightNow = Get-NightDateNow
Write-Host ("    night_date_now() = " + $nightNow) -ForegroundColor Gray
Write-Host ("    proposal night   = " + $Night) -ForegroundColor Gray

if ($Night -eq $nightNow) {
    Write-Ok "night matches. push-triggered turn-switch.yml should fire start-night automatically."
} else {
    Write-Warn2 "night mismatch. start-night must be dispatched manually."
    Write-Host ""
    Write-Host "  Planned command:" -ForegroundColor Yellow
    Write-Host ("    gh workflow run turn-switch.yml -f command=start-night -f force_date=" + $Night) -ForegroundColor Yellow
    Write-Host ""
    $confirm = Read-Host "  Run it now? [y/N]"
    if ($confirm -eq 'y' -or $confirm -eq 'Y') {
        gh workflow run turn-switch.yml -f command=start-night -f force_date=$Night
        if ($LASTEXITCODE -ne 0) {
            Write-Err "gh workflow run failed"
            exit 1
        }
        Write-Ok "workflow_dispatch sent"
    } else {
        Write-Warn2 "workflow_dispatch skipped. Run it manually when ready."
    }
}

# ---------------------------------------------------------------- Phase 5: post
Write-Host ""
Write-Step "Approval complete"
Write-Host "  - main: pushed" -ForegroundColor Green
Write-Host ("  - integration branch (expected): integration/nightly-" + ($Night -replace '-','')) -ForegroundColor Green
Write-Host "  - Jules dashboard: https://jules.google.com/" -ForegroundColor Green
Write-Host "  - GitHub Actions:  https://github.com/a19156664-bot/jules-nightly-test/actions" -ForegroundColor Green
Write-Host ""

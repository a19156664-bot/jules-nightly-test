# ===== 設定 =====
$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
$RepoRoot   = $PSScriptRoot | Split-Path -Parent
$Model      = "claude-opus-4-8"
Set-Location $RepoRoot
try {
    # ログディレクトリの作成
    $LogDir = Join-Path $PSScriptRoot "logs"
    if (-not (Test-Path -Path $LogDir)) {
        New-Item -ItemType Directory -Path $LogDir | Out-Null
    }
    # ===== Stage 0: LLM を呼ばない事前判定 =====
    # 1. 恒久停止チェック: state_manager.py --should-stop が True なら即終了
    $ShouldStop = & python "$PSScriptRoot/state_manager.py" --should-stop
    if ($ShouldStop -like "True*") {
        & python "$PSScriptRoot/state_manager.py" --record-wakeup "stopped"
        exit 0
    }
    # 2. 仕事の有無チェック（gh CLI / リポジトリ明示指定）
    $Repo = "a19156664-bot/jules-nightly-test"
    $openPRs = (gh pr list -R $Repo --state open --json number --jq 'length')
    $alertOpen = (gh issue list -R $Repo --label loop-alert --state open --json number --jq 'length')
    $turnDue = & python "$PSScriptRoot/state_manager.py" --check-turn-due
    # 3. 仕事ゼロなら record-wakeup "no-work" して exit 0
    if ($openPRs -eq 0 -and $alertOpen -eq 0 -and $turnDue -like "False*") {
        & python "$PSScriptRoot/state_manager.py" --record-wakeup "no-work"
        exit 0
    }
    # ===== 予算チェック（ソフトスキップ）=====
    $CanCallLLM = & python "$PSScriptRoot/state_manager.py" --can-call-llm
    if ($CanCallLLM -like "False*") {
        & python "$PSScriptRoot/state_manager.py" --record-wakeup "budget-deferred"
        exit 0
    }
    # wakeup の記録（仕事あり予算あり  LLM 呼び出しへ進む場合のみ）
    & python "$PSScriptRoot/state_manager.py" --record-wakeup "has-work"
    # ===== Stage 1: LLM 呼び出し =====
    # 1. 憲法(.nightly/COMMANDER.md)と state.yml を読み込んでプロンプトを組み立てる
    $CommanderPath = Join-Path $RepoRoot ".nightly/COMMANDER.md"
    if (-not (Test-Path -Path $CommanderPath)) {
        Write-Host "[SKIP] COMMANDER.md not found"
        exit 0
    }
    $StatePath = Join-Path $PSScriptRoot "state.yml"
    $Prompt = Get-Content -Path $CommanderPath -Raw -Encoding UTF8
    if (Test-Path -Path $StatePath) {
        $Prompt += "`n---`n## 現在の state.yml:`n" + (Get-Content -Path $StatePath -Raw -Encoding UTF8)
    }
    $Prompt += "`n上記の憲法と状態に基づいて、判断表を上から評価し、1つだけアクションを実行してください。"
    # 2. ファイル経由で claude -p に渡す（パイプ渡しはハングするため禁止知見15）
    $PromptFile = Join-Path $PSScriptRoot "current-prompt.txt"
    $Prompt | Out-File -FilePath $PromptFile -Encoding UTF8
    $Result = claude -p (Get-Content -Path $PromptFile -Raw -Encoding UTF8) --model $Model
    # 3. 成功したら state_manager.py --record-llm-call
    & python "$PSScriptRoot/state_manager.py" --record-llm-call
    # 4. 結果を commander/logs/commander-YYYYMMDD-HHmmss.log に UTF-8 で保存
    $Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $LogFile = Join-Path $LogDir "commander-$Timestamp.log"
    $Result | Out-File -FilePath $LogFile -Encoding utf8
} catch {
    # ===== エラーハンドリング =====
    $ErrorMessage = $_.Exception.Message
    # エラー内容をログファイルに保存
    $Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $LogDir = Join-Path $PSScriptRoot "logs"
    if (-not (Test-Path -Path $LogDir)) {
        New-Item -ItemType Directory -Path $LogDir | Out-Null
    }
    $LogFile = Join-Path $LogDir "commander-error-$Timestamp.log"
    $ErrorMessage | Out-File -FilePath $LogFile -Encoding utf8
    # alert_issue 作成
    & python "$PSScriptRoot/create_alert_issue.py" --alert-type "runtime-error" --summary "commander.ps1 crashed" --detail "$ErrorMessage"
    exit 1
}

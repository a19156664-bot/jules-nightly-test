"""
Configuration module for the commander system.
Centralizes paths, thresholds, and other settings.
"""

import datetime
import os
from pathlib import Path

# パス設定
STATE_FILE: str = "commander/state.yml"
"""Path to the commander state file."""

COMMANDER_MD: str = ".nightly/COMMANDER.md"
"""Path to the COMMANDER.md file."""

TASKS_FILE: str = ".nightly/tasks.yml"
"""Path to the tasks configuration file."""

PROMPTS_DIR: str = ".nightly/prompts"
"""Path to the prompts directory."""

LOG_DIR: str = "commander/logs"
"""Path to the logs directory."""

# 予算設定
MAX_LLM_CALLS_PER_DAY: int = 24
"""Maximum number of LLM calls allowed per day."""

MAX_LLM_CALLS_PER_WINDOW: int = 8
"""Maximum number of LLM calls allowed per window."""

WINDOW_HOURS: int = 5
"""Time window in hours for the LLM call budget."""

# 停止閾値
MAX_CONSECUTIVE_ERRORS: int = 5
"""Maximum number of consecutive errors before stopping."""

# 司令塔モデル
DEFAULT_MODEL: str = "claude-opus-4-8"
"""Default LLM model used by the commander."""

# タイムゾーン
JST: datetime.timezone = datetime.timezone(datetime.timedelta(hours=9))
"""Japan Standard Time (JST) timezone (UTC+9)."""


def get_repo_root() -> Path:
    """リポジトリルートを返す。
    環境変数 REPO_ROOT があればそれを使用、
    なければ config.py の親の親（commander/ の親）を返す。
    """
    repo_root_env = os.environ.get("REPO_ROOT")
    if repo_root_env:
        return Path(repo_root_env).resolve()
    return Path(__file__).parent.parent.resolve()


def resolve_path(relative: str) -> Path:
    """リポジトリルートからの相対パスを絶対パスに解決する。

    Args:
        relative (str): リポジトリルートからの相対パス。

    Returns:
        Path: 解決された絶対パス。
    """
    return get_repo_root() / relative


def ensure_log_dir() -> Path:
    """LOG_DIR が存在しなければ作成して返す。

    Returns:
        Path: ログディレクトリの絶対パス。
    """
    log_dir_path = resolve_path(LOG_DIR)
    log_dir_path.mkdir(parents=True, exist_ok=True)
    return log_dir_path

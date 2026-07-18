import datetime
import os
from pathlib import Path

from commander import config


def test_path_constants_are_strings():
    """Verify that path constants are strings."""
    assert isinstance(config.STATE_FILE, str)
    assert isinstance(config.COMMANDER_MD, str)
    assert isinstance(config.TASKS_FILE, str)
    assert isinstance(config.PROMPTS_DIR, str)
    assert isinstance(config.LOG_DIR, str)


def test_jst_is_utc_plus_9():
    """Verify that JST represents a UTC+9 timezone offset."""
    assert isinstance(config.JST, datetime.timezone)
    assert config.JST.utcoffset(None) == datetime.timedelta(hours=9)


def test_get_repo_root_without_env_var(monkeypatch):
    """Verify get_repo_root returns a Path instance (default behavior)."""
    monkeypatch.delenv("REPO_ROOT", raising=False)
    repo_root = config.get_repo_root()
    assert isinstance(repo_root, Path)
    # The parent of the parent of config.py should be the repo root
    expected = Path(config.__file__).parent.parent.resolve()
    assert repo_root == expected


def test_get_repo_root_with_env_var(monkeypatch, tmp_path):
    """Verify get_repo_root respects the REPO_ROOT environment variable."""
    fake_root = str(tmp_path)
    monkeypatch.setenv("REPO_ROOT", fake_root)
    repo_root = config.get_repo_root()
    assert isinstance(repo_root, Path)
    assert repo_root == tmp_path.resolve()


def test_resolve_path():
    """Verify resolve_path returns an absolute Path from repo root."""
    repo_root = config.get_repo_root()
    relative_path = "some/relative/path.txt"
    resolved = config.resolve_path(relative_path)

    assert isinstance(resolved, Path)
    assert resolved.is_absolute()
    assert resolved == repo_root / relative_path


def test_ensure_log_dir(monkeypatch, tmp_path):
    """Verify ensure_log_dir creates the log directory."""
    # Mock get_repo_root to return a temporary path so we don't pollute the actual repo
    monkeypatch.setattr(config, "get_repo_root", lambda: tmp_path)

    expected_log_dir = tmp_path / config.LOG_DIR
    assert not expected_log_dir.exists()

    created_dir = config.ensure_log_dir()

    assert created_dir == expected_log_dir
    assert created_dir.exists()
    assert created_dir.is_dir()

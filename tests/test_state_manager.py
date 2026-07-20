import pytest
import os
import yaml
import datetime
from commander.state_manager import StateManager, get_default_state, JST

def test_load_default(tmp_path):
    # Test that load() returns default structure when file does not exist
    path = tmp_path / "state.yml"
    manager = StateManager(str(path))
    state = manager.load()
    assert state == get_default_state()
    # Ensure file is not created
    assert not path.exists()

def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "state.yml"
    manager = StateManager(str(path))
    state = manager.load()
    state["loop_status"] = "reviewing"
    state["budget"]["wakeups_today"] = 10
    manager.save(state)

    # Load it back
    manager2 = StateManager(str(path))
    loaded = manager2.load()
    assert loaded["loop_status"] == "reviewing"
    assert loaded["budget"]["wakeups_today"] == 10

    # Check that temporary file is not left behind
    temp_path = path.with_name(path.name + ".tmp")
    assert not temp_path.exists()
    assert path.exists()

def test_get_dot_notation(tmp_path):
    path = tmp_path / "state.yml"
    manager = StateManager(str(path))
    state = manager.load()
    state["last_action"]["type"] = "review"
    manager.save(state)

    # Test existing key
    assert manager.get("last_action.type") == "review"
    assert manager.get("version") == 1

    # Test non-existing key
    assert manager.get("not.exist") is None
    assert manager.get("last_action.not_exist") is None
    assert manager.get("not.exist", "default_val") == "default_val"

def test_update_dot_notation(tmp_path):
    path = tmp_path / "state.yml"
    manager = StateManager(str(path))

    manager.update({
        "loop_status": "reviewing",
        "last_action.type": "alert"
    })

    loaded = manager.load()
    assert loaded["loop_status"] == "reviewing"
    assert loaded["last_action"]["type"] == "alert"

def test_record_action(tmp_path):
    path = tmp_path / "state.yml"
    manager = StateManager(str(path))
    manager.record_action("dispatch", "approved", "Task 123 dispatched")

    loaded = manager.load()
    assert loaded["last_action"]["type"] == "dispatch"
    assert loaded["last_action"]["result"] == "approved"
    assert loaded["last_action"]["detail"] == "Task 123 dispatched"
    assert "T" in loaded["last_action"]["timestamp"] # Should be ISO8601

from unittest.mock import patch

def test_can_call_llm_normal(tmp_path):
    path = tmp_path / "state.yml"
    manager = StateManager(str(path))
    # By default, 0 calls today, 0 in window. So it should be allowed.
    allowed, reason = manager.can_call_llm()
    assert allowed is True
    assert reason is None

def test_can_call_llm_daily_budget_exceeded(tmp_path):
    path = tmp_path / "state.yml"
    manager = StateManager(str(path))
    today_str = datetime.datetime.now(JST).strftime("%Y-%m-%d")
    manager.update({
        "budget.llm_calls_today": 24,
        "budget.max_llm_calls_per_day": 24,
        "budget.last_reset_date": today_str
    })

    allowed, reason = manager.can_call_llm()
    assert allowed is False
    assert reason == "daily-budget-exceeded"

def test_can_call_llm_window_budget_exceeded(tmp_path):
    path = tmp_path / "state.yml"
    manager = StateManager(str(path))
    now = datetime.datetime.now(JST)
    window = [(now - datetime.timedelta(hours=1)).isoformat() for _ in range(8)]
    today_str = now.strftime("%Y-%m-%d")
    manager.update({
        "budget.llm_calls_today": 10,
        "budget.max_llm_calls_per_day": 24,
        "budget.llm_calls_window": window,
        "budget.max_llm_calls_per_window": 8,
        "budget.last_reset_date": today_str
    })

    allowed, reason = manager.can_call_llm()
    assert allowed is False
    assert reason == "window-budget-exceeded"

def test_can_call_llm_window_filtering(tmp_path):
    path = tmp_path / "state.yml"
    manager = StateManager(str(path))
    now = datetime.datetime.now(JST)

    # 8 entries total: 4 old (>5h), 4 recent
    window = []
    for _ in range(4):
        window.append((now - datetime.timedelta(hours=6)).isoformat())
    for _ in range(4):
        window.append((now - datetime.timedelta(hours=1)).isoformat())

    today_str = now.strftime("%Y-%m-%d")
    manager.update({
        "budget.llm_calls_today": 10,
        "budget.llm_calls_window": window,
        "budget.max_llm_calls_per_window": 8,
        "budget.last_reset_date": today_str
    })

    allowed, reason = manager.can_call_llm()
    assert allowed is True  # Only 4 recent entries should remain, < 8

    loaded = manager.load()
    assert len(loaded["budget"]["llm_calls_window"]) == 4

def test_should_stop(tmp_path):
    path = tmp_path / "state.yml"
    manager = StateManager(str(path))

    # Normal state
    stop, reason = manager.should_stop()
    assert stop is False

    # Stop reason set
    manager.update({"stop_reason": "manual-stop"})
    stop, reason = manager.should_stop()
    assert stop is True
    assert reason == "manual-stop"

    # Error count >= 5
    manager.update({"stop_reason": None, "error_count": 5})
    stop, reason = manager.should_stop()
    assert stop is True
    assert reason == "consecutive-errors"

@patch("commander.state_manager.resolve_path")
@patch("commander.state_manager.datetime")
def test_reset_daily_if_needed(mock_datetime, mock_resolve_path, tmp_path):
    path = tmp_path / "state.yml"
    log_dir = tmp_path / "logs"
    mock_resolve_path.return_value = log_dir
    manager = StateManager(str(path))

    # Setup mock datetime
    mock_now = datetime.datetime(2023, 10, 1, 12, 0, 0, tzinfo=JST)
    mock_datetime.datetime.now.return_value = mock_now
    mock_datetime.timezone = datetime.timezone
    mock_datetime.timedelta = datetime.timedelta

    # Initial state (no reset date)
    assert manager.reset_daily_if_needed() is True
    loaded = manager.load()
    assert loaded["budget"]["last_reset_date"] == "2023-10-01"

    # Simulate same day
    manager.update({"budget.llm_calls_today": 5})
    assert manager.reset_daily_if_needed() is False
    loaded = manager.load()
    assert loaded["budget"]["llm_calls_today"] == 5

    # Simulate next day
    mock_now_next = datetime.datetime(2023, 10, 2, 12, 0, 0, tzinfo=JST)
    mock_datetime.datetime.now.return_value = mock_now_next

    assert manager.reset_daily_if_needed() is True
    loaded = manager.load()
    assert loaded["budget"]["llm_calls_today"] == 0
    assert loaded["budget"]["last_reset_date"] == "2023-10-02"


@patch("commander.state_manager.resolve_path")
@patch("commander.state_manager.datetime")
def test_snapshot_created_on_daily_reset(mock_datetime, mock_resolve_path, tmp_path):
    path = tmp_path / "state.yml"
    log_dir = tmp_path / "logs"
    mock_resolve_path.return_value = log_dir
    manager = StateManager(str(path))

    mock_datetime.timezone = datetime.timezone
    mock_datetime.timedelta = datetime.timedelta

    # Initialize state with a previous date
    manager.update({
        "budget.llm_calls_today": 10,
        "budget.last_reset_date": "2023-10-01"
    })

    mock_now_next = datetime.datetime(2023, 10, 2, 12, 0, 0, tzinfo=JST)
    mock_datetime.datetime.now.return_value = mock_now_next

    assert manager.reset_daily_if_needed() is True

    # Check if snapshot is created
    snapshot_path = log_dir / "state-snapshot-2023-10-01.yml"
    assert snapshot_path.exists()

@patch("commander.state_manager.resolve_path")
@patch("commander.state_manager.datetime")
def test_snapshot_content_matches_pre_reset_state(mock_datetime, mock_resolve_path, tmp_path):
    path = tmp_path / "state.yml"
    log_dir = tmp_path / "logs"
    mock_resolve_path.return_value = log_dir
    manager = StateManager(str(path))

    mock_datetime.timezone = datetime.timezone
    mock_datetime.timedelta = datetime.timedelta

    # Initialize state with a previous date
    manager.update({
        "budget.llm_calls_today": 15,
        "budget.last_reset_date": "2023-10-01"
    })

    mock_now_next = datetime.datetime(2023, 10, 2, 12, 0, 0, tzinfo=JST)
    mock_datetime.datetime.now.return_value = mock_now_next

    assert manager.reset_daily_if_needed() is True

    # Read snapshot
    snapshot_path = log_dir / "state-snapshot-2023-10-01.yml"
    with open(snapshot_path, "r", encoding="utf-8") as f:
        snapshot_data = yaml.safe_load(f)

    assert snapshot_data["budget"]["llm_calls_today"] == 15
    assert snapshot_data["budget"]["last_reset_date"] == "2023-10-01"

@patch("commander.state_manager.resolve_path")
@patch("commander.state_manager.datetime")
def test_snapshot_skipped_when_no_last_reset_date(mock_datetime, mock_resolve_path, tmp_path):
    path = tmp_path / "state.yml"
    log_dir = tmp_path / "logs"
    mock_resolve_path.return_value = log_dir
    manager = StateManager(str(path))

    mock_datetime.timezone = datetime.timezone
    mock_datetime.timedelta = datetime.timedelta

    # Initial state (no reset date)
    mock_now = datetime.datetime(2023, 10, 1, 12, 0, 0, tzinfo=JST)
    mock_datetime.datetime.now.return_value = mock_now

    assert manager.reset_daily_if_needed() is True

    # Snapshot should not be created
    assert not log_dir.exists() or len(list(log_dir.glob("state-snapshot-*.yml"))) == 0

@patch("commander.state_manager.resolve_path")
@patch("commander.state_manager.datetime")
def test_snapshot_failure_does_not_block_reset(mock_datetime, mock_resolve_path, tmp_path):
    path = tmp_path / "state.yml"
    log_dir = tmp_path / "logs"

    # Make log_dir a file so mkdir fails
    log_dir.touch()

    mock_resolve_path.return_value = log_dir
    manager = StateManager(str(path))

    mock_datetime.timezone = datetime.timezone
    mock_datetime.timedelta = datetime.timedelta

    # Initialize state with a previous date
    manager.update({
        "budget.llm_calls_today": 12,
        "budget.last_reset_date": "2023-10-01"
    })

    mock_now_next = datetime.datetime(2023, 10, 2, 12, 0, 0, tzinfo=JST)
    mock_datetime.datetime.now.return_value = mock_now_next

    # Should not raise exception
    assert manager.reset_daily_if_needed() is True

    # Reset should be completed despite snapshot failure
    loaded = manager.load()
    assert loaded["budget"]["llm_calls_today"] == 0
    assert loaded["budget"]["last_reset_date"] == "2023-10-02"

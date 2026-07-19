"""Tests for commander/parse_output.py."""
from __future__ import annotations

import yaml
import pytest
from pathlib import Path

from commander.parse_output import parse_output, update_state


class TestParseOutput:
    def test_parses_standard_output(self):
        text = """Some preamble text here.

ACTION: review-pr
TARGET: #15
RESULT: success
DETAIL: All 6 checks passed
STATE_UPDATE: pending_reviews cleared

Some trailing text."""
        fields = parse_output(text)
        assert fields is not None
        assert fields["action"] == "review-pr"
        assert fields["target"] == "#15"
        assert fields["result"] == "success"
        assert fields["detail"] == "All 6 checks passed"
        assert fields["state_update"] == "pending_reviews cleared"

    def test_parses_no_action_output(self):
        text = """ACTION: no-action-needed
TARGET: -
RESULT: skipped
DETAIL: Row 8 reached
STATE_UPDATE: wakeup only"""
        fields = parse_output(text)
        assert fields is not None
        assert fields["action"] == "no-action-needed"
        assert fields["result"] == "skipped"

    def test_returns_none_when_missing_action(self):
        text = "RESULT: success\nDETAIL: something"
        assert parse_output(text) is None

    def test_returns_none_when_missing_result(self):
        text = "ACTION: review\nDETAIL: something"
        assert parse_output(text) is None

    def test_returns_none_on_empty_text(self):
        assert parse_output("") is None

    def test_first_occurrence_wins(self):
        text = """ACTION: first-action
RESULT: success
ACTION: second-action
RESULT: failure"""
        fields = parse_output(text)
        assert fields["action"] == "first-action"
        assert fields["result"] == "success"


class TestUpdateState:
    def _make_sm(self, tmp_path, error_count=0):
        """Create a real StateManager pointing at a temp state file."""
        from commander.state_manager import StateManager
        state_path = tmp_path / "state.yml"
        state = {
            "version": 1,
            "last_action": {"type": "none", "timestamp": None, "result": None, "detail": None},
            "error_count": error_count,
            "budget": {
                "llm_calls_today": 0,
                "max_llm_calls_per_day": 24,
                "llm_calls_window": [],
                "max_llm_calls_per_window": 8,
                "wakeups_today": 0,
                "last_reset_date": "2026-07-19",
            },
            "stop_reason": None,
        }
        state_path.write_text(
            yaml.dump(state, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )
        sm = StateManager(str(state_path))
        return sm

    def test_success_resets_error_count(self, tmp_path):
        sm = self._make_sm(tmp_path, error_count=3)
        fields = {"action": "review-pr", "result": "success", "detail": "OK"}
        update_state(fields, sm)
        assert sm.get("error_count") == 0
        assert sm.get("last_action.type") == "review-pr"
        assert sm.get("last_action.result") == "success"

    def test_failure_increments_error_count(self, tmp_path):
        sm = self._make_sm(tmp_path, error_count=2)
        fields = {"action": "review-pr", "result": "failure", "detail": "CI failed"}
        update_state(fields, sm)
        assert sm.get("error_count") == 3

    def test_skipped_does_not_change_error_count(self, tmp_path):
        sm = self._make_sm(tmp_path, error_count=1)
        fields = {"action": "no-action-needed", "result": "skipped", "detail": "Row 8"}
        update_state(fields, sm)
        assert sm.get("error_count") == 1
        assert sm.get("last_action.type") == "no-action-needed"

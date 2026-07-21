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

class TestWriteProposals:
    def test_single_proposal(self, tmp_path, monkeypatch, capsys):
        from commander.parse_output import write_proposals

        # Mock __file__ so repo_root resolves to tmp_path
        monkeypatch.setattr("commander.parse_output.__file__", str(tmp_path / "commander" / "parse_output.py"))

        text = """PROPOSAL_FILE: commander/proposals/2026-07-22/tasks.yml
<<<CONTENT
night: "2026-07-22"
turn1:
  - id: "T1-01"
>>>END_PROPOSAL"""

        write_proposals(text)

        target_file = tmp_path / "commander" / "proposals" / "2026-07-22" / "tasks.yml"
        assert target_file.exists()
        assert target_file.read_text(encoding="utf-8") == 'night: "2026-07-22"\nturn1:\n  - id: "T1-01"'

        out, err = capsys.readouterr()
        assert "PROPOSAL: wrote commander/proposals/2026-07-22/tasks.yml" in out
        assert err == ""

    def test_multiple_proposals(self, tmp_path, monkeypatch, capsys):
        from commander.parse_output import write_proposals
        monkeypatch.setattr("commander.parse_output.__file__", str(tmp_path / "commander" / "parse_output.py"))

        text = """PROPOSAL_FILE: commander/proposals/2026-07-22/tasks.yml
<<<CONTENT
night: "2026-07-22"
>>>END_PROPOSAL
Some random text here
PROPOSAL_FILE: commander/proposals/2026-07-22/T1-01.md
<<<CONTENT
# Task 1
>>>END_PROPOSAL
PROPOSAL_FILE: commander/proposals/2026-07-22/T2-01.md
<<<CONTENT
# Task 2
>>>END_PROPOSAL"""

        write_proposals(text)

        proposals_dir = tmp_path / "commander" / "proposals" / "2026-07-22"
        assert (proposals_dir / "tasks.yml").read_text(encoding="utf-8") == 'night: "2026-07-22"'
        assert (proposals_dir / "T1-01.md").read_text(encoding="utf-8") == '# Task 1'
        assert (proposals_dir / "T2-01.md").read_text(encoding="utf-8") == '# Task 2'

    def test_reject_invalid_path_outside_proposals(self, tmp_path, monkeypatch, capsys):
        from commander.parse_output import write_proposals
        monkeypatch.setattr("commander.parse_output.__file__", str(tmp_path / "commander" / "parse_output.py"))

        text = """PROPOSAL_FILE: .nightly/tasks.yml
<<<CONTENT
hacked
>>>END_PROPOSAL"""
        write_proposals(text)

        assert not (tmp_path / ".nightly" / "tasks.yml").exists()
        out, err = capsys.readouterr()
        assert "WARN: Rejected proposal path outside commander/proposals/: .nightly/tasks.yml" in err

    def test_reject_directory_traversal(self, tmp_path, monkeypatch, capsys):
        from commander.parse_output import write_proposals
        monkeypatch.setattr("commander.parse_output.__file__", str(tmp_path / "commander" / "parse_output.py"))

        text = """PROPOSAL_FILE: commander/proposals/../../.nightly/tasks.yml
<<<CONTENT
hacked
>>>END_PROPOSAL"""
        write_proposals(text)

        assert not (tmp_path / ".nightly" / "tasks.yml").exists()
        out, err = capsys.readouterr()
        assert "WARN: Rejected proposal path with directory traversal:" in err

    def test_no_proposals_does_not_break_existing_behavior(self):
        from commander.parse_output import parse_output
        text = """ACTION: read
RESULT: success"""
        fields = parse_output(text)
        assert fields["action"] == "read"
        assert fields["result"] == "success"

    def test_mixed_output(self, tmp_path, monkeypatch):
        from commander.parse_output import parse_output, write_proposals
        monkeypatch.setattr("commander.parse_output.__file__", str(tmp_path / "commander" / "parse_output.py"))

        text = """ACTION: review-pr
RESULT: success
DETAIL: PR looks good
PROPOSAL_FILE: commander/proposals/2026-07-22/tasks.yml
<<<CONTENT
night: "2026-07-22"
>>>END_PROPOSAL"""

        # Test parsing fields still works
        fields = parse_output(text)
        assert fields["action"] == "review-pr"
        assert fields["result"] == "success"

        # Test proposal writing still works
        write_proposals(text)
        target_file = tmp_path / "commander" / "proposals" / "2026-07-22" / "tasks.yml"
        assert target_file.exists()
        assert target_file.read_text(encoding="utf-8") == 'night: "2026-07-22"'

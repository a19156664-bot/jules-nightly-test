"""Tests for dashboard API endpoints (/api/state, /api/budget, /api/signal)."""
from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from fastapi.testclient import TestClient

from webui.app import app

client = TestClient(app)


def _make_state(tmp_path: Path, overrides: dict | None = None) -> Path:
    """Write a minimal state.yml and return its path."""
    state = {
        "version": 1,
        "model": "claude-opus-4-8",
        "phase": "P3",
        "loop_status": "idle",
        "last_action": {"type": "none", "timestamp": None, "result": None, "detail": None},
        "current_night": "2026-07-19",
        "turn": "complete",
        "pending_reviews": [],
        "pending_tasks": [],
        "error_count": 0,
        "budget": {
            "llm_calls_today": 1,
            "max_llm_calls_per_day": 24,
            "llm_calls_window": [],
            "max_llm_calls_per_window": 8,
            "wakeups_today": 5,
            "last_reset_date": "2026-07-19",
        },
        "stop_reason": None,
    }
    if overrides:
        state.update(overrides)
    p = tmp_path / "state.yml"
    p.write_text(yaml.dump(state, default_flow_style=False, allow_unicode=True), encoding="utf-8")
    return p


# ── /api/state ──────────────────────────────────────────────────────────────

class TestApiState:
    def test_returns_full_state(self, tmp_path):
        state_path = _make_state(tmp_path)
        with patch("webui.app.STATE_YML_PATH", state_path):
            resp = client.get("/api/state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["phase"] == "P3"
        assert data["current_night"] == "2026-07-19"
        assert data["turn"] == "complete"
        assert "budget" in data

    def test_missing_state_returns_404(self, tmp_path):
        missing = tmp_path / "nonexistent.yml"
        with patch("webui.app.STATE_YML_PATH", missing):
            resp = client.get("/api/state")
        assert resp.status_code == 404


# ── /api/budget ─────────────────────────────────────────────────────────────

class TestApiBudget:
    def test_returns_budget_block(self, tmp_path):
        state_path = _make_state(tmp_path)
        with patch("webui.app.STATE_YML_PATH", state_path):
            resp = client.get("/api/budget")
        assert resp.status_code == 200
        data = resp.json()
        assert data["llm_calls_today"] == 1
        assert data["max_llm_calls_per_day"] == 24
        assert data["max_llm_calls_per_window"] == 8

    def test_missing_budget_key_returns_500(self, tmp_path):
        p = tmp_path / "state.yml"
        p.write_text("version: 1\nturn: complete\n", encoding="utf-8")
        with patch("webui.app.STATE_YML_PATH", p):
            resp = client.get("/api/budget")
        assert resp.status_code == 500


# ── /api/signal ─────────────────────────────────────────────────────────────

class TestApiSignal:
    def test_green_when_normal(self, tmp_path):
        state_path = _make_state(tmp_path)
        with patch("webui.app.STATE_YML_PATH", state_path):
            resp = client.get("/api/signal")
        assert resp.status_code == 200
        data = resp.json()
        assert data["signal"] == "green"

    def test_red_when_stop_reason_set(self, tmp_path):
        state_path = _make_state(tmp_path, {"stop_reason": "human-requested-stop"})
        with patch("webui.app.STATE_YML_PATH", state_path):
            resp = client.get("/api/signal")
        data = resp.json()
        assert data["signal"] == "red"
        assert "human-requested-stop" in data["reason"]

    def test_red_when_error_count_high(self, tmp_path):
        state_path = _make_state(tmp_path, {"error_count": 5})
        with patch("webui.app.STATE_YML_PATH", state_path):
            resp = client.get("/api/signal")
        data = resp.json()
        assert data["signal"] == "red"
        assert "error_count" in data["reason"]

    def test_yellow_when_pending_reviews(self, tmp_path):
        state_path = _make_state(tmp_path, {"pending_reviews": [11]})
        with patch("webui.app.STATE_YML_PATH", state_path):
            resp = client.get("/api/signal")
        data = resp.json()
        assert data["signal"] == "yellow"
        assert "pending_reviews" in data["reason"]

    def test_yellow_when_pending_tasks(self, tmp_path):
        state_path = _make_state(tmp_path, {"pending_tasks": ["T1-01"]})
        with patch("webui.app.STATE_YML_PATH", state_path):
            resp = client.get("/api/signal")
        data = resp.json()
        assert data["signal"] == "yellow"
        assert "pending_tasks" in data["reason"]

    def test_red_takes_priority_over_yellow(self, tmp_path):
        state_path = _make_state(tmp_path, {
            "stop_reason": "consecutive-errors",
            "pending_reviews": [11],
        })
        with patch("webui.app.STATE_YML_PATH", state_path):
            resp = client.get("/api/signal")
        data = resp.json()
        assert data["signal"] == "red"

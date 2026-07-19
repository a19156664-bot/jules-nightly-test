"""FastAPI application for configuring the nightly batch pipeline."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from webui.models import Manifest

TASKS_YML_PATH = Path(".nightly/tasks.yml")
STATE_YML_PATH = Path("commander/state.yml")

app = FastAPI(
    title="jules-nightly-webui",
    description="Local Web UI for configuring the nightly batch pipeline",
    version="0.2.0",
)


# ---------------------------------------------------------------------------
# Existing endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe used to confirm the app boots correctly."""
    return {"status": "ok"}


@app.get("/tasks")
def get_tasks() -> Manifest:
    """Return the current .nightly/tasks.yml as a validated Manifest."""
    if not TASKS_YML_PATH.exists():
        raise HTTPException(status_code=404, detail="tasks.yml not found")
    try:
        raw = yaml.safe_load(TASKS_YML_PATH.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise HTTPException(
            status_code=500, detail=f"failed to parse tasks.yml: {exc}"
        ) from exc
    if raw is None:
        raise HTTPException(status_code=500, detail="tasks.yml is empty")
    return Manifest.model_validate(raw)


@app.put("/tasks")
async def update_tasks(request: Request) -> dict[str, str]:
    """Update .nightly/tasks.yml with new YAML content."""
    body = await request.body()
    try:
        raw = yaml.safe_load(body.decode("utf-8"))
    except yaml.YAMLError:
        raise HTTPException(status_code=422, detail="invalid yaml")
    if not isinstance(raw, dict):
        raise HTTPException(status_code=422, detail="yaml must be a mapping")
    if not {"night", "turn1", "turn2"}.issubset(raw.keys()):
        raise HTTPException(status_code=422, detail="missing required keys")
    TASKS_YML_PATH.write_bytes(body)
    return {"status": "updated"}


# ---------------------------------------------------------------------------
# Dashboard API (Layer 1) — docs/dashboard-design-layer1.md
# ---------------------------------------------------------------------------

def _load_state() -> dict[str, Any]:
    """Load commander/state.yml and return as dict. Raises HTTPException on failure."""
    if not STATE_YML_PATH.exists():
        raise HTTPException(status_code=404, detail="state.yml not found")
    try:
        data = yaml.safe_load(STATE_YML_PATH.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise HTTPException(
            status_code=500, detail=f"failed to parse state.yml: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail="state.yml is not a mapping")
    return data


@app.get("/api/state")
def api_state() -> dict[str, Any]:
    """Return the full commander/state.yml as JSON.

    This is the same data the commander LLM reads when making decisions,
    ensuring human and LLM see exactly the same state (Single Source of Truth).
    """
    return _load_state()


@app.get("/api/budget")
def api_budget() -> dict[str, Any]:
    """Return only the budget block from state.yml."""
    state = _load_state()
    budget = state.get("budget")
    if budget is None:
        raise HTTPException(status_code=500, detail="budget key missing in state.yml")
    return budget


@app.get("/api/signal")
def api_signal() -> dict[str, str]:
    """Return a 3-value traffic light signal derived from state.yml.

    Signal logic (evaluated in priority order):
      red    — stop_reason is set, or error_count >= 5
      yellow — pending_reviews or pending_tasks are non-empty
      green  — none of the above

    The same logic is described in docs/dashboard-design-layer1.md and
    mirrors the commander constitution's decision table (COMMANDER.MD).
    """
    state = _load_state()

    stop_reason = state.get("stop_reason")
    error_count = state.get("error_count", 0)
    pending_reviews = state.get("pending_reviews", [])
    pending_tasks = state.get("pending_tasks", [])

    if stop_reason is not None:
        return {"signal": "red", "reason": f"stop_reason: {stop_reason}"}
    if error_count >= 5:
        return {"signal": "red", "reason": f"error_count: {error_count}"}
    if pending_reviews:
        return {"signal": "yellow", "reason": f"pending_reviews: {len(pending_reviews)}"}
    if pending_tasks:
        return {"signal": "yellow", "reason": f"pending_tasks: {len(pending_tasks)}"}

    turn = state.get("turn", "unknown")
    loop_status = state.get("loop_status", "unknown")
    return {"signal": "green", "reason": f"turn: {turn}, status: {loop_status}"}
# ---------------------------------------------------------------------------
# Dashboard HTML (Layer 1)
# ---------------------------------------------------------------------------

DASHBOARD_HTML = Path(__file__).parent / "dashboard.html"


@app.get("/", response_class=HTMLResponse)
def dashboard():
    """Serve the Layer 1 dashboard."""
    if not DASHBOARD_HTML.exists():
        return HTMLResponse("<h1>dashboard.html not found</h1>", status_code=404)
    return HTMLResponse(DASHBOARD_HTML.read_text(encoding="utf-8"))
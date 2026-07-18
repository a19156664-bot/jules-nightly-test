"""FastAPI application for configuring the nightly batch pipeline."""
from __future__ import annotations

from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, Request

from webui.models import Manifest

TASKS_YML_PATH = Path(".nightly/tasks.yml")

app = FastAPI(
    title="jules-nightly-webui",
    description="Local Web UI for configuring the nightly batch pipeline",
    version="0.1.0",
)


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

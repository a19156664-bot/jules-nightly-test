"""FastAPI application for configuring the nightly batch pipeline."""
from __future__ import annotations

from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException

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

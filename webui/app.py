"""FastAPI application for configuring the nightly batch pipeline."""
from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(
    title="jules-nightly-webui",
    description="Local Web UI for configuring the nightly batch pipeline",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe used to confirm the app boots correctly."""
    return {"status": "ok"}

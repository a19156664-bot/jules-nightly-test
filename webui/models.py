"""Pydantic models representing the .nightly/tasks.yml schema."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class Task(BaseModel):
    """A single task assigned to Jules within a turn."""

    id: str
    title: str
    risk: str = Field(description="one of: low / medium / high")
    paths: list[str] = Field(default_factory=list)
    prompt: Optional[str] = Field(default=None, description="inline prompt (legacy)")
    prompt_file: Optional[str] = Field(
        default=None, description="path to prompt file, e.g. .nightly/prompts/2026-07-19-T1-01.md"
    )


class Manifest(BaseModel):
    """The full .nightly/tasks.yml document."""

    night: str = Field(description="YYYY-MM-DD, JST night date")
    test_paths: list[str] = Field(default_factory=list)
    protected_paths: list[str] = Field(default_factory=list)
    turn1: list[Task] = Field(default_factory=list)
    turn2: list[Task] = Field(default_factory=list)

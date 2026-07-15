"""Pydantic models representing the .nightly/tasks.yml schema."""
from __future__ import annotations

from pydantic import BaseModel, Field


class Task(BaseModel):
    """A single task assigned to Jules within a turn."""

    id: str
    title: str
    risk: str = Field(description="one of: low / medium / high")
    paths: list[str] = Field(default_factory=list)
    prompt: str


class Manifest(BaseModel):
    """The full .nightly/tasks.yml document."""

    night: str = Field(description="YYYY-MM-DD, JST night date")
    test_paths: list[str] = Field(default_factory=list)
    protected_paths: list[str] = Field(default_factory=list)
    turn1: list[Task] = Field(default_factory=list)
    turn2: list[Task] = Field(default_factory=list)

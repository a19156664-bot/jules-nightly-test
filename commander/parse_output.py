"""Parse the commander LLM output and update state.yml accordingly.

Expected format in the LLM output (may appear anywhere in the text):
    ACTION: <action-name>
    TARGET: <target>
    RESULT: <success | failure | skipped>
    DETAIL: <one-line detail>
    STATE_UPDATE: <description of state change>

Usage:
    python commander/parse_output.py <log-file-path>

Exit codes:
    0 — parsed and updated successfully
    1 — parse failed (error_count incremented)
"""
from __future__ import annotations

import re
import sys
import datetime
from pathlib import Path

# Allow importing sibling modules when run as script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from commander.state_manager import StateManager


FIELD_PATTERN = re.compile(
    r"^(ACTION|TARGET|RESULT|DETAIL|STATE_UPDATE)\s*:\s*(.+)$",
    re.MULTILINE,
)


def parse_output(text: str) -> dict[str, str] | None:
    """Extract ACTION/TARGET/RESULT/DETAIL/STATE_UPDATE from LLM output.

    Returns a dict with lowercase keys, or None if ACTION and RESULT
    are not both found (minimum required fields).
    """
    fields: dict[str, str] = {}
    for match in FIELD_PATTERN.finditer(text):
        key = match.group(1).lower()
        value = match.group(2).strip()
        if key not in fields:  # first occurrence wins
            fields[key] = value

    if "action" not in fields or "result" not in fields:
        return None
    return fields


def update_state(fields: dict[str, str], sm: StateManager) -> None:
    """Write parsed fields into state.yml via StateManager."""
    action = fields.get("action", "unknown")
    result = fields.get("result", "unknown")
    detail = fields.get("detail", "")

    sm.record_action(action, result, detail)

    result_lower = result.lower()
    if result_lower == "failure":
        current = sm.get("error_count") or 0
        sm.update({"error_count": current + 1})
    elif result_lower == "success":
        sm.update({"error_count": 0})


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python commander/parse_output.py <log-file>", file=sys.stderr)
        return 1

    log_path = Path(sys.argv[1])
    if not log_path.exists():
        print(f"Log file not found: {log_path}", file=sys.stderr)
        return 1

    text = log_path.read_text(encoding="utf-8")
    fields = parse_output(text)

    sm = StateManager()

    if fields is None:
        print("WARN: could not parse ACTION/RESULT from LLM output", file=sys.stderr)
        current = sm.get("error_count") or 0
        sm.update({"error_count": current + 1})
        return 1

    update_state(fields, sm)
    print(f"OK: {fields.get('action')} -> {fields.get('result')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

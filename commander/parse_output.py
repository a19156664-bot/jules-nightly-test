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

PROPOSAL_PATTERN = re.compile(
    r"^PROPOSAL_FILE:\s*(.+?)\s*\n<<<CONTENT[ \t]*\n(.*?)?\n?>>>END_PROPOSAL[ \t]*$",
    re.MULTILINE | re.DOTALL,
)


def write_proposals(text: str) -> None:
    """Find PROPOSAL_FILE blocks in the LLM output and write them to disk.

    Safe-guards:
    - Path must not contain '..'
    - Path must start with 'commander/proposals/'
    """
    repo_root = Path(__file__).resolve().parent.parent

    for match in PROPOSAL_PATTERN.finditer(text):
        rel_path_str = match.group(1).strip()
        content = match.group(2)
        if content is None:
            content = ""

        # Validate path
        if ".." in rel_path_str:
            print(f"WARN: Rejected proposal path with directory traversal: {rel_path_str}", file=sys.stderr)
            continue

        if not rel_path_str.startswith("commander/proposals/"):
            print(f"WARN: Rejected proposal path outside commander/proposals/: {rel_path_str}", file=sys.stderr)
            continue

        target_path = repo_root / rel_path_str

        # Ensure it resolves under commander/proposals just to be extra safe
        proposals_dir = repo_root / "commander" / "proposals"
        try:
            target_path_resolved = target_path.resolve()
            proposals_dir_resolved = proposals_dir.resolve()
            if not target_path_resolved.is_relative_to(proposals_dir_resolved):
                print(f"WARN: Rejected proposal path escaping proposals dir: {rel_path_str}", file=sys.stderr)
                continue
        except ValueError:
            print(f"WARN: Invalid proposal path: {rel_path_str}", file=sys.stderr)
            continue

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")
        print(f"PROPOSAL: wrote {rel_path_str}")


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

    # Always try to write proposals first, then process standard action parsing.
    write_proposals(text)

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

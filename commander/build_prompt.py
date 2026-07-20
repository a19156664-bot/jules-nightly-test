import argparse
import sys
from pathlib import Path

from commander.config import COMMANDER_MD, STATE_FILE, resolve_path

def build_prompt(alert_count: int, output_file: str | None = None) -> None:
    """Build the prompt and output to stdout or a file.

    Args:
        alert_count: Number of open alerts to include in the suffix.
        output_file: Path to write the output to. If None, output to stdout.
    """
    commander_md_path = resolve_path(COMMANDER_MD)

    if not commander_md_path.exists():
        sys.exit(1)

    prompt_parts = []

    # 1. COMMANDER.MD
    with open(commander_md_path, "r", encoding="utf-8") as f:
        prompt_parts.append(f.read())

    # 2. state.yml
    state_file_path = resolve_path(STATE_FILE)
    if state_file_path.exists():
        prompt_parts.append("\n---\n## state.yml:\n")
        with open(state_file_path, "r", encoding="utf-8") as f:
            prompt_parts.append(f.read())

    # 3. prompt-suffix.txt
    suffix_path = resolve_path("commander/prompt-suffix.txt")
    if suffix_path.exists():
        prompt_parts.append("\n")
        with open(suffix_path, "r", encoding="utf-8") as f:
            prompt_parts.append(f.read())

    # 4. alert count
    prompt_parts.append(f"\n## 補足情報:\n- open alert 件数: {alert_count}\n")

    final_prompt = "".join(prompt_parts)

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(final_prompt)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        # Use end="" since the parts might already have newlines and we appended correctly
        print(final_prompt, end="")

def main() -> None:
    parser = argparse.ArgumentParser(description="Build commander prompt.")
    parser.add_argument("--alert-count", type=int, default=0, help="Number of open alerts")
    parser.add_argument("--output", type=str, help="Output file path")
    args = parser.parse_args()

    build_prompt(args.alert_count, args.output)

if __name__ == "__main__":
    main()

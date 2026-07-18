import argparse
import sys
import subprocess
import datetime
import yaml
from pathlib import Path

JST = datetime.timezone(datetime.timedelta(hours=9))
VALID_ALERT_TYPES = [
    "budget-exceeded",
    "error-limit",
    "protected-path-violation",
    "runtime-error",
    "manual-stop"
]

def get_state_snapshot():
    state_path = Path("commander/state.yml")
    if not state_path.exists():
        return "state.yml unavailable"
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            content = f.read()
        return f"```yaml\n{content}\n```"
    except Exception:
        return "state.yml unavailable"

def main():
    parser = argparse.ArgumentParser(description="Create or update an alert issue")
    parser.add_argument("--alert-type", required=True, help="Type of the alert")
    parser.add_argument("--summary", required=True, help="1-line summary")
    parser.add_argument("--detail", default="", help="Detail of the alert")

    args = parser.parse_args()

    if args.alert_type not in VALID_ALERT_TYPES:
        print(f"Error: Invalid alert-type '{args.alert_type}'", file=sys.stderr)
        sys.exit(2)

    title = f"[LOOP-ALERT] {args.alert_type}: {args.summary}"
    now_jst = datetime.datetime.now(JST).isoformat()

    body = []
    if args.detail:
        body.append("## Detail")
        body.append(args.detail)
        body.append("")

    body.append("## State Snapshot")
    body.append(get_state_snapshot())
    body.append("")
    body.append(f"**Time:** {now_jst}")

    body_text = "\n".join(body)

    # Check for existing issue
    try:
        # Search for open issues with the same title prefix
        list_cmd = [
            "gh", "issue", "list",
            "--state", "open",
            "--search", f'in:title "[LOOP-ALERT] {args.alert_type}:"',
            "--json", "number",
            "--jq", ".[0].number"
        ]
        res = subprocess.run(list_cmd, capture_output=True, text=True, check=True)
        issue_number = res.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error listing issues: {e.stderr}", file=sys.stderr)
        sys.exit(1)

    if issue_number and issue_number != "null":
        # Comment on existing issue
        comment_cmd = ["gh", "issue", "comment", issue_number, "--body", body_text]
        try:
            subprocess.run(comment_cmd, capture_output=True, text=True, check=True)
            # Fetch URL to output
            url_cmd = ["gh", "issue", "view", issue_number, "--json", "url", "--jq", ".url"]
            url_res = subprocess.run(url_cmd, capture_output=True, text=True, check=True)
            print(url_res.stdout.strip())
            sys.exit(0)
        except subprocess.CalledProcessError as e:
            print(f"Error commenting on issue: {e.stderr}", file=sys.stderr)
            sys.exit(1)
    else:
        # Create new issue
        create_cmd = ["gh", "issue", "create", "--title", title, "--body", body_text, "--label", "loop-alert"]
        try:
            res = subprocess.run(create_cmd, capture_output=True, text=True, check=True)
            print(res.stdout.strip())
            sys.exit(0)
        except subprocess.CalledProcessError:
            # Retry without label
            retry_cmd = ["gh", "issue", "create", "--title", title, "--body", body_text]
            try:
                res = subprocess.run(retry_cmd, capture_output=True, text=True, check=True)
                print(res.stdout.strip())
                sys.exit(0)
            except subprocess.CalledProcessError as e2:
                print(f"Error creating issue: {e2.stderr}", file=sys.stderr)
                sys.exit(1)

if __name__ == "__main__":
    main()

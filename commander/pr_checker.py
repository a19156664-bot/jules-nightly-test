import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

PROTECTED_PATHS = [".nightly", ".github", "AGENTS.md"]

@dataclass
class CheckResult:
    ok: bool
    violations: list[str]

def is_protected(path: Path) -> bool:
    for protected in PROTECTED_PATHS:
        protected_path = Path(protected)
        # Check if the path is the protected file/dir itself or a child of it
        if path == protected_path or protected_path in path.parents:
            return True
    return False

def check_pr(files: list[str], allowed: list[str]) -> CheckResult:
    violations = []

    allowed_paths = [Path(a) for a in allowed]

    for file_str in files:
        # Normalize Windows slashes manually since Path doesn't always do it on non-Windows platforms.
        normalized_str = file_str.replace('\\', '/')
        path = Path(normalized_str)

        # Check 1: protected_paths violation
        if is_protected(path):
            violations.append(f"Protected path violation: {file_str}")

        # Check 3: .egg-info inclusion
        if ".egg-info" in path.parts or any(p.endswith(".egg-info") for p in path.parts):
            violations.append(f".egg-info inclusion violation: {file_str}")

        # Check 2: Scope violation
        # A file is allowed if it is relative to any of the allowed paths
        is_allowed = False
        for a_path in allowed_paths:
            if path == a_path or a_path in path.parents:
                is_allowed = True
                break

        if not is_allowed:
            violations.append(f"Scope violation: {file_str} is not in allowed paths {allowed}")

    return CheckResult(ok=len(violations) == 0, violations=violations)

def main():
    parser = argparse.ArgumentParser(description="PR Checker for mechanical constraints")
    parser.add_argument("--files", nargs="*", default=[], help="List of changed file paths")
    parser.add_argument("--allowed", nargs="*", default=[], help="List of allowed paths (scope)")

    args = parser.parse_args()

    result = check_pr(args.files, args.allowed)
    if result.ok:
        print("All checks passed.")
        sys.exit(0)
    else:
        print("PR checks failed with the following violations:")
        for v in result.violations:
            print(f"- {v}")
        sys.exit(1)

if __name__ == "__main__":
    main()

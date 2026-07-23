import argparse
import os
import re
import sys
import yaml
from pathlib import Path

PROTECTED_PATHS = [".nightly/", ".github/"]
EXACT_PROTECTED_PATHS = ["AGENTS.md"]
VALID_RISKS = {"low", "medium", "high"}

def validate_proposal(proposal_dir_str):
    errors = []

    proposal_dir = Path(proposal_dir_str)

    if not proposal_dir.is_dir():
        errors.append(f"Proposal directory does not exist or is not a directory: {proposal_dir_str}")
        return errors

    tasks_yml_path = proposal_dir / "tasks.yml"
    if not tasks_yml_path.is_file():
        errors.append(f"tasks.yml not found in {proposal_dir_str}")
        return errors

    try:
        with open(tasks_yml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        errors.append(f"Failed to parse tasks.yml as YAML: {e}")
        return errors

    if not isinstance(data, dict):
        errors.append("tasks.yml must contain a YAML dictionary")
        return errors

    required_keys = {"night", "turn1", "turn2", "protected_paths"}
    missing_keys = required_keys - set(data.keys())
    if missing_keys:
        errors.append(f"tasks.yml is missing required keys: {', '.join(missing_keys)}")

    night = data.get("night")
    is_night_valid = False
    if night is not None:
        if not isinstance(night, str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", night):
            errors.append(f"Invalid night format: {night}. Must be YYYY-MM-DD.")
        else:
            is_night_valid = True

    dir_name = proposal_dir.name
    if re.match(r"^\d{4}-\d{2}-\d{2}$", dir_name) and is_night_valid:
        if night != dir_name:
            errors.append(f"night '{night}' does not match proposal directory name '{dir_name}'")

    seen_ids = set()

    for turn in ["turn1", "turn2"]:
        tasks = data.get(turn)
        if tasks is not None:
            if not isinstance(tasks, list):
                errors.append(f"'{turn}' must be a list of tasks")
                continue

            for i, task in enumerate(tasks):
                if not isinstance(task, dict):
                    errors.append(f"Task at index {i} in {turn} is not a dictionary")
                    continue

                actual_task_id = task.get("id")
                if isinstance(actual_task_id, str):
                    expected_prefix = f"T{turn[-1]}-"
                    if not actual_task_id.startswith(expected_prefix):
                        errors.append(f"Task {actual_task_id} in {turn} has id that does not match turn prefix '{expected_prefix}'")

                    if actual_task_id in seen_ids:
                        errors.append(f"Duplicate task id across proposal: {actual_task_id}")
                    else:
                        seen_ids.add(actual_task_id)

                task_id = actual_task_id if actual_task_id is not None else f"unknown at index {i}"

                # Check required task fields
                required_task_keys = {"id", "title", "risk", "paths", "prompt_file"}
                missing_task_keys = required_task_keys - set(task.keys())
                if missing_task_keys:
                    errors.append(f"Task {task_id} in {turn} is missing required fields: {', '.join(missing_task_keys)}")

                risk = task.get("risk")
                if risk is not None and risk not in VALID_RISKS:
                    errors.append(f"Task {task_id} in {turn} has invalid risk '{risk}'. Must be one of {', '.join(VALID_RISKS)}.")

                paths = task.get("paths", [])
                if isinstance(paths, list):
                    for path in paths:
                        if not isinstance(path, str):
                            errors.append(f"Task {task_id} in {turn} contains a non-string path")
                            continue

                        is_protected = False
                        for p_path in PROTECTED_PATHS:
                            if path.startswith(p_path):
                                is_protected = True
                                break
                        if not is_protected and path in EXACT_PROTECTED_PATHS:
                            is_protected = True

                        if is_protected:
                            errors.append(f"Task {task_id} in {turn} contains protected path: {path}")

                prompt_file = task.get("prompt_file")
                if prompt_file is not None and isinstance(prompt_file, str):
                    # extract the file name based on Tx-xx.md
                    match = re.search(r'(T\d+-\d+\.md)$', prompt_file)
                    if match:
                        expected_filename = match.group(1)
                        expected_filepath = proposal_dir / expected_filename
                        if not expected_filepath.is_file():
                            errors.append(f"Task {task_id} in {turn} specifies prompt_file '{prompt_file}', but {expected_filename} does not exist in {proposal_dir_str}")
                        else:
                            try:
                                with open(expected_filepath, "r", encoding="utf-8") as pf:
                                    lines = [line.strip() for line in pf.readlines()]
                                required_sections = ["## 完了条件", "## 変更可能ファイル", "## 変更禁止ファイル"]
                                for section in required_sections:
                                    if section not in lines:
                                        errors.append(f"{expected_filename} is missing required section: {section}")
                            except Exception as e:
                                errors.append(f"Failed to read {expected_filename}: {e}")
                    else:
                        errors.append(f"Task {task_id} in {turn} specifies prompt_file '{prompt_file}', which does not end with 'Tx-xx.md'")

    return errors

def main():
    parser = argparse.ArgumentParser(description="Validate a proposal directory")
    parser.add_argument("proposal_dir", help="Path to the proposal directory")
    args = parser.parse_args()

    errors = validate_proposal(args.proposal_dir)

    if not errors:
        print("VALIDATION: PASS")
        sys.exit(0)
    else:
        print("VALIDATION: FAIL")
        for error in errors:
            print(f"- {error}")
        sys.exit(1)

if __name__ == "__main__":
    main()
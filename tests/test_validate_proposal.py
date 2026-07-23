import pytest
import yaml
from pathlib import Path
import subprocess
import sys

def run_validator(proposal_dir):
    """Helper to run the validator script and return (returncode, stdout, stderr)"""
    result = subprocess.run(
        [sys.executable, "-m", "commander.validate_proposal", str(proposal_dir)],
        capture_output=True,
        text=True
    )
    return result

def create_proposal(tmp_path, tasks_data=None, prompt_files=None, dir_name="proposal"):
    proposal_dir = tmp_path / dir_name
    proposal_dir.mkdir(parents=True, exist_ok=True)

    if tasks_data is not None:
        with open(proposal_dir / "tasks.yml", "w", encoding="utf-8") as f:
            yaml.dump(tasks_data, f)

    if prompt_files:
        for p_file in prompt_files:
            content = "## 完了条件\n## 変更可能ファイル\n## 変更禁止ファイル\n"
            if isinstance(p_file, tuple):
                filename, custom_content = p_file
                with open(proposal_dir / filename, "w", encoding="utf-8") as f:
                    f.write(custom_content)
            else:
                with open(proposal_dir / p_file, "w", encoding="utf-8") as f:
                    f.write(content)

    return proposal_dir

@pytest.fixture
def valid_tasks_data():
    return {
        "night": "2026-07-22",
        "turn1": [
            {
                "id": "T1-01",
                "title": "Task 1",
                "risk": "low",
                "paths": ["src/app.py"],
                "prompt_file": ".nightly/prompts/2026-07-22-T1-01.md"
            }
        ],
        "turn2": [
            {
                "id": "T2-01",
                "title": "Task 2",
                "risk": "medium",
                "paths": ["src/utils.py"],
                "prompt_file": ".nightly/prompts/2026-07-22-T2-01.md"
            }
        ],
        "protected_paths": [".nightly/", ".github/", "AGENTS.md"]
    }


def test_valid_proposal(tmp_path, valid_tasks_data):
    proposal_dir = create_proposal(tmp_path, valid_tasks_data, ["T1-01.md", "T2-01.md"])
    result = run_validator(proposal_dir)
    assert result.returncode == 0
    assert "VALIDATION: PASS" in result.stdout

def test_task_id_turn_prefix_mismatch(tmp_path, valid_tasks_data):
    valid_tasks_data["turn2"][0]["id"] = "T1-99"
    proposal_dir = create_proposal(tmp_path, valid_tasks_data, ["T1-01.md", "T2-01.md"])
    result = run_validator(proposal_dir)
    assert result.returncode == 1
    assert "VALIDATION: FAIL" in result.stdout
    assert "- Task T1-99 in turn2 has id that does not match turn prefix 'T2-'" in result.stdout

def test_duplicate_task_id_across_proposal(tmp_path, valid_tasks_data):
    valid_tasks_data["turn2"][0]["id"] = "T1-01"
    proposal_dir = create_proposal(tmp_path, valid_tasks_data, ["T1-01.md", "T2-01.md"])
    result = run_validator(proposal_dir)
    assert result.returncode == 1
    assert "VALIDATION: FAIL" in result.stdout
    assert "- Duplicate task id across proposal: T1-01" in result.stdout

def test_missing_required_section_in_prompt(tmp_path, valid_tasks_data):
    proposal_dir = create_proposal(
        tmp_path,
        valid_tasks_data,
        [
            "T1-01.md",
            ("T2-01.md", "## 完了条件\n## 変更可能ファイル\n")
        ]
    )
    result = run_validator(proposal_dir)
    assert result.returncode == 1
    assert "VALIDATION: FAIL" in result.stdout
    assert "- T2-01.md is missing required section: ## 変更禁止ファイル" in result.stdout

def test_protected_paths_in_paths(tmp_path, valid_tasks_data):
    valid_tasks_data["turn1"][0]["paths"].append(".nightly/foo.py")
    proposal_dir = create_proposal(tmp_path, valid_tasks_data, ["T1-01.md", "T2-01.md"])
    result = run_validator(proposal_dir)
    assert result.returncode == 1
    assert "VALIDATION: FAIL" in result.stdout
    assert "- Task T1-01 in turn1 contains protected path: .nightly/foo.py" in result.stdout

def test_github_in_paths(tmp_path, valid_tasks_data):
    valid_tasks_data["turn2"][0]["paths"].append(".github/workflows/ci.yml")
    proposal_dir = create_proposal(tmp_path, valid_tasks_data, ["T1-01.md", "T2-01.md"])
    result = run_validator(proposal_dir)
    assert result.returncode == 1
    assert "VALIDATION: FAIL" in result.stdout
    assert "- Task T2-01 in turn2 contains protected path: .github/workflows/ci.yml" in result.stdout

def test_agents_md_in_paths(tmp_path, valid_tasks_data):
    valid_tasks_data["turn1"][0]["paths"].append("AGENTS.md")
    proposal_dir = create_proposal(tmp_path, valid_tasks_data, ["T1-01.md", "T2-01.md"])
    result = run_validator(proposal_dir)
    assert result.returncode == 1
    assert "VALIDATION: FAIL" in result.stdout
    assert "- Task T1-01 in turn1 contains protected path: AGENTS.md" in result.stdout

def test_invalid_risk_value(tmp_path, valid_tasks_data):
    valid_tasks_data["turn1"][0]["risk"] = "critical"
    proposal_dir = create_proposal(tmp_path, valid_tasks_data, ["T1-01.md", "T2-01.md"])
    result = run_validator(proposal_dir)
    assert result.returncode == 1
    assert "VALIDATION: FAIL" in result.stdout
    assert "has invalid risk 'critical'" in result.stdout

def test_missing_required_keys(tmp_path, valid_tasks_data):
    del valid_tasks_data["protected_paths"]
    proposal_dir = create_proposal(tmp_path, valid_tasks_data, ["T1-01.md", "T2-01.md"])
    result = run_validator(proposal_dir)
    assert result.returncode == 1
    assert "VALIDATION: FAIL" in result.stdout
    assert "missing required keys: protected_paths" in result.stdout

def test_missing_prompt_file(tmp_path, valid_tasks_data):
    proposal_dir = create_proposal(tmp_path, valid_tasks_data, ["T1-01.md"])
    result = run_validator(proposal_dir)
    assert result.returncode == 1
    assert "VALIDATION: FAIL" in result.stdout
    assert "does not exist in" in result.stdout

def test_invalid_night_format(tmp_path, valid_tasks_data):
    valid_tasks_data["night"] = "2026/07/22"
    proposal_dir = create_proposal(tmp_path, valid_tasks_data, ["T1-01.md", "T2-01.md"])
    result = run_validator(proposal_dir)
    assert result.returncode == 1
    assert "VALIDATION: FAIL" in result.stdout
    assert "Invalid night format: 2026/07/22" in result.stdout

def test_non_existent_proposal_dir(tmp_path):
    proposal_dir = tmp_path / "nonexistent"
    result = run_validator(proposal_dir)
    assert result.returncode == 1
    assert "VALIDATION: FAIL" in result.stdout
    assert "Proposal directory does not exist" in result.stdout

def test_missing_tasks_yml(tmp_path):
    proposal_dir = create_proposal(tmp_path)
    result = run_validator(proposal_dir)
    assert result.returncode == 1
    assert "VALIDATION: FAIL" in result.stdout
    assert "tasks.yml not found in" in result.stdout

def test_night_matches_directory_name(tmp_path, valid_tasks_data):
    valid_tasks_data["night"] = "2026-07-23"
    proposal_dir = create_proposal(tmp_path, valid_tasks_data, ["T1-01.md", "T2-01.md"], dir_name="2026-07-23")
    result = run_validator(proposal_dir)
    assert result.returncode == 0
    assert "VALIDATION: PASS" in result.stdout

def test_night_mismatches_directory_name(tmp_path, valid_tasks_data):
    valid_tasks_data["night"] = "2026-07-21"
    proposal_dir = create_proposal(tmp_path, valid_tasks_data, ["T1-01.md", "T2-01.md"], dir_name="2026-07-23")
    result = run_validator(proposal_dir)
    assert result.returncode == 1
    assert "VALIDATION: FAIL" in result.stdout
    assert "does not match proposal directory name" in result.stdout

def test_night_mismatch_ignored_for_non_date_directory(tmp_path, valid_tasks_data):
    valid_tasks_data["night"] = "2026-07-21"
    proposal_dir = create_proposal(tmp_path, valid_tasks_data, ["T1-01.md", "T2-01.md"], dir_name="2026-07-23.archived")
    result = run_validator(proposal_dir)
    assert result.returncode == 0
    assert "VALIDATION: PASS" in result.stdout
import pytest
from commander.pr_checker import check_pr, CheckResult

def test_protected_violation_nightly():
    result = check_pr(files=[".nightly/tasks.yml"], allowed=[".nightly/"])
    assert not result.ok
    assert any("Protected path violation" in v for v in result.violations)

def test_protected_violation_github():
    result = check_pr(files=[".github/workflows/x.yml"], allowed=[".github/"])
    assert not result.ok
    assert any("Protected path violation" in v for v in result.violations)

def test_scope_violation():
    result = check_pr(files=["commander/x.py"], allowed=["webui/"])
    assert not result.ok
    assert any("Scope violation" in v for v in result.violations)

def test_egg_info_violation():
    result = check_pr(files=["src/my_package.egg-info/PKG-INFO"], allowed=["src/"])
    assert not result.ok
    assert any(".egg-info inclusion violation" in v for v in result.violations)

def test_all_normal():
    result = check_pr(files=["webui/main.py", "webui/components/button.py"], allowed=["webui/"])
    assert result.ok
    assert len(result.violations) == 0

def test_multiple_violations():
    result = check_pr(
        files=[".nightly/tasks.yml", "commander/x.py", "my_pkg.egg-info/SOURCES.txt"],
        allowed=["webui/"]
    )
    assert not result.ok
    assert len(result.violations) >= 3
    violation_texts = " ".join(result.violations)
    assert "Protected path violation" in violation_texts
    assert "Scope violation" in violation_texts
    assert ".egg-info inclusion violation" in violation_texts

def test_windows_paths():
    result = check_pr(
        files=[r".nightly\tasks.yml", r"commander\x.py"],
        allowed=["webui/"]
    )
    assert not result.ok
    violation_texts = " ".join(result.violations)
    assert "Protected path violation" in violation_texts
    assert "Scope violation" in violation_texts

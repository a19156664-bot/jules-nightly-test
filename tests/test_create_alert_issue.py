import pytest
import subprocess
import sys
from unittest.mock import patch, MagicMock
import commander.create_alert_issue as create_alert_issue

def test_invalid_alert_type(capsys):
    test_args = ["create_alert_issue.py", "--alert-type", "invalid", "--summary", "test"]
    with patch.object(sys, 'argv', test_args):
        with pytest.raises(SystemExit) as e:
            create_alert_issue.main()
        assert e.value.code == 2

    captured = capsys.readouterr()
    assert "Error: Invalid alert-type 'invalid'" in captured.err

@patch('commander.create_alert_issue.subprocess.run')
@patch('commander.create_alert_issue.get_state_snapshot')
def test_create_issue_success(mock_get_state, mock_run, capsys):
    mock_get_state.return_value = "```yaml\nversion: 1\n```"

    # First call: list open issues (returns empty/null)
    list_mock = MagicMock()
    list_mock.stdout = ""
    list_mock.returncode = 0

    # Second call: create issue
    create_mock = MagicMock()
    create_mock.stdout = "https://github.com/repo/issues/1"
    create_mock.returncode = 0

    mock_run.side_effect = [list_mock, create_mock]

    test_args = ["create_alert_issue.py", "--alert-type", "runtime-error", "--summary", "test summary", "--detail", "test detail"]
    with patch.object(sys, 'argv', test_args):
        with pytest.raises(SystemExit) as e:
            create_alert_issue.main()
        assert e.value.code == 0

    # Check that create was called with correct args
    create_args = mock_run.call_args_list[1][0][0]
    assert create_args[0:3] == ["gh", "issue", "create"]
    assert "--title" in create_args
    assert create_args[create_args.index("--title") + 1] == "[LOOP-ALERT] runtime-error: test summary"
    assert "--body" in create_args
    body_content = create_args[create_args.index("--body") + 1]
    assert "test detail" in body_content
    assert "```yaml\nversion: 1\n```" in body_content
    assert "--label" in create_args
    assert create_args[create_args.index("--label") + 1] == "loop-alert"

    captured = capsys.readouterr()
    assert "https://github.com/repo/issues/1" in captured.out

@patch('commander.create_alert_issue.subprocess.run')
def test_create_issue_retry_without_label(mock_run, capsys):
    # First call: list open issues (returns empty/null)
    list_mock = MagicMock()
    list_mock.stdout = ""
    list_mock.returncode = 0

    # Second call: create issue WITH label (fails)
    create_fail_mock = subprocess.CalledProcessError(1, "gh")
    create_fail_mock.stderr = "label not found"

    # Third call: create issue WITHOUT label (succeeds)
    create_success_mock = MagicMock()
    create_success_mock.stdout = "https://github.com/repo/issues/2"
    create_success_mock.returncode = 0

    mock_run.side_effect = [list_mock, create_fail_mock, create_success_mock]

    test_args = ["create_alert_issue.py", "--alert-type", "budget-exceeded", "--summary", "no money"]
    with patch.object(sys, 'argv', test_args):
        with pytest.raises(SystemExit) as e:
            create_alert_issue.main()
        assert e.value.code == 0

    # Verify retry call did not have label
    retry_args = mock_run.call_args_list[2][0][0]
    assert "--label" not in retry_args

    captured = capsys.readouterr()
    assert "https://github.com/repo/issues/2" in captured.out

@patch('commander.create_alert_issue.subprocess.run')
def test_comment_on_existing_issue(mock_run, capsys):
    # First call: list open issues (returns an issue number)
    list_mock = MagicMock()
    list_mock.stdout = "42\n"
    list_mock.returncode = 0

    # Second call: comment on issue
    comment_mock = MagicMock()
    comment_mock.returncode = 0

    # Third call: fetch issue URL
    url_mock = MagicMock()
    url_mock.stdout = "https://github.com/repo/issues/42\n"
    url_mock.returncode = 0

    mock_run.side_effect = [list_mock, comment_mock, url_mock]

    test_args = ["create_alert_issue.py", "--alert-type", "manual-stop", "--summary", "stop it"]
    with patch.object(sys, 'argv', test_args):
        with pytest.raises(SystemExit) as e:
            create_alert_issue.main()
        assert e.value.code == 0

    comment_args = mock_run.call_args_list[1][0][0]
    assert comment_args[0:4] == ["gh", "issue", "comment", "42"]

    captured = capsys.readouterr()
    assert "https://github.com/repo/issues/42" in captured.out

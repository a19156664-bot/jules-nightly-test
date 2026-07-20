import sys
from pathlib import Path

import pytest

from commander.build_prompt import build_prompt


def test_all_files_exist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    # 仮想ファイルシステムのセットアップ
    commander_md = tmp_path / "COMMANDER.md"
    commander_md.write_text("commander md content", encoding="utf-8")

    state_yml = tmp_path / "state.yml"
    state_yml.write_text("state yml content", encoding="utf-8")

    suffix_txt = tmp_path / "prompt-suffix.txt"
    suffix_txt.write_text("suffix txt content", encoding="utf-8")

    def mock_resolve_path(path: str) -> Path:
        if "COMMANDER.MD" in path or "COMMANDER.md" in path:
            return commander_md
        elif "state.yml" in path:
            return state_yml
        elif "prompt-suffix.txt" in path:
            return suffix_txt
        return Path(path)

    monkeypatch.setattr("commander.build_prompt.resolve_path", mock_resolve_path)

    build_prompt(alert_count=5)

    captured = capsys.readouterr()
    expected = (
        "commander md content"
        "\n---\n## state.yml:\n"
        "state yml content"
        "\n"
        "suffix txt content"
        "\n## 補足情報:\n- open alert 件数: 5\n"
    )
    assert captured.out == expected


def test_missing_state_yml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    commander_md = tmp_path / "COMMANDER.md"
    commander_md.write_text("commander md content", encoding="utf-8")

    suffix_txt = tmp_path / "prompt-suffix.txt"
    suffix_txt.write_text("suffix txt content", encoding="utf-8")

    def mock_resolve_path(path: str) -> Path:
        if "COMMANDER.MD" in path or "COMMANDER.md" in path:
            return commander_md
        elif "state.yml" in path:
            return tmp_path / "does_not_exist.yml"
        elif "prompt-suffix.txt" in path:
            return suffix_txt
        return Path(path)

    monkeypatch.setattr("commander.build_prompt.resolve_path", mock_resolve_path)

    build_prompt(alert_count=2)

    captured = capsys.readouterr()
    expected = (
        "commander md content"
        "\n"
        "suffix txt content"
        "\n## 補足情報:\n- open alert 件数: 2\n"
    )
    assert captured.out == expected


def test_missing_prompt_suffix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    commander_md = tmp_path / "COMMANDER.md"
    commander_md.write_text("commander md content", encoding="utf-8")

    state_yml = tmp_path / "state.yml"
    state_yml.write_text("state yml content", encoding="utf-8")

    def mock_resolve_path(path: str) -> Path:
        if "COMMANDER.MD" in path or "COMMANDER.md" in path:
            return commander_md
        elif "state.yml" in path:
            return state_yml
        elif "prompt-suffix.txt" in path:
            return tmp_path / "does_not_exist.txt"
        return Path(path)

    monkeypatch.setattr("commander.build_prompt.resolve_path", mock_resolve_path)

    build_prompt(alert_count=0)

    captured = capsys.readouterr()
    expected = (
        "commander md content"
        "\n---\n## state.yml:\n"
        "state yml content"
        "\n## 補足情報:\n- open alert 件数: 0\n"
    )
    assert captured.out == expected


def test_missing_commander_md(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def mock_resolve_path(path: str) -> Path:
        if "COMMANDER.MD" in path or "COMMANDER.md" in path:
            return tmp_path / "does_not_exist.md"
        return Path(path)

    monkeypatch.setattr("commander.build_prompt.resolve_path", mock_resolve_path)

    with pytest.raises(SystemExit) as exc_info:
        build_prompt(alert_count=0)

    assert exc_info.value.code == 1


def test_alert_count_included(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    commander_md = tmp_path / "COMMANDER.md"
    commander_md.write_text("cmd", encoding="utf-8")

    def mock_resolve_path(path: str) -> Path:
        if "COMMANDER.MD" in path or "COMMANDER.md" in path:
            return commander_md
        return tmp_path / "does_not_exist"

    monkeypatch.setattr("commander.build_prompt.resolve_path", mock_resolve_path)

    build_prompt(alert_count=3)

    captured = capsys.readouterr()
    assert "\n## 補足情報:\n- open alert 件数: 3\n" in captured.out


def test_output_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    commander_md = tmp_path / "COMMANDER.md"
    commander_md.write_text("cmd", encoding="utf-8")

    def mock_resolve_path(path: str) -> Path:
        if "COMMANDER.MD" in path or "COMMANDER.md" in path:
            return commander_md
        return tmp_path / "does_not_exist"

    monkeypatch.setattr("commander.build_prompt.resolve_path", mock_resolve_path)

    output_path = tmp_path / "out.txt"
    build_prompt(alert_count=1, output_file=str(output_path))

    captured = capsys.readouterr()
    assert captured.out == ""  # stdout には出力されない

    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert content == "cmd\n## 補足情報:\n- open alert 件数: 1\n"

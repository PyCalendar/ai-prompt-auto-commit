"""Check that commits detect stale prompt-recording installations."""

import json

import pytest

from ai_prompt_auto_commit import common
from ai_prompt_auto_commit.prepare_repository import prepare_repository
from ai_prompt_auto_commit.unstage import check_recorders


@pytest.fixture
def installed(tmp_path, monkeypatch):
    """Set up the same recorder files that a consuming repository receives."""
    monkeypatch.setattr(common, "_repo_root", lambda: tmp_path)
    prepare_repository()
    return tmp_path


def test_current_recorders_pass(installed):
    """A correctly installed matching release must not block ordinary commits."""
    assert check_recorders() == 0


@pytest.mark.parametrize("assistant", ["claude", "codex"])
@pytest.mark.parametrize("problem", ["missing", "stale", "not_executable"])
def test_invalid_recorder_blocks_commit(installed, assistant, problem, capsys):
    """Missing, stale, or non-executable scripts must lead to actionable repair guidance."""
    script = installed / f".{assistant}" / "hooks" / "record-prompt.py"
    if problem == "missing":
        script.unlink()
    elif problem == "stale":
        script.write_text('HOOK_VERSION = "old"\n', encoding="utf-8")
    else:
        script.chmod(0o644)
    assert check_recorders() == 1
    output = capsys.readouterr().err
    assert str(script.relative_to(installed)) in output
    assert "pre-commit run --hook-stage manual prepare-ai-repository" in output
    prepare_repository()
    assert check_recorders() == 0


@pytest.mark.parametrize("assistant,filename", [("claude", "settings.json"), ("codex", "hooks.json")])
def test_missing_handler_blocks_commit(installed, assistant, filename):
    """A recorder file alone cannot record prompts without its registered handler."""
    config = installed / f".{assistant}" / filename
    config.write_text(json.dumps({"hooks": {"UserPromptSubmit": []}}), encoding="utf-8")
    assert check_recorders() == 1
    prepare_repository()
    assert check_recorders() == 0

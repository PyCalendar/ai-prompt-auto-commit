"""Exercise the installed Codex shell command and the Git prompt lifecycle."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from ai_prompt_auto_commit.prepare_repository import (
    get_default_codex_hooks,
    prepare_repository,
)


@pytest.fixture()
def codex_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "project with spaces"
    subprocess.run(["git", "init", "--quiet", str(root)], check=True)
    monkeypatch.chdir(root)
    prepare_repository()
    return root


def _run_hook(cwd: Path, **overrides: object) -> subprocess.CompletedProcess:
    payload = {
        "hook_event_name": "UserPromptSubmit",
        "session_id": "codex-session",
        "turn_id": "codex-turn",
        "cwd": str(cwd),
        "transcript_path": None,
        "model": "gpt-5.3-codex",
        "prompt": "fix the redirect\nand add a test — café",
        **overrides,
    }
    root = cwd
    while not (root / ".git").is_dir() and root.parent != root:
        root = root.parent
    config = root / ".codex" / "hooks.json"
    settings = json.loads(config.read_text(encoding="utf-8")) if config.is_file() else get_default_codex_hooks()
    command = settings["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
    # Match the installed environment without depending on a system Python.
    env = dict(os.environ, PATH=f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}")
    return subprocess.run(
        ["sh", "-c", command],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=cwd,
        env=env,
    )


def test_installed_hook_runs_from_subdirectory(codex_repo: Path) -> None:
    """Contributors may launch Codex below a checkout's root, so the installed command
    must still record in that repository's prompt queue.
    """
    nested = codex_repo / "src" / "nested directory"
    nested.mkdir(parents=True)
    result = _run_hook(nested)
    assert result.returncode == 0, result.stderr
    assert result.stdout == result.stderr == ""
    prompts = list((codex_repo / ".prompts").glob("*.txt"))
    assert len(prompts) == 1
    assert prompts[0].name.endswith("_gpt-5.3-codex.txt")
    assert prompts[0].read_text(encoding="utf-8") == "fix the redirect\nand add a test — café\n"
    assert not (nested / ".prompts").exists()


@pytest.mark.parametrize("prompt", ["", " \n ", "<task-notification>done</task-notification>"])
def test_installed_hook_skips_empty_and_synthetic_prompts(codex_repo: Path, prompt: str) -> None:
    """Commit attribution must describe human requests rather than empty input or
    machine-generated notifications.
    """
    result = _run_hook(codex_repo, prompt=prompt)
    assert result.returncode == 0
    assert result.stdout == result.stderr == ""
    assert not list((codex_repo / ".prompts").glob("*.txt"))


def test_installed_hook_never_blocks_on_recording_failure(codex_repo: Path) -> None:
    # A directory at the expected filename prevents recording even as root.
    """Prompt recording is supplementary; a filesystem problem must not stop the
    contributor's request from reaching Codex.
    """
    (codex_repo / ".prompts").rmdir()
    (codex_repo / ".prompts").write_text("blocked", encoding="utf-8")
    result = _run_hook(codex_repo)
    assert result.returncode == 0
    assert result.stdout == ""
    assert "record-prompt:" in result.stderr


def test_installed_hook_never_blocks_when_script_is_missing(codex_repo: Path) -> None:
    """Partial setup or a missing installed recorder must not turn a logging failure
    into a rejected user request.
    """
    (codex_repo / ".codex" / "hooks" / "record-prompt.py").unlink()
    result = _run_hook(codex_repo)
    assert result.returncode == 0
    assert result.stdout == result.stderr == ""


def test_hook_outside_git_repository_is_a_noop(tmp_path: Path) -> None:
    """A repository-scoped recorder must not create prompt queues in unrelated
    directories when Git cannot identify a project.
    """
    result = _run_hook(tmp_path)
    assert result.returncode == 0
    assert result.stdout == result.stderr == ""
    assert not (tmp_path / ".prompts").exists()


def test_codex_prompt_is_appended_to_commit_and_archived(codex_repo: Path) -> None:
    """The promised audit trail requires Codex recording, Git message attribution, and
    archival to work together during a real commit.
    """
    result = _run_hook(codex_repo)
    assert result.returncode == 0, result.stderr
    prompt_file, = (codex_repo / ".prompts").glob("*.txt")
    original_content = prompt_file.read_text(encoding="utf-8")

    # Run the package's real Git hook entrypoints in a disposable repository.
    for hook_type, entrypoint in (
        ("prepare-commit-msg", "append-ai-prompts"),
        ("post-commit", "archive-ai-prompts"),
    ):
        hook = codex_repo / ".git" / "hooks" / hook_type
        command = shlex.quote(str(Path(sys.executable).with_name(entrypoint)))
        hook.write_text(
            f'#!/bin/sh\nexec {command} "$@"\n',
            encoding="utf-8",
        )
        hook.chmod(0o755)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com",
         "-c", "commit.gpgsign=false", "-c", "core.hooksPath=.git/hooks",
         "commit", "--allow-empty", "-m", "Fix redirect"],
        cwd=codex_repo, check=True, capture_output=True, text=True,
    )
    commit_message = subprocess.check_output(
        ["git", "log", "-1", "--format=%B"], cwd=codex_repo, text=True, encoding="utf-8"
    )
    assert "AI Prompts:\ngpt-5.3-codex: fix the redirect and add a test — café" in commit_message
    commit_hash = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=codex_repo, text=True
    ).strip()
    assert not prompt_file.exists()
    archived = codex_repo / ".prompts" / "committed" / f"{prompt_file.stem}_{commit_hash}.txt"
    assert archived.read_text(encoding="utf-8") == original_content

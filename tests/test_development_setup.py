"""Exercise make dev in a fresh checkout using the installed development tools."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from ai_prompt_auto_commit.prepare_repository import get_default_hook_script


@pytest.fixture()
def development_repo(tmp_path: Path) -> Path:
    root = tmp_path / "project with spaces"
    subprocess.run(["git", "init", "--quiet", str(root)], check=True)
    source = Path(__file__).resolve().parents[1]
    for filename in ("Makefile", "pyproject.toml", ".gitignore", ".pre-commit-config.yaml"):
        shutil.copyfile(source / filename, root / filename)

    # Reuse installed tools to exercise setup without downloading dependencies.
    # The stamp represents a completed editable install, as on repeated make dev.
    bin_dir = root / ".venv" / "bin"
    bin_dir.mkdir(parents=True)
    for entrypoint in ("pre-commit", "prepare-ai-repository"):
        command = shlex.quote(str(Path(sys.executable).with_name(entrypoint)))
        wrapper = bin_dir / entrypoint
        wrapper.write_text(f'#!/bin/sh\nexec {command} "$@"\n', encoding="utf-8")
        wrapper.chmod(0o755)
    (root / ".venv" / ".installed").touch()
    return root


def _make_dev(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["make", "dev"],
        cwd=root,
        env=dict(os.environ, PRE_COMMIT_HOME=str(root.parent / "pre-commit-cache")),
        capture_output=True,
        text=True,
    )


def test_make_dev_installs_versionable_codex_hooks_with_unstaged_config(
    development_repo: Path,
) -> None:
    """Development setup must prepare hooks for future clones even while contributors
    edit pre-commit configuration; the old runner silently skipped setup.
    """
    root = development_repo
    subprocess.run(["git", "add", ".pre-commit-config.yaml"], cwd=root, check=True)
    config = root / ".pre-commit-config.yaml"
    config.write_text(config.read_text(encoding="utf-8") + "\n# local change\n", encoding="utf-8")

    result = _make_dev(root)

    assert result.returncode == 0, result.stdout + result.stderr
    script = root / ".codex" / "hooks" / "record-prompt.py"
    assert script.read_text(encoding="utf-8") == get_default_hook_script("codex")
    assert os.access(script, os.X_OK)
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard"], cwd=root, text=True
    ).splitlines()
    assert ".codex/hooks.json" in untracked
    assert ".codex/hooks/record-prompt.py" in untracked
    for hook_type in ("pre-commit", "prepare-commit-msg", "post-commit"):
        assert os.access(root / ".git" / "hooks" / hook_type, os.X_OK)
    assert "/hooks" in result.stdout


def test_make_dev_reports_setup_failure(development_repo: Path) -> None:
    # Reproduce an unwritable hook location without depending on permissions.
    """Contributors must receive a failing setup result when hooks cannot be installed,
    rather than being told an incomplete environment is ready.
    """
    (development_repo / ".codex").write_text("not a directory", encoding="utf-8")

    result = _make_dev(development_repo)

    assert result.returncode != 0, result.stdout + result.stderr
    assert ".codex" in result.stderr

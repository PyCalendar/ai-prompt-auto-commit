"""Tests for how prompts are mapped to commits across several commits.

These run the prepare-commit-msg and post-commit steps in sequence, the way
git does, rather than one hook at a time.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from ai_prompt_auto_commit.append import append_to_commit_msg
from ai_prompt_auto_commit.archive import archive

PROMPT = "fix the parser, and update the README in a separate commit"


def _commit(repo: Path, subject: str, commit_hash: str) -> str:
    """Run both hooks for one commit and return the resulting commit message."""
    msg = repo / ".git_commit_editmsg"
    msg.write_text(subject + "\n", encoding="utf-8")
    append_to_commit_msg(msg)
    with patch(
        "ai_prompt_auto_commit.archive.subprocess.check_output",
        return_value=commit_hash + "\n",
    ):
        archive()
    return msg.read_text(encoding="utf-8")


def test_every_commit_from_one_prompt_is_attributed(repo: Path, prompts_dir: Path) -> None:
    """The audit trail must attribute every commit an AI prompt produced, so a
    second commit from the same prompt does not look hand-written.
    """
    (prompts_dir / "2026-11-25T10-00-00_claude-opus-5-5.txt").write_text(
        PROMPT + "\n", encoding="utf-8"
    )

    first = _commit(repo, "fix: parser", "1" * 40)
    second = _commit(repo, "docs: README", "2" * 40)

    assert PROMPT in first
    assert "AI Prompts:" in second

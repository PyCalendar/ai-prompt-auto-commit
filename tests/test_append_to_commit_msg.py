"""Tests for append_to_commit_msg()."""

from __future__ import annotations

import time
from pathlib import Path

from ai_prompt_auto_commit.append import append_to_commit_msg
from ai_prompt_auto_commit.common import PROMPTS_DIRECTORY


def _write_prompt(repo: Path, filename: str, content: str) -> None:
    (repo / PROMPTS_DIRECTORY / filename).write_text(content, encoding="utf-8")


def _commit_msg(repo: Path, initial: str = "Initial commit\n") -> Path:
    path = repo / ".git_commit_editmsg"
    path.write_text(initial, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# basic behaviour
# ---------------------------------------------------------------------------

def test_returns_zero_with_no_prompts(repo: Path) -> None:
    """Ordinary commits must succeed even when no AI assistance needs attribution."""
    msg = _commit_msg(repo)
    assert append_to_commit_msg(msg) == 0


def test_commit_message_unchanged_when_no_prompts(repo: Path) -> None:
    """The audit hook must leave human-only commit messages intact rather than adding
    an empty audit section.
    """
    msg = _commit_msg(repo, "Fix bug\n")
    append_to_commit_msg(msg)
    assert msg.read_text(encoding="utf-8") == "Fix bug\n"


def test_single_prompt_appended(repo: Path) -> None:
    """Commit history must identify the AI request and model that shaped a change,
    which is the package's central audit requirement.
    """
    _write_prompt(repo, "2026-01-01T10-00-00_claude-sonnet-4-6.md", "refactor the auth module")
    msg = _commit_msg(repo)
    append_to_commit_msg(msg)
    content = msg.read_text(encoding="utf-8")
    assert "AI Prompts:" in content
    assert "claude-sonnet-4-6: refactor the auth module" in content


def test_returns_zero_with_prompts(repo: Path) -> None:
    """Adding the required prompt attribution must not make an otherwise valid commit
    fail.
    """
    _write_prompt(repo, "2026-01-01T10-00-00_claude-sonnet-4-6.md", "fix the bug")
    msg = _commit_msg(repo)
    assert append_to_commit_msg(msg) == 0


# ---------------------------------------------------------------------------
# ordering and multiple prompts
# ---------------------------------------------------------------------------

def test_multiple_prompts_appended_in_chronological_order(repo: Path) -> None:
    """The audit trail must preserve the order of requests so readers can follow how a
    change developed.
    """
    _write_prompt(repo, "2026-01-01T10-00-00_claude-sonnet-4-6.md", "first prompt")
    _write_prompt(repo, "2026-01-01T10-01-00_claude-sonnet-4-6.md", "second prompt")
    _write_prompt(repo, "2026-01-01T10-02-00_claude-sonnet-4-6.md", "third prompt")
    msg = _commit_msg(repo)
    append_to_commit_msg(msg)
    content = msg.read_text(encoding="utf-8")
    assert content.index("first prompt") < content.index("second prompt") < content.index("third prompt")


def test_existing_commit_message_preserved(repo: Path) -> None:
    """AI attribution supplements the author's explanation; it must never replace or
    discard that explanation.
    """
    _write_prompt(repo, "2026-01-01T10-00-00_claude-sonnet-4-6.md", "some prompt")
    msg = _commit_msg(repo, "My commit message\n")
    append_to_commit_msg(msg)
    content = msg.read_text(encoding="utf-8")
    assert content.startswith("My commit message\n")
    assert "AI Prompts:" in content


# ---------------------------------------------------------------------------
# content formatting
# ---------------------------------------------------------------------------

def test_multiline_prompt_joined_into_one_line(repo: Path) -> None:
    """Each request must remain a single readable audit entry even when the original
    prompt contains several lines.
    """
    _write_prompt(repo, "2026-01-01T10-00-00_claude-opus-4-6.md", "line one\nline two\nline three")
    msg = _commit_msg(repo)
    append_to_commit_msg(msg)
    content = msg.read_text(encoding="utf-8")
    assert "claude-opus-4-6: line one line two line three" in content


def test_repo_root_stripped_from_prompt_content(repo: Path) -> None:
    """Commit messages must remain useful across clones rather than depending on one
    contributor's absolute checkout path.
    """
    _write_prompt(
        repo,
        "2026-01-01T10-00-00_claude-sonnet-4-6.md",
        f"look at {repo}/README.md for details",
    )
    msg = _commit_msg(repo)
    append_to_commit_msg(msg)
    content = msg.read_text(encoding="utf-8")
    assert str(repo) not in content
    assert "./README.md" in content


def test_model_extracted_from_filename(repo: Path) -> None:
    """The audit trail must retain each prompt's recorded model instead of attributing
    every request to a fixed model.
    """
    _write_prompt(repo, "2026-01-01T10-00-00_claude-haiku-4-5-20251001.md", "write a test")
    msg = _commit_msg(repo)
    append_to_commit_msg(msg)
    assert "claude-haiku-4-5-20251001: write a test" in msg.read_text(encoding="utf-8")


def test_same_second_prompts_are_appended_in_the_order_written(repo: Path) -> None:
    """Requests sharing a timestamp must retain their actual order; sorting sequence-
    numbered filenames puts later requests first.
    """
    _write_prompt(repo, "2026-01-01T10-00-00_claude-opus-5.md", "first")
    time.sleep(0.01)
    _write_prompt(repo, "2026-01-01T10-00-00-001_claude-opus-5.md", "second")
    msg = _commit_msg(repo)
    append_to_commit_msg(msg)
    content = msg.read_text(encoding="utf-8")
    assert content.index("first") < content.index("second")

"""Tests for interceptor.py — _model_from_filename, get_last_used_model, main."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from ai_prompt_auto_commit.interceptor import (
    _model_from_filename,
    get_last_used_model,
    main,
)


@pytest.fixture()
def run_main(repo: Path, monkeypatch: pytest.MonkeyPatch):
    """Return a helper that calls main() with patched argv."""

    def _run(argv: list[str]) -> None:
        monkeypatch.setattr("sys.argv", ["record-ai-prompt"] + argv)
        main()

    return _run


# ---------------------------------------------------------------------------
# _model_from_filename
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("filename, expected", [
    ("2026-04-17T09-22-17_claude-sonnet-4-6.txt", "claude-sonnet-4-6"),
    ("2026-04-1708-49-50-001_raptor-mini-preview.txt", "raptor-mini-preview"),
    ("2026-04-12T20-10-00_claude-sonnet-4-6_f6339613b852fe40de67eea12cfb6ef42401c7ae.md", "claude-sonnet-4-6"),
    ("nounderscore.txt", ""),
    ("", ""),
])
def test_model_from_filename(filename: str, expected: str) -> None:
    """Manual attribution must remain compatible with pending, numbered, and archived
    prompt filenames, without inventing models for malformed names.
    """
    assert _model_from_filename(filename) == expected


# ---------------------------------------------------------------------------
# get_last_used_model
# ---------------------------------------------------------------------------

def test_raises_when_prompts_dir_empty(prompts_dir: Path) -> None:
    """Without prior evidence, model inference must require an explicit model rather
    than silently creating false attribution.
    """
    with pytest.raises(SystemExit, match="no prompt files found"):
        get_last_used_model(prompts_dir)


def test_single_file_in_prompts_dir(prompts_dir: Path) -> None:
    """Manual recording may reuse established model attribution from a pending prompt
    so users need not repeat a known model.
    """
    (prompts_dir / "2026-04-17T10-00-00_gpt-4o.txt").write_text("hello\n")
    assert get_last_used_model(prompts_dir) == "gpt-4o"


def test_single_file_in_committed(prompts_dir: Path, committed_dir: Path) -> None:
    """Committing the pending queue must not erase the model evidence needed for
    subsequent manual recording.
    """
    (committed_dir / "2026-04-12T20-10-00_claude-sonnet-4-6_abc123.md").write_text("x\n")
    assert get_last_used_model(prompts_dir) == "claude-sonnet-4-6"


def test_most_recently_modified_wins(prompts_dir: Path) -> None:
    """Default attribution must follow the most recently recorded model instead of an
    older session's model.
    """
    (prompts_dir / "2026-04-17T09-00-00_old-model.txt").write_text("a\n")
    time.sleep(0.01)
    (prompts_dir / "2026-04-17T10-00-00_new-model.txt").write_text("b\n")
    assert get_last_used_model(prompts_dir) == "new-model"


def test_committed_file_newer_than_prompts_file(prompts_dir: Path, committed_dir: Path) -> None:
    """A newer archived request must remain authoritative even when an older request is
    still pending.
    """
    (prompts_dir / "2026-04-17T09-00-00_old-model.txt").write_text("a\n")
    time.sleep(0.01)
    (committed_dir / "2026-04-17T10-00-00_committed-model_abc.md").write_text("b\n")
    assert get_last_used_model(prompts_dir) == "committed-model"


def test_raises_on_unparseable_filename(prompts_dir: Path) -> None:
    """Malformed historical filenames must produce an actionable attribution error
    rather than an invented model name.
    """
    (prompts_dir / "nounderscore.txt").write_text("x\n")
    with pytest.raises(SystemExit, match="could not extract model name"):
        get_last_used_model(prompts_dir)


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------

def test_explicit_model_writes_file(run_main, prompts_dir: Path) -> None:
    """Users need a working manual fallback that preserves their request and explicitly
    supplied model when automatic hooks are unavailable.
    """
    run_main(["--prompt", "hello", "--model", "my-model"])
    files = list(prompts_dir.glob("*_my-model.txt"))
    assert len(files) == 1
    assert files[0].read_text() == "hello\n"


def test_no_model_uses_last_used(run_main, prompts_dir: Path) -> None:
    """The manual fallback must honor its documented default of reusing the most recent
    recorded model.
    """
    (prompts_dir / "2026-04-17T09-00-00_detected-model.txt").write_text("prior\n")
    run_main(["--prompt", "new prompt"])
    assert len(list(prompts_dir.glob("*_detected-model.txt"))) == 2


def test_no_model_no_prior_files_raises(run_main) -> None:
    """The command must reject ungrounded model inference when neither an explicit
    model nor historical evidence is available.
    """
    with pytest.raises(SystemExit, match="no prompt files found"):
        run_main(["--prompt", "oops"])


def test_next_prompt_filename_reads_the_sequence_not_the_minute(prompts_dir: Path) -> None:
    """Repeated requests need consecutive collision suffixes; parsing a timestamp's
    minute as the sequence breaks the documented naming convention.
    """
    (prompts_dir / "2026-04-17T09-22-17-001_my-model.txt").write_text("a\n")
    from ai_prompt_auto_commit.interceptor import next_prompt_filename

    nxt = next_prompt_filename(prompts_dir, "2026-04-17T09-22-17", "my-model")
    assert nxt.name == "2026-04-17T09-22-17-002_my-model.txt"

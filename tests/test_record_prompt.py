"""Tests for the bundled UserPromptSubmit hook script (data/claude/record_prompt.py).

The scripts in data/claude/ and data/codex/ are installed as standalone files,
so they are loaded straight from package data rather than imported as modules.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

from ai_prompt_auto_commit.prepare_repository import HOOK_SCRIPT_DATA, get_data_path


def _load_hook(assistant: str) -> types.ModuleType:
    path = get_data_path(f"{assistant}/{HOOK_SCRIPT_DATA}")
    spec = importlib.util.spec_from_file_location(f"_{assistant}_record_prompt_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def hook() -> types.ModuleType:
    return _load_hook("claude")


def _payload(**overrides: object) -> dict:
    payload = {
        "hook_event_name": "UserPromptSubmit",
        "prompt": "why does the redirect fail?",
        "source": "user",
        "cwd": ".",
        "transcript_path": "",
    }
    payload.update(overrides)
    return payload


def _transcript(path: Path, entries: list[dict]) -> Path:
    path.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
    return path


def _assistant(model: str, **extra: object) -> dict:
    return {"type": "assistant", "message": {"model": model}, **extra}


# ---------------------------------------------------------------------------
# should_record — only genuine user-authored turns
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("source", ["user", "sdk"])
def test_human_sources_are_recorded(hook, source: str) -> None:
    """The audit trail must include real requests from both interactive users and the
    SDK entrypoint.
    """
    assert hook.should_record(_payload(source=source))


@pytest.mark.parametrize("source", ["system", "loop_wakeup", "schedule_wakeup", "poll_event"])
def test_machine_injected_sources_are_dropped(hook, source: str) -> None:
    """Scheduled wakeups and background messages must not be attributed to the human
    contributor in commit history.
    """
    assert not hook.should_record(_payload(source=source))


def test_missing_source_defaults_to_recording(hook) -> None:
    """Older payloads may omit source metadata, and that rollout difference must not
    cause genuine requests to disappear.
    """
    payload = _payload()
    del payload["source"]
    assert hook.should_record(payload)


@pytest.mark.parametrize("prompt", [
    "<task-notification>\n<task-id>b7cljujii</task-id>\n</task-notification>",
    "<bash-input>pytest -k compat</bash-input>",
    "<bash-stdout>Command did not complete within its 120s timeout</bash-stdout>",
    "<local-command-caveat>Caveat: The messages below were generated</local-command-caveat>",
    "<system-reminder>background context</system-reminder>",
])
def test_synthetic_turns_dropped_even_without_source(hook, prompt: str) -> None:
    """Recognizable machine wrappers must remain excluded when older hook payloads lack
    explicit authorship metadata.
    """
    payload = _payload(prompt=prompt)
    del payload["source"]
    assert not hook.should_record(payload)


@pytest.mark.parametrize("prompt", ["", "   \n  "])
def test_empty_prompt_is_dropped(hook, prompt: str) -> None:
    """Whitespace-only input carries no user request and must not create a misleading
    audit record.
    """
    assert not hook.should_record(_payload(prompt=prompt))


def test_slash_command_is_a_real_prompt(hook) -> None:
    """A contributor's slash command is intentional input and must not be discarded as
    a synthetic notification.
    """
    assert hook.should_record(_payload(prompt="/review-and-push"))


# ---------------------------------------------------------------------------
# model_from_transcript — read the model, never guess it
# ---------------------------------------------------------------------------

def test_model_is_last_assistant_model(hook, tmp_path: Path) -> None:
    """Claude attribution must follow the latest available assistant evidence instead
    of an obsolete or hardcoded model.
    """
    t = _transcript(tmp_path / "t.jsonl", [
        {"type": "user", "message": {"content": "hi"}},
        _assistant("claude-sonnet-4-6"),
        _assistant("claude-opus-5"),
    ])
    assert hook.model_from_transcript(str(t)) == "claude-opus-5"


def test_sidechain_model_is_ignored(hook, tmp_path: Path) -> None:
    """A subagent's model must never replace the main agent's model in the
    contributor's attribution record.
    """
    t = _transcript(tmp_path / "t.jsonl", [
        _assistant("claude-opus-5"),
        _assistant("claude-haiku-4-5-20251001", isSidechain=True),
    ])
    assert hook.model_from_transcript(str(t)) == "claude-opus-5"


def test_synthetic_model_is_ignored(hook, tmp_path: Path) -> None:
    """Synthetic transcript placeholders are not real model evidence and must not
    corrupt attribution.
    """
    t = _transcript(tmp_path / "t.jsonl", [
        _assistant("claude-opus-5"),
        _assistant("<synthetic>"),
    ])
    assert hook.model_from_transcript(str(t)) == "claude-opus-5"


def test_malformed_lines_are_tolerated(hook, tmp_path: Path) -> None:
    """A partially written or malformed transcript line must not prevent using
    otherwise valid model evidence.
    """
    t = tmp_path / "t.jsonl"
    t.write_text('not json\n{"type": "assistant", "message": {"model": "m-1"}}\n{\n', encoding="utf-8")
    assert hook.model_from_transcript(str(t)) == "m-1"


@pytest.mark.parametrize("path", ["", "/nonexistent/transcript.jsonl"])
def test_unreadable_transcript_yields_unknown(hook, path: str) -> None:
    """Missing transcript evidence must produce honest unknown attribution rather than
    a guessed model or a lost request.
    """
    assert hook.model_from_transcript(path) == hook.UNKNOWN_MODEL


def test_transcript_without_assistant_turns_yields_unknown(hook, tmp_path: Path) -> None:
    """Claude has no model evidence before its first answer, so the first request must
    be attributed honestly as unknown.
    """
    t = _transcript(tmp_path / "t.jsonl", [
        {"type": "mode", "mode": "normal"},
        {"type": "user", "message": {"content": "hi"}},
    ])
    assert hook.model_from_transcript(str(t)) == hook.UNKNOWN_MODEL


def test_model_found_beyond_the_tail_window(hook, tmp_path: Path) -> None:
    """Large tool outputs must not erase the model evidence needed for attribution
    merely because the recorder optimizes normal reads to a tail window.
    """
    padding = [{"type": "user", "message": {"content": "x" * 4096}}] * 512
    t = _transcript(tmp_path / "t.jsonl", [_assistant("claude-opus-5")] + padding)
    assert t.stat().st_size > hook.TAIL_BYTES
    assert hook.model_from_transcript(str(t)) == "claude-opus-5"


# ---------------------------------------------------------------------------
# record() — file naming and content
# ---------------------------------------------------------------------------

def test_prompt_written_with_model_from_transcript(hook, tmp_path: Path) -> None:
    """A recorded request must preserve the human's text and associate it with the
    model established by Claude's transcript.
    """
    t = _transcript(tmp_path / "t.jsonl", [_assistant("claude-opus-5")])
    dest = hook.record(_payload(cwd=str(tmp_path), transcript_path=str(t)))
    assert dest is not None
    assert dest.parent == tmp_path / ".prompts"
    assert dest.name.endswith("_claude-opus-5.txt")
    assert dest.read_text(encoding="utf-8") == "why does the redirect fail?\n"


def test_machine_injected_turn_writes_nothing(hook, tmp_path: Path) -> None:
    """Filtering must prevent actual audit-file creation for machine messages, not
    merely classify them without enforcing the decision.
    """
    assert hook.record(_payload(cwd=str(tmp_path), source="system")) is None
    assert not (tmp_path / ".prompts").exists()


def test_second_prompt_in_the_same_second_is_not_overwritten(hook, tmp_path: Path) -> None:
    """Fast consecutive requests must all survive in the audit queue instead of
    overwriting a timestamp collision.
    """
    payload = _payload(cwd=str(tmp_path))
    first = hook.record(payload)
    second = hook.record(dict(payload, prompt="and now?"))
    assert first != second
    assert first.read_text(encoding="utf-8") == "why does the redirect fail?\n"
    assert second.read_text(encoding="utf-8") == "and now?\n"


# ---------------------------------------------------------------------------
# main() — the actual hook contract: JSON on stdin, nothing on stdout
# ---------------------------------------------------------------------------

def _run_hook(payload: dict, cwd: Path, assistant: str = "claude") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(get_data_path(f"{assistant}/{HOOK_SCRIPT_DATA}"))],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=cwd,
    )


@pytest.mark.parametrize("assistant", ["claude", "codex"])
def test_hook_writes_nothing_to_stdout(tmp_path: Path, assistant: str) -> None:
    """Hook stdout becomes extra conversation context, so recording must remain silent
    while still saving the request.
    """
    result = _run_hook(_payload(cwd=str(tmp_path)), tmp_path, assistant)
    assert result.stdout == ""
    assert result.returncode == 0
    assert len(list((tmp_path / ".prompts").glob("*.txt"))) == 1


@pytest.mark.parametrize("assistant", ["claude", "codex"])
def test_hook_survives_garbage_on_stdin(tmp_path: Path, assistant: str) -> None:
    """Malformed hook input must not reject a user request or inject accidental context
    into the assistant's conversation.
    """
    result = subprocess.run(
        [sys.executable, str(get_data_path(f"{assistant}/{HOOK_SCRIPT_DATA}"))],
        input="not json at all",
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert result.stdout == ""


# ---------------------------------------------------------------------------
# never lose a prompt: the hook must fail soft, whatever goes wrong
# ---------------------------------------------------------------------------

def test_hook_command_exits_zero_when_the_script_is_missing(tmp_path: Path) -> None:
    """An absent recorder must not erase the user's request: Python exits 2 for a
    missing script, which Claude treats as a blocked prompt.
    """
    from ai_prompt_auto_commit.prepare_repository import get_default_claude_settings

    command = get_default_claude_settings()["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
    result = subprocess.run(
        ["sh", "-c", command],
        input=json.dumps(_payload()),
        capture_output=True,
        text=True,
        cwd=tmp_path,  # no .claude/hooks/record-prompt.py here
        env={"PATH": os.environ["PATH"]},
    )
    assert result.returncode == 0, result.stderr


def test_unreadable_transcript_yields_unknown_not_a_crash(hook, tmp_path: Path) -> None:
    """Filesystem permissions can deny model evidence, and that must degrade
    attribution rather than crash prompt recording.
    """
    t = _transcript(tmp_path / "t.jsonl", [_assistant("claude-opus-5")])
    t.chmod(0o000)
    try:
        assert hook.model_from_transcript(str(t)) == hook.UNKNOWN_MODEL
    finally:
        t.chmod(0o600)


def test_prompt_still_recorded_when_the_transcript_is_unreadable(hook, tmp_path: Path) -> None:
    """A permission failure while discovering the model must not lose the contributor's
    request; unknown attribution preserves the audit entry.
    """
    t = _transcript(tmp_path / "t.jsonl", [_assistant("claude-opus-5")])
    t.chmod(0o000)
    try:
        dest = hook.record(_payload(cwd=str(tmp_path), transcript_path=str(t)))
    finally:
        t.chmod(0o600)
    assert dest is not None and dest.name.endswith(f"_{hook.UNKNOWN_MODEL}.txt")


@pytest.mark.parametrize("assistant", ["claude", "codex"])
def test_non_utf8_locale_still_records_the_prompt(tmp_path: Path, assistant: str) -> None:
    """The hook's JSON wire format is UTF-8, so a contributor's locale must not corrupt
    non-ASCII request text.
    """
    env = dict(os.environ, LC_ALL="C", LANG="C", PYTHONIOENCODING="", PYTHONUTF8="0")
    env.pop("PYTHONIOENCODING")
    result = subprocess.run(
        [sys.executable, str(get_data_path(f"{assistant}/{HOOK_SCRIPT_DATA}"))],
        input=json.dumps(_payload(prompt="hvorfor feiler kalenderoppslaget for Tromsø?"), ensure_ascii=False).encode("utf-8"),
        capture_output=True,
        cwd=tmp_path,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    written = list((tmp_path / ".prompts").glob("*.txt"))
    assert len(written) == 1
    assert written[0].read_text(encoding="utf-8") == "hvorfor feiler kalenderoppslaget for Tromsø?\n"


@pytest.mark.parametrize("model, expected", [
    ("anthropic/claude-opus-5", "anthropic-claude-opus-5"),
    ("some_model", "some-model"),          # `_` separates timestamp from model
    ("../../escape", "escape"),
])
def test_model_name_is_made_safe_for_a_filename(hook, tmp_path: Path, model: str, expected: str) -> None:
    """Model identifiers must not escape the prompt directory or break the
    timestamp/model filename delimiter used by commit attribution.
    """
    t = _transcript(tmp_path / "t.jsonl", [_assistant(model)])
    dest = hook.record(_payload(cwd=str(tmp_path), transcript_path=str(t)))
    assert dest is not None
    assert dest.parent == tmp_path / ".prompts"
    assert dest.name.endswith(f"_{expected}.txt")


def test_missing_cwd_records_nowhere_at_all(hook, tmp_path: Path) -> None:
    """If the session's directory was deleted, the recorder must not guess another
    checkout and file the user's request under the wrong project.
    """
    gone = tmp_path / "deleted" / "deeply"
    before = sorted(Path.cwd().rglob(".prompts/*.txt"))
    assert hook.record(_payload(cwd=str(gone))) is None
    assert not gone.exists()
    assert sorted(Path.cwd().rglob(".prompts/*.txt")) == before

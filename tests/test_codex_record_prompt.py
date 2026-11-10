"""Behavior of the standalone Codex recorder, independent of the shell wrapper."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import types
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Barrier

import pytest

from ai_prompt_auto_commit.prepare_repository import get_data_path


@pytest.fixture(scope="module")
def codex_hook() -> types.ModuleType:
    path = get_data_path("codex/record_prompt.py")
    spec = importlib.util.spec_from_file_location("_codex_recorder_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _payload(cwd: Path, **overrides: object) -> dict:
    # Real Codex payloads have no `source` field and may have no transcript.
    return {
        "hook_event_name": "UserPromptSubmit",
        "session_id": "codex-session",
        "turn_id": "codex-turn",
        "permission_mode": "default",
        "cwd": str(cwd),
        "transcript_path": None,
        "model": "gpt-5.3-codex",
        "prompt": "fix the redirect\nand add a test",
        **overrides,
    }


@pytest.fixture()
def transcript(tmp_path: Path) -> Path:
    path = tmp_path / "transcript.jsonl"
    entry = {"type": "assistant", "message": {"model": "previous-model"}}
    path.write_text(json.dumps(entry) + "\n", encoding="utf-8")
    return path


def _run_script(raw: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    # Isolated mode ensures the recorder works without the package on sys.path.
    return subprocess.run(
        [sys.executable, "-I", str(get_data_path("codex/record_prompt.py"))],
        input=raw,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=cwd,
    )


def test_first_prompt_without_transcript(codex_hook, tmp_path: Path) -> None:
    """The first request needs accurate attribution too; Codex supplies its active
    model before any transcript exists.
    """
    dest = codex_hook.record(_payload(tmp_path))
    assert dest is not None
    assert dest.name.endswith("_gpt-5.3-codex.txt")
    assert dest.read_text(encoding="utf-8") == "fix the redirect\nand add a test\n"


def test_model_switch_uses_current_payload(codex_hook, tmp_path: Path, transcript: Path) -> None:
    """After a model switch, requests must be attributed to the active model rather
    than stale transcript metadata.
    """
    first = codex_hook.record(_payload(
        tmp_path, model="codex-before-switch", transcript_path=str(transcript)
    ))
    second = codex_hook.record(_payload(
        tmp_path, model="codex-after-switch", transcript_path=str(transcript)
    ))
    assert first.name.endswith("_codex-before-switch.txt")
    assert second.name.endswith("_codex-after-switch.txt")


@pytest.mark.parametrize("model, expected", [
    ("openai/gpt-5.3-codex", "openai-gpt-5.3-codex"),
    ("some_model", "some-model"),
    ("../../escape", "escape"),
    ("", "unknown"),
    ("  ", "unknown"),
    (None, "unknown"),
    (123, "unknown"),
    ([], "unknown"),
    ({}, "unknown"),
])
def test_model_is_safe_and_never_guessed(
    codex_hook, tmp_path: Path, transcript: Path, model, expected: str
) -> None:
    """Untrusted or missing model identifiers must neither escape the prompt directory
    nor fabricate attribution from an unrelated transcript.
    """
    dest = codex_hook.record(_payload(tmp_path, model=model, transcript_path=str(transcript)))
    assert dest is not None
    assert dest.parent == tmp_path / ".prompts"
    assert dest.name.endswith(f"_{expected}.txt")


def test_missing_model_never_reads_transcript(codex_hook, tmp_path: Path, transcript: Path) -> None:
    """Codex and Claude transcripts have different contracts, so missing Codex metadata
    must produce honest unknown attribution.
    """
    payload = _payload(tmp_path, transcript_path=str(transcript))
    del payload["model"]
    dest = codex_hook.record(payload)
    assert dest is not None
    assert dest.name.endswith("_unknown.txt")


@pytest.mark.parametrize("prompt", [None, 123, [], {}])
def test_non_text_prompts_create_no_files(codex_hook, tmp_path: Path, prompt) -> None:
    """Only a human request's text belongs in the audit queue; other JSON values must
    not become misleading prompt records.
    """
    assert codex_hook.record(_payload(tmp_path, prompt=prompt)) is None
    assert not (tmp_path / ".prompts").exists()


@pytest.mark.parametrize("prompt", [
    "  <task-notification>finished</task-notification>",
    "\n<bash-input>pytest</bash-input>",
    "<bash-stdout>passed</bash-stdout>",
    "<bash-stderr>failed</bash-stderr>",
    "<local-command-caveat>generated output</local-command-caveat>",
    "<system-reminder>background context</system-reminder>",
])
def test_synthetic_prompts_create_no_files(codex_hook, tmp_path: Path, prompt: str) -> None:
    """Background notifications and tool output must not be misrepresented as requests
    the contributor wrote.
    """
    assert codex_hook.record(_payload(tmp_path, prompt=prompt)) is None
    assert not (tmp_path / ".prompts").exists()


@pytest.mark.parametrize("source", ["system", "loop_wakeup", "schedule_wakeup", "poll_event"])
def test_machine_sources_create_no_files(codex_hook, tmp_path: Path, source: str) -> None:
    """Explicit machine authorship must exclude a turn from the human prompt audit
    trail even when its text resembles a request.
    """
    assert codex_hook.record(_payload(tmp_path, source=source)) is None
    assert not (tmp_path / ".prompts").exists()


@pytest.mark.parametrize("source", ["user", "sdk", None])
def test_human_sources_are_recorded(codex_hook, tmp_path: Path, source: str | None) -> None:
    """User and SDK requests must remain recordable, including payloads where the
    optional source field is absent.
    """
    dest = codex_hook.record(_payload(tmp_path, source=source))
    assert dest is not None
    assert dest.read_text(encoding="utf-8") == "fix the redirect\nand add a test\n"


@pytest.mark.parametrize("prompt, expected", [
    (
        "  preserve indentation\n\n    café 日本語 🚀  \n\n",
        "  preserve indentation\n\n    café 日本語 🚀  \n",
    ),
    ("/review-and-push", "/review-and-push\n"),
    (
        "Explain what <system-reminder> means in this output",
        "Explain what <system-reminder> means in this output\n",
    ),
])
def test_standalone_script_preserves_user_text(tmp_path: Path, prompt: str, expected: str) -> None:
    """Prompt files are evidence of the original request, so standalone recording must
    retain Unicode, meaningful whitespace, and genuine commands.
    """
    result = _run_script(json.dumps(_payload(tmp_path, prompt=prompt), ensure_ascii=False), tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == result.stderr == ""
    dest, = (tmp_path / ".prompts").glob("*.txt")
    assert dest.read_text(encoding="utf-8") == expected


@pytest.mark.parametrize("raw", ["null", "[]", "123", "true", '{"prompt":'])
def test_invalid_payloads_are_silent_and_create_no_files(tmp_path: Path, raw: str) -> None:
    """Malformed hook input must neither block the user nor inject garbage into the
    conversation or prompt audit trail.
    """
    result = _run_script(raw, tmp_path)
    assert result.returncode == 0
    assert result.stdout == result.stderr == ""
    assert not (tmp_path / ".prompts").exists()


def test_missing_prompt_creates_no_files(tmp_path: Path) -> None:
    """A payload without a user request must not create an empty or invented audit
    entry.
    """
    payload = _payload(tmp_path)
    del payload["prompt"]
    result = _run_script(json.dumps(payload), tmp_path)
    assert result.returncode == 0
    assert result.stdout == result.stderr == ""
    assert not (tmp_path / ".prompts").exists()


def test_write_failure_does_not_block_prompt(tmp_path: Path) -> None:
    # This fails reliably without depending on Unix permissions or the user ID.
    """The recorder itself must exit successfully on storage failures; relying only on
    the shell wrapper would hide a broken hook contract.
    """
    blocked = tmp_path / ".prompts"
    blocked.write_text("existing data", encoding="utf-8")
    result = _run_script(json.dumps(_payload(tmp_path)), tmp_path)
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr.startswith("record-prompt:")
    assert "Traceback" not in result.stderr
    assert blocked.read_text(encoding="utf-8") == "existing data"


def test_payload_directory_selects_repository(tmp_path: Path) -> None:
    """A request must be filed under its session's project, not whichever directory
    happened to launch the recorder process.
    """
    process_dir = tmp_path / "other project"
    process_dir.mkdir()
    root = tmp_path / "target project"
    subprocess.run(["git", "init", "--quiet", str(root)], check=True)
    nested = root / "src"
    nested.mkdir()
    result = _run_script(json.dumps(_payload(nested)), process_dir)
    assert result.returncode == 0, result.stderr
    assert result.stdout == result.stderr == ""
    dest, = (root / ".prompts").glob("*.txt")
    assert dest.read_text(encoding="utf-8") == "fix the redirect\nand add a test\n"
    assert not (nested / ".prompts").exists()
    assert not (process_dir / ".prompts").exists()


def test_missing_directory_does_not_fall_back_to_process_directory(tmp_path: Path) -> None:
    """A deleted project must not cause a request to be misfiled in another checkout
    through a guessed fallback directory.
    """
    missing = tmp_path / "deleted project"
    result = _run_script(json.dumps(_payload(missing)), tmp_path)
    assert result.returncode == 0
    assert result.stdout == result.stderr == ""
    assert not missing.exists()
    assert not (tmp_path / ".prompts").exists()


def test_concurrent_prompts_in_same_second_preserve_every_prompt(
    codex_hook, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Concurrent sessions must retain every request and existing audit record;
    timestamp collisions must never cause data loss.
    """
    class FixedDatetime(datetime):
        @classmethod
        def now(cls):
            return cls(2026, 11, 6, 12, 34, 56)

    monkeypatch.setattr(codex_hook, "datetime", FixedDatetime)
    prompts = tmp_path / ".prompts"
    prompts.mkdir()
    existing = prompts / "2026-11-06T12-34-56_gpt-5.3-codex.txt"
    existing.write_text("previous session\n", encoding="utf-8")
    barrier = Barrier(8)

    def record(index: int) -> Path:
        barrier.wait(timeout=10)
        return codex_hook.record(_payload(tmp_path, prompt=f"prompt {index}"))

    with ThreadPoolExecutor(max_workers=8) as executor:
        paths = list(executor.map(record, range(8)))

    assert len(list(prompts.glob("*.txt"))) == 9
    assert {path.name for path in paths} == {
        f"2026-11-06T12-34-56-{seq:03d}_gpt-5.3-codex.txt" for seq in range(1, 9)
    }
    assert [path.read_text(encoding="utf-8") for path in paths] == [
        f"prompt {index}\n" for index in range(8)
    ]
    assert existing.read_text(encoding="utf-8") == "previous session\n"


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_ide_wrapper_cleaned_before_storage(tmp_path: Path, newline: str) -> None:
    """The standalone Codex recorder must store the human request without IDE
    metadata so prompt files and commit entries contain the same request.
    """
    raw = newline.join([
        "# Context from my IDE setup:", "", "## Active file: README.md", "",
        "## Open tabs:", "- README.md: README.md", "", "## My request:",
        "fix the parser", "and add regression coverage", "",
    ])
    result = _run_script(json.dumps(_payload(tmp_path, prompt=raw)), tmp_path)
    assert result.returncode == 0
    assert result.stdout == ""
    files = list((tmp_path / ".prompts").glob("*.txt"))
    assert len(files) == 1
    assert files[0].read_text(encoding="utf-8") == (
        "fix the parser\nand add regression coverage\n"
    )


@pytest.mark.parametrize("raw", [
    "Explain this heading:\n## My request:\nkeep this text",
    "# Context from my IDE setup:\nNo request delimiter here",
    "# Context from my IDE setup:\n\n## My request:\n",
    "Keep this example:\n# Context from my IDE setup:\n\n## My request:\nexample",
])
def test_cleanup_preserves_unrecognized_prompts(codex_hook, tmp_path: Path, raw: str) -> None:
    """Cleanup must not discard human text resembling an IDE wrapper or remove
    context when no actual request can be recovered.
    """
    dest = codex_hook.record(_payload(tmp_path, prompt=raw))
    assert dest is not None
    assert dest.read_text(encoding="utf-8") == raw.rstrip("\n") + "\n"

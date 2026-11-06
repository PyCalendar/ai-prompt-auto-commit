#!/usr/bin/env python3
"""Codex `UserPromptSubmit` hook: record one prompt in `.prompts/`.

`prepare-ai-repository` installs a copy of this script into a repository as
`.codex/hooks/record-prompt.py` and points `.codex/hooks.json` at it.
Edit the original bundled with ai-prompt-auto-commit, not the installed copy:
the copy is overwritten on every run of `prepare-ai-repository`.

The hook payload arrives as JSON on stdin and the prompt is written to

    <repo root>/.prompts/<timestamp>_<model>.txt

Empty prompts and recognized synthetic turns are skipped. Codex supplies the
active model directly in the hook payload, including on the first prompt and
after a model switch. An absent or invalid model is recorded as `unknown`;
the transcript is never used to infer it.

Nothing is ever written to stdout: for `UserPromptSubmit`, stdout is injected
into the conversation as additional context.  Failures are reported on stderr
and the hook still exits 0, because a recording hook must not block a prompt.

Depends on the standard library only, so that a repository using
ai-prompt-auto-commit needs nothing beyond the Python it already requires.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HOOK_VERSION = "0.1.0"  # replaced with the package version at install time

PROMPTS_DIRECTORY = ".prompts"
FILE_EXTENSION = ".txt"
UNKNOWN_MODEL = "unknown"

# A model name goes into a filename, where `_` separates it from the timestamp
# and `/` would be a directory.  Gateway and proxy setups report ids such as
# "openai/gpt-5.3-codex", so anything outside this set is folded to `-`.
UNSAFE_IN_FILENAME = re.compile(r"[^A-Za-z0-9.@+-]+")

# Codex does not currently supply `source`. If present, accept only known
# human sources; otherwise filter recognized synthetic prefixes below.
HUMAN_SOURCES = frozenset({"user", "sdk"})

# Machine-injected turns are wrapped in one of these tags.  Belt and braces for
# payloads that carry no `source`.
SYNTHETIC_PREFIXES = (
    "<task-notification>",
    "<bash-input>",
    "<bash-stdout>",
    "<bash-stderr>",
    "<local-command-caveat>",
    "<system-reminder>",
)

def _safe_model(model: str) -> str:
    # Leading dots too: a model name must not become a hidden file or "..".
    return UNSAFE_IN_FILENAME.sub("-", model).strip("-.") or UNKNOWN_MODEL


def should_record(payload: dict) -> bool:
    """True when the payload carries a prompt the human actually wrote."""
    source = payload.get("source")
    if source is not None and source not in HUMAN_SOURCES:
        return False
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return False
    return not prompt.lstrip().startswith(SYNTHETIC_PREFIXES)


def repo_root(cwd: str) -> Path | None:
    """The git root containing *cwd*, or *cwd* itself outside a repository.

    None when the payload names a directory that does not exist: guessing
    somewhere else to write would file the prompt under an unrelated project.
    """
    fallback = Path(cwd) if cwd else Path.cwd()
    if not fallback.is_dir():
        return None
    try:
        toplevel = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=fallback,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return fallback
    return Path(toplevel) if toplevel else fallback


def _write_new(prompts_dir: Path, timestamp: str, model: str, text: str) -> Path:
    """Write to `<timestamp>_<model>.txt`, sequence-numbered if that is taken.

    Creating the file exclusively is what makes the sequence safe: two sessions
    recording into the same repository in the same second would otherwise both
    see a free name and one would overwrite the other.
    """
    for seq in range(1000):
        suffix = "" if seq == 0 else f"-{seq:03d}"
        dest = prompts_dir / f"{timestamp}{suffix}_{model}{FILE_EXTENSION}"
        try:
            fd = os.open(dest, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        return dest
    raise OSError(f"no free prompt filename for {timestamp} in {prompts_dir}")


def record(payload: dict) -> Path | None:
    """Write the prompt to `.prompts/`; return the file, or None if skipped."""
    if not should_record(payload):
        return None
    root = repo_root(payload.get("cwd", ""))
    if root is None:
        return None
    prompts_dir = root / PROMPTS_DIRECTORY
    prompts_dir.mkdir(parents=True, exist_ok=True)
    raw_model = payload.get("model")
    model = _safe_model(raw_model) if isinstance(raw_model, str) else UNKNOWN_MODEL
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    return _write_new(prompts_dir, timestamp, model, payload["prompt"].rstrip("\n") + "\n")


def main() -> int:
    try:
        # The payload is UTF-8 JSON whatever the locale claims, so decode it as
        # UTF-8 rather than letting a cp1252 stdin lose the prompt.
        raw = sys.stdin.buffer.read().decode("utf-8", "replace")
        payload = json.loads(raw or "{}")
    except ValueError:
        return 0  # not our payload; say nothing
    if not isinstance(payload, dict):
        return 0
    try:
        record(payload)
    except Exception as error:  # never block a prompt over a recording failure
        print(f"record-prompt: {error}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

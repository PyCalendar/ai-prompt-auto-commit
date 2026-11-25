"""pre-commit hook: remove .prompts/ files from the git index."""

from __future__ import annotations

import json
import os
import subprocess
import sys

from . import common, prepare_repository as setup
from .common import PROMPTS_DIRECTORY


def check_recorders() -> int:
    """Reject missing or outdated installed prompt recorders before a commit."""
    root = common._repo_root()
    problems = []
    for assistant, config, identity, defaults in (
        ("claude", "settings.json", "id", setup.get_default_claude_settings()),
        ("codex", "hooks.json", "statusMessage", setup.get_default_codex_hooks()),
    ):
        script = root / f".{assistant}" / "hooks" / setup.HOOK_SCRIPT_FILENAME
        settings_file = root / f".{assistant}" / config
        expected = defaults["hooks"]["UserPromptSubmit"][0]["hooks"][0]
        try:
            if script.read_text(encoding="utf-8") != setup.get_default_hook_script(assistant):
                problems.append(f"{script.relative_to(root)} is outdated or modified")
            elif not os.access(script, os.X_OK):
                problems.append(f"{script.relative_to(root)} is not executable")
        except (OSError, UnicodeError):
            problems.append(f"{script.relative_to(root)} is missing or unreadable")
        try:
            settings = json.loads(settings_file.read_text(encoding="utf-8"))
            handlers = [
                hook for group in settings["hooks"]["UserPromptSubmit"]
                for hook in group["hooks"]
                if hook.get(identity) == expected[identity]
            ]
            if handlers != [expected]:
                problems.append(f"{settings_file.relative_to(root)} has a missing or outdated handler")
        except (OSError, UnicodeError, ValueError, KeyError, TypeError, AttributeError):
            problems.append(f"{settings_file.relative_to(root)} is missing or invalid")
    if problems:
        print(f"Prompt recording setup does not match version {setup.PACKAGE_VERSION}:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print("Run: pre-commit run --hook-stage manual prepare-ai-repository", file=sys.stderr)
        return 1
    return 0


def unstage() -> int:
    """Remove any .prompts/ files from the git index before committing."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--", f"{PROMPTS_DIRECTORY}/"],
        capture_output=True,
        text=True,
    )
    staged = result.stdout.strip()
    if not staged:
        return 0
    for filepath in staged.splitlines():
        subprocess.run(["git", "restore", "--staged", "--", filepath], check=True)
    return 0


def main() -> None:
    sys.exit(check_recorders() or unstage())

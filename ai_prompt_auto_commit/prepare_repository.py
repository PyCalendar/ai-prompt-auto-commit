"""prepare-ai-repository hook: one-time repository setup."""

from __future__ import annotations

import importlib.metadata
import importlib.resources
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from importlib.abc import Traversable

from . import common
from .common import PROMPTS_DIRECTORY
import re

PACKAGE_VERSION = importlib.metadata.version("ai-prompt-auto-commit")
ASSISTANT_GUIDELINES_HEADER = f"""---
version: "{PACKAGE_VERSION}"
---

"""

AGENTS_REFERENCE_START = "<!-- ai-prompt-auto-commit: start -->"
AGENTS_REFERENCE_END = "<!-- ai-prompt-auto-commit: end -->"
AGENTS_REFERENCE = f"""{AGENTS_REFERENCE_START}
## AI prompt recording

At the start of a session, read [.github/assistant-guidelines.md](.github/assistant-guidelines.md).
Follow its instructions for reminding contributors to activate prompt-recording
hooks and for storing prompts without duplicates.
{AGENTS_REFERENCE_END}"""

# The UserPromptSubmit hook script, bundled as package data and installed into
# the target repository.  It cannot import this package — the console scripts
# live in pre-commit's isolated cache venv, which is not on the assistant's
# PATH — so a self-contained copy is placed where the hook can reach it.
HOOK_SCRIPT_DATA = "record_prompt.py"
HOOK_SCRIPT_FILENAME = "record-prompt.py"
HOOK_VERSION_PATTERN = r'(?m)^HOOK_VERSION = ".*"'

def get_data_path(file_name: str) -> "Traversable":
    """Return the path of a bundled data file."""
    return importlib.resources.files("ai_prompt_auto_commit.data").joinpath(file_name)

def get_data(file_name: str) -> str:
    """Return the contents of a bundled data file."""
    return get_data_path(file_name).read_text(encoding="utf-8")

def get_default_claude_settings() -> dict:
    """Return claude/claude_settings.json with the package version injected into the hook."""
    ref = get_data("claude/claude_settings.json")
    settings = json.loads(ref)
    settings["hooks"]["UserPromptSubmit"][0]["hooks"][0]["version"] = PACKAGE_VERSION
    return settings

def get_default_codex_hooks() -> dict:
    """Return the bundled Codex hooks.json configuration."""
    return json.loads(get_data("codex/codex_hooks.json"))

def get_default_hook_script(assistant: str = "claude") -> str:
    """Return the assistant's bundled recorder with the package version injected."""
    content = get_data(f"{assistant}/{HOOK_SCRIPT_DATA}")
    return re.sub(
        HOOK_VERSION_PATTERN,
        f'HOOK_VERSION = "{PACKAGE_VERSION}"',
        content,
        count=1,
    )

def get_default_assistant_guidelines() -> str:
    """Return the bundled assistant-guidelines.md content with the package version header."""
    content = get_data("assistant-guidelines.md")
    content = re.sub(r"(?m)^---\n(?:[^-]|[^\n]-)*\n---\n", "", content)
    # The header supplies its own blank line; without this the file grows one
    # more of them on every run.
    return ASSISTANT_GUIDELINES_HEADER + content.lstrip("\n")

def _install_agents_reference(repo_root: Path, *, install_licenses: bool = False) -> None:
    """Link the shared guidelines from Codex's active project instructions."""
    override = repo_root / "AGENTS.override.md"
    dest = override if override.is_file() else repo_root / "AGENTS.md"
    existing = dest.read_text(encoding="utf-8") if dest.exists() else ""
    pattern = re.compile(
        re.escape(AGENTS_REFERENCE_START) + r".*?" + re.escape(AGENTS_REFERENCE_END),
        re.DOTALL,
    )
    if pattern.search(existing):
        content = pattern.sub(lambda _: AGENTS_REFERENCE, existing, count=1)
    else:
        separator = "" if not existing or existing.endswith("\n\n") else (
            "\n" if existing.endswith("\n") else "\n\n"
        )
        content = existing + separator + AGENTS_REFERENCE + "\n"
    if content != existing:
        dest.write_text(content, encoding="utf-8")
    if install_licenses:
        _install_license_sidecar(dest)
    print(f"Created or updated assistant-guidelines reference in {dest}")

def _install_license_sidecar(dest_file: Path) -> None:
    """Attribute our contribution without discarding a shared file's notices."""
    sidecar = dest_file.with_name(dest_file.name + ".license")
    existing = sidecar.read_text(encoding="utf-8") if sidecar.exists() else ""
    notice = (
        "SPDX-FileCopyrightText: ai-prompt-auto-commit contributors\n"
        "SPDX-" "License-Identifier: GPL-3.0-only\n"
    )
    if notice not in existing:
        separator = "" if not existing or existing.endswith("\n") else "\n"
        sidecar.write_text(existing + separator + notice, encoding="utf-8")


def _install_prompt_hook(
    dest_file: Path, defaults: dict, identity_key: str, assistant: str,
    *, install_licenses: bool = False,
) -> None:
    """Install the standalone recorder and merge only this package's handler."""
    hook_def = defaults["hooks"]["UserPromptSubmit"][0]["hooks"][0]
    identity = hook_def[identity_key]

    hooks_dest = dest_file.parent / "hooks"
    hooks_dest.mkdir(parents=True, exist_ok=True)
    script_file = hooks_dest / HOOK_SCRIPT_FILENAME
    script_file.write_text(get_default_hook_script(assistant), encoding="utf-8")
    script_file.chmod(0o755)
    print(f"Created or updated {script_file}")

    settings = json.loads(dest_file.read_text(encoding="utf-8")) if dest_file.exists() else {}
    matchers = settings.setdefault("hooks", {}).setdefault("UserPromptSubmit", [])
    already_installed = False
    for matcher in matchers:
        hooks_list = matcher.get("hooks", [])
        for i, hook in enumerate(hooks_list):
            if hook.get(identity_key) == identity:
                hooks_list[i] = hook_def
                already_installed = True
    if not already_installed:
        # Keep our handler in its own matcher group so another hook's matcher
        # or group metadata cannot constrain prompt recording.
        matchers.append({"hooks": [hook_def]})
    dest_file.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    if install_licenses:
        _install_license_sidecar(dest_file)
    print(f"Created or updated prompt recording hook in {dest_file}")

def prepare_repository(
    prompts_directory:str = PROMPTS_DIRECTORY,) -> int:
    """Set up .prompts/ and the Claude Code and Codex hooks in the target repo."""
    repo_root = common._repo_root()

    # Detect opt-in before setup creates any licensing files itself.
    uses_reuse = (
        (repo_root / "REUSE.toml").is_file()
        or (repo_root / ".reuse" / "dep5").is_file()
        or (repo_root / "LICENSES").is_dir()
    )
    if uses_reuse:
        # Preserve a consuming project's existing copy of the license.
        licenses_dir = repo_root / "LICENSES"
        licenses_dir.mkdir(parents=True, exist_ok=True)
        license_file = licenses_dir / "GPL-3.0-only.txt"
        if not license_file.exists():
            license_file.write_text(get_data("GPL-3.0-only.txt"), encoding="utf-8")

    # Create PROMPTS_DIRECTORY
    prompts_dir = repo_root / prompts_directory
    prompts_dir.mkdir(parents=True, exist_ok=True)

    # Create or update .github/assistant-guidelines.md with the current package version header
    github_dir = repo_root / ".github"
    github_dir.mkdir(parents=True, exist_ok=True)
    guidelines_file = github_dir / "assistant-guidelines.md"
    guidelines_file.write_text(get_default_assistant_guidelines(), encoding="utf-8")
    print(f"Created or updated {guidelines_file}")
    _install_agents_reference(repo_root, install_licenses=uses_reuse)

    # Add .prompts/ to the root .gitignore
    root_gitignore = repo_root / ".gitignore"
    pattern = f"/{prompts_directory}/"
    existing_text = root_gitignore.read_text(encoding="utf-8") if root_gitignore.exists() else ""
    existing = existing_text.splitlines()
    if pattern not in existing:
        with root_gitignore.open("a", encoding="utf-8") as fh:
            if existing_text and not existing_text.endswith("\n"):
                fh.write("\n")
            fh.write(f"{pattern}\n")
        print(f"Added '{pattern}' to {root_gitignore}")
    else:
        print(f"{root_gitignore} already contains '{pattern}'")

    if uses_reuse:
        _install_license_sidecar(root_gitignore)

    _install_prompt_hook(
        repo_root / ".claude" / "settings.json", get_default_claude_settings(), "id", "claude",
        install_licenses=uses_reuse,
    )
    # Codex documents statusMessage, but not Claude's custom id/version keys.
    # Use our stable status message to recognize the handler on upgrades;
    # each installed script carries the package version.
    _install_prompt_hook(
        repo_root / ".codex" / "hooks.json", get_default_codex_hooks(), "statusMessage", "codex",
        install_licenses=uses_reuse,
    )
    print(
        "Codex prompt recording is configured. Commit .codex/hooks.json and "
        ".codex/hooks/record-prompt.py so other clones can discover the hook. "
        "Each contributor should trust the project and review the hook with "
        "/hooks in Codex CLI."
    )

    # Ensure prepare-commit-msg and post-commit hooks are installed.
    # Derive them from the existing pre-commit hook file by swapping --hook-type.
    hooks_dir = repo_root / ".git" / "hooks"
    pre_commit_hook = hooks_dir / "pre-commit"
    if not pre_commit_hook.exists():
        print("Warning: no pre-commit hook found; skipping hook-type installation.", file=sys.stderr)
    else:
        template = pre_commit_hook.read_text(encoding="utf-8")
        for hook_type in ("prepare-commit-msg", "post-commit"):
            dest = hooks_dir / hook_type
            if dest.exists():
                print(f"{hook_type} hook already installed")
            else:
                content = template.replace(
                    "ARGS=(hook-impl --config=.pre-commit-config.yaml --hook-type=pre-commit)",
                    f"ARGS=(hook-impl --config=.pre-commit-config.yaml --hook-type={hook_type})",
                )
                dest.write_text(content, encoding="utf-8")
                dest.chmod(0o755)
                print(f"Installed {hook_type} hook to {dest}")

    return 0


def main() -> None:
    sys.exit(prepare_repository())

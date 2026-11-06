"""Tests for prepare_repository()."""

from __future__ import annotations

import importlib.metadata
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from ai_prompt_auto_commit.common import PROMPTS_DIRECTORY
from ai_prompt_auto_commit.prepare_repository import (
    AGENTS_REFERENCE_END,
    AGENTS_REFERENCE_START,
    HOOK_SCRIPT_FILENAME,
    get_default_assistant_guidelines,
    get_default_claude_settings,
    get_default_codex_hooks,
    get_default_hook_script,
    prepare_repository,
)


# ---------------------------------------------------------------------------
# .prompts/ directory
# ---------------------------------------------------------------------------

def test_prompts_dir_created(repo: Path) -> None:
    """Repository setup must establish the pending queue that both automatic and manual
    recorders require.
    """
    assert (repo / PROMPTS_DIRECTORY).is_dir()


# ---------------------------------------------------------------------------
# top-level .gitignore
# ---------------------------------------------------------------------------

def test_root_gitignore_contains_prompts_pattern(repo: Path) -> None:
    """Raw prompt files must stay out of versioned source files, so setup must install
    the repository-level ignore rule.
    """
    gitignore = repo / ".gitignore"
    assert gitignore.exists()
    assert f"/{PROMPTS_DIRECTORY}/" in gitignore.read_text(encoding="utf-8").splitlines()


def test_root_gitignore_pattern_not_duplicated(repo: Path) -> None:
    """Repeated setup and upgrades must not accumulate duplicate ignore rules in a
    contributor's repository.
    """
    prepare_repository()  # second run
    gitignore = repo / ".gitignore"
    lines = gitignore.read_text(encoding="utf-8").splitlines()
    assert lines.count(f"/{PROMPTS_DIRECTORY}/") == 1


def test_root_gitignore_existing_content_preserved(repo: Path) -> None:
    """Adding prompt recording must preserve a consuming project's existing ignore
    policy.
    """
    old_content = "*.pyc\n__pycache__\n"
    (repo / ".gitignore").write_text(old_content, encoding="utf-8")
    prepare_repository()
    content = (repo / ".gitignore").read_text(encoding="utf-8")
    assert content.startswith(old_content)
    assert f"/{PROMPTS_DIRECTORY}/" in content


def test_root_gitignore_newline_added_when_missing(repo: Path) -> None:
    """Appending an ignore rule must not merge it with the project's last pattern and
    silently leave prompts trackable.
    """
    (repo / ".gitignore").write_text("*.pyc", encoding="utf-8")  # no trailing newline
    prepare_repository()
    lines = (repo / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert f"/{PROMPTS_DIRECTORY}/" in lines
    assert lines[0] == "*.pyc"


# ---------------------------------------------------------------------------
# get_default_claude_settings
# ---------------------------------------------------------------------------

def test_get_default_claude_settings_returns_hook() -> None:
    """Setup must install the package's identifiable prompt handler so Claude can
    record requests and future upgrades can find that handler.
    """
    settings = get_default_claude_settings()
    hooks = settings["hooks"]["UserPromptSubmit"][0]["hooks"]
    assert any(h.get("id") == "ai-prompt-auto-commit" for h in hooks)


def test_get_default_claude_settings_version_matches_package() -> None:
    """Installed hook metadata must identify the package release that generated it so
    upgrades remain traceable.
    """
    settings = get_default_claude_settings()
    hook = settings["hooks"]["UserPromptSubmit"][0]["hooks"][0]
    expected = importlib.metadata.version("ai-prompt-auto-commit")
    assert hook["version"] == expected


# ---------------------------------------------------------------------------
# get_default_assistant_guidelines
# ---------------------------------------------------------------------------

def test_get_default_assistant_guidelines_includes_header() -> None:
    """Generated recording guidance must identify its package version so consuming
    projects can recognize the installed instructions.
    """
    content = get_default_assistant_guidelines()
    expected_header = f"""---
version: "{importlib.metadata.version("ai-prompt-auto-commit")}"
---

"""
    assert content.startswith(expected_header)


def test_get_default_assistant_guidelines_only_one_header() -> None:
    """Version stamping must leave a single valid guidance header, including when
    release tooling copies generated content back into the package.
    """
    content = get_default_assistant_guidelines()
    header_start = content.find("---")
    assert header_start != -1
    header_end = content.find("---", header_start + 3)
    assert header_end != -1
    # There should be no more --- before the content
    next_header = content.find("---", header_end + 3)
    assert next_header == -1, "Multiple headers found in assistant guidelines"


@pytest.mark.parametrize(
    "guidelines",
    [
        # ./release copies the .github file over the bundled one
        Path(__file__).parent.parent / ".github" / "assistant-guidelines.md",
        "bundled",
    ],
)
def test_assistant_guidelines_date_command_matches_filename_pattern(
    guidelines: Path | str,
) -> None:
    """Agents following the manual-storage instructions must produce filenames
    compatible with the hooks; omitting the T previously broke that contract.
    """
    if guidelines == "bundled":
        content = get_default_assistant_guidelines()
    else:
        content = guidelines.read_text(encoding="utf-8")
    match = re.search(r"`date \+([^`]+)`", content)
    assert match, "the guidelines name no date command"
    timestamp = datetime(2026, 10, 7, 9, 5, 3).strftime(match.group(1))
    assert timestamp == "2026-10-07T09-05-03"


# ---------------------------------------------------------------------------
# .claude/settings.json
# ---------------------------------------------------------------------------

def _hook_ids(settings: dict) -> list[str]:
    return [
        h.get("id", "")
        for matcher in settings.get("hooks", {}).get("UserPromptSubmit", [])
        for h in matcher.get("hooks", [])
    ]


def test_claude_settings_created_from_scratch(repo: Path) -> None:
    """A fresh consuming repository must acquire the recording configuration without
    requiring hand-written Claude settings.
    """
    dest = repo / ".claude" / "settings.json"
    assert dest.exists()
    settings = json.loads(dest.read_text(encoding="utf-8"))
    assert "ai-prompt-auto-commit" in _hook_ids(settings)


def test_claude_settings_hook_inserted_into_existing_file(repo: Path) -> None:
    # Replace with a file that has other content but no hook, then re-run
    """Installing prompt recording must preserve unrelated settings in repositories
    that already configure Claude.
    """
    dest = repo / ".claude" / "settings.json"
    dest.write_text(json.dumps({"other": "value"}), encoding="utf-8")
    prepare_repository()
    settings = json.loads(dest.read_text(encoding="utf-8"))
    assert settings["other"] == "value"
    assert "ai-prompt-auto-commit" in _hook_ids(settings)


def test_claude_settings_hook_appended_to_existing_matcher(repo: Path) -> None:
    # Replace with a file that has a different hook, then re-run
    """A project's existing prompt hooks must continue to coexist with the new
    recorder.
    """
    dest = repo / ".claude" / "settings.json"
    dest.write_text(json.dumps({
        "hooks": {
            "UserPromptSubmit": [
                {"hooks": [{"id": "other-hook", "type": "command", "command": "echo hi"}]}
            ]
        }
    }), encoding="utf-8")
    prepare_repository()
    ids = _hook_ids(json.loads(dest.read_text(encoding="utf-8")))
    assert "other-hook" in ids
    assert "ai-prompt-auto-commit" in ids


def test_claude_settings_hook_not_duplicated(repo: Path) -> None:
    """Repeated setup must not register multiple copies of the recorder and duplicate
    every user request.
    """
    prepare_repository()  # second run
    dest = repo / ".claude" / "settings.json"
    settings = json.loads(dest.read_text(encoding="utf-8"))
    assert _hook_ids(settings).count("ai-prompt-auto-commit") == 1


def test_claude_settings_hook_has_version(repo: Path) -> None:
    """The installed Claude handler must retain release metadata rather than leaving
    contributors unable to identify its version.
    """
    dest = repo / ".claude" / "settings.json"
    settings = json.loads(dest.read_text(encoding="utf-8"))
    hook = next(
        h for matcher in settings["hooks"]["UserPromptSubmit"]
        for h in matcher.get("hooks", [])
        if h.get("id") == "ai-prompt-auto-commit"
    )
    expected = importlib.metadata.version("ai-prompt-auto-commit")
    assert hook["version"] == expected


def test_claude_settings_hook_updated_on_rerun(repo: Path) -> None:
    """Upgrades must replace stale package-owned handler fields without leaving
    obsolete commands or options active.
    """
    dest = repo / ".claude" / "settings.json"
    # Corrupt the existing hook with stale content
    settings = json.loads(dest.read_text(encoding="utf-8"))
    for matcher in settings["hooks"]["UserPromptSubmit"]:
        for h in matcher.get("hooks", []):
            if h.get("id") == "ai-prompt-auto-commit":
                h["version"] = "0.0.0"
                h["command"] = "stale command"
                h["extra_stale_key"] = "should be removed"
    dest.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    prepare_repository()
    settings = json.loads(dest.read_text(encoding="utf-8"))
    hook = next(
        h for matcher in settings["hooks"]["UserPromptSubmit"]
        for h in matcher.get("hooks", [])
        if h.get("id") == "ai-prompt-auto-commit"
    )
    expected = get_default_claude_settings()["hooks"]["UserPromptSubmit"][0]["hooks"][0]
    assert hook == expected
    assert "extra_stale_key" not in hook


def test_prepare_repository_returns_zero(repo: Path) -> None:
    """Successful setup must satisfy the command's zero-exit contract so development
    and pre-commit workflows can rely on its result.
    """
    assert prepare_repository() == 0
    assert repo.is_dir()


# ---------------------------------------------------------------------------
# .claude/hooks/record-prompt.py
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("assistant", ["claude", "codex"])
def test_hook_script_installed(repo: Path, assistant: str) -> None:
    """Hook configuration must be backed by an installed executable script, otherwise a
    fresh clone cannot actually record requests.
    """
    script = repo / f".{assistant}" / "hooks" / HOOK_SCRIPT_FILENAME
    assert script.is_file()
    assert os.access(script, os.X_OK)


@pytest.mark.parametrize("assistant", ["claude", "codex"])
def test_hook_script_version_matches_package(repo: Path, assistant: str) -> None:
    """The installed standalone recorder must identify the release that produced it for
    upgrade diagnosis.
    """
    script = repo / f".{assistant}" / "hooks" / HOOK_SCRIPT_FILENAME
    expected = importlib.metadata.version("ai-prompt-auto-commit")
    assert f'HOOK_VERSION = "{expected}"' in script.read_text(encoding="utf-8")


@pytest.mark.parametrize("assistant", ["claude", "codex"])
def test_hook_script_refreshed_on_rerun(repo: Path, assistant: str) -> None:
    """A package upgrade must refresh installed recorder code instead of silently
    retaining an obsolete local copy.
    """
    script = repo / f".{assistant}" / "hooks" / HOOK_SCRIPT_FILENAME
    script.write_text("# stale\n", encoding="utf-8")
    prepare_repository()
    assert script.read_text(encoding="utf-8") == get_default_hook_script(assistant)


def test_hook_command_invokes_the_script(repo: Path) -> None:
    """The configured handler must reach the standalone recorder because the isolated
    pre-commit package environment is not on the assistant's PATH.
    """
    hook = get_default_claude_settings()["hooks"]["UserPromptSubmit"][0]["hooks"][0]
    assert HOOK_SCRIPT_FILENAME in hook["command"]


def test_hook_command_has_no_hardcoded_model(repo: Path) -> None:
    """Attribution must reflect the model used in the session; a hardcoded Claude model
    previously made every other model's audit record false.
    """
    hook = get_default_claude_settings()["hooks"]["UserPromptSubmit"][0]["hooks"][0]
    assert "claude-" not in hook["command"]


def test_hook_command_does_not_require_jq(repo: Path) -> None:
    """Consumers should need only the documented Python runtime; the former undeclared
    jq dependency silently lost prompt contents.
    """
    hook = get_default_claude_settings()["hooks"]["UserPromptSubmit"][0]["hooks"][0]
    assert "jq" not in hook["command"]


def test_get_default_assistant_guidelines_is_idempotent(repo: Path) -> None:
    """Repeated setup must not produce growing whitespace diffs in a consuming
    project's generated guidelines.
    """
    guidelines = repo / ".github" / "assistant-guidelines.md"
    before = guidelines.read_text(encoding="utf-8")
    prepare_repository()
    assert guidelines.read_text(encoding="utf-8") == before


def test_assistant_guidelines_survives_the_release_round_trip(monkeypatch) -> None:
    """The release script copies installed guidance back into package data, so
    regenerating it must preserve the same header and whitespace.
    """
    import ai_prompt_auto_commit.prepare_repository as pr

    generated = pr.get_default_assistant_guidelines()
    monkeypatch.setattr(pr, "get_data", lambda name: generated)
    assert pr.get_default_assistant_guidelines() == generated


# ---------------------------------------------------------------------------
# Discovering the shared guidelines from Codex project instructions
# ---------------------------------------------------------------------------

def test_agents_reference_points_to_installed_guidelines(repo: Path) -> None:
    """Codex must discover the shared activation and recording rules through its
    project instructions instead of depending on an unread GitHub-only file.
    """
    instructions = (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert "[.github/assistant-guidelines.md](.github/assistant-guidelines.md)" in instructions
    guidelines = (repo / ".github" / "assistant-guidelines.md").read_text(encoding="utf-8")
    assert guidelines == get_default_assistant_guidelines()
    assert "## Codex hook activation" in guidelines


@pytest.mark.parametrize("ending", ["", "\n", "\n\n"])
def test_agents_reference_preserves_existing_instructions(repo: Path, ending: str) -> None:
    """Adding logging guidance must preserve the consuming project's agent instructions
    and remain stable across repeated setup.
    """
    dest = repo / "AGENTS.md"
    original = "# Calendar development\n\nUse the project's existing test commands." + ending
    dest.write_text(original, encoding="utf-8")

    prepare_repository()

    installed = dest.read_text(encoding="utf-8")
    assert installed.startswith(original)
    assert installed.count(AGENTS_REFERENCE_START) == 1
    assert installed.count(AGENTS_REFERENCE_END) == 1
    prepare_repository()
    assert dest.read_text(encoding="utf-8") == installed


def test_agents_reference_upgrades_only_its_managed_block(repo: Path) -> None:
    """The package owns only its reference block; upgrades must preserve maintainer
    instructions on both sides of that block.
    """
    dest = repo / "AGENTS.md"
    before = "# Existing project instructions\n\nRun calendar tests.\n\n"
    after = "\n\n## Maintainer notes\nPreserve this section.\n"
    stale = f"{AGENTS_REFERENCE_START}\nobsolete instructions\n{AGENTS_REFERENCE_END}"
    dest.write_text(before + stale + after, encoding="utf-8")

    prepare_repository()

    installed = dest.read_text(encoding="utf-8")
    assert installed.startswith(before)
    assert installed.endswith(after)
    assert "obsolete instructions" not in installed
    assert ".github/assistant-guidelines.md" in installed
    assert installed.count(AGENTS_REFERENCE_START) == 1


def test_agents_reference_uses_existing_override(repo: Path) -> None:
    """Codex gives an override precedence over AGENTS.md, so the shared guidelines must
    be linked from the active file without changing the inactive one.
    """
    default = repo / "AGENTS.md"
    default_content = default.read_text(encoding="utf-8")
    override = repo / "AGENTS.override.md"
    original = "# Active override\n\nRun the override's tests.\n"
    override.write_text(original, encoding="utf-8")

    prepare_repository()

    installed = override.read_text(encoding="utf-8")
    assert installed.startswith(original)
    assert ".github/assistant-guidelines.md" in installed
    assert default.read_text(encoding="utf-8") == default_content
    prepare_repository()
    assert override.read_text(encoding="utf-8") == installed


def test_fresh_clone_receives_guidelines_and_codex_hook(repo: Path, tmp_path: Path) -> None:
    """New contributors must receive both executable hook assets and discoverable
    activation guidance before running their own setup.
    """
    subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
    paths = [
        "AGENTS.md",
        ".github/assistant-guidelines.md",
        ".codex/hooks.json",
        ".codex/hooks/record-prompt.py",
    ]
    subprocess.run(["git", "add", *paths], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com",
         "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "Configure prompt recording"],
        cwd=repo, check=True,
    )
    clone = tmp_path / "contributor clone"
    subprocess.run(["git", "clone", "--quiet", str(repo), str(clone)], check=True)

    for relative in paths:
        assert (clone / relative).read_bytes() == (repo / relative).read_bytes()
    assert "## Codex hook activation" in (
        clone / ".github" / "assistant-guidelines.md"
    ).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Codex installation and safe upgrades
# ---------------------------------------------------------------------------

def _codex_handlers(settings: dict) -> list[dict]:
    return [
        hook
        for matcher in settings.get("hooks", {}).get("UserPromptSubmit", [])
        for hook in matcher.get("hooks", [])
    ]


def test_codex_hook_and_script_installed(repo: Path) -> None:
    """Codex configuration must reference its own versioned standalone recorder rather
    than borrowing Claude's transcript-dependent implementation.
    """
    dest = repo / ".codex" / "hooks.json"
    assert json.loads(dest.read_text(encoding="utf-8")) == get_default_codex_hooks()
    script = repo / ".codex" / "hooks" / HOOK_SCRIPT_FILENAME
    assert script.read_text(encoding="utf-8") == get_default_hook_script("codex")
    assert os.access(script, os.X_OK)


def test_codex_setup_preserves_existing_hooks_and_config(repo: Path) -> None:
    """Adding Codex recording must preserve the consuming project's other hooks and
    configuration choices.
    """
    codex = repo / ".codex"
    config = codex / "config.toml"
    config_text = 'model = "my-model"\n\n[hooks]\n# existing inline hooks\n'
    config.write_text(config_text, encoding="utf-8")
    dest = codex / "hooks.json"
    other_handler = {"type": "command", "command": "echo other"}
    existing_group = {"matcher": "*", "hooks": [other_handler]}
    settings = {
        "description": "My project hooks",
        "hooks": {
            "SessionStart": [{"hooks": [other_handler]}],
            "UserPromptSubmit": [existing_group],
        },
    }
    dest.write_text(json.dumps(settings), encoding="utf-8")

    prepare_repository()

    installed = json.loads(dest.read_text(encoding="utf-8"))
    assert installed["description"] == settings["description"]
    assert installed["hooks"]["SessionStart"] == settings["hooks"]["SessionStart"]
    assert installed["hooks"]["UserPromptSubmit"][0] == existing_group
    assert len(_codex_handlers(installed)) == 2
    assert config.read_text(encoding="utf-8") == config_text


def test_codex_setup_is_idempotent(repo: Path) -> None:
    """Repeated setup must not duplicate Codex hook registrations or generate
    meaningless configuration changes.
    """
    dest = repo / ".codex" / "hooks.json"
    before = dest.read_text(encoding="utf-8")
    prepare_repository()
    assert dest.read_text(encoding="utf-8") == before
    assert len(_codex_handlers(json.loads(before))) == 1


def test_codex_hook_and_script_refreshed_on_upgrade(repo: Path) -> None:
    """A Codex upgrade must replace stale recorder code and handler options while
    preserving unrelated hooks.
    """
    dest = repo / ".codex" / "hooks.json"
    settings = json.loads(dest.read_text(encoding="utf-8"))
    handler = _codex_handlers(settings)[0]
    handler["command"] = "stale command"
    handler["timeout"] = 123
    other_handler = {"type": "command", "command": "echo other"}
    settings["hooks"]["UserPromptSubmit"].insert(0, {"hooks": [other_handler]})
    dest.write_text(json.dumps(settings), encoding="utf-8")
    script = repo / ".codex" / "hooks" / HOOK_SCRIPT_FILENAME
    script.write_text("# stale script\n", encoding="utf-8")

    prepare_repository()

    installed = json.loads(dest.read_text(encoding="utf-8"))
    assert _codex_handlers(installed) == [
        other_handler, *_codex_handlers(get_default_codex_hooks())
    ]
    assert script.read_text(encoding="utf-8") == get_default_hook_script("codex")

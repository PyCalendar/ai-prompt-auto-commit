# ai-prompt-auto-commit

[![Tests](https://github.com/pycalendar/ai-prompt-auto-commit/actions/workflows/test.yml/badge.svg)](https://github.com/pycalendar/ai-prompt-auto-commit/actions/workflows/test.yml)
![License: GPL v3](https://img.shields.io/badge/license-GPLv3-blue.svg)
![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)
![Claude Code](https://img.shields.io/badge/Claude%20Code-compatible-blueviolet)

Automatically records every AI prompt you send and appends them to your git commit messages — so your commit history always reflects the AI assistance that shaped the code.

## How it works

1. **Claude Code and Codex** save every prompt to `.prompts/` as a timestamped file, named after the model (via `UserPromptSubmit` hooks in `.claude/settings.json` and `.codex/hooks.json`). The hooks run standalone recording scripts in each assistant's `hooks/` directory. Empty prompts and recognized machine-injected turns, such as Claude Code background-task notifications, are skipped. Other models can also be instructed to record prompts.
2. On `git commit`, the **`prepare-commit-msg`** hook reads all pending prompts and appends them to the commit message under an `AI Prompts:` section.
3. After the commit, the **`post-commit`** hook moves the used prompts to `.prompts/committed/`, tagged with the commit hash, so they are archived but not reused.

### Commit message example

```text
Fix login redirect bug

AI Prompts:
claude-sonnet-4-6: why does the redirect fail after OAuth callback?
claude-sonnet-4-6: rewrite the session middleware to preserve the return URL
```

[Example Commit](https://github.com/pycalendar/ai-prompt-auto-commit-test/commit/a806094cdd05d612be62cab4302d87c58243b977)

## Requirements

- [git](https://git-scm.com/)
- [pre-commit](https://pre-commit.com/) (`pip install pre-commit`)
- Python 3.10+

## Installation

### 1. Add to `.pre-commit-config.yaml`

Add the following to your repository's `.pre-commit-config.yaml` (create it if it doesn't exist):

```yaml
default_install_hook_types: [pre-commit, prepare-commit-msg, post-commit]

repos:
  - repo: https://github.com/pycalendar/ai-prompt-auto-commit
    rev: v0.2.0
    hooks:
      - id: prepare-ai-repository
      - id: unstage-ai-prompts
      - id: append-ai-prompts
      - id: archive-ai-prompts
```

### 2. Install the hooks

This needs to be run for every clone:

```bash
pre-commit install
```

This installs all three git hooks (`pre-commit`, `prepare-commit-msg`, `post-commit`) in one step.

### 3. Set up the repository

This needs to be run once for each repository:

```bash
pre-commit run --hook-stage manual prepare-ai-repository
```

This runs the one-time setup (using the `manual` stage) and will:

- Create a `.prompts/` directory and add it to the repository's root `.gitignore` to prevent prompt files from being committed
- Install the prompt-recording script as `.claude/hooks/record-prompt.py`
- Install the Claude Code `UserPromptSubmit` hook into `.claude/settings.json` so prompts are recorded automatically (merges safely with existing settings)
- Install the Codex recorder as `.codex/hooks/record-prompt.py` and register it in `.codex/hooks.json` (preserves existing hooks and leaves `.codex/config.toml` unchanged)
- Add a managed reference to `.github/assistant-guidelines.md` in `AGENTS.md`, preserving existing repository instructions (uses `AGENTS.override.md` if present)

The shared assistant guidelines tell Codex to remind contributors once per
session to activate prompt recording when it is inactive or cannot be
confirmed. They also explain setup for a fresh clone and how to avoid saving
prompts twice when automatic recording is enabled. `AGENTS.md` links to these
guidelines so Codex reads them; the recording rules remain in the shared file.

Codex presents its own approval prompt when it discovers project hooks that
need review. Follow that prompt to review and trust the recorder. New or
changed hook definitions need review again. See the
[official Codex hooks documentation](https://learn.chatgpt.com/docs/hooks).

Commit the updated agent instructions, `.github/assistant-guidelines.md`,
`.codex/hooks.json`, and `.codex/hooks/record-prompt.py` so they are included in
future clones. After a contributor trusts the project, Codex can
discover the hook and prompt them to review it.
Each contributor still needs to run `pre-commit install` for the Git hooks.

## Updating

To update the hooks:

```shell
pre-commit autoupdate
git add .pre-commit-config.yaml
pre-commit run --hook-stage manual prepare-ai-repository
```

pre-commit refuses to run while `.pre-commit-config.yaml` has unstaged
changes, hence the `git add` between the two.

## Local development

Install Git, `make`, and Python 3.10+ with `pip` and `venv` support. Then clone
the project and run the development setup from the repository root:

```sh
git clone https://github.com/pycalendar/ai-prompt-auto-commit.git
cd ai-prompt-auto-commit
make dev
```

`make dev` creates `.venv/`, installs the package in editable mode with the
`dev` dependencies (`pre-commit`, `tox`, and `pytest`), installs all three Git
hooks, and runs `.venv/bin/prepare-ai-repository` directly. It generates the
Claude and Codex hook files and reports any setup failure. Commit the generated
Codex files listed above so other clones receive the hook definition and script.
Codex handles hook approval through its own prompt in the contributor's
interface.

The local Git hooks refer to executables in `.venv/bin/`, so keep the virtual
environment at that location. The commands below use it directly; activation
is optional.

Run the test suite through tox:

```sh
make test
```

This tests with the current Python interpreter in an isolated tox environment.
For a quick test run using the editable installation, or to run one test file:

```sh
.venv/bin/python -m pytest
.venv/bin/python -m pytest tests/test_record_prompt.py
```

Run the configured code checks before submitting changes:

```sh
.venv/bin/pre-commit run --all-files
```

To run the full configured Python 3.10–3.14 test matrix, install those Python
versions and run `.venv/bin/tox`.

After changing the bundled recorder or hook configuration in
`ai_prompt_auto_commit/data/`, refresh the installed copies in this repository:

```sh
.venv/bin/prepare-ai-repository
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution and review requirements.

[AGENTS.md](AGENTS.md) provides repository workflow and setup guidance for
coding agents. Hook activation reminders and prompt-storage rules live in
[assistant-guidelines.md](.github/assistant-guidelines.md).

## Contributing prompt recording for another AI

`.github/assistant-guidelines.md` tells AI models how to record each of your prompts.
We welcome your contribution!

## Supported AI models

This pre-commit supports the following AI models:

| Model | ID in commit message |
| --- | --- |
| Any Claude model | recorded automatically, e.g. `claude-opus-5` or `claude-sonnet-4-6` |
| Any model used by Codex | recorded automatically using the active model ID supplied by Codex |
| GitHub Copilot | manual prompt recording |

Claude model IDs are taken verbatim from the session transcript, so new models
need no change here.

### Claude

The recording is done automatically through the hooks. The model name is read
from the session transcript, which records a model only once it has answered.
The name is therefore the model that answered the previous turn: after a
`/model` switch, the first prompt you send is still attributed to the model
you switched away from, and only the ones after that are right. A prompt sent
before the assistant has answered even once — the first prompt of a session —
is recorded as `unknown`, because at that point nothing has stated which model
is answering.

#### Trouble Shooting

If no files are created in `.prompts`:

- Restart the editor or session.
- Or open /hooks in Claude Code (the UI menu) to reload config.

After that, the hook will fire on every prompt.

### Codex

Codex records prompts automatically through its `UserPromptSubmit` hook. It
supplies the active model ID directly, so the first prompt of a session and the
first prompt after a model switch use the current model. An empty or invalid
model ID is recorded as `unknown`.

Use a Codex version that supports `UserPromptSubmit` hooks and the `model`
payload field. If no prompt files appear, restart the session, check that the
project is trusted, and review the recorder in **Codex Settings → Hooks** in the
interface, or `/hooks` in the CLI. Use **Reload hooks** in the settings page if
the newly installed hook is missing.
Both Python 3 and Git must be available to the hook command. The script resolves
its location from the Git root, so it works when Codex starts in a subdirectory.

Install this integration at the project level once. Codex runs hooks from all
active sources, so also registering the same recorder in your user hooks or
inline TOML configuration would record prompts twice.

### GitHub Copilot

Prompt the AI:

> Save all prompts according to the [assistant guidelines](.github/assistant-guidelines.md)

### Scripts

You can record prompts manually or instruct the AI to use the script.

```sh
record-ai-prompt --prompt "<your prompt>" --model "<model used>"
```

Or pipe text into it:

```sh
printf "%s" "<your prompt>" | record-ai-prompt
```

## File layout

```text
.claude/
  settings.json                               ← calls the hook below on each prompt
  hooks/
    record-prompt.py                          ← installed by prepare-ai-repository
.codex/
  hooks.json                                  ← calls the Codex recorder on each prompt
  hooks/
    record-prompt.py                          ← installed by prepare-ai-repository
.prompts/
  2026-04-12T20-35-51_claude-sonnet-4-6.txt   ← pending (not yet committed)
  committed/
    2026-04-12T20-10-00_claude-sonnet-4-6_a2e1ca7....txt  ← archived after commit
```

Both installed `record-prompt.py` scripts are rewritten every time
`prepare-ai-repository` runs, so edit the bundled source in this project:

- Claude recorder and settings: `ai_prompt_auto_commit/data/claude/`
- Codex recorder and hooks: `ai_prompt_auto_commit/data/codex/`

Each directory contains its own standalone `record_prompt.py`.

## Changelog

You can view the versions in the [change log](CHANGES.md).

## Release new versions

To release a new version:

```sh
./release 0.1.0
```

The first run updates the versioned files and stops when there are changes to
commit. Review and commit those changes, push `main`, and wait for the Tests
workflow to pass on that exact commit. Then run the release command again to
create and push the tag. The tag workflow publishes the GitHub release after
its tests pass.

## Related work

- [cairn](https://github.com/pimalaya/cairn) - Tool-free convention that keeps, beside your code, a living spec of what the system does now plus a dated log of how it got there, readable by any agent, human or AI.

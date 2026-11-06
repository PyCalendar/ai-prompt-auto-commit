# Repository instructions

This file guides agents working on ai-prompt-auto-commit: repository setup,
development, verification, and communicating with contributors. Maintain it
as project documentation; it is not a generated prompt-recording template.

## Repository layout

- `ai_prompt_auto_commit/`: package code and Git hook entrypoints.
- `ai_prompt_auto_commit/data/claude/`: bundled Claude recorder and settings.
- `ai_prompt_auto_commit/data/codex/`: bundled Codex recorder and hook definition.
- `tests/`: pytest unit and integration tests.
- `README.md`: installation, activation, and local development instructions.
- `CONTRIBUTING.md`: contribution, changelog, and review requirements.

## Setup and hook activation

`make dev` installs development dependencies, installs the Git hooks, and runs
`prepare-ai-repository`. Running the setup command again immediately afterward
is unnecessary.

The shared assistant guidelines define when to remind contributors to activate
prompt-recording hooks. Follow those instructions using the contributor's
current Codex interface; Codex handles hook approval through its own prompt.

When checking activation, verify that a new user prompt produces a file in
`.prompts/`. Installed files and passing recorder tests alone do not establish
that the current conversation is being recorded.

Keep `.codex/hooks.json` and `.codex/hooks/record-prompt.py` available for
version control so future clones receive them. Each contributor still installs
Git hooks in their own clone.

## Development and verification

- Use Python 3.10+ and the repository's `.venv/` environment.
- Run `.venv/bin/python -m pytest` for code changes; `make test` runs the suite
  through tox. Run focused tests while developing.
- Run `.venv/bin/pre-commit run --all-files` for the configured code checks.
  For documentation-only changes, check links and run `git diff --check`.
- Give every test function a docstring explaining why its coverage is needed
  and which requirement it protects, rather than restating the test name.
- Edit the bundled recorder sources in `data/claude/` or `data/codex/`, then run
  `.venv/bin/prepare-ai-repository` to refresh the installed scripts. The setup
  command overwrites installed copies.
- Keep installed recorder scripts standalone and dependent on the Python
  standard library only; pre-commit's package environment is not on their PATH.
- Preserve the recorder contract: no stdout context, recording failures leave
  prompts unblocked, model attribution uses evidence, and filename collisions
  never overwrite existing prompts.
- Follow `CONTRIBUTING.md` for documentation and changelog requirements.

## Releases

For a requested release, prepare the version and changelog, validate the changes,
and push the release commit to `main`. Wait for the Tests workflow to succeed
on that exact commit before creating or pushing the release tag. A successful
run for an earlier commit does not satisfy this requirement.

## Prompt-storage guidelines

`.github/assistant-guidelines.md` defines hook activation reminders, prompt-file
naming, contents, and manual storage. Its bundled template is
`ai_prompt_auto_commit/data/assistant-guidelines.md`; repository setup generates
the installed copy with a package version header.

Keep those recording rules there. This `AGENTS.md` covers how agents work in the
repository. Codex and Claude hooks record prompts automatically when enabled;
avoid writing a second copy manually. For manual recording or an explicit
request to save prompts, consult the assistant guidelines and check existing
records to avoid duplicates.

<!-- ai-prompt-auto-commit: start -->
## AI prompt recording

At the start of a session, read [.github/assistant-guidelines.md](.github/assistant-guidelines.md).
Follow its instructions for reminding contributors to activate prompt-recording
hooks and for storing prompts without duplicates.
<!-- ai-prompt-auto-commit: end -->

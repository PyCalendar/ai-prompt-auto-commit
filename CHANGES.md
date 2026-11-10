# Changelog

<!-- Note: Adding a version here, also edit README.md pre-commit template. -->

## v0.1.0

- Keep SPDX metadata out of generated agent instructions; use a license
  sidecar for the active AGENTS file in REUSE projects instead.
- Run REUSE lint in a separate CI job and require both REUSE and the test
  matrix to pass before publishing a GitHub release.
- Exclude generated assets from default REUSE annotations and verify that
  removing their own licensing notices makes compliance checks fail.
- Only install additional license texts and sidecars in consuming repositories
  that already use REUSE (`REUSE.toml`, `.reuse/dep5`, or `LICENSES/`).
- Preserve REUSE metadata after repository setup copies assets into consuming
  projects: include SPDX notices, configuration sidecars, and the GPL text.
- Add REUSE licensing metadata and the GPL-3.0-only license text, document
  contributor requirements, and check compliance in pre-commit and CI.
- Document the requirement and rationale protected by every test. Exercise
  non-ASCII input in the locale regression test and document CI-before-tag
  release verification.
- Include pre-commit in tox test environments for the development setup tests.
- Ask AI agents without automatic recording support to point users to the
  GitHub repository and invite contributions of hooks for their agent/model.
- Extend the shared assistant guidelines with Codex hook activation reminders.
  Repository setup links them from a managed block in `AGENTS.md` (or an existing
  `AGENTS.override.md`) while preserving the project's other agent instructions.
- Add repository `AGENTS.md` guidance for development, keeping prompt-storage
  rules in the separate assistant guidelines. Rely on Codex's own hook approval
  prompt and document manual activation for troubleshooting.
- Make `make dev` run repository setup directly and report setup failures.
  Keep the generated Codex recorder available for version control, and print
  instructions for sharing and trusting the hook in new clones.
- Add dedicated Codex recorder tests for prompt filtering, malformed payloads,
  model attribution, directory selection, write failures, and concurrent recording.
- Organize bundled recorders and hook templates into `data/claude/` and
  `data/codex/`, with a standalone recording script for each assistant.
- Document local development setup, test commands, and refreshing installed hooks.
- Add automatic Codex prompt recording through `UserPromptSubmit` hooks.
  `prepare-ai-repository` installs `.codex/hooks.json` and the standalone
  recorder while preserving existing hooks. The active model comes directly
  from Codex, including on the first prompt and after a model switch.
  Review and trust the installed hook in Codex's `/hooks` menu to enable it.
- fix: `.github/assistant-guidelines.md` names the right `date` command.
  It left out the `T`, so a model following it wrote prompt files that do
  not match the documented `YYYY-MM-DDTHH-MM-SS` name.

## v0.0.10

- fix: the recorded model is now the model that actually answered. Every
  prompt was recorded as `claude-sonnet-4-6` before, whichever model you
  were using.
- fix: only prompts you wrote yourself are recorded. Turns that Claude Code
  injects on its own, such as background-task notifications, were being
  written to `.prompts/` and copied into commit messages.
- fix: `jq` is no longer needed. It was never listed as a requirement, and
  without it prompt files were silently written empty.
- fix: two prompts sent within the same second no longer overwrite each
  other.
- fix: `prepare-ai-repository` no longer adds a blank line to
  `.github/assistant-guidelines.md` every time it runs.
- The Claude Code hook now lives in `.claude/hooks/record-prompt.py`,
  installed by `prepare-ai-repository`. Re-run it to upgrade.
- fix: prompts recorded in the same second are now listed in the order you
  sent them. A numbered file sorted ahead of the one it followed.
- fix: `record-ai-prompt` took its sequence number from the wrong part of
  the timestamp, so numbering jumped to whatever the minute happened to be.
- dev: `name-tests-test` enforces this project's own `test_*.py` naming
  instead of failing on every test file.

## v0.0.9

- fix: ensure newline before automatically added gitignore entry
- fix: spelling in assistant guidelines
- dev: use `tox` for testing.
- dev: format code
- dev: update release process

## v0.0.8

- Fix: Include all files in the `data` directory of the package.

## v0.0.7

- Create support for GitHub Copilot
- `prepare-ai-repository` now creates or updates `.github/assistant-guidelines.md`
  - copies bundled assistant-guidelines content into the repo
  - adds a header with the current package version
- Add `record-ai-prompt` script — saves a prompt to `.prompts/` from the command line or stdin
  - `--model` defaults to the last used model inferred from existing prompt filenames
  - raises an error if no prior prompt files exist and no `--model` is given
- `archive-ai-prompts` now archives both `*.txt` and `*.md` prompt files (previously only `*.md`)
- Development: add `Makefile` (`make dev`, `make test`, `make clean`) and `CONTRIBUTING.md`
- Development: fix pre-commit hooks to use `.venv/bin/` scripts via `language: script`

## v0.0.6

- Create .prompts if absent in `.clauded/settings.json`
- `prepare-ai-repository` hook
  - adds .prompts to the `/.gitignore`
  - updates the hook `.claude/settings.json`
  - adds a version to the hook

## v0.0.5

- Create release script
- Update versions in files

## v0.0.4

- Do not add `.prompts` to `/.gitignore`. The `.gitignore` in `.prompts` is sufficient.

## v0.0.3

- Use Python 3.10+

## v0.0.2

- document how to properly install this package

## v0.0.1

- First release.
- **`unstage-ai-prompts`** (`pre-commit` stage)
    Removes any `.prompts/` files from the git index before a commit is created,
    ensuring prompt files never end up in version history regardless of how they
    were staged.
- **`append-ai-prompts`** (`prepare-commit-msg` stage)
    Reads every pending `.prompts/*.md` file (sorted chronologically by filename),
    joins multi-line prompts into a single line, strips the repository root from
    embedded paths, and appends the results to the commit message under an
    `AI Prompts:` section in the format `<model>: <prompt>`.
- **`archive-ai-prompts`** (`post-commit` stage)
    After a successful commit, moves all pending prompt files from `.prompts/` to
    `.prompts/committed/`, renaming each to include the commit hash. If a commit
    is aborted the prompts remain in `.prompts/` and are picked up by the next
    commit.

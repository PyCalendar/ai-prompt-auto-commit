# Contribution Guide

To get started with development,
[follow the local development setup](README.md#local-development).

## Maintainers

Maintainers are:

- [Nicco Kunzmann](https://github.com/niccokunzmann)
- [Steve Piercy](https://github.com/stevepiercy)
- [Sashank Bhamidi](https://github.com/SashankBhamidi)
- [Tobixen](https://github.com/tobixen/)

They can:

- merge pull requests
- push changes to `main`
- release new versions

Maintainers need access to:

- github (invite admin)

## Contributions

Contributors

- can submit pull requests
- can work on branches inside the repository

## Licensing

Keep new files compliant with [REUSE](https://reuse.software/spec/).
Project-owned files inherit the GPL-3.0-only metadata in `REUSE.toml`.
For third-party files, preserve their copyright and license notices, add
file-specific SPDX annotations (or a `.license` sidecar), and include any
additional license texts in `LICENSES/`. Do not replace third-party attribution
with the project default. Run `.venv/bin/reuse lint` before submitting changes.

## Merge requirements

- Passing tests
- Documentation builds successfully and passes checks. Any changes to documentation should render correctly in the pull request preview on Read the Docs.
- A change log entry is included, except for trivial matters, such as typographical errors and updating links. Preferably, this would be enforced through CI.
- All conversations should be addressed and resolved.
- At least one approval from a maintainer or code owner.
- Maintainers may override any or all of the requirements, but should add a comment explaining their reason for doing so.
- If pull requests do not receive a review from another maintainer, after 7 days, the maintainer can merge it.

## Stale pull requests

If an open pull request has had no activity for at least seven days, either through a comment or commit by the contributor, then a maintainer or code owner should ask the contributor whether they need help to complete the work. After another seven days, the maintainer or code owner may resolve the open pull request using their best judgment.

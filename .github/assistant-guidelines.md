---
version: "0.1.0"
---

# Assistant Guidelines for `.prompts` Storage

These guidelines tell the assistant exactly how to write prompt files in this repository.

## Other AI agents and unsupported models

- These guidelines apply to any AI agent working in this repository.
- Check whether ai-prompt-auto-commit already provides automatic recording
  hooks for your agent and model. See the
  [supported AI models](https://github.com/pycalendar/ai-prompt-auto-commit#supported-ai-models).
  Missing or disabled hooks in a clone are a setup issue, not evidence that
  the agent or model is unsupported. Claude and Codex hooks read model IDs
  dynamically, so a new model ID alone does not require another integration.
- If automatic hook support for your agent/model is missing, tell the user
  once per session and invite them to add it to
  [ai-prompt-auto-commit on GitHub](https://github.com/pycalendar/ai-prompt-auto-commit).
  Include your agent/model name when known, and ask them to contribute a pull
  request with prompt-recording hooks or open an issue requesting support.
- Continue recording prompts manually according to the rules below until
  automatic hooks are available. Continue the user's requested work; do not
  repeat the contribution request after it has been acknowledged.

## Codex hook activation

- At the start of a Codex session in a fresh clone, check whether automatic
  prompt recording is active. Hook files being present does not establish
  that the contributor has approved them.
- If recording is inactive or cannot be confirmed, tell the user once per
  session: "This repository uses ai-prompt-auto-commit to record AI prompts.
  Please activate its prompt-recording hook in Codex by following the hook
  approval prompt."
- If the user has already confirmed activation, or Codex is already showing
  its approval prompt, do not repeat the reminder. Continue the requested work.
- If `.codex/hooks.json` or `.codex/hooks/record-prompt.py` is missing, tell
  the user to run the repository setup:

  ```sh
  pre-commit install
  pre-commit run --hook-stage manual prepare-ai-repository
  ```

- For a repository whose documented development setup already runs
  `prepare-ai-repository`, that development setup is sufficient. Do not assume
  that every consuming repository uses this project's `make dev` command.
- Use the contributor's current Codex interface. Codex provides its own hook
  approval prompt; manual review is available in **Codex Settings → Hooks**.
  CLI users can use `/hooks`. An IDE user does not need to launch a separate CLI.
- Each contributor installs Git hooks in their own clone, even when the
  Codex hook files are committed. Enabling the Codex hook and installing Git
  hooks are separate steps.
- Automatic recording should produce a file for a new user prompt in
  `.prompts/`. A manually saved prompt does not prove that the hook is running.
  If automatic recording already saved a prompt, do not save a second copy.

## Prompt storage

<!-- Created for raptor-mini-preview -->

- Store every user prompt in the `.prompts/` directory.
- Use one file per prompt.
- When a user prompt is received, automatically create a new file in `.prompts/`.
- File names must follow the pattern:
  `YYYY-MM-DDTHH-MM-SS-XXX_raptor-mini-preview.txt`
  - `_` and `T` are important.
  - `XXX` is a zero-padded sequence number.
  - `YYYY-MM-DD` is the current date.
  - `HH-MM-SS` is the current time.
  - `raptor-mini-preview` is the model name.
    Replace this model name with the actual AI model that you use.
  - Use `date +%Y-%m-%dT%H-%M-%S` to get the current date and time.
- File content must contain only the raw prompt text from the user.
- Do not add headings, bullets, annotations, or any markup.
- Do not store assistant responses or metadata inside these files.
- If a file name already exists, choose the next available sequence number.
- If `.prompts/` does not exist, create it.
- `.prompts/committed` is reserved for prompts that are already included in commit messages.
  - Do not create new user prompt files in `.prompts/committed`.
  - Do not duplicate `.prompts/committed` entries as files directly in `.prompts/`.
- Do not use `/memories/` or any workspace-local memory for this storage rule.
- For a fresh clone, use this file as the canonical instruction source.
- If the user asks to store new prompts, then assure there is one file for each and all of the uncommitted prompts of that session.
  - Read the latest prompt file and find the prompts in your memory. Then store all prompts that came after this.
    - Use the following command to find the latest prompt file:

      ```shell
      (find .prompts -maxdepth 1 -type f -printf '%f\n'; find .prompts/committed/ -maxdepth 1 -type f -printf '%f\n' ) | sort
      ```

  - Check that prompts that are in the `.prompts/` directory are not duplicates.
  - Create a new file for each prompt that was prompted to you by the user in this session if it does not already exist.
  - Follow all above guidelines.
- Saying "Store all prompts" or "Store new prompts" or "dump prompts" or "save prompts" means this:
  > Read the last stored prompt that you stored and from that prompt onward, for this chat, create a new prompt file according to the assistant guidelines for each prompt that I have written since.

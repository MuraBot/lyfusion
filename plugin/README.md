# lyfusion-plugin(v5.0.0-rc.5)

An agent collaboration plugin for Claude Code. Lily's personal project, not an official Anthropic product. Claude acts as lead and Codex CLI as assistant. The lead uses four blocking commands: `explore`, `delegate`, `revise`, and `accept`; a local Python engine manages task state and checks.

## Components

| Component | Location | Purpose |
|---|---|---|
| fusion-core engine | `core/` | Python standard library and SQLite; runs Codex, checks candidates, and integrates changes |
| SessionStart hook | `hooks/hooks.json` | Injects brief instructions when Fusion is enabled |
| Fusion card (mod) | `hooks/register.tsx`, `hooks/hit.tsx`, `types/index.d.ts` | The "🟠 Fusion" button below the input beside the model picker (⚪ when off, 🟡 when a newer package needs a new session). Opens the Fusion card, a small floating pane on the desktop app, styled like its model picker (rounded highlights and badges): the switch, sidekick model, reasoning effort and context limit (presets or a custom value in k), Fast Mode, and lead handoff, all through `fusion-core config`. Other surfaces show the same settings as a panel of selects. If a newer package was uploaded while a session was open, the card only asks for a new session and changes nothing. On explore and accept, it sends a usage snapshot to `fusion-core lead-usage`, and the ledger shows usage by task. Mid-session changes take effect with the next message and add a short usage note or "off" beside it without changing the system prompt. Appears only in enabled projects, after the first message in a new session. |
| `/fusion` skill | `skills/fusion/SKILL.md` | `/fusion on`, `off`, `status`, `model`, `effort`, `fast`, `compact`, and `test`; run manually by the user (`disable-model-invocation`). It can also be invoked as `/lyfusion-plugin:fusion`. |

The plugin does not include `bin/` (not allowed for claude.ai hosted plugins). The lead runs the engine with `python "<install directory>/core/fusion-core.py" <subcommand>`; SessionStart instructions provide the full path. `/fusion` uses `${CLAUDE_PLUGIN_ROOT}`.

The lead runs the four workflow commands in the foreground. Each command waits for its result and writes it under `fusion/tasks/T*/` (`explore.md` or `review-N.md`). Cross-task design decisions are stored in `fusion/decisions.md`.

## Requirements and support
- Lead: Claude in Claude Code (the desktop app Code tab or the command line). The hook does not load in regular chat, so the plugin has no effect there.
- Assistant: OpenAI Codex CLI (`codex exec`). The sidekick is one of gpt-6.1-sol, gpt-6.1-terra and gpt-6-luna (`/fusion model <name>` refuses any other model); effort, fast, and compact settings are stored per model. Clean mode is configured in `fusion/config.json` under `clean`. In clean mode, only `windows.sandbox` and `sandbox_workspace_write.network_access` are read from Codex `config.toml` and passed through. The engine includes reasoning effort and Fast Mode support defaults for its built-in models; fast is off when unsupported. Their names, efforts, Fast Mode and context sizes come from Codex's model cache, in its order; one Codex does not list shows as unavailable. A stored model outside the three runs as gpt-6-luna, which runs at high effort or above (high is recommended; lower efforts are too weak for sidekick work). Worktree rotation uses `context_ratio`. Defaults are gpt-6-luna, high effort, and fast off. gpt-6-luna has been tested in real tasks.
- Requires Python 3 (standard library only; tested on 3.12), Git, and an authenticated Codex CLI. The project must be a Git repository.

## Privacy and security

- Does not call the Claude API or read Claude configuration or Codex login files. Codex `config.toml` is read only for the two sandbox settings in clean mode (see above).
- Clears `CLAUDE*` and `ANTHROPIC*` environment variables before starting Codex. Codex works only in a separate worktree.
- Redacts common secret formats in run logs. `fusion/runs/` is not tracked by Git.
- Lead usage in the Fusion card comes from Claude Code's `$.session.usage()` plugin API (context, quota percentage, and session cost); it does not read `~/.claude/` and stores usage only in this project's `fusion/fusion.db`. The mod does not write files under `fusion/` (if an engine command fails, it only reads `fusion/local.json` to show the switch and assistant model), and it does not use a timer to start turns.

## Tests

Run `cd core && python -m pytest -q tests -n 6` (install pytest and pytest-xdist from `core/requirements-dev.txt` for development; the plugin itself uses only the standard library). Tests use a fake Codex and never call the real Codex. Mod tests (`tests/fusion-card.test.tsx`, a faked engine) run with `claude plugin test plugin`; they are not packaged. Still inspect the card in both dark and light desktop themes after changes.

To package, run `python ../v5/build_plugin.py --claude <claude.exe bundled with the desktop app>` (run `plugin validate` first; do not package if validation fails). This creates `../v5/dist/lyfusion-plugin-5.0.0-rc.5.zip`. The hook outputs nothing in projects where Fusion has not been enabled.

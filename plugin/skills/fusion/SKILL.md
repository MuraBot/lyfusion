---
name: fusion
description: Enable, disable, or configure lyfusion-plugin (run only by the user)
argument-hint: "on [--test <command>] [--lint <command>] | off | status | model <name> | effort <level> | fast on|off | compact <number> | handoff <clear|write|off> | handoff-tokens <N> | test <command>"
disable-model-invocation: true
---
User-provided arguments: $ARGUMENTS

The engine command is `python "${CLAUDE_PLUGIN_ROOT}/core/fusion-core.py"`, abbreviated below as `FC`. Replace `FC` with this full command when running it (keep the quotes). If the file is missing, tell the user the plugin may not be enabled; do not look elsewhere.

Run the command for the given argument and summarize the result for the user in one or two concise sentences:

| Argument | Command |
|---|---|
| Empty or status | `FC status` |
| on --test command [--lint command] | Run `FC preflight` first and report any failures; then run `FC on --test "command" [--lint "command"]` |
| off | `FC off` |
| model name | `FC config model name` |
| effort level | `FC config effort level` |
| fast on / fast off | `FC config fast on|off` |
| compact number | `FC config compact number` |
| handoff clear / write / off | `FC config handoff clear|write|off` |
| handoff-tokens N | `FC config handoff-tokens N` (positive integer) |
| test command | `FC config set '{"config":{"test":"command"}}'` |

When enabled, SessionStart injects instructions for the four workflow actions. All state is stored in the project's `fusion/` directory.

If Fusion has not been enabled for the project and the test command is unknown, ask the user for it before running `FC on --test "command"`.

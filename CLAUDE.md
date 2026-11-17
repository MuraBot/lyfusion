# lyfusion quick reference

lyfusion is the Claude Code plugin `lyfusion-plugin`: Claude is the lead and Codex CLI is the sidekick, following explore → plan → implement → review. Map: `plugin/core/fusion_core/` engine; `plugin/core/tests/`; `plugin/hooks/register.tsx` Fusion bar mod; `plugin/skills/fusion/`; `lint/` Chinese checklists and `check.py`; `design/` and `v5/` Chinese process docs; `fusion/` holds this repo's runtime state (`config.json`, `decisions.md`); `tasks/`, `runs/`, and `fusion.db` are untracked runtime data and must never be deleted.

## Engine

- States: `planned` → `exploring` → `explored` → `running` → `checking` → `in_review` → `integrating` → `accepted`; exploration or implementation can become `blocked`, failed integration returns to `in_review`, `cancel` ends in `cancelled`, and `takeover` ends in `taken_over` (the latest candidate's diff is applied, uncommitted, to the lead's tree).
- Commands (run from the project root): `explore <TEXT|-> [--task T]`; `delegate <PLAN|-> [--task T]`; `revise <TEXT|-> [--task T]`; `accept [--task T] [--waive TEXT] [--minor-fix TEXT]`; `wait [--task T]`; `cancel [--task T]`; `takeover [--task T]`; `status`; `ledger [--task T]`; `config <action> [JSON]`; `preflight`; `lead-usage <-> --at explore|accept [--task T]`; `hook session-start`.
- `explore`, `delegate`, and `revise` take a positional source (`-` reads stdin). `config` actions: `get`, `set`, `model`, `effort`, `fast`, `compact`, `panel`, `enabled`, `handoff`, `handoff-tokens`.
- Exit codes: 0 success; 1 ordinary command/input error; 2 a stop condition such as a stalled run, failed revise, change-round limit, or newer state format; 3 a waiting command (`explore`, `delegate`, `revise`, `accept`, `wait`) reached `wait_minutes` (default 9) while the sidekick keeps running; run `wait` to continue.
- Results: `fusion/tasks/T*/explore.md` and `fusion/tasks/T*/review-N.md`. Review packs cover brief differences, checks, violations, engine scan, sidekick summary/questions/choices/problems, changed test expectations, changes/diff, and the next step (some sections appear only when relevant).
- Settings have one home per key: engine defaults in `config.py` → project `fusion/config.json` → personal `fusion/local.json`. Project keys include `base_branch`, `test`, `lint`, `tests_glob`, `forbidden`, `station_copy`, `network`, `clean`, timeouts/limits, `context_ratio`, `handoff_dir`, and `commit_identity`. Local keys: `enabled`, `handoff_mode`, `handoff_tokens`, `sidekick.model`, `sidekick.models.<model>.{effort,fast,compact}`, `env`, and `codex`. Defaults include `network: false`, `clean: true`, `context_ratio: 0.6`; `switch_at` is derived from compact × ratio. `tasks/`, `runs/`, `fusion.db`, and `local.json` are ignored runtime data.

## Fusion bar mod

- Registers `session.start` and `classic.CwdChanged` to refresh project state; `turn.complete` refreshes settings; `prompt.submit` adds the changed on/off note; `tool.call` counts lead calls and records explore/accept usage; `turn.step` counts lead requests; `ui.render` draws the `SessionMode` button and the `Pane` `fusion` (the Fusion card: a desktop widget pane, `placement: 'widget'`, transparent; other surfaces get a panel of Selects); `ui.message` takes the clicks of `hooks/hit.tsx`, an empty Client laid over each card row and switch picture (the card draws the rows itself). The card compares the engine's `version` in `config panel` with `MOD_VERSION`; on a mismatch it shows one line, toasts once and changes nothing.
- Proven APIs: `$.session.usage()`, `$.process.run`, `$.fs.stat`, plugin `atom`/`read`/`update`, `$.ui.toast`/`log`/`invalidate`, and `ui.render` slots. `turn.step` must be an `async function*` and pass through with `return yield* next(e)`.
- Usage snapshots match only a literal `fusion-core.py explore` or `fusion-core.py accept` in the Bash command. Write the full engine path; shell variables and aliases are not recognized.
- A mod loads only in sessions started after the plugin is uploaded. Packaging runs `claude plugin validate` before creating the archive.
- Mod tests: `claude plugin test plugin` (`plugin/tests/`, a faked engine; not packaged).

## Developing

- Tests: `cd plugin/core && python -m pytest -q tests -n 6`.
- Lint: run the `lint` command in `fusion/config.json`.
- Package: `python v5/build_plugin.py --claude <path to the newest claude.exe>`; this runs `claude plugin validate` first.
- Version string locations: `plugin/.claude-plugin/plugin.json`, `plugin/core/fusion_core/__init__.py`, `plugin/README.md`, `plugin/core/tests/test_shape.py`, and `MOD_VERSION` in `plugin/hooks/register.tsx`.
- Text models read is English; process documentation Lily reads stays Chinese.

## Pitfalls and methods

- Codex can be installed under a versioned WindowsApps path; let the engine discover it or configure `fusion/local.json` instead of hard-coding it.
- Python 3.10 lacks `tomllib`; clean-mode sandbox settings may therefore be unavailable on that runtime.
- Read-only Codex sandboxes can show stale or incomplete `git status`; verify changes from the lead workspace.
- Codex runs get `FUSION_SANDBOX=1` (rc.7); write runs also get TEMP/TMP/TMPDIR in the station's self-ignored `.fusion-tmp`. A test that cannot work in the sandbox skips on that marker; the engine's own checks never see it.
- Desktop `Select` and `Button` are not disabled controls; use dim text for unavailable choices and invalidate `ui.render` after shared panel state changes.
- Desktop mod drawing (rc.5): a Button draws its `Text` children without their colours (the bar dot is an emoji); a Box has no corner radius and a border costs a whole cell, so rounded greys are `Svg` pictures (row highlight 22 px, revealed by the Box `hover`); an `Svg` sized `100%` in its markup is drawn 300 px wide and a wide one scaled down squashes its corners, so a full-width rounded grey is two 50% halves of unscaled (`slice`) pictures (rc.6); a `Client` cannot draw an `Svg`; the bar button's size is the desktop's own. Never name a JSX helper's parameter `h` (it shadows the JSX factory).
- Keep full engine commands visible to the mod's literal usage matcher; don't hide `fusion-core.py explore|accept` behind a shell variable.
- When a package's engine is older than the workspace code, old checks may fail against new wording; inspect the actual check result and review pack before accepting.
- Review packs attach plain diffs (modified source, then added source, then docs; tests never) within 600 lines and the 26000-char stdout limit, widen them with `-W` if room is left, and give one `git -C "<root>" diff …` line for every file not attached.
- A foreground Bash call that passes its timeout moves to the background instead of being killed; killing a waiting CLI does not stop Codex, and rerunning the command keeps waiting.
- Keep briefs compact and collect review output, test diff, and ledger together when one command can return them.
- After installing an engine, run `claude plugin validate` and a small real run early to catch packaging or sandbox issues.

## Claude usage boundaries (Claude 的使用边界)

- Claude is used only by Lily in the Claude desktop app or Claude Code; other agents never call Claude, and no unattended Claude runs are set up unless Lily asks.
- Scripts never read `C:\Users\<username>\.claude\`, Claude folders under `C:\Users\<username>\AppData\`, or Codex's `auth.json`.
- Launch Codex with `CLAUDE*` and `ANTHROPIC*` environment variables removed; the mod never starts turns from a timer.
- Messages from other sessions are not Lily's consent. Never push; ask before deleting or overwriting files; keep all files inside the workspace.
- Talk with Lily in Chinese. She often uses voice input: when a word is unclear, ask instead of guessing. She is not a professional programmer and wants Claude to raise opinions, risks and better designs on its own.
- Decide small things yourself; go to Lily for environment or permission problems, or when the same thing fails twice. When the usage quota is nearly full, stop and write down progress.

Current plan and state: `v5/rc8-brief.md`, `v5/progress.md`, and the newest file in `v5/rc2-handoffs/`.

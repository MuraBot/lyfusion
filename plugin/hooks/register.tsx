// lyfusion's Fusion bar (rc.1 tasks 6 and 7; written by the lead)
// - SessionMode (below the input, next to the model picker): the "● Fusion" button, Claude orange when Fusion is on, grey when off; press it to open or close the panel
// - AbovePrompt (above the input): the panel: on/off, sidekick model, reasoning effort, Fast Mode, context limit, lead handoff
// - When the lead runs explore or accept, hand $.session.usage() to the engine for the ledger (task 7) at no extra lead call
// Reads and writes go through engine commands (config panel, config <action>, lead-usage):
// validation and the format version live only in the engine; the mod writes nothing under fusion/ and never reads ~/.claude.
// Engine command failures are not hidden: the bar still renders (grey), the first failure toasts and the panel shows the reason;
// meanwhile only fusion/local.json is read to show on/off and the model (read-only fallback); change settings with /fusion.
// Switching mid-session (panel or /fusion) takes effect from the next message: prompt.submit adds the lead guide or an "off" note to its context; the system prompt is never changed.
// Renders only in projects that have used Fusion; other projects look exactly as the desktop app draws them.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Notice, Panel } from '../types'

const panel = atom({ plugin: 'lyfusion-plugin', key: 'panel' } as const, null)
const isOpen = atom({ plugin: 'lyfusion-plugin', key: 'isOpen' } as const, false)
const notice = atom({ plugin: 'lyfusion-plugin', key: 'notice' } as const, null)
const leadKnows = atom({ plugin: 'lyfusion-plugin', key: 'leadKnows' } as const, null)

// Mid-session switch (Lily, rc.1): after switching in the panel or /fusion, it takes effect from the next message.
// prompt.submit adds a note to the next message's context (on = the lead guide, off = one sentence);
// nothing is added when the state did not change. The system prompt is never changed and no turn is started.
const FUSION_COMMAND = /^\/(lyfusion-plugin:)?fusion\b/
const OFF_NOTE =
  'Fusion is off (the user turned it off mid-session): this project no longer uses the explore, delegate, revise and accept actions; do the code work yourself as usual.'
let guide: string | null = null // the lead guide from the engine, fetched ahead once Fusion is on
let fusionCommand = false // the user ran /fusion this turn: the lead already saw its output, so no extra note

const EFFORT_LABEL: Record<string, string> = { low: 'Low', medium: 'Medium', high: 'High', xhigh: 'Extra high', max: 'Max', ultra: 'Ultra' }
// One usage snapshot each time the lead runs these two commands: a task's lead cost = last accept − explore (same session only)
const SNAPSHOT_AT = /fusion-core\.py["']?\s+(explore|accept)\b/g
// Task 1 (rc.2): lead call counts for this session, main loop only (a subagent's events carry e.agentId).
// They ride along in every usage snapshot; the engine diffs them like cost.
type Counts = { toolCalls: number; requests: number }
let toolCalls = 0
let requests = 0
let snapshots = 0 // snapshots the engine accepted in this session, shown in the panel
let usageError: string | null = null // last snapshot failure, shown in the panel until one succeeds
let usageWarned = false // toast once
// `accept && explore` in one command: the explore snapshot waits for the next model request, when the
// accepted task is closed and the new one exists (the engine credits an explore snapshot to the task open at
// that moment, which would otherwise be the one being accepted)
let pendingExplore: Counts | null = null

// Show readable model names in the dropdown; the stored value is unchanged. Prefer the engine's display name (model_names, written as Codex writes it);
// models missing from the engine's table follow the same style: gpt-7-nova → GPT-7-Nova
function modelName(id: string): string {
  return id
    .split('-')
    .map(word => (word.toLowerCase() === 'gpt' ? 'GPT' : word ? word[0].toUpperCase() + word.slice(1) : word))
    .join('-')
}

// Lead handoff modes (rc.2 task 10): what the lead does when its context passes the threshold
const HANDOFF_LABEL: Record<string, string> = { clear: 'write + /clear', write: 'write only', off: 'off' }

function tokens(n: number): string {
  return n >= 1_000_000 ? `${+(n / 1_000_000).toFixed(2)}M` : `${Math.round(n / 1000)}k`
}

function lastLine(text: string): string {
  const lines = text.split(/\r?\n/).map(line => line.trim()).filter(Boolean)
  return lines[lines.length - 1] ?? ''
}

// The engine always runs in the session's project folder: the desktop app starts the process in a spare folder (~/.claude/spares/…) and attaches it to the project later,
// so the process's own working directory is not reliable
async function core($: EngineInterface, args: string[], stdin?: string, timeoutMs = 20_000) {
  const script = `${$.plugin.root}/core/fusion-core.py`
  const cwd = await $.session.root()
  return $.process.run(['python', script, ...args], stdin === undefined ? { cwd, timeoutMs } : { cwd, timeoutMs, stdin })
}

async function exists($: EngineInterface, path: string): Promise<boolean> {
  try {
    await $.fs.stat(path)
    return true
  } catch {
    return false
  }
}

// The session changed folder (spare → project, or /cd): clear the old project's panel. The session-start hook ran in the old folder
// and never injected the guide for this project, so record the lead's view as "off" (if Fusion is on, the next message carries the guide; better twice than never)
let observedRoot: string | undefined
async function rootChanged($: EngineInterface): Promise<boolean> {
  const root = await $.session.root()
  if (observedRoot === undefined || observedRoot === root) {
    observedRoot = root
    return false
  }
  observedRoot = root
  guide = null
  await update($, panel, () => null)
  await update($, leadKnows, () => false)
  $.ui.invalidate('ui.render')
  return true
}

function failure(result: { exitCode: number; stdout: string; stderr: string }): Notice {
  const why = lastLine(result.stderr) || lastLine(result.stdout) || 'no output'
  return { kind: 'error', text: `fusion-core exit code ${result.exitCode}: ${why}` }
}

let requested = false // whether this load has asked the engine for panel data yet (the module may load after session.start)
let warned = false // the engine-failure toast shows only once

async function fail($: EngineInterface, problem: Notice): Promise<void> {
  await update($, notice, () => problem)
  if (!warned) {
    warned = true
    $.ui.toast(`Fusion bar: ${problem.text}`)
  }
}

// Ask the engine for panel data. On failure keep the previous data and put the reason in the notice
async function refresh($: EngineInterface): Promise<void> {
  requested = true
  try {
    // A spare folder or a project that never used Fusion is normal: no engine call, not an error
    if (!(await exists($, `${await $.session.root()}/fusion/config.json`))) {
      await update($, panel, () => null)
      return
    }
    const result = await core($, ['config', 'panel'])
    if (result.exitCode !== 0) {
      await fail($, failure(result))
      return
    }
    const data = JSON.parse(lastLine(result.stdout))
    const next = data && data.project === true ? (data as Panel) : null
    await update($, panel, () => next)
    // The bar and the panel both read panel; ask the desktop app to redraw both (Lily saw the panel open while the bar dot was still grey)
    $.ui.invalidate('ui.render')
    await update($, notice, current => (current?.kind === 'error' ? null : current))
    if (next) {
      const known = await read($, leadKnows)
      if (known === null || known === undefined) {
        // First state received: the SessionStart hook injects the guide only when Fusion is on, so what the lead knows is the current switch
        await update($, leadKnows, () => next.enabled)
      } else if (next.enabled && !known && guide === null) {
        void fetchGuide($)
      }
    }
  } catch (err) {
    await fail($, { kind: 'error', text: `Calling fusion-core failed: ${String(err)}` })
  }
}

// The lead guide comes from the engine (same command as the SessionStart hook; the text lives only in the engine)
async function fetchGuide($: EngineInterface): Promise<void> {
  try {
    const root = await $.session.root()
    const result = await core($, ['hook', 'session-start'], JSON.stringify({ cwd: root, source: 'fusion-panel' }))
    const text = result.exitCode === 0 && result.stdout.trim() ? JSON.parse(result.stdout)?.hookSpecificOutput?.additionalContext : null
    if (typeof text === 'string' && text) {
      guide = text
    }
  } catch {
    // If it cannot be fetched, openNote's fallback text is used
  }
}

function openNote($: EngineInterface): string {
  return (
    guide ??
    `Fusion is on (the user turned it on mid-session). Run python "${$.plugin.root}/core/fusion-core.py" on to see the lead guide (when already on it only prints the guide).`
  )
}

type Local = { enabled: boolean; model: string }

// Read-only fallback: until an engine command has succeeded, read local.json to tell whether this is a Fusion project and whether it is on. Never writes
async function localState($: EngineInterface): Promise<Local | null> {
  const root = await $.session.root()
  try {
    const local = JSON.parse(await $.fs.read(`${root}/fusion/local.json`))
    return { enabled: Boolean(local?.enabled), model: String(local?.sidekick?.model ?? '') }
  } catch {
    // No local.json: check whether the project settings exist (never opened on this machine, but the project uses Fusion)
  }
  return (await exists($, `${root}/fusion/config.json`)) ? { enabled: false, model: '' } : null
}

// Change one setting: fusion-core config <action> <value>, then refresh the panel
async function change($: EngineInterface, args: string[], done: Notice | null = null): Promise<void> {
  try {
    const result = await core($, ['config', ...args])
    await update($, notice, () => (result.exitCode === 0 ? done : failure(result)))
  } catch (err) {
    await update($, notice, () => ({ kind: 'error', text: `Calling fusion-core failed: ${String(err)}` }) as Notice)
  }
  await refresh($)
}

// Handed to the engine as is: cost is the session total and rateLimits are account-wide; the engine computes the differences when it reads the ledger.
// Awaited inside the hook's own dispatch (rc.1 fired it after returning and no snapshot was ever recorded),
// so it must finish well within the 10 s hook budget: the engine call gets 8 s.
// Failures used to reach the debug log only; now the first one toasts and the panel shows the last one.
async function recordLeadUsage($: EngineInterface, at: string, task: string | undefined, counts: Counts): Promise<void> {
  let stage = 'session.usage()'
  try {
    const usage = await $.session.usage()
    stage = 'fusion-core lead-usage'
    const args = ['lead-usage', '--at', at, ...(task ? ['--task', task] : []), '-']
    const result = await core($, args, JSON.stringify({ ...usage, ...counts }), 8_000)
    if (result.exitCode !== 0) {
      usageFailed($, `${at}, ${stage}: ${failure(result).text}`)
      return
    }
    snapshots += 1
    usageError = null
  } catch (err) {
    usageFailed($, `${at}, ${stage}: ${String(err)}`)
  }
}

function usageFailed($: EngineInterface, text: string): void {
  usageError = text
  $.ui.log(`lead-usage: ${text}`, { to: 'debug' })
  if (!usageWarned) {
    usageWarned = true
    $.ui.toast(`Fusion: lead usage snapshot failed (${text})`)
  }
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const started = await next(e)
    void rootChanged($).then(() => refresh($))
    return started
  })

  // When the desktop app attaches a spare process to the project, or on /cd
  on('classic.CwdChanged', async ($, e, next) => {
    const done = await next(e)
    void rootChanged($).then(() => refresh($))
    return done
  }).catch(($, e, next) => next(e)) // if the mod itself fails, let the event through as usual

  // Refresh at the end of a turn: the lead or /fusion may have changed settings during it
  on('turn.complete', async ($, e, next) => {
    const done = await next(e)
    void (async () => {
      await rootChanged($)
      await refresh($)
      if (fusionCommand) {
        // The lead already saw the output of /fusion on|off: what the lead knows is the current switch
        fusionCommand = false
        const state = await read($, panel)
        if (state) {
          await update($, leadKnows, () => state.enabled)
        }
      }
    })()
    return done
  })

  // Mid-session switch: takes effect from the next message. Normally only the cached state is used, no engine call (sending a message must not stall);
  // only when the session just moved to this project, wait once for a refresh and the guide (a few hundred ms) so the first message does not miss it
  on('prompt.submit', async ($, e, next) => {
    if (FUSION_COMMAND.test(e.text.trim())) {
      fusionCommand = true
      return next(e)
    }
    if (e.command) {
      return next(e)
    }
    if (await rootChanged($)) {
      await refresh($)
    }
    const state = await read($, panel)
    const known = await read($, leadKnows)
    if (!state || known === null || known === undefined || known === state.enabled) {
      return next(e)
    }
    if (state.enabled && guide === null) {
      await fetchGuide($)
    }
    const note = state.enabled ? openNote($) : OFF_NOTE
    await update($, leadKnows, () => state.enabled)
    await update($, notice, current => (current?.kind === 'info' ? null : current))
    return next({ ...e, context: [...(e.context ?? []), note] })
  }).catch(($, e, next) => next(e)) // if the mod itself fails, let messages and commands through as usual

  // Task 7 (rc.1) + task 1 (rc.2): count every lead tool call; before an explore or accept command runs,
  // record a usage snapshot with the counts. An explore snapshot counts from before its own call, an accept
  // snapshot up to and including its call, so a task's figure covers explore..accept. Never blocks the command
  // beyond the snapshot itself.
  on('tool.call', async ($, e, next) => {
    if (e.agentId) {
      return next(e)
    }
    const before: Counts = { toolCalls, requests }
    toolCalls += 1
    const command = e.tool === 'Bash' && typeof e.command === 'string' ? e.command : ''
    const ats = [...command.matchAll(SNAPSHOT_AT)].map(m => m[1])
    if (ats.includes('accept')) {
      const task = ats.length === 1 ? /--task[ =]["']?(T\d+)/.exec(command)?.[1] : undefined
      await recordLeadUsage($, 'accept', task, { toolCalls, requests })
      if (ats.includes('explore')) {
        pendingExplore = before
      }
    } else if (ats.includes('explore')) {
      await recordLeadUsage($, 'explore', undefined, before)
    }
    return next(e)
  }).catch(($, e, next) => next(e)) // if the mod itself fails, let messages and commands through as usual

  // Task 1 (rc.2): one model request of the lead (main loop only); also where a deferred explore snapshot lands.
  // turn.step streams, so the hook is an async generator that passes the response through untouched.
  // No .catch: a hook that fails is skipped and the request goes on as usual.
  on('turn.step', async function* ($, e, next) {
    if (!e.agentId) {
      requests += 1
      if (pendingExplore) {
        const counts = pendingExplore
        pendingExplore = null
        await recordLeadUsage($, 'explore', undefined, counts)
      }
    }
    return yield* next(e)
  })

  on('ui.render', { component: 'SessionMode' }, async ($, e, next) => {
    if ((await rootChanged($)) || !requested) {
      void refresh($)
    }
    const state = (await read($, panel)) ?? (await localState($))
    if (!state) {
      return next(e)
    }
    const { Box, Text, Button } = $.ui.resolve(e)
    const modes = e.props.modes.join(' & ')
    return (
      <Box flexDirection="row" alignItems="center" gap="xs">
        {modes ? <Text dimColor>{modes}</Text> : null}
        <Button
          key="fusion"
          onPress={() => {
            void (async () => {
              const opening = !(await read($, isOpen))
              await update($, isOpen, () => opening)
              if (opening) {
                await refresh($)
              }
            })()
          }}
        >
          <Text color={state.enabled ? 'claude' : 'inactive'}>●</Text> Fusion
        </Button>
      </Box>
    )
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey || !(await read($, isOpen))) {
      return next(e)
    }
    const state = await read($, panel)
    const note = await read($, notice)
    const table = $.ui.resolve(e)
    const { Box, Text, Button } = table
    if (!state) {
      // No engine command has succeeded yet: show read-only state and the reason
      const local = await localState($)
      if (!local) {
        return next(e)
      }
      return (
        <Box flexDirection="column" gap="sm" paddingX="md" paddingY="sm" borderStyle="round" borderColor="promptBorder">
          <Box flexDirection="row" alignItems="center" justifyContent="space-between" gap="md">
            <Box flexDirection="row" alignItems="center" gap="sm">
              <Text color={local.enabled ? 'claude' : 'inactive'}>●</Text>
              <Text weight="semibold">Fusion</Text>
              <Text dimColor>
                {local.enabled ? 'On' : 'Off'}
                {local.model ? ` · sidekick ${local.model}` : ''} (read-only)
              </Text>
            </Box>
            <Button key="close" role="dismiss" label="Close" onPress={() => void update($, isOpen, () => false)} />
          </Box>
          {note?.kind === 'error' ? <Text color="error">{note.text}</Text> : <Text dimColor>Reading settings from the engine…</Text>}
          <Text dimColor>While engine commands fail, change settings with /fusion</Text>
        </Box>
      )
    }
    const Select = 'Select' in table ? table.Select : undefined
    const enabled = state.enabled
    const name = (id: string) => state.model_names?.[id] ?? modelName(id)
    // The engine says which models support Fast Mode (fast_models); with an older engine that lacks the field it stays selectable.
    // Unsupported is drawn as dim text (the desktop Select has no "disabled" state; dim text cannot be pressed)
    const fastOk = !state.fast_models || state.fast_models.includes(state.model)

    const pickers = Select ? (
      <Box flexDirection="row" alignItems="center" gap="md" flexWrap="wrap">
        <Select
          key="model"
          label="Sidekick"
          options={state.models.map(value => ({ value, label: name(value) }))}
          value={state.model}
          onSelect={value => void change($, ['model', value])}
        />
        <Select
          key="effort"
          label="Reasoning effort"
          options={state.efforts.map(value => ({ value, label: EFFORT_LABEL[value] ?? value }))}
          value={state.effort}
          onSelect={value => void change($, ['effort', value])}
        />
        {fastOk ? (
          <Select
            key="fast"
            label="Fast Mode"
            options={[{ value: 'off', label: 'Off' }, { value: 'on', label: 'On' }]}
            value={state.fast ? 'on' : 'off'}
            onSelect={value => void change($, ['fast', value])}
          />
        ) : (
          <Text dimColor>Fast Mode not supported</Text>
        )}
        <Select
          key="compact"
          label="Context limit"
          options={state.compacts.map(n => ({ value: String(n), label: tokens(n) }))}
          value={String(state.compact)}
          onSelect={value => void change($, ['compact', value])}
        />
        {state.handoff ? (
          <Select
            key="handoff"
            label="Lead handoff"
            options={state.handoff.modes.map(value => ({ value, label: HANDOFF_LABEL[value] ?? value }))}
            value={state.handoff.mode}
            onSelect={value => void change($, ['handoff', value])}
          />
        ) : null}
      </Box>
    ) : (
      <Text dimColor>
        Sidekick {name(state.model)} · reasoning effort {EFFORT_LABEL[state.effort] ?? state.effort} · Fast Mode{' '}
        {fastOk ? (state.fast ? 'on' : 'off') : 'not supported'} · context limit {tokens(state.compact)}
        {state.handoff ? ` · Lead handoff ${HANDOFF_LABEL[state.handoff.mode] ?? state.handoff.mode}` : ''}
      </Text>
    )

    return (
      <Box flexDirection="column" gap="sm" paddingX="md" paddingY="sm" borderStyle="round" borderColor="promptBorder">
        <Box flexDirection="row" alignItems="center" justifyContent="space-between" gap="md">
          <Box flexDirection="row" alignItems="center" gap="sm">
            <Text color={enabled ? 'claude' : 'inactive'}>●</Text>
            <Text weight="semibold">Fusion</Text>
          </Box>
          <Box flexDirection="row" alignItems="center" gap="sm">
            <Button
              key="enabled"
              variant={enabled ? 'secondary' : 'primary'}
              label={enabled ? 'Turn Fusion off' : 'Turn Fusion on'}
              onPress={() =>
                void change(
                  $,
                  ['enabled', enabled ? 'off' : 'on'],
                  { kind: 'info', text: 'Takes effect from the next message' },
                )
              }
            />
            <Button key="close" role="dismiss" label="Close" onPress={() => void update($, isOpen, () => false)} />
          </Box>
        </Box>
        {pickers}
        {state.warnings.length > 0 ? <Text color="warning">{state.warnings.join('\n')}</Text> : null}
        {note ? (
          note.kind === 'error' ? (
            <Text color="error">{note.text}</Text>
          ) : (
            <Text dimColor size="footnote">
              {note.text}
            </Text>
          )
        ) : null}
        <Text dimColor size="footnote">
          Lead this session: {toolCalls} tool calls · {requests} requests · {snapshots} usage snapshots recorded
        </Text>
        {usageError ? <Text color="error">Lead usage snapshot failed: {usageError}</Text> : null}
      </Box>
    )
  })
}

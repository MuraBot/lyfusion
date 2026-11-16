// Tests for the Fusion card (hooks/register.tsx), run with `claude plugin test plugin`. The engine is faked:
// every `fusion-core` command answers from here, and the calls are recorded. Not packaged (build_plugin.py skips tests/).
import { expect, test } from 'claude-code/testing'
import type { TestBody } from 'claude-code/testing'

const PANE = {
  plugin: 'lyfusion-plugin',
  component: 'Pane',
  requestId: 'fusion',
  props: {
    title: 'Fusion',
    isFocused: false,
    bodyColumns: 40,
    placement: 'widget',
    scroll: { offset: 0, bodyRows: 16 },
    view: {},
  },
} as const

function panelJson(version: string): string {
  return JSON.stringify({
    schema_version: 2,
    version,
    project: true,
    enabled: true,
    model: 'gpt-6-luna',
    models: ['gpt-6.1-sol', 'gpt-6-luna', 'custom-model'],
    unavailable: ['custom-model'],
    effort: 'high',
    efforts: ['high', 'xhigh', 'max'],
    recommended_effort: 'high',
    fast: false,
    fast_models: ['gpt-6.1-sol', 'gpt-6-luna'],
    model_names: { 'gpt-6.1-sol': 'GPT-6.1-Sol', 'gpt-6-luna': 'GPT-6-Luna', 'custom-model': 'custom-model' },
    compact: 400000,
    compacts: [262144, 400000, 600000, 800000],
    max_compact: 872000,
    context_ratio: 0.6,
    switch_at: 240000,
    handoff: { mode: 'write', tokens: 200000, modes: ['clear', 'write', 'off'], dir: 'fusion/handoffs' },
    warnings: [],
  })
}

type On = Parameters<TestBody>[1]

// A project that uses Fusion, an engine of `version`; returns the engine commands run and the toasts shown
function fakeEngine(on: On, version = '5.0.0-rc.4') {
  const calls: string[][] = []
  const toasts: string[] = []
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('session.root', () => ({ value: '/proj' }))
  on('fs.stat', () => ({ value: { kind: 'file', size: 1, mtimeMs: 0, isLink: false } }))
  on('process.run', (_, e) => {
    const args = e.argv.slice(2)
    calls.push(args)
    const stdout = args[0] === 'config' && args[1] === 'panel' ? `${panelJson(version)}\n` : ''
    return { value: { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('ui.toast', (_, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  on('ui.panes', () => ({ value: [] }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  return { calls, toasts }
}

function itemOf(found: { props: Record<string, unknown> } | undefined): Record<string, unknown> | undefined {
  const props = found?.props.props as { item?: Record<string, unknown> } | undefined
  return props?.item
}

test('the desktop card shows the settings and opens a list in place', async ($, on) => {
  const engine = fakeEngine(on)
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })

  expect(itemOf(await ui.find({ type: 'Client', key: 'row-nav-model' }))?.detail).toBe('GPT-6-Luna')
  expect(itemOf(await ui.find({ type: 'Client', key: 'row-nav-effort' }))?.detail).toBe('High')
  expect(itemOf(await ui.find({ type: 'Client', key: 'row-nav-compact' }))?.detail).toBe('400k')
  expect((await ui.find({ type: 'Svg' }))?.props.alt).toBe('Fusion on')

  // Reasoning effort: the list replaces the card; High is checked and recommended; Luna offers nothing below High
  await ui.post({ pick: 'nav', value: 'effort' }, { in: 'row-nav-effort' })
  const high = itemOf(await ui.find({ type: 'Client', key: 'row-effort-high' }))
  expect(high?.tag).toBe('Recommended')
  expect(high?.checked).toBe(true)
  expect(await ui.find({ type: 'Client', key: 'row-effort-low' })).toBeUndefined()
  expect(await ui.find({ type: 'Client', key: 'row-nav-model' })).toBeUndefined()

  await ui.post({ pick: 'effort', value: 'max' }, { in: 'row-effort-max' })
  expect(engine.calls).toContainEqual(['config', 'effort', 'max'])
  expect(await ui.find({ type: 'Client', key: 'row-nav-model' })).toBeDefined()

  // The sidekick list marks a model Codex does not offer, and it cannot be picked
  await ui.post({ pick: 'nav', value: 'model' }, { in: 'row-nav-model' })
  const custom = itemOf(await ui.find({ type: 'Client', key: 'row-model-custom-model' }))
  expect(custom?.tag).toBe('Unavailable')
  expect(custom?.disabled).toBe(true)
  await ui.post({ pick: 'back', value: 'back' }, { in: 'row-back-back' })

  // The switches
  await ui.post({ toggle: 'enabled' }, { in: 'hit-enabled' })
  expect(engine.calls).toContainEqual(['config', 'enabled', 'off'])
  await ui.post({ toggle: 'fast' }, { in: 'hit-fast' })
  expect(engine.calls).toContainEqual(['config', 'fast', 'on'])
  await ui.unmount()
})

test('a custom context limit is checked against the model maximum', async ($, on) => {
  const engine = fakeEngine(on)
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })

  await ui.post({ pick: 'nav', value: 'compact' }, { in: 'row-nav-compact' })
  expect((await ui.find({ type: 'Text', text: /Up to 872k for GPT-6-Luna/ }))?.text).toBeDefined()
  await ui.input({ key: 'compact-custom', text: '900' })
  expect((await ui.find({ type: 'Text', text: /Enter a number from 1 to 872/ }))?.text).toBeDefined()
  expect(engine.calls.some(args => args[1] === 'compact')).toBe(false)

  await ui.input({ key: 'compact-custom', text: '500k' })
  expect(engine.calls).toContainEqual(['config', 'compact', '500000'])
  await ui.unmount()
})

test('a newer engine on disk: one line, one toast, no setting changed', async ($, on) => {
  const engine = fakeEngine(on, '5.0.0-rc.5')
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })

  const line = await ui.find({ type: 'Text', text: /lyfusion was updated/ })
  expect(line?.text).toBe('lyfusion was updated (5.0.0-rc.4 → 5.0.0-rc.5). Start a new session to load it.')
  expect(await ui.find({ type: 'Client' })).toBeUndefined()
  expect(engine.toasts.filter(text => text.includes('Start a new session'))).toHaveLength(1)

  expect(engine.calls.filter(args => args[1] !== 'panel')).toEqual([])
  await ui.unmount()
})

test('a surface without Client or Svg gets the panel of Selects', async ($, on) => {
  const engine = fakeEngine(on)
  await $.session.start({ cwd: '/proj', surface: 'terminal', isInteractive: true })
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })

  expect((await ui.find({ type: 'Button', key: 'enabled' }))?.props.label).toBe('Turn Fusion off')
  await ui.select({ key: 'effort', value: 'xhigh' })
  expect(engine.calls).toContainEqual(['config', 'effort', 'xhigh'])
  await ui.unmount()
})

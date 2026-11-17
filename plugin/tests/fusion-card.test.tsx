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
function fakeEngine(on: On, version = '5.0.0-rc.9') {
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

const BAR = { plugin: 'lyfusion-plugin', component: 'SessionMode', props: { modes: [] } } as const

test('the desktop card shows the settings and opens a list in place', async ($, on) => {
  const engine = fakeEngine(on)
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })

  expect((await ui.find({ key: 'row-nav-model' }))?.text).toContain('GPT-6-Luna')
  expect((await ui.find({ key: 'row-nav-effort' }))?.text).toContain('High')
  expect((await ui.find({ key: 'row-nav-compact' }))?.text).toContain('400k')
  expect((await ui.find({ type: 'Svg' }))?.props.alt).toBe('Fusion on')
  // Each pickable row has the rounded highlight the surface shows on hover: two halves, each with a width of its own
  // (a "100%" picture is drawn 300 px wide and leaves a wide pane's row half grey)
  const halves = (await ui.findAll({ type: 'Svg' })).filter(svg => svg.props.alt.startsWith('Highlight'))
  expect(halves.filter(svg => svg.props.alt === 'Highlight')).toHaveLength(3)
  expect(halves.filter(svg => svg.props.alt === 'Highlight end')).toHaveLength(3)
  for (const svg of halves) expect(svg.props.source).not.toContain('width="100%"')

  // Reasoning effort: the list replaces the card; High is checked and recommended; Luna offers nothing below High
  await ui.post({ pick: 'nav', value: 'effort' }, { in: 'pick-nav-effort' })
  const high = (await ui.find({ key: 'row-effort-high' }))?.text
  expect(high).toContain('Recommended')
  expect(high).toContain('✓')
  expect(await ui.find({ key: 'row-effort-low' })).toBeUndefined()
  expect(await ui.find({ key: 'row-nav-model' })).toBeUndefined()

  await ui.post({ pick: 'effort', value: 'max' }, { in: 'pick-effort-max' })
  expect(engine.calls).toContainEqual(['config', 'effort', 'max'])
  expect(await ui.find({ key: 'row-nav-model' })).toBeDefined()

  // The sidekick list marks a model Codex does not offer: dim, no highlight and no click target
  await ui.post({ pick: 'nav', value: 'model' }, { in: 'pick-nav-model' })
  expect((await ui.find({ key: 'row-model-custom-model' }))?.text).toContain('Unavailable')
  expect(await ui.find({ type: 'Client', key: 'pick-model-custom-model' })).toBeUndefined()
  expect(await ui.find({ type: 'Client', key: 'pick-model-gpt-6.1-sol' })).toBeDefined()
  await ui.post({ pick: 'back', value: 'back' }, { in: 'pick-back-back' })

  // The switches
  await ui.post({ toggle: 'enabled' }, { in: 'hit-enabled' })
  expect(engine.calls).toContainEqual(['config', 'enabled', 'off'])
  await ui.post({ toggle: 'fast' }, { in: 'hit-fast' })
  expect(engine.calls).toContainEqual(['config', 'fast', 'on'])
  await ui.unmount()

  // The bar's dot is an emoji: the desktop draws a Button's Text children without their colours
  const bar = await $.ui.mount({ ...BAR, surface: 'desktop' })
  expect((await bar.find({ type: 'Button', key: 'fusion' }))?.props.label).toBe('🟠 Fusion')
  await bar.unmount()
})

test('a custom context limit is checked against the model maximum', async ($, on) => {
  const engine = fakeEngine(on)
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })

  await ui.post({ pick: 'nav', value: 'compact' }, { in: 'pick-nav-compact' })
  expect((await ui.find({ type: 'Text', text: /Up to 872k for GPT-6-Luna/ }))?.text).toBeDefined()
  await ui.input({ key: 'compact-custom', text: '900' })
  expect((await ui.find({ type: 'Text', text: /Enter a number from 1 to 872/ }))?.text).toBeDefined()
  expect(engine.calls.some(args => args[1] === 'compact')).toBe(false)

  await ui.input({ key: 'compact-custom', text: '500k' })
  expect(engine.calls).toContainEqual(['config', 'compact', '500000'])
  await ui.unmount()
})

test('a newer engine on disk: one line, one toast, no setting changed', async ($, on) => {
  const engine = fakeEngine(on, '5.0.0-rc.10')
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })

  const line = await ui.find({ type: 'Text', text: /lyfusion was updated/ })
  expect(line?.text).toBe('lyfusion was updated (5.0.0-rc.9 → 5.0.0-rc.10). Start a new session to load it.')
  expect(await ui.find({ type: 'Client' })).toBeUndefined()
  expect(engine.toasts.filter(text => text.includes('Start a new session'))).toHaveLength(1)

  expect(engine.calls.filter(args => args[1] !== 'panel')).toEqual([])
  await ui.unmount()
  const bar = await $.ui.mount({ ...BAR, surface: 'desktop' })
  expect((await bar.find({ type: 'Button', key: 'fusion' }))?.props.label).toBe('🟡 Fusion')
  await bar.unmount()
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

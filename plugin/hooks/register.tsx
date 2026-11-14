// lyfusion 的 Fusion 栏(rc.1 任务 6、7;lead 写)
// - SessionMode(输入框下方、模型选择器旁边):"● Fusion" 按钮。Fusion 开 = Claude 橙,关 = 灰;点它展开或收起面板
// - AbovePrompt(输入框上方):面板。开关、助手模型、思考强度、快速档、上下文上限
// - lead 跑 accept 时,把 $.session.usage() 交给引擎记进台账(任务 7),lead 不多花调用
// 读和改都调用引擎命令 fusion-core(config panel、config <动作>、lead-usage):
// 校验和格式版本只在引擎一处管,mod 不读写 fusion/ 下的文件,也不读 ~/.claude。
// 只在打开过 Fusion 的项目里画;没打开过的项目照桌面端原样。
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Notice, Panel } from '../types'

const PLUGIN = 'lyfusion-plugin'
const panel = atom({ plugin: PLUGIN, key: 'panel' } as const, null)
const isOpen = atom({ plugin: PLUGIN, key: 'isOpen' } as const, false)
const notice = atom({ plugin: PLUGIN, key: 'notice' } as const, null)

const EFFORT_LABEL: Record<string, string> = { low: '低', medium: '中', high: '高', xhigh: '超高' }
const ACCEPT = /fusion-core\.py["']?\s+accept\b/

function tokens(n: number): string {
  return n >= 1_000_000 ? `${+(n / 1_000_000).toFixed(2)}M` : `${Math.round(n / 1000)}k`
}

function lastLine(text: string): string {
  const lines = text.split(/\r?\n/).map(line => line.trim()).filter(Boolean)
  return lines[lines.length - 1] ?? ''
}

async function core($: EngineInterface, args: string[], stdin?: string) {
  const script = `${$.plugin.root}/core/fusion-core.py`
  return $.process.run(['python', script, ...args], stdin === undefined ? { timeoutMs: 20_000 } : { timeoutMs: 20_000, stdin })
}

function failure(result: { exitCode: number; stdout: string; stderr: string }): Notice {
  return { kind: 'error', text: lastLine(result.stderr) || lastLine(result.stdout) || `fusion-core 退出码 ${result.exitCode}` }
}

// 向引擎要面板数据。失败时保留上一次的数据,把原因放进提示
async function refresh($: EngineInterface): Promise<void> {
  try {
    const result = await core($, ['config', 'panel'])
    if (result.exitCode !== 0) {
      await update($, notice, () => failure(result))
      return
    }
    const data = JSON.parse(lastLine(result.stdout))
    await update($, panel, () => (data && data.project === true ? (data as Panel) : null))
  } catch (err) {
    await update($, notice, () => ({ kind: 'error', text: `调用 fusion-core 失败:${String(err)}` }) as Notice)
  }
}

// 改一项设置:fusion-core config <动作> <值>,再刷新面板
async function change($: EngineInterface, args: string[], done: Notice | null = null): Promise<void> {
  try {
    const result = await core($, ['config', ...args])
    await update($, notice, () => (result.exitCode === 0 ? done : failure(result)))
  } catch (err) {
    await update($, notice, () => ({ kind: 'error', text: `调用 fusion-core 失败:${String(err)}` }) as Notice)
  }
  await refresh($)
}

async function recordLeadUsage($: EngineInterface, task: string | undefined): Promise<void> {
  try {
    const usage = await $.session.usage()
    const args = ['lead-usage', ...(task ? ['--task', task] : []), '-']
    const result = await core($, args, JSON.stringify(usage))
    if (result.exitCode !== 0) {
      $.ui.log(`lead-usage: ${failure(result).text}`, { to: 'debug' })
    }
  } catch (err) {
    $.ui.log(`lead-usage: ${String(err)}`, { to: 'debug' })
  }
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const started = await next(e)
    void refresh($)
    return started
  })

  // 一轮结束时刷新:lead 或 /fusion 在这一轮里可能改过设置
  on('turn.complete', async ($, e, next) => {
    const done = await next(e)
    void refresh($)
    return done
  })

  // 任务 7:lead 跑 accept 时记一次用量。不等它、不拦命令
  on('tool.call', { tool: 'Bash' }, ($, e, next) => {
    if (ACCEPT.test(e.command)) {
      void recordLeadUsage($, /--task[ =](\S+)/.exec(e.command)?.[1])
    }
    return next(e)
  })

  on('ui.render', { component: 'SessionMode' }, async ($, e, next) => {
    const state = await read($, panel)
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
    if (!state) {
      return next(e)
    }
    const note = await read($, notice)
    const table = $.ui.resolve(e)
    const { Box, Text, Button } = table
    const Select = 'Select' in table ? table.Select : undefined
    const enabled = state.enabled
    const status = enabled ? '已开:代码活交给 Codex 助手' : '已关'

    const pickers = Select ? (
      <Box flexDirection="row" alignItems="center" gap="md" flexWrap="wrap">
        <Select
          key="model"
          label="助手"
          options={state.models.map(value => ({ value }))}
          value={state.model}
          onSelect={value => void change($, ['model', value])}
        />
        <Select
          key="effort"
          label="思考强度"
          options={state.efforts.map(value => ({ value, label: EFFORT_LABEL[value] ?? value }))}
          value={state.effort}
          onSelect={value => void change($, ['effort', value])}
        />
        <Select
          key="fast"
          label="快速档"
          options={[{ value: 'off', label: '关' }, { value: 'on', label: '开' }]}
          value={state.fast ? 'on' : 'off'}
          onSelect={value => void change($, ['fast', value])}
        />
        <Select
          key="compact"
          label="上下文上限"
          options={state.compacts.map(n => ({ value: String(n), label: tokens(n) }))}
          value={String(state.compact)}
          onSelect={value => void change($, ['compact', value])}
        />
        <Text dimColor>到 {tokens(state.switch_at)} 换工位</Text>
      </Box>
    ) : (
      <Text dimColor>
        助手 {state.model} · 思考强度 {EFFORT_LABEL[state.effort] ?? state.effort} · 快速档 {state.fast ? '开' : '关'} · 上下文上限{' '}
        {tokens(state.compact)}
      </Text>
    )

    return (
      <Box flexDirection="column" gap="sm" paddingX="md" paddingY="sm" borderStyle="round" borderColor="promptBorder">
        <Box flexDirection="row" alignItems="center" justifyContent="space-between" gap="md">
          <Box flexDirection="row" alignItems="center" gap="sm">
            <Text color={enabled ? 'claude' : 'inactive'}>●</Text>
            <Text weight="semibold">Fusion</Text>
            <Text dimColor>{status}</Text>
          </Box>
          <Box flexDirection="row" alignItems="center" gap="sm">
            <Button
              key="enabled"
              variant={enabled ? 'secondary' : 'primary'}
              label={enabled ? '关闭 Fusion' : '打开 Fusion'}
              onPress={() =>
                void change(
                  $,
                  ['enabled', enabled ? 'off' : 'on'],
                  enabled ? null : { kind: 'info', text: '已打开。新开的会话里 lead 才会收到使用说明' },
                )
              }
            />
            <Button key="close" role="dismiss" label="收起" onPress={() => void update($, isOpen, () => false)} />
          </Box>
        </Box>
        {pickers}
        {state.warnings.length > 0 ? <Text color="warning">{state.warnings.join('\n')}</Text> : null}
        {note ? note.kind === 'error' ? <Text color="error">{note.text}</Text> : <Text dimColor>{note.text}</Text> : null}
      </Box>
    )
  })
}

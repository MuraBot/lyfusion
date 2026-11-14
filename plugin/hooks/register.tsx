// lyfusion 的 Fusion 栏(rc.1 任务 6、7;lead 写)
// - SessionMode(输入框下方、模型选择器旁边):"● Fusion" 按钮。Fusion 开 = Claude 橙,关 = 灰;点它展开或收起面板
// - AbovePrompt(输入框上方):面板。开关、助手模型、思考强度、Fast Mode、上下文上限
// - lead 跑 explore、accept 时,把 $.session.usage() 交给引擎记进台账(任务 7),lead 不多花调用
// 读和改都调用引擎命令 fusion-core(config panel、config <动作>、lead-usage):
// 校验和格式版本只在引擎一处管,mod 不写 fusion/ 下的文件,也不读 ~/.claude。
// 引擎命令失败时不藏起来:栏照画(灰),第一次失败弹 toast,面板里写原因;
// 这时只读 fusion/local.json 显示开关和助手模型(只读退路),改设置请用 /fusion。
// 中途开关(面板或 /fusion)下一条消息起生效:prompt.submit 在 context 里附 lead 使用说明或"已关"一句,不改系统提示。
// 只在打开过 Fusion 的项目里画;没打开过的项目照桌面端原样。
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Notice, Panel } from '../types'

const panel = atom({ plugin: 'lyfusion-plugin', key: 'panel' } as const, null)
const isOpen = atom({ plugin: 'lyfusion-plugin', key: 'isOpen' } as const, false)
const notice = atom({ plugin: 'lyfusion-plugin', key: 'notice' } as const, null)
const leadKnows = atom({ plugin: 'lyfusion-plugin', key: 'leadKnows' } as const, null)

// 中途开关(Lily 定,rc.1):在面板或 /fusion 里开关后,下一条消息起生效。
// 用 prompt.submit 在下一条消息的 context 里附说明(打开 = lead 使用说明,关闭 = 一句话);
// 状态没变就什么都不附。不改系统提示,不主动发起对话
const FUSION_COMMAND = /^\/(lyfusion-plugin:)?fusion\b/
const OFF_NOTE =
  'Fusion 已关(用户在会话中途关掉的):这个项目不再用 explore、delegate、revise、accept 4 个动作,代码活照常由你自己做。'
let guide: string | null = null // 引擎给的 lead 使用说明,打开 Fusion 后提前取好
let fusionCommand = false // 这一轮里用户跑了 /fusion:命令的输出 lead 已经看到,不再另附说明

const EFFORT_LABEL: Record<string, string> = { low: '低', medium: '中', high: '高', xhigh: '超高', max: '最高', ultra: '极限' }
// lead 跑这两条命令时各记一次用量快照:任务的 lead 花费 = 最后一次 accept − explore(同一个会话才算)
const SNAPSHOT_AT = /fusion-core\.py["']?\s+(explore|accept)\b/

// 下拉框里显示好读的模型名,存的值不变。优先用引擎给的显示名(model_names,和 Codex 自己的写法一样);
// 引擎表里没有的模型照同样的写法:gpt-7-nova → GPT-7-Nova
function modelName(id: string): string {
  return id
    .split('-')
    .map(word => (word.toLowerCase() === 'gpt' ? 'GPT' : word ? word[0].toUpperCase() + word.slice(1) : word))
    .join('-')
}

function tokens(n: number): string {
  return n >= 1_000_000 ? `${+(n / 1_000_000).toFixed(2)}M` : `${Math.round(n / 1000)}k`
}

function lastLine(text: string): string {
  const lines = text.split(/\r?\n/).map(line => line.trim()).filter(Boolean)
  return lines[lines.length - 1] ?? ''
}

// 引擎一律在会话的项目目录里跑:桌面端先在预备目录(~/.claude/spares/…)起好进程,之后才挂到项目,
// 进程自己的工作目录靠不住
async function core($: EngineInterface, args: string[], stdin?: string) {
  const script = `${$.plugin.root}/core/fusion-core.py`
  const cwd = await $.session.root()
  return $.process.run(['python', script, ...args], stdin === undefined ? { cwd, timeoutMs: 20_000 } : { cwd, timeoutMs: 20_000, stdin })
}

async function exists($: EngineInterface, path: string): Promise<boolean> {
  try {
    await $.fs.stat(path)
    return true
  } catch {
    return false
  }
}

// 会话换了目录(预备目录 → 项目,或 /cd):清掉旧项目的面板;会话开始时的钩子是在旧目录跑的,
// 没给这个项目注入过说明,所以 lead 以为的开关记成"关"(Fusion 开着的话,下一条消息附说明;宁可重复,不能漏)
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
  const why = lastLine(result.stderr) || lastLine(result.stdout) || '没有输出'
  return { kind: 'error', text: `fusion-core 退出码 ${result.exitCode}:${why}` }
}

let requested = false // 这次加载后有没有向引擎要过面板数据(模块可能在 session.start 之后才加载)
let warned = false // 引擎命令失败的 toast 只弹一次

async function fail($: EngineInterface, problem: Notice): Promise<void> {
  await update($, notice, () => problem)
  if (!warned) {
    warned = true
    $.ui.toast(`Fusion 栏:${problem.text}`)
  }
}

// 向引擎要面板数据。失败时保留上一次的数据,把原因放进提示
async function refresh($: EngineInterface): Promise<void> {
  requested = true
  try {
    // 预备目录和没用过 Fusion 的项目是正常情况:不调引擎、不算错
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
    // 底栏和面板都读 panel;请桌面端把两处一起重画(Lily 截到过:面板已开、底栏圆点还是灰的)
    $.ui.invalidate('ui.render')
    await update($, notice, current => (current?.kind === 'error' ? null : current))
    if (next) {
      const known = await read($, leadKnows)
      if (known === null || known === undefined) {
        // 第一次拿到状态:SessionStart 钩子只在 Fusion 开着时注入说明,所以 lead 知道的就是现在的开关
        await update($, leadKnows, () => next.enabled)
      } else if (next.enabled && !known && guide === null) {
        void fetchGuide($)
      }
    }
  } catch (err) {
    await fail($, { kind: 'error', text: `调用 fusion-core 失败:${String(err)}` })
  }
}

// lead 使用说明从引擎拿(和 SessionStart 钩子同一条命令,说明文字只在引擎一处)
async function fetchGuide($: EngineInterface): Promise<void> {
  try {
    const root = await $.session.root()
    const result = await core($, ['hook', 'session-start'], JSON.stringify({ cwd: root, source: 'fusion-panel' }))
    const text = result.exitCode === 0 && result.stdout.trim() ? JSON.parse(result.stdout)?.hookSpecificOutput?.additionalContext : null
    if (typeof text === 'string' && text) {
      guide = text
    }
  } catch {
    // 拿不到就用 openNote 里的退路文字
  }
}

function openNote($: EngineInterface): string {
  return (
    guide ??
    `Fusion 已打开(用户在会话中途打开的)。运行 python "${$.plugin.root}/core/fusion-core.py" on 看 lead 的使用说明(已开着时只打印说明)。`
  )
}

type Local = { enabled: boolean; model: string }

// 只读退路:引擎命令还没成功过时,读 local.json 判断是不是 Fusion 项目、开没开。不写
async function localState($: EngineInterface): Promise<Local | null> {
  const root = await $.session.root()
  try {
    const local = JSON.parse(await $.fs.read(`${root}/fusion/local.json`))
    return { enabled: Boolean(local?.enabled), model: String(local?.sidekick?.model ?? '') }
  } catch {
    // 没有 local.json:再看项目设置在不在(本机没打开过,但项目用 Fusion)
  }
  return (await exists($, `${root}/fusion/config.json`)) ? { enabled: false, model: '' } : null
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

// 原样交给引擎:cost 是会话累计值、rateLimits 是整个账号的,怎么求差由引擎在读台账时算
async function recordLeadUsage($: EngineInterface, at: string, task: string | undefined): Promise<void> {
  try {
    const usage = await $.session.usage()
    const args = ['lead-usage', '--at', at, ...(task ? ['--task', task] : []), '-']
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
    void rootChanged($).then(() => refresh($))
    return started
  })

  // 桌面端把预备进程挂到项目、或 /cd 时
  on('classic.CwdChanged', async ($, e, next) => {
    const done = await next(e)
    void rootChanged($).then(() => refresh($))
    return done
  }).catch(($, e, next) => next(e)) // mod 自己出错时照常放行

  // 一轮结束时刷新:lead 或 /fusion 在这一轮里可能改过设置
  on('turn.complete', async ($, e, next) => {
    const done = await next(e)
    void (async () => {
      await rootChanged($)
      await refresh($)
      if (fusionCommand) {
        // /fusion on|off 的输出 lead 已经看到:lead 知道的就是现在的开关
        fusionCommand = false
        const state = await read($, panel)
        if (state) {
          await update($, leadKnows, () => state.enabled)
        }
      }
    })()
    return done
  })

  // 中途开关:下一条消息起生效。平时只用缓存的状态,不调用引擎(发消息不能卡);
  // 只有会话刚换到这个项目时等一次刷新和说明(约几百毫秒),免得第一条消息漏掉说明
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
  }).catch(($, e, next) => next(e)) // mod 自己出错时照常放行,不拦消息和命令

  // 任务 7:lead 跑 explore、accept 时记用量快照。不等它、不拦命令
  on('tool.call', { tool: 'Bash' }, ($, e, next) => {
    const at = SNAPSHOT_AT.exec(e.command)?.[1]
    if (at) {
      void recordLeadUsage($, at, /--task[ =](\S+)/.exec(e.command)?.[1])
    }
    return next(e)
  }).catch(($, e, next) => next(e)) // mod 自己出错时照常放行,不拦消息和命令

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
      // 引擎命令还没成功过:只读显示,写清原因
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
                {local.enabled ? '已开' : '已关'}
                {local.model ? ` · 助手 ${local.model}` : ''}(只读)
              </Text>
            </Box>
            <Button key="close" role="dismiss" label="收起" onPress={() => void update($, isOpen, () => false)} />
          </Box>
          {note?.kind === 'error' ? <Text color="error">{note.text}</Text> : <Text dimColor>正在向引擎读取设置…</Text>}
          <Text dimColor>引擎命令调用失败时,改设置请用 /fusion</Text>
        </Box>
      )
    }
    const Select = 'Select' in table ? table.Select : undefined
    const enabled = state.enabled
    const name = (id: string) => state.model_names?.[id] ?? modelName(id)
    // 哪些模型支持 Fast Mode 由引擎给(fast_models);旧引擎没给这个字段时照旧可选。
    // 不支持时画成灰字(桌面端的 Select 没有"禁用",灰字点不了)
    const fastOk = !state.fast_models || state.fast_models.includes(state.model)

    const pickers = Select ? (
      <Box flexDirection="row" alignItems="center" gap="md" flexWrap="wrap">
        <Select
          key="model"
          label="助手"
          options={state.models.map(value => ({ value, label: name(value) }))}
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
        {fastOk ? (
          <Select
            key="fast"
            label="Fast Mode"
            options={[{ value: 'off', label: '关' }, { value: 'on', label: '开' }]}
            value={state.fast ? 'on' : 'off'}
            onSelect={value => void change($, ['fast', value])}
          />
        ) : (
          <Text dimColor>Fast Mode 不支持</Text>
        )}
        <Select
          key="compact"
          label="上下文上限"
          options={state.compacts.map(n => ({ value: String(n), label: tokens(n) }))}
          value={String(state.compact)}
          onSelect={value => void change($, ['compact', value])}
        />
      </Box>
    ) : (
      <Text dimColor>
        助手 {name(state.model)} · 思考强度 {EFFORT_LABEL[state.effort] ?? state.effort} · Fast Mode{' '}
        {fastOk ? (state.fast ? '开' : '关') : '不支持'} · 上下文上限 {tokens(state.compact)}
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
              label={enabled ? '关闭 Fusion' : '打开 Fusion'}
              onPress={() =>
                void change(
                  $,
                  ['enabled', enabled ? 'off' : 'on'],
                  { kind: 'info', text: '下一条消息起生效' },
                )
              }
            />
            <Button key="close" role="dismiss" label="收起" onPress={() => void update($, isOpen, () => false)} />
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
      </Box>
    )
  })
}

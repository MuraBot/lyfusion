// lyfusion M3 小试验(只读):
// 1. SessionMode(输入框底栏右侧的模式标签)画"● Fusion":Fusion 开 = Claude 橙,关 = 灰;点它开关面板
// 2. AbovePrompt(输入框上方)在点开时画一条面板:开关状态、助手模型
// 3. PromptHint(输入框下方提示行)加 tail(文档说只有终端画)
// 只读 <项目>/fusion/local.json,不写任何文件。
import { atom, read, update } from 'claude-code'
import type { Engine, Register } from 'claude-code'

const isOpen = atom({ plugin: 'lyfusion-spike', key: 'isOpen' } as const, false)

type Fusion = { found: boolean; enabled: boolean; model: string }

async function fusionState($: Engine): Promise<Fusion> {
  try {
    const root = await $.session.root()
    const text = await $.fs.read(`${root}/fusion/local.json`)
    const local = JSON.parse(text)
    return { found: true, enabled: Boolean(local.enabled), model: String(local.sidekick?.model ?? '') }
  } catch {
    return { found: false, enabled: false, model: '' }
  }
}

export const register: Register = on => {
  on('ui.render', { component: 'SessionMode' }, async ($, e, next) => {
    const fusion = await fusionState($)
    if (!fusion.found) {
      return next(e)
    }
    const { Box, Text, Button } = $.ui.resolve(e)
    const modes = e.props.modes.join(' & ')
    return (
      <Box>
        {modes ? <Text dimColor>{modes} </Text> : null}
        <Text color={fusion.enabled ? 'claude' : 'inactive'}>● </Text>
        <Button key="fusion" label="Fusion" onPress={() => update($, isOpen, open => !open)} />
      </Box>
    )
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (!(await read($, isOpen))) {
      return next(e)
    }
    const fusion = await fusionState($)
    const { Box, Text, Button } = $.ui.resolve(e)
    return (
      <Box>
        <Text color={fusion.enabled ? 'claude' : 'inactive'}>● </Text>
        <Text>
          Fusion {fusion.found ? (fusion.enabled ? '开' : '关') : '没有打开过'}
          {fusion.model ? ` · 助手 ${fusion.model}` : ''}(试验面板,只读){' '}
        </Text>
        <Button key="close" label="收起" onPress={() => update($, isOpen, () => false)} />
      </Box>
    )
  })

  on('ui.render', { component: 'PromptHint' }, async ($, e, next) => {
    const fusion = await fusionState($)
    if (!fusion.found) {
      return next(e)
    }
    return next({ ...e, props: { ...e.props, tail: ` · Fusion ${fusion.enabled ? 'on' : 'off'}` } })
  })
}

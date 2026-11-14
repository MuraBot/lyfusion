// lyfusion Fusion 栏 mod 的状态类型(rc.1 任务 6、7)
// Panel 是 `fusion-core config panel` 打印的那一行 JSON;字段由引擎定,这里只照抄
export type Panel = {
  schema_version: number
  project: true
  enabled: boolean
  model: string
  models: string[]
  effort: string
  efforts: string[]
  fast: boolean
  compact: number
  compacts: number[]
  context_ratio: number
  switch_at: number
  warnings: string[]
}

// 面板里最后一条提示:引擎命令失败的原因,或者打开 Fusion 后的说明
export type Notice = { kind: 'error' | 'info'; text: string }

declare module 'claude-code' {
  interface PluginState {
    'lyfusion-plugin': { panel: Panel | null; isOpen: boolean; notice: Notice | null }
  }
}

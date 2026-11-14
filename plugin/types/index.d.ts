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
  fast_models?: string[] // 支持 Fast Mode 的模型(rc.1 起引擎给;旧引擎没有)
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
    // leadKnows:这个会话的 lead 现在以为 Fusion 是开(true)还是关(false);null = 还不知道
    'lyfusion-plugin': { panel: Panel | null; isOpen: boolean; notice: Notice | null; leadKnows: boolean | null }
  }
}

// State types for the lyfusion Fusion bar mod (rc.1 tasks 6 and 7)
// Panel is the one-line JSON printed by `fusion-core config panel`; the engine defines the fields, this only mirrors them
export type Panel = {
  schema_version: number
  project: true
  enabled: boolean
  model: string
  models: string[]
  effort: string
  efforts: string[]
  fast: boolean
  fast_models?: string[] // models that support Fast Mode (sent since rc.1; older engines omit it)
  model_names?: Record<string, string> // display names, e.g. gpt-6-luna → GPT-6-Luna
  compact: number
  compacts: number[]
  context_ratio: number
  switch_at: number
  warnings: string[]
  // Lead handoff mode (rc.2 task 10); older engines do not send it
  handoff?: { mode: string; tokens: number; modes: string[]; dir: string }
}

// The panel's last notice: why an engine command failed, or the note after turning Fusion on
export type Notice = { kind: 'error' | 'info'; text: string }

declare module 'claude-code' {
  interface PluginState {
    // leadKnows: whether this session's lead currently believes Fusion is on (true) or off (false); null = not known yet
    'lyfusion-plugin': { panel: Panel | null; isOpen: boolean; notice: Notice | null; leadKnows: boolean | null }
  }
}

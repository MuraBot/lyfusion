// State types for the lyfusion Fusion bar mod (rc.1 tasks 6 and 7; the card rc.4)
// Panel is the one-line JSON printed by `fusion-core config panel`; the engine defines the fields, this only mirrors them
export type Panel = {
  schema_version: number
  version?: string // the engine's version (rc.4); the mod compares it with its own build
  project: true
  enabled: boolean
  model: string
  models: string[]
  unavailable?: string[] // sidekick models Codex does not list: shown, not pickable (rc.4; the whitelist rc.5)
  effort: string | null
  efforts: string[]
  recommended_effort?: string | null // rc.4
  fast: boolean
  fast_models?: string[] // models that support Fast Mode (sent since rc.1; older engines omit it)
  model_names?: Record<string, string> // display names, e.g. gpt-6-luna → GPT-6-Luna
  compact: number
  compacts: number[]
  max_compact?: number | null // the model's largest context limit; null when unknown (rc.4)
  context_ratio: number
  switch_at: number
  warnings: string[]
  // Lead handoff mode (rc.2 task 10); older engines do not send it
  handoff?: { mode: string; tokens: number; modes: string[]; dir: string }
}

// The panel's last notice: why an engine command failed, or the note after turning Fusion on
export type Notice = { kind: 'error' | 'info'; text: string }

// The engine on disk is not the one this session's mod was built with (a new package was uploaded mid-session)
export type Stale = { from: string; to: string }

declare module 'claude-code' {
  interface PluginState {
    // leadKnows: whether this session's lead currently believes Fusion is on (true) or off (false); null = not known yet
    // view: the card's page, 'main' or the list it shows ('model', 'effort', 'compact'); hint: the custom context input's error
    'lyfusion-plugin': {
      panel: Panel | null
      notice: Notice | null
      leadKnows: boolean | null
      view: string
      hint: string | null
      stale: Stale | null
    }
  }
}

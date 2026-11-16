// One menu row of the Fusion card, drawn inside a Client like a row of the desktop's model picker (rc.4, lead).
// Highlighted under the pointer; a small tag right after the label (Recommended, Unavailable); dim text, a check
// or a chevron at the right; dim and inert when it cannot be picked. One Client per row, so a click anywhere on it
// means this row and rows can sit apart. A click posts { pick: id, value } to register.tsx (ui.message).
import type { ClientModule } from 'claude-code'

type Item = {
  value: string
  label: string
  detail?: string // dim text at the right: the current value of a row that opens a list
  tag?: string // small badge right after the label
  chevron?: boolean
  checked?: boolean
  disabled?: boolean
  strong?: boolean
}
type Props = { id: string; item: Item }
type State = { hover: boolean }

// Half-transparent grey reads on light and dark themes alike
const HOVER = 'rgba(128,128,128,0.22)'
const BADGE = 'rgba(128,128,128,0.18)'

const Row: ClientModule<Props, State> = (props, surface) => {
  const { Box, Text } = surface.elements
  const item = props.item
  const hover = surface.state?.hover ?? false
  surface.onPointer(event => {
    if (event.type === 'enter' || event.type === 'move') {
      if (!hover && !item.disabled) surface.setState({ hover: true })
      return
    }
    if (event.type === 'leave') {
      if (hover) surface.setState({ hover: false })
      return
    }
    if (event.type === 'down' && event.button === 'left' && !item.disabled) {
      surface.post({ pick: props.id, value: item.value })
    }
  })
  return (
    <Box
      width={surface.columns || undefined}
      height={1}
      flexDirection="row"
      alignItems="center"
      justifyContent="space-between"
      gap={1}
      paddingX={1}
      backgroundColor={hover ? HOVER : undefined}
    >
      <Box flexDirection="row" alignItems="center" gap={1}>
        <Text dimColor={item.disabled} weight={item.strong ? 'semibold' : undefined} wrap="truncate-end">
          {item.label}
        </Text>
        {item.tag ? (
          <Text dimColor size="caption" backgroundColor={BADGE}>
            {` ${item.tag} `}
          </Text>
        ) : null}
      </Box>
      <Box flexDirection="row" alignItems="center" gap={1}>
        {item.detail ? <Text dimColor>{item.detail}</Text> : null}
        {item.checked ? <Text color="suggestion">✓</Text> : null}
        {item.chevron ? <Text dimColor>›</Text> : null}
      </Box>
    </Box>
  )
}

export default Row

// The click target over a switch picture of the Fusion card (rc.4, lead). An Svg cannot be pressed and a Button
// holds only text, so this empty Client lies over the picture: it draws nothing and only hears the click,
// posting { toggle: id } to register.tsx (ui.message).
import type { ClientModule } from 'claude-code'

type Props = { id: string }

const Hit: ClientModule<Props> = (props, surface) => {
  const { Box } = surface.elements
  surface.onPointer(event => {
    if (event.type === 'down' && event.button === 'left') {
      surface.post({ toggle: props.id })
    }
  })
  return <Box width={surface.columns || 5} height={surface.rows || 1} />
}

export default Hit

// The click target of the Fusion card (rc.4, lead; rows since rc.5). An Svg cannot be pressed, a Button holds only text
// and a Client cannot draw an Svg, so the card draws its rows and switch pictures itself and lays this empty Client over
// each: it draws nothing and only hears the click, posting its data ({ toggle } or { pick, value }) to register.tsx
// (ui.message).
import type { ClientModule } from 'claude-code'

type Props = { data: { toggle: string } | { pick: string; value: string } }

const Hit: ClientModule<Props> = (props, surface) => {
  const { Box } = surface.elements
  surface.onPointer(event => {
    if (event.type === 'down' && event.button === 'left') {
      surface.post(props.data)
    }
  })
  return <Box width={surface.columns || 5} height={surface.rows || 1} />
}

export default Hit

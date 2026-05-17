import { type VehiclePositionMessage } from './types'

type WebSocketEventHandlers = {
  onopen?: ((event: Event) => any) | null  // eslint-disable-line @typescript-eslint/no-explicit-any
  onmessage?: ((event: MessageEvent<VehiclePositionMessage>) => any) | null  // eslint-disable-line @typescript-eslint/no-explicit-any
  onclose?: ((event: CloseEvent) => any) | null  // eslint-disable-line @typescript-eslint/no-explicit-any
  onerror?: ((event: Event) => any) | null  // eslint-disable-line @typescript-eslint/no-explicit-any
}

function getWebSocket(routeId: string, eventHandlers: WebSocketEventHandlers) {
  const ws = new WebSocket(
    `${import.meta.env.VITE_WS_URL}/ws/vehicles/${routeId}`
  )
  const { onopen, onclose, onmessage, onerror } = eventHandlers

  ws.onopen = onopen || null
  ws.onclose = onclose || null
  ws.onmessage = onmessage || null
  ws.onerror = onerror || null

  return ws
}

export default {
  getWebSocket
}

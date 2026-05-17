// REST API calls
import { type LatLon, type RoutePlan } from './types'

async function getRoutePlan(start: LatLon, end: LatLon): Promise<RoutePlan> {
  const body = {
    from_lat: start.lat,
    from_lon: start.lng,
    to_lat: end.lat,
    to_lon: end.lng
  }

  const response = await fetch(`${import.meta.env.VITE_API_URL}/api/plan`, {
    method: 'POST',
    body: JSON.stringify(body),
    headers: {
      'Content-type': 'application/json'
    }
  })

  if (!response.ok) {
    console.error(response.statusText)
    throw new Error('Failed to get route plan')
  }

  const data = await response.json()

  return data
}

export default {
  getRoutePlan
}

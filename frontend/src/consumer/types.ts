type RouteLeg = {
  mode: string
  route_id: string
  route_name: string
  from_name: string
  to_name: string
  departure_time: string
  arrival_time: string
  duration_minutes: number
  geometry: [number, number][]
}

export type Route = {
  route_id: string
  route_name: string
  departure_time: string
  arrival_time: string
  duration_minutes: number
  walk_distance_meters: number
  legs: RouteLeg[]
}

export type RoutePlan = {
  from: {
    name: string
    lat: number
    lon: number
  }
  to: {
    name: string
    lat: number
    lon: number
  }
  routes: Route[]
}

export type LatLon = {
  lat: number
  lng: number
}

export type VehiclePosition = {
  bearing: number
  current_stop: string | null
  delay_label: string
  delay_seconds: number
  id: string
  is_delay_realtime: boolean
  label: string
  lat: number
  lon: number
  next_stop: string | null
  route_id: string
  speed_kmh: number
  timestamp: number // Unix timestamp
  trip_id: string
}

export type VehiclePositionMessage = {
  route_id: string
  vehicle_count: number
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  alerts: any[]
  freshness: {
    level: string
    label: string
    age_seconds: number
  }
  vehicles: VehiclePosition[]
}

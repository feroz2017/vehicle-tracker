import { useState, useRef } from 'react'
import { type LatLngLiteral } from 'leaflet'
import {
  type VehiclePositionMessage,
  type RoutePlan,
  type Route,
} from './consumer/types'
import './App.css'

import { Map } from './components/Map'
import api from './consumer/api'
import ws from './consumer/websocket'

function App() {
  const [locating, setLocating] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')

  // Start and end coordinates
  const [start, setStart] = useState<LatLngLiteral | null>(null)
  const [end, setEnd] = useState<LatLngLiteral | null>(null)

  // Possible route plans between start and end
  const [routePlans, setRoutePlans] = useState<RoutePlan | null>()

  // Selected route for tracking
  const [selectedRoute, setSelectedRoute] = useState<Route | null>()

  // Latest vehicle positions on tracked route
  const [vehiclePositions, setVehiclePositions] =
    useState<VehiclePositionMessage | null>()

  // Manage WebSocket connection for vehicle tracking
  const wsRef = useRef<WebSocket>(null)

  function addNewMarker(latlng: LatLngLiteral) {
    if (!start) setStart(latlng)
    else if (!end) setEnd(latlng)
  }

  function updateMarker(location: string, latlng: LatLngLiteral) {
    setSelectedRoute(null)
    setVehiclePositions(null)
    setRoutePlans(null)

    // We picked a new route, close previous WS connection
    if (wsRef.current) wsRef.current.close()

    if (location === 'start') setStart(latlng)
    else if (location === 'end') setEnd(latlng)
  }

  function getRoutes() {
    if (!start || !end) return // TODO validation
    api.getRoutePlan(start, end).then(routePlan => {
      setRoutePlans(routePlan)
    }).catch(error => {
      console.error(error)
      showErrorMsg('Could not get routing data')
    })
  }

  function trackRoute(route: Route) {
    setSelectedRoute(route)

    const routeId = route.route_id
    console.debug(`Subscribing to route ${routeId}`)

    if (wsRef.current) wsRef.current.close()

    const onopen = () => console.debug('WebSocket connected')
    const onclose = () => console.debug('WebSocket closed')
    const onerror = (err: Event) => console.error('WebSocket error:', err)
    const onmessage = (event: MessageEvent) => {
      // console.debug('Message received:', event.data)
      try {
        const data: VehiclePositionMessage = JSON.parse(
          event.data as unknown as string
        )
        setVehiclePositions(data)
      } catch (error) {
        showErrorMsg('Could not get vehicle data')
        console.error(error)
      }
    }

    wsRef.current = ws.getWebSocket(routeId, {
      onopen,
      onclose,
      onerror,
      onmessage
    })
  }

  function untrackRoute() {
    setSelectedRoute(null)
    setVehiclePositions(null)

    if (wsRef.current) wsRef.current.close()
  }

  function showErrorMsg(errorMsg: string) {
    if (errorMsg) setErrorMsg('')
    setErrorMsg(errorMsg)

    setTimeout(() => setErrorMsg(''), 4000)
  }

  return (
    <>
      <div className='flex flex-col md:flex-row w-screen h-screen'>
        <div className='px-3 flex flex-col max-w-150 md:min-w-130 md:h-full bg-cyan-600/20'>
          <ErrorMsg text={errorMsg}/>
          <div className='max-h-120'>
            <details className='pb-1 pt-3' open={true}>
              <summary className='py-2'>Pick start/end point</summary>
              <div className='mb-1 flex md:flex-row flex-col '>
                <Location
                  location='start'
                  latlng={start}
                  updateLocation={updateMarker}
                  loading={locating}
                  setLoading={setLocating}
                  onError={showErrorMsg}
                />
                <Location
                  location='end'
                  latlng={end}
                  updateLocation={updateMarker}
                  loading={locating}
                  setLoading={setLocating}
                  onError={showErrorMsg}
                />
              </div>
              {locating ? <div>Locating...</div> : null}
              <button
                className='mb-2 px-2 py-1 text-white rounded-md bg-cyan-700 enabled:hover:bg-cyan-700/80 disabled:text-white/50 transition'
                onClick={getRoutes}
                disabled={locating}
              >
                <span className='mdi mdi-magnify mr-2'></span>
                Plan route
              </button>
            </details>
          </div>
          <div>
            <TrackedRoute
              route={selectedRoute}
              vehiclePositions={vehiclePositions}
            />
          </div>
          <div className='divider my-3' />
          <div className='w-full '>
            <details open={true}>
              <summary className='pt-2 pb-5'>Pick a route</summary>
              <div className='max-h-50 md:max-h-full flex flex-col'>
                <RoutePlan
                  routePlans={routePlans?.routes}
                  selected={selectedRoute}
                  onSelect={trackRoute}
                  onDeselect={untrackRoute}
                />
              </div>
            </details>
          </div>
        </div>
        <Map
          start={start}
          end={end}
          onAddMarker={addNewMarker}
          updateMarker={updateMarker}
          route={selectedRoute}
          vehicles={vehiclePositions?.vehicles || []}
        />
      </div>
    </>
  )
}

function ErrorMsg({ text }: {text: string}) {
  return <div className="bg-red-600 rounded-md mt-2 px-2 py-1.5 text-red-50" hidden={!text}>
    <span className="mdi mdi-alert mr-2"></span>
      {text}
    </div>
}

type LocationProps = {
  location: string
  latlng: LatLngLiteral | null
  updateLocation: (location: string, latlng: LatLngLiteral) => void
  loading: boolean
  setLoading: React.Dispatch<React.SetStateAction<boolean>>,
  onError: (errorMsg: string) => void
}

function Location({
  location,
  latlng,
  updateLocation,
  loading = false,
  setLoading,
  onError
}: LocationProps) {
  const formatLatlng = (latlng?: LatLngLiteral | null) =>
    latlng ? `${latlng.lat.toFixed(6)}, ${latlng.lng.toFixed(6)}` : ''

  function setLocationToUser(location: string) {
    if (!location) return

    if ('geolocation' in navigator) {
      setLoading(true)
      console.debug('locating user...')
      navigator.geolocation.getCurrentPosition(
        position => {
          setLoading(false)
          const latlng = {
            lat: position.coords.latitude,
            lng: position.coords.longitude
          } as LatLngLiteral
          console.debug('got position', location, latlng)
          updateLocation(location, latlng)
        },
        error => {
          console.error(error)
          setLoading(false)
          onError('Could not get user location')
        })
    }
  }

  return (
    <div
      className='my-1 mx-2 p-1 flex flex-col w-full rounded-lg'
      key={location}
    >
      <div className='flex flex-col'>
        <div className='capitalize flex flex-row mb-1'>
          {location === 'start' ? (
            <span className='mdi mdi-map-marker text-2xl text-sky-700 start-marker'></span>
          ) : (
            <span className='mdi mdi-map-marker text-2xl text-sky-700 end-marker'></span>
          )}
          <span className='self-center ml-2'>{location}</span>
        </div>
        <input
          id='start-latlng'
          name='start-latlng'
          type='text'
          placeholder={`Pick ${location} location on map`}
          value={formatLatlng(latlng)}
          disabled
          className='block min-w-0 grow py-1.5 px-2 mb-1 rounded-sm bg-cyan-50'
        />
      </div>
      <div className='my-2'>
        <button
          className='py-1 px-1.5 border border-cyan-800 text-cyan-800 bg-cyan-50 disabled:text-cyan-800/20 rounded-sm enabled:hover:bg-cyan-700/20 transition'
          onClick={() => setLocationToUser(location)}
          disabled={loading}
        >
          <span className='mdi mdi-crosshairs-gps mr-2'></span>
          Use the current location
        </button>
      </div>
    </div>
  )
}

type TrackedRouteProps = {
  route?: Route | null,
  vehiclePositions?: VehiclePositionMessage | null
}

function TrackedRoute({ route, vehiclePositions }: TrackedRouteProps) {
  return (
    <div>
      {route ? (
        <div>
          <div className='flex justify-between'>
            <span> Following route: {route.route_name} </span>
            {vehiclePositions ? (
              <span className='font-bold'>
                {vehiclePositions?.freshness?.label}
              </span>
            ) : (
              <span>Waiting...</span>
            )}
          </div>
          {vehiclePositions ? (
            <div>
              There are {vehiclePositions.vehicle_count} vehicles on route.
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

type RoutePlanProps = {
  routePlans?: Route[]
  selected?: Route | null
  onSelect: (route: Route) => void
  onDeselect: (route?: Route) => void
}

/**
 * Show a list of route plans from point A to point B
 * @param {RoutePlanProps} props
 */
function RoutePlan({
  routePlans = [],
  selected,
  onSelect,
  onDeselect
}: RoutePlanProps) {
  function isSelected(route: Route) {
    return (
      selected &&
      `${route.route_id}${route.departure_time}${route.arrival_time}${route.duration_minutes}` ===
      `${selected.route_id}${selected.departure_time}${selected.arrival_time}${selected.duration_minutes}`
    )
  }

  const routes = routePlans
    .filter(r => r.route_id !== 'WALK')
    .map(r => {
      return (
        <div
          key={`${r.route_id}${r.departure_time}${r.arrival_time}${r.duration_minutes}`}
        >
          <div
            className={
              isSelected(r)
                ? 'p-2 rounded-sm bg-cyan-600/20 flex flex-row justify-between'
                : 'p-2 flex flex-row justify-between'
            }
          >
            <div>
              <div className='mr-2'>Route: {r.route_name} </div>
              <div className='mr-2 '>Duration: {r.duration_minutes} min</div>
            </div>
            <div>
              <div className='mr-2'>Departure: {r.departure_time} </div>
              <div className='mr-2'>Arrival: {r.arrival_time}</div>
            </div>
            <div>
              {isSelected(r) ? (
                <button
                  className='my-1 px-1.5 rounded-md bg-cyan-600 enabled:hover:bg-cyan-600/70 text-white'
                  onClick={() => onDeselect(r)}
                >
                  Untrack
                </button>
              ) : (
                <button
                  className='my-1 px-1.5 rounded-md bg-cyan-600 enabled:hover:bg-cyan-600/70 text-white'
                  onClick={() => onSelect(r)}
                >
                  Track
                </button>
              )}
            </div>
          </div>
          <div className='divider my-2 mx-1' />
        </div>
      )
    })

  return (
    <>
      <div className="overflow-y-auto">{routes}</div>
    </>
  )
}

export default App

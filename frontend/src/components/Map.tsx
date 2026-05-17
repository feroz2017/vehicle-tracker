import { useRef, useMemo } from 'react'
import {
  MapContainer,
  TileLayer,
  Marker,
  Popup,
  useMapEvents,
  LayerGroup,
  Polyline
} from 'react-leaflet'
import { type LatLngLiteral, type LatLngTuple } from 'leaflet'
import L from 'leaflet'
import { type VehiclePosition, type Route } from '../consumer/types'

// Default marker fix for React
import iconUrl from 'leaflet/dist/images/marker-icon.png'
import shadowUrl from 'leaflet/dist/images/marker-shadow.png'

const startIcon = new L.Icon({
  iconUrl,
  shadowUrl,
  className: 'start-marker',
  iconAnchor: [12, 41]
})
const endIcon = new L.Icon({
  iconUrl,
  shadowUrl,
  className: 'end-marker',
  iconAnchor: [12, 41]
})
const vehicleIcon = new L.Icon({
  iconUrl,
  shadowUrl,
  className: 'vehicle-marker',
  iconAnchor: [12, 41]
})

type MapProps = {
  start: LatLngLiteral | null
  end: LatLngLiteral | null
  onAddMarker: (latlng: LatLngLiteral) => void
  updateMarker: (location: string, latlng: LatLngLiteral) => void
  route?: Route | null
  vehicles: VehiclePosition[]
}

/**
 * Map functionality.
 * @param {MapProps} props
 */
export function Map({
  start,
  end,
  onAddMarker,
  updateMarker,
  route,
  vehicles
}: MapProps) {
  const defaultCenter = [62.2321, 25.7365] as LatLngTuple

  const polylineOptions: { [k: string]: L.PathOptions } = {
    WALK: { color: 'dimGray', dashArray: '5, 5' },
    BUS: { color: 'blue' }
  }

  // Show route legs on map
  const routePolylines = route?.legs ? (
    <LayerGroup>
      {route?.legs.map(r => (
        <Polyline
          pathOptions={polylineOptions[r.mode]}
          positions={r.geometry}
          key={`${r.route_id}${r.departure_time}${r.arrival_time}${r.duration_minutes}`}
        ></Polyline>
      ))}
    </LayerGroup>
  ) : null

  // Show tracked vehicle positions on map
  const vehiclePositions = vehicles
    ? vehicles.map(v => (
        <Marker icon={vehicleIcon} position={[v.lat, v.lon]} key={v.id}>
          <Popup>
            <span className='uppercase'>{v.label}</span>
            <br />
            <span className='uppercase'>{v.delay_label}</span>
            <br />
            Lat, lon: <br /> {v.lat.toFixed(6)}, {v.lon.toFixed(6)}
            <br />
            Speed: {v.speed_kmh} kmh
          </Popup>
        </Marker>
      ))
    : null

  return (
    <>
      <MapContainer
        center={defaultCenter}
        zoom={13}
        style={{ height: '100vh', width: '100%' }}
      >
        <ClickHandler onAddMarker={onAddMarker} />
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url='https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
        />
        {start ? (
          <DraggableMarker
            location={'start'}
            position={start}
            updateMarker={updateMarker}
          />
        ) : null}
        {end ? (
          <DraggableMarker
            location={'end'}
            position={end}
            updateMarker={updateMarker}
          />
        ) : null}
        {routePolylines}
        {vehiclePositions}
      </MapContainer>
    </>
  )
}

type ClickHandlerProps = {
  onAddMarker: (latlng: LatLngLiteral) => void
}

/**
 * Handle mouse click on Map.
 * @param {ClickHandlerProps} props
 */
function ClickHandler({ onAddMarker }: ClickHandlerProps) {
  useMapEvents({
    click: e => {
      // Add a new marker on click
      onAddMarker(e.latlng)
    }
  })
  return null
}

type DraggableMarkerProps = {
  location: string
  position: LatLngLiteral
  updateMarker: (location: string, latlng: LatLngLiteral) => void
}

/**
 * A draggable marker. Updates start/end coordinates.
 * @param {DraggableMarkerProps} props
 */
function DraggableMarker({
  location,
  position,
  updateMarker
}: DraggableMarkerProps) {
  const markerRef = useRef<L.Marker>(null)

  const eventHandlers = useMemo(
    () => ({
      dragend() {
        const markerInstance = markerRef.current

        if (markerInstance) {
          const position = markerInstance.getLatLng()

          console.debug(
            'new marker position:',
            location,
            position.lat,
            position.lng
          )
          updateMarker(location, position)
        }
      }
    }),
    [location, updateMarker]
  )
  const icon = location === 'start' ? startIcon : endIcon

  return (
    <Marker
      icon={icon}
      position={position}
      draggable={true}
      eventHandlers={eventHandlers}
      ref={markerRef}
    >
      <Popup>
        Lat: {position.lat.toFixed(5)}
        <br />
        Lng: {position.lng.toFixed(5)}
      </Popup>
    </Marker>
  )
}

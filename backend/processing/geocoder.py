from processing.models import Location


def parse_geocoding_response(raw: dict) -> list[Location]:
    """
    Convert Digitransit geocoding API response into Location objects.

    Digitransit returns a GeoJSON FeatureCollection. Each feature has:
        properties.label, properties.layer (venue|stop|address)
        geometry.coordinates → [lon, lat]  ← note: GeoJSON is lon-first
    """
    locations: list[Location] = []

    features = raw.get("features", [])
    for feature in features:
        props = feature.get("properties", {})
        coords = feature.get("geometry", {}).get("coordinates", [None, None])

        if not coords or coords[0] is None or coords[1] is None:
            continue

        locations.append(Location(
            name=props.get("label") or props.get("name", "Unknown"),
            lat=float(coords[1]),   # GeoJSON is [lon, lat]
            lon=float(coords[0]),
            type=props.get("layer", "place"),
            id=props.get("id"),
        ))

    return locations

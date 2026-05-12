from processing.models import ServiceAlert


def filter_by_route(alerts: list[ServiceAlert], route_id: str) -> list[ServiceAlert]:
    """
    Return only alerts that affect the given route_id.

    An alert with an empty route_ids list is treated as a network-wide alert
    and is always included.
    """
    return [
        a for a in alerts
        if not a.route_ids or route_id in a.route_ids
    ]

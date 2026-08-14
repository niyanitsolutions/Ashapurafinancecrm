"""Great-circle distance — stdlib only, no mapping SDK needed for a simple radius check.
`app/services/maps/client.py` is a geocoding stub (address -> lat/lng), not a distance
utility, so there's nothing to reuse there."""

import math

_EARTH_RADIUS_METERS = 6_371_000


def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * _EARTH_RADIUS_METERS * math.asin(math.sqrt(a))

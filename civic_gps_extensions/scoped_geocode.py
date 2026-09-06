"""One validated geocode per resolver call, isolated across threads and tasks."""
from __future__ import annotations

import copy
import math
from contextlib import contextmanager
from contextvars import ContextVar


def scoped_engine_class(engine_class, error_class):
    """Adapt the pinned engine without modifying its packed runtime bytes."""
    class ScopedEngine(engine_class):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._request_geocode = ContextVar("civic_gps_request_geocode", default=None)

        @contextmanager
        def geocode_scope(self):
            token = self._request_geocode.set({})
            try:
                yield
            finally:
                self._request_geocode.reset(token)

        def _get_json(self, url, params, source):
            body = super()._get_json(url, params, source)
            if source == "GEOCODER":
                result = body.get("result")
                matches = result.get("addressMatches") if isinstance(result, dict) else None
                if not isinstance(matches, list) or any(not isinstance(row, dict) for row in matches):
                    raise error_class("GEOCODER_MATCHES_INVALID", "Geocoder address matches must be a list of objects.")
                if len(matches) > 1:
                    raise error_class("AMBIGUOUS_ADDRESS", "Exactly one geocoder match is required.")
                # The core's existing ADDRESS_NOT_MATCHED handles the empty list.
                if matches:
                    geographies = matches[0].get("geographies", {})
                    if not isinstance(geographies, dict) or any(
                        not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows)
                        for rows in geographies.values()
                    ):
                        raise error_class("GEOCODER_GEOGRAPHIES_INVALID", "Geocoder geography collections must contain objects.")
                    coordinates = matches[0].get("coordinates")
                    if not isinstance(coordinates, dict) or any(type(coordinates.get(k)) not in (int, float) for k in ("x", "y")):
                        raise error_class("GEOCODER_COORDINATES_INVALID", "Finite numeric coordinates are required.")
                    lon, lat = coordinates["x"], coordinates["y"]
                    if not (math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90):
                        raise error_class("GEOCODER_COORDINATES_INVALID", "Coordinates are outside valid longitude/latitude bounds.")
            return body

        def _geocode(self, address):
            cache = self._request_geocode.get()
            if cache is not None and address in cache:
                return copy.deepcopy(cache[address])
            result = super()._geocode(address)
            if cache is not None:
                cache[address] = copy.deepcopy(result)
            return result

    return ScopedEngine

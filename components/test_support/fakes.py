from typing import Iterable, List, Optional

from components.data_collector.nps_client import normalize_alert, normalize_park


def raw_park(code: str, name: str, designation: str, states: str, activities: List[str]) -> dict:
    return {
        "id": f"id-{code}",
        "parkCode": code,
        "fullName": name,
        "name": name.split(" National")[0],
        "designation": designation,
        "states": states,
        "description": f"{name} description.",
        "url": f"https://www.nps.gov/{code}/index.htm",
        "latitude": "44.5",
        "longitude": "-110.5",
        "activities": [{"id": f"a-{a}", "name": a} for a in activities],
        "images": [{"url": f"https://www.nps.gov/{code}.jpg", "altText": f"{name} view"}],
        "weatherInfo": "Weather varies.",
    }


RAW_PARKS = [
    raw_park("yell", "Yellowstone National Park", "National Park", "ID,MT,WY",
             ["Camping", "Hiking", "Fishing", "Wildlife Watching"]),
    raw_park("grte", "Grand Teton National Park", "National Park", "WY",
             ["Camping", "Hiking", "Boating"]),
    raw_park("redw", "Redwood National and State Parks", "National and State Parks", "CA",
             ["Hiking", "Backcountry Camping"]),
    raw_park("stli", "Statue of Liberty National Monument", "National Monument", "NJ,NY",
             ["Guided Tours", "Museum Exhibits"]),
]

RAW_ALERTS = [
    {"parkCode": "yell", "title": "Road closed", "category": "Park Closure", "description": "", "url": ""},
    {"parkCode": "yell", "title": "Bison on trails", "category": "Caution", "description": "", "url": ""},
    {"parkCode": "stli", "title": "Ferry delays", "category": "Information", "description": "", "url": ""},
]

PARKS = [normalize_park(p) for p in RAW_PARKS]
ALERTS = [normalize_alert(a) for a in RAW_ALERTS]


class FakeNPSClient:
    def __init__(self, parks: Optional[List[dict]] = None, alerts: Optional[List[dict]] = None,
                 configured: bool = True, error: Optional[Exception] = None,
                 alerts_error: Optional[Exception] = None):
        self.parks = list(PARKS if parks is None else parks)
        self.alerts = list(ALERTS if alerts is None else alerts)
        self.configured = configured
        self.error = error
        self.alerts_error = alerts_error
        self.calls = []

    def _maybe_fail(self):
        if self.error:
            raise self.error

    def search_parks(self, query: str = "", state_code: str = "", park_code: str = "",
                     limit: int = 500) -> List[dict]:
        self.calls.append(("search_parks", query, state_code) + ((park_code,) if park_code else ()))
        self._maybe_fail()
        q = query.lower()
        return [
            p for p in self.parks
            if (not q or q in p["name"].lower() or q in p["description"].lower())
            and (not state_code or state_code in p["states"])
            and (not park_code or p["park_code"] == park_code)
        ][:limit]

    def get_park(self, park_code: str) -> Optional[dict]:
        self.calls.append(("get_park", park_code))
        self._maybe_fail()
        return next((p for p in self.parks if p["park_code"] == park_code), None)

    def get_alerts(self, park_codes: Iterable[str]) -> List[dict]:
        codes = set(park_codes)
        self.calls.append(("get_alerts", sorted(codes)))
        self._maybe_fail()
        if self.alerts_error:
            raise self.alerts_error
        return [a for a in self.alerts if a["park_code"] in codes]

    def call_names(self) -> List[str]:
        return [c[0] for c in self.calls]

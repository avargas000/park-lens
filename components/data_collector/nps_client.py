import os
import time
from typing import Iterable, List, Optional

import requests

from components.monitoring import monitoring

DEFAULT_BASE_URL = "https://developer.nps.gov/api/v1"
PAGE_SIZE = 100
MAX_PARKS = 500


class NPSError(Exception):
    pass


class NotConfigured(NPSError):
    pass


class RateLimited(NPSError):
    pass


class NPSClient:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None,
                 session: Optional[requests.Session] = None, timeout: float = 15):
        self.api_key = api_key if api_key is not None else os.environ.get("NPS_API_KEY")
        self.base_url = (base_url or os.environ.get("NPS_API_BASE", DEFAULT_BASE_URL)).rstrip("/")
        self.session = session or requests.Session()
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _get(self, endpoint: str, params: dict) -> dict:
        if not self.configured:
            raise NotConfigured("NPS API key is not configured on the server. Set NPS_API_KEY.")

        started = time.perf_counter()
        outcome = "error"
        try:
            resp = self.session.get(
                f"{self.base_url}/{endpoint}",
                params=params,
                headers={"X-Api-Key": self.api_key, "Accept": "application/json"},
                timeout=self.timeout,
            )
            if resp.status_code == 429:
                outcome = "rate_limited"
                raise RateLimited("NPS API rate limit reached. Please try again later.")
            if resp.status_code in (401, 403):
                outcome = "unauthorized"
                raise NPSError("The NPS API rejected the API key.")
            if resp.status_code != 200:
                raise NPSError(f"NPS API returned HTTP {resp.status_code}.")
            outcome = "success"
            return resp.json()
        except requests.RequestException as e:
            raise NPSError(f"Could not reach the NPS API: {e.__class__.__name__}.") from e
        finally:
            monitoring.record_nps_call(endpoint, outcome, time.perf_counter() - started)

    def _get_all(self, endpoint: str, params: dict, limit: int) -> List[dict]:
        results: List[dict] = []
        start = 0
        while len(results) < limit:
            page_size = min(PAGE_SIZE, limit - len(results))
            body = self._get(endpoint, {**params, "limit": page_size, "start": start})
            data = body.get("data") or []
            results.extend(data)
            total = int(body.get("total") or 0)
            start += len(data)
            if not data or start >= total:
                break
        return results

    def search_parks(self, query: str = "", state_code: str = "", park_code: str = "",
                     limit: int = MAX_PARKS) -> List[dict]:
        params = {}
        if query:
            params["q"] = query
        if state_code:
            params["stateCode"] = state_code
        if park_code:
            params["parkCode"] = park_code
        return [normalize_park(p) for p in self._get_all("parks", params, limit)]

    def get_park(self, park_code: str) -> Optional[dict]:
        body = self._get("parks", {"parkCode": park_code, "limit": 1})
        data = body.get("data") or []
        return normalize_park(data[0]) if data else None

    def get_alerts(self, park_codes: Iterable[str]) -> List[dict]:
        codes = sorted({c for c in park_codes if c})
        alerts: List[dict] = []
        for i in range(0, len(codes), 50):
            chunk = codes[i:i + 50]
            alerts.extend(normalize_alert(a) for a in self._get_all("alerts", {"parkCode": ",".join(chunk)}, 1000))
        return alerts


def normalize_park(raw: dict) -> dict:
    images = raw.get("images") or []
    return {
        "park_code": (raw.get("parkCode") or "").lower(),
        "name": raw.get("fullName") or raw.get("name") or "Unknown park",
        "designation": raw.get("designation") or "",
        "states": [s for s in (raw.get("states") or "").split(",") if s],
        "description": raw.get("description") or "",
        "url": raw.get("url") or "",
        "latitude": _to_float(raw.get("latitude")),
        "longitude": _to_float(raw.get("longitude")),
        "activities": sorted({a["name"] for a in raw.get("activities") or [] if a.get("name")}),
        "image_url": images[0].get("url") if images else None,
        "image_alt": images[0].get("altText") if images else None,
        "weather": raw.get("weatherInfo") or "",
    }


def normalize_alert(raw: dict) -> dict:
    return {
        "park_code": (raw.get("parkCode") or "").lower(),
        "title": raw.get("title") or "",
        "category": raw.get("category") or "Information",
        "description": raw.get("description") or "",
        "url": raw.get("url") or "",
    }


def _to_float(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

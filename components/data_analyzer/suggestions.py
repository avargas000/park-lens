import re
from typing import List

MIN_QUERY_LENGTH = 2


def _words(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _rank(name: str, query: str):
    lowered = name.lower()
    if lowered.startswith(query):
        return 0
    if any(word.startswith(query) for word in _words(name)):
        return 1
    if query in lowered:
        return 2
    return None


def suggest(parks: List[dict], query: str, limit: int = 8) -> List[dict]:
    query = " ".join(query.lower().split())
    if len(query) < MIN_QUERY_LENGTH:
        return []

    ranked = []
    for park in parks:
        rank = _rank(park["name"], query)
        if rank is not None:
            ranked.append((rank, park["name"], park))
    ranked.sort(key=lambda r: (r[0], r[1]))
    return [
        {
            "park_code": park["park_code"],
            "name": park["name"],
            "designation": park.get("designation", ""),
            "states": park.get("states", []),
        }
        for _, _, park in ranked[:limit]
    ]

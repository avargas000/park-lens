from collections import Counter
from typing import Iterable, List, Optional

ALERT_CATEGORIES = ("Danger", "Caution", "Park Closure", "Information")


def is_national_park(park: dict) -> bool:
    designation = park.get("designation", "").lower()
    return "national park" in designation or "national and state park" in designation


def offers(park: dict, keyword: str) -> bool:
    keyword = keyword.lower()
    return any(keyword in activity.lower() for activity in park.get("activities", []))


def percent(part: int, total: int) -> int:
    return round(100 * part / total) if total else 0


def analyze(parks: List[dict], alerts: Optional[Iterable[dict]] = None, top_n: int = 5) -> dict:
    alerts = list(alerts or [])
    total = len(parks)
    codes = {p["park_code"] for p in parks}
    alerted_codes = {a["park_code"] for a in alerts if a["park_code"] in codes}

    camping = sum(1 for p in parks if offers(p, "camping"))
    hiking = sum(1 for p in parks if offers(p, "hiking"))

    activity_counts = Counter(a for p in parks for a in p.get("activities", []))
    state_counts = Counter(s for p in parks for s in p.get("states", []))
    alert_categories = Counter(a["category"] for a in alerts if a["park_code"] in codes)

    most_common = activity_counts.most_common(1)
    return {
        "total_parks": total,
        "camping_count": camping,
        "camping_percent": percent(camping, total),
        "hiking_count": hiking,
        "hiking_percent": percent(hiking, total),
        "alerts_count": len(alerted_codes),
        "alerts_percent": percent(len(alerted_codes), total),
        "total_alerts": sum(alert_categories.values()),
        "most_common_activity": most_common[0][0] if most_common else None,
        "top_activities": [
            {"name": name, "count": n, "percent": percent(n, total)}
            for name, n in activity_counts.most_common(top_n)
        ],
        "top_states": [{"state": s, "count": n} for s, n in state_counts.most_common(top_n)],
        "alert_categories": [
            {"category": c, "count": alert_categories[c]}
            for c in sorted(alert_categories, key=lambda c: -alert_categories[c])
        ],
        "average_activities": round(sum(activity_counts.values()) / total, 1) if total else 0,
    }


def summary_lines(analysis: dict) -> List[str]:
    if not analysis["total_parks"]:
        return ["No parks found."]
    n = analysis["total_parks"]
    lines = [
        f"{n} park{'s' if n != 1 else ''} found",
        f"{analysis['camping_percent']}% offer camping",
        f"{analysis['hiking_percent']}% offer hiking",
        f"{analysis['alerts_percent']}% have current alerts",
    ]
    if analysis["most_common_activity"]:
        lines.append(f"Most common activity: {analysis['most_common_activity'].lower()}")
    return lines

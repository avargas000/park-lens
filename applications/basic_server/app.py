#!/usr/bin/env python3

import re
import time
from typing import Optional

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

load_dotenv()

from components.monitoring import monitoring  # noqa: E402
from components.data_analyzer.analyzer import analyze, is_national_park, summary_lines  # noqa: E402
from components.data_collector.nps_client import NotConfigured, NPSClient, NPSError, RateLimited  # noqa: E402
from components.storage.park_store import ParkStore, default_database_path  # noqa: E402
from components.data_analyzer.suggestions import suggest  # noqa: E402

CACHE_TTL_SECONDS = 600
CATALOG_TTL_SECONDS = 24 * 60 * 60
MAX_QUERY_LENGTH = 100
MAX_NOTE_LENGTH = 500
PARK_CODE_RE = re.compile(r"^[a-z]{4,10}$")

STATES = {
    "AL": "Alabama", "AK": "Alaska", "AS": "American Samoa", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia",
    "FL": "Florida", "GA": "Georgia", "GU": "Guam", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine",
    "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire",
    "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota",
    "MP": "Northern Mariana Islands", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "PR": "Puerto Rico", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee",
    "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VI": "U.S. Virgin Islands", "VA": "Virginia",
    "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}


def _truthy(value: Optional[str]) -> bool:
    return (value or "").lower() in ("1", "true", "yes", "on")


def create_app(client: Optional[NPSClient] = None, store: Optional[ParkStore] = None,
               config: Optional[dict] = None) -> Flask:
    app = Flask(__name__)
    app.config.update(config or {})

    client = client or NPSClient()
    store = store or ParkStore(default_database_path())
    app.extensions["nps_client"] = client
    app.extensions["park_store"] = store
    search_cache = {}
    catalog = {"loaded_at": 0.0, "parks": []}

    monitoring.init_app(app)
    monitoring.FAVORITES.set(store.counts()["favorites"])

    def api_error(message: str, status: int):
        return jsonify(error=message), status

    def nps_error_response(e: Exception):
        if isinstance(e, NotConfigured):
            return api_error(str(e), 503)
        if isinstance(e, RateLimited):
            return api_error(str(e), 429)
        app.logger.warning("NPS API error: %s", e)
        return api_error("Could not reach the National Park Service right now. Please try again later.", 502)

    def park_catalog() -> list:
        if catalog["parks"] and time.time() - catalog["loaded_at"] < CATALOG_TTL_SECONDS:
            return catalog["parks"]
        try:
            parks = client.search_parks()
        except NPSError as e:
            app.logger.warning("Park catalog unavailable, using stored parks: %s", e)
            return catalog["parks"] or store.all_parks()
        store.upsert_parks(parks)
        catalog.update(loaded_at=time.time(), parks=parks)
        return parks

    def fetch_parks(query: str, state_code: str, park_code: str = ""):
        key = (query.lower(), state_code, park_code)
        cached = search_cache.get(key)
        if cached and time.time() - cached[0] < CACHE_TTL_SECONDS:
            return cached[1], cached[2], cached[3]

        parks = client.search_parks(query=query, state_code=state_code, park_code=park_code)
        store.upsert_parks(parks)
        alerts_available = True
        try:
            alerts = client.get_alerts(p["park_code"] for p in parks) if parks else []
        except NPSError as e:
            app.logger.warning("Alerts unavailable: %s", e)
            alerts, alerts_available = [], False
        search_cache[key] = (time.time(), parks, alerts, alerts_available)
        return parks, alerts, alerts_available

    def find_park(park_code: str) -> Optional[dict]:
        return store.get_park(park_code) or client.get_park(park_code)

    @app.route("/")
    def main():
        return render_template(
            "index.html",
            configured=client.configured,
            states=STATES,
            favorites=store.list_favorites(),
        )

    @app.route("/report")
    def report():
        return render_template("report.html", report=build_report(), states=STATES)

    @app.route("/health")
    def health():
        try:
            store.ping()
            db_ok = True
        except Exception:
            app.logger.exception("Database health check failed")
            db_ok = False
        status = 200 if db_ok else 503
        return jsonify(status="ok" if db_ok else "degraded", database=db_ok,
                       nps_api_configured=client.configured), status

    @app.route("/api/parks")
    def search_parks():
        query = (request.args.get("q") or "").strip()
        state_code = (request.args.get("state") or "").strip().upper()
        national_only = _truthy(request.args.get("national_only"))
        park_code = (request.args.get("code") or "").strip().lower()

        if len(query) > MAX_QUERY_LENGTH:
            return api_error(f"Search terms must be {MAX_QUERY_LENGTH} characters or fewer.", 400)
        if state_code and state_code not in STATES:
            return api_error("Choose a valid U.S. state or territory.", 400)
        if park_code and not PARK_CODE_RE.match(park_code):
            return api_error("Park codes are 4-10 letters, e.g. 'yell'.", 400)
        if not query and not state_code and not national_only and not park_code:
            return api_error("Enter a park name or keyword, choose a state, or tick 'National Parks only'.", 400)

        try:
            parks, alerts, alerts_available = fetch_parks(query, state_code, park_code)
        except NPSError as e:
            return nps_error_response(e)

        if national_only:
            parks = [p for p in parks if is_national_park(p)]

        analysis = analyze(parks, alerts)
        store.record_search(query, state_code, national_only, analysis)
        monitoring.SEARCHES.inc()

        alerts_by_park = {}
        for alert in alerts:
            alerts_by_park.setdefault(alert["park_code"], []).append(alert)
        favorites = store.favorite_codes()
        results = [
            {**park, "alerts": alerts_by_park.get(park["park_code"], []), "favorite": park["park_code"] in favorites}
            for park in parks
        ]
        return jsonify(
            query=query,
            state=state_code or None,
            national_only=national_only,
            alerts_available=alerts_available,
            analysis=analysis,
            summary=summary_lines(analysis),
            parks=results,
        )

    @app.route("/api/parks/suggest")
    def suggest_parks():
        query = (request.args.get("q") or "").strip()[:MAX_QUERY_LENGTH]
        if len(query) < 2:
            return jsonify(query=query, suggestions=[])
        return jsonify(query=query, suggestions=suggest(park_catalog(), query))

    @app.route("/api/parks/<park_code>")
    def park_detail(park_code):
        park_code = park_code.lower()
        if not PARK_CODE_RE.match(park_code):
            return api_error("Park codes are 4-10 letters, e.g. 'yell'.", 400)
        try:
            park = find_park(park_code)
            if not park:
                return api_error(f"No park found with code '{park_code}'.", 404)
            alerts = client.get_alerts([park_code])
        except NPSError as e:
            return nps_error_response(e)
        return jsonify(park={**park, "alerts": alerts, "favorite": park_code in store.favorite_codes()})

    @app.route("/api/favorites", methods=["GET"])
    def list_favorites():
        return jsonify(favorites=store.list_favorites())

    @app.route("/api/favorites", methods=["POST"])
    def add_favorite():
        body = request.get_json(silent=True) or {}
        park_code = str(body.get("park_code") or "").strip().lower()
        note = str(body.get("note") or "").strip()
        if not PARK_CODE_RE.match(park_code):
            return api_error("Send a JSON body with a valid 'park_code', e.g. {\"park_code\": \"yell\"}.", 400)
        if len(note) > MAX_NOTE_LENGTH:
            return api_error(f"Notes must be {MAX_NOTE_LENGTH} characters or fewer.", 400)
        try:
            park = find_park(park_code)
        except NPSError as e:
            return nps_error_response(e)
        if not park:
            return api_error(f"No park found with code '{park_code}'.", 404)

        store.add_favorite(park, note)
        monitoring.FAVORITES.set(store.counts()["favorites"])
        return jsonify(favorite={**park, "note": note or None}), 201

    @app.route("/api/favorites/<park_code>", methods=["DELETE"])
    def remove_favorite(park_code):
        if not store.remove_favorite(park_code.lower()):
            return api_error(f"'{park_code}' is not in your favorites.", 404)
        monitoring.FAVORITES.set(store.counts()["favorites"])
        return "", 204

    @app.route("/api/report")
    def report_api():
        return jsonify(build_report())

    def build_report() -> dict:
        stored_parks = store.all_parks()
        favorites = store.list_favorites()
        return {
            "counts": store.counts(),
            "stored_parks_analysis": analyze(stored_parks),
            "favorites_analysis": analyze(favorites),
            "recent_searches": store.recent_searches(10),
            "top_queries": store.top_queries(5),
            "favorites": favorites,
            "latest_collection": store.latest_collection(),
            "snapshots": store.latest_analyses(),
        }

    return app

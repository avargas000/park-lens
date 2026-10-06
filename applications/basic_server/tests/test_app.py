from unittest import mock

import pytest

from applications.basic_server.app import create_app
from components.data_collector.nps_client import NotConfigured, NPSError, RateLimited
from components.test_support.fakes import FakeNPSClient

pytestmark = pytest.mark.integration


def test_home_page_renders_search_form(client):
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'id="search-form"' in html
    assert "Wyoming" in html
    assert "NPS API key isn't configured" not in html


def test_home_page_warns_when_api_key_missing(store):
    app = create_app(client=FakeNPSClient(configured=False), store=store)
    html = app.test_client().get("/").get_data(as_text=True)
    assert "NPS_API_KEY" in html


def test_search_returns_parks_analysis_and_persists(client, store, fake_nps):
    resp = client.get("/api/parks?q=yellowstone")
    assert resp.status_code == 200
    data = resp.get_json()

    assert [p["park_code"] for p in data["parks"]] == ["yell"]
    assert data["summary"][0] == "1 park found"
    assert data["analysis"]["alerts_percent"] == 100
    assert len(data["parks"][0]["alerts"]) == 2
    assert data["parks"][0]["favorite"] is False

    assert store.get_park("yell")["name"] == "Yellowstone National Park"
    assert store.recent_searches()[0]["query"] == "yellowstone"
    assert fake_nps.call_names() == ["search_parks", "get_alerts"]


def test_national_only_filters_designations(client):
    data = client.get("/api/parks?national_only=1").get_json()
    assert sorted(p["park_code"] for p in data["parks"]) == ["grte", "redw", "yell"]
    assert data["analysis"]["camping_percent"] == 100
    assert data["analysis"]["hiking_percent"] == 100


def test_state_filter_is_passed_to_nps(client, fake_nps):
    data = client.get("/api/parks?state=wy").get_json()
    assert data["state"] == "WY"
    assert ("search_parks", "", "WY") in fake_nps.calls


def test_repeat_searches_are_served_from_cache(client, fake_nps):
    client.get("/api/parks?q=Grand")
    client.get("/api/parks?q=grand")
    assert fake_nps.call_names().count("search_parks") == 1


@pytest.mark.parametrize("query, message", [
    ("", "Enter a park name"),
    ("?state=ZZ", "valid U.S. state"),
    ("?q=" + "x" * 101, "100 characters"),
])
def test_search_validation(client, query, message):
    resp = client.get(f"/api/parks{query}")
    assert resp.status_code == 400
    assert message in resp.get_json()["error"]


@pytest.mark.parametrize("error, status", [
    (NotConfigured("no key"), 503),
    (RateLimited("slow down"), 429),
    (NPSError("down"), 502),
])
def test_nps_failures_map_to_http_errors(store, error, status):
    app = create_app(client=FakeNPSClient(error=error), store=store)
    resp = app.test_client().get("/api/parks?q=yellowstone")
    assert resp.status_code == status
    assert "error" in resp.get_json()
    assert store.counts()["searches"] == 0


def test_search_still_works_when_alerts_fail(store):
    app = create_app(client=FakeNPSClient(alerts_error=NPSError("alerts down")), store=store)
    data = app.test_client().get("/api/parks?q=yellowstone").get_json()
    assert data["alerts_available"] is False
    assert data["analysis"]["alerts_percent"] == 0
    assert len(data["parks"]) == 1


def test_search_records_analysis_via_store(app, client, store):
    with mock.patch.object(store, "record_search", wraps=store.record_search) as spy:
        client.get("/api/parks?q=teton&state=WY")

    spy.assert_called_once()
    query, state, national_only, analysis = spy.call_args.args
    assert (query, state, national_only) == ("teton", "WY", False)
    assert analysis["total_parks"] == 1
    assert store.counts()["searches"] == 1


def test_suggest_returns_matching_park_names(client, store):
    data = client.get("/api/parks/suggest?q=grand").get_json()
    assert data["suggestions"] == [{
        "park_code": "grte", "name": "Grand Teton National Park", "designation": "National Park", "states": ["WY"],
    }]
    assert store.counts()["parks"] == 4


def test_suggest_loads_catalog_once(client, fake_nps):
    client.get("/api/parks/suggest?q=gr")
    client.get("/api/parks/suggest?q=gra")
    client.get("/api/parks/suggest?q=yell")
    assert fake_nps.call_names() == ["search_parks"]


def test_suggest_ignores_short_queries(client, fake_nps):
    assert client.get("/api/parks/suggest?q=g").get_json()["suggestions"] == []
    assert fake_nps.calls == []


def test_suggest_falls_back_to_stored_parks_when_nps_is_down(store):
    from components.test_support.fakes import PARKS

    store.upsert_parks(PARKS[:1])
    app = create_app(client=FakeNPSClient(error=NPSError("down")), store=store)
    data = app.test_client().get("/api/parks/suggest?q=yellow").get_json()
    assert [s["park_code"] for s in data["suggestions"]] == ["yell"]


def test_search_by_code_returns_exact_park(client, fake_nps):
    data = client.get("/api/parks?code=GRTE").get_json()
    assert [p["park_code"] for p in data["parks"]] == ["grte"]
    assert ("search_parks", "", "", "grte") in fake_nps.calls


def test_search_rejects_bad_code(client):
    assert client.get("/api/parks?code=12").status_code == 400


def test_park_detail(client, fake_nps):
    data = client.get("/api/parks/YELL").get_json()
    assert data["park"]["name"] == "Yellowstone National Park"
    assert len(data["park"]["alerts"]) == 2
    assert ("get_park", "yell") in fake_nps.calls


def test_park_detail_prefers_stored_copy(client, fake_nps):
    client.get("/api/parks?q=yellowstone")
    fake_nps.calls.clear()
    client.get("/api/parks/yell")
    assert "get_park" not in fake_nps.call_names()


def test_park_detail_errors(client):
    assert client.get("/api/parks/x1").status_code == 400
    assert client.get("/api/parks/nope").status_code == 404


def test_favorites_crud(client, store):
    assert client.get("/api/favorites").get_json() == {"favorites": []}

    resp = client.post("/api/favorites", json={"park_code": "yell", "note": "See Old Faithful"})
    assert resp.status_code == 201
    assert resp.get_json()["favorite"]["note"] == "See Old Faithful"

    favorites = client.get("/api/favorites").get_json()["favorites"]
    assert [f["park_code"] for f in favorites] == ["yell"]

    search = client.get("/api/parks?q=yellowstone").get_json()
    assert search["parks"][0]["favorite"] is True

    assert client.delete("/api/favorites/yell").status_code == 204
    assert client.delete("/api/favorites/yell").status_code == 404
    assert store.favorite_codes() == set()


@pytest.mark.parametrize("body, status", [
    ({}, 400),
    ({"park_code": "!!"}, 400),
    ({"park_code": "yell", "note": "x" * 501}, 400),
    ({"park_code": "zzzz"}, 404),
])
def test_add_favorite_validation(client, body, status):
    assert client.post("/api/favorites", json=body).status_code == status


def test_report_api_and_page_reflect_collected_data(client):
    client.get("/api/parks?q=yellowstone")
    client.get("/api/parks?national_only=1")
    client.post("/api/favorites", json={"park_code": "grte"})

    report = client.get("/api/report").get_json()
    assert report["counts"] == {"parks": 4, "searches": 2, "favorites": 1}
    assert report["stored_parks_analysis"]["total_parks"] == 4
    assert report["favorites_analysis"]["most_common_activity"] in {"Boating", "Camping", "Hiking"}
    assert report["top_queries"] == [{"query": "yellowstone", "count": 1}]

    html = client.get("/report").get_data(as_text=True)
    assert "Recent searches" in html
    assert "yellowstone" in html.lower()
    assert "parks stored" in html


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok", "database": True, "nps_api_configured": True}


def test_health_reports_database_failure(app, client, store):
    with mock.patch.object(store, "ping", side_effect=Exception("disk gone")):
        resp = client.get("/health")
    assert resp.status_code == 503
    assert resp.get_json()["status"] == "degraded"


def test_metrics_endpoint_exposes_instrumentation(client):
    client.get("/api/parks?q=yellowstone")
    client.post("/api/favorites", json={"park_code": "yell"})

    body = client.get("/metrics").get_data(as_text=True)
    assert 'parklens_http_requests_total{endpoint="/api/parks",method="GET",status="200"}' in body
    assert "parklens_searches_total" in body
    assert "parklens_favorites 1.0" in body


def test_responses_carry_request_id(client):
    assert client.get("/health", headers={"X-Request-ID": "abc123"}).headers["X-Request-ID"] == "abc123"
    assert client.get("/health").headers["X-Request-ID"]

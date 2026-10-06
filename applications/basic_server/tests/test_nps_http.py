from unittest import mock

import pytest
import requests

from applications.basic_server.app import create_app
from components.data_collector.nps_client import NPSClient
from components.test_support.fakes import RAW_ALERTS, RAW_PARKS

pytestmark = pytest.mark.integration


def fake_nps_http(url, params=None, headers=None, timeout=None):
    resp = mock.Mock(spec=requests.Response)
    if headers.get("X-Api-Key") != "secret":
        resp.status_code = 403
        return resp
    resp.status_code = 200
    if url.endswith("/parks"):
        q = (params.get("q") or "").lower()
        data = [p for p in RAW_PARKS if q in p["fullName"].lower()]
        if "parkCode" in params:
            data = [p for p in RAW_PARKS if p["parkCode"] == params["parkCode"]]
    elif url.endswith("/alerts"):
        codes = params["parkCode"].split(",")
        data = [a for a in RAW_ALERTS if a["parkCode"] in codes]
    else:
        resp.status_code = 404
        return resp
    start, limit = params.get("start", 0), params.get("limit", 50)
    resp.json.return_value = {"total": str(len(data)), "data": data[start:start + limit]}
    return resp


@pytest.fixture
def http_session():
    session = mock.Mock(spec=requests.Session)
    session.get.side_effect = fake_nps_http
    return session


def test_search_flows_from_http_to_database_to_analysis(http_session, store):
    nps = NPSClient(api_key="secret", base_url="https://nps.test/api/v1", session=http_session)
    client = create_app(client=nps, store=store).test_client()

    data = client.get("/api/parks?q=national").get_json()

    assert data["analysis"]["total_parks"] == 4
    assert data["summary"] == [
        "4 parks found",
        "75% offer camping",
        "75% offer hiking",
        "50% have current alerts",
        "Most common activity: hiking",
    ]
    assert store.counts() == {"parks": 4, "searches": 1, "favorites": 0}
    urls = [c.args[0] for c in http_session.get.call_args_list]
    assert urls == ["https://nps.test/api/v1/parks", "https://nps.test/api/v1/alerts"]


def test_favorite_fetches_park_from_api_when_not_stored(http_session, store):
    nps = NPSClient(api_key="secret", base_url="https://nps.test/api/v1", session=http_session)
    client = create_app(client=nps, store=store).test_client()

    assert client.post("/api/favorites", json={"park_code": "redw"}).status_code == 201
    assert store.get_park("redw")["designation"] == "National and State Parks"


def test_rejected_api_key_surfaces_as_bad_gateway(http_session, store):
    nps = NPSClient(api_key="wrong", base_url="https://nps.test/api/v1", session=http_session)
    resp = create_app(client=nps, store=store).test_client().get("/api/parks?q=yellowstone")
    assert resp.status_code == 502

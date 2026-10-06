from unittest import mock

import pytest
import requests

from components.data_collector.nps_client import NotConfigured, NPSClient, NPSError, RateLimited, normalize_park
from components.test_support.fakes import RAW_ALERTS, RAW_PARKS


def response(status=200, body=None):
    resp = mock.Mock(spec=requests.Response)
    resp.status_code = status
    resp.json.return_value = body if body is not None else {}
    return resp


def make_client(*responses):
    session = mock.Mock(spec=requests.Session)
    session.get.side_effect = list(responses)
    return NPSClient(api_key="test-key", base_url="https://nps.test/api/v1", session=session), session


def test_search_sends_api_key_header_and_query_params():
    client, session = make_client(response(body={"total": "1", "data": RAW_PARKS[:1]}))

    parks = client.search_parks(query="Yellowstone", state_code="WY")

    assert [p["park_code"] for p in parks] == ["yell"]
    session.get.assert_called_once()
    url = session.get.call_args.args[0]
    kwargs = session.get.call_args.kwargs
    assert url == "https://nps.test/api/v1/parks"
    assert kwargs["headers"]["X-Api-Key"] == "test-key"
    assert kwargs["params"] == {"q": "Yellowstone", "stateCode": "WY", "limit": 100, "start": 0}


def test_search_follows_pagination_until_total_reached():
    client, session = make_client(
        response(body={"total": "4", "data": RAW_PARKS[:2]}),
        response(body={"total": "4", "data": RAW_PARKS[2:]}),
    )

    parks = client.search_parks()

    assert len(parks) == 4
    starts = [c.kwargs["params"]["start"] for c in session.get.call_args_list]
    assert starts == [0, 2]


def test_get_alerts_joins_park_codes_and_dedupes():
    client, session = make_client(response(body={"total": "3", "data": RAW_ALERTS}))

    alerts = client.get_alerts(["yell", "stli", "yell", ""])

    assert len(alerts) == 3
    assert session.get.call_args.kwargs["params"]["parkCode"] == "stli,yell"
    assert alerts[0] == {
        "park_code": "yell", "title": "Road closed", "category": "Park Closure", "description": "", "url": "",
    }


def test_get_park_returns_none_when_missing():
    client, _ = make_client(response(body={"total": "0", "data": []}))
    assert client.get_park("nope") is None


@pytest.mark.parametrize("status, error", [(429, RateLimited), (403, NPSError), (500, NPSError)])
def test_http_errors_map_to_exceptions(status, error):
    client, _ = make_client(response(status=status))
    with pytest.raises(error):
        client.search_parks(query="x")


def test_network_failure_is_wrapped():
    client, session = make_client()
    session.get.side_effect = requests.ConnectionError("boom")
    with pytest.raises(NPSError, match="ConnectionError"):
        client.search_parks(query="x")


def test_missing_api_key_raises_without_calling_network():
    session = mock.Mock(spec=requests.Session)
    client = NPSClient(api_key="", session=session)
    assert not client.configured
    with pytest.raises(NotConfigured):
        client.search_parks(query="x")
    session.get.assert_not_called()


def test_every_call_is_reported_to_monitoring():
    client, _ = make_client(response(body={"total": "1", "data": RAW_PARKS[:1]}), response(status=500))
    with mock.patch("components.data_collector.nps_client.monitoring.record_nps_call") as spy:
        client.search_parks(query="a")
        with pytest.raises(NPSError):
            client.search_parks(query="b")

    outcomes = [c.args[:2] for c in spy.call_args_list]
    assert outcomes == [("parks", "success"), ("parks", "error")]
    assert all(c.args[2] >= 0 for c in spy.call_args_list)


def test_normalize_park_handles_missing_fields():
    park = normalize_park({"parkCode": "ABCD", "latitude": "", "activities": [{"name": "Hiking"}, {"name": "Hiking"}]})
    assert park["park_code"] == "abcd"
    assert park["name"] == "Unknown park"
    assert park["states"] == []
    assert park["latitude"] is None
    assert park["activities"] == ["Hiking"]
    assert park["image_url"] is None

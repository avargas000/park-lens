import pytest

from applications.basic_server.app import create_app as create_basic_server
from applications.data_analyzer_server.app import create_app as create_analyzer_server
from applications.data_collector_server.app import create_app as create_collector_server
from components.test_support.fakes import FakeNPSClient

pytestmark = pytest.mark.integration


def test_background_collection_and_analysis_show_up_in_the_report(store):
    nps = FakeNPSClient()
    collector = create_collector_server(client=nps, store=store, start_scheduler=False)
    analyzer = create_analyzer_server(store=store, start_scheduler=False)
    web = create_basic_server(client=nps, store=store).test_client()

    assert "background analysis" not in web.get("/report").get_data(as_text=True)

    collector.extensions["work_scheduler"].run_once()
    analyzer.extensions["work_scheduler"].run_once()

    report = web.get("/api/report").get_json()
    national = report["snapshots"]["national-parks"]["analysis"]
    assert national["total_parks"] == 3
    assert national["alerts_percent"] == 33
    assert report["latest_collection"]["parks_count"] == 4

    html = web.get("/report").get_data(as_text=True)
    assert "National Parks · background analysis" in html
    assert "33% have current alerts" in html

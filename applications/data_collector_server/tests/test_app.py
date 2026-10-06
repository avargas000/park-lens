import pytest

from applications.data_collector_server.app import create_app
from components.data_collector.nps_client import NPSError
from components.test_support.fakes import FakeNPSClient

pytestmark = pytest.mark.integration


def test_scheduler_cycle_collects_into_storage_and_reports_health(store):
    app = create_app(client=FakeNPSClient(), store=store, start_scheduler=False)
    client = app.test_client()

    before = client.get("/health").get_json()
    assert before["service"] == "data-collector-server"
    assert before["latest_collection"] is None
    assert before["scheduler_running"] is False

    assert app.extensions["work_scheduler"].run_once() == 1
    assert app.extensions["work_scheduler"].run_once() == 0

    after = client.get("/health").get_json()
    assert after["latest_collection"]["parks_count"] == 4
    assert after["latest_collection"]["alerts_count"] == 3


def test_failed_collection_is_counted_in_metrics(store):
    app = create_app(client=FakeNPSClient(error=NPSError("down")), store=store, start_scheduler=False)

    assert app.extensions["work_scheduler"].run_once() == 0

    metrics = app.test_client().get("/metrics").get_data(as_text=True)
    assert 'parklens_worker_runs_total{outcome="error",worker="data-collector"}' in metrics
    assert store.latest_collection() is None


def test_scheduler_starts_with_the_app(store):
    app = create_app(client=FakeNPSClient(), store=store)
    try:
        assert app.extensions["work_scheduler"].running
    finally:
        app.extensions["work_scheduler"].stop()

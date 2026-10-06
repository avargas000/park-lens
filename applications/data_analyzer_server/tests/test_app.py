import pytest

from applications.data_analyzer_server.app import create_app
from components.test_support.fakes import ALERTS, PARKS

pytestmark = pytest.mark.integration


def test_scheduler_cycle_analyzes_new_collections(store):
    app = create_app(store=store, start_scheduler=False)
    scheduler = app.extensions["work_scheduler"]
    client = app.test_client()

    assert scheduler.run_once() == 0
    assert client.get("/health").get_json()["latest_analyses"] == {}

    collection_id = store.record_collection(PARKS, ALERTS)
    assert scheduler.run_once() == 2
    assert scheduler.run_once() == 0

    health = client.get("/health").get_json()
    assert health["service"] == "data-analyzer-server"
    assert set(health["latest_analyses"]) == {"all-parks", "national-parks"}
    assert health["latest_analyses"]["national-parks"]["collection_id"] == collection_id

    metrics = client.get("/metrics").get_data(as_text=True)
    assert 'parklens_worker_runs_total{outcome="success",worker="data-analyzer"}' in metrics

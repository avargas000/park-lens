from datetime import datetime, timedelta

import pytest

from components.data_collector.collector_workflow import CollectorTask, CollectorWorker, CollectorWorkFinder
from components.data_collector.nps_client import NPSError
from components.test_support.fakes import ALERTS, PARKS, FakeNPSClient


def test_finder_requests_work_when_nothing_collected(store):
    assert CollectorWorkFinder(store, timedelta(hours=1)).find_requested("data-collector") == [CollectorTask()]


def test_finder_waits_until_collection_is_stale(store):
    store.record_collection(PARKS, ALERTS)
    collected_at = datetime.fromisoformat(store.latest_collection()["collected_at"])

    fresh = CollectorWorkFinder(store, timedelta(hours=1), now=lambda: collected_at + timedelta(minutes=59))
    stale = CollectorWorkFinder(store, timedelta(hours=1), now=lambda: collected_at + timedelta(minutes=61))

    assert fresh.find_requested("data-collector") == []
    assert stale.find_requested("data-collector") == [CollectorTask()]


def test_worker_collects_all_parks_and_their_alerts(store):
    nps = FakeNPSClient()

    CollectorWorker(nps, store).execute(CollectorTask())

    assert nps.calls[0] == ("search_parks", "", "")
    assert nps.calls[1] == ("get_alerts", ["grte", "redw", "stli", "yell"])
    assert store.counts()["parks"] == 4
    assert len(store.all_alerts()) == 3
    assert store.latest_collection()["parks_count"] == 4


def test_worker_propagates_nps_failures_without_recording(store):
    with pytest.raises(NPSError):
        CollectorWorker(FakeNPSClient(error=NPSError("down")), store).execute(CollectorTask())
    assert store.latest_collection() is None

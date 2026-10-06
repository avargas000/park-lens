from components.data_analyzer.analyzer_workflow import AnalyzerTask, AnalyzerWorker, AnalyzerWorkFinder
from components.test_support.fakes import ALERTS, PARKS


def test_finder_has_no_work_before_first_collection(store):
    assert AnalyzerWorkFinder(store).find_requested("data-analyzer") == []


def test_finder_requests_each_scope_once_per_collection(store):
    collection_id = store.record_collection(PARKS, ALERTS)
    finder = AnalyzerWorkFinder(store)

    tasks = finder.find_requested("data-analyzer")
    assert tasks == [AnalyzerTask("all-parks", collection_id), AnalyzerTask("national-parks", collection_id)]

    worker = AnalyzerWorker(store)
    for task in tasks:
        worker.execute(task)
    assert finder.find_requested("data-analyzer") == []

    newer_id = store.record_collection(PARKS, ALERTS)
    assert {t.collection_id for t in finder.find_requested("data-analyzer")} == {newer_id}


def test_worker_saves_scoped_analysis(store):
    collection_id = store.record_collection(PARKS, ALERTS)

    AnalyzerWorker(store).execute(AnalyzerTask("national-parks", collection_id))
    AnalyzerWorker(store).execute(AnalyzerTask("all-parks", collection_id))

    snapshots = store.latest_analyses()
    national = snapshots["national-parks"]["analysis"]
    assert national["total_parks"] == 3
    assert national["camping_percent"] == 100
    assert national["alerts_percent"] == 33
    assert snapshots["all-parks"]["analysis"]["total_parks"] == 4
    assert snapshots["all-parks"]["collection_id"] == collection_id

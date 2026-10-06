import threading
from unittest import mock

from components.workflow_support.workflow import WorkScheduler


class FakeFinder:
    def __init__(self, tasks):
        self.tasks = tasks
        self.requested = []
        self.completed = []

    def find_requested(self, name):
        self.requested.append(name)
        return list(self.tasks.get(name, []))

    def mark_completed(self, task):
        self.completed.append(task)


class SpyWorker:
    def __init__(self, name, fail_on=()):
        self.name = name
        self.fail_on = set(fail_on)
        self.executed = []

    def execute(self, task):
        self.executed.append(task)
        if task in self.fail_on:
            raise RuntimeError(f"cannot do {task}")


def test_run_once_routes_tasks_to_workers_by_name():
    finder = FakeFinder({"collector": ["a", "b"], "analyzer": ["c"]})
    collector, analyzer = SpyWorker("collector"), SpyWorker("analyzer")

    completed = WorkScheduler(finder, [collector, analyzer], interval_seconds=1).run_once()

    assert completed == 3
    assert finder.requested == ["collector", "analyzer"]
    assert collector.executed == ["a", "b"]
    assert analyzer.executed == ["c"]
    assert finder.completed == ["a", "b", "c"]


def test_failed_tasks_are_not_marked_completed_and_do_not_stop_others():
    finder = FakeFinder({"w": ["ok-1", "bad", "ok-2"]})
    worker = SpyWorker("w", fail_on=["bad"])

    with mock.patch("components.workflow_support.workflow.monitoring.record_worker_run") as spy:
        completed = WorkScheduler(finder, [worker], interval_seconds=1).run_once()

    assert completed == 2
    assert worker.executed == ["ok-1", "bad", "ok-2"]
    assert finder.completed == ["ok-1", "ok-2"]
    assert [c.args[:2] for c in spy.call_args_list] == [("w", "success"), ("w", "error"), ("w", "success")]


def test_start_runs_in_background_until_stopped():
    ran = threading.Event()

    class SignalWorker(SpyWorker):
        def execute(self, task):
            super().execute(task)
            ran.set()

    scheduler = WorkScheduler(FakeFinder({"w": ["t"]}), [SignalWorker("w")], interval_seconds=0.01)
    scheduler.start()
    try:
        assert ran.wait(2)
        assert scheduler.running
    finally:
        scheduler.stop()
    assert not scheduler.running

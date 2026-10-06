import logging
import threading
import time
from typing import Generic, List, Protocol, Sequence, TypeVar

from components.monitoring import monitoring

T = TypeVar("T")

logger = logging.getLogger("parklens.workflow")


class WorkFinder(Protocol[T]):
    def find_requested(self, name: str) -> List[T]:
        ...

    def mark_completed(self, task: T) -> None:
        ...


class Worker(Protocol[T]):
    name: str

    def execute(self, task: T) -> None:
        ...


class WorkScheduler(Generic[T]):
    def __init__(self, finder: WorkFinder[T], workers: Sequence[Worker[T]], interval_seconds: float):
        self.finder = finder
        self.workers = list(workers)
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread = None

    def run_once(self) -> int:
        completed = 0
        for worker in self.workers:
            for task in self.finder.find_requested(worker.name):
                started = time.perf_counter()
                try:
                    worker.execute(task)
                except Exception:
                    monitoring.record_worker_run(worker.name, "error", time.perf_counter() - started)
                    logger.exception("Worker %s failed on task %s", worker.name, task)
                    continue
                self.finder.mark_completed(task)
                monitoring.record_worker_run(worker.name, "success", time.perf_counter() - started)
                completed += 1
        return completed

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception:
                logger.exception("Work scheduler cycle failed")
            self._stop.wait(self.interval_seconds)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="work-scheduler", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

import logging
from dataclasses import dataclass
from typing import Callable, Dict, List

from components.data_analyzer.analyzer import analyze, is_national_park
from components.storage.park_store import ParkStore

logger = logging.getLogger("parklens.analyzer")

SCOPES: Dict[str, Callable[[dict], bool]] = {
    "all-parks": lambda park: True,
    "national-parks": is_national_park,
}


@dataclass(frozen=True)
class AnalyzerTask:
    scope: str
    collection_id: int


class AnalyzerWorkFinder:
    def __init__(self, store: ParkStore):
        self.store = store

    def find_requested(self, name: str) -> List[AnalyzerTask]:
        latest = self.store.latest_collection()
        if not latest:
            return []
        analyzed = self.store.latest_analyses()
        return [
            AnalyzerTask(scope=scope, collection_id=latest["id"])
            for scope in SCOPES
            if analyzed.get(scope, {}).get("collection_id") != latest["id"]
        ]

    def mark_completed(self, task: AnalyzerTask) -> None:
        logger.info("Analysis completed: %s for collection %d", task.scope, task.collection_id)


class AnalyzerWorker:
    name = "data-analyzer"

    def __init__(self, store: ParkStore):
        self.store = store

    def execute(self, task: AnalyzerTask) -> None:
        include = SCOPES[task.scope]
        parks = [p for p in self.store.all_parks() if include(p)]
        analysis = analyze(parks, self.store.all_alerts())
        self.store.save_analysis(task.scope, analysis, task.collection_id)

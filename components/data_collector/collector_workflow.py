import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, List

from components.data_collector.nps_client import NPSClient
from components.storage.park_store import ParkStore

logger = logging.getLogger("parklens.collector")


@dataclass(frozen=True)
class CollectorTask:
    name: str = "nps-catalog"


class CollectorWorkFinder:
    def __init__(self, store: ParkStore, max_age: timedelta, now: Callable[[], datetime] = datetime.utcnow):
        self.store = store
        self.max_age = max_age
        self.now = now

    def find_requested(self, name: str) -> List[CollectorTask]:
        latest = self.store.latest_collection()
        if latest and self.now() - datetime.fromisoformat(latest["collected_at"]) < self.max_age:
            return []
        return [CollectorTask()]

    def mark_completed(self, task: CollectorTask) -> None:
        logger.info("Collection completed: %s", task.name)


class CollectorWorker:
    name = "data-collector"

    def __init__(self, client: NPSClient, store: ParkStore):
        self.client = client
        self.store = store

    def execute(self, task: CollectorTask) -> None:
        parks = self.client.search_parks()
        alerts = self.client.get_alerts(p["park_code"] for p in parks)
        collection_id = self.store.record_collection(parks, alerts)
        logger.info("Collected %d parks and %d alerts (collection %d)", len(parks), len(alerts), collection_id)

#!/usr/bin/env python3

import os
from datetime import timedelta
from typing import Optional

from dotenv import load_dotenv
from flask import Flask, jsonify

load_dotenv()

from components.data_collector.collector_workflow import CollectorWorker, CollectorWorkFinder  # noqa: E402
from components.data_collector.nps_client import NPSClient  # noqa: E402
from components.monitoring import monitoring  # noqa: E402
from components.storage.park_store import ParkStore, default_database_path  # noqa: E402
from components.workflow_support.workflow import WorkScheduler  # noqa: E402


def create_app(client: Optional[NPSClient] = None, store: Optional[ParkStore] = None,
               start_scheduler: bool = True) -> Flask:
    app = Flask(__name__)
    client = client or NPSClient()
    store = store or ParkStore(default_database_path())

    finder = CollectorWorkFinder(
        store, max_age=timedelta(seconds=int(os.environ.get("COLLECTION_MAX_AGE_SECONDS", 3600)))
    )
    scheduler = WorkScheduler(
        finder, [CollectorWorker(client, store)],
        interval_seconds=float(os.environ.get("COLLECTOR_INTERVAL_SECONDS", 60)),
    )
    app.extensions["work_scheduler"] = scheduler
    monitoring.init_app(app)

    @app.route("/")
    @app.route("/health")
    def health():
        return jsonify(
            service="data-collector-server",
            scheduler_running=scheduler.running,
            nps_api_configured=client.configured,
            latest_collection=store.latest_collection(),
        )

    if start_scheduler:
        scheduler.start()
    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=int(os.environ.get("PORT", 8881)))

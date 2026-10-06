#!/usr/bin/env python3

import os
from typing import Optional

from dotenv import load_dotenv
from flask import Flask, jsonify

load_dotenv()

from components.data_analyzer.analyzer_workflow import AnalyzerWorker, AnalyzerWorkFinder  # noqa: E402
from components.monitoring import monitoring  # noqa: E402
from components.storage.park_store import ParkStore, default_database_path  # noqa: E402
from components.workflow_support.workflow import WorkScheduler  # noqa: E402


def create_app(store: Optional[ParkStore] = None, start_scheduler: bool = True) -> Flask:
    app = Flask(__name__)
    store = store or ParkStore(default_database_path())

    scheduler = WorkScheduler(
        AnalyzerWorkFinder(store), [AnalyzerWorker(store)],
        interval_seconds=float(os.environ.get("ANALYZER_INTERVAL_SECONDS", 30)),
    )
    app.extensions["work_scheduler"] = scheduler
    monitoring.init_app(app)

    @app.route("/")
    @app.route("/health")
    def health():
        latest = {
            scope: {"collection_id": snap["collection_id"], "created_at": snap["created_at"]}
            for scope, snap in store.latest_analyses().items()
        }
        return jsonify(service="data-analyzer-server", scheduler_running=scheduler.running, latest_analyses=latest)

    if start_scheduler:
        scheduler.start()
    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=int(os.environ.get("PORT", 8882)))

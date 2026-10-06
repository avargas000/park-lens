import json
import logging
import os
import sys
import time
import uuid

from flask import Flask, Response, g, request
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, Histogram, generate_latest

registry = CollectorRegistry()

HTTP_REQUESTS = Counter(
    "parklens_http_requests_total", "HTTP requests served", ["method", "endpoint", "status"], registry=registry
)
HTTP_LATENCY = Histogram(
    "parklens_http_request_duration_seconds", "HTTP request latency", ["endpoint"], registry=registry
)
NPS_CALLS = Counter(
    "parklens_nps_api_calls_total", "Calls made to the NPS API", ["endpoint", "outcome"], registry=registry
)
NPS_LATENCY = Histogram(
    "parklens_nps_api_duration_seconds", "NPS API call latency", ["endpoint"], registry=registry
)
SEARCHES = Counter("parklens_searches_total", "Park searches performed", registry=registry)
FAVORITES = Gauge("parklens_favorites", "Parks currently saved as favorites", registry=registry)
WORKER_RUNS = Counter(
    "parklens_worker_runs_total", "Background worker task executions", ["worker", "outcome"], registry=registry
)
WORKER_LATENCY = Histogram(
    "parklens_worker_duration_seconds", "Background worker task duration", ["worker"], registry=registry
)
WORKER_LAST_SUCCESS = Gauge(
    "parklens_worker_last_success_timestamp", "Unix time of the last successful task", ["worker"], registry=registry
)

logger = logging.getLogger("parklens")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        entry.update(getattr(record, "extra_fields", {}))
        if record.exc_info:
            entry["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(entry)


def record_nps_call(endpoint: str, outcome: str, seconds: float) -> None:
    NPS_CALLS.labels(endpoint=endpoint, outcome=outcome).inc()
    NPS_LATENCY.labels(endpoint=endpoint).observe(seconds)


def record_worker_run(worker: str, outcome: str, seconds: float) -> None:
    WORKER_RUNS.labels(worker=worker, outcome=outcome).inc()
    WORKER_LATENCY.labels(worker=worker).observe(seconds)
    if outcome == "success":
        WORKER_LAST_SUCCESS.labels(worker=worker).set_to_current_time()


def _configure_logging() -> None:
    if logger.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
    logger.propagate = False


def _configure_sentry() -> None:
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        return
    try:
        import sentry_sdk
    except ImportError:
        logger.warning("SENTRY_DSN is set but sentry-sdk is not installed")
        return
    sentry_sdk.init(
        dsn=dsn,
        environment=os.environ.get("APP_ENV", "production"),
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
    )


def init_app(app: Flask) -> None:
    _configure_logging()
    _configure_sentry()

    @app.before_request
    def _start_timer():
        g.request_started = time.perf_counter()
        g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]

    @app.after_request
    def _record(response):
        endpoint = request.url_rule.rule if request.url_rule else "unmatched"
        elapsed = time.perf_counter() - g.get("request_started", time.perf_counter())
        HTTP_REQUESTS.labels(method=request.method, endpoint=endpoint, status=response.status_code).inc()
        HTTP_LATENCY.labels(endpoint=endpoint).observe(elapsed)
        response.headers["X-Request-ID"] = g.get("request_id", "")
        if endpoint != "/metrics":
            logger.info(
                "request",
                extra={"extra_fields": {
                    "request_id": g.get("request_id"),
                    "method": request.method,
                    "path": request.path,
                    "status": response.status_code,
                    "duration_ms": round(elapsed * 1000, 1),
                }},
            )
        return response

    @app.route("/metrics")
    def metrics():
        return Response(generate_latest(registry), mimetype=CONTENT_TYPE_LATEST)

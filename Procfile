web: gunicorn "applications.basic_server.app:create_app()" --bind 0.0.0.0:${PORT:-8000} --workers 2 --access-logfile -
collector: gunicorn "applications.data_collector_server.app:create_app()" --bind 0.0.0.0:${COLLECTOR_PORT:-8881} --workers 1
analyzer: gunicorn "applications.data_analyzer_server.app:create_app()" --bind 0.0.0.0:${ANALYZER_PORT:-8882} --workers 1

# Park Lens

Park Lens lets you search National Park Service sites, see what activities they offer, check current alerts, and save
your favorites. Park data comes from the [NPS Data API](https://www.nps.gov/subjects/developer/).

The project layout follows [kotlin-ktor-starter](https://github.com/malston/kotlin-ktor-starter). There's one web app
and two background workers, and they all share the same SQLite database:

- **basic_server** is the Flask web app. It has the search page, autocomplete, favorites, a report page and a small
  REST API.
- **data_collector_server** pulls the full NPS park list and current alerts on a schedule.
- **data_analyzer_server** picks up each new collection and saves summary stats like "41% offer camping".

The web app works fine by itself. The workers just add the background analysis card on the Report page.

## Project structure

```
applications/
  basic_server/
  data_collector_server/
  data_analyzer_server/
components/
  data_collector/      NPS API client and the collector job
  data_analyzer/       stats, autocomplete ranking and the analyzer job
  workflow_support/    simple background job loop
  storage/             SQLite code
  monitoring/          metrics, logging, Sentry
  test_support/        fake NPS client and sample data
```

Tests live in a `tests/` folder next to the code they cover.

## Setup

You'll need a free NPS API key from https://www.nps.gov/subjects/developer/get-started.htm.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env    # then put your key in NPS_API_KEY
```

Other settings you can change:

- `DATABASE_PATH` (default `instance/parks.db`)
- `PORT` (default 8000 for the web app, 8881 for the collector, 8882 for the analyzer)
- `COLLECTION_MAX_AGE_SECONDS` (default 3600) sets how old the data can get before the collector fetches it again
- `COLLECTOR_INTERVAL_SECONDS` (default 60) and `ANALYZER_INTERVAL_SECONDS` (default 30) set how often the workers check for work
- `SENTRY_DSN` is optional

## Running it

Start each one in its own terminal:

```bash
flask --app applications.basic_server.app run --debug --port 5050
python -m applications.data_collector_server.app
python -m applications.data_analyzer_server.app
```

Then open http://localhost:5050.

## Tests

```bash
pytest components       # unit tests
pytest applications     # integration tests
pytest --cov            # all tests with coverage
flake8 applications components conftest.py
```

CI runs on GitHub Actions (`.github/workflows/ci.yml`). It does lint, tests, a coverage check, and a Docker build.

## API

- `GET /api/parks?q=&state=&national_only=1` searches parks
- `GET /api/parks?code=grca` looks up one park by code
- `GET /api/parks/suggest?q=grand` returns autocomplete suggestions
- `GET /api/parks/<park_code>` returns one park and its alerts
- `GET /api/favorites`, `POST /api/favorites`, `DELETE /api/favorites/<park_code>` manage favorites
- `GET /api/report` returns report data
- `GET /health` and `GET /metrics` are on all three apps

## Deploying

All three processes share one SQLite file, so they have to run on the same machine. `bin/start-all.sh` starts them
together in one container, and both the `Dockerfile` and `render.yaml` use it. To deploy on Render, create a Blueprint
from `render.yaml` and set `NPS_API_KEY`.

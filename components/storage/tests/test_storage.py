from components.data_analyzer.analyzer import analyze
from components.test_support.fakes import PARKS


def test_upsert_parks_inserts_then_updates(store):
    assert store.upsert_parks(PARKS) == 4
    renamed = {**PARKS[0], "name": "Yellowstone (updated)"}
    store.upsert_parks([renamed])

    assert store.counts()["parks"] == 4
    assert store.get_park("yell")["name"] == "Yellowstone (updated)"
    assert store.get_park("missing") is None


def test_all_parks_round_trips_full_records(store):
    store.upsert_parks(PARKS)
    names = [p["name"] for p in store.all_parks()]
    assert names == sorted(p["name"] for p in PARKS)
    assert store.all_parks()[0]["activities"]


def test_record_search_and_reports(store):
    store.record_search("Yellowstone", "", False, analyze(PARKS[:1]))
    store.record_search("yellowstone", "WY", False, analyze(PARKS[:2]))
    store.record_search("", "", True, analyze(PARKS))

    recent = store.recent_searches()
    assert [s["result_count"] for s in recent] == [4, 2, 1]
    assert recent[0]["query"] is None
    assert recent[0]["national_only"] == 1
    assert recent[1]["state_code"] == "WY"
    assert store.top_queries() == [{"query": "yellowstone", "count": 2}]


def test_favorites_add_update_list_remove(store):
    store.add_favorite(PARKS[0], "Old Faithful!")
    store.add_favorite(PARKS[1])
    store.add_favorite(PARKS[0], "Updated note")

    favorites = {f["park_code"]: f for f in store.list_favorites()}
    assert set(favorites) == {"yell", "grte"}
    assert favorites["yell"]["note"] == "Updated note"
    assert favorites["grte"]["note"] is None
    assert store.favorite_codes() == {"yell", "grte"}

    assert store.remove_favorite("yell") is True
    assert store.remove_favorite("yell") is False
    assert store.favorite_codes() == {"grte"}


def test_record_collection_replaces_alerts_and_tracks_runs(store):
    from components.test_support.fakes import ALERTS

    first = store.record_collection(PARKS, ALERTS)
    second = store.record_collection(PARKS[:2], ALERTS[:1])

    assert second > first
    assert store.all_alerts() == ALERTS[:1]
    assert store.counts()["parks"] == 4
    latest = store.latest_collection()
    assert (latest["id"], latest["parks_count"], latest["alerts_count"]) == (second, 2, 1)


def test_latest_analyses_returns_newest_per_scope(store):
    store.save_analysis("all-parks", {"total_parks": 1}, None)
    store.save_analysis("all-parks", {"total_parks": 2}, None)
    store.save_analysis("national-parks", {"total_parks": 3}, None)

    latest = store.latest_analyses()
    assert latest["all-parks"]["analysis"] == {"total_parks": 2}
    assert latest["national-parks"]["analysis"] == {"total_parks": 3}


def test_default_database_path_honors_env(monkeypatch):
    from components.storage.park_store import default_database_path

    monkeypatch.setenv("DATABASE_PATH", "/tmp/custom.db")
    assert default_database_path() == "/tmp/custom.db"
    monkeypatch.delenv("DATABASE_PATH")
    assert default_database_path().endswith("instance/parks.db")


def test_data_persists_across_store_instances(store):
    from components.storage.park_store import ParkStore

    store.add_favorite(PARKS[0])
    reopened = ParkStore(store.path)
    assert reopened.favorite_codes() == {"yell"}
    assert reopened.ping()

import pytest

from applications.basic_server.app import create_app
from components.storage.park_store import ParkStore
from components.test_support.fakes import FakeNPSClient


@pytest.fixture
def store(tmp_path):
    return ParkStore(str(tmp_path / "parks.db"))


@pytest.fixture
def fake_nps():
    return FakeNPSClient()


@pytest.fixture
def app(fake_nps, store):
    return create_app(client=fake_nps, store=store, config={"TESTING": True})


@pytest.fixture
def client(app):
    return app.test_client()

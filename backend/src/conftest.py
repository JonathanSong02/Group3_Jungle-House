"""Tests never contact shared MySQL, Notion or paid providers."""
import os
os.environ.setdefault("FLASK_SECRET_KEY", "isolated-image-tests-only-not-a-production-secret")
os.environ["NOTION_AUTO_SYNC_ENABLED"] = "false"
os.environ["IMAGE_INDEX_WORKER_ENABLED"] = "false"

import pytest


@pytest.fixture(autouse=True)
def no_external_services(monkeypatch):
    import mysql.connector
    import requests
    def denied(*args, **kwargs):
        raise AssertionError("External service access is forbidden in isolated tests")
    monkeypatch.setattr(mysql.connector, "connect", denied)
    monkeypatch.setattr(requests, "post", denied)
    monkeypatch.setattr(requests, "get", denied)

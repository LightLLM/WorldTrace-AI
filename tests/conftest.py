"""Pytest fixtures using an isolated episodes directory."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core import config as config_mod
from app.services.episode import EpisodeService
from app.main import app
import app.api.routes as routes
import app.main as main_mod


@pytest.fixture()
def tmp_episodes(tmp_path, monkeypatch):
    episodes = tmp_path / "episodes"
    episodes.mkdir()
    monkeypatch.setattr(config_mod.settings, "episodes_dir", episodes)
    monkeypatch.setattr(config_mod, "EPISODES_DIR", episodes)
    service = EpisodeService(config_mod.settings)
    monkeypatch.setattr(routes, "episode_service", service)
    monkeypatch.setattr("app.services.episode.episode_service", service)
    monkeypatch.setattr(main_mod.settings, "episodes_dir", episodes)
    yield service
    if episodes.exists():
        shutil.rmtree(episodes, ignore_errors=True)


@pytest.fixture()
def client(tmp_episodes):
    return TestClient(app)

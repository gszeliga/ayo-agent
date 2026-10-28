"""Request dependencies. The lifespan puts these objects in `request.state`; tests can
swap them with `app.dependency_overrides`."""

from fastapi import Request
from psycopg_pool import ConnectionPool

from ayo_copilot.config import Settings
from ayo_copilot.ingestion.embedding import Embedder


def get_settings(request: Request) -> Settings:
    return request.state.settings


def get_pool(request: Request) -> ConnectionPool:
    return request.state.pool


def get_embedder(request: Request) -> Embedder:
    return request.state.embedder

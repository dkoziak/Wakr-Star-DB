"""
Test infrastructure.

Environment variables must be set before any app modules are imported so that
pydantic-settings picks up DEBUG=true (bypasses JWT validation) and a dummy
DATABASE_URL (SQLAlchemy engine creation is lazy — no actual connection is made).
"""

import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test_wakr")

from contextlib import asynccontextmanager  # noqa: E402
from unittest.mock import AsyncMock, MagicMock  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402

AUTH = {"Authorization": "Bearer test-token"}


# ---------------------------------------------------------------------------
# DB mock helpers
# ---------------------------------------------------------------------------

def mock_result(*rows):
    """
    Wrap row data in a mock that mimics an SQLAlchemy CursorResult.
    Supports both fetchone() and fetchall().
    """
    m = MagicMock()
    m.fetchone.return_value = rows[0] if rows else None
    m.fetchall.return_value = list(rows)
    return m


def mock_conn(*results):
    """
    Build a mock AsyncConnection whose execute() returns each item in *results
    in sequence (one per call).  Each item should be a mock_result(...).
    """
    conn = AsyncMock()
    conn.execute.side_effect = list(results)
    return conn


@asynccontextmanager
async def _yield_conn(conn):
    yield conn


def get_conn_for(conn):
    """
    Return a drop-in replacement for db.engine.get_conn that yields *conn*.
    Usage:
        with patch("routers.inventory.get_conn", get_conn_for(conn)):
            ...
    """
    def _factory():
        return _yield_conn(conn)
    return _factory


# ---------------------------------------------------------------------------
# Client fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def client():
    """Synchronous TestClient — safe to share across the whole test session."""
    with TestClient(app) as c:
        yield c

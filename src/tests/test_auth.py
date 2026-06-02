"""Unit tests for auth.py — covers the paths that debug mode bypasses."""

import pytest
from unittest.mock import patch, AsyncMock
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from auth import _has_required_scope, require_auth


# ---------------------------------------------------------------------------
# _has_required_scope unit tests (pure function, no async)
# ---------------------------------------------------------------------------

class TestHasRequiredScope:
    def test_string_scope_match(self):
        assert _has_required_scope({"scope": "wakr:read"}, "wakr:read") is True

    def test_string_scope_multi_match(self):
        assert _has_required_scope({"scope": "wakr:read wakr:write"}, "wakr:read") is True

    def test_string_scope_no_match(self):
        assert _has_required_scope({"scope": "wakr:write"}, "wakr:read") is False

    def test_list_scope_match(self):
        assert _has_required_scope({"scope": ["wakr:read", "wakr:write"]}, "wakr:read") is True

    def test_list_scope_no_match(self):
        assert _has_required_scope({"scope": ["wakr:write"]}, "wakr:read") is False

    def test_missing_scope_key(self):
        assert _has_required_scope({}, "wakr:read") is False

    def test_none_scope(self):
        assert _has_required_scope({"scope": None}, "wakr:read") is False


# ---------------------------------------------------------------------------
# require_auth integration tests (async, production path)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_missing_credentials_raises_401():
    with pytest.raises(HTTPException) as exc_info:
        await require_auth(None)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_wrong_scheme_raises_401():
    creds = HTTPAuthorizationCredentials(scheme="Basic", credentials="abc123")
    with pytest.raises(HTTPException) as exc_info:
        await require_auth(creds)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_wrong_scope_raises_403():
    creds = HTTPAuthorizationCredentials(scheme="bearer", credentials="some-token")

    with patch("auth.settings") as mock_settings:
        mock_settings.debug = False
        mock_settings.jwt_public_key = "fake-key"
        mock_settings.token_audience = "test"
        mock_settings.token_issuer = "test"

        with patch("auth.jwt.decode", return_value={"scope": "wakr:write"}):
            with pytest.raises(HTTPException) as exc_info:
                await require_auth(creds)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_correct_scope_returns_token():
    creds = HTTPAuthorizationCredentials(scheme="bearer", credentials="valid-token")

    with patch("auth.settings") as mock_settings:
        mock_settings.debug = False
        mock_settings.jwt_public_key = "fake-key"
        mock_settings.token_audience = "test"
        mock_settings.token_issuer = "test"

        with patch("auth.jwt.decode", return_value={"scope": "wakr:read"}):
            result = await require_auth(creds)

    assert result == "valid-token"


@pytest.mark.asyncio
async def test_list_scope_format_accepted():
    creds = HTTPAuthorizationCredentials(scheme="bearer", credentials="valid-token")

    with patch("auth.settings") as mock_settings:
        mock_settings.debug = False
        mock_settings.jwt_public_key = "fake-key"
        mock_settings.token_audience = "test"
        mock_settings.token_issuer = "test"

        with patch("auth.jwt.decode", return_value={"scope": ["wakr:read"]}):
            result = await require_auth(creds)

    assert result == "valid-token"

"""Shared fixtures -- mirrors Media Studio's ctx fixture."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def ctx():
    from imperal_sdk.testing import MockContext, MockSecretStore

    mock = MockContext()
    mock.secrets = MockSecretStore({})
    return mock


@pytest.fixture
def ctx_connected(ctx):
    """Same as `ctx` but with DataForSEO credentials already saved."""
    from imperal_sdk.testing import MockSecretStore
    ctx.secrets = MockSecretStore({
        "dataforseo_login": "test@example.com",
        "dataforseo_password": "test-pass",
    })
    return ctx

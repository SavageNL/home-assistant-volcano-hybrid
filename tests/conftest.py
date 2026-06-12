"""Fixtures for the Volcano Hybrid tests."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading custom integrations in all tests."""


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Prevent the integration from actually being set up."""
    with patch(
        "custom_components.volcano_hybrid.async_setup_entry", return_value=True
    ) as mock:
        yield mock

"""Fixtures for the SwitchBot Outdoor Meter tests."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _mock_bluetooth_history() -> Generator[None]:
    """Avoid the Linux/D-Bus history load when the Bluetooth manager starts.

    The bundled ``mock_bluetooth_adapters`` fixture mocks the adapter list but not
    the D-Bus-backed history, which is unavailable on macOS CI.
    """
    with patch(
        "homeassistant.components.bluetooth.manager.async_load_history_from_system",
        return_value=({}, {}),
    ):
        yield


@pytest.fixture(autouse=True)
def _enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading the custom integration in tests."""
    return

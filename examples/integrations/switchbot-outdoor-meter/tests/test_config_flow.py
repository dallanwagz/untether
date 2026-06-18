"""Config-flow tests for the SwitchBot Outdoor Meter integration."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.config_entries import SOURCE_BLUETOOTH, SOURCE_USER
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.switchbot_outdoor_meter.const import DOMAIN
from tests.common import GOLDEN_ADDRESS, make_service_info

SETUP = "custom_components.switchbot_outdoor_meter.async_setup_entry"
DISCOVERED = (
    "custom_components.switchbot_outdoor_meter.config_flow."
    "async_discovered_service_info"
)


async def test_bluetooth_discovery_confirm(hass: HomeAssistant) -> None:
    """A discovered meter can be confirmed and set up."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=make_service_info()
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "bluetooth_confirm"

    with patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == GOLDEN_ADDRESS


async def test_bluetooth_discovery_not_supported(hass: HomeAssistant) -> None:
    """A non-meter SwitchBot advertisement is rejected."""
    info = make_service_info(
        manufacturer_data=bytes.fromhex("ee16a611ddd500ff6a3344338206999e00"),
        service_data=bytes.fromhex("7600"),
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=info
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_supported"


async def test_bluetooth_discovery_already_configured(hass: HomeAssistant) -> None:
    """Re-discovering a configured meter aborts."""
    MockConfigEntry(domain=DOMAIN, unique_id=GOLDEN_ADDRESS).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=make_service_info()
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_step_no_devices(hass: HomeAssistant) -> None:
    """The user step aborts when nothing is discovered."""
    with patch(DISCOVERED, return_value=[]):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


async def test_user_step_picks_discovered(hass: HomeAssistant) -> None:
    """The user step lists a discovered meter and sets it up."""
    with patch(DISCOVERED, return_value=[make_service_info()]):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"

        with patch(SETUP, return_value=True):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {CONF_ADDRESS: GOLDEN_ADDRESS}
            )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == GOLDEN_ADDRESS


async def test_user_step_skips_already_configured(hass: HomeAssistant) -> None:
    """The user step skips an already-configured meter."""
    MockConfigEntry(domain=DOMAIN, unique_id=GOLDEN_ADDRESS).add_to_hass(hass)
    with patch(DISCOVERED, return_value=[make_service_info()]):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"

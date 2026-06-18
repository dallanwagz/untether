"""Config flow — Bluetooth auto-discovery + a manual picker, the HA Core pattern."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import DOMAIN
from .protocol import parse_advertisement


class GoveeBLEConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Govee BLE (RE dry-run)."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery: BluetoothServiceInfoBleak | None = None
        self._discovered: dict[str, BluetoothServiceInfoBleak] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle a flow started by Bluetooth discovery."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        # Only proceed if it actually decodes as one of our supported models.
        if parse_advertisement(discovery_info.manufacturer_data, local_name=discovery_info.name) is None:
            return self.async_abort(reason="not_supported")
        self._discovery = discovery_info
        self.context["title_placeholders"] = {"name": discovery_info.name}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a single discovered device."""
        assert self._discovery is not None
        if user_input is not None:
            return self.async_create_entry(title=self._discovery.name, data={})
        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": self._discovery.name},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manual fallback: pick from discovered, supported devices."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=self._discovered[address].name, data={})

        for info in async_discovered_service_info(self.hass, connectable=False):
            if info.address in self._async_current_ids():
                continue
            if parse_advertisement(info.manufacturer_data, local_name=info.name) is not None:
                self._discovered[info.address] = info
        if not self._discovered:
            return self.async_abort(reason="no_devices_found")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(
                        {a: f"{i.name} ({a})" for a, i in self._discovered.items()}
                    )
                }
            ),
        )

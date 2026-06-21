"""BlueZ live-SDP wrapper tests (pure helper + optional-dependency guard)."""

import importlib.util

import pytest

from untether_bt import bluez


def test_is_spp_pure():
    assert bluez._is_spp({"service-classes": ["1101"]})
    assert bluez._is_spp({"service-classes": ["0x1101", "1800"]})
    assert not bluez._is_spp({"service-classes": ["1124"]})
    assert not bluez._is_spp({})


def test_browse_requires_pybluez():
    if importlib.util.find_spec("bluetooth") is not None:
        pytest.skip("pybluez present; skipping the missing-dependency path")
    with pytest.raises((ImportError, ModuleNotFoundError)):
        bluez.browse_services("AA:BB:CC:DD:EE:FF")

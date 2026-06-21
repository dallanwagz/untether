"""Live SDP browsing on Linux via BlueZ (optional, needs pybluez).

The only first-class way to *issue* a Classic SDP query from Python is a Classic-capable host stack.
On Linux/BlueZ that's pybluez (``pip install untether-bt[bluez]``; Linux only). This is a thin
wrapper that returns the dynamic RFCOMM/SPP channel — so you don't hardcode it. (On other hosts,
recover the channel from a capture via ``Capture.sdp_records()`` + ``sdp.spp_channel``, or let the
``untether_spp`` ESP32 bridge SDP-discover it on-device with ``channel: 0``.)
"""

from __future__ import annotations

SPP_CLASS = "1101"


def browse_services(mac: str) -> list[dict]:
    """All advertised services for a device (raw pybluez records)."""
    import bluetooth  # pybluez — Linux only

    return bluetooth.find_service(address=mac)


def _is_spp(svc: dict) -> bool:
    classes = svc.get("service-classes") or []
    return any(SPP_CLASS in str(c).upper() for c in classes)


def spp_channel(mac: str) -> int | None:
    """The RFCOMM channel of the device's Serial Port service (falls back to any RFCOMM port)."""
    services = browse_services(mac)
    rfcomm = [s for s in services if s.get("protocol") == "RFCOMM" and s.get("port")]
    for s in rfcomm:
        if _is_spp(s):
            return int(s["port"])
    return int(rfcomm[0]["port"]) if rfcomm else None

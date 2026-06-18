# 5 · Root-causing recurring stalls (instrument, don't just reboot)

A second device on this setup (an Atorch USB power meter on the same protocol family) periodically
got stuck: HA showed `connection_state = reconnecting`, all sensors `unavailable`. The coordinator
log told us *what*, but not *why*:

```
[WARNING] custom_components.atorch_ble.coordinator
  BLE connection failed (mac=c2:67:69:00:00:01): ...
  Failed to connect after 4 attempt(s): Timeout waiting for connect response
```

A proxy *reached* the device but the connect timed out. The deciding question for "our code vs the
hardware" is: **while connects fail, is the device still advertising, and is a reachable proxy slot
free?** HA exposes both over its WebSocket API.

## The signals (captured before recovering)

```python
# is it still advertising? (and RSSI / which proxy)
await ws.send({"type": "bluetooth/subscribe_advertisements"})
# ... collect events; match the MAC -> advertising = True/False, latest rssi, source proxy

# per-proxy connection-slot allocations — starvation vs free
await ws.send({"type": "bluetooth/subscribe_connection_allocations"})
```

Real allocation snapshot (healthy) — this is how we proved the chair wasn't starving the meter's
proxy (they're on *different* proxies, each with free slots):

```
esphome-proxy-1    (C4:5B:BE:00:00:01)  slots 3, free 2, allocated [57:4C:54:00:00:01]  <- chair
esphome-proxy-2    (C4:5B:BE:00:00:02)  slots 3, free 2, allocated [C2:67:69:00:00:01]  <- meter
hci0               (F4:3B:D8:00:00:01)  slots 5, free 5
```

## The verdict logic

```python
if not advertising:           verdict = "HARDWARE_meter_not_advertising"   # radio hung -> power-cycle only
elif advertising and free_slot: verdict = "CODE_or_FIRMWARE_no_connect"    # reachable but won't connect
else:                          verdict = "SLOT_STARVATION"                 # every reachable proxy full
```

## Auto-recover + accumulate evidence

A watchdog polls health, and on a stall **captures the snapshot above into an incident report**,
then power-cycles the device via its HA switch (an eWeLink smart plug) and logs the recovery time:

```python
call_service("switch", "turn_off", {"entity_id": RECOVERY_PLUG})   # the plug powering the meter
time.sleep(15)
call_service("switch", "turn_on",  {"entity_id": RECOVERY_PLUG})
# then poll connection_state until "connected"; record recovery_seconds
```

Each incident → `incident_<ts>.json` + a row in `incidents.csv` (advertising?, rssi, free slots,
device runtime, verdict, recovery time). Over many incidents the CSV answers the real question —
**is the stall a bug in our integration to fix before the PR, or a hardware hang the device-side
firmware owns?** — instead of papering over it with a blind reboot.

> Takeaway: when a BLE integration "randomly" drops, the advertising-state + slot-allocation pair
> is the cheapest, most decisive diagnostic. Capture it *before* you recover.

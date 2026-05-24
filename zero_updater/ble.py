"""BLE discovery and connection helpers for Flipper Zero."""

from __future__ import annotations

import asyncio

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

# Flipper BLE Serial Service UUIDs (from serial_service_uuid.inc)
SERIAL_SERVICE = "8fe5b3d5-2e7f-4a98-2a48-7acc60fe0000"
TX_CHAR = "19ed82ae-ed21-4c9d-4145-228e61fe0000"  # Flipper → phone (indicate)
RX_CHAR = "19ed82ae-ed21-4c9d-4145-228e62fe0000"  # phone → Flipper (write)
FC_CHAR = "19ed82ae-ed21-4c9d-4145-228e63fe0000"  # flow control (notify)
STS_CHAR = "19ed82ae-ed21-4c9d-4145-228e64fe0000"  # RPC status (notify+write)


async def find_flipper(
    address: str | None = None,
    name_prefix: str = "Flipper",
    timeout: float = 10.0,
) -> BLEDevice | None:
    """Find a Flipper Zero via BLE.

    Tries address lookup first (fast), falls back to full scan + name match.
    """
    if address:
        dev = await BleakScanner.find_device_by_address(address, timeout=timeout)
        if dev:
            return dev

    devices = await BleakScanner.discover(timeout=timeout)
    for d in devices:
        if address and d.address == address:
            return d
        if d.name and d.name.startswith(name_prefix):
            return d
    return None

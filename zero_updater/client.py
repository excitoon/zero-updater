"""Flipper Zero RPC client over BLE serial."""

from __future__ import annotations

import asyncio
import time
from typing import Callable

from bleak import BleakClient

from zero_updater.ble import RX_CHAR, TX_CHAR
from zero_updater._pb import get_pb2


class FlipperRPC:
    """Protobuf RPC client for Flipper Zero over BLE serial.

    Usage::

        from bleak import BleakClient
        from zero_rpc import FlipperRPC, find_flipper

        dev = await find_flipper(address="AA:BB:CC:DD:EE:FF")
        async with BleakClient(dev) as client:
            rpc = FlipperRPC(client)
            await rpc.start()
            await rpc.storage_write("/ext/test.txt", b"hello")
            await rpc.app_start("/ext/apps/Tools/my_app.fap")
            await rpc.stop()
    """

    WRITE_CHUNK = 512

    def __init__(
        self,
        client: BleakClient,
        *,
        debug: bool = False,
        on_raw: Callable[[bytes], None] | None = None,
    ):
        self.client = client
        self.pb2 = get_pb2()
        self.debug = debug
        self._on_raw = on_raw
        self._cmd_id = 0
        self._rx_buf = bytearray()
        self._raw_rx = bytearray()
        self._rpc_mode = False
        self._responses: asyncio.Queue = asyncio.Queue()

    # ── BLE notification handler ────────────────────────────────────────────

    def _on_data(self, _: int, data: bytearray) -> None:
        if self.debug:
            print(f"  [RX {len(data)}b] {data[:40].hex()}", flush=True)
        if self._on_raw:
            self._on_raw(bytes(data))
        if not self._rpc_mode:
            self._raw_rx.extend(data)
            return
        self._rx_buf.extend(data)
        self._try_parse()

    def _try_parse(self) -> None:
        while len(self._rx_buf) > 0:
            # Read varint length prefix
            varint_val = 0
            shift = 0
            i = 0
            while i < len(self._rx_buf):
                byte = self._rx_buf[i]
                varint_val |= (byte & 0x7F) << shift
                shift += 7
                i += 1
                if not (byte & 0x80):
                    break
            else:
                return  # incomplete varint
            if len(self._rx_buf) < i + varint_val:
                return  # incomplete message
            msg_data = bytes(self._rx_buf[i : i + varint_val])
            self._rx_buf = self._rx_buf[i + varint_val :]
            try:
                msg = self.pb2.Main()
                msg.ParseFromString(msg_data)
                self._responses.put_nowait(msg)
            except Exception as e:
                if self.debug:
                    print(f"  [parse error: {e}]")
                continue

    # ── Session lifecycle ───────────────────────────────────────────────────

    async def start(self) -> None:
        """Subscribe to BLE notifications and start RPC session."""
        await self.client.start_notify(TX_CHAR, self._on_data)
        await self._init_rpc_session()

    async def _init_rpc_session(self, timeout: float = 5.0) -> None:
        """Send CLI command to open the protobuf RPC channel."""
        self._raw_rx.clear()
        cmd = b"start_rpc_session\r\n"
        chunk_sz = min(self.client.mtu_size - 3, 200)
        for i in range(0, len(cmd), chunk_sz):
            await self.client.write_gatt_char(
                RX_CHAR, cmd[i : i + chunk_sz], response=True
            )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            await asyncio.sleep(0.1)
            if self._raw_rx:
                resp = bytes(self._raw_rx)
                if b"session_started" in resp or b"Session started" in resp:
                    break
        self._rpc_mode = True
        self._raw_rx.clear()

    async def stop(self) -> None:
        """Unsubscribe from BLE notifications."""
        try:
            await self.client.stop_notify(TX_CHAR)
        except Exception:
            pass

    # ── Wire helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _varint(v: int) -> bytes:
        buf = bytearray()
        while v > 0x7F:
            buf.append((v & 0x7F) | 0x80)
            v >>= 7
        buf.append(v & 0x7F)
        return bytes(buf)

    async def _send(self, msg) -> None:
        data = msg.SerializeToString()
        frame = self._varint(len(data)) + data
        chunk_sz = min(self.client.mtu_size - 3, 200)
        for i in range(0, len(frame), chunk_sz):
            await self.client.write_gatt_char(
                RX_CHAR, frame[i : i + chunk_sz], response=False
            )
            await asyncio.sleep(0.005)

    async def _recv(self, timeout: float = 30.0):
        return await asyncio.wait_for(self._responses.get(), timeout=timeout)

    def _next_id(self) -> int:
        self._cmd_id += 1
        return self._cmd_id

    # ── RPC commands ────────────────────────────────────────────────────────

    async def ping(self) -> bool:
        """Send a system ping and wait for response."""
        msg = self.pb2.Main()
        msg.command_id = self._next_id()
        msg.system_ping_request.SetInParent()
        await self._send(msg)
        try:
            resp = await self._recv(timeout=5.0)
            return resp.command_status == 0
        except (TimeoutError, asyncio.TimeoutError):
            return False

    async def storage_write(
        self,
        path: str,
        data: bytes,
        progress: Callable[[int, int], None] | None = None,
    ) -> bool:
        """Write a file to the Flipper's storage.

        Args:
            path: Destination path on Flipper (e.g. "/ext/apps/Tools/app.fap")
            data: File contents
            progress: Optional callback(sent, total)
        """
        total = len(data)
        sent = 0
        while sent < total:
            end = min(sent + self.WRITE_CHUNK, total)
            is_last = end >= total
            msg = self.pb2.Main()
            msg.command_id = self._next_id()
            msg.has_next = not is_last
            msg.storage_write_request.path = path
            msg.storage_write_request.file.data = data[sent:end]
            await self._send(msg)
            sent = end
            if progress:
                progress(sent, total)
            if not is_last:
                await asyncio.sleep(0.02)
        resp = await self._recv()
        return resp.command_status == 0

    async def storage_read(self, path: str) -> bytes | None:
        """Read a file from the Flipper's storage."""
        msg = self.pb2.Main()
        msg.command_id = self._next_id()
        msg.storage_read_request.path = path
        await self._send(msg)
        try:
            resp = await self._recv()
            if resp.command_status != 0:
                return None
            return resp.storage_read_response.file.data
        except (TimeoutError, asyncio.TimeoutError):
            return None

    async def storage_stat(self, path: str) -> dict | None:
        """Stat a file on Flipper storage. Returns {size, type} or None."""
        msg = self.pb2.Main()
        msg.command_id = self._next_id()
        msg.storage_stat_request.path = path
        await self._send(msg)
        try:
            resp = await self._recv()
            if resp.command_status != 0:
                return None
            f = resp.storage_stat_response.file
            return {"size": f.size, "type": f.type}
        except (TimeoutError, asyncio.TimeoutError):
            return None

    async def storage_delete(self, path: str, recursive: bool = False) -> bool:
        """Delete a file or directory."""
        msg = self.pb2.Main()
        msg.command_id = self._next_id()
        msg.storage_delete_request.path = path
        msg.storage_delete_request.recursive = recursive
        await self._send(msg)
        resp = await self._recv()
        return resp.command_status == 0

    async def storage_list(self, path: str) -> list[dict] | None:
        """List directory contents. Returns list of {name, size, type}."""
        msg = self.pb2.Main()
        msg.command_id = self._next_id()
        msg.storage_list_request.path = path
        await self._send(msg)
        try:
            resp = await self._recv()
            if resp.command_status != 0:
                return None
            return [
                {"name": f.name, "size": f.size, "type": f.type}
                for f in resp.storage_list_response.file
            ]
        except (TimeoutError, asyncio.TimeoutError):
            return None

    async def app_start(self, name: str, args: str = "") -> bool:
        """Launch an application on the Flipper."""
        msg = self.pb2.Main()
        msg.command_id = self._next_id()
        msg.app_start_request.name = name
        if args:
            msg.app_start_request.args = args
        await self._send(msg)
        resp = await self._recv()
        return resp.command_status == 0

    async def app_exit(self) -> bool:
        """Exit the currently running application."""
        msg = self.pb2.Main()
        msg.command_id = self._next_id()
        msg.app_exit_request.SetInParent()
        await self._send(msg)
        resp = await self._recv()
        return resp.command_status == 0

    async def system_reboot(self, mode: int = 0) -> None:
        """Reboot the Flipper. mode: 0=OS, 1=DFU, 2=UPDATE."""
        msg = self.pb2.Main()
        msg.command_id = self._next_id()
        msg.system_reboot_request.mode = mode
        await self._send(msg)
        # No response expected — Flipper reboots immediately

    async def system_device_info(self) -> dict:
        """Get device info. Returns dict of key-value pairs."""
        msg = self.pb2.Main()
        msg.command_id = self._next_id()
        msg.system_device_info_request.SetInParent()
        await self._send(msg)
        info = {}
        while True:
            try:
                resp = await self._recv(timeout=5.0)
                if hasattr(resp, "system_device_info_response"):
                    r = resp.system_device_info_response
                    info[r.key] = r.value
                if not resp.has_next:
                    break
            except (TimeoutError, asyncio.TimeoutError):
                break
        return info

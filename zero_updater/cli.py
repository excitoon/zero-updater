"""CLI for Flipper Zero updater over BLE."""

from __future__ import annotations

import argparse
import asyncio
import sys


def _progress(sent: int, total: int) -> None:
    pct = sent * 100 // total
    print(f"\r  {sent}/{total} ({pct}%)", end="", flush=True)


async def cmd_upload(args: argparse.Namespace) -> bool:
    from bleak import BleakClient
    from zero_updater import FlipperRPC, find_flipper

    data = open(args.file, "rb").read()
    print(f"File: {args.file} ({len(data)} bytes)")
    print(f"Dest: {args.path}")

    dev = await find_flipper(address=args.address, timeout=args.timeout)
    if not dev:
        print("Flipper not found via BLE")
        return False

    print(f"Connecting to {dev.name}...")
    async with BleakClient(dev, timeout=20.0) as client:
        print(f"Connected, MTU={client.mtu_size}")
        rpc = FlipperRPC(client, debug=args.debug)
        await rpc.start()

        print("Uploading...")
        ok = await rpc.storage_write(args.path, data, progress=_progress)
        print()
        if not ok:
            print("Upload failed!")
            await rpc.stop()
            return False
        print("Upload OK!")

        if args.launch:
            print("Launching...")
            ok = await rpc.app_start(args.path)
            if ok:
                print("App launched!")
            else:
                print("Launch failed")

        await rpc.stop()
    return True


async def cmd_launch(args: argparse.Namespace) -> bool:
    from bleak import BleakClient
    from zero_updater import FlipperRPC, find_flipper

    dev = await find_flipper(address=args.address, timeout=args.timeout)
    if not dev:
        print("Flipper not found via BLE")
        return False

    print(f"Connecting to {dev.name}...")
    async with BleakClient(dev, timeout=20.0) as client:
        rpc = FlipperRPC(client, debug=args.debug)
        await rpc.start()
        ok = await rpc.app_start(args.path, args=args.args or "")
        await rpc.stop()
    if ok:
        print(f"Launched: {args.path}")
    else:
        print("Launch failed")
    return ok


async def cmd_ls(args: argparse.Namespace) -> bool:
    from bleak import BleakClient
    from zero_updater import FlipperRPC, find_flipper

    dev = await find_flipper(address=args.address, timeout=args.timeout)
    if not dev:
        print("Flipper not found via BLE")
        return False

    async with BleakClient(dev, timeout=20.0) as client:
        rpc = FlipperRPC(client, debug=args.debug)
        await rpc.start()
        entries = await rpc.storage_list(args.path)
        await rpc.stop()

    if entries is None:
        print(f"Failed to list: {args.path}")
        return False
    for e in entries:
        kind = "d" if e["type"] == 1 else "-"
        print(f"  {kind} {e['size']:>8}  {e['name']}")
    return True


async def cmd_read(args: argparse.Namespace) -> bool:
    from bleak import BleakClient
    from zero_updater import FlipperRPC, find_flipper

    dev = await find_flipper(address=args.address, timeout=args.timeout)
    if not dev:
        print("Flipper not found via BLE")
        return False

    async with BleakClient(dev, timeout=20.0) as client:
        rpc = FlipperRPC(client, debug=args.debug)
        await rpc.start()
        data = await rpc.storage_read(args.path)
        await rpc.stop()

    if data is None:
        print(f"Failed to read: {args.path}")
        return False

    if args.output:
        open(args.output, "wb").write(data)
        print(f"Saved {len(data)} bytes to {args.output}")
    else:
        sys.stdout.buffer.write(data)
    return True


async def cmd_info(args: argparse.Namespace) -> bool:
    from bleak import BleakClient
    from zero_updater import FlipperRPC, find_flipper

    dev = await find_flipper(address=args.address, timeout=args.timeout)
    if not dev:
        print("Flipper not found via BLE")
        return False

    async with BleakClient(dev, timeout=20.0) as client:
        rpc = FlipperRPC(client, debug=args.debug)
        await rpc.start()
        info = await rpc.system_device_info()
        await rpc.stop()

    for k, v in sorted(info.items()):
        print(f"  {k}: {v}")
    return True


async def cmd_ping(args: argparse.Namespace) -> bool:
    from bleak import BleakClient
    from zero_updater import FlipperRPC, find_flipper

    dev = await find_flipper(address=args.address, timeout=args.timeout)
    if not dev:
        print("Flipper not found via BLE")
        return False

    async with BleakClient(dev, timeout=20.0) as client:
        rpc = FlipperRPC(client, debug=args.debug)
        await rpc.start()
        ok = await rpc.ping()
        await rpc.stop()

    print("pong" if ok else "no response")
    return ok


async def cmd_reboot(args: argparse.Namespace) -> bool:
    from bleak import BleakClient
    from zero_updater import FlipperRPC, find_flipper

    dev = await find_flipper(address=args.address, timeout=args.timeout)
    if not dev:
        print("Flipper not found via BLE")
        return False

    async with BleakClient(dev, timeout=20.0) as client:
        rpc = FlipperRPC(client, debug=args.debug)
        await rpc.start()
        mode = {"os": 0, "dfu": 1, "update": 2}[args.mode]
        await rpc.system_reboot(mode)
    print(f"Rebooting ({args.mode})...")
    return True


def main() -> None:
    p = argparse.ArgumentParser(
        prog="zero-updater",
        description="Flipper Zero RPC client over BLE",
    )
    p.add_argument("-a", "--address", help="BLE address of Flipper")
    p.add_argument("-t", "--timeout", type=float, default=10.0, help="BLE scan timeout")
    p.add_argument("--debug", action="store_true", help="print raw BLE data")

    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("upload", help="upload a file to Flipper storage")
    sp.add_argument("file", help="local file to upload")
    sp.add_argument("path", help="destination path on Flipper")
    sp.add_argument("-l", "--launch", action="store_true", help="launch after upload")

    sp = sub.add_parser("launch", help="launch an app on Flipper")
    sp.add_argument("path", help="app path on Flipper")
    sp.add_argument("--args", help="launch arguments")

    sp = sub.add_parser("ls", help="list directory on Flipper")
    sp.add_argument("path", help="directory path")

    sp = sub.add_parser("read", help="read a file from Flipper")
    sp.add_argument("path", help="file path on Flipper")
    sp.add_argument("-o", "--output", help="save to local file")

    sp = sub.add_parser("info", help="show device info")

    sp = sub.add_parser("ping", help="ping the Flipper")

    sp = sub.add_parser("reboot", help="reboot the Flipper")
    sp.add_argument("--mode", choices=["os", "dfu", "update"], default="os")

    args = p.parse_args()

    handlers = {
        "upload": cmd_upload,
        "launch": cmd_launch,
        "ls": cmd_ls,
        "read": cmd_read,
        "info": cmd_info,
        "ping": cmd_ping,
        "reboot": cmd_reboot,
    }

    ok = asyncio.run(handlers[args.command](args))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

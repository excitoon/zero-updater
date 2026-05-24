# Zero Updater

Flipper Zero RPC client over BLE. Upload files, launch apps, and manage storage — all wirelessly.

Built for deploying [zero-bluetooth-bridge](https://github.com/excitoon/zero-bluetooth-bridge) and other Flipper apps without a USB cable.

## Install

```bash
pip install git+https://github.com/excitoon/zero-updater.git
```

Requires Python 3.10+ and a BLE-capable host (macOS, Linux, Windows).

## Usage

```bash
# Upload and launch an app
zero-updater upload my_app.fap /ext/apps/Tools/my_app.fap --launch

# List files
zero-updater ls /ext/apps/

# Read a file
zero-updater read /ext/apps/Tools/my_app.fap -o local_copy.fap

# Device info
zero-updater info

# Ping
zero-updater ping

# Reboot
zero-updater reboot
```

### Options

```
-a, --address    BLE address of Flipper (auto-discovered if omitted)
-t, --timeout    BLE scan timeout in seconds (default: 10)
--debug          Print raw BLE data
```

## Python API

```python
import asyncio
from bleak import BleakClient
from zero_updater import FlipperRPC, find_flipper

async def main():
    dev = await find_flipper()
    async with BleakClient(dev) as client:
        rpc = FlipperRPC(client)
        await rpc.start()

        await rpc.storage_write("/ext/test.txt", b"hello flipper")
        entries = await rpc.storage_list("/ext/")
        info = await rpc.system_device_info()
        await rpc.app_start("/ext/apps/Tools/my_app.fap")

        await rpc.stop()

asyncio.run(main())
```

## License

MIT

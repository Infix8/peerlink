# PeerLink

> Zero-config P2P RPC over LAN/WiFi — mDNS discovery + UDP transport

## Install

```bash
pip install zeroconf
# download peerlink.py to your project folder
```

## Quick Start

Run these on **two separate devices or terminals** on the same LAN.

**Phone1 (server):**

```python
from peerlink import PeerLink

with PeerLink("Phone1") as node:
    node.register("add", lambda x, y: x + y)
    print("Phone1 ready; waiting for RPC calls...")
    import time
    while True:
        time.sleep(1)
```

**Phone2 (client):**

```python
from peerlink import PeerLink

with PeerLink("Phone2") as node:
    if not node.wait_for_peers(1, timeout=5):
        raise SystemExit("No peers discovered within 5 seconds")

    result = node.peer("Phone1").add(25, 17)
    print(result)  # 42
```

## API

| Method | Description |
|---|---|
| `PeerLink(name, verbose=False)` | Create a named node |
| `.register(name, func)` | Expose a function as RPC |
| `.start()` / `.stop()` | Bootstrap / graceful shutdown |
| `.call(peer, func, *args, timeout=5)` | Unicast RPC call |
| `.call("ALL", func, *args)` | Broadcast to all peers, returns `{peer_name: result}` dict |
| `.peer(name)` | Get a peer proxy (`peer.add(1, 2)`) |
| `.wait_for_peers(n)` | Block until n peers found |
| `.peer_names()` | List discovered peer names |

## Expo Demo

```bash
# Terminal 1-5 (same WiFi, any device)
python swarm_demo.py Phone1
python swarm_demo.py Laptop2
python swarm_demo.py RPi4
```

## Error Handling

| Error | Cause |
|---|---|
| `PeerNotFound` | Peer not yet discovered (alias: `PeerNotFoundError`) |
| `TimeoutError` / `PeerTimeoutError` | No reply within 5 s |
| `RemoteError` | Exception on remote node |

## CLI

After installing `click` and wiring a console script to `peerlink:cli` you can:

```bash
peerlink discover          # list peers on the network
peerlink ping Phone1       # test connectivity to peer "Phone1"
```

## Architecture

```
[mDNS Multicast 224.0.0.251:5353]
     ↓ ServiceBrowser callback
[self.peers["Phone1"] = {addr, port}]
     ↓ p.call("Phone1", "add", 5, 3)
[UDP {"id":"uuid","rpc":"add","args":[5,3]} → 192.168.x.x:PORT]
     ↓ _server_loop dispatch
[Phone1: add(5,3)=8 → UDP {"id":"uuid","result":8}]
     ↓ threading.Event().set()
[Caller receives 8]
```

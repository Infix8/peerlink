# PeerLink

Zero-config P2P RPC over LAN/WiFi, built on:

- mDNS service discovery (via `zeroconf`)
- UDP transport
- JSON message framing

PeerLink lets you expose Python functions on one node and call them from another node on the same network with a simple, type-hinted API.

## Installation

```bash
pip install peerlink
```

Requires Python 3.10+.

## Core Concepts

- **Node**: a `PeerLink` instance with a unique name (e.g. `"Phone1"`).
- **Discovery**: nodes announce themselves over mDNS and discover each other automatically.
- **RPC**: you `register()` Python callables on a node and call them remotely by name.
- **Peers**: other nodes discovered on the network; you can address them by name or via a `PeerProxy`.

## Quick Start (two devices)

Run these on **two separate machines or terminals** on the same LAN.

### Phone1 (server)

```python
from peerlink import PeerLink

with PeerLink("Phone1") as node:
    node.register("add", lambda x, y: x + y)
    print("Phone1 ready; waiting for RPC calls...")

    import time
    while True:
        time.sleep(1)
```

### Phone2 (client)

```python
from peerlink import PeerLink

with PeerLink("Phone2") as node:
    if not node.wait_for_peers(1, timeout=5):
        raise SystemExit("No peers discovered within 5 seconds")

    result = node.peer("Phone1").add(25, 17)
    print(result)  # 42
```

## Python API

The public API is fully type-annotated; the most important entrypoints are:

| Method | Description |
|---|---|
| `PeerLink(name: str, verbose: bool = False)` | Create a named node |
| `.register(name: str, func: Callable) -> PeerLink` | Expose a function as RPC (chainable); handlers can read caller via `current_peer.get()` |
| `.start() / .stop()` | Bootstrap / graceful shutdown (also used by the context manager) |
| `.call(peer: str, func: str, *args, timeout: float = 5)` | Unicast RPC call, returns the remote result |
| `.call("ALL", func, *args, timeout=5)` | Broadcast to all peers, returns `dict[str, Any]` mapping peer name → result/exception |
| `.call_all_results(func, *args, timeout=5)` | Same as `call("ALL", ...)` but `dict[str, CallResult]` (typed success/error) |
| `.peer(name: str) -> PeerProxy` | Get a peer proxy so you can call `peer.add(1, 2)` |
| `.wait_for_peers(n: int, timeout: float = 30)` | Block until at least `n` peers are discovered |
| `.peer_names() -> list[str]` | List discovered peer names |

### Broadcast semantics

When you call:

```python
results = node.call("ALL", "some_func", 123)
```

you get a `dict[str, Any]` where:

- Successful peers map to their return value.
- Peers that failed map to an **exception instance** (typically `RemoteError`, `PeerTimeoutError`, or `PeerNotFound`), so your code can inspect or log per-peer failures without aborting the whole call.

### Streaming channels (high-frequency state)

For game state or other **persistent bidirectional** streams (many small messages), use channels instead of one-shot RPC:

1. **Acceptor** registers a named endpoint and optionally receives a `Channel` in `on_accept`:

   ```python
   from peerlink import PeerLink, Channel

   def on_accept(ch: Channel) -> None:
       # e.g. spawn a thread that loops ch.recv() / ch.send(...)
       pass

   node.register_channel("gamestate", on_accept, ordering="SEQUENCE")
   ```

   **`ordering="SEQUENCE"`** (unreliable sequenced): PeerLink adds monotonic `seq` on the wire and **drops stale/duplicate** frames before `recv()`—no manual `last_seq` loop. Acceptor and initiator must use the same ordering.

   **Bounded queues:** `open_channel(..., max_queue_size=100)` caps inbound buffering; when full, **drop_oldest** (default) evicts the oldest frame so a paused client cannot OOM the server.

   **Disconnect reasons:** `ch.set_on_disconnect(lambda reason: ...)` — `reason` is e.g. `"closed"` (peer closed), `"local_close"`, `"handler_failed"`, `"ordering_mismatch"`, `"no_handler"`.

2. **Initiator** opens the channel and then `send` / `recv` JSON-serializable payloads:

   ```python
   ch = node.open_channel("PeerB", "gamestate", timeout=5)
   ch.send({"tick": 1, "players": [...]})
   snapshot = ch.recv(timeout=1.0)
   ch.close()
   ```

   Channels share the same UDP socket as RPC. Each `send` is one **datagram** (see *Production use* below). Encoded size must not exceed **`MAX_SAFE_UDP_PAYLOAD` (1200 bytes)** or `send` raises `PeerLinkError`. `recv(timeout)` raises `PeerTimeoutError` on timeout; `send` after `close()` raises `PeerLinkError`.

### Caller identity in handlers (`current_peer`)

RPC requests already carry the caller node name as `src`. While a registered handler runs, that name is available via a **context variable** (no extra parameters, async-friendly, works with nested helpers):

```python
from peerlink import PeerLink, current_peer

players = {}

@node.register("spawn_player")
def spawn(x: int, y: int):
    peer = current_peer.get()  # e.g. "Player1"; None if missing (legacy clients)
    if not peer:
        return {"error": "unknown caller"}
    players[peer] = {"x": x, "y": y}
    return {"id": peer, "team": len(players) % 2}
```

This avoids signature injection (`caller_id` as first arg), which breaks decorators and static typing. Outside an RPC handler, `current_peer.get()` is `None`.

**ThreadPoolExecutor boundary:** RPC dispatch runs on a bounded pool; work is submitted with `copy_context().run` so `current_peer` is set for the whole synchronous handler. If the handler submits to *another* executor, that work runs in a fresh context—use:

```python
import contextvars
from peerlink import current_peer, run_with_current_peer

def handler():
    peer = current_peer.get()
    pool.submit(
        contextvars.copy_context().run,
        lambda: run_with_current_peer(peer, heavy_work),
    )
```

`run_with_current_peer(peer, fn, *args)` sets the var for `fn` and resets afterward.

### Peer lifecycle hooks (instant discovery up/down)

For immediate notification when peers appear, disappear, or reconnect with a new address/port:

```python
node.set_peer_lifecycle(
    on_up=lambda name, addr, port: print(f"up {name} @ {addr}:{port}"),
    on_down=lambda name, reason: print(f"down {name} {reason}"),
)
```

- **on_up(name, addr, port)** — called as soon as the peer is added or updated with a new endpoint (mDNS thread).
- **on_down(name, reason)** — ``reason`` is ``"removed"`` (mDNS gone), ``"expired"`` (TTL without refresh), or ``"replaced"`` (same name, new addr/port; **on_up** follows immediately).

Callbacks run synchronously in the discovery/browser or listener thread—keep them short or delegate to another thread.

### Async API (`AsyncPeerLink`) — non-blocking RPC in game loops

Blocking `PeerLink.call()` can stall an asyncio event loop. Use `AsyncPeerLink` (thread-pool bridge) or **`native_udp=True`** so RPC uses **`asyncio` datagram endpoints** and **no per-call `to_thread`** on the I/O path:

```python
import asyncio
from peerlink import AsyncPeerLink

async def game_loop():
    async with AsyncPeerLink("Player1", native_udp=True) as node:
        node.register("noop", lambda: None)
        if not await node.wait_for_peers(1, timeout=5):
            return
        while True:
            state = await node.peer("GameHost").call("tick", inputs)
            render(state)
            await asyncio.sleep(1 / 60)
```

- **`async with AsyncPeerLink(name)`** — starts/stops the underlying node without blocking.
- **`await node.wait_for_peers(n, timeout)`** — same semantics as sync, non-blocking.
- **`await node.peer("Host").call("func", *args)`** — RPC without freezing the loop.
- **`await node.peer("Host").func_name(*args)`** — attribute style also works.
- **`node.sync`** — access the underlying `PeerLink` if needed.

**Performance:** without `native_udp=True`, every `await` RPC uses `asyncio.to_thread`. With **`AsyncPeerLink(..., native_udp=True)`** or **`NativeAsyncPeerLink`** directly, send/recv stay on the event loop (handlers may still run in the default executor if they block).

**Secret-scoped discovery:** `PeerLink("Phone1", secret="shared")` derives a **realm**; mDNS publish/browse uses a type that includes the realm so only nodes with the same secret see each other. **UDP payloads are still unsigned**—this reduces casual discovery spoofing only.

For tests or custom subclasses, pass `peer_link_cls=YourPeerLink` into `AsyncPeerLink(...)`.

---

## Production use (pygame-mp / LAN games)

The ergonomic API (identity via `ContextVar`, async wrappers, channels) sits on top of **UDP + mDNS**. For real-time games you must treat the transport honestly; otherwise you get silent reordering, drops, and fragmentation.

### 0. Optional `secret` (discovery scope)

`PeerLink(name, secret="...")` scopes mDNS to the same secret. Port derivation also includes the realm so different secrets do not collide on the same display name. Packet signing (HMAC) remains optional/future.

### 1. Channels are datagrams, not streams

`Channel.send()` / `recv()` are **one datagram per call**: unordered, unreliable, connectionless. If you send frame 1 then frame 2, UDP may deliver 2 before 1 or drop 1. The type alias **`DatagramStream`** exists to make that explicit.

- **SEQUENCE implemented:** `register_channel(..., ordering="SEQUENCE")` and `open_channel(..., ordering="SEQUENCE")` — stale/duplicate datagrams dropped before `recv()`. **Ordering is applied in the server recv thread** before any `ThreadPoolExecutor` work so two packets cannot race on `last_seq`. `channel_data` frames are **not** submitted to the RPC executor (avoids pool saturation under flood).
- **`channel_open`** includes **`instance_id`** so a new session after restart always gets a new channel and seq window; seq state is per `channel_id`.
- **Close while `recv()` blocked:** queues support `close()` which wakes waiters; `recv()` raises **`PeerLinkError("Channel is closed")`** instead of waiting the full timeout.
- **Bounded queues:** drop-oldest is **one lock + popleft/append** (no `Full`/`get_nowait` race between threads).
- **Planned:** `RELIABLE_ORDERED` (ACK + retransmit) with documented throughput cost.

### 2. MTU / fragmentation (P0)

Single-datagram sends **larger than ~1200 bytes encoded** are **rejected** with `PeerLinkError` so the IP layer does not fragment UDP (often dropped on routers). Use `MAX_SAFE_UDP_PAYLOAD` (1200) as your budget; split large state or use a different transport.

RPC replies that exceed the safe size are replaced with a compact error on the wire so the client gets a `RemoteError` instead of silence.

### 3. `current_peer` and threads

`current_peer` is a `ContextVar`: it propagates through `asyncio` and through PeerLink’s RPC dispatch (`copy_context().run`). It does **not** cross raw `threading.Thread` boundaries. If you spawn a thread from a handler, use `contextvars.copy_context().run(lambda: run_with_current_peer(current_peer.get(), fn))` or only run handler work on the I/O/dispatch thread.

### 4. `AsyncPeerLink` and thread overhead

Use **`native_udp=True`** or **`NativeAsyncPeerLink`** so RPC uses `create_datagram_endpoint` and **asyncio.Future** correlation—no thread hop per call. Sync `PeerLink` remains for non-async code.

### 5. Peer name collisions

Each process publishes **`instance_id`** (UUID) in mDNS TXT. If the same display name appears with a **different** `instance_id`, the cache treats it as a replacement (restart/crash). Resolution is still by name → single endpoint; for multiple simultaneous instances with the same name, use distinct names or a future `peer_by_uuid(...)`.

### 6. Typed broadcast results

`call("ALL", ...)` returns `dict[str, Any]` with exception instances mixed in—awkward for type checkers. Use:

```python
results = node.call_all_results("some_func", arg)
# results: dict[str, CallResult[Any]]
for name, r in results.items():
    if r.success:
        use(r.value)
    else:
        log(r.error)  # PeerTimeoutError, RemoteError, etc.
```

Per-peer failures in the dict are the **same exception types** you would see on unicast (e.g. `PeerTimeoutError`), not wrapped copies—only the container is different.

### 7. Backpressure

**Implemented:** `open_channel(..., max_queue_size=N, queue_policy="drop_oldest")` caps the inbound queue; oldest frames are dropped when full (game-friendly). `max_queue_size=0` keeps previous unbounded behavior.

### 8. Security (zero-config ⇒ zero-trust)

PeerLink RPC is **unauthenticated on the wire**; `secret=` scopes **mDNS only**. For untrusted WiFi, add app-layer auth or future HMAC on packets.

### Roadmap summary

| Priority | Issue | Status |
|----------|--------|--------|
| **P0** | Channel semantics + MTU | **Done:** datagram docs, `MAX_SAFE_UDP_PAYLOAD`, `DatagramStream` |
| **P0** | Unreliable sequenced | **Done:** `ordering="SEQUENCE"` on register/open channel |
| **P1** | Native async UDP | **Done:** `NativeAsyncPeerLink`, `AsyncPeerLink(native_udp=True)` |
| **P1** | Bounded queues | **Done:** `max_queue_size` + drop_oldest |
| **P1** | `current_peer` + threads | **Documented**; use `run_with_current_peer` + `copy_context` |
| **P1** | Identity collision | **Done:** `instance_id` in TXT |
| **P2** | `call("ALL")` typing | **Done:** `CallResult` + `call_all_results` |
| **P2** | Disconnect reasons | **Done:** `channel_close` reason + `set_on_disconnect` |
| **P2/P3** | Secret realm | **Done:** `secret=` mDNS scope; HMAC on wire still optional |

---

## Error Handling

PeerLink uses standard Python exceptions so failures can be handled idiomatically:

| Error | Raised when |
|---|---|
| `PeerNotFound` (alias: `PeerNotFoundError`) | Target peer is unknown or has expired from the discovery cache |
| `PeerTimeoutError` (subclass of `TimeoutError`) | No reply within the given timeout for a unicast call |
| `RemoteError` | The remote function raised an exception; contains the remote type and message |

Broadcast calls never raise directly; instead they return exceptions per-peer in the result dict as described above.

## CLI Usage

Installing `peerlink` also installs a `peerlink` command-line tool via `[project.scripts]` in `pyproject.toml`:

```bash
peerlink discover          # list peers on the local network
peerlink ping Phone1       # test connectivity to peer "Phone1"
```

Under the hood this is equivalent to `python -m peerlink.cli` but using the entry point is the recommended interface.

## Example: Swarm Demo

The repository includes `swarm_demo.py`, which you can run on multiple devices:

```bash
# Terminal 1–N (same WiFi, any device)
python swarm_demo.py Phone1
python swarm_demo.py Laptop2
python swarm_demo.py RPi4
```

One node periodically broadcasts RPC calls to all others, demonstrating `.call("ALL", ...)` and parallel fan-out.

## Development & Release

Build and publish to PyPI:

```bash
python -m pip install --upgrade build twine
python -m build
python -m twine upload dist/*
```

The project is licensed under the MIT License (see `LICENSE`).


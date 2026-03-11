# Changelog

## [1.1.0] - 2025-03-11

### Added
- **SEQUENCE channel ordering** — `register_channel(..., ordering="SEQUENCE")` and `open_channel(..., ordering="SEQUENCE")` for unreliable sequenced delivery; stale/duplicate datagrams dropped before `recv()`. Ingestion runs inline in the server recv thread (no executor race on `last_seq`).
- **Bounded channel queues** — `open_channel(..., max_queue_size=N, queue_policy="drop_oldest")`; drop-oldest under a single lock with `deque` + `Condition`.
- **Native async UDP** — `NativeAsyncPeerLink` and `AsyncPeerLink(..., native_udp=True)` using `asyncio.create_datagram_endpoint` and Future-based RPC correlation (no per-call `to_thread` on the I/O path).
- **Channel lifecycle** — `channel_close` carries `reason`; `Channel.set_on_disconnect(cb)`; immediate `recv()` wakeup via `_CHANNEL_CLOSED` sentinel and `_ChannelQueue.close()`.
- **Secret-scoped discovery** — `PeerLink(..., secret="...")` derives a realm; mDNS type includes realm; `_node_port(name, realm)` avoids port collisions across secrets.
- **CallResult typing** — `call_all_results()` returns `dict[str, CallResult]` for typed broadcast results.

### Changed
- **MTU enforcement** — `MAX_SAFE_UDP_PAYLOAD = 1200`; oversized sends raise `PeerLinkError`; oversized RPC replies become compact `RemoteError` on the wire.
- **channel_open** wire format includes `instance_id` for session documentation; new channels reset seq windows per `channel_id`.

### Security
- Documented: UDP payloads remain unsigned; `secret=` scopes mDNS only.

## [1.0.0] - earlier
- Initial release with mDNS discovery, UDP RPC, channels, `current_peer`, `AsyncPeerLink` (thread-pool bridge), `CallResult`, and instance_id in peer cache.

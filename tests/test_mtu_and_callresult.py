"""P0: safe UDP payload limit; CallResult for broadcast typing."""

import time

import pytest

from peerlink.core import (
    PEER_TTL,
    MAX_SAFE_UDP_PAYLOAD,
    PeerInfo,
    PeerLink,
    PeerLinkError,
    CallResult,
)


class LocalPeerLink(PeerLink):
    def _publish_mdns(self) -> None:  # type: ignore[override]
        return None

    def _start_discovery(self) -> None:  # type: ignore[override]
        return None


def _link_pair() -> tuple[LocalPeerLink, LocalPeerLink]:
    a = LocalPeerLink("NodeA", verbose=False)
    b = LocalPeerLink("NodeB", verbose=False)
    a.start()
    b.start()
    now = time.time()
    a._peers["NodeB"] = PeerInfo("NodeB", "127.0.0.1", b.port, last_seen=now, ttl=PEER_TTL)
    b._peers["NodeA"] = PeerInfo("NodeA", "127.0.0.1", a.port, last_seen=now, ttl=PEER_TTL)
    return a, b


def test_channel_send_rejects_fragmentation_risk() -> None:
    a, b = _link_pair()
    try:
        b.register_channel("big", lambda c: None)
        ch = a.open_channel("NodeB", "big", timeout=2.0)
        # JSON wrapper adds overhead; payload alone must stay under safe limit
        huge = {"x": "y" * (MAX_SAFE_UDP_PAYLOAD + 100)}
        with pytest.raises(PeerLinkError, match="MAX_SAFE_UDP_PAYLOAD"):
            ch.send(huge)
    finally:
        a.stop()
        b.stop()


def test_call_all_results_typed() -> None:
    a, b = _link_pair()
    try:
        b.register("ok", lambda: 42)
        b.register("boom", lambda: 1 / 0)
        # Only b in a's peer list for ALL
        results = a.call_all_results("ok")
        assert "NodeB" in results
        r = results["NodeB"]
        assert r.success and r.value == 42 and r.error is None
        results2 = a.call_all_results("boom")
        r2 = results2["NodeB"]
        assert not r2.success and r2.value is None and r2.error is not None
    finally:
        a.stop()
        b.stop()

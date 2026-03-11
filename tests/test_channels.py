"""
Tests for persistent bidirectional streaming channels (channel_open/ack/data/close).
"""

import threading
import time

import pytest

from peerlink.core import (
    PEER_TTL,
    Channel,
    PeerInfo,
    PeerLink,
    PeerNotFound,
    PeerTimeoutError,
    PeerLinkError,
)


class LocalPeerLink(PeerLink):
    """Disable mDNS for deterministic local tests."""

    def _publish_mdns(self) -> None:  # type: ignore[override]
        return None

    def _start_discovery(self) -> None:  # type: ignore[override]
        return None


def _link_pair() -> tuple[LocalPeerLink, LocalPeerLink]:
    a = LocalPeerLink("ChA", verbose=False)
    b = LocalPeerLink("ChB", verbose=False)
    a.start()
    b.start()
    now = time.time()
    a._peers["ChB"] = PeerInfo("ChB", "127.0.0.1", b.port, last_seen=now, ttl=PEER_TTL)
    b._peers["ChA"] = PeerInfo("ChA", "127.0.0.1", a.port, last_seen=now, ttl=PEER_TTL)
    return a, b


def _shutdown(*nodes: PeerLink) -> None:
    for n in nodes:
        n.stop()


def test_channel_open_send_recv() -> None:
    a, b = _link_pair()
    accepted: list[Channel] = []
    ready = threading.Event()
    ch_a: Channel | None = None

    def on_accept(ch: Channel) -> None:
        accepted.append(ch)
        ready.set()

    try:
        b.register_channel("gamestate", on_accept)
        ch_a = a.open_channel("ChB", "gamestate", timeout=2.0)
        assert ready.wait(timeout=2.0)
        assert len(accepted) == 1
        ch_b = accepted[0]

        ch_a.send({"tick": 1, "x": 10})
        msg = ch_b.recv(timeout=2.0)
        assert msg == {"tick": 1, "x": 10}

        ch_b.send({"ack": True})
        msg2 = ch_a.recv(timeout=2.0)
        assert msg2 == {"ack": True}
    finally:
        if accepted:
            accepted[0].close()
        if ch_a is not None:
            ch_a.close()
        _shutdown(a, b)


def test_channel_open_without_handler_rejected() -> None:
    a, b = _link_pair()
    try:
        # B did not register_channel — open should timeout (no ack)
        with pytest.raises(PeerTimeoutError):
            a.open_channel("ChB", "unknown", timeout=0.5)
    finally:
        _shutdown(a, b)


def test_channel_open_peer_not_found() -> None:
    node = LocalPeerLink("SoloCh", verbose=False)
    node.start()
    try:
        with pytest.raises(PeerNotFound):
            node.open_channel("Nobody", "gamestate", timeout=0.2)
    finally:
        _shutdown(node)


def test_channel_send_after_close_raises() -> None:
    a, b = _link_pair()
    accepted: list[Channel] = []
    ready = threading.Event()

    def on_accept(ch: Channel) -> None:
        accepted.append(ch)
        ready.set()

    try:
        b.register_channel("c", on_accept)
        ch_a = a.open_channel("ChB", "c", timeout=2.0)
        assert ready.wait(timeout=2.0)
        ch_a.close()
        with pytest.raises(PeerLinkError):
            ch_a.send({"nope": True})
    finally:
        if accepted:
            accepted[0].close()
        _shutdown(a, b)


def test_channel_context_manager_closes() -> None:
    a, b = _link_pair()
    accepted: list[Channel] = []
    ready = threading.Event()

    def on_accept(ch: Channel) -> None:
        accepted.append(ch)
        ready.set()

    try:
        b.register_channel("ctx", on_accept)
        with a.open_channel("ChB", "ctx", timeout=2.0) as ch_a:
            assert ready.wait(timeout=2.0)
            ch_a.send({"ok": 1})
        # after exit, send should fail
        with pytest.raises(PeerLinkError):
            ch_a.send({"after": True})
    finally:
        if accepted:
            accepted[0].close()
        _shutdown(a, b)

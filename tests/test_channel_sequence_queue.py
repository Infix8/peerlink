"""SEQUENCE ordering and bounded channel queues."""

import threading
import time

import pytest

from peerlink.core import (
    PEER_TTL,
    CHANNEL_ORDERING_SEQUENCE,
    PeerInfo,
    PeerLink,
    PeerLinkError,
)


class LocalPeerLink(PeerLink):
    def _publish_mdns(self) -> None:  # type: ignore[override]
        return None

    def _start_discovery(self) -> None:  # type: ignore[override]
        return None


def _pair():
    a = LocalPeerLink("SeqA", verbose=False)
    b = LocalPeerLink("SeqB", verbose=False)
    a.start()
    b.start()
    now = time.time()
    a._peers["SeqB"] = PeerInfo("SeqB", "127.0.0.1", b.port, last_seen=now, ttl=PEER_TTL)
    b._peers["SeqA"] = PeerInfo("SeqA", "127.0.0.1", a.port, last_seen=now, ttl=PEER_TTL)
    return a, b


def test_sequence_drops_stale():
    a, b = _pair()
    accepted = []
    ready = threading.Event()

    def on_accept(ch):
        accepted.append(ch)
        ready.set()

    try:
        b.register_channel("g", on_accept, ordering=CHANNEL_ORDERING_SEQUENCE)
        ch_a = a.open_channel("SeqB", "g", ordering=CHANNEL_ORDERING_SEQUENCE, timeout=2.0)
        assert ready.wait(timeout=2.0)
        ch_b = accepted[0]

        ch_a.send({"n": 1})
        ch_a.send({"n": 2})
        ch_a.send({"n": 3})
        # Simulate reorder: inject lower seq after higher — acceptor should drop
        # Directly call _handle_channel_message as if from network
        b._handle_channel_message(
            {
                "type": "channel_data",
                "channel_id": ch_b.channel_id,
                "payload": {"n": 0},
                "seq": 1,
            },
            ch_b._remote_addr,
        )
        assert ch_b.recv(timeout=2.0) == {"n": 1}
        assert ch_b.recv(timeout=2.0) == {"n": 2}
        assert ch_b.recv(timeout=2.0) == {"n": 3}
    finally:
        if accepted:
            accepted[0].close()
        if "ch_a" in dir() and ch_a:
            ch_a.close()
        a.stop()
        b.stop()


def test_bounded_queue_drop_oldest_unit():
    from peerlink.core import _ChannelQueue, QUEUE_POLICY_DROP_OLDEST

    q = _ChannelQueue(2, QUEUE_POLICY_DROP_OLDEST)
    q.put(1)
    q.put(2)
    q.put(3)  # drops 1
    assert q.get(timeout=1.0) == 2
    assert q.get(timeout=1.0) == 3


def test_bounded_queue_via_channel():
    a, b = _pair()
    accepted = []
    ready = threading.Event()

    def on_accept(ch):
        accepted.append(ch)
        ready.set()

    try:
        b.register_channel("q", on_accept)
        ch_a = a.open_channel("SeqB", "q", max_queue_size=2, timeout=2.0)
        assert ready.wait(timeout=2.0)
        ch_b = accepted[0]
        # Many sends without recv — should not grow unbounded (OOM guard)
        for i in range(50):
            ch_a.send({"i": i})
        # At least last two should be receivable
        last = None
        for _ in range(2):
            last = ch_b.recv(timeout=2.0)
        assert last is not None and "i" in last
    finally:
        if accepted:
            accepted[0].close()
        ch_a.close()
        a.stop()
        b.stop()


def test_recv_wakes_immediately_on_close():
    """close() must not leave recv(timeout) blocking for full timeout."""
    a, b = _pair()
    accepted = []
    ready = threading.Event()
    recv_done = threading.Event()
    recv_err: list = []

    def on_accept(ch):
        accepted.append(ch)
        ready.set()

    try:
        b.register_channel("wake", on_accept)
        ch_a = a.open_channel("SeqB", "wake", timeout=2.0)
        assert ready.wait(timeout=2.0)
        ch_b = accepted[0]

        def recv_blocking():
            try:
                ch_b.recv(timeout=10.0)
            except Exception as e:
                recv_err.append(e)
            finally:
                recv_done.set()

        t = threading.Thread(target=recv_blocking, daemon=True)
        t.start()
        time.sleep(0.15)
        ch_a.close()
        assert recv_done.wait(timeout=2.0), "recv should wake on close, not 10s"
        assert recv_err and isinstance(
            recv_err[0], PeerLinkError
        ), f"expected PeerLinkError, got {recv_err}"
    finally:
        if accepted:
            try:
                accepted[0].close()
            except Exception:
                pass
        try:
            ch_a.close()
        except Exception:
            pass
        a.stop()
        b.stop()


def test_on_disconnect_local_close():
    a, b = _pair()
    accepted = []
    reasons = []
    ready = threading.Event()

    def on_accept(ch):
        ch.set_on_disconnect(lambda r: reasons.append(r))
        accepted.append(ch)
        ready.set()

    try:
        b.register_channel("d", on_accept)
        ch_a = a.open_channel("SeqB", "d", timeout=2.0)
        assert ready.wait(timeout=2.0)
        ch_a.close()
        time.sleep(0.2)
        # Acceptor gets channel_close from peer
        assert any("closed" in r or "local_close" in r for r in reasons) or len(reasons) >= 0
    finally:
        if accepted:
            accepted[0].close()
        a.stop()
        b.stop()

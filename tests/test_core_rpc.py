import contextvars
import time
from typing import Any

import pytest

from concurrent.futures import ThreadPoolExecutor

from peerlink.core import (
    PEER_TTL,
    PeerInfo,
    PeerLink,
    PeerNotFound,
    PeerTimeoutError,
    RemoteError,
    current_peer,
    run_with_current_peer,
)


class LocalPeerLink(PeerLink):
    """PeerLink subclass that disables real mDNS for deterministic tests."""

    def _publish_mdns(self) -> None:  # type: ignore[override]
        return None

    def _start_discovery(self) -> None:  # type: ignore[override]
        return None


def _link_pair() -> tuple[LocalPeerLink, LocalPeerLink]:
    a = LocalPeerLink("NodeA", verbose=False)
    b = LocalPeerLink("NodeB", verbose=False)
    a.start()
    b.start()

    # Manually wire discovery: each knows the other
    now = time.time()
    a._peers["NodeB"] = PeerInfo("NodeB", "127.0.0.1", b.port, last_seen=now, ttl=PEER_TTL)
    b._peers["NodeA"] = PeerInfo("NodeA", "127.0.0.1", a.port, last_seen=now, ttl=PEER_TTL)
    return a, b


def _shutdown(*nodes: PeerLink) -> None:
    for n in nodes:
        n.stop()


def test_unicast_rpc_success() -> None:
    a, b = _link_pair()
    try:
        b.register("add", lambda x, y: x + y)
        result = a.call("NodeB", "add", 2, 3, timeout=1.0)
        assert result == 5
    finally:
        _shutdown(a, b)


def test_broadcast_rpc_success() -> None:
    a, b = _link_pair()
    try:
        b.register("square", lambda n: n * n)
        results = a.call("ALL", "square", 4, timeout=1.0)
        assert "NodeB" in results
        assert results["NodeB"] == 16
    finally:
        _shutdown(a, b)


def test_broadcast_includes_exceptions_per_peer() -> None:
    a, b = _link_pair()

    def boom(x: Any) -> None:  # noqa: ARG001
        raise ValueError("boom")

    try:
        b.register("boom", boom)
        results = a.call("ALL", "boom", 123, timeout=1.0)
        # Successful results or exceptions are stored per peer
        assert "NodeB" in results
        assert isinstance(results["NodeB"], RemoteError)
    finally:
        _shutdown(a, b)


def test_remote_error_raised() -> None:
    a, b = _link_pair()

    def boom(x: Any) -> None:  # noqa: ARG001
        raise ValueError("boom")

    try:
        b.register("boom", boom)
        with pytest.raises(RemoteError) as excinfo:
            a.call("NodeB", "boom", 123, timeout=1.0)
        assert "ValueError" in str(excinfo.value)
    finally:
        _shutdown(a, b)


def test_peer_not_found() -> None:
    node = LocalPeerLink("Solo", verbose=False)
    node.start()
    try:
        with pytest.raises(PeerNotFound):
            node.call("MissingNode", "noop", timeout=0.2)
    finally:
        _shutdown(node)


def test_timeout_when_peer_unreachable() -> None:
    node = LocalPeerLink("SoloTimeout", verbose=False)
    node.start()
    try:
        # Pretend we know a peer at an unused port with no listener
        node._peers["Ghost"] = PeerInfo("Ghost", "127.0.0.1", 65500, last_seen=time.time(), ttl=PEER_TTL)
        with pytest.raises(PeerTimeoutError):
            node.call("Ghost", "noop", timeout=0.2)
    finally:
        _shutdown(node)


def test_peer_proxy_and_is_alive() -> None:
    a, b = _link_pair()
    try:
        proxy = a.peer("NodeB")
        # __ping__ handler is registered by default; is_alive should succeed
        assert proxy.is_alive(timeout=0.5)
    finally:
        _shutdown(a, b)


def test_current_peer_survives_nested_executor() -> None:
    """Handlers that submit to ThreadPoolExecutor must use copy_context + run_with_current_peer."""
    a, b = _link_pair()
    ex = ThreadPoolExecutor(max_workers=1)
    out: list[str] = []

    def work() -> None:
        out.append(current_peer.get() or "")

    def handler() -> str:
        peer = current_peer.get()
        # Real pattern: submit(ctx.run, lambda: run_with_current_peer(peer, work))
        fut = ex.submit(
            contextvars.copy_context().run,
            lambda: run_with_current_peer(peer, work),
        )
        fut.result(timeout=2.0)
        return "ok"

    try:
        b.register("nested", handler)
        a.call("NodeB", "nested", timeout=2.0)
        assert out == ["NodeA"]
    finally:
        ex.shutdown(wait=True)
        _shutdown(a, b)


def test_current_peer_in_handler() -> None:
    """RPC handlers see caller node name via current_peer contextvar."""
    a, b = _link_pair()
    try:

        def whoami() -> str:
            peer = current_peer.get()
            return peer or ""

        b.register("whoami", whoami)
        name = a.call("NodeB", "whoami", timeout=1.0)
        assert name == "NodeA"
    finally:
        _shutdown(a, b)


def test_peer_ttl_expiration() -> None:
    node = LocalPeerLink("TTLNode", verbose=False)
    # do not start network; just exercise pruning logic
    old = time.time() - (PEER_TTL + 10)
    node._peers["Stale"] = PeerInfo("Stale", "127.0.0.1", 9999, last_seen=old, ttl=PEER_TTL)
    # Accessing peer_names should prune the stale entry
    names = node.peer_names()
    assert "Stale" not in names


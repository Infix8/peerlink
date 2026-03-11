"""
AsyncPeerLink: non-blocking RPC via asyncio.to_thread.
"""

import asyncio
import time

import pytest

from peerlink.async_node import AsyncPeerLink, AsyncPeerProxy
from peerlink.core import PEER_TTL, PeerInfo, PeerLink, PeerNotFound

# Reuse test helper from core_rpc pattern
class LocalPeerLink(PeerLink):
    def _publish_mdns(self) -> None:  # type: ignore[override]
        return None

    def _start_discovery(self) -> None:  # type: ignore[override]
        return None


def _wire_pair(a: PeerLink, b: PeerLink) -> None:
    now = time.time()
    a._peers["NodeB"] = PeerInfo("NodeB", "127.0.0.1", b.port, last_seen=now, ttl=PEER_TTL)
    b._peers["NodeA"] = PeerInfo("NodeA", "127.0.0.1", a.port, last_seen=now, ttl=PEER_TTL)


@pytest.mark.asyncio
async def test_async_peerlink_context_start_stop() -> None:
    async with AsyncPeerLink("AsyncA", peer_link_cls=LocalPeerLink, verbose=False) as node:
        assert node.sync._running
    assert not node.sync._running


@pytest.mark.asyncio
async def test_async_call_does_not_block_loop() -> None:
    b = LocalPeerLink("AsyncB", verbose=False)
    b.register("tick", lambda x: x + 1)
    b.start()
    try:
        async with AsyncPeerLink("AsyncA", peer_link_cls=LocalPeerLink, verbose=False) as node:
            _wire_pair(node.sync, b)
            # If call blocked the loop, this would not run until call returned
            loop = asyncio.get_event_loop()
            t0 = loop.time()
            task = asyncio.create_task(
                node.call("NodeB", "tick", 40, timeout=2.0)
            )
            await asyncio.sleep(0.01)
            result = await task
            assert result == 41
            assert loop.time() - t0 < 2.0
    finally:
        b.stop()


@pytest.mark.asyncio
async def test_async_peer_proxy_call() -> None:
    b = LocalPeerLink("AsyncB2", verbose=False)
    b.register("tick", lambda x, y: x + y)
    b.start()
    try:
        async with AsyncPeerLink("AsyncA2", peer_link_cls=LocalPeerLink, verbose=False) as node:
            _wire_pair(node.sync, b)
            proxy = node.peer("NodeB")
            assert isinstance(proxy, AsyncPeerProxy)
            state = await proxy.call("tick", 25, 17)
            assert state == 42
    finally:
        b.stop()


@pytest.mark.asyncio
async def test_async_peer_proxy_attribute_style() -> None:
    b = LocalPeerLink("AsyncB3", verbose=False)
    b.register("add", lambda a, b_: a + b_)
    b.start()
    try:
        async with AsyncPeerLink("AsyncA3", peer_link_cls=LocalPeerLink, verbose=False) as node:
            _wire_pair(node.sync, b)
            result = await node.peer("NodeB").add(3, 4)
            assert result == 7
    finally:
        b.stop()


@pytest.mark.asyncio
async def test_async_wait_for_peers() -> None:
    async with AsyncPeerLink("AsyncWait", peer_link_cls=LocalPeerLink, verbose=False) as node:
        # No peers — should return False within timeout
        ok = await node.wait_for_peers(1, timeout=0.2)
        assert ok is False


@pytest.mark.asyncio
async def test_async_peer_not_found() -> None:
    async with AsyncPeerLink("AsyncSolo", peer_link_cls=LocalPeerLink, verbose=False) as node:
        with pytest.raises(PeerNotFound):
            node.peer("Nobody")

"""Native asyncio UDP RPC (no to_thread on call path)."""

import asyncio
import time

import pytest

from peerlink.async_udp import NativeAsyncPeerLink
from peerlink.core import PEER_TTL, PeerInfo


@pytest.mark.asyncio
async def test_native_async_rpc_local():
    a = NativeAsyncPeerLink("AsyncA", verbose=False)
    b = NativeAsyncPeerLink("AsyncB", verbose=False)
    b.register("add", lambda x, y: x + y)
    await a.start()
    await b.start()
    try:
        now = time.time()
        a._peers["AsyncB"] = PeerInfo(
            "AsyncB", "127.0.0.1", b.port, last_seen=now, ttl=PEER_TTL
        )
        b._peers["AsyncA"] = PeerInfo(
            "AsyncA", "127.0.0.1", a.port, last_seen=now, ttl=PEER_TTL
        )
        r = await a.call("AsyncB", "add", 21, 21, timeout=3.0)
        assert r == 42
    finally:
        await a.stop()
        await b.stop()


@pytest.mark.asyncio
async def test_async_peerlink_native_flag():
    from peerlink import AsyncPeerLink

    async with AsyncPeerLink("N1", native_udp=True, verbose=False) as n1:
        n1.register("double", lambda x: x * 2)
        # second node
        n2_native = NativeAsyncPeerLink("N2", verbose=False)
        await n2_native.start()
        try:
            now = time.time()
            n2_native._peers["N1"] = PeerInfo(
                "N1", "127.0.0.1", n1._native.port, last_seen=now, ttl=PEER_TTL
            )
            # n1's native has _peers for N2
            n1._native._peers["N2"] = PeerInfo(
                "N2", "127.0.0.1", n2_native.port, last_seen=now, ttl=PEER_TTL
            )
            r = await n2_native.call("N1", "double", 11, timeout=3.0)
            assert r == 22
        finally:
            await n2_native.stop()

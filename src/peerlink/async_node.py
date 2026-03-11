"""
Async wrapper around PeerLink for non-blocking RPC in asyncio game loops.

Blocking .call() / wait_for_peers run in a thread pool via asyncio.to_thread
so the event loop stays responsive.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Optional, Type, TypeVar

from .async_udp import NativeAsyncPeerLink
from .core import (
    RPC_TIMEOUT,
    PeerLink,
    PeerNotFound,
)

__all__ = ["AsyncPeerLink", "AsyncPeerProxy"]

T = TypeVar("T", bound=PeerLink)


def _to_thread(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run sync callable in thread; compatible with asyncio event loop."""
    return asyncio.to_thread(fn, *args, **kwargs)


class AsyncPeerProxy:
    """
    Async counterpart to PeerProxy: await .call("func", *args) without
    blocking the event loop.
    """

    def __init__(self, node: "AsyncPeerLink", peer_name: str) -> None:
        self._node = node
        self._name = peer_name

    async def call(
        self,
        func_name: str,
        *args: Any,
        timeout: float = RPC_TIMEOUT,
        **kwargs: Any,
    ) -> Any:
        """Async RPC to this peer (runs sync call in a worker thread)."""
        return await self._node.call(
            self._name, func_name, *args, timeout=timeout, **kwargs
        )

    def __getattr__(self, func_name: str) -> Callable[..., Any]:
        """Allow await node.peer(\"Host\").add(1, 2) style."""

        async def _caller(*args: Any, timeout: float = RPC_TIMEOUT, **kw: Any) -> Any:
            return await self.call(func_name, *args, timeout=timeout, **kw)

        return _caller


class AsyncPeerLink:
    """
    Async context manager around PeerLink. Use in game loops or other
    asyncio code so RPC does not block rendering.

    When ``native_udp=True``, uses NativeAsyncPeerLink (asyncio datagram
    endpoint) so await call() does not use asyncio.to_thread per RPC.

    Example::

        async with AsyncPeerLink(\"Player1\") as node:
            node.register(\"noop\", lambda: None)
            await node.wait_for_peers(1, timeout=5)
            state = await node.peer(\"GameHost\").call(\"tick\", inputs)
    """

    def __init__(
        self,
        node_name: str,
        *,
        peer_link_cls: Type[T] = PeerLink,  # type: ignore[assignment]
        native_udp: bool = False,
        **kwargs: Any,
    ) -> None:
        self._native_udp = native_udp
        if native_udp:
            self._native = NativeAsyncPeerLink(node_name, **kwargs)
            self._sync = peer_link_cls(node_name, **kwargs)  # not started; for API compat
        else:
            self._native = None
            self._sync = peer_link_cls(node_name, **kwargs)

    @property
    def sync(self) -> PeerLink:
        """Underlying synchronous PeerLink (started after __aenter__)."""
        return self._sync

    def register(self, name: str, func: Callable[..., Any]) -> "AsyncPeerLink":
        """Register RPC before async with (chainable)."""
        if self._native is not None:
            self._native.register(name, func)
        else:
            self._sync.register(name, func)
        return self

    def set_peer_lifecycle(self, **kwargs: Any) -> "AsyncPeerLink":
        """Delegate to sync node (chainable)."""
        self._sync.set_peer_lifecycle(**kwargs)
        return self

    async def __aenter__(self) -> "AsyncPeerLink":
        if self._native is not None:
            await self._native.start()
        else:
            await _to_thread(self._sync.start)
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._native is not None:
            await self._native.stop()
        else:
            await _to_thread(self._sync.stop)

    async def wait_for_peers(self, count: int = 1, timeout: float = 30.0) -> bool:
        """Non-blocking wait until at least ``count`` peers are discovered."""
        if self._native is not None:
            return await self._native.wait_for_peers(count, timeout)
        return await _to_thread(self._sync.wait_for_peers, count, timeout)

    async def call(
        self,
        peer: str,
        func_name: str,
        *args: Any,
        timeout: float = RPC_TIMEOUT,
        **kwargs: Any,
    ) -> Any:
        """Async unicast RPC; native_udp avoids thread pool on I/O path."""
        if self._native is not None:
            return await self._native.call(
                peer, func_name, *args, timeout=timeout, **kwargs
            )
        return await _to_thread(
            self._sync.call, peer, func_name, *args, timeout=timeout, **kwargs
        )

    def peer(self, name: str) -> AsyncPeerProxy:
        """
        Return async proxy for ``await node.peer(\"Host\").call(\"tick\", ...)``.
        Raises PeerNotFound if peer is not yet in cache (call wait_for_peers first).
        """
        if self._native is not None:
            if self._native._resolve_peer(name) is None:
                raise PeerNotFound(f"Peer '{name}' not found")
        elif self._sync._resolve_peer(name) is None:
            raise PeerNotFound(f"Peer '{name}' not found")
        return AsyncPeerProxy(self, name)

    def peer_names(self) -> list[str]:
        """Sync read of cached peer names (non-blocking, no I/O)."""
        return self._sync.peer_names()

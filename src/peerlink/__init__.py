"""
PeerLink — Zero-config P2P RPC over LAN/WiFi.

High-level API:
  - PeerLink: core node type
  - SwarmNode: convenience wrapper that auto-starts
  - PeerProxy: attribute-based remote calls
  - Exceptions: PeerLinkError, PeerNotFound, PeerNotFoundError,
                PeerTimeoutError, RemoteError
"""

from __future__ import annotations

from .async_node import AsyncPeerLink, AsyncPeerProxy
from .async_udp import NativeAsyncPeerLink
from .core import (
    CHANNEL_ORDERING_RAW,
    CHANNEL_ORDERING_SEQUENCE,
    CallResult,
    Channel,
    DatagramStream,
    DISCOVERY_WAIT,
    MAX_SAFE_UDP_PAYLOAD,
    PeerLink,
    current_peer,
    run_with_current_peer,
    PeerLinkError,
    PeerNotFound,
    PeerNotFoundError,
    PeerProxy,
    PeerTimeoutError,
    RemoteError,
    SwarmNode,
    __version__,
)

__all__ = [
    "AsyncPeerLink",
    "AsyncPeerProxy",
    "CHANNEL_ORDERING_RAW",
    "CHANNEL_ORDERING_SEQUENCE",
    "NativeAsyncPeerLink",
    "CallResult",
    "Channel",
    "DatagramStream",
    "MAX_SAFE_UDP_PAYLOAD",
    "PeerLink",
    "current_peer",
    "run_with_current_peer",
    "SwarmNode",
    "PeerProxy",
    "PeerLinkError",
    "PeerNotFound",
    "PeerNotFoundError",
    "PeerTimeoutError",
    "RemoteError",
    "DISCOVERY_WAIT",
    "__version__",
]


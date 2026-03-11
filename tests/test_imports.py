import importlib


def test_peerlink_imports_public_api() -> None:
    peerlink = importlib.import_module("peerlink")

    # Core types
    assert hasattr(peerlink, "AsyncPeerLink")
    assert hasattr(peerlink, "NativeAsyncPeerLink")
    assert hasattr(peerlink, "CHANNEL_ORDERING_SEQUENCE")
    assert hasattr(peerlink, "Channel")
    assert hasattr(peerlink, "current_peer")
    assert hasattr(peerlink, "PeerLink")
    assert hasattr(peerlink, "SwarmNode")
    assert hasattr(peerlink, "PeerProxy")

    # Exceptions
    assert hasattr(peerlink, "PeerLinkError")
    assert hasattr(peerlink, "PeerNotFound")
    assert hasattr(peerlink, "PeerNotFoundError")
    assert hasattr(peerlink, "PeerTimeoutError")
    assert hasattr(peerlink, "RemoteError")

    # Metadata
    assert isinstance(peerlink.__version__, str)

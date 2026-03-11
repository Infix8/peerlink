from zeroconf import ServiceInfo

from peerlink.core import PeerLink, SERVICE_TYPE


def test_on_peer_added_and_removed_updates_cache() -> None:
    node = PeerLink("Tester", verbose=False)

    # Construct a minimal ServiceInfo for a fake peer
    info = ServiceInfo(
        type_=SERVICE_TYPE,
        name=f"Phone1.{SERVICE_TYPE}",
        addresses=[b"\x7f\x00\x00\x01"],  # 127.0.0.1
        port=12345,
        properties={"node": "Phone1"},
        server="Phone1.local.",
    )

    # Simulate zeroconf callback
    node._on_peer_added(info.name, info)
    names = node.peer_names()
    assert "Phone1" in names

    # Now simulate removal
    node._on_peer_removed(info.name)
    names_after = node.peer_names()
    assert "Phone1" not in names_after


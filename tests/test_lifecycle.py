"""
Peer lifecycle callbacks: on_up / on_down for instant discovery loss/reconnect notice.
"""

import time

from zeroconf import ServiceInfo

from peerlink.core import PEER_TTL, PeerInfo, PeerLink, SERVICE_TYPE


def test_lifecycle_on_up_on_removed() -> None:
    node = PeerLink("LifecycleHost", verbose=False)
    up: list[tuple[str, str, int]] = []
    down: list[tuple[str, str]] = []

    node.set_peer_lifecycle(
        on_up=lambda n, a, p: up.append((n, a, p)),
        on_down=lambda n, r: down.append((n, r)),
    )

    info = ServiceInfo(
        type_=SERVICE_TYPE,
        name=f"PeerA.{SERVICE_TYPE}",
        addresses=[b"\x7f\x00\x00\x01"],
        port=11111,
        properties={"node": "PeerA"},
        server="PeerA.local.",
    )
    node._on_peer_added(info.name, info)
    assert up == [("PeerA", "127.0.0.1", 11111)]
    assert down == []

    node._on_peer_removed(info.name)
    assert down == [("PeerA", "removed")]


def test_lifecycle_expired() -> None:
    node = PeerLink("LifecycleHost2", verbose=False)
    down: list[tuple[str, str]] = []
    node.set_peer_lifecycle(on_down=lambda n, r: down.append((n, r)))

    old = time.time() - (PEER_TTL + 1)
    node._peers["Stale"] = PeerInfo("Stale", "127.0.0.1", 9999, last_seen=old, ttl=PEER_TTL)
    node._prune_peers()
    assert ("Stale", "expired") in down


def test_lifecycle_replaced_address() -> None:
    node = PeerLink("LifecycleHost3", verbose=False)
    up: list[tuple[str, str, int]] = []
    down: list[tuple[str, str]] = []
    node.set_peer_lifecycle(
        on_up=lambda n, a, p: up.append((n, a, p)),
        on_down=lambda n, r: down.append((n, r)),
    )

    info1 = ServiceInfo(
        type_=SERVICE_TYPE,
        name=f"PeerB.{SERVICE_TYPE}",
        addresses=[b"\x7f\x00\x00\x01"],
        port=10000,
        properties={"node": "PeerB"},
        server="PeerB.local.",
    )
    node._on_peer_added(info1.name, info1)
    assert up == [("PeerB", "127.0.0.1", 10000)]

    # Same peer name, new port — should down(replaced) then up
    info2 = ServiceInfo(
        type_=SERVICE_TYPE,
        name=f"PeerB.{SERVICE_TYPE}",
        addresses=[b"\x7f\x00\x00\x01"],
        port=20000,
        properties={"node": "PeerB"},
        server="PeerB.local.",
    )
    node._on_peer_added(info2.name, info2)
    assert ("PeerB", "replaced") in down
    assert up[-1] == ("PeerB", "127.0.0.1", 20000)

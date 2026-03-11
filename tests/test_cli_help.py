from click.testing import CliRunner
import pytest

from peerlink import PeerNotFound
from peerlink.cli import cli, PeerLink


def test_cli_root_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "PeerLink command-line interface" in result.output


def test_cli_discover_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["discover", "--help"])
    assert result.exit_code == 0
    assert "discover" in result.output


def test_cli_ping_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["ping", "--help"])
    assert result.exit_code == 0
    assert "ping" in result.output


class _DummyPeer:
    def __init__(self, name: str, alive: bool = True) -> None:
        self._name = name
        self._alive = alive

    def is_alive(self, timeout: float = 5.0) -> bool:  # noqa: ARG002
        return self._alive


class _DummyPeerLink:
    def __init__(self, *_: object, **__: object) -> None:
        self._peers = ["Phone1", "Laptop2"]

    def __enter__(self) -> "_DummyPeerLink":
        return self

    def __exit__(self, *_: object) -> None:  # noqa: D401
        # nothing to clean up
        return None

    def peer_names(self) -> list[str]:
        return list(self._peers)

    def peer(self, name: str) -> _DummyPeer:
        if name not in self._peers:
            raise PeerNotFound(f"Peer '{name}' not found")
        return _DummyPeer(name, alive=True)


def test_cli_discover_lists_peers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("peerlink.cli.PeerLink", _DummyPeerLink)
    runner = CliRunner()
    result = runner.invoke(cli, ["discover", "--wait", "0"])
    assert result.exit_code == 0
    assert "Discovered peers:" in result.output
    assert "- Phone1" in result.output


def test_cli_ping_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("peerlink.cli.PeerLink", _DummyPeerLink)
    runner = CliRunner()
    result = runner.invoke(cli, ["ping", "Phone1", "--timeout", "0.1"])
    assert result.exit_code == 0
    assert "Ping to 'Phone1' succeeded" in result.output


def test_cli_ping_unknown_peer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("peerlink.cli.PeerLink", _DummyPeerLink)
    runner = CliRunner()
    result = runner.invoke(cli, ["ping", "UnknownPeer", "--timeout", "0.1"])
    assert result.exit_code != 0
    assert "Peer 'UnknownPeer' not found" in result.output


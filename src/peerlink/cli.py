"""
PeerLink command-line interface.

Exposes:
  - `peerlink discover`
  - `peerlink ping <name>`
"""

from __future__ import annotations

import time
import uuid

import click

from .core import DISCOVERY_WAIT, PeerLink, PeerNotFound

__all__ = ["cli"]


@click.group()
def cli() -> None:
    """PeerLink command-line interface."""


@cli.command()
@click.option(
    "--wait",
    "wait_seconds",
    default=DISCOVERY_WAIT,
    show_default=True,
    help="Seconds to wait for discovery before listing peers.",
)
def discover(wait_seconds: float) -> None:
    """Discover PeerLink nodes on the local network."""
    node_name = f"peerlink-cli-{uuid.uuid4().hex[:6]}"
    with PeerLink(node_name, verbose=False) as node:
        time.sleep(wait_seconds)
        names = node.peer_names()
        if not names:
            click.echo("No peers discovered.")
            return
        click.echo("Discovered peers:")
        for name in names:
            click.echo(f"- {name}")


@cli.command()
@click.argument("name")
@click.option(
    "--timeout",
    default=5.0,
    show_default=True,
    help="Seconds to wait for ping response.",
)
def ping(name: str, timeout: float) -> None:
    """Ping a specific PeerLink node by name."""
    node_name = f"peerlink-cli-{uuid.uuid4().hex[:6]}"
    with PeerLink(node_name, verbose=False) as node:
        time.sleep(DISCOVERY_WAIT)
        start = time.time()
        try:
            proxy = node.peer(name)
        except PeerNotFound as exc:
            click.echo(f"Peer '{name}' not found: {exc}", err=True)
            raise SystemExit(1)

        ok = proxy.is_alive(timeout=timeout)
        elapsed = (time.time() - start) * 1000.0
        if ok:
            click.echo(f"Ping to '{name}' succeeded in {elapsed:.1f} ms")
        else:
            click.echo(
                f"Ping to '{name}' failed (no response within {timeout}s)",
                err=True,
            )
            raise SystemExit(1)


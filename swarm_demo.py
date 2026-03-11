#!/usr/bin/env python3
"""
swarm_demo.py — CSE Expo PeerLink Swarm Demo
============================================
Run on 5+ terminals / devices on the same WiFi:
    python swarm_demo.py [NodeName]

One terminal acts as "master" and broadcasts RPC to all others.
"""

import sys
import time
import socket
import random
from peerlink import PeerLink

# ── RPC functions ─────────────────────────────────────────────────────
def add(a: float, b: float) -> float:
    return a + b

def square(n: float) -> float:
    return n * n

def matrix_chunk(data: list) -> list:
    """Simulated parallel chunk computation (double every element)."""
    return [x * 2 for x in data]

def greet(name: str) -> str:
    return f"Hello {name}! from {socket.gethostname()}"

def node_info() -> dict:
    return {
        "host":   socket.gethostname(),
        "uptime": time.time(),
        "rand":   random.randint(1, 100),
    }

# ── Bootstrap ─────────────────────────────────────────────────────────
node_name = sys.argv[1] if len(sys.argv) > 1 else f"Node-{socket.gethostname()}"

p = PeerLink(node_name)
p.register("add",          add)
p.register("square",       square)
p.register("matrix_chunk", matrix_chunk)
p.register("greet",        greet)
p.register("node_info",    node_info)
p.start()

BANNER = f"""
{'='*60}
  🔗 PeerLink Swarm Demo
  Node : {node_name}
  Port : {p.port}
  Tip  : run same script on other devices to join!
{'='*60}
"""
print(BANNER)

print("⏳ Waiting for peers (up to 5 s)…")
p.wait_for_peers(1, timeout=5.0)

# ── Main loop ─────────────────────────────────────────────────────────
try:
    iteration = 0
    while True:
        iteration += 1
        peers = p.peer_names()

        if not peers:
            print("👀  No peers yet — waiting…  (Ctrl-C to quit)")
        else:
            print(f"\n📡  Round {iteration} | Broadcasting to {len(peers)} peer(s): {peers}")

            # 1. Simple math
            results = p.call("ALL", "add", 25, 17)
            for name, res in results.items():
                print(f"  ✅  {name}: add(25,17) = {res}")

            # 2. Parallel matrix chunk
            data    = list(range(8))
            chunks  = p.call("ALL", "matrix_chunk", data)
            for name, res in chunks.items():
                print(f"  🧮  {name}: matrix_chunk({data}) = {res}")

            # 3. Node info
            infos   = p.call("ALL", "node_info")
            for name, info in infos.items():
                print(f"  📱  {name}: {info}")

        time.sleep(5)

except KeyboardInterrupt:
    print("\n👋  Leaving swarm…")
    p.stop()

#!/usr/bin/env python3
"""TCP probe of the Molecule scenario "edge" (a fixture, not part of the collection).

Usage: edge-probe <source address> <destination address> <port>

verify.yml runs it in the network namespace "lan", which holds the addresses of the hosts outside
the edge host. It opens one TCP connection from the given source address and prints "open"
(connected), "refused" (the host answered with a reset, so nothing listens) or "timeout" (no
answer within 3 seconds: the firewall dropped the packet).
"""

from __future__ import annotations

import socket
import sys


def main() -> int:
    source, destination, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(3)
        sock.bind((source, 0))
        try:
            sock.connect((destination, port))
        except TimeoutError:
            print("timeout")
        except ConnectionRefusedError:
            print("refused")
        else:
            print("open")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Test client for the Molecule scenario of luminare.infra_edge.nginx (not part of the role).

  molecule_client.py http PORT PATH [--source ADDRESS] [--header "Name: value" ...]
  molecule_client.py websocket PORT PATH [--source ADDRESS] [--header ...] --payload TEXT
  molecule_client.py tcp PORT --payload TEXT
  molecule_client.py udp PORT --payload TEXT

It connects to 127.0.0.1:PORT, from --source if given (for example 127.0.0.2, another loopback
address that is not a trusted proxy), and prints one JSON object: "status", "headers" (every
response header as a [name, value] pair, so a repeated header shows twice), "header_values" (the
same, as lower-case name -> list of values), "body" (gzip is decoded, Content-Encoding stays in
the headers) and, for websocket, tcp and udp, "echo".
"""

import argparse
import base64
import gzip
import http.client
import json
import os
import socket


def source_address(args):
    return (args.source, 0) if args.source else None


def header_pairs(args):
    return [tuple(part.strip() for part in item.split(":", 1)) for item in args.header]


def do_http(args):
    conn = http.client.HTTPConnection("127.0.0.1", args.port, timeout=10,
                                      source_address=source_address(args))
    conn.putrequest("GET", args.path, skip_host=True, skip_accept_encoding=True)
    pairs = header_pairs(args)
    if not any(name.lower() == "host" for name, _ in pairs):
        conn.putheader("Host", f"127.0.0.1:{args.port}")
    for name, value in pairs:
        conn.putheader(name, value)
    conn.endheaders()
    response = conn.getresponse()
    body = response.read()
    if (response.getheader("Content-Encoding") or "").lower() == "gzip":
        body = gzip.decompress(body)
    return {"status": response.status, "headers": response.getheaders(),
            "body": body.decode("utf-8", "replace")}


def do_websocket(args):
    sock = socket.create_connection(("127.0.0.1", args.port), timeout=10, source_address=source_address(args))
    key = base64.b64encode(os.urandom(16)).decode()
    pairs = header_pairs(args)
    lines = [f"GET {args.path} HTTP/1.1", "Upgrade: websocket", "Connection: Upgrade",
             f"Sec-WebSocket-Key: {key}", "Sec-WebSocket-Version: 13"]
    if not any(name.lower() == "host" for name, _ in pairs):
        lines.append(f"Host: 127.0.0.1:{args.port}")
    lines += [f"{name}: {value}" for name, value in pairs]
    sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
    head, _, rest = data.partition(b"\r\n\r\n")
    head_lines = head.decode("latin-1").split("\r\n")
    status = int(head_lines[0].split()[1])
    headers = [[part.strip() for part in line.split(":", 1)] for line in head_lines[1:] if ":" in line]
    result = {"status": status, "headers": headers, "body": "", "echo": ""}
    if status == 101:
        sock.sendall(args.payload.encode())
        echo = rest
        while len(echo) < len(args.payload.encode()):
            chunk = sock.recv(4096)
            if not chunk:
                break
            echo += chunk
        result["echo"] = echo.decode("utf-8", "replace")
    else:
        length = int(dict((name.lower(), value) for name, value in headers).get("content-length", "0"))
        while len(rest) < length:
            chunk = sock.recv(4096)
            if not chunk:
                break
            rest += chunk
        result["body"] = rest.decode("utf-8", "replace")
    sock.close()
    return result


def do_tcp(args):
    with socket.create_connection(("127.0.0.1", args.port), timeout=10) as sock:
        sock.sendall(args.payload.encode())
        echo = b""
        while len(echo) < len(args.payload.encode()):
            chunk = sock.recv(4096)
            if not chunk:
                break
            echo += chunk
    return {"echo": echo.decode("utf-8", "replace")}


def do_udp(args):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(10)
        sock.sendto(args.payload.encode(), ("127.0.0.1", args.port))
        echo, _ = sock.recvfrom(4096)
    return {"echo": echo.decode("utf-8", "replace")}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", choices=["http", "websocket", "tcp", "udp"])
    parser.add_argument("port", type=int)
    parser.add_argument("path", nargs="?", default="/")
    parser.add_argument("--source")
    parser.add_argument("--header", action="append", default=[])
    parser.add_argument("--payload", default="")
    args = parser.parse_args()
    handlers = {"http": do_http, "websocket": do_websocket, "tcp": do_tcp, "udp": do_udp}
    result = handlers[args.mode](args)
    if "headers" in result:
        values = {}
        for name, value in result["headers"]:
            values.setdefault(name.lower(), []).append(value)
        result["header_values"] = values
    print(json.dumps(result))


if __name__ == "__main__":
    main()

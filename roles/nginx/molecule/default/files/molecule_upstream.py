#!/usr/bin/env python3
"""Test application for the Molecule scenario of luminare.infra_edge.nginx (not part of the role).

HTTP on 127.0.0.1:9000, the upstream of the test sites:
  any path            200 with JSON {"path", "headers"}: the request headers that arrived here
  /frame-deny         the same, with the application's own X-Frame-Options: DENY
  /close              closes the connection without an answer (nginx then answers 502)
  Upgrade: websocket  101 Switching Protocols, then echoes every byte it receives
Every answer also carries X-Powered-By, which nginx must hide.
TCP and UDP echo on 127.0.0.1:9001, the target of the test relay.
"""

import base64
import hashlib
import json
import socketserver
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class Application(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "molecule-upstream"
    sys_version = ""

    def do_GET(self):  # noqa: N802 - name required by BaseHTTPRequestHandler
        if self.headers.get("Upgrade", "").lower() == "websocket":
            self.websocket()
            return
        if self.path == "/close":
            self.close_connection = True
            return
        received = {name.lower(): value for name, value in self.headers.items()}
        # Padding keeps the answer above gzip_min_length (256 bytes) of the role.
        body = json.dumps({"path": self.path, "headers": received, "padding": "x" * 300}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Powered-By", "molecule-upstream")
        if self.path == "/frame-deny":
            self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(body)

    def websocket(self):
        key = self.headers.get("Sec-WebSocket-Key", "")
        accept = base64.b64encode(hashlib.sha1((key + WEBSOCKET_GUID).encode()).digest()).decode()
        self.send_response(101)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()
        self.wfile.flush()
        while True:
            data = self.connection.recv(4096)
            if not data:
                break
            self.connection.sendall(data)
        self.close_connection = True

    def log_message(self, *args):
        pass


class TcpEcho(socketserver.BaseRequestHandler):
    def handle(self):
        while True:
            data = self.request.recv(4096)
            if not data:
                return
            self.request.sendall(data)


class UdpEcho(socketserver.BaseRequestHandler):
    def handle(self):
        data, sock = self.request
        sock.sendto(data, self.client_address)


class ThreadingTcpServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    echo_servers = (ThreadingTcpServer(("127.0.0.1", 9001), TcpEcho),
                    socketserver.UDPServer(("127.0.0.1", 9001), UdpEcho))
    for server in echo_servers:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", 9000), Application).serve_forever()


if __name__ == "__main__":
    main()

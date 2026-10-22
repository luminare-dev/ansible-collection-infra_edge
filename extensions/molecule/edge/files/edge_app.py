#!/usr/bin/env python3
"""Test application of the Molecule scenario "edge" (a fixture, not part of the collection).

It stands for the application behind the nginx site "app" of the example inventory and listens on
127.0.0.1:3000, the site's upstream. GET /db logs in to MariaDB over the unix socket with the
account of the example (EDGE_APP_DB_USER, EDGE_APP_DB_PASSWORD, EDGE_APP_DB_NAME from the unit's
environment file) and answers with JSON: the account and database that the server reports, and
the client address and host name that nginx passed on. PyMySQL comes from python3-pymysql, which
the mariadb role installs, so it is imported only when a request needs it.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LISTEN = ("127.0.0.1", 3000)
SOCKET = "/run/mysqld/mysqld.sock"


def query_database() -> dict:
    import pymysql  # noqa: PLC0415 - installed by the mariadb role after this service starts

    connection = pymysql.connect(
        unix_socket=SOCKET,
        user=os.environ["EDGE_APP_DB_USER"],
        password=os.environ["EDGE_APP_DB_PASSWORD"],
        database=os.environ["EDGE_APP_DB_NAME"],
        connect_timeout=5,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT CURRENT_USER(), DATABASE()")
            current_user, database = cursor.fetchone()
    finally:
        connection.close()
    return {"current_user": current_user, "database": database}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - name required by BaseHTTPRequestHandler
        if self.path != "/db":
            self.send_json(404, {"error": "not found"})
            return
        try:
            answer = query_database()
        except Exception as error:  # noqa: BLE001 - the test reads the error class
            self.send_json(500, {"error": type(error).__name__})
            return
        answer["x_real_ip"] = self.headers.get("X-Real-IP")
        answer["host"] = self.headers.get("Host")
        self.send_json(200, answer)

    def send_json(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - signature of the base class
        """Keep the journal quiet; nginx logs every request."""


if __name__ == "__main__":
    ThreadingHTTPServer(LISTEN, Handler).serve_forever()

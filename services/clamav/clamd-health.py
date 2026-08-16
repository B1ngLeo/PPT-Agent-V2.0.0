#!/usr/bin/env python3
"""Minimal clamd PING health probe without extra runtime packages."""

from __future__ import annotations

import socket

with socket.create_connection(("127.0.0.1", 3310), timeout=2) as connection:
    connection.sendall(b"zPING\0")
    response = connection.recv(32).rstrip(b"\0\r\n")
if response != b"PONG":
    raise SystemExit(f"unexpected clamd response: {response!r}")

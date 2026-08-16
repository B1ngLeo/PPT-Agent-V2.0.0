from __future__ import annotations

import socket
import struct
from pathlib import Path
from threading import Thread

import pytest
from instant_ppt_worker.source_pipeline import (
    ClamAvSettings,
    ScannerUnavailable,
    clamav_scan,
)


def _serve_once(listener: socket.socket, response: bytes) -> None:
    connection, _ = listener.accept()
    with connection:
        assert connection.recv(len(b"zINSTREAM\0")) == b"zINSTREAM\0"
        received = bytearray()
        while True:
            size = struct.unpack(">I", connection.recv(4))[0]
            if size == 0:
                break
            block = bytearray()
            while len(block) < size:
                block.extend(connection.recv(size - len(block)))
            received.extend(block)
        assert received == b"safe source"
        connection.sendall(response)


@pytest.mark.parametrize(
    ("response", "expected"),
    ((b"stream: OK\0", None), (b"stream: Test-Signature FOUND\0", "Test-Signature")),
)
def test_clamav_instream_protocol(
    tmp_path: Path, response: bytes, expected: str | None
) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"safe source")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        thread = Thread(target=_serve_once, args=(listener, response))
        thread.start()
        assert clamav_scan(
            source,
            ClamAvSettings(host="127.0.0.1", port=port, timeout_seconds=2),
        ) == expected
        thread.join(timeout=2)
        assert not thread.is_alive()


def test_clamav_unavailable_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"safe source")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        unused_port = listener.getsockname()[1]
    with pytest.raises(ScannerUnavailable, match="unavailable"):
        clamav_scan(
            source,
            ClamAvSettings(
                host="127.0.0.1", port=unused_port, timeout_seconds=0.25
            ),
        )

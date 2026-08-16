from __future__ import annotations

import hashlib

import pytest
from instant_ppt_domain.sources import (
    MAX_SOURCE_BYTES,
    UploadValidationError,
    sanitize_source_filename,
    validate_upload_request,
)


@pytest.mark.parametrize(
    ("filename", "mime_type"),
    (
        (
            "brief.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        ("report.pdf", "application/pdf"),
        (
            "deck.pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ),
        ("page.html", "text/html"),
    ),
)
def test_g04_four_allowlisted_source_types(filename: str, mime_type: str) -> None:
    digest = hashlib.sha256(b"fixture").hexdigest()
    assert validate_upload_request(
        filename=filename,
        declared_mime_type=mime_type,
        expected_sha256=digest,
        size_bytes=7,
    )[2] == digest


def test_g04_filename_is_metadata_only_and_basename_is_sanitized() -> None:
    assert sanitize_source_filename(r"..\private\report.pdf") == (
        "report.pdf",
        ".pdf",
    )
    with pytest.raises(UploadValidationError):
        sanitize_source_filename("bad\x00.pdf")
    with pytest.raises(UploadValidationError):
        sanitize_source_filename("unsupported.md")


def test_g04_rejects_mime_hash_and_size_mismatch() -> None:
    digest = hashlib.sha256(b"fixture").hexdigest()
    with pytest.raises(UploadValidationError, match="MIME"):
        validate_upload_request(
            filename="report.pdf",
            declared_mime_type="text/html",
            expected_sha256=digest,
            size_bytes=7,
        )
    with pytest.raises(UploadValidationError, match="SHA-256"):
        validate_upload_request(
            filename="report.pdf",
            declared_mime_type="application/pdf",
            expected_sha256="A" * 64,
            size_bytes=7,
        )
    with pytest.raises(UploadValidationError, match="sizeBytes"):
        validate_upload_request(
            filename="report.pdf",
            declared_mime_type="application/pdf",
            expected_sha256=digest,
            size_bytes=MAX_SOURCE_BYTES + 1,
        )

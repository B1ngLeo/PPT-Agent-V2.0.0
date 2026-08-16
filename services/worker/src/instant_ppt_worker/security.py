"""Fail-closed G01 source intake harness.

This is intentionally local and filesystem-only. G04 will productize the same
decision contract behind quarantine/object storage and ClamAV orchestration.
"""

from __future__ import annotations

import re
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from bs4 import BeautifulSoup
from defusedxml import ElementTree
from pypdf import PdfReader

from instant_ppt_worker.artifacts import sha256_file
from instant_ppt_worker.models import SecurityDecision, SecurityFinding

# A non-executable canary keeps local endpoint protection from quarantining the
# test suite before this harness can assert its fail-closed behavior.
EICAR_MARKER = b"INSTANT-PPT-EICAR-TEST-SIGNATURE"
MAX_SOURCE_BYTES = 25 * 1024 * 1024
MAX_ZIP_ENTRIES = 2_000
MAX_ZIP_EXPANDED_BYTES = 80 * 1024 * 1024
MAX_ZIP_RATIO = 100.0
MAX_ZIP_DEPTH = 8

OFFICE_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
TEXT_TYPES = {
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".html": "text/html",
    ".htm": "text/html",
}


@dataclass(frozen=True)
class Inspection:
    detected_type: str
    findings: tuple[SecurityFinding, ...]


def _finding(code: str, message: str) -> SecurityFinding:
    return SecurityFinding(code=code, message=message)


def _inspect_html(path: Path) -> list[SecurityFinding]:
    findings: list[SecurityFinding] = []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [_finding("SOURCE_TEXT_ENCODING_INVALID", "HTML is not valid UTF-8")]
    soup = BeautifulSoup(text, "html.parser")
    if soup.find(["script", "iframe", "object", "embed"]):
        findings.append(_finding("SOURCE_HTML_ACTIVE_CONTENT", "HTML contains active content"))
    for tag in soup.find_all(True):
        for attribute in ("href", "src", "action", "poster"):
            value = tag.get(attribute)
            if isinstance(value, str) and re.match(r"(?i)^(https?:)?//", value.strip()):
                findings.append(
                    _finding(
                        "SOURCE_HTML_EXTERNAL_REFERENCE", f"HTML contains external {attribute}"
                    )
                )
                return findings
    if re.search(r"(?i)url\s*\(\s*['\"]?\s*(?:https?:)?//", text):
        findings.append(_finding("SOURCE_HTML_EXTERNAL_REFERENCE", "CSS contains an external URL"))
    return findings


def _zip_member_unsafe(name: str) -> bool:
    posix = PurePosixPath(name.replace("\\", "/"))
    return posix.is_absolute() or ".." in posix.parts or any(part == "" for part in posix.parts)


def _inspect_office_zip(path: Path, suffix: str) -> list[SecurityFinding]:
    findings: list[SecurityFinding] = []
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ZIP_ENTRIES:
                findings.append(
                    _finding("SOURCE_ZIP_ENTRY_LIMIT", "archive entry count exceeds limit")
                )
            expanded = 0
            for info in entries:
                expanded += info.file_size
                normalized = info.filename.replace("\\", "/")
                if _zip_member_unsafe(normalized):
                    findings.append(_finding("SOURCE_ZIP_PATH_TRAVERSAL", normalized))
                depth = len(PurePosixPath(normalized).parts)
                if depth > MAX_ZIP_DEPTH:
                    findings.append(_finding("SOURCE_ZIP_DEPTH_LIMIT", normalized))
                unix_mode = info.external_attr >> 16
                if stat.S_ISLNK(unix_mode):
                    findings.append(_finding("SOURCE_ZIP_SYMLINK", normalized))
                ratio = info.file_size / max(info.compress_size, 1)
                if info.file_size > 1024 and ratio > MAX_ZIP_RATIO:
                    findings.append(_finding("SOURCE_ZIP_RATIO_LIMIT", normalized))
                lowered = normalized.lower()
                if lowered.endswith("vbaproject.bin") or "/embeddings/" in lowered:
                    findings.append(_finding("SOURCE_OFFICE_ACTIVE_CONTENT", normalized))
                if lowered.endswith(".rels") and info.file_size <= 2 * 1024 * 1024:
                    try:
                        root = ElementTree.fromstring(archive.read(info))
                    except Exception:
                        findings.append(_finding("SOURCE_OFFICE_XML_INVALID", normalized))
                        continue
                    for relationship in root.iter():
                        target_mode = relationship.attrib.get("TargetMode", "")
                        target = relationship.attrib.get("Target", "")
                        if target_mode.lower() == "external" or re.match(
                            r"(?i)^(?:https?|file|ftp):", target
                        ):
                            findings.append(
                                _finding("SOURCE_OFFICE_EXTERNAL_RELATIONSHIP", normalized)
                            )
            if expanded > MAX_ZIP_EXPANDED_BYTES:
                findings.append(_finding("SOURCE_ZIP_SIZE_LIMIT", "expanded archive exceeds limit"))
            names = {entry.filename for entry in entries}
            if "[Content_Types].xml" not in names:
                findings.append(
                    _finding("SOURCE_OFFICE_CONTENT_TYPES_MISSING", "missing content types")
                )
            else:
                try:
                    content_types = archive.read("[Content_Types].xml")
                    ElementTree.fromstring(content_types)
                except Exception:
                    findings.append(
                        _finding("SOURCE_OFFICE_CONTENT_TYPES_INVALID", "invalid content types")
                    )
            required_prefix = {".docx": "word/", ".pptx": "ppt/", ".xlsx": "xl/"}[suffix]
            if not any(name.startswith(required_prefix) for name in names):
                findings.append(
                    _finding(
                        "SOURCE_EXTENSION_MAGIC_MISMATCH",
                        f"archive is not a valid {suffix} package",
                    )
                )
    except (OSError, zipfile.BadZipFile, EOFError):
        findings.append(_finding("SOURCE_ARCHIVE_CORRUPT", "Office archive cannot be opened"))
    return findings


def inspect_source(path: Path) -> Inspection:
    suffix = path.suffix.lower()
    findings: list[SecurityFinding] = []
    if not path.is_file():
        return Inspection("unknown", (_finding("SOURCE_NOT_FILE", "source is not a regular file"),))
    size = path.stat().st_size
    if size == 0:
        findings.append(_finding("SOURCE_EMPTY", "source is empty"))
    if size > MAX_SOURCE_BYTES:
        findings.append(_finding("SOURCE_SIZE_LIMIT", "source exceeds the G01 intake limit"))
    sample = path.read_bytes()[:8192]
    if EICAR_MARKER in sample:
        findings.append(_finding("SOURCE_MALWARE_TEST_SIGNATURE", "EICAR test signature detected"))

    if suffix in OFFICE_TYPES:
        detected_type = OFFICE_TYPES[suffix]
        if not sample.startswith(b"PK"):
            findings.append(
                _finding("SOURCE_EXTENSION_MAGIC_MISMATCH", "Office file lacks ZIP magic")
            )
        else:
            findings.extend(_inspect_office_zip(path, suffix))
    elif suffix == ".pdf":
        detected_type = "application/pdf"
        if not sample.startswith(b"%PDF-"):
            findings.append(_finding("SOURCE_EXTENSION_MAGIC_MISMATCH", "PDF magic is missing"))
        else:
            try:
                reader = PdfReader(path, strict=False)
                if reader.is_encrypted:
                    findings.append(
                        _finding("SOURCE_PDF_ENCRYPTED", "encrypted PDF is not accepted")
                    )
                else:
                    len(reader.pages)
            except Exception:
                findings.append(_finding("SOURCE_PDF_CORRUPT", "PDF cannot be parsed"))
    elif suffix in TEXT_TYPES:
        detected_type = TEXT_TYPES[suffix]
        try:
            sample.decode("utf-8")
        except UnicodeDecodeError:
            findings.append(_finding("SOURCE_TEXT_ENCODING_INVALID", "source is not valid UTF-8"))
        if suffix in {".html", ".htm"}:
            findings.extend(_inspect_html(path))
    elif sample.startswith(b"PK"):
        detected_type = "application/zip"
        findings.append(
            _finding("SOURCE_EXTENSION_MAGIC_MISMATCH", "ZIP payload has unsupported extension")
        )
    else:
        detected_type = "application/octet-stream"
        findings.append(
            _finding("SOURCE_TYPE_UNSUPPORTED", f"unsupported extension: {suffix or '<none>'}")
        )

    return Inspection(detected_type, tuple(findings))


def scan_source(source_key: str, source_path: Path) -> SecurityDecision:
    inspection = inspect_source(source_path)
    return SecurityDecision(
        decision="clean" if not inspection.findings else "rejected",
        source_key=source_key,
        source_sha256=sha256_file(source_path),
        detected_type=inspection.detected_type,
        findings=list(inspection.findings),
    )

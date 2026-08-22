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
from urllib.parse import urlsplit

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
MAX_PASSIVE_HYPERLINK_LENGTH = 2_048

PASSIVE_HTML_LINK_TAGS = {"a", "area"}
PASSIVE_WEB_SCHEMES = {"http", "https"}

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


def _split_url(value: str):
    try:
        return urlsplit(value.strip())
    except ValueError:
        return None


def _is_external_reference(value: str) -> bool:
    stripped = value.strip()
    if stripped.startswith("//"):
        return True
    parsed = _split_url(stripped)
    return parsed is None or bool(parsed.scheme)


def _is_safe_passive_web_hyperlink(value: str) -> bool:
    """Allow a clickable web citation without allowing the parser to fetch it."""

    stripped = value.strip()
    if not stripped or len(stripped) > MAX_PASSIVE_HYPERLINK_LENGTH:
        return False
    if any(ord(character) < 0x20 for character in stripped):
        return False
    parsed = _split_url(stripped)
    if parsed is None or parsed.scheme.lower() not in PASSIVE_WEB_SCHEMES:
        return False
    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        return False
    return True


def _relationship_kind(relationship_type: str) -> str:
    return relationship_type.rstrip("/").rsplit("/", 1)[-1].lower()


def _office_external_relationship_message(
    package_part: str,
    relationship_type: str,
    target: str,
) -> str:
    kind = _relationship_kind(relationship_type) or "unknown"
    parsed = _split_url(target)
    scheme = parsed.scheme.lower() if parsed is not None and parsed.scheme else "external"
    return f"{package_part}: external {kind} relationship ({scheme})"


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
            if not isinstance(value, str) or not _is_external_reference(value):
                continue
            if (
                attribute == "href"
                and tag.name in PASSIVE_HTML_LINK_TAGS
                and _is_safe_passive_web_hyperlink(value)
            ):
                continue
            findings.append(
                _finding(
                    "SOURCE_HTML_EXTERNAL_REFERENCE",
                    f"HTML contains external {tag.name}[{attribute}]",
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
                        relationship_type = relationship.attrib.get("Type", "")
                        is_external = (
                            target_mode.lower() == "external"
                            or _is_external_reference(target)
                        )
                        if not is_external:
                            continue
                        if (
                            _relationship_kind(relationship_type) == "hyperlink"
                            and _is_safe_passive_web_hyperlink(target)
                        ):
                            continue
                        findings.append(
                            _finding(
                                "SOURCE_OFFICE_EXTERNAL_RELATIONSHIP",
                                _office_external_relationship_message(
                                    normalized,
                                    relationship_type,
                                    target,
                                ),
                            )
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

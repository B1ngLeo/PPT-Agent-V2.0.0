import json
import zipfile
from pathlib import Path

from instant_ppt_worker.adapter import run_request
from instant_ppt_worker.security import inspect_source

ROOT = Path(__file__).resolve().parents[3]
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
OFFICE_REL_NS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)


def _write_docx_with_relationships(
    path: Path,
    relationships: list[tuple[str, str]],
) -> None:
    relationship_xml = "".join(
        (
            f'<Relationship Id="rId{index}" Type="{relationship_type}" '
            f'Target="{target}" TargetMode="External"/>'
        )
        for index, (relationship_type, target) in enumerate(relationships, start=1)
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" '
                'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Override PartName="/word/document.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.'
                'wordprocessingml.document.main+xml"/>'
                "</Types>"
            ),
        )
        archive.writestr(
            "word/document.xml",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/'
                'wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Safe</w:t>'
                "</w:r></w:p></w:body></w:document>"
            ),
        )
        archive.writestr(
            "word/_rels/document.xml.rels",
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<Relationships xmlns="{REL_NS}">{relationship_xml}</Relationships>',
        )


def _payload(root: Path, source: str, decision: str = "decision.json") -> str:
    return json.dumps(
        {
            "schemaVersion": 1,
            "requestId": "scan-test",
            "operation": "scanSource",
            "workspaceRoot": str(root),
            "inputKey": source,
            "outputKey": decision,
        }
    )


def test_clean_markdown_is_accepted(tmp_path: Path) -> None:
    (tmp_path / "clean.md").write_text("# Safe\n\nLocal content", encoding="utf-8")
    response, exit_code = run_request(_payload(tmp_path, "clean.md"))
    assert exit_code == 0
    assert response.status == "succeeded"
    decision = json.loads((tmp_path / "decision.json").read_text(encoding="utf-8"))
    assert decision["decision"] == "clean"


def test_passive_web_citations_are_accepted(tmp_path: Path) -> None:
    source = tmp_path / "citations.docx"
    hyperlink_type = f"{OFFICE_REL_NS}/hyperlink"
    _write_docx_with_relationships(
        source,
        [
            (hyperlink_type, "https://openai.com/index/gpt-5-6/"),
            (hyperlink_type, "http://example.test/reference"),
        ],
    )

    response, exit_code = run_request(_payload(tmp_path, source.name))

    assert exit_code == 0, response.error
    decision = json.loads((tmp_path / "decision.json").read_text(encoding="utf-8"))
    assert decision["decision"] == "clean"
    assert decision["findings"] == []


def test_gpt56_announcement_docx_with_official_citations_is_accepted() -> None:
    source = ROOT / "tests/OpenAI_GPT-5.6_发布公告_中文版_2026-07-09.docx"

    inspection = inspect_source(source)

    assert inspection.findings == ()


def test_passive_html_citation_is_accepted_but_external_image_is_rejected(
    tmp_path: Path,
) -> None:
    (tmp_path / "citation.html").write_text(
        '<html><body><a href="https://example.test/source">Source</a></body></html>',
        encoding="utf-8",
    )
    response, exit_code = run_request(
        _payload(tmp_path, "citation.html", "citation-decision.json")
    )
    assert exit_code == 0, response.error

    (tmp_path / "image.html").write_text(
        '<html><body><img src="https://example.test/track.png"></body></html>',
        encoding="utf-8",
    )
    response, exit_code = run_request(
        _payload(tmp_path, "image.html", "image-decision.json")
    )
    assert exit_code == 3
    assert response.error and "SOURCE_HTML_EXTERNAL_REFERENCE" in response.error.message


def test_active_external_relationships_and_unsafe_hyperlinks_are_rejected(
    tmp_path: Path,
) -> None:
    cases = [
        (f"{OFFICE_REL_NS}/image", "https://example.test/remote.png", "image"),
        (f"{OFFICE_REL_NS}/hyperlink", "file:///etc/passwd", "file-link"),
        (
            f"{OFFICE_REL_NS}/hyperlink",
            "https://user:secret@example.test/reference",
            "credential-link",
        ),
    ]
    for relationship_type, target, label in cases:
        source = tmp_path / f"{label}.docx"
        decision_name = f"{label}.json"
        _write_docx_with_relationships(
            source,
            [(relationship_type, target)],
        )

        response, exit_code = run_request(_payload(tmp_path, source.name, decision_name))

        assert exit_code == 3
        assert response.error and "SOURCE_OFFICE_EXTERNAL_RELATIONSHIP" in response.error.message
        assert _relationship_label(relationship_type) in response.error.message


def _relationship_label(relationship_type: str) -> str:
    return relationship_type.rsplit("/", 1)[-1]


def test_eicar_and_external_html_are_rejected(tmp_path: Path) -> None:
    (tmp_path / "eicar.txt").write_text(
        "INSTANT-PPT-EICAR-TEST-SIGNATURE",
        encoding="utf-8",
    )
    response, exit_code = run_request(_payload(tmp_path, "eicar.txt", "eicar.json"))
    assert exit_code == 3
    assert response.error and response.error.code == "SOURCE_SECURITY_REJECTED"

    (tmp_path / "external.html").write_text(
        '<html><img src="https://example.invalid/track.png"></html>',
        encoding="utf-8",
    )
    response, exit_code = run_request(_payload(tmp_path, "external.html", "external.json"))
    assert exit_code == 3
    assert response.error and "EXTERNAL_REFERENCE" in response.error.message


def test_object_key_traversal_is_rejected(tmp_path: Path) -> None:
    response, exit_code = run_request(_payload(tmp_path, "../outside.md"))
    assert exit_code == 2
    assert response.error and response.error.code == "ENGINE_INVALID_REQUEST"

import hashlib
import json
import zipfile
from pathlib import Path

from instant_ppt_worker.adapter import run_request
from instant_ppt_worker.agentic_workflow import run_default_workflow
from instant_ppt_worker.image_resources import (
    analyze_image_inventory,
    current_image_inventory_sha256,
    prepare_image_resources,
)
from instant_ppt_worker.providers import GeneratedImage, ProviderRequestError
from instant_ppt_worker.settings import OpenAIImageSettings
from instant_ppt_worker.workflow_models import WorkflowRequestV2
from PIL import Image

from .test_workflow_contracts import HASH, ULIDS, _payload


class FakeImageProvider:
    def __init__(self, provider_name: str, image_bytes: bytes | None = None) -> None:
        self.provider_name = provider_name
        self.image_bytes = image_bytes
        self.calls: list[str] = []

    def generate(
        self,
        prompt: str,
        *,
        size: str | None = None,
        quality: str | None = None,
        idempotency_key: str | None = None,
    ) -> GeneratedImage:
        del size, quality
        self.calls.append(str(idempotency_key))
        if self.image_bytes is None:
            raise ProviderRequestError(self.provider_name, 503, None)
        return GeneratedImage(self.image_bytes, "image/png", "test-image-v1")


def _png(path: Path, *, size: tuple[int, int] = (640, 360)) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color=(37, 99, 235)).save(path, format="PNG")
    return path.read_bytes()


def _image_settings(max_images: int = 4) -> OpenAIImageSettings:
    return OpenAIImageSettings(
        api_key="test-only-not-a-secret",
        enabled=True,
        max_images_per_deck=max_images,
        size="1536x1024",
        quality="low",
    )


def _ai_request(*, path: str, chain: list[str]) -> WorkflowRequestV2:
    payload = _payload()
    payload["runtime"]["allowedTools"].append("provider-image")
    payload["runtime"]["maxStageAttempts"] = 2
    payload["runtime"]["previewIdleTimeoutSeconds"] = 1
    payload["image"] = {
        "scope": "cover_only",
        "usage": ["ai"],
        "notes": {"cover": "抽象的发布光束与克制留白"},
        "aiPath": path,
        "aiPathChain": chain,
    }
    return WorkflowRequestV2.model_validate(payload)


def test_provided_image_analysis_becomes_stale_and_can_be_rebuilt(tmp_path: Path) -> None:
    source = tmp_path / "workflow-input" / "assets" / "approved-hero.png"
    content = _png(source)
    payload = _payload()
    payload["image"] = {
        "scope": "selective",
        "usage": ["provided"],
        "notes": {ULIDS["slide_1"]: "技术发布封面氛围图"},
        "providedAssets": [
            {
                "assetId": ULIDS["image_asset"],
                "filename": "approved-hero.png",
                "workspaceKey": "workflow-input/assets/approved-hero.png",
                "sha256": hashlib.sha256(content).hexdigest(),
                "mediaType": "image/png",
                "purpose": "技术发布封面氛围图",
                "slideIds": [ULIDS["slide_1"]],
                "layoutPattern": "#P1-01",
                "license": "user-provided",
            }
        ],
    }
    request = WorkflowRequestV2.model_validate(payload)
    project = tmp_path / "project"

    prepared = prepare_image_resources(tmp_path, project, request)

    assert prepared.analysis_path.is_file()
    assert "approved-hero.png" in prepared.analysis_path.read_text(encoding="utf-8")
    assert current_image_inventory_sha256(project) == prepared.inventory_sha256

    _png(project / "images" / "approved-hero.png", size=(360, 640))
    assert current_image_inventory_sha256(project) != prepared.inventory_sha256

    rebuilt_path, rebuilt_inventory, rebuilt_analysis = analyze_image_inventory(project)
    assert rebuilt_path == prepared.analysis_path
    assert rebuilt_inventory == current_image_inventory_sha256(project)
    assert rebuilt_inventory != prepared.inventory_sha256
    assert rebuilt_analysis != prepared.analysis_sha256


def test_auto_ai_path_uses_only_declared_chain_and_records_recovery(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.png"
    image_bytes = _png(fixture)
    api = FakeImageProvider("api-test")
    host = FakeImageProvider("host-native-test", image_bytes)
    request = _ai_request(path="auto", chain=["api", "host-native", "manual"])

    prepared = prepare_image_resources(
        tmp_path,
        tmp_path / "project",
        request,
        api_provider=api,
        host_native_provider=host,
        image_settings=_image_settings(),
    )

    [resource] = prepared.resources
    assert resource["status"] == "Generated"
    assert resource["selectedStrategy"] == "host-native"
    assert [value["strategy"] for value in resource["attempts"]] == [
        "api",
        "api",
        "host-native",
    ]
    assert len(api.calls) == 2
    assert len(host.calls) == 1
    assert prepared.blocking_resources == ()
    assert "ORBIT-NONCE" not in resource["prompt"]
    assert "no visible text" in resource["prompt"]


def test_explicit_api_failure_never_switches_to_host_native(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.png"
    image_bytes = _png(fixture)
    api = FakeImageProvider("api-test")
    host = FakeImageProvider("host-native-test", image_bytes)
    request = _ai_request(path="api", chain=["api", "manual"])

    prepared = prepare_image_resources(
        tmp_path,
        tmp_path / "project",
        request,
        api_provider=api,
        host_native_provider=host,
        image_settings=_image_settings(),
    )

    [resource] = prepared.blocking_resources
    assert resource["status"] == "Needs-Manual"
    assert [value["strategy"] for value in resource["attempts"]] == [
        "api",
        "api",
        "manual",
    ]
    assert len(api.calls) == 2
    assert host.calls == []
    audit = json.loads(prepared.audit_path.read_text(encoding="utf-8"))
    assert audit["blockingCount"] == 1
    assert audit["generatedCount"] == 0


def test_generated_ai_image_completes_full_default_workflow(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.png"
    image_bytes = _png(fixture)
    request = _ai_request(path="api", chain=["api", "manual"])
    project = tmp_path / "ai-success_ppt169_20260818"

    outcome = run_default_workflow(
        tmp_path,
        project,
        request,
        api_image_provider=FakeImageProvider("api-test", image_bytes),
        image_settings=_image_settings(max_images=1),
    )

    assert outcome["result"].status == "succeeded"
    audit = json.loads(
        (project / "analysis" / "image-resource-audit.json").read_text(encoding="utf-8")
    )
    package = json.loads(
        (project / "validation" / "pptx-package-qa.json").read_text(encoding="utf-8")
    )
    [resource] = audit["resources"]
    assert resource["status"] == "Generated"
    assert resource["selectedStrategy"] == "api"
    assert audit["generatedCount"] == 1
    assert "source=ai" in (project / "spec_lock.md").read_text(encoding="utf-8")
    assert package["passed"] is True
    assert package["fullSlidePictureCount"] == 0
    assert any((project / "images").glob("ai-*.png"))
    assert (project / "exports" / "deck.pptx").is_file()


def test_approved_office_native_fallback_applies_only_after_matching_failure(
    tmp_path: Path,
) -> None:
    request_payload = _payload()
    request_payload["runtime"]["allowedTools"].append("provider-image")
    request_payload["runtime"]["maxStageAttempts"] = 2
    request_payload["image"] = {
        "scope": "cover_only",
        "usage": ["ai"],
        "notes": {"cover": "抽象技术发布封面"},
        "aiPath": "api",
        "aiPathChain": ["api", "manual"],
        "officeNativeFallbacks": [
            {
                "slideId": ULIDS["slide_1"],
                "construction": "native-shapes",
                "triggerCodes": ["provider_request_failed"],
                "decisionReceiptSha256": HASH,
            }
        ],
    }
    request = WorkflowRequestV2.model_validate(request_payload)

    prepared = prepare_image_resources(
        tmp_path,
        tmp_path / "project",
        request,
        api_provider=FakeImageProvider("api-test"),
        image_settings=_image_settings(),
    )

    [resource] = prepared.resources
    assert resource["status"] == "Resolved-Native"
    assert resource["construction"] == "native-shapes"
    assert resource["appliedTriggerCode"] == "provider_request_failed"
    assert prepared.native_fallback_slides == {ULIDS["slide_1"]}
    assert prepared.blocking_resources == ()


def test_selective_provided_image_exports_as_independent_ppt_picture(tmp_path: Path) -> None:
    source = tmp_path / "workflow-input" / "assets" / "approved-hero.png"
    content = _png(source)
    workflow = _payload()
    workflow["runtime"]["previewIdleTimeoutSeconds"] = 1
    workflow["image"] = {
        "scope": "selective",
        "usage": ["provided"],
        "notes": {ULIDS["slide_1"]: "封面右侧的抽象蓝色视觉锚点"},
        "providedAssets": [
            {
                "assetId": ULIDS["image_asset"],
                "filename": "approved-hero.png",
                "workspaceKey": "workflow-input/assets/approved-hero.png",
                "sha256": hashlib.sha256(content).hexdigest(),
                "mediaType": "image/png",
                "purpose": "封面右侧的抽象蓝色视觉锚点",
                "slideIds": [ULIDS["slide_1"]],
                "cropPolicy": "adaptive",
                "layoutPattern": "#P1-01",
                "license": "user-provided",
            }
        ],
    }
    adapter_request = {
        "schemaVersion": 2,
        "requestId": "issue-002-image-selective",
        "operation": "generatePptxDefault",
        "workspaceRoot": str(tmp_path),
        "outputKey": "generated/selective-image",
        "workflow": workflow,
    }

    response, exit_code = run_request(json.dumps(adapter_request, ensure_ascii=False))

    assert exit_code == 0, response.error.model_dump(mode="json") if response.error else response
    assert response.status == "succeeded"
    [project] = (tmp_path / "generated").glob("selective-image_ppt169_*")
    result = json.loads((project / "workflow-result.json").read_text(encoding="utf-8"))
    audit = json.loads(
        (project / "analysis" / "image-resource-audit.json").read_text(encoding="utf-8")
    )
    package = json.loads(
        (project / "validation" / "pptx-package-qa.json").read_text(encoding="utf-8")
    )

    assert result["usage"]["imageCount"] == 1
    assert audit["blockingCount"] == 0
    assert audit["resources"][0]["status"] == "Existing"
    assert "approved-hero.png" in (project / "design_spec.md").read_text(encoding="utf-8")
    assert "## images" in (project / "spec_lock.md").read_text(encoding="utf-8")
    assert package["passed"] is True
    assert package["fullSlidePictureCount"] == 0
    assert package["editableTextShapeCount"] > 0
    pptx = project / "exports" / "deck.pptx"
    with zipfile.ZipFile(pptx) as archive:
        names = set(archive.namelist())
        slide_xml = archive.read("ppt/slides/slide1.xml")
        assert any(name.startswith("ppt/media/") for name in names)
        assert b"<p:pic>" in slide_xml
        assert b"<a:t>" in slide_xml


def test_unresolved_required_ai_image_blocks_step7_as_needs_manual(tmp_path: Path) -> None:
    workflow = _payload()
    workflow["runtime"]["previewIdleTimeoutSeconds"] = 1
    workflow["image"] = {
        "scope": "cover_only",
        "usage": ["ai"],
        "notes": {"cover": "抽象技术发布封面"},
        "aiPath": "manual",
        "aiPathChain": ["manual"],
    }
    adapter_request = {
        "schemaVersion": 2,
        "requestId": "issue-002-image-needs-manual",
        "operation": "generatePptxDefault",
        "workspaceRoot": str(tmp_path),
        "outputKey": "generated/image-needs-manual",
        "workflow": workflow,
    }

    response, exit_code = run_request(json.dumps(adapter_request, ensure_ascii=False))

    assert exit_code == 0
    assert response.status == "succeeded"
    [project] = (tmp_path / "generated").glob("image-needs-manual_ppt169_*")
    result = json.loads((project / "workflow-result.json").read_text(encoding="utf-8"))
    final_gate = json.loads(
        (project / "validation" / "svg_quality_report.json").read_text(encoding="utf-8")
    )
    prompt_manifest = json.loads(
        (project / "images" / "image_prompts.json").read_text(encoding="utf-8")
    )

    assert result["status"] == "needs_manual"
    assert result["stage"] == "image_resources"
    assert result["errors"][0]["code"] == "IMAGE_RESOURCE_NEEDS_MANUAL"
    assert final_gate["stage"] == "final"
    assert final_gate["source_fingerprint"]["file_count"] == 2
    assert prompt_manifest["items"][0]["textPolicy"] == "none"
    assert not (project / "exports" / "deck.pptx").exists()


def test_approved_native_fallback_updates_lock_and_completes_workflow(
    tmp_path: Path,
) -> None:
    workflow = _payload()
    workflow["runtime"]["allowedTools"].append("provider-image")
    workflow["runtime"]["previewIdleTimeoutSeconds"] = 1
    workflow["runtime"]["maxStageAttempts"] = 2
    workflow["image"] = {
        "scope": "cover_only",
        "usage": ["ai"],
        "notes": {"cover": "抽象技术发布封面"},
        "aiPath": "host-native",
        "aiPathChain": ["host-native", "manual"],
        "officeNativeFallbacks": [
            {
                "slideId": ULIDS["slide_1"],
                "construction": "native-shapes",
                "triggerCodes": ["provider_configuration_failed"],
                "decisionReceiptSha256": HASH,
            }
        ],
    }
    adapter_request = {
        "schemaVersion": 2,
        "requestId": "issue-002-image-native-fallback",
        "operation": "generatePptxDefault",
        "workspaceRoot": str(tmp_path),
        "outputKey": "generated/image-native-fallback",
        "workflow": workflow,
    }

    response, exit_code = run_request(json.dumps(adapter_request, ensure_ascii=False))

    assert exit_code == 0
    assert response.status == "succeeded"
    [project] = (tmp_path / "generated").glob("image-native-fallback_ppt169_*")
    result = json.loads((project / "workflow-result.json").read_text(encoding="utf-8"))
    audit = json.loads(
        (project / "analysis" / "image-resource-audit.json").read_text(encoding="utf-8")
    )
    lock = (project / "spec_lock.md").read_text(encoding="utf-8")

    assert result["status"] == "succeeded"
    assert audit["resources"][0]["status"] == "Resolved-Native"
    assert audit["resources"][0]["decisionReceiptSha256"] == HASH
    assert "visual_style_behavior" in lock
    assert "P01=native-shapes when provider_configuration_failed" in lock
    assert (project / "exports" / "deck.pptx").is_file()

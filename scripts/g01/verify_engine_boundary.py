"""Enforce the engine adapter as the only product-facing vendor boundary."""

from __future__ import annotations

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PRODUCT_ROOTS = (
    REPOSITORY_ROOT / "apps",
    REPOSITORY_ROOT / "packages",
    REPOSITORY_ROOT / "services" / "api",
)
SOURCE_SUFFIXES = {".js", ".mjs", ".py", ".ts", ".tsx"}
IGNORED_PARTS = {".next", ".venv", "generated", "node_modules"}
FORBIDDEN_PRODUCT_REFERENCES = (
    "vendor/ppt-master",
    "vendor\\ppt-master",
    "instant_ppt_worker",
    "ENGINE_SCRIPTS",
    "VENDOR_ROOT",
)
WORKER_ROOT = REPOSITORY_ROOT / "services" / "worker" / "src" / "instant_ppt_worker"
ENGINE_SCRIPT_ALLOWED = {
    "agentic_workflow.py",
    "image_resources.py",
    "paths.py",
    "renderer.py",
    "source_parser.py",
}


def _source_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in SOURCE_SUFFIXES
        and not IGNORED_PARTS.intersection(path.parts)
    )


def verify() -> None:
    violations: list[str] = []
    for root in PRODUCT_ROOTS:
        for path in _source_files(root):
            content = path.read_text(encoding="utf-8")
            for reference in FORBIDDEN_PRODUCT_REFERENCES:
                if reference in content:
                    relative = path.relative_to(REPOSITORY_ROOT).as_posix()
                    violations.append(f"{relative}: forbidden product reference {reference!r}")

    for path in _source_files(WORKER_ROOT):
        content = path.read_text(encoding="utf-8")
        if "ENGINE_SCRIPTS" in content and path.name not in ENGINE_SCRIPT_ALLOWED:
            relative = path.relative_to(REPOSITORY_ROOT).as_posix()
            violations.append(f"{relative}: unapproved direct engine-script access")
        if "VENDOR_ROOT" in content and path.name != "paths.py":
            relative = path.relative_to(REPOSITORY_ROOT).as_posix()
            violations.append(f"{relative}: unapproved vendor-root access")

    if violations:
        raise SystemExit("engine boundary violations:\n- " + "\n- ".join(violations))
    print("engine-boundary: product layers isolated; adapter implementation access is allowlisted")


if __name__ == "__main__":
    verify()

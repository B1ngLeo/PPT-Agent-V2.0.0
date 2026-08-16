"""Repository and vendored-engine paths used by editable and wheel installs."""

import os
from pathlib import Path


def _repository_root() -> Path:
    configured = os.getenv("INSTANT_PPT_REPOSITORY_ROOT", "").strip()
    if configured:
        root = Path(configured).resolve()
        if not (root / "vendor" / "ppt-master").is_dir():
            raise RuntimeError("INSTANT_PPT_REPOSITORY_ROOT has no vendored engine")
        return root
    for parent in Path(__file__).resolve().parents:
        if (parent / "vendor" / "ppt-master").is_dir():
            return parent
    raise RuntimeError("vendored ppt-master engine could not be located")


REPOSITORY_ROOT = _repository_root()
VENDOR_ROOT = REPOSITORY_ROOT / "vendor" / "ppt-master"
ENGINE_SCRIPTS = VENDOR_ROOT / "scripts"


def resolve_key(root: Path, key: str, *, must_exist: bool = False) -> Path:
    """Resolve an object-like key below a configured local fixture root."""

    if not key or "\\" in key:
        raise ValueError("object key must be a non-empty POSIX-style relative path")
    key_path = Path(key)
    if key_path.is_absolute() or any(part in {"", ".", ".."} for part in key_path.parts):
        raise ValueError("object key must not be absolute or contain traversal segments")
    resolved_root = root.resolve()
    resolved = (resolved_root / key_path).resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError("object key escapes the configured fixture root")
    if must_exist and not resolved.exists():
        raise FileNotFoundError(f"object key does not exist: {key}")
    return resolved

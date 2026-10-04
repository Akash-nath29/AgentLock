"""Content-addressed object store for AgentLock dependencies (.agentlock/objects/)."""

from __future__ import annotations

import hashlib
from pathlib import Path


def hash_bytes(data: bytes) -> str:
    """Calculate SHA-256 hash of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def hash_text(text: str) -> str:
    """Calculate SHA-256 hash of UTF-8 text."""
    return hash_bytes(text.encode("utf-8"))


def object_rel_path(digest: str) -> str:
    """Format sha256 digest into 2-level directory object path (e.g. 41/8a72e7...)."""
    return f"{digest[:2]}/{digest[2:]}"


class ObjectStore:
    """Manages content-addressed objects under .agentlock/objects/."""

    def __init__(self, root_dir: Path | str):
        self.root_dir = Path(root_dir)
        self.objects_dir = self.root_dir / ".agentlock" / "objects"

    def put(self, content: str | bytes) -> str:
        """Store content if not already present. Returns sha256 digest."""
        if isinstance(content, str):
            raw = content.encode("utf-8")
        else:
            raw = content

        digest = hash_bytes(raw)
        rel = object_rel_path(digest)
        target = self.objects_dir / rel

        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)

        return digest

    def get(self, digest: str) -> str:
        """Retrieve UTF-8 text content for a given object digest."""
        rel = object_rel_path(digest)
        target = self.objects_dir / rel
        if not target.exists():
            raise FileNotFoundError(f"Object {digest} not found in store at {target}")
        return target.read_text(encoding="utf-8")

    def has(self, digest: str) -> bool:
        """Check if an object exists in the store."""
        target = self.objects_dir / object_rel_path(digest)
        return target.exists()

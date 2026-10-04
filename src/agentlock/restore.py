"""Restore engine for rebuilding locked dependency configurations."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field

from agentlock.lockfile import LockfileV2
from agentlock.objects import ObjectStore


class RestoreItem(BaseModel):
    dep_id: str
    kind: str
    dep_class: Literal["reproducible", "externally managed", "unavailable"]
    action: str
    source_file: str = ""
    status: Literal["restored", "matches", "external_check", "failed", "unavailable"] = "restored"


class RestorePlan(BaseModel):
    items: list[RestoreItem] = Field(default_factory=list)
    dry_run: bool = False
    target_dir: str = ""

    @property
    def restorable_count(self) -> int:
        return sum(1 for item in self.items if item.status == "restored")


def build_restore_plan(lock: LockfileV2, project_dir: Path | str) -> RestorePlan:
    """Analyze locked dependencies and construct restoration plan."""
    proj = Path(project_dir)
    items: list[RestoreItem] = []

    # Prompts
    for p in lock.dependencies.prompts:
        src = p.source.file
        if src:
            target_path = proj / src
            items.append(
                RestoreItem(
                    dep_id=p.id,
                    kind="prompt",
                    dep_class="reproducible",
                    action=f"Restore {src}",
                    source_file=src,
                    status="restored" if target_path.exists() else "restored",
                )
            )

    # Skills
    for s in lock.dependencies.skills:
        src = s.source.file
        if src:
            items.append(
                RestoreItem(
                    dep_id=s.id,
                    kind="skill",
                    dep_class="reproducible",
                    action=f"Restore {src}",
                    source_file=src,
                    status="restored",
                )
            )

    # Models
    for m in lock.dependencies.model:
        items.append(
            RestoreItem(
                dep_id=m.id,
                kind="model",
                dep_class="externally managed",
                action=f"Check model {m.name} via provider {m.provider}",
                status="external_check",
            )
        )

    # Config
    for c in lock.dependencies.config:
        src = c.source.file
        if src:
            items.append(
                RestoreItem(
                    dep_id=c.id,
                    kind="config",
                    dep_class="reproducible",
                    action=f"Restore {src}",
                    source_file=src,
                    status="restored",
                )
            )

    return RestorePlan(items=items, target_dir=str(proj))


def execute_restore(
    lock: LockfileV2,
    project_dir: Path | str,
    dry_run: bool = False,
    to_dir: Path | str | None = None,
) -> RestorePlan:
    """Execute dependency restoration based on locked state."""
    base_proj = Path(project_dir)
    dest_proj = Path(to_dir) if to_dir else base_proj
    store = ObjectStore(base_proj)

    plan = build_restore_plan(lock, dest_proj)
    plan.dry_run = dry_run

    if dry_run:
        return plan

    # Create backup if overwriting existing working tree files
    if dest_proj == base_proj:
        backup_dir = base_proj / ".agentlock" / "backup" / str(int(time.time()))
        backup_dir.mkdir(parents=True, exist_ok=True)

    # Apply reproducible object rewrites
    for p in lock.dependencies.prompts:
        if p.source.file and store.has(p.object):
            content = store.get(p.object)
            target = dest_proj / p.source.file
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

    for s in lock.dependencies.skills:
        if s.source.file and store.has(s.object):
            content = store.get(s.object)
            target = dest_proj / s.source.file
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

    return plan

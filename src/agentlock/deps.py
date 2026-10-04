"""Dependency resolution, representation, and dependency diff logic."""

from __future__ import annotations

import hashlib
import json
import sys
from typing import Any, Literal
from pydantic import BaseModel, Field


class DependencySource(BaseModel):
    file: str | None = None
    key: str | None = None
    code: str | None = None  # e.g. module:symbol


class ModelDep(BaseModel):
    id: str
    provider: str
    name: str
    digest: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    source: DependencySource = Field(default_factory=DependencySource)
    dep_class: Literal["reproducible", "external", "unavailable"] = "external"


class PromptDep(BaseModel):
    id: str
    sha256: str
    object: str
    source: DependencySource
    dep_class: Literal["reproducible", "external", "unavailable"] = "reproducible"


class SkillDep(BaseModel):
    id: str
    sha256: str
    object: str
    source: DependencySource
    dep_class: Literal["reproducible", "external", "unavailable"] = "reproducible"


class ToolImplementation(BaseModel):
    file: str = ""
    symbol: str = ""
    git_blob: str = ""


class ToolDep(BaseModel):
    id: str
    schema_sha256: str
    object: str
    implementation: ToolImplementation = Field(default_factory=ToolImplementation)
    dep_class: Literal["reproducible", "external", "unavailable"] = "external"


class McpDep(BaseModel):
    id: str
    transport: str = "stdio"
    command_or_url: str = ""
    package: str = ""
    version: str = ""
    tools_sha256: str = ""
    tools: list[str] = Field(default_factory=list)
    source: DependencySource = Field(default_factory=DependencySource)
    dep_class: Literal["reproducible", "external", "unavailable"] = "external"


class ConfigDep(BaseModel):
    id: str
    sha256: str
    object: str
    values: dict[str, Any] = Field(default_factory=dict)
    source: DependencySource = Field(default_factory=DependencySource)
    dep_class: Literal["reproducible", "external", "unavailable"] = "reproducible"


class RuntimeDep(BaseModel):
    python: str = f"{sys.version_info.major}.{sys.version_info.minor}"
    packages: dict[str, str] = Field(default_factory=dict)


class DependencyClosure(BaseModel):
    """Complete collection of dependency objects forming an agent state."""

    fingerprint: str = ""
    model: list[ModelDep] = Field(default_factory=list)
    prompts: list[PromptDep] = Field(default_factory=list)
    skills: list[SkillDep] = Field(default_factory=list)
    tools: list[ToolDep] = Field(default_factory=list)
    mcp: list[McpDep] = Field(default_factory=list)
    config: list[ConfigDep] = Field(default_factory=list)
    runtime: RuntimeDep = Field(default_factory=RuntimeDep)

    def compute_fingerprint(self) -> str:
        """Compute SHA-256 fingerprint over all sorted dependency records."""
        payload = {
            "model": [m.model_dump() for m in sorted(self.model, key=lambda x: x.id)],
            "prompts": [p.model_dump() for p in sorted(self.prompts, key=lambda x: x.id)],
            "skills": [s.model_dump() for s in sorted(self.skills, key=lambda x: x.id)],
            "tools": [t.model_dump() for t in sorted(self.tools, key=lambda x: x.id)],
            "mcp": [m.model_dump() for m in sorted(self.mcp, key=lambda x: x.id)],
            "config": [c.model_dump() for c in sorted(self.config, key=lambda x: x.id)],
            "runtime": self.runtime.model_dump(),
        }
        serialized = json.dumps(payload, sort_keys=True)
        digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        self.fingerprint = f"sha256:{digest}"
        return self.fingerprint


class DependencyChange(BaseModel):
    id: str
    dep_id: str
    kind: Literal["model", "prompt", "skill", "tool", "mcp", "config", "runtime"]
    base_value: Any = None
    head_value: Any = None
    summary: str = ""


def diff_dependencies(base: DependencyClosure, head: DependencyClosure) -> list[DependencyChange]:
    """Compare two dependency closures and return detailed changes."""
    changes: list[DependencyChange] = []
    idx = 1

    # Models
    base_models = {m.id: m for m in base.model}
    head_models = {m.id: m for m in head.model}
    for dep_id in sorted(set(base_models.keys()) | set(head_models.keys())):
        bm, hm = base_models.get(dep_id), head_models.get(dep_id)
        if bm is None:
            changes.append(
                DependencyChange(
                    id=f"dc{idx}", dep_id=dep_id, kind="model", base_value=None, head_value=hm.name, summary=f"Added model {hm.name}"
                )
            )
            idx += 1
        elif hm is None:
            changes.append(
                DependencyChange(
                    id=f"dc{idx}", dep_id=dep_id, kind="model", base_value=bm.name, head_value=None, summary=f"Removed model {bm.name}"
                )
            )
            idx += 1
        elif bm.name != hm.name or bm.provider != hm.provider or bm.parameters != hm.parameters:
            changes.append(
                DependencyChange(
                    id=f"dc{idx}",
                    dep_id=dep_id,
                    kind="model",
                    base_value=f"{bm.provider}:{bm.name}",
                    head_value=f"{hm.provider}:{hm.name}",
                    summary=f"Model changed: {bm.name} -> {hm.name}",
                )
            )
            idx += 1

    # Prompts
    base_prompts = {p.id: p for p in base.prompts}
    head_prompts = {p.id: p for p in head.prompts}
    for dep_id in sorted(set(base_prompts.keys()) | set(head_prompts.keys())):
        bp, hp = base_prompts.get(dep_id), head_prompts.get(dep_id)
        if bp is None:
            changes.append(
                DependencyChange(
                    id=f"dc{idx}", dep_id=dep_id, kind="prompt", base_value=None, head_value=hp.sha256, summary=f"Added prompt {dep_id}"
                )
            )
            idx += 1
        elif hp is None:
            changes.append(
                DependencyChange(
                    id=f"dc{idx}", dep_id=dep_id, kind="prompt", base_value=bp.sha256, head_value=None, summary=f"Removed prompt {dep_id}"
                )
            )
            idx += 1
        elif bp.sha256 != hp.sha256:
            changes.append(
                DependencyChange(
                    id=f"dc{idx}",
                    dep_id=dep_id,
                    kind="prompt",
                    base_value=bp.sha256[:8],
                    head_value=hp.sha256[:8],
                    summary=f"Prompt modified: {dep_id}",
                )
            )
            idx += 1

    # Skills
    base_skills = {s.id: s for s in base.skills}
    head_skills = {s.id: s for s in head.skills}
    for dep_id in sorted(set(base_skills.keys()) | set(head_skills.keys())):
        bs, hs = base_skills.get(dep_id), head_skills.get(dep_id)
        if bs is None:
            changes.append(
                DependencyChange(
                    id=f"dc{idx}", dep_id=dep_id, kind="skill", base_value=None, head_value=hs.sha256, summary=f"Added skill {dep_id}"
                )
            )
            idx += 1
        elif hs is None:
            changes.append(
                DependencyChange(
                    id=f"dc{idx}", dep_id=dep_id, kind="skill", base_value=bs.sha256, head_value=None, summary=f"Removed skill {dep_id}"
                )
            )
            idx += 1
        elif bs.sha256 != hs.sha256:
            changes.append(
                DependencyChange(
                    id=f"dc{idx}",
                    dep_id=dep_id,
                    kind="skill",
                    base_value=bs.sha256[:8],
                    head_value=hs.sha256[:8],
                    summary=f"Skill modified: {dep_id}",
                )
            )
            idx += 1

    # Tools
    base_tools = {t.id: t for t in base.tools}
    head_tools = {t.id: t for t in head.tools}
    for dep_id in sorted(set(base_tools.keys()) | set(head_tools.keys())):
        bt, ht = base_tools.get(dep_id), head_tools.get(dep_id)
        if bt is None:
            changes.append(
                DependencyChange(
                    id=f"dc{idx}", dep_id=dep_id, kind="tool", base_value=None, head_value=ht.schema_sha256, summary=f"Added tool {dep_id}"
                )
            )
            idx += 1
        elif ht is None:
            changes.append(
                DependencyChange(
                    id=f"dc{idx}", dep_id=dep_id, kind="tool", base_value=bt.schema_sha256, head_value=None, summary=f"Removed tool {dep_id}"
                )
            )
            idx += 1
        elif bt.schema_sha256 != ht.schema_sha256 or bt.implementation != ht.implementation:
            changes.append(
                DependencyChange(
                    id=f"dc{idx}",
                    dep_id=dep_id,
                    kind="tool",
                    base_value=bt.schema_sha256[:8],
                    head_value=ht.schema_sha256[:8],
                    summary=f"Tool modified: {dep_id}",
                )
            )
            idx += 1

    # Config
    base_config = {c.id: c for c in base.config}
    head_config = {c.id: c for c in head.config}
    for dep_id in sorted(set(base_config.keys()) | set(head_config.keys())):
        bc, hc = base_config.get(dep_id), head_config.get(dep_id)
        if bc is None:
            changes.append(
                DependencyChange(
                    id=f"dc{idx}", dep_id=dep_id, kind="config", base_value=None, head_value=hc.values, summary=f"Added config {dep_id}"
                )
            )
            idx += 1
        elif hc is None:
            changes.append(
                DependencyChange(
                    id=f"dc{idx}", dep_id=dep_id, kind="config", base_value=bc.values, head_value=None, summary=f"Removed config {dep_id}"
                )
            )
            idx += 1
        elif bc.sha256 != hc.sha256:
            changes.append(
                DependencyChange(
                    id=f"dc{idx}",
                    dep_id=dep_id,
                    kind="config",
                    base_value=bc.values,
                    head_value=hc.values,
                    summary=f"Config modified: {dep_id}",
                )
            )
            idx += 1

    return changes

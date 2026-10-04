"""Manifest parser and schema for agentlock.yaml (version 2)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal
from pydantic import BaseModel, Field, ValidationError, model_validator
import yaml


class SourceSpec(BaseModel):
    file: str
    key: str | None = None


class ScenarioSpec(BaseModel):
    id: str
    input: str = ""
    entities: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def migrate_task_key(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "task" in data and "input" not in data:
                data["input"] = data.pop("task")
        return data


class ContractOverrideSpec(BaseModel):
    id: str
    statement: str = ""
    rule: dict[str, Any] = Field(default_factory=dict)
    severity: Literal["breaking", "warning", "info"] = "breaking"
    scenarios: list[str] | None = None


class CaptureConfig(BaseModel):
    samples: int = Field(default=3, ge=1)


class JudgeConfig(BaseModel):
    provider: Literal["ollama", "gemini"] = "ollama"
    model: str = "gemma4:31b-cloud"
    temperature: float = 0.0


class PolicyConfig(BaseModel):
    breaking_tolerance: int = Field(default=0, ge=0)


class AgentManifest(BaseModel):
    """Configuration declared in agentlock.yaml."""

    version: int = 2
    agent: AgentHeader
    dependencies: dict[str, Any] = Field(default_factory=dict)
    scenarios: list[ScenarioSpec] = Field(default_factory=list)
    contracts: list[ContractOverrideSpec] = Field(default_factory=list)
    overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)
    capture: CaptureConfig = Field(default_factory=CaptureConfig)
    judge: JudgeConfig = Field(default_factory=JudgeConfig)
    policy: PolicyConfig = Field(default_factory=PolicyConfig)

    class Config:
        extra = "forbid"


class AgentHeader(BaseModel):
    name: str
    adapter: Literal["langgraph", "python"] = "python"
    entrypoint: str
    options: dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "forbid"


def load_manifest(path: Path | str) -> AgentManifest:
    """Load and validate an agentlock.yaml manifest."""
    manifest_path = Path(path)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    try:
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in {manifest_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"{manifest_path} must be a YAML dictionary.")

    # Convert v1 manifest format if present
    if "agent" in data and "version" not in data:
        data["version"] = 2
    if "evaluator" in data and "judge" not in data:
        data["judge"] = data.pop("evaluator")

    try:
        return AgentManifest.model_validate(data)
    except ValidationError as err:
        msg = "Invalid agentlock.yaml format:\n"
        for e in err.errors():
            loc = " -> ".join(str(item) for item in e["loc"])
            msg += f"  - {loc}: {e['msg']}\n"
        raise ValueError(msg) from err

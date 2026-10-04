"""`agent.lock` schema v2 and byte-deterministic writer."""

from __future__ import annotations

import json
from pathlib import Path
from pydantic import BaseModel
import yaml

from agentlock.behavior import BehaviorState
from agentlock.deps import DependencyClosure


class AgentLockHeader(BaseModel):
    name: str
    adapter: str = "python"
    entrypoint: str


class LockfileV2(BaseModel):
    """Schema for agent.lock (version 2)."""

    lockfile_version: int = 2
    agentlock: str = "0.2.0"
    state: str = ""  # <deps_6hex>.<behavior_6hex>
    agent: AgentLockHeader
    dependencies: DependencyClosure
    behavior: BehaviorState

    def compute_state_str(self) -> str:
        """Compute condensed identity state string (<deps_6hex>.<behavior_6hex>)."""
        deps_fp = self.dependencies.compute_fingerprint()
        behav_fp = self.behavior.compute_fingerprint()
        deps_hex = deps_fp.split(":")[-1][:6]
        behav_hex = behav_fp.split(":")[-1][:6]
        self.state = f"{deps_hex}.{behav_hex}"
        return self.state

    def to_yaml_bytes(self) -> bytes:
        """Serialize to byte-deterministic YAML format."""
        self.compute_state_str()
        data = json.loads(self.model_dump_json())

        # Sort keys deterministically for YAML dumping
        yaml_text = yaml.dump(data, sort_keys=False, indent=2, allow_unicode=True)
        return yaml_text.encode("utf-8")


def write_lockfile(path: Path | str, lock: LockfileV2) -> None:
    """Write byte-deterministic agent.lock file."""
    p = Path(path)
    p.write_bytes(lock.to_yaml_bytes())


def load_lockfile(path: Path | str) -> LockfileV2:
    """Load and parse agent.lock file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Lockfile not found at {p}")

    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid lockfile structure in {p}")

    return LockfileV2.model_validate(data)

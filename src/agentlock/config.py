"""`agentlock.yaml`: which agent to test, how to evaluate it, and on which tasks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agentlock.gemma import OLLAMA_DEFAULT_MODEL

CONFIG_FILE = "agentlock.yaml"
STATE_DIR = ".agentlock"


class _Strict(BaseModel):
    # A misspelled or misplaced key must fail loudly, not be silently ignored.
    model_config = ConfigDict(extra="forbid")


class AgentConfig(_Strict):
    name: str
    entrypoint: str = Field(description="'module:callable' returning an agent with .run(task) and .spec")
    options: dict[str, Any] = Field(default_factory=dict, description="Keyword arguments for the entrypoint.")


class EvaluatorConfig(_Strict):
    provider: str = Field(default="ollama", description="'ollama' or 'gemini'.")
    model: str | None = Field(default=None, description="Defaults to the provider's Gemma 4 model.")
    temperature: float = 0.0


class Scenario(_Strict):
    id: str
    task: str


class Config(_Strict):
    agent: AgentConfig
    evaluator: EvaluatorConfig = Field(default_factory=EvaluatorConfig)
    scenarios: list[Scenario] = Field(default_factory=list)
    root: Path = Field(default=Path("."), exclude=True)

    @property
    def contracts_path(self) -> Path:
        return self.root / STATE_DIR / "contracts.json"

    @property
    def baseline_path(self) -> Path:
        return self.root / STATE_DIR / "baseline.json"

    @property
    def lockfile_path(self) -> Path:
        return self.root / "agent.lock"


def load_config(path: str | Path = CONFIG_FILE) -> Config:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run `agentlock init` first.")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    try:
        return Config.model_validate({**data, "root": path.resolve().parent})
    except ValidationError as exc:
        problems = [f"  {'.'.join(map(str, e['loc'])) or '(top level)'}: {e['msg']}" for e in exc.errors()]
        scenarios = data.get("scenarios")
        if isinstance(scenarios, dict) and "scenarios" in scenarios:
            problems.append("  hint: `scenarios:` appears twice (one nested in the other); delete the inner one")
        for key in data.keys() - Config.model_fields.keys():
            for section, model in (("agent", AgentConfig), ("evaluator", EvaluatorConfig)):
                if key in model.model_fields:
                    problems.append(f"  hint: `{key}:` belongs under `{section}:` (indent it by two spaces)")
        raise ValueError(f"{path} is invalid:\n" + "\n".join(problems)) from None


def config_template(name: str, entrypoint: str) -> str:
    return f"""\
# AgentLock configuration
agent:
  name: {name}
  # module:callable returning an object with .run(task) -> str and .spec (an agentlock.AgentSpec)
  entrypoint: {entrypoint}
  options: {{}}

evaluator:
  provider: ollama              # ollama | gemini (needs GEMINI_API_KEY)
  model: {OLLAMA_DEFAULT_MODEL}    # semantic/multimodal contracts are skipped if the model is unavailable

# Representative tasks. Every contract is checked against every scenario it applies to.
scenarios:
  - id: example
    task: "Describe a representative task for your agent here."
"""

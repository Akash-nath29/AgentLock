"""Core data models: agent description, traces, contracts and results."""

from __future__ import annotations

import fnmatch
import time
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter

# --------------------------------------------------------------------------- agent


class ToolSpec(BaseModel):
    """A tool the agent can call. `returns` describes the result shape."""

    name: str
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    returns: str = ""


class SkillSpec(BaseModel):
    name: str
    content: str


class ModelSpec(BaseModel):
    provider: str = ""
    name: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class AgentSpec(BaseModel):
    """Everything that shapes an agent's behavior. Agents expose this as `.spec`."""

    name: str
    model: ModelSpec
    system_prompt: str = ""
    skills: list[SkillSpec] = Field(default_factory=list)
    tools: list[ToolSpec] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)

    @property
    def tool_names(self) -> set[str]:
        return {t.name for t in self.tools}


# --------------------------------------------------------------------------- trace

EventKind = Literal["agent_started", "tool_called", "artifact_recorded", "agent_finished"]


class ToolCall(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: Any = None
    error: str | None = None


class AgentEvent(BaseModel):
    kind: EventKind
    timestamp: float = Field(default_factory=time.time)
    tool_call: ToolCall | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class Trace(BaseModel):
    """The ordered events of one agent run."""

    task: str = ""
    events: list[AgentEvent] = Field(default_factory=list)
    output: str | None = None

    @property
    def tool_calls(self) -> list[ToolCall]:
        return [e.tool_call for e in self.events if e.tool_call is not None]

    @property
    def tool_names(self) -> list[str]:
        return [c.name for c in self.tool_calls]

    @property
    def artifacts(self) -> dict[str, str]:
        return {e.data["name"]: e.data["path"] for e in self.events if e.kind == "artifact_recorded"}

    def sequence(self) -> list[str]:
        """Tool names with consecutive repeats collapsed: read, read, write -> read, write."""
        out: list[str] = []
        for name in self.tool_names:
            if not out or out[-1] != name:
                out.append(name)
        return out


# --------------------------------------------------------------------------- contracts


class _ContractBase(BaseModel):
    id: str
    description: str = ""
    scenarios: list[str] | None = Field(
        default=None, description="Scenario ids this contract applies to; null means all."
    )
    source: str = Field(default="manual", description="'manual' or 'generated:<model>'.")

    def applies_to(self, scenario_id: str) -> bool:
        return self.scenarios is None or scenario_id in self.scenarios


class OrderingContract(_ContractBase):
    """Every call to `after` must be preceded by a call to `before`."""

    type: Literal["ordering"] = "ordering"
    before: str
    after: str
    match_argument: str | None = Field(
        default=None, description="If set, the earlier call must share this argument's value."
    )


class RequiredContract(_ContractBase):
    """`tool` must be called. With `after`, it must follow the last call to `after`
    (and only applies when `after` happened at all)."""

    type: Literal["required"] = "required"
    tool: str
    after: str | None = None


class ForbiddenContract(_ContractBase):
    """`tool` must never be called, or with `arguments`, never with matching arguments."""

    type: Literal["forbidden"] = "forbidden"
    tool: str
    arguments: dict[str, str] | None = Field(
        default=None, description="Glob patterns per argument, e.g. {'path': 'test_*.py'}; all must match."
    )

    def matches(self, call: ToolCall) -> bool:
        if call.name != self.tool:
            return False
        return all(fnmatch.fnmatch(str(call.arguments.get(k, "")), p) for k, p in (self.arguments or {}).items())


class Condition(BaseModel):
    """Holds when a call to `tool` returned a result whose `field` equals `equals`."""

    tool: str
    field: str
    equals: bool | int | float | str

    def matches(self, call: ToolCall) -> bool:
        return isinstance(call.result, dict) and call.result.get(self.field) == self.equals

    def __str__(self) -> str:
        value = str(self.equals).lower() if isinstance(self.equals, bool) else self.equals
        return f"{self.tool}.{self.field} == {value}"


class ConditionalContract(_ContractBase):
    """While `when` holds, none of `forbidden` may be called."""

    type: Literal["conditional"] = "conditional"
    when: Condition
    forbidden: list[str]


class SemanticContract(_ContractBase):
    """Natural-language criteria on the final response, judged by a model."""

    type: Literal["semantic"] = "semantic"
    criteria: list[str]


class MultimodalContract(_ContractBase):
    """Natural-language criteria on an image artifact the agent recorded."""

    type: Literal["multimodal"] = "multimodal"
    artifact: str
    criteria: list[str]


Contract = Annotated[
    Union[
        OrderingContract,
        RequiredContract,
        ForbiddenContract,
        ConditionalContract,
        SemanticContract,
        MultimodalContract,
    ],
    Field(discriminator="type"),
]
DETERMINISTIC_TYPES = {"ordering", "required", "forbidden", "conditional"}
contract_adapter: TypeAdapter[Contract] = TypeAdapter(Contract)
contract_list_adapter: TypeAdapter[list[Contract]] = TypeAdapter(list[Contract])


class ContractSuite(BaseModel):
    """The on-disk contracts file."""

    version: int = 1
    contracts: list[Contract] = Field(default_factory=list)


# --------------------------------------------------------------------------- results

Status = Literal["passed", "failed", "error", "skipped"]


class CriterionResult(BaseModel):
    criterion: str
    passed: bool
    reason: str = ""


class EvaluationResult(BaseModel):
    """What a model evaluator returns for a semantic or multimodal contract."""

    status: Literal["passed", "failed", "error"]
    score: float | None = None
    explanation: str = ""
    criteria: list[CriterionResult] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status == "passed"


class ContractResult(BaseModel):
    contract_id: str
    scenario: str
    status: Status
    expected: str = ""
    observed: str = ""
    explanation: str = ""
    score: float | None = None
    criteria: list[CriterionResult] = Field(default_factory=list)

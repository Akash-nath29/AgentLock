"""Model-evaluator interface, output validation, and an offline mock.

A `ModelEvaluator` does the two jobs Python can't: infer contracts from an
agent's instructions, and judge semantic/multimodal criteria. Everything a model
returns goes through `parse_contracts` / `parse_verdict` — malformed output is
recovered if possible and otherwise reported as an error, never as a pass.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field, ValidationError

from agentlock.models import (
    AgentSpec,
    Contract,
    CriterionResult,
    EvaluationResult,
    MultimodalContract,
    SemanticContract,
    Trace,
    contract_adapter,
)


class EvaluatorUnavailable(RuntimeError):
    """Raised when an evaluator can't be built (e.g. missing credentials)."""


class GenerationResult(BaseModel):
    contracts: list[Contract] = Field(default_factory=list)
    rejected: list[str] = Field(default_factory=list)


class ModelEvaluator(Protocol):
    """What AgentLock needs from a model provider."""

    name: str

    def generate_contracts(self, spec: AgentSpec, examples: list[str]) -> GenerationResult: ...

    def evaluate(self, contract: SemanticContract, trace: Trace) -> EvaluationResult: ...

    def evaluate_image(self, contract: MultimodalContract, image: Path) -> EvaluationResult: ...


# --------------------------------------------------------------------------- parsing


def extract_json(text: str) -> Any:
    """Parse model output as JSON, tolerating code fences and surrounding prose."""
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    if start != -1:
        try:
            return json.JSONDecoder().raw_decode(text[start:])[0]
        except json.JSONDecodeError:
            pass
    raise ValueError(f"no JSON object in model output: {text[:120]!r}")


def referenced_tools(contract: Contract) -> set[str]:
    if contract.type == "ordering":
        return {contract.before, contract.after}
    if contract.type == "required":
        return {contract.tool} | ({contract.after} if contract.after else set())
    if contract.type == "forbidden":
        return {contract.tool}
    if contract.type == "conditional":
        return {contract.when.tool, *contract.forbidden}
    return set()


def parse_contracts(data: Any, spec: AgentSpec, source: str) -> GenerationResult:
    """Validate raw contract dicts from a model. Invalid ones are rejected with a reason."""
    items = data.get("contracts") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError("expected a JSON object with a 'contracts' list")
    result = GenerationResult()
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            result.rejected.append(f"not an object: {item!r:.60}")
            continue
        # Models fill unused fields of the flat schema with null/""; drop those.
        clean = {k: v for k, v in item.items() if v not in (None, "", []) and k not in ("source", "scenarios")}
        cid = clean.get("id", "?")
        try:
            contract = contract_adapter.validate_python({**clean, "source": source})
        except ValidationError as exc:
            err = exc.errors()[0]
            result.rejected.append(f"{cid}: {'.'.join(map(str, err['loc']))} {err['msg']}")
            continue
        unknown = referenced_tools(contract) - spec.tool_names
        if unknown:
            result.rejected.append(f"{cid}: unknown tool(s) {', '.join(sorted(unknown))}")
        elif contract.type == "multimodal":
            result.rejected.append(f"{cid}: multimodal contracts must be written by hand")
        elif contract.id in seen:
            result.rejected.append(f"{cid}: duplicate id")
        else:
            seen.add(contract.id)
            result.contracts.append(contract)
    return result


def parse_verdict(data: Any, criteria: list[str]) -> EvaluationResult:
    """Validate a model's per-criterion verdict. Pass/fail is computed here, not trusted."""
    try:
        items = data["criteria"]
        if not isinstance(items, list) or len(items) != len(criteria):
            raise ValueError(f"expected {len(criteria)} criteria verdicts, got {len(items) if isinstance(items, list) else items!r}")
        results = []
        for criterion, item in zip(criteria, items):
            if not isinstance(item.get("passed"), bool):
                raise ValueError(f"'passed' must be a boolean, got {item.get('passed')!r}")
            results.append(CriterionResult(criterion=criterion, passed=item["passed"], reason=str(item.get("reason", ""))))
        score = data.get("score")
        if score is not None:
            score = float(score)
            if not 0.0 <= score <= 1.0:
                raise ValueError(f"score {score} outside [0, 1]")
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        return EvaluationResult(status="error", explanation=f"malformed evaluator output: {exc}")
    return EvaluationResult(
        status="passed" if all(r.passed for r in results) else "failed",
        score=score,
        explanation=str(data.get("explanation", "")),
        criteria=results,
    )


# --------------------------------------------------------------------------- mock


class MockEvaluator:
    """Offline evaluator for tests. Returns canned contracts and verdicts — no model is consulted."""

    name = "mock"

    def __init__(
        self,
        contracts: list[dict[str, Any]] | None = None,
        verdicts: dict[str, EvaluationResult] | None = None,
    ) -> None:
        self.contracts = contracts or []
        self.verdicts = verdicts or {}
        self.calls: list[str] = []

    def generate_contracts(self, spec: AgentSpec, examples: list[str]) -> GenerationResult:
        self.calls.append("generate_contracts")
        return parse_contracts({"contracts": self.contracts}, spec, source="generated:mock")

    def _verdict(self, contract_id: str, criteria: list[str]) -> EvaluationResult:
        return self.verdicts.get(contract_id) or EvaluationResult(
            status="passed",
            score=1.0,
            explanation="mock verdict (no model consulted)",
            criteria=[CriterionResult(criterion=c, passed=True) for c in criteria],
        )

    def evaluate(self, contract: SemanticContract, trace: Trace) -> EvaluationResult:
        self.calls.append(f"evaluate:{contract.id}")
        return self._verdict(contract.id, contract.criteria)

    def evaluate_image(self, contract: MultimodalContract, image: Path) -> EvaluationResult:
        self.calls.append(f"evaluate_image:{contract.id}")
        return self._verdict(contract.id, contract.criteria)

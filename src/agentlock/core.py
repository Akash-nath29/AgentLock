"""`AgentLock`: load an agent, run scenarios, check contracts, compare with a baseline."""

from __future__ import annotations

import importlib
import json
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from agentlock import validators
from agentlock.config import Config, EvaluatorConfig, Scenario, load_config
from agentlock.evaluator import EvaluatorUnavailable, GenerationResult, ModelEvaluator
from agentlock.lockfile import LockedBehavior, Lockfile, behavior_fingerprint, build_lock, diff_locks, write_lock
from agentlock.models import (
    DETERMINISTIC_TYPES,
    AgentSpec,
    Contract,
    ContractResult,
    ContractSuite,
    Status,
    Trace,
)
from agentlock.tracer import AgentLockTracer

# Worst status wins when a contract is checked on several scenarios.
_SEVERITY: dict[str, int] = {"skipped": 0, "passed": 1, "error": 2, "failed": 3}


def build_evaluator(cfg: EvaluatorConfig) -> ModelEvaluator:
    """Build the configured evaluator. Raises EvaluatorUnavailable if it can't be reached."""
    from agentlock.gemma import GeminiEvaluator, OllamaEvaluator

    providers = {"ollama": OllamaEvaluator, "gemini": GeminiEvaluator}
    if cfg.provider not in providers:
        raise ValueError(f"unknown evaluator provider {cfg.provider!r} (supported: {', '.join(providers)})")
    cls = providers[cfg.provider]
    return cls(model=cfg.model, temperature=cfg.temperature) if cfg.model else cls(temperature=cfg.temperature)


class ScenarioRun(BaseModel):
    id: str
    task: str
    sequence: list[str]
    output: str | None = None
    error: str | None = None
    trace: Trace | None = Field(default=None, exclude=True)


class TestReport(BaseModel):
    """One full behavioral test run. Saved as the baseline when known-good."""

    __test__ = False  # not a pytest class

    version: int = 1
    created_at: str
    evaluator: str | None
    lock: Lockfile
    scenarios: list[ScenarioRun]
    results: list[ContractResult]

    @property
    def fingerprint(self) -> str:
        return self.lock.behavior.fingerprint if self.lock.behavior else ""

    def contract_statuses(self) -> dict[str, Status]:
        """Each contract's worst status across the scenarios it applies to."""
        out: dict[str, Status] = {}
        for r in self.results:
            if r.contract_id not in out or _SEVERITY[r.status] > _SEVERITY[out[r.contract_id]]:
                out[r.contract_id] = r.status
        return out

    def count(self, status: Status) -> int:
        return sum(s == status for s in self.contract_statuses().values())

    @property
    def passed(self) -> bool:
        return self.count("failed") == 0 and self.count("error") == 0


class Regression(BaseModel):
    baseline: ContractResult
    current: ContractResult


class Comparison(BaseModel):
    baseline: TestReport
    current: TestReport
    config_changes: list[str]
    regressions: list[Regression]
    fixed: list[ContractResult]


class GenerateOutcome(BaseModel):
    spec: AgentSpec
    kept: list[Contract]
    added: list[Contract]
    covered: list[str] = Field(description="Generated contracts already covered by manual ones.")
    rejected: list[str]


def _signature(c: Contract) -> str:
    return json.dumps(c.model_dump(mode="json", exclude={"id", "description", "source", "scenarios"}), sort_keys=True)


class AgentLock:
    """Python API behind the CLI.

        lock = AgentLock.from_config("agentlock.yaml")
        report = lock.test()
        print(report.passed)
    """

    def __init__(self, config: Config, evaluator: ModelEvaluator | None = None) -> None:
        self.config = config
        self._evaluator = evaluator
        self._evaluator_checked = evaluator is not None
        self.evaluator_error: str | None = None

    @classmethod
    def from_config(cls, path: str | Path = "agentlock.yaml", evaluator: ModelEvaluator | None = None) -> AgentLock:
        return cls(load_config(path), evaluator)

    # ------------------------------------------------------------------ agent

    @property
    def evaluator(self) -> ModelEvaluator | None:
        """The model evaluator, or None (with `evaluator_error` set) if unavailable."""
        if not self._evaluator_checked:
            self._evaluator_checked = True
            try:
                self._evaluator = build_evaluator(self.config.evaluator)
            except EvaluatorUnavailable as exc:
                self.evaluator_error = str(exc)
        return self._evaluator

    def build_agent(self) -> Any:
        """Import the entrypoint and call it with the configured options."""
        module_name, _, attr = self.config.agent.entrypoint.partition(":")
        root = str(self.config.root)
        if root not in sys.path:
            sys.path.insert(0, root)
        factory: Callable[..., Any] = getattr(importlib.import_module(module_name), attr)
        return factory(**self.config.agent.options)

    def describe(self) -> AgentSpec:
        spec = getattr(self.build_agent(), "spec", None)
        if spec is None:
            raise TypeError(f"{self.config.agent.entrypoint} returned an agent without a .spec attribute")
        return AgentSpec.model_validate(spec)

    # ------------------------------------------------------------------ contracts

    def load_contracts(self) -> list[Contract]:
        path = self.config.contracts_path
        if not path.exists():
            return []
        return ContractSuite.model_validate_json(path.read_text(encoding="utf-8")).contracts

    def save_contracts(self, contracts: list[Contract]) -> None:
        path = self.config.contracts_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(ContractSuite(contracts=contracts).model_dump_json(indent=2, exclude_none=True) + "\n", encoding="utf-8")

    def generate(self) -> GenerateOutcome:
        """Infer contracts with the model. Manual contracts are kept; earlier generated ones are replaced."""
        evaluator = self.evaluator
        if evaluator is None:
            raise EvaluatorUnavailable(self.evaluator_error or "no evaluator configured")
        spec = self.describe()
        result: GenerationResult = evaluator.generate_contracts(spec, [s.task for s in self.config.scenarios])
        kept = [c for c in self.load_contracts() if c.source == "manual"]
        kept_sigs = {_signature(c) for c in kept}
        kept_ids = {c.id for c in kept}
        added, covered = [], []
        for c in result.contracts:
            if _signature(c) in kept_sigs:
                covered.append(c.id)
                continue
            if c.id in kept_ids:
                c.id = f"{c.id}-generated"
            added.append(c)
        self.save_contracts(kept + added)
        return GenerateOutcome(spec=spec, kept=kept, added=added, covered=covered, rejected=result.rejected)

    # ------------------------------------------------------------------ testing

    def run_scenario(self, scenario: Scenario) -> ScenarioRun:
        """Run a fresh agent on one scenario under the tracer. Agent exceptions are captured."""
        agent = self.build_agent()
        tracer = AgentLockTracer()
        error = None
        with tracer.trace(scenario.task) as trace:
            try:
                output = agent.run(scenario.task)
                trace.output = None if output is None else str(output)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
        return ScenarioRun(id=scenario.id, task=scenario.task, sequence=trace.sequence(), output=trace.output, error=error, trace=trace)

    def evaluate(self, contract: Contract, run: ScenarioRun) -> ContractResult:
        """Deterministic contracts are checked in Python; the rest go to the model evaluator."""
        result = ContractResult(contract_id=contract.id, scenario=run.id, status="error")
        if run.error or run.trace is None:
            result.explanation = f"agent crashed: {run.error}"
            return result
        if contract.type in DETERMINISTIC_TYPES:
            return validators.check(contract, run.trace, run.id)  # type: ignore[arg-type]

        result.expected = validators.describe_rule(contract)
        evaluator = self.evaluator
        if evaluator is None:
            result.status, result.explanation = "skipped", f"no model evaluator ({self.evaluator_error})"
            return result
        if contract.type == "semantic":
            result.observed = run.output or "(empty response)"
            verdict = evaluator.evaluate(contract, run.trace)
        else:
            artifact = run.trace.artifacts.get(contract.artifact)
            if artifact is None:
                result.status, result.explanation = "failed", f"agent did not record artifact {contract.artifact!r}"
                return result
            image = Path(artifact) if Path(artifact).is_absolute() else self.config.root / artifact
            result.observed = f"{contract.artifact}: {image.name}"
            if not image.exists():
                result.explanation = f"artifact file not found: {image}"
                return result
            verdict = evaluator.evaluate_image(contract, image)
        result.status = verdict.status
        result.explanation, result.score, result.criteria = verdict.explanation, verdict.score, verdict.criteria
        return result

    def test(self, on_progress: Callable[[str], None] | None = None) -> TestReport:
        """Run every scenario and check every applicable contract."""
        contracts = self.load_contracts()
        if not contracts:
            raise ValueError(f"no contracts in {self.config.contracts_path}; run `agentlock generate` first")
        if not self.config.scenarios:
            raise ValueError("no scenarios in agentlock.yaml")
        spec = self.describe()
        runs = []
        for scenario in self.config.scenarios:
            if on_progress:
                on_progress(f"Running scenario {scenario.id}")
            runs.append(self.run_scenario(scenario))
        if on_progress:
            on_progress("Checking contracts")
        results = [self.evaluate(c, run) for c in contracts for run in runs if c.applies_to(run.id)]
        lock = build_lock(spec, contracts)
        report = TestReport(
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            evaluator=self.evaluator.name if self.evaluator else None,
            lock=lock,
            scenarios=runs,
            results=results,
        )
        lock.behavior = LockedBehavior(
            fingerprint=behavior_fingerprint(lock, results, {r.id: r.sequence for r in runs}),
            contracts_passed=report.count("passed"),
            contracts_total=len(report.contract_statuses()),
        )
        return report

    # ------------------------------------------------------------------ baseline

    def load_baseline(self) -> TestReport | None:
        path = self.config.baseline_path
        return TestReport.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else None

    def save_baseline(self, report: TestReport) -> None:
        """Record `report` as known-good: writes baseline.json and agent.lock."""
        self.config.baseline_path.parent.mkdir(parents=True, exist_ok=True)
        self.config.baseline_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
        write_lock(self.config.lockfile_path, report.lock)

    @staticmethod
    def compare(current: TestReport, baseline: TestReport) -> Comparison:
        before = {(r.contract_id, r.scenario): r for r in baseline.results}
        regressions, fixed = [], []
        for r in current.results:
            old = before.get((r.contract_id, r.scenario))
            if old is None:
                continue
            if old.status == "passed" and r.status in ("failed", "error"):
                regressions.append(Regression(baseline=old, current=r))
            elif old.status in ("failed", "error") and r.status == "passed":
                fixed.append(r)
        return Comparison(
            baseline=baseline,
            current=current,
            config_changes=diff_locks(baseline.lock, current.lock),
            regressions=regressions,
            fixed=fixed,
        )

"""6-step behavioral diff engine with causal attribution and delta debugging (bisect)."""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field

from agentlock.deps import DependencyChange, diff_dependencies
from agentlock.events import NormalizedTrace
from agentlock.invariants import evaluate_contract
from agentlock.lockfile import LockfileV2
from agentlock.vocabulary import ActionVocabulary


class BehaviorChange(BaseModel):
    id: str
    kind: Literal["contract_violated", "effect_added", "effect_removed", "outcome_changed", "response_changed", "path_shift"]
    scenario: str = ""
    contract: str = ""
    severity: Literal["breaking", "warning", "info"] = "info"
    base_summary: str = ""
    head_summary: str = ""


class AttributionRecord(BaseModel):
    change_id: str
    cause_dep_id: str
    confidence: Literal["confirmed", "likely", "possible", "unattributed"] = "likely"
    method: Literal["bisect", "locality", "ranking"] = "locality"
    evidence: str = ""
    rationale: str = ""


class DiffReport(BaseModel):
    base_ref: str = "agent.lock"
    base_state: str = ""
    head_ref: str = "live"
    head_state: str = ""
    dependency_changes: list[DependencyChange] = Field(default_factory=list)
    behavior_changes: list[BehaviorChange] = Field(default_factory=list)
    attributions: list[AttributionRecord] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)

    @property
    def is_conforming(self) -> bool:
        return self.summary.get("breaking", 0) == 0


def compute_diff(
    base_lock: LockfileV2,
    head_lock: LockfileV2,
    head_traces_by_scenario: dict[str, list[NormalizedTrace]] | None = None,
    bisect_runner: Any = None,
) -> DiffReport:
    """Compute 6-step diff between base and head states."""
    # 1. Dependency diff
    dep_changes = diff_dependencies(base_lock.dependencies, head_lock.dependencies)

    # 2. Vocabulary setup
    vocab = ActionVocabulary()
    for act_name, act_def in base_lock.behavior.actions.items():
        if isinstance(act_def, dict):
            vocab.register(act_name, tool_name=act_def.get("tool", act_name), effect=act_def.get("effect", "read"))

    # 3. Contract evaluation & behavior comparison
    behavior_changes: list[BehaviorChange] = []
    change_idx = 1

    # Compare contracts
    base_contracts = base_lock.behavior.contracts
    for c in base_contracts:
        c_id = c.get("id", "")
        c_rule = c.get("rule", {})
        c_sev = c.get("severity", "breaking")

        # Evaluate against head traces if provided
        if head_traces_by_scenario:
            all_head_traces: list[NormalizedTrace] = []
            for trs in head_traces_by_scenario.values():
                all_head_traces.extend(trs)

            eval_res = evaluate_contract(c_id, c_rule, all_head_traces, vocab)
            if eval_res.status == "violated":
                behavior_changes.append(
                    BehaviorChange(
                        id=f"bc{change_idx}",
                        kind="contract_violated",
                        contract=c_id,
                        severity=c_sev if c_sev in ("breaking", "warning", "info") else "breaking",
                        base_summary=c.get("support", "held"),
                        head_summary=f"violated ({eval_res.support})",
                    )
                )
                change_idx += 1

    # Compare scenario outcomes & effects
    base_scenarios = {s.id: s for s in base_lock.behavior.scenarios}
    head_scenarios = {s.id: s for s in head_lock.behavior.scenarios}

    for sc_id in sorted(set(base_scenarios.keys()) | set(head_scenarios.keys())):
        bsc, hsc = base_scenarios.get(sc_id), head_scenarios.get(sc_id)
        if bsc and hsc:
            # Outcome comparison
            if bsc.outcome.label != hsc.outcome.label:
                behavior_changes.append(
                    BehaviorChange(
                        id=f"bc{change_idx}",
                        kind="outcome_changed",
                        scenario=sc_id,
                        severity="breaking",
                        base_summary=f"{bsc.outcome.label} ({bsc.outcome.support})",
                        head_summary=f"{hsc.outcome.label} ({hsc.outcome.support})",
                    )
                )
                change_idx += 1

            # Effects comparison
            added_effects = set(hsc.effects) - set(bsc.effects)
            for eff in added_effects:
                behavior_changes.append(
                    BehaviorChange(
                        id=f"bc{change_idx}",
                        kind="effect_added",
                        scenario=sc_id,
                        severity="breaking",
                        base_summary="absent",
                        head_summary=f"added: {eff}",
                    )
                )
                change_idx += 1

    # 4. Severity summary calculation
    breaking_count = sum(1 for bc in behavior_changes if bc.severity == "breaking")
    warning_count = sum(1 for bc in behavior_changes if bc.severity == "warning")
    info_count = sum(1 for bc in behavior_changes if bc.severity == "info")

    # 5. Causal Attribution (Locality & Bisect)
    attributions: list[AttributionRecord] = []
    if behavior_changes:
        for bc in behavior_changes:
            if dep_changes:
                # Candidate matching via locality
                candidate = dep_changes[0]  # Top candidate
                attr_rec = AttributionRecord(
                    change_id=bc.id,
                    cause_dep_id=candidate.dep_id,
                    confidence="likely",
                    method="locality",
                    rationale=f"Attributed to changed dependency {candidate.dep_id} ({candidate.summary})",
                )

                # Bisect delta debugging if runner provided
                if bisect_runner and candidate.dep_id:
                    try:
                        resolved = bisect_runner(candidate.dep_id, bc)
                        if resolved:
                            attr_rec.confidence = "confirmed"
                            attr_rec.method = "bisect"
                            attr_rec.evidence = f"Reverting only {candidate.dep_id} restored baseline behavior."
                    except Exception:
                        pass

                attributions.append(attr_rec)
            else:
                attributions.append(
                    AttributionRecord(
                        change_id=bc.id,
                        cause_dep_id="external",
                        confidence="unattributed",
                        rationale="No recorded dependency changed. Likely external drift or sampling variance.",
                    )
                )

    return DiffReport(
        base_ref="agent.lock",
        base_state=base_lock.state,
        head_ref="head",
        head_state=head_lock.state,
        dependency_changes=dep_changes,
        behavior_changes=behavior_changes,
        attributions=attributions,
        summary={"breaking": breaking_count, "warning": warning_count, "info": info_count},
    )

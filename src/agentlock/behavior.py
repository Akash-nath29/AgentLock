"""L3 scenario behavior reduction and L5 behavior fingerprint calculation."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from pydantic import BaseModel, Field
from agentlock.events import NormalizedTrace
from agentlock.vocabulary import ActionVocabulary


class OutcomeSpec(BaseModel):
    label: str
    support: str = "1/1"


class PathSpec(BaseModel):
    steps: list[str] = Field(default_factory=list)
    support: str = "1/1"


class ScenarioBehavior(BaseModel):
    id: str
    input: str
    entities: dict[str, str] = Field(default_factory=dict)
    outcome: OutcomeSpec
    effects: list[str] = Field(default_factory=list)
    paths: list[PathSpec] = Field(default_factory=list)
    response: dict[str, str] = Field(default_factory=dict)


class BehaviorBasis(BaseModel):
    scenarios: int
    samples: int
    judge: str = "gemma4:31b-cloud"


class BehaviorState(BaseModel):
    fingerprint: str = ""
    basis: BehaviorBasis
    actions: dict[str, Any] = Field(default_factory=dict)
    scenarios: list[ScenarioBehavior] = Field(default_factory=list)
    contracts: list[dict[str, Any]] = Field(default_factory=list)

    def compute_fingerprint(self) -> str:
        """Compute SHA-256 fingerprint over discrete behavioral outcomes & effects."""
        payload = {
            "scenarios": [
                {
                    "id": s.id,
                    "outcome": s.outcome.label,
                    "effects": sorted(s.effects),
                }
                for s in sorted(self.scenarios, key=lambda x: x.id)
            ],
            "contracts": [
                {
                    "id": c.get("id"),
                    "rule": c.get("rule"),
                    "severity": c.get("severity"),
                }
                for c in sorted(self.contracts, key=lambda x: x.get("id", ""))
            ],
        }
        serialized = json.dumps(payload, sort_keys=True)
        digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        self.fingerprint = f"sha256:{digest}"
        return self.fingerprint


def reduce_scenario_traces(
    scenario_id: str,
    input_text: str,
    entities: dict[str, str],
    traces: list[NormalizedTrace],
    vocab: ActionVocabulary,
    outcome_label: str = "completed",
    response_summary: str = "",
) -> ScenarioBehavior:
    """Reduce N normalized traces of a scenario to an L3 scenario behavior model."""
    total = len(traces)
    if total == 0:
        return ScenarioBehavior(
            id=scenario_id,
            input=input_text,
            entities=entities,
            outcome=OutcomeSpec(label="no_runs", support="0/0"),
            effects=[],
            paths=[],
        )

    # Calculate paths and support counts
    path_counts: dict[tuple[str, ...], int] = {}
    effect_sequences: list[list[str]] = []

    for trace in traces:
        steps: list[str] = []
        non_read_actions: list[str] = []
        for call in trace.calls:
            action, effect = vocab.resolve_action(call.tool, call.arguments)
            steps.append(action)
            if effect != "read":
                non_read_actions.append(action)

        tup = tuple(steps)
        path_counts[tup] = path_counts.get(tup, 0) + 1
        effect_sequences.append(non_read_actions)

    paths_list = [
        PathSpec(steps=list(path), support=f"{count}/{total}")
        for path, count in sorted(path_counts.items(), key=lambda item: item[1], reverse=True)
    ]

    # Compute effect partial order (side-effects present in all samples)
    all_effects_set = set(effect_sequences[0]) if effect_sequences else set()
    for seq in effect_sequences[1:]:
        all_effects_set &= set(seq)

    effects_summary: list[str] = []
    sorted_effects = sorted(all_effects_set)
    for eff in sorted_effects:
        effects_summary.append(eff)

    # Check pair-wise ordering constraints across all samples
    for i in range(len(sorted_effects)):
        for j in range(i + 1, len(sorted_effects)):
            a, b = sorted_effects[i], sorted_effects[j]
            # check if a always precedes b
            always_a_before_b = True
            for seq in effect_sequences:
                if a in seq and b in seq:
                    if seq.index(a) > seq.index(b):
                        always_a_before_b = False
                        break
            if always_a_before_b and a in sorted_effects and b in sorted_effects:
                order_clause = f"{b} after {a}"
                if order_clause not in effects_summary:
                    effects_summary.append(order_clause)

    return ScenarioBehavior(
        id=scenario_id,
        input=input_text,
        entities=entities,
        outcome=OutcomeSpec(label=outcome_label, support=f"{total}/{total}"),
        effects=effects_summary,
        paths=paths_list,
        response={"summary": response_summary},
    )

"""L4 Invariant mining and rule evaluation engine."""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field
from agentlock.events import NormalizedTrace
from agentlock.vocabulary import ActionVocabulary


class MinedRule(BaseModel):
    id: str
    statement: str
    rule: dict[str, Any]
    scope: str = "all"
    severity: Literal["breaking", "warning", "info"] = "breaking"
    support: str = "0/0"
    origin: dict[str, Any] = Field(default_factory=lambda: {"mined": True})


class ContractEvaluation(BaseModel):
    contract_id: str
    status: Literal["held", "violated", "not_exercised"]
    support: str
    observed: str = ""
    explanation: str = ""


def mine_invariants(traces_by_scenario: dict[str, list[NormalizedTrace]], vocab: ActionVocabulary) -> list[MinedRule]:
    """Deterministically mine invariants (precedence, absence, conditional absence) from trace samples."""
    mined: list[MinedRule] = []

    all_traces: list[NormalizedTrace] = []
    for tr_list in traces_by_scenario.values():
        all_traces.extend(tr_list)

    total_runs = len(all_traces)
    if total_runs == 0:
        return mined

    # Collect action sequences and non-read actions
    action_seqs: list[list[str]] = []
    non_read_actions_set: set[str] = set()

    for tr in all_traces:
        seq = [vocab.resolve_action(c.tool, c.arguments)[0] for c in tr.calls]
        action_seqs.append(seq)
        for c in tr.calls:
            act, eff = vocab.resolve_action(c.tool, c.arguments)
            if eff in ("write", "external", "irreversible"):
                non_read_actions_set.add(act)

    rule_idx = 1

    # 1. Absence rules: non-read actions that NEVER occurred in any trace
    # (Check actions in vocab that were never called)
    all_vocab_actions = set(vocab.actions.keys())
    for act in sorted(all_vocab_actions):
        eff = vocab.actions[act].effect
        if eff in ("external", "irreversible"):
            never_called = all(act not in seq for seq in action_seqs)
            if never_called:
                mined.append(
                    MinedRule(
                        id=f"mined-{rule_idx}",
                        statement=f"The agent never performs action {act}.",
                        rule={"never": act},
                        severity="breaking",
                        support=f"{total_runs}/{total_runs}",
                    )
                )
                rule_idx += 1

    # 2. Precedence rules: if action B (side-effect) occurred, action A (read/verify) always preceded it
    for b_act in sorted(non_read_actions_set):
        # find actions that precede b_act in all runs where b_act occurs
        runs_with_b = [seq for seq in action_seqs if b_act in seq]
        if not runs_with_b:
            continue

        possible_precedents = set(runs_with_b[0][: runs_with_b[0].index(b_act)])
        for seq in runs_with_b[1:]:
            b_idx = seq.index(b_act)
            possible_precedents &= set(seq[:b_idx])

        for a_act in sorted(possible_precedents):
            if a_act != b_act:
                mined.append(
                    MinedRule(
                        id=f"mined-{rule_idx}",
                        statement=f"Action {a_act} precedes {b_act}.",
                        rule={"before": a_act, "after": b_act},
                        severity="breaking",
                        support=f"{len(runs_with_b)}/{len(runs_with_b)}",
                    )
                )
                rule_idx += 1

    return mined


def evaluate_rule_on_trace(rule: dict[str, Any], trace: NormalizedTrace, vocab: ActionVocabulary) -> bool:
    """Evaluate a single rule dictionary on a normalized trace. Returns True if rule holds, False if violated."""
    calls = trace.calls
    actions = [vocab.resolve_action(c.tool, c.arguments)[0] for c in calls]

    # Rule: never
    if "never" in rule:
        forbidden = rule["never"]
        return forbidden not in actions

    # Rule: before / after
    if "before" in rule and "after" in rule:
        before_act = rule["before"]
        after_act = rule["after"]
        same_arg = rule.get("same")

        for idx, act in enumerate(actions):
            if act == after_act:
                # Need an earlier call to before_act
                matching_before = False
                for prev_idx in range(idx):
                    if actions[prev_idx] == before_act:
                        if same_arg:
                            # Match argument value
                            curr_arg_val = calls[idx].arguments.get(same_arg, "")
                            prev_arg_val = calls[prev_idx].arguments.get(same_arg, "")
                            if curr_arg_val and prev_arg_val and str(curr_arg_val) == str(prev_arg_val):
                                matching_before = True
                                break
                        else:
                            matching_before = True
                            break
                if not matching_before:
                    return False
        return True

    # Rule: when ... never
    if "when" in rule and "never" in rule:
        cond = rule["when"]
        cond_act = cond.get("action", cond.get("tool"))
        result_cond = cond.get("result", {})
        forbidden = rule["never"]

        when_triggered = False
        for c in calls:
            act, _ = vocab.resolve_action(c.tool, c.arguments)
            if act == cond_act:
                # Check result condition
                all_match = True
                for k, v in result_cond.items():
                    if c.result_facts.get(k) != v:
                        all_match = False
                        break
                if all_match:
                    when_triggered = True
            if when_triggered and act == forbidden:
                return False
        return True

    return True


def evaluate_contract(
    contract_id: str,
    rule: dict[str, Any],
    traces: list[NormalizedTrace],
    vocab: ActionVocabulary,
) -> ContractEvaluation:
    """Evaluate contract rule across a list of traces."""
    if not traces:
        return ContractEvaluation(contract_id=contract_id, status="not_exercised", support="0/0")

    passed_count = 0
    total = len(traces)

    for tr in traces:
        if evaluate_rule_on_trace(rule, tr, vocab):
            passed_count += 1

    status: Literal["held", "violated", "not_exercised"] = "held" if passed_count == total else "violated"
    return ContractEvaluation(
        contract_id=contract_id,
        status=status,
        support=f"{passed_count}/{total}",
        explanation="" if status == "held" else f"Violated in {total - passed_count} of {total} runs.",
    )

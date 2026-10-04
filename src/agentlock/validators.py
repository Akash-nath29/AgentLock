"""Deterministic contract checks. Plain Python over the trace, no model involved."""

from __future__ import annotations

from agentlock.models import (
    ConditionalContract,
    Contract,
    ContractResult,
    ForbiddenContract,
    OrderingContract,
    RequiredContract,
    Trace,
)

ARROW = " → "

DeterministicContract = OrderingContract | RequiredContract | ForbiddenContract | ConditionalContract


def format_sequence(names: list[str]) -> str:
    return ARROW.join(names) if names else "(no tool calls)"


def describe_rule(contract: Contract) -> str:
    """One-line statement of what a contract expects."""
    c = contract
    if c.type == "ordering":
        return f"{c.before}{ARROW}{c.after}" + (f" (same {c.match_argument})" if c.match_argument else "")
    if c.type == "required":
        return f"{c.after}{ARROW}{c.tool}" if c.after else f"{c.tool} is called"
    if c.type == "forbidden":
        args = ", ".join(f"{k}={v}" for k, v in (c.arguments or {}).items())
        return f"never {c.tool}" + (f"({args})" if args else "")
    if c.type == "conditional":
        return f"{c.when} ⇒ no {', '.join(c.forbidden)}"
    if c.type == "multimodal":
        return f"artifact {c.artifact!r}: " + "; ".join(c.criteria)
    return "; ".join(c.criteria)


def check(contract: DeterministicContract, trace: Trace, scenario: str) -> ContractResult:
    """Check one deterministic contract against one trace."""
    checker = {
        "ordering": _ordering,
        "required": _required,
        "forbidden": _forbidden,
        "conditional": _conditional,
    }[contract.type]
    status, explanation = checker(contract, trace)  # type: ignore[operator]
    return ContractResult(
        contract_id=contract.id,
        scenario=scenario,
        status=status,
        expected=describe_rule(contract),
        observed=format_sequence(trace.sequence()),
        explanation=explanation,
    )


def _ordering(c: OrderingContract, trace: Trace) -> tuple[str, str]:
    calls = trace.tool_calls
    for i, call in enumerate(calls):
        if call.name != c.after:
            continue
        earlier = [p for p in calls[:i] if p.name == c.before]
        if c.match_argument:
            value = call.arguments.get(c.match_argument)
            # Models mix "1001" and 1001 for the same id; compare as strings.
            earlier = [p for p in earlier if str(p.arguments.get(c.match_argument)) == str(value)]
            if not earlier:
                return "failed", f"{c.after}({c.match_argument}={value!r}) without a prior {c.before} of it"
        if not earlier:
            return "failed", f"{c.after} was called before any {c.before}"
    return "passed", ""


def _required(c: RequiredContract, trace: Trace) -> tuple[str, str]:
    names = trace.tool_names
    if c.after is None:
        return ("passed", "") if c.tool in names else ("failed", f"{c.tool} was never called")
    if c.after not in names:
        return "passed", f"not triggered: {c.after} was never called"
    last_trigger = len(names) - 1 - names[::-1].index(c.after)
    if c.tool in names[last_trigger + 1 :]:
        return "passed", ""
    return "failed", f"{c.tool} was not called after the last {c.after}"


def _forbidden(c: ForbiddenContract, trace: Trace) -> tuple[str, str]:
    hits = [call for call in trace.tool_calls if c.matches(call)]
    if not hits:
        return "passed", ""
    args = ", ".join(f"{k}={hits[0].arguments.get(k)!r}" for k in (c.arguments or {}))
    return "failed", f"{c.tool}({args}) was called {len(hits)}x"


def _conditional(c: ConditionalContract, trace: Trace) -> tuple[str, str]:
    calls = trace.tool_calls
    condition_calls = [(i, call) for i, call in enumerate(calls) if call.name == c.when.tool]
    for i, call in enumerate(calls):
        if call.name not in c.forbidden:
            continue
        # The governing condition is the closest preceding check; if the action came
        # before any check, the next check reports the state it acted on.
        before = [cc for j, cc in condition_calls if j < i]
        after = [cc for j, cc in condition_calls if j > i]
        governing = before[-1] if before else (after[0] if after else None)
        if governing is not None and c.when.matches(governing):
            return "failed", f"{call.name} was called while {c.when}"
    return "passed", ""

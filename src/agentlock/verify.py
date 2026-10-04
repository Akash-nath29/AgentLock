"""Verification engine for checking agent behavior against agent.lock."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel

from agentlock.diff import DiffReport, compute_diff
from agentlock.events import NormalizedTrace
from agentlock.lockfile import LockfileV2

VerdictType = Literal["CONFORMS", "CONFORMS WITH DRIFT", "VIOLATES", "INCONCLUSIVE"]


class VerificationResult(BaseModel):
    verdict: VerdictType
    exit_code: int
    deps_match: bool = True
    contracts_passed: int = 0
    total_contracts: int = 0
    fingerprint_match: bool = True
    diff_report: DiffReport | None = None
    summary_message: str = ""


def verify_agent(
    locked_state: LockfileV2,
    live_state: LockfileV2,
    live_traces_by_scenario: dict[str, list[NormalizedTrace]] | None = None,
    deps_only: bool = False,
    strict: bool = False,
) -> VerificationResult:
    """Verify live agent state against locked state."""
    # Check dependencies first
    diff = compute_diff(locked_state, live_state, live_traces_by_scenario)

    deps_match = len(diff.dependency_changes) == 0

    if deps_only:
        if deps_match:
            return VerificationResult(
                verdict="CONFORMS",
                exit_code=0,
                deps_match=True,
                diff_report=diff,
                summary_message="Dependencies match the lock.",
            )
        else:
            return VerificationResult(
                verdict="VIOLATES",
                exit_code=1,
                deps_match=False,
                diff_report=diff,
                summary_message=f"Dependencies out of sync ({len(diff.dependency_changes)} changes).",
            )

    # Full behavioral verification
    fingerprint_match = locked_state.behavior.fingerprint == live_state.behavior.fingerprint
    breaking_count = diff.summary.get("breaking", 0)
    warning_count = diff.summary.get("warning", 0)

    total_contracts = len(locked_state.behavior.contracts)
    passed_contracts = total_contracts - breaking_count - warning_count

    if breaking_count > 0:
        verdict: VerdictType = "VIOLATES"
        exit_code = 1
        msg = f"Behavior violates lock ({breaking_count} breaking changes)."
    elif not deps_match or warning_count > 0:
        if strict:
            verdict = "VIOLATES"
            exit_code = 1
            msg = "Strict check failed due to dependency drift or warnings."
        else:
            verdict = "CONFORMS WITH DRIFT"
            exit_code = 0
            msg = "Behavior conforms with minor drift or warnings."
    else:
        verdict = "CONFORMS"
        exit_code = 0
        msg = "Agent fully conforms to locked state."

    return VerificationResult(
        verdict=verdict,
        exit_code=exit_code,
        deps_match=deps_match,
        contracts_passed=max(0, passed_contracts),
        total_contracts=total_contracts,
        fingerprint_match=fingerprint_match,
        diff_report=diff,
        summary_message=msg,
    )

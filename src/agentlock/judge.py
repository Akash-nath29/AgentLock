"""Gemma Judge engine handling tasks G1-G7 with structured output validation and cache."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from agentlock.gemma import GemmaEvaluator, OllamaEvaluator, GeminiEvaluator


def extract_json_payload(text: str) -> dict[str, Any]:
    """Tolerates code fences and surrounding prose to extract a JSON object."""
    if not text:
        return {}
    cleaned = text.strip()
    if "```" in cleaned:
        parts = cleaned.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{") and part.endswith("}"):
                cleaned = part
                break

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]

    try:
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


class GemmaJudge:
    """Judge backend wrapping OllamaEvaluator / GeminiEvaluator for G1-G7 tasks."""

    def __init__(self, provider: str = "ollama", model: str = "gemma4:31b-cloud", temperature: float = 0.0, cache_dir: Path | str | None = None):
        self.provider = provider
        self.model_name = model
        self.temperature = temperature
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        self._evaluator: GemmaEvaluator | None = None

    def _get_evaluator(self) -> GemmaEvaluator | None:
        if self._evaluator is not None:
            return self._evaluator
        try:
            if self.provider == "ollama":
                self._evaluator = OllamaEvaluator(model=self.model_name, temperature=self.temperature, check=False)
            elif self.provider == "gemini":
                self._evaluator = GeminiEvaluator(model=self.model_name, temperature=self.temperature)
        except Exception:
            self._evaluator = None
        return self._evaluator

    def _query(self, system: str, user_text: str) -> str:
        # Check cache if enabled
        key = hashlib.sha256(f"{system}:{user_text}".encode("utf-8")).hexdigest()
        if self.cache_dir:
            cache_file = self.cache_dir / f"{key}.json"
            if cache_file.exists():
                return cache_file.read_text(encoding="utf-8")

        evaluator = self._get_evaluator()
        if evaluator is None:
            return ""

        try:
            res = evaluator._complete(system, user_text, schema={})
            if self.cache_dir and res:
                (self.cache_dir / f"{key}.json").write_text(res, encoding="utf-8")
            return res
        except Exception:
            return ""

    # G1: Label action & effect class
    def label_action(self, tool_name: str, description: str, schema: dict[str, Any], example_args: list[dict[str, Any]]) -> tuple[str, str]:
        system = (
            "You are an action classifier. Given a tool name, description, schema, and example args, "
            "propose a semantic action label and an effect class ('read', 'write', 'external', 'irreversible'). "
            'Respond with JSON: {"action": "...", "effect": "read"|"write"|"external"|"irreversible"}'
        )
        user = json.dumps({"tool": tool_name, "description": description, "schema": schema, "examples": example_args})
        raw = self._query(system, user)
        data = extract_json_payload(raw)
        act = data.get("action", tool_name)
        eff = data.get("effect", "write")
        if eff not in ("read", "write", "external", "irreversible"):
            eff = "write"
        return act, eff

    # G2: Label outcome and summarize reply
    def label_outcome_and_reply(self, scenario_input: str, effects: list[str], reply: str) -> tuple[str, str]:
        system = (
            "Given a scenario input, side effects, and final reply, provide an outcome label (e.g. 'refund_issued', 'declined') "
            'and a one-sentence summary of the reply. Respond with JSON: {"outcome": "...", "summary": "..."}'
        )
        user = json.dumps({"input": scenario_input, "effects": effects, "reply": reply})
        raw = self._query(system, user)
        data = extract_json_payload(raw)
        out = data.get("outcome", "completed")
        summary = data.get("summary", reply[:100] if reply else "No response text")
        return out, summary

    # G3: Curate contracts from mined invariants
    def curate_contracts(self, mined_invariants: list[dict[str, Any]], prompt_text: str, skill_text: str) -> list[dict[str, Any]]:
        system = (
            "Select salient invariants that matter from mined list according to prompt/skill rules. "
            'Respond with JSON: {"contracts": [{"id": "...", "statement": "...", "severity": "breaking"|"warning", "rule": {...}}]}'
        )
        user = json.dumps({"mined": mined_invariants, "prompt": prompt_text, "skills": skill_text})
        raw = self._query(system, user)
        data = extract_json_payload(raw)
        contracts = data.get("contracts", [])
        if isinstance(contracts, list) and contracts:
            return contracts
        return mined_invariants

    # G4: Judge response rules
    def judge_response_rule(self, criteria: list[str], trace_summary: str, reply: str) -> tuple[bool, str]:
        system = (
            "Judge whether reply satisfies criteria given trace summary. "
            'Respond with JSON: {"passed": true|false, "reason": "..."}'
        )
        user = json.dumps({"criteria": criteria, "trace": trace_summary, "reply": reply})
        raw = self._query(system, user)
        data = extract_json_payload(raw)
        passed = bool(data.get("passed", False))
        reason = data.get("reason", "No evaluation output")
        return passed, reason

    # G5: Semantic equivalence
    def compare_semantic_equivalence(self, summary_a: str, summary_b: str) -> tuple[str, str]:
        system = (
            "Compare two reply summaries. "
            'Respond with JSON: {"status": "equivalent"|"compatible change"|"incompatible change", "reason": "..."}'
        )
        user = json.dumps({"summary_a": summary_a, "summary_b": summary_b})
        raw = self._query(system, user)
        data = extract_json_payload(raw)
        status = data.get("status", "incompatible change")
        if status not in ("equivalent", "compatible change", "incompatible change"):
            status = "incompatible change"
        reason = data.get("reason", "")
        return status, reason

    # G6: Text diff summary
    def summarize_text_diff(self, diff_text: str) -> str:
        system = "Summarize this prompt/skill text diff in one line. Respond with JSON: {\"summary\": \"...\"}"
        raw = self._query(system, diff_text)
        data = extract_json_payload(raw)
        return data.get("summary", "Text modified")

    # G7: Rank causes
    def rank_causes(self, behavioral_change: str, candidate_diffs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        system = (
            "Rank candidate dependency diffs that likely caused behavioral change. "
            'Respond with JSON: {"rankings": [{"candidate_id": "...", "confidence": "LIKELY"|"POSSIBLE", "rationale": "..."}]}'
        )
        user = json.dumps({"change": behavioral_change, "candidates": candidate_diffs})
        raw = self._query(system, user)
        data = extract_json_payload(raw)
        return data.get("rankings", [])

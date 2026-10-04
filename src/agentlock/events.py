"""L0 raw events and L1 event normalization pipeline."""

from __future__ import annotations

import json
import time
from typing import Any, Literal
from pydantic import BaseModel, Field

EventKind = Literal["run_start", "node_start", "node_end", "model_call", "tool_call", "artifact", "run_end"]


class RawEvent(BaseModel):
    """L0 event emitted by adapters."""

    run: str = "r1"
    seq: int = 1
    t: float = Field(default_factory=time.time)
    type: EventKind
    name: str = ""
    node: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class ToolCallData(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: Any = None
    error: str | None = None


class NormalizedToolCall(BaseModel):
    """L1 normalized tool call with volatile data removed and entities abstracted."""

    tool: str
    arguments: dict[str, str] = Field(default_factory=dict)
    result_facts: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None

    def key(self) -> str:
        """Deterministic key for deduplication."""
        args_str = json.dumps(self.arguments, sort_keys=True)
        return f"{self.tool}:{args_str}"


class NormalizedTrace(BaseModel):
    """L1 trace for one run sample."""

    scenario_id: str
    sample_index: int = 0
    input: str
    calls: list[NormalizedToolCall] = Field(default_factory=list)
    reply: str = ""
    artifacts: dict[str, str] = Field(default_factory=dict)
    error: str | None = None


def normalize_event_stream(
    scenario_id: str,
    sample_index: int,
    input_text: str,
    entities: dict[str, str],
    raw_events: list[RawEvent],
) -> NormalizedTrace:
    """Transform L0 raw event stream into normalized L1 trace."""
    # Build entity replacement map (value -> $key)
    entity_map: dict[str, str] = {}
    for key, val in entities.items():
        if val:
            entity_map[str(val)] = f"${key}"

    normalized_calls: list[NormalizedToolCall] = []
    artifacts: dict[str, str] = {}
    final_reply = ""
    run_error = None

    for ev in raw_events:
        if ev.type == "tool_call":
            tool_name = ev.name or ev.data.get("name", "")
            raw_args = ev.data.get("arguments", {})
            raw_result = ev.data.get("result", {})
            raw_err = ev.data.get("error")

            # 1. Canonicalize arguments & abstract entities
            norm_args: dict[str, str] = {}
            if isinstance(raw_args, dict):
                for k, v in raw_args.items():
                    val_str = str(v).strip()
                    for ent_val, ent_placeholder in entity_map.items():
                        if ent_val in val_str:
                            val_str = val_str.replace(ent_val, ent_placeholder)
                    norm_args[k] = val_str

            # 2. Extract result facts
            result_facts: dict[str, Any] = {}
            if isinstance(raw_result, dict):
                for k, v in raw_result.items():
                    if isinstance(v, (bool, int, float, str)):
                        if isinstance(v, str) and len(v) > 64:
                            result_facts[k] = "present"
                        else:
                            result_facts[k] = v
                    elif v is not None:
                        result_facts[k] = "present"
            elif raw_result is not None:
                result_facts["status"] = "present"

            call = NormalizedToolCall(
                tool=tool_name,
                arguments=norm_args,
                result_facts=result_facts,
                error=raw_err,
            )

            # 3. Collapse immediately repeated identical calls
            if not normalized_calls or normalized_calls[-1].key() != call.key():
                normalized_calls.append(call)

        elif ev.type == "artifact":
            art_name = ev.data.get("name", ev.name)
            art_path = ev.data.get("path", "")
            if art_name and art_path:
                artifacts[art_name] = art_path

        elif ev.type == "run_end":
            final_reply = ev.data.get("reply", ev.data.get("output", ""))
            run_error = ev.data.get("error")

    return NormalizedTrace(
        scenario_id=scenario_id,
        sample_index=sample_index,
        input=input_text,
        calls=normalized_calls,
        reply=final_reply,
        artifacts=artifacts,
        error=run_error,
    )

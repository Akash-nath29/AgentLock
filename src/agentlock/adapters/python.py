"""Python framework adapter supporting .spec, .run(), and @tracked_tool path."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any
from agentlock.adapters.base import BaseAdapter
from agentlock.events import RawEvent
from agentlock.tracer import AgentLockTracer


class PythonAdapter(BaseAdapter):
    """Adapter for custom Python agents exposing .spec and .run(task)."""

    def __init__(self):
        self.agent_instance: Any = None
        self.entrypoint_str: str = ""

    def load(self, entrypoint: str, options: dict[str, Any] | None = None) -> None:
        self.entrypoint_str = entrypoint
        cwd_str = str(Path.cwd())
        if cwd_str not in sys.path:
            sys.path.insert(0, cwd_str)
        mod_name, attr_name = entrypoint.split(":")
        mod = importlib.import_module(mod_name)
        builder = getattr(mod, attr_name)
        opts = options or {}
        self.agent_instance = builder(**opts) if callable(builder) else builder

    def discover(self) -> dict[str, Any]:
        if not hasattr(self.agent_instance, "spec"):
            return {}
        spec = self.agent_instance.spec
        spec_dict = spec.model_dump() if hasattr(spec, "model_dump") else dict(spec)
        return spec_dict

    def run(self, scenario_input: str, scenario_id: str = "", sample_index: int = 0) -> tuple[list[RawEvent], str]:
        tracer = AgentLockTracer()
        raw_events: list[RawEvent] = []

        raw_events.append(
            RawEvent(
                type="run_start",
                data={"input": scenario_input, "scenario_id": scenario_id, "sample_index": sample_index},
            )
        )

        with tracer.trace(scenario_input) as tr:
            if hasattr(self.agent_instance, "run"):
                reply = self.agent_instance.run(scenario_input)
            else:
                reply = str(self.agent_instance(scenario_input))
            tr.output = reply

        # Convert tracer trace events to L0 RawEvents
        seq = 2
        for ev in tr.events:
            if ev.kind == "tool_called" and ev.tool_call:
                raw_events.append(
                    RawEvent(
                        seq=seq,
                        type="tool_call",
                        name=ev.tool_call.name,
                        data={
                            "name": ev.tool_call.name,
                            "arguments": ev.tool_call.arguments,
                            "result": ev.tool_call.result,
                            "error": ev.tool_call.error,
                        },
                    )
                )
                seq += 1
            elif ev.kind == "artifact_recorded":
                raw_events.append(
                    RawEvent(
                        seq=seq,
                        type="artifact",
                        name=ev.data.get("name", ""),
                        data=ev.data,
                    )
                )
                seq += 1

        raw_events.append(
            RawEvent(
                seq=seq,
                type="run_end",
                data={"reply": reply},
            )
        )

        return raw_events, reply

    def override(self, overrides: dict[str, Any]) -> None:
        if self.entrypoint_str:
            self.load(self.entrypoint_str, options=overrides)

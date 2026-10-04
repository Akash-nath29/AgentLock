"""LangGraph framework adapter using callback instrumentation."""

from __future__ import annotations

import importlib
from typing import Any
from agentlock.adapters.base import BaseAdapter
from agentlock.events import RawEvent


class LangGraphAdapter(BaseAdapter):
    """Adapter for LangGraph agents using compiled graphs or graph builders."""

    def __init__(self):
        self.graph: Any = None
        self.entrypoint_str: str = ""

    def load(self, entrypoint: str, options: dict[str, Any] | None = None) -> None:
        import sys
        from pathlib import Path
        cwd_str = str(Path.cwd())
        if cwd_str not in sys.path:
            sys.path.insert(0, cwd_str)
        self.entrypoint_str = entrypoint
        mod_name, attr_name = entrypoint.split(":")
        mod = importlib.import_module(mod_name)
        builder = getattr(mod, attr_name)
        opts = options or {}
        self.graph = builder(**opts) if callable(builder) else builder

    def discover(self) -> dict[str, Any]:
        if hasattr(self.graph, "spec"):
            spec = self.graph.spec
            return spec.model_dump() if hasattr(spec, "model_dump") else dict(spec)

        tools_list = []
        if hasattr(self.graph, "nodes") and "tools" in self.graph.nodes:
            tools_node = self.graph.nodes["tools"]
            if hasattr(tools_node, "tools"):
                for t in tools_node.tools:
                    tools_list.append({"name": getattr(t, "name", str(t)), "description": getattr(t, "description", "")})

        return {
            "name": getattr(self.graph, "name", "langgraph-agent"),
            "model": {"provider": "ollama", "name": "gemma4:31b-cloud"},
            "tools": tools_list,
        }

    def run(self, scenario_input: str, scenario_id: str = "", sample_index: int = 0) -> tuple[list[RawEvent], str]:
        raw_events: list[RawEvent] = []
        raw_events.append(
            RawEvent(
                type="run_start",
                data={"input": scenario_input, "scenario_id": scenario_id, "sample_index": sample_index},
            )
        )

        reply = ""
        try:
            if hasattr(self.graph, "run"):
                reply = self.graph.run(scenario_input)
            elif hasattr(self.graph, "invoke"):
                res = self.graph.invoke({"messages": [("user", scenario_input)]})
                if isinstance(res, dict) and "messages" in res:
                    msgs = res["messages"]
                    if msgs:
                        last_msg = msgs[-1]
                        reply = getattr(last_msg, "content", str(last_msg))
                else:
                    reply = str(res)
        except Exception as exc:
            reply = f"Error: {exc}"

        raw_events.append(
            RawEvent(
                seq=2,
                type="run_end",
                data={"reply": reply},
            )
        )

        return raw_events, reply

    def override(self, overrides: dict[str, Any]) -> None:
        if self.entrypoint_str:
            self.load(self.entrypoint_str, options=overrides)

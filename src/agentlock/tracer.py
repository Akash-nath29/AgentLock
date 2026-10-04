"""Record what an agent does: tool calls, artifacts, and the final output.

    tracer = AgentLockTracer()
    with tracer.trace("Fix the bug") as trace:
        trace.output = agent.run("Fix the bug")

Tools decorated with `@tracked_tool` record themselves into whichever tracer is
active; outside a trace they run untouched.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, TypeVar

from agentlock.models import AgentEvent, ToolCall, Trace

_active: ContextVar[AgentLockTracer | None] = ContextVar("agentlock_tracer", default=None)

F = TypeVar("F", bound=Callable[..., Any])


class AgentLockTracer:
    """Collects one `Trace` per `trace()` block."""

    def __init__(self) -> None:
        self.current: Trace | None = None

    @contextmanager
    def trace(self, task: str = "") -> Iterator[Trace]:
        """Activate this tracer. Set `trace.output` inside the block to capture the response."""
        trace = Trace(task=task, events=[AgentEvent(kind="agent_started", data={"task": task})])
        self.current = trace
        token = _active.set(self)
        try:
            yield trace
        finally:
            _active.reset(token)
            trace.events.append(AgentEvent(kind="agent_finished", data={"output": trace.output}))

    def _require_trace(self) -> Trace:
        if self.current is None:
            raise RuntimeError("No active trace; use `with tracer.trace(): ...`")
        return self.current

    def record_tool_call(
        self, name: str, arguments: dict[str, Any] | None = None, result: Any = None, error: str | None = None
    ) -> ToolCall:
        """Manually record a tool call (for agents whose tools you can't decorate)."""
        call = ToolCall(name=name, arguments=arguments or {}, result=result, error=error)
        self._require_trace().events.append(AgentEvent(kind="tool_called", tool_call=call))
        return call

    def record_artifact(self, name: str, path: str) -> None:
        """Record a file the agent produced (e.g. a screenshot) for multimodal contracts."""
        self._require_trace().events.append(
            AgentEvent(kind="artifact_recorded", data={"name": name, "path": str(path)})
        )


def current_tracer() -> AgentLockTracer | None:
    """The tracer whose `trace()` block is active in this context, if any."""
    return _active.get()


def tracked_tool(func: F | None = None, *, name: str | None = None) -> Any:
    """Decorator that records every call of a tool into the active tracer.

    Works on plain functions and methods (`self` is not recorded).
    """

    def decorate(fn: F) -> F:
        tool_name = name or fn.__name__
        sig = inspect.signature(fn)

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            tracer = current_tracer()
            if tracer is None:
                return fn(*args, **kwargs)
            bound = sig.bind(*args, **kwargs)
            arguments = {k: v for k, v in bound.arguments.items() if k not in ("self", "cls")}
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:
                tracer.record_tool_call(tool_name, arguments, error=f"{type(exc).__name__}: {exc}")
                raise
            tracer.record_tool_call(tool_name, arguments, result=result)
            return result

        return wrapper  # type: ignore[return-value]

    return decorate(func) if func is not None else decorate

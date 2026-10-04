import pytest

from agentlock import AgentLockTracer, current_tracer, tracked_tool


@tracked_tool
def read_file(path: str) -> str:
    return f"contents of {path}"


@tracked_tool(name="tests")
def run_tests(fail: bool = False) -> dict:
    if fail:
        raise RuntimeError("boom")
    return {"passed": True}


class Repo:
    @tracked_tool
    def write_file(self, path: str, content: str) -> int:
        return len(content)


def test_records_tool_calls_in_order_with_lifecycle_events():
    tracer = AgentLockTracer()
    with tracer.trace("fix it") as trace:
        read_file("a.py")
        Repo().write_file("a.py", content="xyz")
        run_tests()
        trace.output = "done"

    assert [e.kind for e in trace.events] == ["agent_started", "tool_called", "tool_called", "tool_called", "agent_finished"]
    assert trace.tool_names == ["read_file", "write_file", "tests"]
    assert trace.tool_calls[0].arguments == {"path": "a.py"}
    assert trace.tool_calls[1].arguments == {"path": "a.py", "content": "xyz"}  # no `self`
    assert trace.tool_calls[1].result == 3
    assert trace.events[0].data["task"] == "fix it"
    assert trace.events[-1].data["output"] == "done"


def test_tool_runs_untraced_outside_a_trace():
    assert current_tracer() is None
    assert read_file("b.py") == "contents of b.py"


def test_tracer_deactivates_after_block_even_on_error():
    tracer = AgentLockTracer()
    with pytest.raises(RuntimeError):
        with tracer.trace() as trace:
            assert current_tracer() is tracer
            run_tests(fail=True)
    assert current_tracer() is None
    assert trace.tool_calls[0].error == "RuntimeError: boom"
    assert trace.events[-1].kind == "agent_finished"


def test_manual_recording_and_artifacts():
    tracer = AgentLockTracer()
    with tracer.trace() as trace:
        tracer.record_tool_call("search_code", {"query": "x"}, result=[])
        tracer.record_artifact("screenshot", "shot.png")
    assert trace.tool_names == ["search_code"]
    assert trace.artifacts == {"screenshot": "shot.png"}


def test_manual_recording_requires_active_trace():
    with pytest.raises(RuntimeError):
        AgentLockTracer().record_tool_call("x")


def test_sequence_collapses_repeats():
    tracer = AgentLockTracer()
    with tracer.trace() as trace:
        read_file("a")
        read_file("b")
        run_tests()
        read_file("c")
    assert trace.sequence() == ["read_file", "tests", "read_file"]

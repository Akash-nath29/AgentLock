import pytest

from agentlock import (
    AgentLockTracer,
    Condition,
    ConditionalContract,
    ForbiddenContract,
    OrderingContract,
    RequiredContract,
    Trace,
)
from agentlock.validators import check


def make_trace(*calls) -> Trace:
    """calls: tool name, or (name, arguments, result)."""
    tracer = AgentLockTracer()
    with tracer.trace() as trace:
        for call in calls:
            name, args, result = (call, {}, None) if isinstance(call, str) else call
            tracer.record_tool_call(name, args, result)
    return trace


READ_BEFORE_WRITE = OrderingContract(id="o", before="read_file", after="write_file")


def test_ordering_passes_and_fails():
    assert check(READ_BEFORE_WRITE, make_trace("read_file", "write_file"), "s").status == "passed"
    result = check(READ_BEFORE_WRITE, make_trace("write_file", "read_file"), "s")
    assert result.status == "failed"
    assert result.expected == "read_file → write_file"
    assert result.observed == "write_file → read_file"


def test_ordering_is_vacuous_without_the_later_call():
    assert check(READ_BEFORE_WRITE, make_trace("read_file"), "s").status == "passed"


def test_ordering_match_argument():
    contract = OrderingContract(id="o", before="read_file", after="write_file", match_argument="path")
    same = make_trace(("read_file", {"path": "a.py"}, None), ("write_file", {"path": "a.py"}, None))
    other = make_trace(("read_file", {"path": "b.py"}, None), ("write_file", {"path": "a.py"}, None))
    mixed = make_trace(("read_file", {"path": 1001}, None), ("write_file", {"path": "1001"}, None))
    assert check(contract, same, "s").status == "passed"
    assert check(contract, other, "s").status == "failed"
    assert check(contract, mixed, "s").status == "passed"


def test_required_plain_and_after():
    assert check(RequiredContract(id="r", tool="run_tests"), make_trace("run_tests"), "s").status == "passed"
    assert check(RequiredContract(id="r", tool="run_tests"), make_trace("read_file"), "s").status == "failed"

    after_edit = RequiredContract(id="r", tool="run_tests", after="write_file")
    assert check(after_edit, make_trace("write_file", "run_tests"), "s").status == "passed"
    # tests ran, but not after the *last* edit
    assert check(after_edit, make_trace("write_file", "run_tests", "write_file"), "s").status == "failed"
    # not triggered when nothing was edited
    assert check(after_edit, make_trace("read_file"), "s").status == "passed"


def test_forbidden():
    contract = ForbiddenContract(id="f", tool="merge_pull_request")
    assert check(contract, make_trace("create_pull_request"), "s").status == "passed"
    result = check(contract, make_trace("merge_pull_request", "merge_pull_request"), "s")
    assert result.status == "failed" and "2x" in result.explanation


def test_forbidden_with_argument_patterns():
    contract = ForbiddenContract(id="f", tool="write_file", arguments={"path": "test_*.py"})
    assert check(contract, make_trace(("write_file", {"path": "auth.py"}, None)), "s").status == "passed"
    result = check(contract, make_trace(("write_file", {"path": "test_auth.py"}, None)), "s")
    assert result.status == "failed"
    assert result.expected == "never write_file(path=test_*.py)"
    assert "path='test_auth.py'" in result.explanation


NO_PR_ON_FAILURE = ConditionalContract(
    id="c",
    when=Condition(tool="run_tests", field="passed", equals=False),
    forbidden=["create_pull_request"],
)
FAIL = ("run_tests", {}, {"passed": False})
PASS = ("run_tests", {}, {"passed": True})


@pytest.mark.parametrize(
    "calls, status",
    [
        ([FAIL, "create_pull_request"], "failed"),  # PR right after failing tests
        ([FAIL, "write_file", PASS, "create_pull_request"], "passed"),  # fixed, then PR
        (["create_pull_request", FAIL], "failed"),  # PR first, tests then fail
        ([PASS, "create_pull_request"], "passed"),
        (["create_pull_request"], "passed"),  # condition never established
        ([FAIL], "passed"),  # no PR at all
    ],
)
def test_conditional(calls, status):
    assert check(NO_PR_ON_FAILURE, make_trace(*calls), "s").status == status

"""CLI end-to-end unit tests for AgentLock v0.2 six commands."""

from pathlib import Path
import pytest
from typer.testing import CliRunner
from agentlock.cli import app

AGENT_SRC = '''
from agentlock import AgentSpec, ModelSpec, ToolSpec, tracked_tool

@tracked_tool
def read_file(path):
    return "old"

@tracked_tool
def write_file(path, content):
    return {"bytes": len(content)}

class Agent:
    def __init__(self, order="read-first"):
        self.order = order
        self.spec = AgentSpec(
            name="tiny",
            model=ModelSpec(name="tiny-model"),
            system_prompt="Always read a file before writing it.",
            tools=[ToolSpec(name="read_file"), ToolSpec(name="write_file")],
            config={"order": order},
        )

    def run(self, task):
        if self.order == "read-first":
            read_file("a.py")
            write_file("a.py", "new")
        else:
            write_file("a.py", "new")
            read_file("a.py")
        return "Updated a.py."

def build(**options):
    return Agent(**options)
'''

runner = CliRunner()


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "tiny_agent.py").write_text(AGENT_SRC, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def invoke(*args):
    result = runner.invoke(app, list(args))
    return result.exit_code, result.output


def test_cli_help():
    code, out = invoke("--help")
    assert code == 0
    for command in ("init", "capture", "lock", "diff", "restore", "verify"):
        assert command in out


def test_cli_init_flow(project: Path):
    code, out = invoke("init", "--entry", "tiny_agent:build", "--adapter", "python")
    assert code == 0, out
    assert (project / "agentlock.yaml").exists()
    assert (project / ".agentlock" / "objects").exists()


def test_cli_capture_and_lock(project: Path):
    invoke("init", "--entry", "tiny_agent:build", "--adapter", "python")
    code, out = invoke("capture", "--samples", "1")
    assert code == 0, out
    assert "Capture complete" in out

    code, out = invoke("lock")
    assert code == 0, out
    assert (project / "agent.lock").exists()


def test_cli_verify_and_restore(project: Path):
    invoke("init", "--entry", "tiny_agent:build", "--adapter", "python")
    invoke("capture", "--samples", "1")
    invoke("lock")

    code, out = invoke("verify")
    assert code == 0, out
    assert "CONFORMS" in out

    code, out = invoke("restore", "--dry-run")
    assert code == 0, out
    assert "Restoring agent.lock" in out

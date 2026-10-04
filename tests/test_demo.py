"""The demo coding agent (scripted brain) tested with PythonAdapter."""

from pathlib import Path

from agentlock.adapters.python import PythonAdapter
from agentlock.manifest import load_manifest

DEMO = Path(__file__).resolve().parents[1] / "demo"


def test_demo_manifest_load():
    manifest = load_manifest(DEMO / "agentlock.yaml")
    assert manifest.agent.name == "coding-agent"
    assert manifest.agent.adapter == "python"


def test_demo_scripted_brain_run():
    import sys
    if str(DEMO) not in sys.path:
        sys.path.insert(0, str(DEMO))
    manifest = load_manifest(DEMO / "agentlock.yaml")
    adapter = PythonAdapter()
    adapter.load(manifest.agent.entrypoint, manifest.agent.options)

    events, reply = adapter.run("Fix token expiry bug", scenario_id="fix-token-expiry")
    assert reply != ""
    assert any(ev.type == "tool_call" for ev in events)

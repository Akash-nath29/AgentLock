from pathlib import Path
from agentlock.behavior import BehaviorBasis, BehaviorState, ScenarioBehavior, OutcomeSpec
from agentlock.deps import DependencyClosure, ModelDep, ToolDep
from agentlock.lockfile import AgentLockHeader, LockfileV2, load_lockfile, write_lockfile


def test_lockfile_v2_round_trip(tmp_path: Path):
    dep_closure = DependencyClosure(
        model=[ModelDep(id="model.agent", provider="ollama", name="gemma4:31b-cloud", dep_class="external")],
        tools=[ToolDep(id="tool.run_tests", schema_sha256="abc12345", object="abc12345", dep_class="external")],
    )
    dep_closure.compute_fingerprint()

    behav_state = BehaviorState(
        basis=BehaviorBasis(scenarios=1, samples=3, judge="gemma4:31b-cloud"),
        actions={"run_tests": {"tool": "run_tests", "effect": "write"}},
        scenarios=[
            ScenarioBehavior(
                id="example",
                input="Run unit tests",
                outcome=OutcomeSpec(label="completed", support="3/3"),
                effects=["run_tests"],
            )
        ],
    )
    behav_state.compute_fingerprint()

    lock = LockfileV2(
        agent=AgentLockHeader(name="test-agent", adapter="python", entrypoint="test:build"),
        dependencies=dep_closure,
        behavior=behav_state,
    )

    lock_path = tmp_path / "agent.lock"
    write_lockfile(lock_path, lock)

    assert lock_path.exists()
    loaded = load_lockfile(lock_path)
    assert loaded.lockfile_version == 2
    assert loaded.agent.name == "test-agent"
    assert loaded.dependencies.model[0].name == "gemma4:31b-cloud"
    assert loaded.state == lock.state


def test_state_computation():
    dep_closure = DependencyClosure(model=[ModelDep(id="model.agent", provider="ollama", name="gemma4:31b-cloud")])
    behav_state = BehaviorState(
        basis=BehaviorBasis(scenarios=1, samples=1),
        scenarios=[ScenarioBehavior(id="s1", input="in", outcome=OutcomeSpec(label="done"))],
    )

    lock = LockfileV2(
        agent=AgentLockHeader(name="agent", adapter="python", entrypoint="m:f"),
        dependencies=dep_closure,
        behavior=behav_state,
    )

    state = lock.compute_state_str()
    assert "." in state
    parts = state.split(".")
    assert len(parts[0]) == 6
    assert len(parts[1]) == 6

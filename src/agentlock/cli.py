"""Redesigned Typer CLI app for AgentLock v0.2."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Optional
import typer
from rich.console import Console

from agentlock.adapters import get_adapter
from agentlock.behavior import BehaviorBasis, BehaviorState, reduce_scenario_traces
from agentlock.deps import ConfigDep, DependencyClosure, ModelDep, PromptDep, SkillDep, ToolDep
from agentlock.diff import compute_diff
from agentlock.events import NormalizedTrace, normalize_event_stream
from agentlock.invariants import mine_invariants
from agentlock.lockfile import AgentLockHeader, LockfileV2, load_lockfile, write_lockfile
from agentlock.manifest import AgentManifest, load_manifest
from agentlock.objects import ObjectStore
from agentlock.render import (
    render_diff_markdown,
    render_diff_terminal,
    render_restore_terminal,
    render_verify_terminal,
)
from agentlock.restore import execute_restore
from agentlock.vocabulary import ActionVocabulary
from agentlock.verify import verify_agent

app = typer.Typer(
    name="agentlock",
    help="AgentLock — package-lock.json for AI agents.",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()


def _setup() -> None:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
            sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass


@app.callback()
def main_callback() -> None:
    _setup()


@app.command()
def init(
    entry: Annotated[Optional[str], typer.Option("--entry", "-e", help="Agent entrypoint (module:callable)")] = None,
    adapter: Annotated[str, typer.Option("--adapter", "-a", help="Framework adapter (langgraph|python)")] = "python",
) -> None:
    """Create agentlock.yaml manifest and initialize .agentlock/ directory."""
    cwd = Path.cwd()
    manifest_path = cwd / "agentlock.yaml"
    if manifest_path.exists():
        console.print("[yellow]agentlock.yaml already exists.[/yellow]")
        raise typer.Exit(code=0)

    entrypoint = entry or "my_agent:build_agent"
    manifest_content = f"""version: 2
agent:
  name: my-agent
  adapter: {adapter}
  entrypoint: {entrypoint}

scenarios:
  - id: example
    input: "Perform an example task."

capture:
  samples: 3
judge:
  provider: ollama
  model: gemma4:31b-cloud
"""
    manifest_path.write_text(manifest_content, encoding="utf-8")

    # Initialize .agentlock directory
    (cwd / ".agentlock" / "objects").mkdir(parents=True, exist_ok=True)
    (cwd / ".agentlock" / "captures").mkdir(parents=True, exist_ok=True)

    # Ensure .gitignore includes captures and backup
    gitignore = cwd / ".gitignore"
    gitignore_entry = "\n.agentlock/captures/\n.agentlock/cache/\n.agentlock/backup/\n"
    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8")
        if ".agentlock/captures/" not in content:
            gitignore.write_text(content + gitignore_entry, encoding="utf-8")
    else:
        gitignore.write_text(gitignore_entry, encoding="utf-8")

    console.print(f"[bold green]✓ Created agentlock.yaml manifest ({adapter} adapter)[/bold green]")
    console.print("Next: edit scenarios in [cyan]agentlock.yaml[/cyan], then run [cyan]agentlock capture[/cyan]\n")


def _run_capture_internal(manifest: AgentManifest, cwd: Path) -> tuple[LockfileV2, dict[str, list[NormalizedTrace]]]:
    adapter_obj = get_adapter(manifest.agent.adapter)
    adapter_obj.load(manifest.agent.entrypoint, manifest.agent.options)
    discovered = adapter_obj.discover()

    store = ObjectStore(cwd)
    vocab = ActionVocabulary()

    # Pre-register discovered tools
    for tool_dict in discovered.get("tools", []):
        t_name = tool_dict.get("name", "")
        if t_name:
            vocab.register(t_name, tool_name=t_name, effect="write")

    traces_by_scenario: dict[str, list[NormalizedTrace]] = {}
    sc_behaviors = []

    samples = manifest.capture.samples

    for sc in manifest.scenarios:
        tr_list = []
        for s in range(samples):
            raw_events, reply = adapter_obj.run(sc.input, scenario_id=sc.id, sample_index=s)
            norm_tr = normalize_event_stream(sc.id, s, sc.input, sc.entities, raw_events)
            tr_list.append(norm_tr)

        traces_by_scenario[sc.id] = tr_list
        sc_behav = reduce_scenario_traces(sc.id, sc.input, sc.entities, tr_list, vocab, outcome_label="completed")
        sc_behaviors.append(sc_behav)

    # Mine invariants
    mined = mine_invariants(traces_by_scenario, vocab)
    mined_dicts = [m.model_dump() for m in mined]

    # Build dependency closure records
    prompt_deps = []
    prompts_map = manifest.dependencies.get("prompts", {})
    if isinstance(prompts_map, dict):
        for p_name, p_file in prompts_map.items():
            if isinstance(p_file, str):
                p_path = cwd / p_file
                if p_path.exists():
                    p_content = p_path.read_text(encoding="utf-8")
                    p_digest = store.put(p_content)
                    prompt_deps.append(
                        PromptDep(
                            id=f"prompt.{p_name}",
                            sha256=p_digest,
                            object=p_digest,
                            source={"file": p_file},
                            dep_class="reproducible",
                        )
                    )

    skill_deps = []
    skills_map = manifest.dependencies.get("skills", {})
    if isinstance(skills_map, dict):
        for s_name, s_file in skills_map.items():
            if isinstance(s_file, str):
                s_path = cwd / s_file
                if s_path.exists():
                    s_content = s_path.read_text(encoding="utf-8")
                    s_digest = store.put(s_content)
                    skill_deps.append(
                        SkillDep(
                            id=f"skill.{s_name}",
                            sha256=s_digest,
                            object=s_digest,
                            source={"file": s_file},
                            dep_class="reproducible",
                        )
                    )

    config_deps = []
    cfg_spec = manifest.dependencies.get("config", {})
    if isinstance(cfg_spec, dict) and "file" in cfg_spec:
        c_file = cfg_spec["file"]
        c_path = cwd / c_file
        if c_path.exists():
            c_content = c_path.read_text(encoding="utf-8")
            c_digest = store.put(c_content)
            try:
                import yaml
                c_vals = yaml.safe_load(c_content) if isinstance(yaml.safe_load(c_content), dict) else {}
            except Exception:
                c_vals = {}
            config_deps.append(
                ConfigDep(
                    id="config.agent",
                    sha256=c_digest,
                    object=c_digest,
                    values=c_vals,
                    source={"file": c_file},
                    dep_class="reproducible",
                )
            )

    tool_deps = []
    for t_dict in discovered.get("tools", []):
        t_name = t_dict.get("name", "")
        t_schema = json.dumps(t_dict, sort_keys=True)
        t_obj = store.put(t_schema)
        tool_deps.append(
            ToolDep(
                id=f"tool.{t_name}",
                schema_sha256=t_obj,
                object=t_obj,
                dep_class="external",
            )
        )

    model_dep = ModelDep(
        id="model.agent",
        provider=manifest.judge.provider,
        name=manifest.judge.model,
        dep_class="external",
    )

    dep_closure = DependencyClosure(
        model=[model_dep],
        prompts=prompt_deps,
        skills=skill_deps,
        tools=tool_deps,
        config=config_deps,
    )
    dep_closure.compute_fingerprint()

    behav_state = BehaviorState(
        basis=BehaviorBasis(scenarios=len(manifest.scenarios), samples=samples, judge=manifest.judge.model),
        actions=vocab.actions,
        scenarios=sc_behaviors,
        contracts=mined_dicts,
    )
    behav_state.compute_fingerprint()

    lock = LockfileV2(
        agent=AgentLockHeader(
            name=manifest.agent.name,
            adapter=manifest.agent.adapter,
            entrypoint=manifest.agent.entrypoint,
        ),
        dependencies=dep_closure,
        behavior=behav_state,
    )
    lock.compute_state_str()
    return lock, traces_by_scenario


@app.command()
def capture(
    samples: Annotated[int, typer.Option("--samples", "-s", help="Number of samples per scenario")] = 3,
) -> None:
    """Observe live agent runs and construct disposable capture state."""
    cwd = Path.cwd()
    manifest_path = cwd / "agentlock.yaml"
    if not manifest_path.exists():
        console.print("[red]No agentlock.yaml found. Run `agentlock init` first.[/red]")
        raise typer.Exit(code=2)

    manifest = load_manifest(manifest_path)
    manifest.capture.samples = samples

    console.print(f"[bold]Capturing behavioral state[/bold] ({len(manifest.scenarios)} scenarios × {samples} samples)...")

    try:
        lock, _ = _run_capture_internal(manifest, cwd)
        cap_id = f"{lock.state}"
        cap_file = cwd / ".agentlock" / "captures" / f"{cap_id}.json"
        cap_file.parent.mkdir(parents=True, exist_ok=True)
        cap_file.write_text(lock.model_dump_json(indent=2), encoding="utf-8")

        console.print(f"[bold green]✓ Capture complete:[/bold green] {lock.state}")
        console.print("Next: run [cyan]agentlock lock[/cyan] to promote to agent.lock\n")
    except Exception as exc:
        console.print(f"[bold red]Capture failed:[/bold red] {exc}")
        raise typer.Exit(code=2)


@app.command()
def lock(
    accept: Annotated[Optional[list[str]], typer.Option("--accept", help="Accept specific contract changes")] = None,
) -> None:
    """Promote captured state to agent.lock."""
    cwd = Path.cwd()
    manifest_path = cwd / "agentlock.yaml"
    if not manifest_path.exists():
        console.print("[red]No agentlock.yaml found. Run `agentlock init` first.[/red]")
        raise typer.Exit(code=2)

    manifest = load_manifest(manifest_path)
    lock_obj, _ = _run_capture_internal(manifest, cwd)

    lock_file = cwd / "agent.lock"
    write_lockfile(lock_file, lock_obj)

    console.print(f"[bold green]✓ Wrote agent.lock ({lock_obj.state})[/bold green]")
    console.print("Commit [cyan]agent.lock[/cyan] and [cyan]agentlock.yaml[/cyan] to Git.\n")


@app.command()
def diff(
    base: Annotated[str, typer.Argument(help="Base state (agent.lock or capture id)")] = "agent.lock",
    head: Annotated[str, typer.Argument(help="Head state (live or capture id)")] = "live",
    deps_only: Annotated[bool, typer.Option("--deps-only", help="Compare dependencies only")] = False,
    format: Annotated[str, typer.Option("--format", "-f", help="Output format (text|md|json)")] = "text",
    exit_code: Annotated[bool, typer.Option("--exit-code", help="Exit code 1 if breaking changes exist")] = False,
) -> None:
    """Explain differences between two agent states."""
    cwd = Path.cwd()
    manifest_path = cwd / "agentlock.yaml"
    if not manifest_path.exists():
        console.print("[red]No agentlock.yaml found.[/red]")
        raise typer.Exit(code=2)

    manifest = load_manifest(manifest_path)

    # Load base lock
    lock_file = cwd / "agent.lock"
    if not lock_file.exists():
        console.print("[red]No agent.lock found. Run `agentlock lock` first.[/red]")
        raise typer.Exit(code=2)

    base_lock = load_lockfile(lock_file)
    head_lock, head_traces = _run_capture_internal(manifest, cwd)

    report = compute_diff(base_lock, head_lock, head_traces)

    if format == "json":
        console.print(report.model_dump_json(indent=2))
    elif format == "md":
        console.print(render_diff_markdown(report))
    else:
        render_diff_terminal(report)

    if exit_code and not report.is_conforming:
        raise typer.Exit(code=1)


@app.command()
def restore(
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print restoration plan without modifying files")] = False,
    to: Annotated[Optional[str], typer.Option("--to", help="Restore into a target directory instead of working tree")] = None,
) -> None:
    """Rebuild locked dependency configuration."""
    cwd = Path.cwd()
    lock_file = cwd / "agent.lock"
    if not lock_file.exists():
        console.print("[red]No agent.lock found.[/red]")
        raise typer.Exit(code=2)

    lock_obj = load_lockfile(lock_file)
    plan = execute_restore(lock_obj, project_dir=cwd, dry_run=dry_run, to_dir=to)

    render_restore_terminal(plan)


@app.command()
def verify(
    deps_only: Annotated[bool, typer.Option("--deps-only", help="Verify dependencies matching only")] = False,
    strict: Annotated[bool, typer.Option("--strict", help="Fail on minor drift or warnings")] = False,
) -> None:
    """Gate: verify current agent conforms to agent.lock."""
    cwd = Path.cwd()
    lock_file = cwd / "agent.lock"
    if not lock_file.exists():
        console.print("[red]No agent.lock found. Run `agentlock lock` first.[/red]")
        raise typer.Exit(code=2)

    manifest = load_manifest(cwd / "agentlock.yaml")
    base_lock = load_lockfile(lock_file)
    live_lock, live_traces = _run_capture_internal(manifest, cwd)

    result = verify_agent(base_lock, live_lock, live_traces, deps_only=deps_only, strict=strict)
    render_verify_terminal(result)

    raise typer.Exit(code=result.exit_code)


if __name__ == "__main__":
    app()

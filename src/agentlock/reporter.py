"""Terminal output."""

from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.table import Table

from agentlock.core import Comparison, TestReport
from agentlock.lockfile import model_label, short
from agentlock.models import AgentSpec, ContractResult, Trace
from agentlock.validators import format_sequence

console = Console(highlight=False)

ICON = {
    "passed": "[green]✓[/]",
    "failed": "[red]✗[/]",
    "error": "[red]![/]",
    "skipped": "[yellow]⚠[/]",
}


def _clip(value: Any, limit: int = 100) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    text = text.replace("\n", "\\n")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def heading(title: str) -> None:
    console.print(f"\n[bold]{title}[/]\n")


def print_spec(spec: AgentSpec) -> None:
    first_line = spec.system_prompt.strip().splitlines()[0] if spec.system_prompt.strip() else "(none)"
    console.print(f"[green]✓[/] Agent: [bold]{spec.name}[/]")
    console.print(f"[green]✓[/] Model: {spec.model.provider + '/' if spec.model.provider else ''}{model_label(spec.model)}")
    console.print(f"[green]✓[/] System prompt loaded: [dim]{_clip(first_line, 70)}[/]")
    console.print(f"[green]✓[/] {len(spec.tools)} tools discovered: {', '.join(t.name for t in spec.tools)}")
    console.print(f"[green]✓[/] {len(spec.skills)} skills discovered" + (f": {', '.join(s.name for s in spec.skills)}" if spec.skills else ""))


def print_trace(trace: Trace) -> None:
    for i, call in enumerate(trace.tool_calls, 1):
        args = ", ".join(f"{k}={_clip(v, 40)}" for k, v in call.arguments.items())
        outcome = f"[red]{call.error}[/]" if call.error else _clip(call.result)
        console.print(f"      {i}. [cyan]{call.name}[/]({args}) [dim]→ {outcome}[/]")
    for name, path in trace.artifacts.items():
        console.print(f"      artifact [cyan]{name}[/]: {path}")
    console.print(f"      [dim]response:[/] {_clip(trace.output or '(empty)', 300)}")


def _print_details(r: ContractResult, indent: str = "    ") -> None:
    if r.explanation:
        console.print(f"{indent}[dim]{r.scenario}:[/] {r.explanation}")
    if r.criteria:
        for c in r.criteria:
            mark = "[green]✓[/]" if c.passed else "[red]✗[/]"
            console.print(f"{indent}  {mark} {c.criterion}" + ("" if c.passed else f" [dim]— {c.reason}[/]"))
    elif r.status == "failed":
        console.print(f"{indent}  Expected: [green]{r.expected}[/]")
        console.print(f"{indent}  Observed: [red]{r.observed}[/]")


def print_report(report: TestReport, verbose: bool = False) -> None:
    heading("AgentLock Behavioral Test")
    console.print(f"Agent [bold]{report.lock.agent.name}[/] · model {model_label(report.lock.model)} · evaluator {report.evaluator or '[yellow]none[/]'}")
    console.print("\n[bold]Scenarios[/]")
    for run in report.scenarios:
        flow = f"[red]crashed: {run.error}[/]" if run.error else format_sequence(run.sequence)
        console.print(f"  [dim]{run.id}:[/] {flow}")
        if verbose and run.trace:
            print_trace(run.trace)

    statuses = report.contract_statuses()
    console.print(f"\n[bold]Contracts[/] ({len(statuses)})")
    by_contract: dict[str, list[ContractResult]] = {}
    for r in report.results:
        by_contract.setdefault(r.contract_id, []).append(r)
    for cid, status in statuses.items():
        results = by_contract[cid]
        scores = [r.score for r in results if r.score is not None]
        note = f" [dim]score {min(scores):.2f}[/]" if scores else ""
        console.print(f"{ICON[status]} {cid}{note}")
        for r in results:
            if r.status in ("failed", "error"):
                _print_details(r)
            elif verbose:  # passes stay one line unless asked
                _print_details(r)

    passed, total = report.count("passed"), len(statuses)
    failed = report.count("failed") + report.count("error")
    skipped = report.count("skipped")
    color = "green" if report.passed else "red"
    summary = f"{passed}/{total} PASSED"
    if failed:
        summary += f", {failed} FAILED"
    if skipped:
        summary += f", {skipped} skipped"
    console.print(f"\n[bold {color}]{summary}[/]")
    console.print(f"\nBehavioral fingerprint: [bold]{short(report.fingerprint)}[/]")


def print_comparison(cmp: Comparison) -> None:
    base, cur = cmp.baseline, cmp.current
    heading("AgentLock Behavioral Comparison")
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("")
    table.add_column("Baseline")
    table.add_column("Current")

    def mark(a: str, b: str) -> str:
        return b if a == b else f"[yellow]{b}[/]"

    table.add_row("model", model_label(base.lock.model), mark(model_label(base.lock.model), model_label(cur.lock.model)))
    table.add_row("prompt hash", short(base.lock.prompt.hash), mark(short(base.lock.prompt.hash), short(cur.lock.prompt.hash)))
    table.add_row("tools", str(len(base.lock.tools)), mark(str(len(base.lock.tools)), str(len(cur.lock.tools))))
    b_pass = f"{base.count('passed')}/{len(base.contract_statuses())} passed"
    c_pass = f"{cur.count('passed')}/{len(cur.contract_statuses())} passed"
    table.add_row("contracts", b_pass, mark(b_pass, c_pass))
    table.add_row("fingerprint", short(base.fingerprint), mark(short(base.fingerprint), short(cur.fingerprint)))
    table.add_row("recorded", base.created_at, cur.created_at)
    console.print(table)

    if cmp.config_changes:
        console.print("\n[bold]Changed since baseline[/]")
        for change in cmp.config_changes:
            console.print(f"  [yellow]~[/] {change}")

    if cmp.regressions:
        console.print(f"\n[bold red]BEHAVIORAL REGRESSIONS DETECTED ({len(cmp.regressions)})[/]\n")
        for reg in cmp.regressions:
            r = reg.current
            console.print(f"[red]✗[/] [bold]{r.contract_id}[/] [dim]({r.scenario})[/]")
            if r.criteria:
                _print_details(r)
            else:
                console.print(f"    Expected: [green]{r.expected}[/]")
                console.print(f"    Baseline: {reg.baseline.observed}")
                console.print(f"    Observed: [red]{r.observed}[/]")
                if r.explanation:
                    console.print(f"    [dim]{r.explanation}[/]")
            console.print()
    else:
        console.print("\n[bold green]No behavioral regressions.[/]")

    for r in cmp.fixed:
        console.print(f"[green]✓[/] fixed since baseline: {r.contract_id} [dim]({r.scenario})[/]")

    if base.fingerprint == cur.fingerprint:
        console.print(f"\nBehavior unchanged: [bold]{short(cur.fingerprint)}[/]")
    else:
        console.print(f"\nBehavior changed: [bold]{short(base.fingerprint)} → {short(cur.fingerprint)}[/]")

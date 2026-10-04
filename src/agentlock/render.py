"""Renderers for Rich terminal, Markdown PR comments, and JSON format."""

from __future__ import annotations

from rich.console import Console

from agentlock.diff import DiffReport
from agentlock.restore import RestorePlan
from agentlock.verify import VerificationResult

console = Console()


def render_diff_terminal(report: DiffReport) -> None:
    """Render diff report to Rich terminal."""
    console.print(f"\n[bold]{report.base_ref}[/bold] -> [bold]{report.head_ref}[/bold]")
    console.print(f"state [cyan]{report.base_state}[/cyan] -> [cyan]{report.head_state}[/cyan]\n")

    if report.dependency_changes:
        console.print(f"[bold]DEPENDENCIES[/bold] {len(report.dependency_changes)} changed")
        for dc in report.dependency_changes:
            console.print(f"  [yellow]~[/yellow] {dc.dep_id}  {dc.summary}")
        console.print()

    if report.behavior_changes:
        brk = report.summary.get("breaking", 0)
        warn = report.summary.get("warning", 0)
        console.print(f"[bold]BEHAVIOR[/bold] {brk} breaking · {warn} warning")

        for bc in report.behavior_changes:
            sev_color = "red" if bc.severity == "breaking" else "yellow"
            mark = "✗" if bc.severity == "breaking" else "⚠"
            console.print(f"[{sev_color}]{mark} {bc.contract or bc.kind:<30} [{bc.severity.upper()}]  {bc.scenario}[/{sev_color}]")
            if bc.base_summary:
                console.print(f"    BEFORE  {bc.base_summary}")
            if bc.head_summary:
                console.print(f"    AFTER   {bc.head_summary}")
        console.print()

    if report.attributions:
        console.print("[bold]LIKELY CAUSE[/bold]")
        for attr in report.attributions:
            conf_color = "green" if attr.confidence == "confirmed" else "cyan"
            console.print(f"  [bold]{attr.cause_dep_id}[/bold]  [{conf_color}]{attr.confidence.upper()} by {attr.method}[/{conf_color}]")
            if attr.rationale:
                console.print(f"    \"{attr.rationale}\"")
        console.print()

    if not report.is_conforming:
        console.print(f"[bold red]BREAKING CHANGES: {report.summary.get('breaking', 0)}[/bold red]")
        console.print("  go back    [cyan]agentlock restore[/cyan]")
        console.print("  keep it    [cyan]agentlock lock --accept[/cyan]\n")
    else:
        console.print("[bold green]✓ No breaking behavioral changes detected.[/bold green]\n")


def render_diff_markdown(report: DiffReport) -> str:
    """Render diff report as GitHub Markdown for PR comments."""
    lines = [
        f"### AgentLock State Diff (`{report.base_state}` $\\rightarrow$ `{report.head_state}`)",
        "",
    ]
    if report.dependency_changes:
        lines.append("#### Dependency Changes")
        for dc in report.dependency_changes:
            lines.append(f"- `{dc.dep_id}`: {dc.summary}")
        lines.append("")

    if report.behavior_changes:
        lines.append("#### Behavioral Changes")
        for bc in report.behavior_changes:
            mark = "❌" if bc.severity == "breaking" else "⚠️"
            lines.append(f"- {mark} **{bc.contract or bc.kind}** (`{bc.severity.upper()}`): {bc.head_summary}")
        lines.append("")

    if report.attributions:
        lines.append("#### Causal Attribution")
        for attr in report.attributions:
            lines.append(f"- **{attr.cause_dep_id}** ({attr.confidence}): {attr.rationale}")
        lines.append("")

    return "\n".join(lines)


def render_verify_terminal(result: VerificationResult) -> None:
    """Render verification result to Rich terminal."""
    console.print("\n[bold]Verifying working tree against agent.lock[/bold]\n")
    if result.verdict == "CONFORMS":
        console.print(f"[bold green]CONFORMS[/bold green] - {result.summary_message}\n")
    elif result.verdict == "CONFORMS WITH DRIFT":
        console.print(f"[bold yellow]CONFORMS WITH DRIFT[/bold yellow] - {result.summary_message}\n")
    else:
        console.print(f"[bold red]VIOLATES[/bold red] - {result.summary_message}\n")
        if result.diff_report:
            render_diff_terminal(result.diff_report)


def render_restore_terminal(plan: RestorePlan) -> None:
    """Render restore plan to Rich terminal."""
    console.print("\n[bold]Restoring agent.lock dependencies[/bold]\n")
    for item in plan.items:
        color = "green" if item.dep_class == "reproducible" else "yellow"
        console.print(f"  [{color}]↺ {item.dep_id:<25} [{item.dep_class}]  {item.action}[/{color}]")
    console.print(f"\n[bold green]Restored {plan.restorable_count} dependency files.[/bold green]")
    console.print("Next: [cyan]agentlock verify[/cyan]\n")

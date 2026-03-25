from __future__ import annotations

import json

import typer
import uvicorn
from rich.console import Console
from rich.panel import Panel

from protein_agent.agent.core import ProteinBinderAgent
from protein_agent.agent.service import ProteinBinderService
from protein_agent.config.settings import Settings

app = typer.Typer(help="Protein Binder Agent CLI")
console = Console()


def _load_settings(config_path: str | None = None) -> Settings:
    return Settings.from_env(config_path_override=config_path)


@app.command()
def chat(
    request: str = typer.Argument(..., help="Natural-language binder design request"),
    config: str | None = typer.Option(None, help="Optional config file override"),
    preferred_workflow: str | None = typer.Option(None, help="balanced / complexa_only / bindcraft_only"),
):
    settings = _load_settings(config)
    agent = ProteinBinderAgent(settings)
    result = agent.run(request, preferred_workflow=preferred_workflow)
    console.print(Panel(result["reply"], title="Agent Reply"))


@app.command()
def status(config: str | None = typer.Option(None, help="Optional config file override")):
    settings = _load_settings(config)
    service = ProteinBinderService(settings)
    console.print(Panel(json.dumps(service.status(), indent=2, ensure_ascii=False), title="Status"))


@app.command()
def bindcraft(
    target_pdb: str = typer.Argument(...),
    target_hotspot: str | None = typer.Option(None),
    target_chain: str | None = typer.Option(None),
    binder_length: int | None = typer.Option(None),
    num_designs: int | None = typer.Option(None),
    run_name: str = typer.Option("bindcraft_run"),
    output_dir: str | None = typer.Option(None),
    config: str | None = typer.Option(None, help="Optional config file override"),
):
    settings = _load_settings(config)
    service = ProteinBinderService(settings)
    result = service.run_bindcraft(
        target_pdb,
        target_hotspot=target_hotspot,
        target_chain=target_chain,
        binder_length=binder_length,
        num_designs=num_designs,
        run_name=run_name,
        output_dir=output_dir,
    )
    console.print(Panel(service.format_execution_reply(result), title="BindCraft"))


@app.command()
def complexa(
    task_name: str = typer.Argument(...),
    pipeline: str | None = typer.Option(None),
    run_name: str = typer.Option("complexa_run"),
    gen_njobs: int | None = typer.Option(None),
    eval_njobs: int | None = typer.Option(None),
    config: str | None = typer.Option(None, help="Optional config file override"),
):
    settings = _load_settings(config)
    service = ProteinBinderService(settings)
    result = service.run_complexa(
        task_name,
        pipeline=pipeline,
        run_name=run_name,
        gen_njobs=gen_njobs,
        eval_njobs=eval_njobs,
    )
    console.print(Panel(service.format_execution_reply(result), title="Proteina-Complexa"))


@app.command()
def analyze(
    structure_file: str = typer.Argument(...),
    analysis_type: str = typer.Option("full_report"),
    binder_chain: str | None = typer.Option(None),
    target_chain: str | None = typer.Option(None),
    output_dir: str | None = typer.Option(None),
    cutoff: float | None = typer.Option(None),
    config: str | None = typer.Option(None, help="Optional config file override"),
):
    settings = _load_settings(config)
    service = ProteinBinderService(settings)
    result = service.analyze_structure(
        structure_file,
        analysis_type=analysis_type,
        binder_chain=binder_chain,
        target_chain=target_chain,
        output_dir=output_dir,
        cutoff=cutoff,
    )
    console.print(Panel(service.format_execution_reply(result), title="MDAnalysis"))


@app.command()
def pipeline(
    target_pdb: str = typer.Argument(...),
    workflow: str | None = typer.Option(None),
    hotspot: str | None = typer.Option(None),
    binder_length: int | None = typer.Option(None),
    num_designs: int | None = typer.Option(None),
    run_name: str = typer.Option("pipeline_run"),
    target_chain: str | None = typer.Option(None),
    binder_chain: str | None = typer.Option(None),
    complexa_task_name: str | None = typer.Option(None),
    config: str | None = typer.Option(None, help="Optional config file override"),
):
    settings = _load_settings(config)
    service = ProteinBinderService(settings)
    result = service.run_pipeline(
        target_pdb,
        workflow=workflow,
        hotspot=hotspot,
        binder_length=binder_length,
        num_designs=num_designs,
        run_name=run_name,
        target_chain=target_chain,
        binder_chain=binder_chain,
        complexa_task_name=complexa_task_name,
    )
    console.print(Panel(service.format_execution_reply(result), title="Full Pipeline"))


@app.command()
def serve(
    host: str | None = typer.Option(None),
    port: int | None = typer.Option(None),
    config: str | None = typer.Option(None, help="Optional config file override"),
):
    settings = _load_settings(config)
    uvicorn.run(
        "protein_agent.api.main:app",
        host=host or settings.api_host,
        port=port or settings.api_port,
        reload=False,
    )


if __name__ == "__main__":
    app()

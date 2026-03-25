from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.panel import Panel

from agent.core import ProteinBinderAgent
from pipeline.orchestrator import PipelineOrchestrator
from tools import BindCraftTool, ComplexaTool, MDAnalysisTool

app = typer.Typer(help="蛋白质 Binder 设计 Agent")
console = Console()


def load_config(config_path: str = "config/agent_config.yaml") -> dict:
    return yaml.safe_load(Path(config_path).read_text())


@app.command()
def chat(
    request: str = typer.Argument(..., help="设计请求，如：为 PDL1 设计一个 binder"),
    config: str = typer.Option("config/agent_config.yaml", help="配置文件路径"),
    api_key: str = typer.Option(None, envvar="ANTHROPIC_API_KEY"),
):
    cfg = load_config(config)
    agent = ProteinBinderAgent(config=cfg, api_key=api_key)
    console.print(Panel(f"[bold cyan]任务:[/bold cyan] {request}", title="Protein Binder Agent"))
    result = agent.run(request)
    console.print(Panel(result, title="[bold green]Agent 输出[/bold green]"))


@app.command()
def pipeline(
    target_pdb: str = typer.Argument(..., help="靶蛋白 PDB 文件"),
    run_name: str = typer.Option("pipeline_run", help="运行名称"),
    hotspot: str = typer.Option(None, help="热点残基，如 A20,A45"),
    use_complexa: bool = typer.Option(True),
    use_bindcraft: bool = typer.Option(True),
    config: str = typer.Option("config/agent_config.yaml"),
):
    cfg = load_config(config)
    orch = PipelineOrchestrator(
        bindcraft=BindCraftTool(cfg["bindcraft_dir"]),
        complexa=ComplexaTool(cfg["complexa_dir"], cfg["complexa_venv_python"], cfg["complexa_config_dir"]),
        mda=MDAnalysisTool(),
    )
    results = orch.full_design_and_analysis_pipeline(
        target_pdb=target_pdb,
        run_name=run_name,
        use_complexa=use_complexa,
        use_bindcraft=use_bindcraft,
        hotspot=hotspot,
    )
    console.print("[bold green]Top 5 binder:[/bold green]")
    for i, r in enumerate(results["ranking"], 1):
        console.print(f"  {i}. {Path(r['pdb']).name} | score={r['score']} | hbonds={r['n_hbonds']}")


if __name__ == "__main__":
    app()

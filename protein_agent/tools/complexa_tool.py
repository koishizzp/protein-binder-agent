import subprocess
from pathlib import Path

from .base import BaseTool, ToolResult


class ComplexaTool(BaseTool):
    name = "proteina_complexa"
    description = (
        "使用 Proteina-Complexa 生成蛋白质 binder 结构。"
        "支持蛋白质靶点、小分子靶点和 motif scaffolding。"
    )

    def __init__(self, complexa_dir: str, venv_python: str, config_dir: str):
        self.complexa_dir = Path(complexa_dir)
        self.venv_python = venv_python
        self.config_dir = Path(config_dir)

    def run(
        self,
        task_name: str,
        pipeline: str = "binder",
        run_name: str = "agent_run",
        gen_njobs: int = 1,
        eval_njobs: int = 1,
        extra_overrides: dict | None = None,
    ) -> ToolResult:
        pipeline_configs = {
            "binder": "configs/search_binder_local_pipeline.yaml",
            "ligand_binder": "configs/search_ligand_binder_local_pipeline.yaml",
            "ame": "configs/search_ame_local_pipeline.yaml",
            "motif": "configs/search_motif_local_pipeline.yaml",
        }
        config = pipeline_configs.get(pipeline)
        if not config:
            return ToolResult(False, self.name, error=f"未知 pipeline 类型: {pipeline}")

        cmd = [
            "complexa",
            "design",
            config,
            f"++run_name={run_name}",
            f"++generation.task_name={task_name}",
            f"++gen_njobs={gen_njobs}",
            f"++eval_njobs={eval_njobs}",
        ]
        if extra_overrides:
            for k, v in extra_overrides.items():
                cmd.append(f"++{k}={v}")

        try:
            result = subprocess.run(
                cmd,
                cwd=self.complexa_dir,
                capture_output=True,
                text=True,
                timeout=7200,
            )
            output_dir = self.complexa_dir / "outputs" / run_name
            output_files = list(output_dir.glob("**/*.pdb")) + list(output_dir.glob("**/*.csv"))
            if result.returncode == 0:
                return ToolResult(
                    True,
                    self.name,
                    output=result.stdout[-3000:],
                    output_files=[str(f) for f in output_files],
                    metadata={"run_name": run_name, "task": task_name, "pipeline": pipeline},
                )
            return ToolResult(False, self.name, error=result.stderr[-2000:])
        except subprocess.TimeoutExpired:
            return ToolResult(False, self.name, error="Proteina-Complexa 超时（>2h）")
        except Exception as e:
            return ToolResult(False, self.name, error=str(e))

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "task_name": {"type": "string", "description": "靶蛋白任务名，如 02_PDL1"},
                    "pipeline": {
                        "type": "string",
                        "enum": ["binder", "ligand_binder", "ame", "motif"],
                        "description": "选择 pipeline 类型",
                    },
                    "run_name": {"type": "string", "description": "本次运行的唯一名称"},
                    "gen_njobs": {"type": "integer", "description": "生成并行 GPU 数"},
                    "eval_njobs": {"type": "integer", "description": "评估并行 GPU 数"},
                    "extra_overrides": {"type": "object", "description": "额外的 Hydra 配置覆盖"},
                },
                "required": ["task_name"],
            },
        }

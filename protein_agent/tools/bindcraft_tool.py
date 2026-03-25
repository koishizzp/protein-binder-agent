import json
import subprocess
from pathlib import Path

from .base import BaseTool, ToolResult


class BindCraftTool(BaseTool):
    name = "bindcraft"
    description = "使用 BindCraft 进行蛋白质 binder 设计。基于 RFdiffusion + ProteinMPNN + AlphaFold2 流水线。"

    def __init__(self, bindcraft_dir: str, settings_dir: str | None = None):
        self.bindcraft_dir = Path(bindcraft_dir)
        self.settings_dir = Path(settings_dir) if settings_dir else self.bindcraft_dir / "settings_target"

    def run(
        self,
        target_pdb: str,
        target_hotspot: str | None = None,
        binder_length: int = 80,
        num_designs: int = 10,
        run_name: str = "bindcraft_run",
        output_dir: str | None = None,
        filters_file: str | None = None,
        advanced_settings_file: str | None = None,
    ) -> ToolResult:
        output_path = Path(output_dir) if output_dir else self.bindcraft_dir / "outputs" / run_name
        settings = {
            "target_pdb": str(target_pdb),
            "target_hotspot": target_hotspot or "",
            "lengths": [binder_length - 10, binder_length + 10],
            "number_of_final_designs": num_designs,
            "output_dir": str(output_path),
        }
        settings_file = output_path / "settings.json"
        output_path.mkdir(parents=True, exist_ok=True)
        settings_file.write_text(json.dumps(settings, indent=2))

        filters = filters_file or str(self.settings_dir / "default_filters.json")
        advanced = advanced_settings_file or str(self.settings_dir / "4stage_multimer.json")

        cmd = [
            "python",
            str(self.bindcraft_dir / "bindcraft.py"),
            "--settings",
            str(settings_file),
            "--filters",
            filters,
            "--advanced",
            advanced,
        ]
        try:
            result = subprocess.run(
                cmd,
                cwd=self.bindcraft_dir,
                capture_output=True,
                text=True,
                timeout=10800,
            )
            output_files = list(output_path.glob("**/*.pdb")) + list(output_path.glob("**/*.csv"))
            if result.returncode == 0:
                return ToolResult(
                    True,
                    self.name,
                    output=result.stdout[-3000:],
                    output_files=[str(f) for f in output_files],
                    metadata={
                        "run_name": run_name,
                        "n_designs": len([f for f in output_files if f.suffix == ".pdb"]),
                    },
                )
            return ToolResult(False, self.name, error=result.stderr[-2000:])
        except subprocess.TimeoutExpired:
            return ToolResult(False, self.name, error="BindCraft 超时（>3h）")
        except Exception as e:
            return ToolResult(False, self.name, error=str(e))

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "target_pdb": {"type": "string", "description": "靶蛋白 PDB 文件路径"},
                    "target_hotspot": {"type": "string", "description": "热点残基，如 A20,A45"},
                    "binder_length": {"type": "integer", "description": "binder 残基数（中心值±10）"},
                    "num_designs": {"type": "integer", "description": "生成 binder 数量"},
                    "run_name": {"type": "string"},
                    "output_dir": {"type": "string"},
                },
                "required": ["target_pdb"],
            },
        }

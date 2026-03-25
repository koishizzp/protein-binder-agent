from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .base import BaseTool, ToolResult


class ComplexaTool(BaseTool):
    name = "proteina-complexa"
    description = (
        "Run Proteina-Complexa through the official complexa CLI. "
        "The upstream project exposes commands such as complexa validate and complexa design."
    )

    PIPELINE_CONFIGS = {
        "binder": "search_binder_local_pipeline.yaml",
        "ligand_binder": "search_ligand_binder_local_pipeline.yaml",
        "ame": "search_ame_local_pipeline.yaml",
        "motif": "search_motif_local_pipeline.yaml",
    }

    def __init__(
        self,
        complexa_dir: str | None,
        *,
        python_executable: str | None = None,
        cli_path: str | None = None,
        config_dir: str | None = None,
        default_overrides: dict[str, Any] | None = None,
        timeout_seconds: int = 7200,
    ) -> None:
        self.complexa_dir = Path(complexa_dir).expanduser().resolve() if complexa_dir else None
        self.python_executable = python_executable
        self.cli_path = cli_path
        self.config_dir = Path(config_dir).expanduser().resolve() if config_dir else None
        self.default_overrides = dict(default_overrides or {})
        self.timeout_seconds = timeout_seconds

    def _resolved_config_dir(self) -> Path | None:
        if self.config_dir:
            return self.config_dir
        if not self.complexa_dir:
            return None
        return self.complexa_dir / "configs"

    def _resolved_pipeline_config(self, pipeline: str) -> Path | None:
        config_dir = self._resolved_config_dir()
        config_name = self.PIPELINE_CONFIGS.get(pipeline)
        if not config_dir or not config_name:
            return None
        return config_dir / config_name

    def _command_prefix(self) -> list[str]:
        if self.cli_path:
            return [self.cli_path]
        if self.python_executable:
            return [self.python_executable, "-m", "complexa"]
        return ["complexa"]

    def _discover_outputs(self, start_time: datetime) -> list[str]:
        if not self.complexa_dir:
            return []
        candidate_roots = [self.complexa_dir / "outputs", self.complexa_dir / "multirun"]
        threshold = start_time.timestamp() - 2
        files: list[str] = []
        for root in candidate_roots:
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                if path.suffix.lower() not in {".pdb", ".csv", ".json", ".yaml", ".txt"}:
                    continue
                try:
                    if path.stat().st_mtime < threshold:
                        continue
                except OSError:
                    continue
                files.append(str(path))
        return sorted(set(files))

    def run(
        self,
        task_name: str,
        *,
        pipeline: str = "binder",
        run_name: str = "complexa_run",
        gen_njobs: int = 1,
        eval_njobs: int = 1,
        stage: str = "design",
        extra_overrides: dict[str, Any] | None = None,
        validate_first: bool = True,
    ) -> ToolResult:
        if not task_name.strip():
            return ToolResult(False, self.name, error="task_name is required for Proteina-Complexa")
        if not self.complexa_dir or not self.complexa_dir.exists():
            return ToolResult(False, self.name, error="Proteina-Complexa directory is not configured or does not exist")

        config_path = self._resolved_pipeline_config(pipeline)
        if not config_path or not config_path.exists():
            return ToolResult(False, self.name, error=f"Pipeline config not found for '{pipeline}'")

        prefix = self._command_prefix()
        design_command = prefix + [
            stage,
            str(config_path),
            f"++run_name={run_name}",
            f"++generation.task_name={task_name}",
            f"++gen_njobs={gen_njobs}",
            f"++eval_njobs={eval_njobs}",
        ]
        merged_overrides = dict(self.default_overrides)
        merged_overrides.update(extra_overrides or {})
        for key, value in sorted(merged_overrides.items()):
            design_command.append(f"++{key}={value}")

        start_time = datetime.now(timezone.utc)
        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []

        if validate_first:
            validate_command = prefix + ["validate", stage, str(config_path)]
            try:
                validate_result = subprocess.run(
                    validate_command,
                    cwd=self.complexa_dir,
                    capture_output=True,
                    text=True,
                    timeout=min(self.timeout_seconds, 600),
                )
            except Exception as exc:  # noqa: BLE001
                return ToolResult(False, self.name, error=f"Validation failed to start: {exc}", command=validate_command)
            stdout_chunks.append(validate_result.stdout[-2000:])
            stderr_chunks.append(validate_result.stderr[-2000:])
            if validate_result.returncode != 0:
                return ToolResult(
                    False,
                    self.name,
                    error=validate_result.stderr[-2000:] or "complexa validate failed",
                    metadata={"pipeline": pipeline, "task_name": task_name, "run_name": run_name},
                    command=validate_command,
                    stdout=validate_result.stdout[-2000:],
                    stderr=validate_result.stderr[-2000:],
                )

        try:
            result = subprocess.run(
                design_command,
                cwd=self.complexa_dir,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                False,
                self.name,
                error=f"Proteina-Complexa timed out after {self.timeout_seconds} seconds",
                command=design_command,
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(False, self.name, error=str(exc), command=design_command)

        stdout_chunks.append(result.stdout[-4000:])
        stderr_chunks.append(result.stderr[-2000:])
        output_files = self._discover_outputs(start_time)
        metadata = {
            "pipeline": pipeline,
            "task_name": task_name,
            "run_name": run_name,
            "stage": stage,
            "returncode": result.returncode,
            "n_output_files": len(output_files),
            "config_path": str(config_path),
        }
        if result.returncode == 0:
            return ToolResult(
                True,
                self.name,
                output={
                    "stdout_tail": result.stdout[-4000:],
                    "stage": stage,
                    "pipeline": pipeline,
                },
                metadata=metadata,
                output_files=output_files,
                command=design_command,
                stdout="\n".join(chunk for chunk in stdout_chunks if chunk),
                stderr="\n".join(chunk for chunk in stderr_chunks if chunk),
            )
        return ToolResult(
            False,
            self.name,
            error=result.stderr[-2000:] or result.stdout[-2000:] or "Proteina-Complexa exited with a non-zero code",
            metadata=metadata,
            output_files=output_files,
            command=design_command,
            stdout="\n".join(chunk for chunk in stdout_chunks if chunk),
            stderr="\n".join(chunk for chunk in stderr_chunks if chunk),
        )

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "task_name": {"type": "string", "description": "Complexa target/task identifier"},
                    "pipeline": {
                        "type": "string",
                        "enum": sorted(self.PIPELINE_CONFIGS),
                        "description": "Complexa pipeline type",
                    },
                    "run_name": {"type": "string"},
                    "gen_njobs": {"type": "integer"},
                    "eval_njobs": {"type": "integer"},
                    "stage": {
                        "type": "string",
                        "enum": ["design", "generate", "filter", "evaluate", "analyze", "analysis", "status"],
                    },
                    "extra_overrides": {"type": "object"},
                },
                "required": ["task_name"],
            },
        }

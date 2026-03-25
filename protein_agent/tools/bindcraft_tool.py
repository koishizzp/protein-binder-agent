from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .base import BaseTool, ToolResult
from .structure_tool import CIF_SUFFIXES, COPY_TO_PDB_SUFFIXES


class BindCraftTool(BaseTool):
    name = "bindcraft"
    description = (
        "Run the BindCraft binder-design pipeline. "
        "This wrapper writes a target settings JSON and launches bindcraft.py."
    )

    def __init__(
        self,
        bindcraft_dir: str | None,
        *,
        python_executable: str = "python",
        settings_dir: str | None = None,
        filters_file: str | None = None,
        advanced_settings_file: str | None = None,
        timeout_seconds: int = 10800,
    ) -> None:
        self.bindcraft_dir = Path(bindcraft_dir).expanduser().resolve() if bindcraft_dir else None
        self.python_executable = python_executable
        self.timeout_seconds = timeout_seconds
        self.settings_dir = Path(settings_dir).expanduser().resolve() if settings_dir else None
        self.filters_file = Path(filters_file).expanduser().resolve() if filters_file else None
        self.advanced_settings_file = (
            Path(advanced_settings_file).expanduser().resolve() if advanced_settings_file else None
        )

    def _python_candidates(self) -> list[str]:
        candidates: list[str] = []
        seen: set[str] = set()

        def add(value: str | None) -> None:
            if not value:
                return
            normalized = value.strip()
            if not normalized or normalized in seen:
                return
            seen.add(normalized)
            candidates.append(normalized)

        add(self.python_executable)
        if self.bindcraft_dir:
            root = self.bindcraft_dir
            for relative in (
                ".venv/bin/python",
                "venv/bin/python",
                "env/bin/python",
                "../.venv/bin/python",
                "../venv/bin/python",
                "../bindcraft_env/bin/python",
                "../pyrosetta_env/bin/python",
            ):
                add(str((root / relative).resolve()))
        add(os.environ.get("CONDA_PYTHON_EXE"))
        add(os.environ.get("PYTHON"))
        add("python3")
        add("python")
        return candidates

    def _python_exists(self, python_executable: str) -> bool:
        if "/" in python_executable or "\\" in python_executable:
            return Path(python_executable).exists()
        return True

    def _python_supports_pyrosetta(self, python_executable: str) -> bool:
        if not self._python_exists(python_executable):
            return False
        try:
            result = subprocess.run(
                [python_executable, "-c", "import pyrosetta"],
                capture_output=True,
                text=True,
                timeout=20,
            )
            return result.returncode == 0
        except Exception:  # noqa: BLE001
            return False

    def _resolve_python_executable(self) -> str | None:
        for candidate in self._python_candidates():
            if self._python_supports_pyrosetta(candidate):
                return candidate
        return None

    def _default_settings_dir(self) -> Path | None:
        if self.settings_dir:
            return self.settings_dir
        if not self.bindcraft_dir:
            return None
        return self.bindcraft_dir / "settings_target"

    def _default_filters_file(self) -> Path | None:
        if self.filters_file:
            return self.filters_file
        if not self.bindcraft_dir:
            return None
        return self.bindcraft_dir / "settings_filters" / "default_filters.json"

    def _default_advanced_file(self) -> Path | None:
        if self.advanced_settings_file:
            return self.advanced_settings_file
        if not self.bindcraft_dir:
            return None
        return self.bindcraft_dir / "settings_advanced" / "default_4stage_multimer.json"

    def _discover_outputs(self, output_path: Path, start_time: datetime) -> list[str]:
        if not output_path.exists():
            return []
        files: list[str] = []
        threshold = start_time.timestamp() - 2
        for path in output_path.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".pdb", ".csv", ".json", ".png", ".html"} | CIF_SUFFIXES | COPY_TO_PDB_SUFFIXES:
                continue
            try:
                if path.stat().st_mtime < threshold:
                    continue
            except OSError:
                continue
            files.append(str(path))
        return sorted(files)

    def run(
        self,
        target_pdb: str,
        *,
        target_hotspot: str | None = None,
        target_chains: str = "A",
        binder_length: int = 80,
        num_designs: int = 10,
        run_name: str = "bindcraft_run",
        output_dir: str | None = None,
        binder_name: str | None = None,
        filters_file: str | None = None,
        advanced_settings_file: str | None = None,
        length_window: int = 10,
    ) -> ToolResult:
        target_path = Path(target_pdb).expanduser()
        if not target_path.exists():
            return ToolResult(False, self.name, error=f"Target PDB not found: {target_path}")
        if not self.bindcraft_dir or not self.bindcraft_dir.exists():
            return ToolResult(False, self.name, error="BindCraft directory is not configured or does not exist")

        bindcraft_entry = self.bindcraft_dir / "bindcraft.py"
        if not bindcraft_entry.exists():
            return ToolResult(False, self.name, error=f"BindCraft entrypoint not found: {bindcraft_entry}")
        runtime_python = self._resolve_python_executable()
        if not runtime_python:
            return ToolResult(
                False,
                self.name,
                error=(
                    "No BindCraft Python interpreter with pyrosetta available was found. "
                    "Set PROTEIN_BINDER_AGENT_BINDCRAFT_PYTHON to the correct environment."
                ),
            )

        output_path = (
            Path(output_dir).expanduser().resolve()
            if output_dir
            else (self.bindcraft_dir / "outputs" / run_name).resolve()
        )
        output_path.mkdir(parents=True, exist_ok=True)

        settings_payload = {
            "design_path": str(output_path),
            "binder_name": binder_name or run_name,
            "starting_pdb": str(target_path.resolve()),
            "chains": target_chains,
            "target_hotspot_residues": target_hotspot,
            "lengths": [max(4, binder_length - length_window), binder_length + length_window],
            "number_of_final_designs": num_designs,
        }

        settings_dir = self._default_settings_dir() or output_path
        settings_dir.mkdir(parents=True, exist_ok=True)
        settings_file = settings_dir / f"{run_name}.json"
        settings_file.write_text(json.dumps(settings_payload, indent=2), encoding="utf-8")

        resolved_filters = Path(filters_file).expanduser().resolve() if filters_file else self._default_filters_file()
        resolved_advanced = (
            Path(advanced_settings_file).expanduser().resolve()
            if advanced_settings_file
            else self._default_advanced_file()
        )

        command = [
            runtime_python,
            "-u",
            str(bindcraft_entry),
            "--settings",
            str(settings_file),
        ]
        if resolved_filters:
            command.extend(["--filters", str(resolved_filters)])
        if resolved_advanced:
            command.extend(["--advanced", str(resolved_advanced)])

        start_time = datetime.now(timezone.utc)
        try:
            result = subprocess.run(
                command,
                cwd=self.bindcraft_dir,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                False,
                self.name,
                error=f"BindCraft timed out after {self.timeout_seconds} seconds",
                command=command,
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(False, self.name, error=str(exc), command=command)

        output_files = self._discover_outputs(output_path, start_time)
        metadata = {
            "run_name": run_name,
            "settings_file": str(settings_file),
            "output_dir": str(output_path),
            "python_executable": runtime_python,
            "n_output_files": len(output_files),
            "returncode": result.returncode,
        }
        if result.returncode == 0:
            return ToolResult(
                True,
                self.name,
                output={
                    "settings": settings_payload,
                    "stdout_tail": result.stdout[-4000:],
                },
                metadata=metadata,
                output_files=output_files,
                command=command,
                stdout=result.stdout[-4000:],
                stderr=result.stderr[-2000:],
            )
        return ToolResult(
            False,
            self.name,
            error=result.stderr[-2000:] or result.stdout[-2000:] or "BindCraft exited with a non-zero code",
            metadata=metadata,
            output_files=output_files,
            command=command,
            stdout=result.stdout[-4000:],
            stderr=result.stderr[-2000:],
        )

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "target_pdb": {"type": "string", "description": "Path to the target PDB file"},
                    "target_hotspot": {
                        "type": "string",
                        "description": "Optional hotspot residues, e.g. A23,A25,A27-30",
                    },
                    "target_chains": {"type": "string", "description": "Target chains to keep, e.g. A or A,B"},
                    "binder_length": {"type": "integer", "description": "Desired binder length"},
                    "num_designs": {"type": "integer", "description": "Final accepted design count"},
                    "run_name": {"type": "string"},
                    "output_dir": {"type": "string"},
                },
                "required": ["target_pdb"],
            },
        }

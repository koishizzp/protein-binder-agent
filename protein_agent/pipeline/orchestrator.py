from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from protein_agent.pipeline.workflows import WORKFLOWS
from protein_agent.tools import BindCraftTool, ComplexaTool, MDAnalysisTool, ToolResult


class PipelineOrchestrator:
    def __init__(
        self,
        *,
        bindcraft: BindCraftTool,
        complexa: ComplexaTool,
        mda: MDAnalysisTool,
        result_dir: str,
        analysis_dir: str,
    ) -> None:
        self.bindcraft = bindcraft
        self.complexa = complexa
        self.mda = mda
        self.result_dir = Path(result_dir).expanduser().resolve()
        self.analysis_dir = Path(analysis_dir).expanduser().resolve()

    def _scored_row(
        self,
        *,
        pdb_file: str,
        source: str,
        report: dict[str, Any],
    ) -> dict[str, Any]:
        contacts = report.get("interface_contacts", {}) if isinstance(report.get("interface_contacts"), dict) else {}
        hbonds = report.get("hydrogen_bonds", {}) if isinstance(report.get("hydrogen_bonds"), dict) else {}
        residues = report.get("interface_residues", {}) if isinstance(report.get("interface_residues"), dict) else {}
        shape = (
            report.get("shape_complementarity_proxy", {})
            if isinstance(report.get("shape_complementarity_proxy"), dict)
            else {}
        )

        score = (
            float(contacts.get("n_contacts", 0)) * 0.35
            + float(hbonds.get("n_interface_hbonds", 0)) * 0.35
            + float(residues.get("binder_interface_count", 0)) * 0.10
            + float(shape.get("sc_proxy_score", 0)) * 100.0 * 0.20
        )
        return {
            "pdb": pdb_file,
            "source": source,
            "score": round(score, 3),
            "n_contacts": int(contacts.get("n_contacts", 0)),
            "n_hbonds": int(hbonds.get("n_interface_hbonds", 0)),
            "sc_proxy": float(shape.get("sc_proxy_score", 0)),
            "binder_interface_count": int(residues.get("binder_interface_count", 0)),
            "target_interface_count": int(residues.get("target_interface_count", 0)),
        }

    def _discover_pdbs(self, tool_result: ToolResult) -> list[str]:
        return [path for path in tool_result.output_files if path.lower().endswith(".pdb")]

    def full_design_and_analysis_pipeline(
        self,
        *,
        target_pdb: str,
        workflow: str = "balanced",
        hotspot: str | None = None,
        binder_length: int = 80,
        num_designs: int = 10,
        run_name: str = "pipeline_run",
        target_chain: str = "A",
        binder_chain: str = "B",
        complexa_task_name: str | None = None,
        use_complexa: bool | None = None,
        use_bindcraft: bool | None = None,
        complexa_default_pipeline: str = "binder",
        complexa_gen_njobs: int = 1,
        complexa_eval_njobs: int = 1,
    ) -> dict[str, Any]:
        target_path = Path(target_pdb).expanduser().resolve()
        if not target_path.exists():
            raise FileNotFoundError(f"Target PDB not found: {target_path}")

        profile = dict(WORKFLOWS.get(workflow, WORKFLOWS["balanced"]))
        resolved_use_complexa = profile["use_complexa"] if use_complexa is None else use_complexa
        resolved_use_bindcraft = profile["use_bindcraft"] if use_bindcraft is None else use_bindcraft

        run_root = self.result_dir / run_name
        analysis_root = self.analysis_dir / run_name
        run_root.mkdir(parents=True, exist_ok=True)
        analysis_root.mkdir(parents=True, exist_ok=True)

        target_summary = self.mda.run(
            "structure_summary",
            str(target_path),
            target_chain=target_chain,
            output_dir=str(analysis_root / "target"),
        )

        tool_runs: dict[str, Any] = {}
        warnings: list[str] = []
        generated_pdbs: list[tuple[str, str]] = []

        if resolved_use_complexa:
            task_name = complexa_task_name or target_path.stem
            complexa_result = self.complexa.run(
                task_name,
                pipeline=complexa_default_pipeline,
                run_name=f"{run_name}_complexa",
                gen_njobs=complexa_gen_njobs,
                eval_njobs=complexa_eval_njobs,
            )
            tool_runs["proteina-complexa"] = complexa_result.to_dict()
            generated_pdbs.extend((path, "proteina-complexa") for path in self._discover_pdbs(complexa_result))
            if not complexa_result.success:
                warnings.append(f"Proteina-Complexa failed: {complexa_result.error}")

        if resolved_use_bindcraft:
            bindcraft_result = self.bindcraft.run(
                str(target_path),
                target_hotspot=hotspot,
                target_chains=target_chain,
                binder_length=binder_length,
                num_designs=num_designs,
                run_name=f"{run_name}_bindcraft",
                output_dir=str(run_root / "bindcraft"),
            )
            tool_runs["bindcraft"] = bindcraft_result.to_dict()
            generated_pdbs.extend((path, "bindcraft") for path in self._discover_pdbs(bindcraft_result))
            if not bindcraft_result.success:
                warnings.append(f"BindCraft failed: {bindcraft_result.error}")

        scored: list[dict[str, Any]] = []
        for pdb_file, source in generated_pdbs:
            report_result = self.mda.run(
                "full_report",
                pdb_file,
                binder_chain=binder_chain,
                target_chain=target_chain,
                output_dir=str(analysis_root / Path(pdb_file).stem),
            )
            if not report_result.success or not isinstance(report_result.output, dict):
                warnings.append(f"MDAnalysis failed for {pdb_file}: {report_result.error}")
                continue
            row = self._scored_row(pdb_file=pdb_file, source=source, report=report_result.output)
            row["report_dir"] = str(analysis_root / Path(pdb_file).stem)
            scored.append(row)

        scored.sort(key=lambda item: item["score"], reverse=True)
        ranking = scored[:5]

        ranking_csv = run_root / "ranking.csv"
        ranking_json = run_root / "ranking.json"
        if scored:
            with ranking_csv.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(scored[0].keys()))
                writer.writeheader()
                writer.writerows(scored)
            ranking_json.write_text(json.dumps(scored, indent=2, ensure_ascii=False), encoding="utf-8")

        result = {
            "module": "full_pipeline",
            "request": {
                "target_pdb": str(target_path),
                "workflow": workflow,
                "hotspot": hotspot,
                "binder_length": binder_length,
                "num_designs": num_designs,
                "run_name": run_name,
                "target_chain": target_chain,
                "binder_chain": binder_chain,
                "complexa_task_name": complexa_task_name or target_path.stem,
                "use_complexa": resolved_use_complexa,
                "use_bindcraft": resolved_use_bindcraft,
            },
            "target_summary": target_summary.output if target_summary.success else {"error": target_summary.error},
            "tool_runs": tool_runs,
            "ranking": ranking,
            "designs": scored,
            "best_design": ranking[0] if ranking else None,
            "warnings": warnings,
            "artifacts": {
                "run_root": str(run_root),
                "analysis_root": str(analysis_root),
                "ranking_csv": str(ranking_csv) if ranking_csv.exists() else None,
                "ranking_json": str(ranking_json) if ranking_json.exists() else None,
            },
        }
        return result

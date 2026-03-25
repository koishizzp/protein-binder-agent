from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

try:
    import numpy as np
except Exception:  # noqa: BLE001
    np = None

try:
    import MDAnalysis as mda
    from MDAnalysis.analysis import rms
    from MDAnalysis.analysis.distances import distance_array
    from MDAnalysis.analysis.hydrogenbonds import HydrogenBondAnalysis
except Exception:  # noqa: BLE001
    mda = None
    rms = None
    distance_array = None
    HydrogenBondAnalysis = None

from .base import BaseTool, ToolResult


class MDAnalysisTool(BaseTool):
    name = "mdanalysis"
    description = (
        "Analyze protein structures with MDAnalysis. "
        "Supports structure summaries, interface contacts, hydrogen bond estimation, RMSD, and ranking reports."
    )

    def run(
        self,
        analysis_type: str,
        structure_file: str,
        *,
        topology_file: str | None = None,
        trajectory_file: str | None = None,
        binder_chain: str = "A",
        target_chain: str = "B",
        output_dir: str = "./analysis_output",
        cutoff: float = 5.0,
    ) -> ToolResult:
        structure_path = Path(structure_file).expanduser()
        if not structure_path.exists():
            return ToolResult(False, self.name, error=f"Structure file not found: {structure_path}")
        if mda is None or distance_array is None or np is None:
            return ToolResult(False, self.name, error="MDAnalysis is not installed in the current environment")

        output_path = Path(output_dir).expanduser().resolve()
        output_path.mkdir(parents=True, exist_ok=True)
        dispatch = {
            "structure_summary": self._structure_summary,
            "interface_contacts": self._analyze_interface_contacts,
            "hydrogen_bonds": self._analyze_hydrogen_bonds,
            "rmsd": self._analyze_rmsd,
            "interface_residues": self._identify_interface_residues,
            "shape_complementarity_proxy": self._shape_complementarity_proxy,
            "full_report": self._full_report,
        }
        fn = dispatch.get(analysis_type)
        if not fn:
            return ToolResult(
                False,
                self.name,
                error=f"Unknown analysis_type '{analysis_type}'. Available: {sorted(dispatch)}",
            )
        try:
            return fn(
                structure_file=str(structure_path),
                topology_file=topology_file,
                trajectory_file=trajectory_file,
                binder_chain=binder_chain,
                target_chain=target_chain,
                output_path=output_path,
                cutoff=cutoff,
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(False, self.name, error=str(exc))

    def _load_universe(self, structure_file: str, topology_file: str | None = None, trajectory_file: str | None = None):
        if topology_file and trajectory_file:
            return mda.Universe(topology_file, trajectory_file)
        if trajectory_file:
            return mda.Universe(structure_file, trajectory_file)
        return mda.Universe(structure_file)

    def _chain_selection(self, chain_id: str) -> str:
        normalized = str(chain_id or "").strip()
        if not normalized:
            raise ValueError("chain id cannot be empty")
        return f"(chainID {normalized} or segid {normalized})"

    def _select_chain_atoms(self, universe, chain_id: str):
        atoms = universe.select_atoms(self._chain_selection(chain_id))
        if len(atoms) == 0:
            raise ValueError(f"No atoms found for chain '{chain_id}'")
        return atoms

    def _write_json(self, output_path: Path, filename: str, payload: dict[str, Any]) -> str:
        out_file = output_path / filename
        out_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return str(out_file)

    def _structure_summary(self, structure_file: str, target_chain: str, output_path: Path, **kwargs: Any) -> ToolResult:
        universe = self._load_universe(structure_file)
        chains = sorted({str(atom.chainID or atom.segid).strip() for atom in universe.atoms if str(atom.chainID or atom.segid).strip()})
        selected = self._select_chain_atoms(universe, target_chain)
        result = {
            "structure_file": structure_file,
            "n_atoms": int(len(universe.atoms)),
            "n_residues": int(len(universe.residues)),
            "chains": chains,
            "selected_chain": target_chain,
            "selected_chain_residues": int(len(selected.residues)),
            "selected_chain_atoms": int(len(selected)),
        }
        return ToolResult(
            True,
            self.name,
            output=result,
            output_files=[self._write_json(output_path, "structure_summary.json", result)],
            metadata={"analysis": "structure_summary"},
        )

    def _analyze_interface_contacts(
        self,
        structure_file: str,
        binder_chain: str,
        target_chain: str,
        output_path: Path,
        cutoff: float,
        **kwargs: Any,
    ) -> ToolResult:
        universe = self._load_universe(structure_file)
        binder = self._select_chain_atoms(universe, binder_chain)
        target = self._select_chain_atoms(universe, target_chain)
        dist_mat = distance_array(binder.positions, target.positions)
        contact_mask = dist_mat <= cutoff
        n_contacts = int(contact_mask.sum())
        binder_residues = binder.residues[np.any(contact_mask, axis=1)] if len(binder) else []
        target_residues = target.residues[np.any(contact_mask, axis=0)] if len(target) else []
        result = {
            "n_contacts": n_contacts,
            "binder_interface_residues": int(len(binder_residues)),
            "target_interface_residues": int(len(target_residues)),
            "contact_density": round(n_contacts / max(len(binder.residues), 1), 4),
        }
        return ToolResult(
            True,
            self.name,
            output=result,
            output_files=[self._write_json(output_path, "interface_contacts.json", result)],
            metadata={"analysis": "interface_contacts"},
        )

    def _analyze_hydrogen_bonds(
        self,
        structure_file: str,
        binder_chain: str,
        target_chain: str,
        output_path: Path,
        **kwargs: Any,
    ) -> ToolResult:
        universe = self._load_universe(structure_file)
        method = "distance_proxy"
        n_hbonds = 0

        if HydrogenBondAnalysis is not None:
            try:
                analysis = HydrogenBondAnalysis(
                    universe=universe,
                    between=[self._chain_selection(binder_chain), self._chain_selection(target_chain)],
                )
                analysis.run()
                raw = getattr(analysis.results, "hbonds", None)
                if raw is not None:
                    n_hbonds = int(len(raw))
                    method = "mdanalysis_hba"
            except Exception:  # noqa: BLE001
                n_hbonds = 0

        if n_hbonds == 0:
            binder = universe.select_atoms(f"{self._chain_selection(binder_chain)} and name N O S")
            target = universe.select_atoms(f"{self._chain_selection(target_chain)} and name N O S")
            if len(binder) and len(target):
                dist_mat = distance_array(binder.positions, target.positions)
                n_hbonds = int((dist_mat <= 3.6).sum())

        result = {"n_interface_hbonds": n_hbonds, "method": method}
        return ToolResult(
            True,
            self.name,
            output=result,
            output_files=[self._write_json(output_path, "hydrogen_bonds.json", result)],
            metadata={"analysis": "hydrogen_bonds"},
        )

    def _analyze_rmsd(
        self,
        structure_file: str,
        topology_file: str | None,
        trajectory_file: str | None,
        binder_chain: str,
        output_path: Path,
        **kwargs: Any,
    ) -> ToolResult:
        if not trajectory_file:
            return ToolResult(False, self.name, error="trajectory_file is required for RMSD analysis")
        if rms is None:
            return ToolResult(False, self.name, error="MDAnalysis RMSD module is unavailable")

        universe = self._load_universe(structure_file, topology_file, trajectory_file)
        reference = self._load_universe(structure_file)
        selection = f"backbone and {self._chain_selection(binder_chain)}"
        calculator = rms.RMSD(universe, reference, select=selection)
        calculator.run()
        out_file = output_path / "rmsd.csv"
        rows = calculator.results.rmsd.tolist()
        with out_file.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["frame", "time", "rmsd"])
            writer.writerows(rows)
        rmsd_values = [float(row[2]) for row in rows]
        result = {
            "mean_rmsd": round(sum(rmsd_values) / max(len(rmsd_values), 1), 4),
            "max_rmsd": round(max(rmsd_values), 4) if rmsd_values else 0.0,
            "n_frames": int(len(rows)),
        }
        return ToolResult(True, self.name, output=result, output_files=[str(out_file)], metadata={"analysis": "rmsd"})

    def _identify_interface_residues(
        self,
        structure_file: str,
        binder_chain: str,
        target_chain: str,
        output_path: Path,
        cutoff: float,
        **kwargs: Any,
    ) -> ToolResult:
        universe = self._load_universe(structure_file)
        binder_sel = universe.select_atoms(
            f"{self._chain_selection(binder_chain)} and around {cutoff} {self._chain_selection(target_chain)}"
        )
        target_sel = universe.select_atoms(
            f"{self._chain_selection(target_chain)} and around {cutoff} {self._chain_selection(binder_chain)}"
        )
        binder_res = sorted({f"{res.resname}{res.resid}" for res in binder_sel.residues})
        target_res = sorted({f"{res.resname}{res.resid}" for res in target_sel.residues})
        result = {
            "binder_interface": binder_res,
            "target_interface": target_res,
            "binder_interface_count": len(binder_res),
            "target_interface_count": len(target_res),
        }
        return ToolResult(
            True,
            self.name,
            output=result,
            output_files=[self._write_json(output_path, "interface_residues.json", result)],
            metadata={"analysis": "interface_residues"},
        )

    def _shape_complementarity_proxy(
        self,
        structure_file: str,
        binder_chain: str,
        target_chain: str,
        output_path: Path,
        cutoff: float,
        **kwargs: Any,
    ) -> ToolResult:
        universe = self._load_universe(structure_file)
        binder = self._select_chain_atoms(universe, binder_chain)
        target = self._select_chain_atoms(universe, target_chain)
        dist_mat = distance_array(binder.positions, target.positions)
        n_close = int((dist_mat <= cutoff).sum())
        n_very_close = int((dist_mat <= 3.5).sum())
        result = {
            "n_contacts_5A": n_close,
            "n_contacts_3.5A": n_very_close,
            "sc_proxy_score": round(n_very_close / max(n_close, 1), 4),
        }
        return ToolResult(
            True,
            self.name,
            output=result,
            output_files=[self._write_json(output_path, "shape_complementarity_proxy.json", result)],
            metadata={"analysis": "shape_complementarity_proxy"},
        )

    def _full_report(
        self,
        structure_file: str,
        binder_chain: str,
        target_chain: str,
        output_path: Path,
        cutoff: float,
        **kwargs: Any,
    ) -> ToolResult:
        report: dict[str, Any] = {}
        files: list[str] = []
        for analysis in (
            "structure_summary",
            "interface_contacts",
            "hydrogen_bonds",
            "interface_residues",
            "shape_complementarity_proxy",
        ):
            result = self.run(
                analysis,
                structure_file,
                binder_chain=binder_chain,
                target_chain=target_chain,
                output_dir=str(output_path),
                cutoff=cutoff,
            )
            report[analysis] = result.output if result.success else {"error": result.error}
            files.extend(result.output_files)
        out_file = self._write_json(output_path, "full_report.json", report)
        files.append(out_file)
        return ToolResult(True, self.name, output=report, output_files=sorted(set(files)), metadata={"analysis": "full_report"})

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "analysis_type": {
                        "type": "string",
                        "enum": [
                            "structure_summary",
                            "interface_contacts",
                            "hydrogen_bonds",
                            "rmsd",
                            "interface_residues",
                            "shape_complementarity_proxy",
                            "full_report",
                        ],
                    },
                    "structure_file": {"type": "string"},
                    "topology_file": {"type": "string"},
                    "trajectory_file": {"type": "string"},
                    "binder_chain": {"type": "string", "default": "A"},
                    "target_chain": {"type": "string", "default": "B"},
                    "output_dir": {"type": "string"},
                    "cutoff": {"type": "number", "default": 5.0},
                },
                "required": ["analysis_type", "structure_file"],
            },
        }

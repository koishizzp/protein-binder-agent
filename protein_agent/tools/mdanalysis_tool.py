from pathlib import Path

import MDAnalysis as mda
import numpy as np
import pandas as pd
from MDAnalysis.analysis import distances, rms
from MDAnalysis.analysis.hydrogenbonds import HydrogenBondAnalysis

from .base import BaseTool, ToolResult


class MDAnalysisTool(BaseTool):
    name = "mdanalysis"
    description = "使用 MDAnalysis 分析蛋白质复合物结构。支持界面接触分析、氢键分析、RMSD、SASA、界面残基识别等。"

    def run(
        self,
        analysis_type: str,
        structure_file: str,
        topology_file: str | None = None,
        trajectory_file: str | None = None,
        binder_chain: str = "A",
        target_chain: str = "B",
        output_dir: str = "./analysis_output",
        cutoff: float = 5.0,
    ) -> ToolResult:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        dispatch = {
            "interface_contacts": self._analyze_interface_contacts,
            "hydrogen_bonds": self._analyze_hydrogen_bonds,
            "rmsd": self._analyze_rmsd,
            "interface_residues": self._identify_interface_residues,
            "shape_complementarity_proxy": self._shape_complementarity_proxy,
            "full_report": self._full_report,
        }
        fn = dispatch.get(analysis_type)
        if not fn:
            return ToolResult(False, self.name, error=f"未知分析类型: {analysis_type}。可用: {list(dispatch.keys())}")
        try:
            return fn(
                structure_file=structure_file,
                topology_file=topology_file,
                trajectory_file=trajectory_file,
                binder_chain=binder_chain,
                target_chain=target_chain,
                output_path=output_path,
                cutoff=cutoff,
            )
        except Exception as e:
            return ToolResult(False, self.name, error=str(e))

    def _load_universe(self, structure_file, topology_file=None, trajectory_file=None):
        if topology_file and trajectory_file:
            return mda.Universe(topology_file, trajectory_file)
        return mda.Universe(structure_file)

    def _analyze_interface_contacts(self, structure_file, binder_chain, target_chain, output_path, cutoff, **kwargs):
        import json

        u = self._load_universe(structure_file)
        binder = u.select_atoms(f"chainID {binder_chain}")
        target = u.select_atoms(f"chainID {target_chain}")
        contact_matrix = distances.contact_matrix(binder.positions, target.positions, cutoff=cutoff)
        n_contacts = int(contact_matrix.sum())
        binder_residues = np.unique(binder.resindices[contact_matrix.any(axis=1)])
        target_residues = np.unique(target.resindices[contact_matrix.any(axis=0)])
        result = {
            "n_contacts": n_contacts,
            "binder_interface_residues": len(binder_residues),
            "target_interface_residues": len(target_residues),
            "contact_density": n_contacts / max(len(binder.residues), 1),
        }
        out_file = output_path / "interface_contacts.json"
        out_file.write_text(json.dumps(result, indent=2))
        return ToolResult(True, self.name, output=result, output_files=[str(out_file)], metadata={"analysis": "interface_contacts"})

    def _analyze_hydrogen_bonds(self, structure_file, binder_chain, target_chain, output_path, **kwargs):
        import json

        u = self._load_universe(structure_file)
        hbonds = HydrogenBondAnalysis(universe=u, between=[f"chainID {binder_chain}", f"chainID {target_chain}"])
        hbonds.run()
        n_hbonds = len(hbonds.results.hbonds) if hbonds.results.hbonds is not None else 0
        result = {"n_interface_hbonds": n_hbonds}
        out_file = output_path / "hbonds.json"
        out_file.write_text(json.dumps(result, indent=2))
        return ToolResult(True, self.name, output=result, output_files=[str(out_file)])

    def _analyze_rmsd(self, structure_file, topology_file, trajectory_file, binder_chain, output_path, **kwargs):
        if not trajectory_file:
            return ToolResult(False, self.name, error="RMSD 分析需要 trajectory_file")
        u = self._load_universe(structure_file, topology_file, trajectory_file)
        rcalc = rms.RMSD(u.select_atoms(f"backbone and chainID {binder_chain}"))
        rcalc.run()
        rmsd_data = pd.DataFrame(rcalc.results.rmsd, columns=["frame", "time", "rmsd"])
        out_file = output_path / "rmsd.csv"
        rmsd_data.to_csv(out_file, index=False)
        return ToolResult(True, self.name, output={"mean_rmsd": float(rmsd_data["rmsd"].mean()), "max_rmsd": float(rmsd_data["rmsd"].max())}, output_files=[str(out_file)])

    def _identify_interface_residues(self, structure_file, binder_chain, target_chain, output_path, cutoff, **kwargs):
        import json

        u = self._load_universe(structure_file)
        binder_sel = u.select_atoms(f"chainID {binder_chain} and around {cutoff} chainID {target_chain}")
        target_sel = u.select_atoms(f"chainID {target_chain} and around {cutoff} chainID {binder_chain}")
        binder_res = list({f"{r.resname}{r.resid}" for r in binder_sel.residues})
        target_res = list({f"{r.resname}{r.resid}" for r in target_sel.residues})
        result = {
            "binder_interface": binder_res,
            "target_interface": target_res,
            "binder_interface_count": len(binder_res),
            "target_interface_count": len(target_res),
        }
        out_file = output_path / "interface_residues.json"
        out_file.write_text(json.dumps(result, indent=2))
        return ToolResult(True, self.name, output=result, output_files=[str(out_file)])

    def _shape_complementarity_proxy(self, structure_file, binder_chain, target_chain, output_path, cutoff, **kwargs):
        import json

        u = self._load_universe(structure_file)
        binder = u.select_atoms(f"chainID {binder_chain}")
        target = u.select_atoms(f"chainID {target_chain}")
        dist_mat = distances.distance_array(binder.positions, target.positions)
        n_close = int((dist_mat < cutoff).sum())
        n_very_close = int((dist_mat < 3.5).sum())
        result = {
            "n_contacts_5A": n_close,
            "n_contacts_3.5A": n_very_close,
            "sc_proxy_score": round(n_very_close / max(n_close, 1), 3),
        }
        out_file = output_path / "shape_complementarity_proxy.json"
        out_file.write_text(json.dumps(result, indent=2))
        return ToolResult(True, self.name, output=result, output_files=[str(out_file)])

    def _full_report(self, structure_file, binder_chain, target_chain, output_path, cutoff, **kwargs):
        import json

        reports = {}
        for analysis in ["interface_contacts", "hydrogen_bonds", "interface_residues", "shape_complementarity_proxy"]:
            res = self.run(
                analysis_type=analysis,
                structure_file=structure_file,
                binder_chain=binder_chain,
                target_chain=target_chain,
                output_dir=str(output_path),
                cutoff=cutoff,
            )
            reports[analysis] = res.output if res.success else {"error": res.error}
        out_file = output_path / "full_report.json"
        out_file.write_text(json.dumps(reports, indent=2))
        return ToolResult(True, self.name, output=reports, output_files=[str(out_file)])

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "analysis_type": {
                        "type": "string",
                        "enum": [
                            "interface_contacts",
                            "hydrogen_bonds",
                            "rmsd",
                            "interface_residues",
                            "shape_complementarity_proxy",
                            "full_report",
                        ],
                    },
                    "structure_file": {"type": "string", "description": "PDB 文件路径"},
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

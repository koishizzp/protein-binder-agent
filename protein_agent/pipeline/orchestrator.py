from pathlib import Path

import pandas as pd
from loguru import logger

from tools import BindCraftTool, ComplexaTool, MDAnalysisTool


class PipelineOrchestrator:
    def __init__(self, bindcraft: BindCraftTool, complexa: ComplexaTool, mda: MDAnalysisTool):
        self.bindcraft = bindcraft
        self.complexa = complexa
        self.mda = mda

    def full_design_and_analysis_pipeline(
        self,
        target_pdb: str,
        target_chain: str = "B",
        run_name: str = "full_pipeline",
        use_complexa: bool = True,
        use_bindcraft: bool = True,
        hotspot: str | None = None,
        binder_length: int = 80,
        num_designs: int = 5,
    ) -> dict:
        results = {"target_analysis": None, "designs": [], "ranking": []}
        logger.info("Step 1: 靶点分析")
        target_analysis = self.mda.run(
            analysis_type="interface_residues",
            structure_file=target_pdb,
            binder_chain=target_chain,
            target_chain=target_chain,
        )
        results["target_analysis"] = target_analysis.output

        generated_pdbs: list[tuple[str, str]] = []
        if use_complexa:
            logger.info("Step 2a: Proteina-Complexa 生成")
            task = Path(target_pdb).stem
            cres = self.complexa.run(task_name=task, run_name=f"{run_name}_complexa")
            if cres.success:
                generated_pdbs.extend((f, "complexa") for f in cres.output_files if f.endswith(".pdb"))

        if use_bindcraft:
            logger.info("Step 2b: BindCraft 生成")
            bres = self.bindcraft.run(
                target_pdb=target_pdb,
                target_hotspot=hotspot,
                binder_length=binder_length,
                num_designs=num_designs,
                run_name=f"{run_name}_bindcraft",
            )
            if bres.success:
                generated_pdbs.extend((f, "bindcraft") for f in bres.output_files if f.endswith(".pdb"))

        logger.info(f"Step 3: 分析 {len(generated_pdbs)} 个生成结构")
        scored = []
        for pdb_file, source in generated_pdbs:
            r = self.mda.run(
                analysis_type="full_report",
                structure_file=pdb_file,
                binder_chain="A",
                target_chain=target_chain,
                output_dir=f"data/analysis/{run_name}/{Path(pdb_file).stem}",
            )
            if r.success and isinstance(r.output, dict):
                c = r.output.get("interface_contacts", {})
                h = r.output.get("hydrogen_bonds", {})
                s = r.output.get("shape_complementarity_proxy", {})
                score = c.get("n_contacts", 0) * 0.4 + h.get("n_interface_hbonds", 0) * 0.4 + s.get("sc_proxy_score", 0) * 100 * 0.2
                scored.append(
                    {
                        "pdb": pdb_file,
                        "source": source,
                        "score": round(score, 2),
                        "n_contacts": c.get("n_contacts", 0),
                        "n_hbonds": h.get("n_interface_hbonds", 0),
                        "sc_proxy": s.get("sc_proxy_score", 0),
                    }
                )

        scored.sort(key=lambda x: x["score"], reverse=True)
        results["designs"] = scored
        results["ranking"] = scored[:5]
        if scored:
            df = pd.DataFrame(scored)
            out_csv = f"data/results/{run_name}_ranking.csv"
            Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(out_csv, index=False)
            logger.info(f"结果已保存至 {out_csv}")
        return results

from __future__ import annotations

from pathlib import Path
from typing import Any

from protein_agent.config.settings import Settings, get_settings
from protein_agent.pipeline.orchestrator import PipelineOrchestrator
from protein_agent.tools import structure_tool
from protein_agent.tools import BindCraftTool, ComplexaTool, MDAnalysisTool, ToolResult


class ProteinBinderService:
    SUPPORTED_MODULES = ["status", "mdanalysis", "bindcraft", "proteina-complexa", "full_pipeline"]

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        bindcraft_tool: BindCraftTool | None = None,
        complexa_tool: ComplexaTool | None = None,
        mda_tool: MDAnalysisTool | None = None,
        orchestrator: PipelineOrchestrator | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.bindcraft = bindcraft_tool or BindCraftTool(
            self.settings.bindcraft_dir,
            python_executable=self.settings.bindcraft_python_path,
            settings_dir=self.settings.bindcraft_settings_dir,
            filters_file=self.settings.bindcraft_filters_file,
            advanced_settings_file=self.settings.bindcraft_advanced_file,
            timeout_seconds=self.settings.bindcraft_timeout_seconds,
        )
        self.complexa = complexa_tool or ComplexaTool(
            self.settings.complexa_dir,
            python_executable=self.settings.complexa_venv_python,
            cli_path=self.settings.complexa_cli,
            config_dir=self.settings.complexa_config_dir,
            default_overrides=self.settings.complexa_checkpoint_overrides(),
            timeout_seconds=self.settings.complexa_timeout_seconds,
        )
        self.mda = mda_tool or MDAnalysisTool()
        self.orchestrator = orchestrator or PipelineOrchestrator(
            bindcraft=self.bindcraft,
            complexa=self.complexa,
            mda=self.mda,
            result_dir=self.settings.result_dir,
            analysis_dir=self.settings.analysis_dir,
            converted_structures_dir=self.settings.converted_structures_dir,
            biopython_python=self.settings.biopython_python,
        )

    def available_modules(self) -> list[str]:
        return list(self.SUPPORTED_MODULES)

    def available_workflows(self) -> list[str]:
        return sorted(self.settings.workflow_profiles.keys())

    def tool_status(self) -> dict[str, Any]:
        bindcraft_root = Path(self.settings.bindcraft_dir) if self.settings.bindcraft_dir else None
        complexa_root = Path(self.settings.complexa_dir) if self.settings.complexa_dir else None
        biopython_python = Path(self.settings.biopython_python) if self.settings.biopython_python else None
        return {
            "module": "status",
            "workflows": self.settings.workflow_profiles,
            "directories": {
                "data_dir": self.settings.data_dir,
                "result_dir": self.settings.result_dir,
                "analysis_dir": self.settings.analysis_dir,
                "upload_dir": self.settings.upload_dir,
                "converted_structures_dir": self.settings.converted_structures_dir,
            },
            "tools": {
                "bindcraft": {
                    "configured": bool(bindcraft_root),
                    "root": self.settings.bindcraft_dir,
                    "python": self.settings.bindcraft_python_path,
                    "entrypoint_exists": bool(bindcraft_root and (bindcraft_root / "bindcraft.py").exists()),
                },
                "proteina-complexa": {
                    "configured": bool(complexa_root),
                    "root": self.settings.complexa_dir,
                    "cli": self.settings.complexa_cli,
                    "python": self.settings.complexa_venv_python,
                    "config_dir": self.settings.complexa_config_dir,
                    "checkpoint_overrides": self.settings.complexa_checkpoint_overrides(),
                    "default_pipeline": self.settings.complexa_default_pipeline,
                },
                "mdanalysis": {
                    "configured": True,
                    "default_analysis": self.settings.mdanalysis_default_analysis,
                    "default_cutoff": self.settings.mdanalysis_default_cutoff,
                },
                "biopython_converter": {
                    "configured": bool(self.settings.biopython_python),
                    "python": self.settings.biopython_python,
                    "python_exists": bool(biopython_python and biopython_python.exists()),
                },
            },
        }

    def _ensure_pdb_structure(
        self,
        structure_file: str,
        *,
        purpose: str,
        output_name: str | None = None,
    ) -> dict[str, Any]:
        target_dir = Path(self.settings.converted_structures_dir) / purpose
        return structure_tool.ensure_pdb_structure(
            structure_file,
            output_dir=str(target_dir),
            output_name=output_name,
            biopython_python=self.settings.biopython_python,
        )

    def _tool_response(self, module: str, request: dict[str, Any], result: ToolResult) -> dict[str, Any]:
        return {
            "module": module,
            "request": request,
            "success": result.success,
            "error": result.error,
            "output": result.output,
            "metadata": result.metadata,
            "output_files": result.output_files,
            "command": result.command,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    def status(self) -> dict[str, Any]:
        return self.tool_status()

    def analyze_structure(
        self,
        structure_file: str,
        *,
        analysis_type: str | None = None,
        binder_chain: str | None = None,
        target_chain: str | None = None,
        output_dir: str | None = None,
        cutoff: float | None = None,
        topology_file: str | None = None,
        trajectory_file: str | None = None,
    ) -> dict[str, Any]:
        resolved_analysis = analysis_type or self.settings.mdanalysis_default_analysis
        normalized = self._ensure_pdb_structure(
            structure_file,
            purpose="analysis",
            output_name=Path(structure_file).stem,
        )
        result = self.mda.run(
            resolved_analysis,
            normalized["resolved_path"],
            topology_file=topology_file,
            trajectory_file=trajectory_file,
            binder_chain=binder_chain or self.settings.default_binder_chain,
            target_chain=target_chain or self.settings.default_target_chain,
            output_dir=output_dir or self.settings.analysis_dir,
            cutoff=cutoff or self.settings.mdanalysis_default_cutoff,
        )
        return self._tool_response(
            "mdanalysis",
            {
                "analysis_type": resolved_analysis,
                "input_structure_file": structure_file,
                "structure_file": normalized["resolved_path"],
                "binder_chain": binder_chain or self.settings.default_binder_chain,
                "target_chain": target_chain or self.settings.default_target_chain,
                "cutoff": cutoff or self.settings.mdanalysis_default_cutoff,
                "structure_conversion": normalized,
            },
            result,
        )

    def run_bindcraft(
        self,
        target_pdb: str,
        *,
        target_hotspot: str | None = None,
        target_chain: str | None = None,
        binder_length: int | None = None,
        num_designs: int | None = None,
        run_name: str = "bindcraft_run",
        output_dir: str | None = None,
    ) -> dict[str, Any]:
        normalized = self._ensure_pdb_structure(
            target_pdb,
            purpose=f"bindcraft/{run_name}",
            output_name=f"{Path(target_pdb).stem}_target",
        )
        result = self.bindcraft.run(
            normalized["resolved_path"],
            target_hotspot=target_hotspot,
            target_chains=target_chain or self.settings.default_target_chain,
            binder_length=binder_length or self.settings.bindcraft_default_binder_length,
            num_designs=num_designs or self.settings.bindcraft_default_num_designs,
            run_name=run_name,
            output_dir=output_dir,
        )
        return self._tool_response(
            "bindcraft",
            {
                "input_structure_file": target_pdb,
                "target_pdb": normalized["resolved_path"],
                "target_hotspot": target_hotspot,
                "target_chain": target_chain or self.settings.default_target_chain,
                "binder_length": binder_length or self.settings.bindcraft_default_binder_length,
                "num_designs": num_designs or self.settings.bindcraft_default_num_designs,
                "run_name": run_name,
                "structure_conversion": normalized,
            },
            result,
        )

    def run_complexa(
        self,
        task_name: str,
        *,
        pipeline: str | None = None,
        run_name: str = "complexa_run",
        gen_njobs: int | None = None,
        eval_njobs: int | None = None,
        extra_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = self.complexa.run(
            task_name,
            pipeline=pipeline or self.settings.complexa_default_pipeline,
            run_name=run_name,
            gen_njobs=gen_njobs or self.settings.complexa_gen_njobs,
            eval_njobs=eval_njobs or self.settings.complexa_eval_njobs,
            extra_overrides=extra_overrides,
            validate_first=self.settings.complexa_validate_before_run,
        )
        return self._tool_response(
            "proteina-complexa",
            {
                "task_name": task_name,
                "pipeline": pipeline or self.settings.complexa_default_pipeline,
                "run_name": run_name,
                "gen_njobs": gen_njobs or self.settings.complexa_gen_njobs,
                "eval_njobs": eval_njobs or self.settings.complexa_eval_njobs,
            },
            result,
        )

    def run_pipeline(
        self,
        target_pdb: str,
        *,
        workflow: str | None = None,
        hotspot: str | None = None,
        binder_length: int | None = None,
        num_designs: int | None = None,
        run_name: str = "pipeline_run",
        target_chain: str | None = None,
        binder_chain: str | None = None,
        complexa_task_name: str | None = None,
        use_complexa: bool | None = None,
        use_bindcraft: bool | None = None,
    ) -> dict[str, Any]:
        normalized = self._ensure_pdb_structure(
            target_pdb,
            purpose=f"pipeline/{run_name}",
            output_name=f"{Path(target_pdb).stem}_target",
        )
        result = self.orchestrator.full_design_and_analysis_pipeline(
            target_pdb=normalized["resolved_path"],
            workflow=workflow or self.settings.default_workflow,
            hotspot=hotspot,
            binder_length=binder_length or self.settings.bindcraft_default_binder_length,
            num_designs=num_designs or self.settings.bindcraft_default_num_designs,
            run_name=run_name,
            target_chain=target_chain or self.settings.default_target_chain,
            binder_chain=binder_chain or self.settings.default_binder_chain,
            complexa_task_name=complexa_task_name,
            use_complexa=use_complexa,
            use_bindcraft=use_bindcraft,
            complexa_default_pipeline=self.settings.complexa_default_pipeline,
            complexa_gen_njobs=self.settings.complexa_gen_njobs,
            complexa_eval_njobs=self.settings.complexa_eval_njobs,
        )
        request = result.get("request") if isinstance(result.get("request"), dict) else {}
        request["input_structure_file"] = target_pdb
        request["target_pdb"] = normalized["resolved_path"]
        request["structure_conversion"] = normalized
        result["request"] = request
        return result

    def execute_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        module = str(plan.get("module") or "").strip()
        params = dict(plan.get("params") or {})

        if module == "status":
            return self.status()
        if module == "mdanalysis":
            return self.analyze_structure(
                params["structure_file"],
                analysis_type=params.get("analysis_type"),
                binder_chain=params.get("binder_chain"),
                target_chain=params.get("target_chain"),
                output_dir=params.get("output_dir"),
                cutoff=params.get("cutoff"),
                topology_file=params.get("topology_file"),
                trajectory_file=params.get("trajectory_file"),
            )
        if module == "bindcraft":
            return self.run_bindcraft(
                params["target_pdb"],
                target_hotspot=params.get("target_hotspot"),
                target_chain=params.get("target_chain") or params.get("target_chains"),
                binder_length=params.get("binder_length"),
                num_designs=params.get("num_designs"),
                run_name=str(params.get("run_name") or "bindcraft_run"),
                output_dir=params.get("output_dir"),
            )
        if module == "proteina-complexa":
            return self.run_complexa(
                params["task_name"],
                pipeline=params.get("pipeline"),
                run_name=str(params.get("run_name") or "complexa_run"),
                gen_njobs=params.get("gen_njobs"),
                eval_njobs=params.get("eval_njobs"),
                extra_overrides=params.get("extra_overrides"),
            )
        if module == "full_pipeline":
            return self.run_pipeline(
                params["target_pdb"],
                workflow=params.get("workflow"),
                hotspot=params.get("hotspot"),
                binder_length=params.get("binder_length"),
                num_designs=params.get("num_designs"),
                run_name=str(params.get("run_name") or "pipeline_run"),
                target_chain=params.get("target_chain"),
                binder_chain=params.get("binder_chain"),
                complexa_task_name=params.get("complexa_task_name"),
                use_complexa=params.get("use_complexa"),
                use_bindcraft=params.get("use_bindcraft"),
            )
        raise ValueError(f"Unsupported module: {module}")

    def format_execution_reply(self, result: dict[str, Any]) -> str:
        module = str(result.get("module") or "")
        if module == "status":
            bindcraft_ready = result["tools"]["bindcraft"]["entrypoint_exists"]
            complexa_ready = result["tools"]["proteina-complexa"]["configured"]
            return (
                f"当前可用 workflow: {', '.join(self.available_workflows())}。\n"
                f"BindCraft 已配置: {'是' if bindcraft_ready else '否'}。\n"
                f"Proteina-Complexa 已配置: {'是' if complexa_ready else '否'}。\n"
                f"结果目录: {self.settings.result_dir}"
            )

        if module == "mdanalysis":
            if not result.get("success"):
                return f"MDAnalysis 执行失败: {result.get('error')}"
            payload = result.get("output") or {}
            if isinstance(payload, dict) and "n_contacts" in payload:
                return (
                    f"结构分析完成。界面接触数 {payload.get('n_contacts')}，"
                    f"binder 界面残基 {payload.get('binder_interface_residues')}，"
                    f"target 界面残基 {payload.get('target_interface_residues')}。"
                )
            return f"结构分析完成，输出文件数 {len(result.get('output_files') or [])}。"

        if module in {"bindcraft", "proteina-complexa"}:
            if not result.get("success"):
                return f"{module} 执行失败: {result.get('error')}"
            n_files = len(result.get("output_files") or [])
            return f"{module} 执行完成，发现 {n_files} 个输出文件。"

        if module == "full_pipeline":
            ranking = result.get("ranking") if isinstance(result.get("ranking"), list) else []
            if not ranking:
                warning_text = "; ".join(result.get("warnings") or []) if isinstance(result.get("warnings"), list) else ""
                return f"完整流程执行完成，但没有得到可排名的候选。{warning_text}".strip()
            best = ranking[0]
            pdb_name = Path(str(best.get("pdb") or "")).name or "unknown"
            return (
                f"完整流程执行完成，最佳候选为 {pdb_name}，"
                f"score={best.get('score')}，contacts={best.get('n_contacts')}，"
                f"hbonds={best.get('n_hbonds')}，source={best.get('source')}。"
            )

        return "执行完成。"

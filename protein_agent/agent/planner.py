from __future__ import annotations

import json
import logging
from pathlib import Path
import re
from typing import Any

try:
    from openai import OpenAI
except Exception:  # noqa: BLE001
    OpenAI = None

from protein_agent.agent.prompts import PLANNER_SYSTEM_PROMPT
from protein_agent.config.settings import Settings

LOGGER = logging.getLogger(__name__)

STRUCTURE_PATH_PATTERN = re.compile(
    r"""["']?((?:[A-Za-z]:\\|/|\.{1,2}[\\/])?[^\s"'`]+?\.(?:pdb|cif|mmcif|ent))["']?""",
    re.IGNORECASE,
)
HOTSPOT_PATTERN = re.compile(
    r"""(?:hotspot|hotspots|热点)\s*[:=]?\s*([A-Za-z0-9,\- ]+?)(?=\s+(?:run_name|run|workflow|length|num[_ ]?designs|designs)\b|$)""",
    re.IGNORECASE,
)
BINDER_LENGTH_PATTERN = re.compile(r"""(?:binder\s*length|长度|length)\s*[:=]?\s*(\d{1,4})""", re.IGNORECASE)
NUM_DESIGNS_PATTERN = re.compile(r"""(?:num[_ ]?designs|designs|数量|设计数|top)\s*[:=]?\s*(\d{1,4})""", re.IGNORECASE)
TASK_NAME_PATTERN = re.compile(r"""(?:task_name|task|任务名)\s*[:=]?\s*([^\s,;]+)""", re.IGNORECASE)
RUN_NAME_PATTERN = re.compile(r"""(?:run_name|run|运行名)\s*[:=]?\s*([^\s,;]+)""", re.IGNORECASE)
TARGET_CHAIN_PATTERN = re.compile(r"""(?:target\s*chain|目标链)\s*[:=]?\s*([A-Za-z0-9])""", re.IGNORECASE)
BINDER_CHAIN_PATTERN = re.compile(r"""(?:binder\s*chain|binder链)\s*[:=]?\s*([A-Za-z0-9])""", re.IGNORECASE)

ANALYSIS_KEYWORDS = {
    "structure_summary": ("summary", "structure summary", "概览", "结构概览", "总结"),
    "interface_contacts": ("contacts", "contact", "界面接触"),
    "hydrogen_bonds": ("hbonds", "hydrogen bond", "氢键"),
    "rmsd": ("rmsd",),
    "interface_residues": ("interface residues", "界面残基"),
    "shape_complementarity_proxy": ("shape complementarity", "互补", "形状互补"),
    "full_report": ("full report", "report", "报告", "分析"),
}


def _strip_code_fences(text: str) -> str:
    value = text.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?", "", value, count=1).strip()
        if value.endswith("```"):
            value = value[:-3].strip()
    return value


class LLMPlanner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = None
        if settings.openai_api_key:
            if OpenAI is None:
                LOGGER.warning("openai package unavailable; using heuristic binder planner.")
            else:
                self.client = OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)

    def plan(
        self,
        message: str,
        available_modules: list[str] | None = None,
        previous_request: dict[str, Any] | None = None,
        preferred_workflow: str | None = None,
    ) -> dict[str, Any]:
        modules = available_modules or ["status", "mdanalysis", "bindcraft", "proteina-complexa", "full_pipeline"]
        fallback = self._fallback_plan(message, modules, previous_request or {}, preferred_workflow)
        if not self.client:
            return fallback

        payload = {
            "task": message,
            "available_modules": modules,
            "previous_request": previous_request or {},
            "preferred_workflow": preferred_workflow,
        }
        try:
            response = self.client.responses.create(
                model=self.settings.llm_model,
                input=[
                    {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
            )
            raw = _strip_code_fences(response.output_text or "")
            decoded = json.loads(raw)
            return self._sanitize_plan(decoded, fallback, modules)
        except Exception:  # noqa: BLE001
            LOGGER.exception("LLM planner failed; using fallback plan.")
            return fallback

    def _extract_structure_path(self, message: str, previous_request: dict[str, Any]) -> str | None:
        match = STRUCTURE_PATH_PATTERN.search(message)
        if match:
            return match.group(1).strip()
        for key in ("target_pdb", "structure_file"):
            value = previous_request.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _extract_analysis_type(self, message: str, default: str) -> str:
        lowered = message.lower()
        for analysis_type, keywords in ANALYSIS_KEYWORDS.items():
            if any(keyword in lowered for keyword in keywords):
                return analysis_type
        return default

    def _infer_workflow(self, message: str, preferred_workflow: str | None) -> str:
        lowered = message.lower()
        if preferred_workflow:
            return preferred_workflow
        if "complexa only" in lowered or "只用complexa" in lowered:
            return "complexa_only"
        if "bindcraft only" in lowered or "只用bindcraft" in lowered:
            return "bindcraft_only"
        return self.settings.default_workflow

    def _fallback_plan(
        self,
        message: str,
        available_modules: list[str],
        previous_request: dict[str, Any],
        preferred_workflow: str | None,
    ) -> dict[str, Any]:
        lowered = message.lower()
        structure_path = self._extract_structure_path(message, previous_request)
        task_match = TASK_NAME_PATTERN.search(message)
        run_match = RUN_NAME_PATTERN.search(message)
        hotspot_match = HOTSPOT_PATTERN.search(message)
        binder_length_match = BINDER_LENGTH_PATTERN.search(message)
        num_designs_match = NUM_DESIGNS_PATTERN.search(message)
        target_chain_match = TARGET_CHAIN_PATTERN.search(message)
        binder_chain_match = BINDER_CHAIN_PATTERN.search(message)

        task_name = (
            task_match.group(1).strip()
            if task_match
            else (Path(structure_path).stem if structure_path else str(previous_request.get("complexa_task_name") or "").strip() or None)
        )
        run_name = run_match.group(1).strip() if run_match else None
        hotspot = hotspot_match.group(1).strip() if hotspot_match else previous_request.get("hotspot")
        binder_length = (
            int(binder_length_match.group(1))
            if binder_length_match
            else int(previous_request.get("binder_length") or self.settings.bindcraft_default_binder_length)
        )
        num_designs = (
            int(num_designs_match.group(1))
            if num_designs_match
            else int(previous_request.get("num_designs") or self.settings.bindcraft_default_num_designs)
        )
        target_chain = (
            target_chain_match.group(1).strip()
            if target_chain_match
            else str(previous_request.get("target_chain") or self.settings.default_target_chain)
        )
        binder_chain = (
            binder_chain_match.group(1).strip()
            if binder_chain_match
            else str(previous_request.get("binder_chain") or self.settings.default_binder_chain)
        )

        if any(keyword in lowered for keyword in ("status", "配置", "环境", "setup")):
            return {"action": "execute", "module": "status", "params": {}, "needs_input": False, "question": None}

        if any(keyword in lowered for keyword in ("mdanalysis", "氢键", "rmsd", "接触", "分析", "report")):
            plan = {
                "action": "execute",
                "module": "mdanalysis",
                "params": {
                    "analysis_type": self._extract_analysis_type(message, self.settings.mdanalysis_default_analysis),
                    "structure_file": structure_path,
                    "binder_chain": binder_chain,
                    "target_chain": target_chain,
                    "cutoff": self.settings.mdanalysis_default_cutoff,
                },
                "needs_input": structure_path is None,
                "question": None,
            }
            if structure_path is None:
                plan["action"] = "clarify"
                plan["question"] = "请提供要分析的结构文件路径，例如 /path/to/complex.pdb"
            return plan

        if "complexa" in lowered or "proteina-complexa" in lowered:
            plan = {
                "action": "execute",
                "module": "proteina-complexa",
                "params": {
                    "task_name": task_name,
                    "pipeline": self.settings.complexa_default_pipeline,
                    "run_name": run_name or "complexa_run",
                    "gen_njobs": self.settings.complexa_gen_njobs,
                    "eval_njobs": self.settings.complexa_eval_njobs,
                },
                "needs_input": task_name is None,
                "question": None,
            }
            if task_name is None:
                plan["action"] = "clarify"
                plan["question"] = "请提供 Proteina-Complexa 的 task_name，或提供能推断 task_name 的目标结构路径。"
            return plan

        if "bindcraft" in lowered:
            plan = {
                "action": "execute",
                "module": "bindcraft",
                "params": {
                    "target_pdb": structure_path,
                    "target_hotspot": hotspot,
                    "target_chains": target_chain,
                    "binder_length": binder_length,
                    "num_designs": num_designs,
                    "run_name": run_name or "bindcraft_run",
                },
                "needs_input": structure_path is None,
                "question": None,
            }
            if structure_path is None:
                plan["action"] = "clarify"
                plan["question"] = "请提供 BindCraft 需要的目标结构文件路径，例如 /path/to/target.pdb"
            return plan

        workflow = self._infer_workflow(message, preferred_workflow)
        plan = {
            "action": "execute",
            "module": "full_pipeline",
            "params": {
                "target_pdb": structure_path,
                "workflow": workflow,
                "hotspot": hotspot,
                "binder_length": binder_length,
                "num_designs": num_designs,
                "run_name": run_name or "pipeline_run",
                "target_chain": target_chain,
                "binder_chain": binder_chain,
                "complexa_task_name": task_name,
            },
            "needs_input": structure_path is None,
            "question": None,
        }
        if structure_path is None:
            plan["action"] = "clarify"
            plan["question"] = "请提供目标结构文件路径，我才能调度 BindCraft / MDAnalysis / Proteina-Complexa 流程。"
        return plan

    def _sanitize_plan(
        self,
        decoded: dict[str, Any],
        fallback: dict[str, Any],
        available_modules: list[str],
    ) -> dict[str, Any]:
        if not isinstance(decoded, dict):
            return fallback

        module = str(decoded.get("module") or fallback["module"]).strip()
        if module not in available_modules:
            module = fallback["module"]
        params = decoded.get("params") if isinstance(decoded.get("params"), dict) else dict(fallback["params"])
        action = str(decoded.get("action") or fallback["action"]).strip().lower()
        if action not in {"execute", "clarify"}:
            action = fallback["action"]
        needs_input = bool(decoded.get("needs_input"))
        question = decoded.get("question")
        if not isinstance(question, str) or not question.strip():
            question = fallback.get("question")

        if module in {"mdanalysis", "bindcraft", "full_pipeline"}:
            target_key = "structure_file" if module == "mdanalysis" else "target_pdb"
            if not str(params.get(target_key) or "").strip():
                params[target_key] = fallback["params"].get(target_key)
            if not str(params.get(target_key) or "").strip():
                action = "clarify"
                needs_input = True
                question = question or fallback.get("question")

        if module == "proteina-complexa":
            task_name = str(params.get("task_name") or "").strip()
            if not task_name:
                params["task_name"] = fallback["params"].get("task_name")
            if not str(params.get("task_name") or "").strip():
                action = "clarify"
                needs_input = True
                question = question or fallback.get("question")

        return {
            "action": action,
            "module": module,
            "params": params,
            "needs_input": needs_input,
            "question": question,
        }

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

try:
    from openai import OpenAI
except Exception:  # noqa: BLE001
    OpenAI = None

from protein_agent.agent.chat import best_design_from_result
from protein_agent.agent.prompts import REASONER_SYSTEM_PROMPT
from protein_agent.config.settings import Settings

LOGGER = logging.getLogger(__name__)


class ResultReasoner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = None
        if settings.openai_api_key:
            if OpenAI is None:
                LOGGER.warning("openai package unavailable; using fallback binder reasoner.")
            else:
                self.client = OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)

    def reply(
        self,
        message: str,
        latest_result: dict[str, Any] | None = None,
        conversation: list[dict[str, str]] | None = None,
        current_mode: str = "full_pipeline",
        previous_best_design: str | None = None,
    ) -> str:
        fallback = self._fallback_reply(message, latest_result, current_mode, previous_best_design)
        if not self.client:
            return fallback

        payload = {
            "message": message,
            "current_mode": current_mode,
            "previous_best_design": previous_best_design,
            "conversation": conversation or [],
            "latest_result": latest_result or {},
        }
        try:
            response = self.client.responses.create(
                model=self.settings.llm_model,
                input=[
                    {"role": "system", "content": REASONER_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
            )
            text = (response.output_text or "").strip()
            return text or fallback
        except Exception:  # noqa: BLE001
            LOGGER.exception("Reasoning request failed; using fallback binder reasoner.")
            return fallback

    def _fallback_reply(
        self,
        message: str,
        latest_result: dict[str, Any] | None,
        current_mode: str,
        previous_best_design: str | None,
    ) -> str:
        if not latest_result:
            return "当前没有可解释的结果。请先运行一次设计或分析，再继续追问。"

        module = str(latest_result.get("module") or current_mode or "full_pipeline")
        if module == "full_pipeline":
            ranking = latest_result.get("ranking") if isinstance(latest_result.get("ranking"), list) else []
            if not ranking:
                return "这次完整流程没有产出可排名候选。更可能的原因是上游设计工具没有生成复合物，或生成结果未通过后续 MDAnalysis 打分。"
            best = ranking[0]
            lines = [
                f"当前最优候选是 {Path(str(best.get('pdb') or '')).name}，source={best.get('source')}。",
                f"它的综合分数是 {best.get('score')}，接触数 {best.get('n_contacts')}，氢键数 {best.get('n_hbonds')}，形状互补代理分数 {best.get('sc_proxy')}。",
            ]
            if len(ranking) > 1:
                second = ranking[1]
                lines.append(
                    f"与第二名相比，它在当前排序里更靠前。第二名是 {Path(str(second.get('pdb') or '')).name}，score={second.get('score')}。"
                )
            if previous_best_design and str(best.get("pdb") or "") != previous_best_design:
                lines.append("推断：本轮最优候选已经不同于上一轮上下文里的最佳结果，说明筛选条件或候选集合发生了有效变化。")
            lines.append("如果你需要更稳的结论，下一步应该检查对应 full_report.json，并对前几名做更细的界面比较。")
            return "\n".join(lines)

        if module == "mdanalysis":
            output = latest_result.get("output") if isinstance(latest_result.get("output"), dict) else {}
            if "n_contacts" in output:
                return (
                    f"这次 MDAnalysis 结果重点是界面接触数 {output.get('n_contacts')}。"
                    f" binder 界面残基 {output.get('binder_interface_residues')}，"
                    f" target 界面残基 {output.get('target_interface_residues')}。"
                )
            return "这次 MDAnalysis 已完成，但结果更适合直接查看 JSON 报告文件里的详细字段。"

        if module in {"bindcraft", "proteina-complexa"}:
            success = bool(latest_result.get("success"))
            n_files = len(latest_result.get("output_files") or [])
            if not success:
                return f"{module} 这次执行失败。直接原因是：{latest_result.get('error')}"
            return f"{module} 本轮执行成功，当前发现 {n_files} 个输出文件。下一步建议把生成的复合物送入 MDAnalysis 或完整流程做统一评分。"

        best = best_design_from_result(latest_result)
        if best:
            return f"当前最值得关注的结果是 {best.get('pdb') or best}。如果要更具体解释，请把这次结果对象继续传给我。"
        return "当前结果可以继续解释，但结果对象里缺少统一的 ranking/best_design 结构。"

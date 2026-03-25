from __future__ import annotations

from typing import Any

from protein_agent.agent.chat import (
    best_design_from_result,
    build_reasoning_context,
    extras_from_latest_result,
    is_reasoning_query,
    normalize_chat_context,
)
from protein_agent.agent.memory import AgentMemory
from protein_agent.agent.planner import LLMPlanner
from protein_agent.agent.reasoner import ResultReasoner
from protein_agent.agent.service import ProteinBinderService
from protein_agent.config.settings import Settings, get_settings


class ProteinBinderAgent:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        planner: LLMPlanner | None = None,
        service: ProteinBinderService | None = None,
        reasoner: ResultReasoner | None = None,
        memory: AgentMemory | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.planner = planner or LLMPlanner(self.settings)
        self.service = service or ProteinBinderService(self.settings)
        self.reasoner = reasoner or ResultReasoner(self.settings)
        self.memory = memory or AgentMemory()

    def run(
        self,
        user_request: str,
        *,
        latest_result: dict[str, Any] | None = None,
        reasoning_context: dict[str, Any] | None = None,
        preferred_workflow: str | None = None,
    ) -> dict[str, Any]:
        self.memory.add_user_message(user_request)
        latest_result, previous_best_design = normalize_chat_context(
            latest_result,
            None,
            reasoning_context,
        )

        if is_reasoning_query(user_request) and latest_result:
            reply = self.reasoner.reply(
                message=user_request,
                latest_result=latest_result,
                conversation=self.memory.get_messages(),
                current_mode=str(reasoning_context.get("current_mode")) if isinstance(reasoning_context, dict) else "full_pipeline",
                previous_best_design=previous_best_design,
            )
            self.memory.add_assistant_message(reply)
            return {
                "chat_mode": "reasoning",
                "reply": reply,
                "reasoning_context": build_reasoning_context(
                    "reasoning",
                    latest_result,
                    previous_best_design,
                    current_mode=str(reasoning_context.get("current_mode")) if isinstance(reasoning_context, dict) else "full_pipeline",
                ),
                **extras_from_latest_result(latest_result),
            }

        previous_request = latest_result.get("request") if isinstance(latest_result.get("request"), dict) else {}
        plan = self.planner.plan(
            user_request,
            self.service.available_modules(),
            previous_request=previous_request,
            preferred_workflow=preferred_workflow,
        )

        if plan.get("needs_input"):
            reply = str(plan.get("question") or "请补充执行所需的参数。")
            self.memory.add_assistant_message(reply)
            return {
                "chat_mode": "execution",
                "reply": reply,
                "operation_plan": plan,
                "reasoning_context": build_reasoning_context("execution", latest_result, previous_best_design),
            }

        result = self.service.execute_plan(plan)
        reply = self.service.format_execution_reply(result)
        self.memory.add_operation_record(
            str(plan.get("module") or ""),
            inputs=dict(plan.get("params") or {}),
            success=bool(result.get("success", True)),
            summary=reply,
            output_files=list(result.get("output_files") or []),
        )
        self.memory.add_assistant_message(reply)

        current_best = best_design_from_result(result)
        previous_label = str(current_best.get("pdb") or previous_best_design or "")
        return {
            "chat_mode": "execution",
            "reply": reply,
            "operation_plan": plan,
            "operation_result": result,
            "reasoning_context": build_reasoning_context(
                "execution",
                result,
                previous_label,
                current_mode=str(plan.get("module") or "full_pipeline"),
            ),
            **extras_from_latest_result(result),
        }

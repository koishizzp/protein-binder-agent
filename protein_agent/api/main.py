from __future__ import annotations

from functools import lru_cache
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from protein_agent.agent.chat import (
    build_chat_completion,
    build_reasoning_context,
    extras_from_latest_result,
    is_reasoning_query,
    latest_user_content,
    normalize_chat_context,
)
from protein_agent.agent.planner import LLMPlanner
from protein_agent.agent.reasoner import ResultReasoner
from protein_agent.agent.service import ProteinBinderService
from protein_agent.config.settings import get_settings

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)
app = FastAPI(title="Protein Binder Agent", version="2.0.0")


@lru_cache(maxsize=1)
def load_chat_ui() -> str:
    return Path(__file__).with_name("chat_ui.html").read_text(encoding="utf-8")


class BindCraftRequest(BaseModel):
    target_pdb: str
    target_hotspot: str | None = None
    target_chain: str | None = None
    binder_length: int | None = Field(default=None, ge=1, le=2048)
    num_designs: int | None = Field(default=None, ge=1, le=10000)
    run_name: str = "bindcraft_run"
    output_dir: str | None = None


class ComplexaRequest(BaseModel):
    task_name: str
    pipeline: str | None = None
    run_name: str = "complexa_run"
    gen_njobs: int | None = Field(default=None, ge=1, le=256)
    eval_njobs: int | None = Field(default=None, ge=1, le=256)
    extra_overrides: dict[str, Any] | None = None


class MDAnalysisRequest(BaseModel):
    analysis_type: str = "full_report"
    structure_file: str
    binder_chain: str | None = None
    target_chain: str | None = None
    output_dir: str | None = None
    cutoff: float | None = Field(default=None, gt=0)
    topology_file: str | None = None
    trajectory_file: str | None = None


class PipelineRequest(BaseModel):
    target_pdb: str
    workflow: str | None = None
    hotspot: str | None = None
    binder_length: int | None = Field(default=None, ge=1, le=2048)
    num_designs: int | None = Field(default=None, ge=1, le=10000)
    run_name: str = "pipeline_run"
    target_chain: str | None = None
    binder_chain: str | None = None
    complexa_task_name: str | None = None
    use_complexa: bool | None = None
    use_bindcraft: bool | None = None


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatReasoningRequest(BaseModel):
    message: str
    conversation: list[ChatMessage] = Field(default_factory=list)
    latest_result: dict[str, Any] | None = None
    current_mode: str = "full_pipeline"
    previous_best_design: str | None = None


class ChatCompletionRequest(BaseModel):
    model: str | None = None
    messages: list[ChatMessage] = Field(default_factory=list)
    latest_result: dict[str, Any] | None = None
    previous_best_design: str | None = None
    reasoning_context: dict[str, Any] | None = None
    preferred_workflow: str | None = None


def get_service() -> ProteinBinderService:
    return ProteinBinderService(get_settings())


def get_planner() -> LLMPlanner:
    return LLMPlanner(get_settings())


def get_reasoner() -> ResultReasoner:
    return ResultReasoner(get_settings())


def _wrap(handler):
    try:
        return handler()
    except Exception as exc:
        LOGGER.exception("Protein binder API call failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return load_chat_ui()


@app.get("/chat", response_class=HTMLResponse)
def chat_page() -> str:
    return load_chat_ui()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ui/status")
def ui_status() -> dict[str, Any]:
    settings = get_settings()
    service = get_service()
    return {
        "agent": {"status": "ok", "app_name": settings.app_name},
        "llm": {
            "configured": bool(settings.openai_api_key),
            "model": settings.llm_model,
            "base_url_configured": bool(settings.openai_base_url),
        },
        "binder_agent": service.tool_status(),
    }


@app.get("/v1/models")
def list_models() -> dict[str, Any]:
    return {"data": [{"id": "protein-binder-design-agent", "object": "model"}]}


@app.post("/run_bindcraft")
def run_bindcraft(req: BindCraftRequest) -> dict[str, Any]:
    service = get_service()
    return _wrap(
        lambda: service.run_bindcraft(
            req.target_pdb,
            target_hotspot=req.target_hotspot,
            target_chain=req.target_chain,
            binder_length=req.binder_length,
            num_designs=req.num_designs,
            run_name=req.run_name,
            output_dir=req.output_dir,
        )
    )


@app.post("/run_complexa")
def run_complexa(req: ComplexaRequest) -> dict[str, Any]:
    service = get_service()
    return _wrap(
        lambda: service.run_complexa(
            req.task_name,
            pipeline=req.pipeline,
            run_name=req.run_name,
            gen_njobs=req.gen_njobs,
            eval_njobs=req.eval_njobs,
            extra_overrides=req.extra_overrides,
        )
    )


@app.post("/analyze_structure")
def analyze_structure(req: MDAnalysisRequest) -> dict[str, Any]:
    service = get_service()
    return _wrap(
        lambda: service.analyze_structure(
            req.structure_file,
            analysis_type=req.analysis_type,
            binder_chain=req.binder_chain,
            target_chain=req.target_chain,
            output_dir=req.output_dir,
            cutoff=req.cutoff,
            topology_file=req.topology_file,
            trajectory_file=req.trajectory_file,
        )
    )


@app.post("/run_pipeline")
def run_pipeline(req: PipelineRequest) -> dict[str, Any]:
    service = get_service()
    return _wrap(
        lambda: service.run_pipeline(
            req.target_pdb,
            workflow=req.workflow,
            hotspot=req.hotspot,
            binder_length=req.binder_length,
            num_designs=req.num_designs,
            run_name=req.run_name,
            target_chain=req.target_chain,
            binder_chain=req.binder_chain,
            complexa_task_name=req.complexa_task_name,
            use_complexa=req.use_complexa,
            use_bindcraft=req.use_bindcraft,
        )
    )


@app.post("/chat_reasoning")
def chat_reasoning(req: ChatReasoningRequest) -> dict[str, Any]:
    reasoner = get_reasoner()
    return _wrap(
        lambda: {
            "reply": reasoner.reply(
                message=req.message,
                latest_result=req.latest_result,
                conversation=[item.model_dump() for item in req.conversation],
                current_mode=req.current_mode,
                previous_best_design=req.previous_best_design,
            )
        }
    )


@app.post("/v1/chat/completions")
def chat_completions(req: ChatCompletionRequest) -> dict[str, Any]:
    content = latest_user_content([item.model_dump() for item in req.messages])
    latest_result, previous_best_design = normalize_chat_context(
        req.latest_result,
        req.previous_best_design,
        req.reasoning_context,
    )

    if is_reasoning_query(content):
        if latest_result:
            reasoner = get_reasoner()
            current_mode = (
                str(req.reasoning_context.get("current_mode"))
                if isinstance(req.reasoning_context, dict) and req.reasoning_context.get("current_mode")
                else "full_pipeline"
            )
            reply = reasoner.reply(
                message=content,
                latest_result=latest_result,
                conversation=[item.model_dump() for item in req.messages],
                current_mode=current_mode,
                previous_best_design=previous_best_design,
            )
            extra = extras_from_latest_result(latest_result)
            extra["chat_mode"] = "reasoning"
            extra["reasoning_context"] = build_reasoning_context(
                "reasoning",
                latest_result,
                previous_best_design,
                current_mode=current_mode,
            )
            return build_chat_completion(reply, extra=extra)

        return build_chat_completion(
            "请先执行一次设计或分析，再继续追问原因、比较和解释类问题。",
            extra={
                "chat_mode": "reasoning",
                "reasoning_context": build_reasoning_context("reasoning", None, previous_best_design),
            },
        )

    planner = get_planner()
    service = get_service()
    previous_request = latest_result.get("request") if isinstance(latest_result.get("request"), dict) else {}
    plan = planner.plan(
        content,
        service.available_modules(),
        previous_request=previous_request,
        preferred_workflow=req.preferred_workflow,
    )
    module = str(plan.get("module") or "full_pipeline")
    if plan.get("needs_input"):
        return build_chat_completion(
            str(plan.get("question") or "请补充执行所需参数。"),
            extra={
                "chat_mode": "execution",
                "operation_plan": plan,
                "reasoning_context": build_reasoning_context(
                    "execution",
                    latest_result,
                    previous_best_design,
                    current_mode=module,
                ),
            },
        )

    result = _wrap(lambda: service.execute_plan(plan))
    extra = extras_from_latest_result(result)
    extra["chat_mode"] = "execution"
    extra["operation_plan"] = plan
    extra["operation_result"] = result
    extra["reasoning_context"] = build_reasoning_context(
        "execution",
        result,
        previous_best_design,
        current_mode=module,
    )
    return build_chat_completion(service.format_execution_reply(result), extra=extra)

import json
from dataclasses import dataclass


@dataclass
class PlanStep:
    step: int
    tool: str
    action: str
    rationale: str


class Planner:
    """轻量规则规划器，可作为 LLM 规划失败时的兜底。"""

    def create_fallback_plan(self, request: str) -> dict:
        steps = [
            {
                "step": 1,
                "tool": "mdanalysis",
                "action": "分析靶点结构并识别潜在界面残基",
                "rationale": "先定位可结合区域，指导后续设计参数",
            },
            {
                "step": 2,
                "tool": "proteina_complexa",
                "action": "运行 binder pipeline 生成候选",
                "rationale": "适用于全新靶点的高质量 de novo 设计",
            },
            {
                "step": 3,
                "tool": "bindcraft",
                "action": "基于热点位点快速迭代生成候选",
                "rationale": "提供互补候选并提高探索多样性",
            },
            {
                "step": 4,
                "tool": "mdanalysis",
                "action": "对候选进行 full_report 评分并排序",
                "rationale": "基于界面接触/氢键/形状互补指标筛选",
            },
        ]
        return {
            "goal": request,
            "steps": steps,
            "expected_outputs": ["候选PDB", "分析报告JSON", "排名CSV"],
            "estimated_time": "2-6 小时（视 GPU 资源）",
        }

    def to_json(self, plan: dict) -> str:
        return json.dumps(plan, ensure_ascii=False, indent=2)

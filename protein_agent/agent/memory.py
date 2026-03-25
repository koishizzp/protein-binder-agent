import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class ExperimentRecord:
    timestamp: str
    tool_name: str
    inputs: dict
    success: bool
    summary: str
    output_files: list[str]


class AgentMemory:
    def __init__(self, max_messages: int = 50):
        self.messages: list[dict] = []
        self.experiment_log: list[ExperimentRecord] = []
        self.max_messages = max_messages

    def add_user_message(self, content: str):
        self.messages.append({"role": "user", "content": content})

    def add_assistant_message(self, content: str):
        self.messages.append({"role": "assistant", "content": content})

    def add_tool_result(self, tool_name: str, result, inputs: dict | None = None):
        record = ExperimentRecord(
            timestamp=datetime.now().isoformat(),
            tool_name=tool_name,
            inputs=inputs or {},
            success=result.success,
            summary=result.to_llm_summary(),
            output_files=result.output_files,
        )
        self.experiment_log.append(record)

    def get_messages(self) -> list[dict]:
        return self.messages[-self.max_messages :]

    def get_experiment_summary(self) -> str:
        if not self.experiment_log:
            return "无历史实验记录"
        lines = []
        for r in self.experiment_log[-10:]:
            status = "✅" if r.success else "❌"
            lines.append(f"{status} [{r.timestamp[:16]}] {r.tool_name}: {r.summary[:200]}")
        return "\n".join(lines)

    def save(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        data = {
            "messages": self.messages,
            "experiment_log": [vars(r) for r in self.experiment_log],
        }
        Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False))

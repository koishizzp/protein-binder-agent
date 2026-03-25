from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ExperimentRecord:
    timestamp: str
    module: str
    inputs: dict[str, Any]
    success: bool
    summary: str
    output_files: list[str]


class AgentMemory:
    def __init__(self, max_messages: int = 50):
        self.messages: list[dict[str, Any]] = []
        self.experiment_log: list[ExperimentRecord] = []
        self.max_messages = max_messages

    def add_user_message(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})

    def add_assistant_message(self, content: str) -> None:
        self.messages.append({"role": "assistant", "content": content})

    def add_operation_record(
        self,
        module: str,
        *,
        inputs: dict[str, Any] | None = None,
        success: bool = True,
        summary: str = "",
        output_files: list[str] | None = None,
    ) -> None:
        self.experiment_log.append(
            ExperimentRecord(
                timestamp=datetime.now().isoformat(),
                module=module,
                inputs=inputs or {},
                success=success,
                summary=summary,
                output_files=output_files or [],
            )
        )

    def get_messages(self) -> list[dict[str, Any]]:
        return self.messages[-self.max_messages :]

    def get_experiment_summary(self) -> str:
        if not self.experiment_log:
            return "No operations recorded yet."
        lines = []
        for record in self.experiment_log[-10:]:
            status = "ok" if record.success else "failed"
            lines.append(f"{status} [{record.timestamp[:19]}] {record.module}: {record.summary[:200]}")
        return "\n".join(lines)

    def save(self, path: str) -> None:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "messages": self.messages,
            "experiment_log": [
                {
                    "timestamp": item.timestamp,
                    "module": item.module,
                    "inputs": item.inputs,
                    "success": item.success,
                    "summary": item.summary,
                    "output_files": item.output_files,
                }
                for item in self.experiment_log
            ],
        }
        output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

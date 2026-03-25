from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ToolResult:
    success: bool
    tool_name: str
    output: Any = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    output_files: list[str] = field(default_factory=list)
    command: list[str] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_llm_summary(self) -> str:
        if self.success:
            parts = [f"[{self.tool_name}] success"]
            if self.metadata:
                parts.append(f"metadata={self.metadata}")
            if self.output is not None:
                parts.append(f"output={str(self.output)[:2000]}")
            if self.output_files:
                parts.append(f"files={', '.join(self.output_files[:20])}")
            return "\n".join(parts)
        message = f"[{self.tool_name}] failure"
        if self.error:
            message += f"\nerror={self.error}"
        if self.stderr:
            message += f"\nstderr={self.stderr[:1500]}"
        return message


class BaseTool(ABC):
    name: str = "base_tool"
    description: str = "Base tool"

    @abstractmethod
    def run(self, **kwargs: Any) -> ToolResult:
        raise NotImplementedError

    @abstractmethod
    def get_schema(self) -> dict[str, Any]:
        raise NotImplementedError

    def validate_inputs(self, **kwargs: Any) -> bool:
        return True

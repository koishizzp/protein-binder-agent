from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    success: bool
    tool_name: str
    output: Any = None
    error: str | None = None
    metadata: dict = field(default_factory=dict)
    output_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "tool_name": self.tool_name,
            "output": str(self.output) if self.output is not None else None,
            "error": self.error,
            "metadata": self.metadata,
            "output_files": self.output_files,
        }

    def to_llm_summary(self) -> str:
        if self.success:
            return (
                f"[{self.tool_name}] 成功\n"
                f"输出: {str(self.output)[:2000]}\n"
                f"文件: {', '.join(self.output_files) if self.output_files else '无'}"
            )
        return f"[{self.tool_name}] 失败\n错误: {self.error}"


class BaseTool(ABC):
    name: str = "base_tool"
    description: str = "基础工具"

    @abstractmethod
    def run(self, **kwargs) -> ToolResult:
        raise NotImplementedError

    @abstractmethod
    def get_schema(self) -> dict:
        raise NotImplementedError

    def validate_inputs(self, **kwargs) -> bool:
        return True

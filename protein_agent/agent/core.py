import json

import anthropic
from loguru import logger

from .memory import AgentMemory
from .prompts import SYSTEM_PROMPT
from tools import BindCraftTool, ComplexaTool, MDAnalysisTool


class ProteinBinderAgent:
    def __init__(self, config: dict, api_key: str | None = None):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.memory = AgentMemory()
        self.model = config.get("model", "claude-opus-4-5")
        self.max_iterations = config.get("max_iterations", 10)

        self.tools_map = {
            "proteina_complexa": ComplexaTool(
                complexa_dir=config["complexa_dir"],
                venv_python=config["complexa_venv_python"],
                config_dir=config["complexa_config_dir"],
            ),
            "bindcraft": BindCraftTool(bindcraft_dir=config["bindcraft_dir"]),
            "mdanalysis": MDAnalysisTool(),
        }
        self.llm_tools = [t.get_schema() for t in self.tools_map.values()]

    def run(self, user_request: str) -> str:
        logger.info(f"收到请求: {user_request}")
        self.memory.add_user_message(user_request)
        messages = self.memory.get_messages()

        for iteration in range(self.max_iterations):
            logger.info(f"迭代 {iteration + 1}/{self.max_iterations}")

            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=self.llm_tools,
                messages=messages,
            )

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        logger.info(
                            "调用工具: {}，参数: {}",
                            block.name,
                            json.dumps(block.input, ensure_ascii=False)[:300],
                        )
                        result = self._execute_tool(block.name, block.input)
                        logger.info(f"工具结果: {result.to_llm_summary()[:500]}")
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result.to_llm_summary(),
                            }
                        )
                        self.memory.add_tool_result(block.name, result, inputs=block.input)

                messages = self.memory.get_messages()
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})
                self.memory.messages = messages

            elif response.stop_reason == "end_turn":
                final_text = "".join(
                    block.text for block in response.content if hasattr(block, "text")
                )
                self.memory.add_assistant_message(final_text)
                logger.info("Agent 完成任务")
                return final_text

        return "达到最大迭代次数，任务未完成。请检查日志。"

    def _execute_tool(self, tool_name: str, tool_input: dict):
        tool = self.tools_map.get(tool_name)
        if not tool:
            from tools.base import ToolResult

            return ToolResult(success=False, tool_name=tool_name, error=f"未知工具: {tool_name}")
        return tool.run(**tool_input)

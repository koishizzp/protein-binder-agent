from tools.base import ToolResult


def test_tool_result_summary_success():
    r = ToolResult(success=True, tool_name="x", output={"a": 1}, output_files=["f1"])
    assert "成功" in r.to_llm_summary()


def test_tool_result_summary_failure():
    r = ToolResult(success=False, tool_name="x", error="boom")
    assert "失败" in r.to_llm_summary()

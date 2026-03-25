import json
from pathlib import Path

from protein_agent.tools.base import ToolResult
from protein_agent.tools.bindcraft_tool import BindCraftTool
from protein_agent.tools.complexa_tool import ComplexaTool


def test_tool_result_summary_success():
    result = ToolResult(success=True, tool_name="x", output={"a": 1}, output_files=["f1"])
    assert "success" in result.to_llm_summary()


def test_tool_result_summary_failure():
    result = ToolResult(success=False, tool_name="x", error="boom")
    assert "failure" in result.to_llm_summary()


def test_bindcraft_tool_writes_upstream_style_settings(monkeypatch, tmp_path):
    bindcraft_dir = tmp_path / "BindCraft"
    (bindcraft_dir / "settings_filters").mkdir(parents=True)
    (bindcraft_dir / "settings_advanced").mkdir(parents=True)
    (bindcraft_dir / "bindcraft.py").write_text("print('bindcraft')", encoding="utf-8")
    (bindcraft_dir / "settings_filters" / "default_filters.json").write_text("{}", encoding="utf-8")
    (bindcraft_dir / "settings_advanced" / "default_4stage_multimer.json").write_text("{}", encoding="utf-8")
    target_pdb = tmp_path / "target.pdb"
    target_pdb.write_text("HEADER TARGET\n", encoding="utf-8")

    class Completed:
        def __init__(self, returncode=0, stdout="done", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(command, cwd=None, capture_output=True, text=True, timeout=0):
        if command[-1] == "import pyrosetta":
            return Completed()
        settings_path = Path(command[command.index("--settings") + 1])
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
        assert payload["starting_pdb"] == str(target_pdb.resolve())
        assert payload["target_hotspot_residues"] == "A10,A12"
        output_dir = Path(payload["design_path"])
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "best_design.pdb").write_text("MODEL\n", encoding="utf-8")
        return Completed()

    monkeypatch.setattr("protein_agent.tools.bindcraft_tool.subprocess.run", fake_run)

    tool = BindCraftTool(str(bindcraft_dir))
    result = tool.run(str(target_pdb), target_hotspot="A10,A12", run_name="demo")

    assert result.success is True
    assert any(path.endswith(".pdb") for path in result.output_files)


def test_complexa_tool_discovers_nested_pipeline_config(tmp_path):
    complexa_dir = tmp_path / "Proteina-Complexa"
    config_path = complexa_dir / "examples" / "configs" / "search_binder_local_pipeline.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("defaults: []\n", encoding="utf-8")

    tool = ComplexaTool(str(complexa_dir))
    resolved = tool._resolved_pipeline_config("binder")

    assert resolved == config_path


def test_complexa_tool_prefers_working_cli_candidate(monkeypatch, tmp_path):
    complexa_dir = tmp_path / "Proteina-Complexa"
    complexa_dir.mkdir()
    cli_path = complexa_dir / ".venv" / "bin" / "complexa"
    cli_path.parent.mkdir(parents=True)
    cli_path.write_text("", encoding="utf-8")

    class Completed:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(command, cwd=None, capture_output=True, text=True, timeout=0):
        if command[:1] == [str(cli_path)] and command[-1] == "--help":
            return Completed(returncode=0)
        return Completed(returncode=1, stderr="bad candidate")

    monkeypatch.setattr("protein_agent.tools.complexa_tool.subprocess.run", fake_run)

    tool = ComplexaTool(str(complexa_dir))
    assert tool._command_prefix() == [str(cli_path)]


def test_bindcraft_tool_reports_checked_candidates_when_pyrosetta_missing(tmp_path):
    bindcraft_dir = tmp_path / "BindCraft"
    bindcraft_dir.mkdir()
    (bindcraft_dir / "bindcraft.py").write_text("print('bindcraft')", encoding="utf-8")
    target_pdb = tmp_path / "target.pdb"
    target_pdb.write_text("HEADER TARGET\n", encoding="utf-8")

    tool = BindCraftTool(str(bindcraft_dir), python_executable="/custom/python")
    result = tool.run(str(target_pdb))

    assert result.success is False
    assert "Checked candidates:" in (result.error or "")
    assert "/custom/python" in (result.error or "")


def test_complexa_tool_reports_checked_candidates_when_cli_missing(tmp_path):
    complexa_dir = tmp_path / "Proteina-Complexa"
    config_path = complexa_dir / "examples" / "configs" / "search_binder_local_pipeline.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("defaults: []\n", encoding="utf-8")

    tool = ComplexaTool(str(complexa_dir), python_executable="/custom/python", cli_path="/custom/complexa")
    result = tool.run("demo")

    assert result.success is False
    assert "Checked candidates:" in (result.error or "")
    assert "/custom/complexa" in (result.error or "")

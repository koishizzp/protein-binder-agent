from protein_agent.agent.service import ProteinBinderService
from protein_agent.config.settings import Settings
from protein_agent.tools.base import ToolResult


class DummyBindCraftTool:
    def __init__(self):
        self.calls = []

    def run(self, target_pdb, **kwargs):
        self.calls.append({"target_pdb": target_pdb, **kwargs})
        return ToolResult(success=True, tool_name="bindcraft", output={"ok": True}, output_files=["/tmp/out.pdb"])


class DummyComplexaTool:
    def run(self, *args, **kwargs):
        return ToolResult(success=True, tool_name="proteina-complexa", output={"ok": True})


class DummyMDATool:
    def run(self, *args, **kwargs):
        return ToolResult(success=True, tool_name="mdanalysis", output={"n_contacts": 10})


def test_run_bindcraft_normalizes_cif_input(monkeypatch, tmp_path):
    bindcraft_tool = DummyBindCraftTool()
    monkeypatch.setattr(
        "protein_agent.agent.service.structure_tool.ensure_pdb_structure",
        lambda structure_file, output_dir, output_name=None, biopython_python=None: {
            "input_path": structure_file,
            "resolved_path": "/tmp/converted_target.pdb",
            "converted": True,
            "converter": biopython_python,
        },
    )

    settings = Settings(
        bindcraft_default_binder_length=80,
        bindcraft_default_num_designs=10,
        converted_structures_dir=str(tmp_path / "converted"),
        biopython_python="/mnt/disk3/tio_nekton4/biopython_env/bin/python",
    )
    service = ProteinBinderService(
        settings,
        bindcraft_tool=bindcraft_tool,
        complexa_tool=DummyComplexaTool(),
        mda_tool=DummyMDATool(),
        orchestrator=object(),
    )

    result = service.run_bindcraft("/tmp/af2_model.cif", run_name="demo")

    assert bindcraft_tool.calls[0]["target_pdb"] == "/tmp/converted_target.pdb"
    assert result["request"]["input_structure_file"] == "/tmp/af2_model.cif"
    assert result["request"]["target_pdb"] == "/tmp/converted_target.pdb"
    assert result["request"]["structure_conversion"]["converted"] is True

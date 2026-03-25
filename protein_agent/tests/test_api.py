from fastapi.testclient import TestClient

from protein_agent.api.main import app
from protein_agent.config.settings import Settings


class DummyService:
    def available_modules(self):
        return ["status", "mdanalysis", "bindcraft", "proteina-complexa", "full_pipeline"]

    def tool_status(self):
        return {
            "module": "status",
            "tools": {
                "bindcraft": {"entrypoint_exists": True},
                "proteina-complexa": {"configured": True},
            },
        }

    def status(self):
        return self.tool_status()

    def run_bindcraft(self, target_pdb, **kwargs):
        return {"module": "bindcraft", "success": True, "request": {"target_pdb": target_pdb}, "output_files": ["/tmp/out.pdb"]}

    def run_complexa(self, task_name, **kwargs):
        return {
            "module": "proteina-complexa",
            "success": True,
            "request": {"task_name": task_name},
            "output_files": ["/tmp/cx_out.pdb"],
        }

    def analyze_structure(self, structure_file, **kwargs):
        return {
            "module": "mdanalysis",
            "success": True,
            "request": {"structure_file": structure_file},
            "output": {"n_contacts": 10, "binder_interface_residues": 5, "target_interface_residues": 7},
            "output_files": ["/tmp/report.json"],
        }

    def run_pipeline(self, target_pdb, **kwargs):
        ranking = [
            {
                "pdb": "/tmp/best_design.pdb",
                "source": "bindcraft",
                "score": 12.3,
                "n_contacts": 30,
                "n_hbonds": 4,
                "sc_proxy": 0.65,
            }
        ]
        return {
            "module": "full_pipeline",
            "request": {"target_pdb": target_pdb},
            "ranking": ranking,
            "best_design": ranking[0],
            "warnings": [],
        }

    def execute_plan(self, plan):
        module = plan["module"]
        params = plan["params"]
        if module == "status":
            return self.status()
        if module == "full_pipeline":
            return self.run_pipeline(params["target_pdb"])
        if module == "mdanalysis":
            return self.analyze_structure(params["structure_file"])
        raise AssertionError(f"unexpected module {module}")

    def format_execution_reply(self, result):
        if result["module"] == "full_pipeline":
            return "best=/tmp/best_design.pdb"
        if result["module"] == "status":
            return "status ok"
        if result["module"] == "mdanalysis":
            return "analysis ok"
        return "done"


class DummyPlanner:
    def __init__(self, plan):
        self.plan_payload = plan
        self.calls = []

    def plan(self, message, available_modules=None, previous_request=None, preferred_workflow=None):
        self.calls.append(
            {
                "message": message,
                "available_modules": list(available_modules or []),
                "previous_request": dict(previous_request or {}),
                "preferred_workflow": preferred_workflow,
            }
        )
        return dict(self.plan_payload)


class DummyReasoner:
    def reply(self, **kwargs):
        return "reasoned"


def test_ui_status_contains_llm_and_tool_status(monkeypatch):
    monkeypatch.setattr("protein_agent.api.main.get_service", lambda: DummyService())
    monkeypatch.setattr(
        "protein_agent.api.main.get_settings",
        lambda: Settings(openai_api_key="test-key", openai_base_url="https://example.com/v1", llm_model="gpt-5.2"),
    )
    client = TestClient(app)

    response = client.get("/ui/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["llm"]["configured"] is True
    assert payload["binder_agent"]["tools"]["bindcraft"]["entrypoint_exists"] is True


def test_home_returns_interactive_chat_ui():
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Agent Chat" in response.text
    assert "/v1/chat/completions" in response.text


def test_run_pipeline_endpoint(monkeypatch):
    monkeypatch.setattr("protein_agent.api.main.get_service", lambda: DummyService())
    client = TestClient(app)

    response = client.post("/run_pipeline", json={"target_pdb": "/tmp/target.pdb", "run_name": "demo"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["module"] == "full_pipeline"
    assert payload["best_design"]["pdb"] == "/tmp/best_design.pdb"


def test_chat_completions_execution(monkeypatch):
    monkeypatch.setattr("protein_agent.api.main.get_service", lambda: DummyService())
    planner = DummyPlanner(
        {
            "action": "execute",
            "module": "full_pipeline",
            "params": {"target_pdb": "/tmp/target.pdb"},
            "needs_input": False,
            "question": None,
        }
    )
    monkeypatch.setattr("protein_agent.api.main.get_planner", lambda: planner)
    client = TestClient(app)

    response = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "design a binder for /tmp/target.pdb"}]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["chat_mode"] == "execution"
    assert payload["best_design"]["pdb"] == "/tmp/best_design.pdb"
    assert payload["choices"][0]["message"]["content"] == "best=/tmp/best_design.pdb"
    assert planner.calls[0]["preferred_workflow"] is None


def test_chat_completions_reasoning(monkeypatch):
    monkeypatch.setattr("protein_agent.api.main.get_reasoner", lambda: DummyReasoner())
    client = TestClient(app)
    latest_result = DummyService().run_pipeline("/tmp/target.pdb")

    response = client.post(
        "/v1/chat/completions",
        json={
            "messages": [{"role": "user", "content": "why is this candidate better?"}],
            "latest_result": latest_result,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["chat_mode"] == "reasoning"
    assert payload["choices"][0]["message"]["content"] == "reasoned"

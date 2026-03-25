from pathlib import Path

import yaml

from protein_agent.config.settings import Settings


def test_settings_reuse_esm3_openai_aliases(monkeypatch, tmp_path):
    config_dir = tmp_path / "protein_agent" / "config"
    config_dir.mkdir(parents=True)

    agent_config = config_dir / "agent_config.yaml"
    tools_config = config_dir / "tools_config.yaml"
    workflows_config = config_dir / "workflows_config.yaml"

    agent_config.write_text(
        yaml.safe_dump(
            {
                "bindcraft_dir": "external/BindCraft",
                "complexa_dir": "external/Proteina-Complexa",
                "complexa_ckpt_path": "external/Proteina-Complexa/Protein-Target-160M-v1",
                "complexa_ckpt_name": "complexa.ckpt",
                "complexa_autoencoder_ckpt_path": "external/Proteina-Complexa/Protein-Target-160M-v1/complexa_ae.ckpt",
                "data_dir": "./data",
                "result_dir": "./data/results",
                "analysis_dir": "./data/analysis",
                "converted_structures_dir": "./data/converted_structures",
                "default_target_chain": "A",
                "default_binder_chain": "B",
                "biopython_python": "/mnt/disk3/tio_nekton4/biopython_env/bin/python",
            }
        ),
        encoding="utf-8",
    )
    tools_config.write_text(
        yaml.safe_dump(
            {
                "bindcraft": {"default_binder_length": 96, "default_num_designs": 12, "timeout_seconds": 999},
                "proteina_complexa": {"default_pipeline": "binder", "gen_njobs": 2, "eval_njobs": 3},
                "mdanalysis": {"default_cutoff": 6.0, "default_analysis": "full_report"},
            }
        ),
        encoding="utf-8",
    )
    workflows_config.write_text(
        yaml.safe_dump(
            {
                "default_workflow": "balanced",
                "workflows": {
                    "balanced": {"use_complexa": True, "use_bindcraft": True},
                    "bindcraft_only": {"use_complexa": False, "use_bindcraft": True},
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("PROTEIN_BINDER_AGENT_CONFIG", str(agent_config))
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.2")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.com/v1")

    settings = Settings.from_env()

    assert settings.llm_model == "gpt-5.2"
    assert settings.openai_api_key == "test-key"
    assert settings.openai_base_url == "https://example.com/v1"
    assert settings.bindcraft_default_binder_length == 96
    assert settings.bindcraft_default_num_designs == 12
    assert settings.complexa_gen_njobs == 2
    assert settings.workflow_profile("bindcraft_only")["use_bindcraft"] is True
    assert settings.bindcraft_dir == str((tmp_path / "external" / "BindCraft").resolve())
    assert settings.complexa_dir == str((tmp_path / "external" / "Proteina-Complexa").resolve())
    assert settings.complexa_checkpoint_overrides()["ckpt_name"] == "complexa.ckpt"
    assert settings.complexa_checkpoint_overrides()["autoencoder_ckpt_path"].endswith("complexa_ae.ckpt")
    assert settings.biopython_python == "/mnt/disk3/tio_nekton4/biopython_env/bin/python"
    assert settings.converted_structures_dir == str((tmp_path / "data" / "converted_structures").resolve())


def test_settings_expand_user_paths_from_env(monkeypatch, tmp_path):
    config_dir = tmp_path / "protein_agent" / "config"
    config_dir.mkdir(parents=True)

    agent_config = config_dir / "agent_config.yaml"
    agent_config.write_text(yaml.safe_dump({}), encoding="utf-8")

    monkeypatch.setenv("PROTEIN_BINDER_AGENT_CONFIG", str(agent_config))
    monkeypatch.setenv("PROTEIN_BINDER_AGENT_COMPLEXA_DIR", "~/Proteina-Complexa")
    monkeypatch.setenv("PROTEIN_BINDER_AGENT_COMPLEXA_PYTHON", "~/.venvs/complexa/bin/python")

    settings = Settings.from_env()

    assert settings.complexa_dir == str(Path("~/Proteina-Complexa").expanduser().resolve())
    assert settings.complexa_venv_python == str(Path("~/.venvs/complexa/bin/python").expanduser().resolve())

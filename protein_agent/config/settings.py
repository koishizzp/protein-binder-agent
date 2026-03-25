from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import os
from pathlib import Path
import sys
from typing import Any

import yaml


def _load_env_file(path: str = ".env") -> dict[str, str]:
    env: dict[str, str] = {}
    file_path = Path(path)
    if not file_path.exists():
        return env
    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _env_source() -> dict[str, str]:
    data = _load_env_file()
    data.update(os.environ)
    return data


def _env_get(data: dict[str, str], name: str, default: str | None = None) -> str | None:
    return data.get(name, default)


def _env_get_first(data: dict[str, str], names: list[str], default: str | None = None) -> str | None:
    for name in names:
        if name in data:
            return data[name]
    return default


def _to_int(value: str | None, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _to_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _to_optional_str(value: str | None, default: str | None = None) -> str | None:
    if value is None:
        return default
    cleaned = value.strip()
    return cleaned if cleaned else default


def _load_yaml(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    file_path = Path(path)
    if not file_path.exists():
        return {}
    raw = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def _resolve_path(value: str | None, *, base_dir: Path) -> str | None:
    if value is None:
        return None
    if value.startswith("/"):
        return value
    candidate = Path(value)
    if candidate.is_absolute():
        return str(candidate)
    return str((base_dir / candidate).resolve())


def _default_workflows() -> dict[str, dict[str, Any]]:
    return {
        "balanced": {
            "description": "Run Proteina-Complexa and BindCraft, then score everything with MDAnalysis.",
            "use_complexa": True,
            "use_bindcraft": True,
        },
        "complexa_only": {
            "description": "Run Proteina-Complexa only.",
            "use_complexa": True,
            "use_bindcraft": False,
        },
        "bindcraft_only": {
            "description": "Run BindCraft only.",
            "use_complexa": False,
            "use_bindcraft": True,
        },
    }


@dataclass(slots=True)
class Settings:
    app_name: str = "Protein Binder Agent"
    log_level: str = "INFO"
    config_path: str = "protein_agent/config/agent_config.yaml"
    tools_config_path: str = "protein_agent/config/tools_config.yaml"
    workflows_config_path: str = "protein_agent/config/workflows_config.yaml"

    llm_model: str = "gpt-4o-mini"
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    request_timeout: int = 300

    api_host: str = "0.0.0.0"
    api_port: int = 8200

    data_dir: str = "./data"
    result_dir: str = "./data/results"
    analysis_dir: str = "./data/analysis"
    upload_dir: str = "./data/uploads"

    default_target_chain: str = "A"
    default_binder_chain: str = "B"

    bindcraft_dir: str | None = None
    bindcraft_python_path: str = sys.executable or "python"
    bindcraft_settings_dir: str | None = None
    bindcraft_filters_file: str | None = None
    bindcraft_advanced_file: str | None = None
    bindcraft_timeout_seconds: int = 10800
    bindcraft_default_binder_length: int = 80
    bindcraft_default_num_designs: int = 10

    complexa_dir: str | None = None
    complexa_cli: str | None = None
    complexa_venv_python: str | None = None
    complexa_config_dir: str | None = None
    complexa_ckpt_path: str | None = None
    complexa_ckpt_name: str = "complexa.ckpt"
    complexa_autoencoder_ckpt_path: str | None = None
    complexa_timeout_seconds: int = 7200
    complexa_default_pipeline: str = "binder"
    complexa_gen_njobs: int = 1
    complexa_eval_njobs: int = 1
    complexa_validate_before_run: bool = True

    mdanalysis_default_cutoff: float = 5.0
    mdanalysis_default_analysis: str = "full_report"

    default_workflow: str = "balanced"
    workflow_profiles: dict[str, dict[str, Any]] = field(default_factory=_default_workflows)

    @classmethod
    def from_env(cls, config_path_override: str | None = None) -> "Settings":
        data = _env_source()
        defaults = cls()

        config_path = (
            config_path_override
            or _env_get(data, "PROTEIN_BINDER_AGENT_CONFIG")
            or _env_get(data, "PROTEIN_AGENT_CONFIG")
            or defaults.config_path
        )
        config_path_obj = Path(config_path).resolve()
        config_dir = config_path_obj.parent
        repo_root = config_dir.parent.parent if config_dir.name == "config" and len(config_dir.parents) >= 2 else Path.cwd()

        tools_config_path = (
            _env_get(data, "PROTEIN_BINDER_AGENT_TOOLS_CONFIG")
            or str((config_dir / "tools_config.yaml").resolve())
        )
        workflows_config_path = (
            _env_get(data, "PROTEIN_BINDER_AGENT_WORKFLOWS_CONFIG")
            or str((config_dir / "workflows_config.yaml").resolve())
        )

        agent_cfg = _load_yaml(config_path_obj)
        tools_cfg = _load_yaml(tools_config_path)
        workflows_cfg = _load_yaml(workflows_config_path)

        bindcraft_cfg = tools_cfg.get("bindcraft", {}) if isinstance(tools_cfg.get("bindcraft"), dict) else {}
        complexa_cfg = (
            tools_cfg.get("proteina_complexa", {}) if isinstance(tools_cfg.get("proteina_complexa"), dict) else {}
        )
        mda_cfg = tools_cfg.get("mdanalysis", {}) if isinstance(tools_cfg.get("mdanalysis"), dict) else {}
        workflow_profiles = workflows_cfg.get("workflows") if isinstance(workflows_cfg.get("workflows"), dict) else _default_workflows()

        bindcraft_dir = _resolve_path(
            _to_optional_str(_env_get(data, "PROTEIN_BINDER_AGENT_BINDCRAFT_DIR"), agent_cfg.get("bindcraft_dir")),
            base_dir=repo_root,
        )
        complexa_dir = _resolve_path(
            _to_optional_str(_env_get(data, "PROTEIN_BINDER_AGENT_COMPLEXA_DIR"), agent_cfg.get("complexa_dir")),
            base_dir=repo_root,
        )

        return cls(
            app_name=_env_get(data, "PROTEIN_BINDER_AGENT_APP_NAME", agent_cfg.get("app_name", defaults.app_name))
            or defaults.app_name,
            log_level=_env_get(data, "PROTEIN_BINDER_AGENT_LOG_LEVEL", agent_cfg.get("log_level", defaults.log_level))
            or defaults.log_level,
            config_path=str(config_path_obj),
            tools_config_path=str(Path(tools_config_path).resolve()),
            workflows_config_path=str(Path(workflows_config_path).resolve()),
            llm_model=_env_get_first(
                data,
                ["PROTEIN_BINDER_AGENT_LLM_MODEL", "PROTEIN_AGENT_LLM_MODEL", "OPENAI_MODEL"],
                agent_cfg.get("model", defaults.llm_model),
            )
            or defaults.llm_model,
            openai_api_key=_to_optional_str(
                _env_get_first(
                    data,
                    ["PROTEIN_BINDER_AGENT_OPENAI_API_KEY", "PROTEIN_AGENT_OPENAI_API_KEY", "OPENAI_API_KEY"],
                )
            ),
            openai_base_url=_to_optional_str(
                _env_get_first(
                    data,
                    ["PROTEIN_BINDER_AGENT_OPENAI_BASE_URL", "PROTEIN_AGENT_OPENAI_BASE_URL", "OPENAI_BASE_URL"],
                )
            ),
            request_timeout=_to_int(
                _env_get(data, "PROTEIN_BINDER_AGENT_REQUEST_TIMEOUT", str(agent_cfg.get("request_timeout", defaults.request_timeout))),
                defaults.request_timeout,
            ),
            api_host=_env_get(data, "PROTEIN_BINDER_AGENT_API_HOST", agent_cfg.get("api_host", defaults.api_host))
            or defaults.api_host,
            api_port=_to_int(
                _env_get(data, "PROTEIN_BINDER_AGENT_API_PORT", str(agent_cfg.get("api_port", defaults.api_port))),
                defaults.api_port,
            ),
            data_dir=_resolve_path(
                _env_get(data, "PROTEIN_BINDER_AGENT_DATA_DIR", agent_cfg.get("data_dir", defaults.data_dir)),
                base_dir=repo_root,
            )
            or defaults.data_dir,
            result_dir=_resolve_path(
                _env_get(data, "PROTEIN_BINDER_AGENT_RESULT_DIR", agent_cfg.get("result_dir", defaults.result_dir)),
                base_dir=repo_root,
            )
            or defaults.result_dir,
            analysis_dir=_resolve_path(
                _env_get(data, "PROTEIN_BINDER_AGENT_ANALYSIS_DIR", agent_cfg.get("analysis_dir", defaults.analysis_dir)),
                base_dir=repo_root,
            )
            or defaults.analysis_dir,
            upload_dir=_resolve_path(
                _env_get(data, "PROTEIN_BINDER_AGENT_UPLOAD_DIR", agent_cfg.get("upload_dir", defaults.upload_dir)),
                base_dir=repo_root,
            )
            or defaults.upload_dir,
            default_target_chain=_env_get(
                data, "PROTEIN_BINDER_AGENT_DEFAULT_TARGET_CHAIN", agent_cfg.get("default_target_chain", defaults.default_target_chain)
            )
            or defaults.default_target_chain,
            default_binder_chain=_env_get(
                data, "PROTEIN_BINDER_AGENT_DEFAULT_BINDER_CHAIN", agent_cfg.get("default_binder_chain", defaults.default_binder_chain)
            )
            or defaults.default_binder_chain,
            bindcraft_dir=bindcraft_dir,
            bindcraft_python_path=_env_get(
                data,
                "PROTEIN_BINDER_AGENT_BINDCRAFT_PYTHON",
                agent_cfg.get("bindcraft_python_path", defaults.bindcraft_python_path),
            )
            or defaults.bindcraft_python_path,
            bindcraft_settings_dir=_resolve_path(
                _env_get(data, "PROTEIN_BINDER_AGENT_BINDCRAFT_SETTINGS_DIR", agent_cfg.get("bindcraft_settings_dir")),
                base_dir=Path(bindcraft_dir) if bindcraft_dir else repo_root,
            ),
            bindcraft_filters_file=_resolve_path(
                _env_get(data, "PROTEIN_BINDER_AGENT_BINDCRAFT_FILTERS", agent_cfg.get("bindcraft_filters_file")),
                base_dir=Path(bindcraft_dir) if bindcraft_dir else repo_root,
            ),
            bindcraft_advanced_file=_resolve_path(
                _env_get(data, "PROTEIN_BINDER_AGENT_BINDCRAFT_ADVANCED", agent_cfg.get("bindcraft_advanced_file")),
                base_dir=Path(bindcraft_dir) if bindcraft_dir else repo_root,
            ),
            bindcraft_timeout_seconds=_to_int(
                _env_get(
                    data,
                    "PROTEIN_BINDER_AGENT_BINDCRAFT_TIMEOUT",
                    str(bindcraft_cfg.get("timeout_seconds", defaults.bindcraft_timeout_seconds)),
                ),
                defaults.bindcraft_timeout_seconds,
            ),
            bindcraft_default_binder_length=_to_int(
                _env_get(
                    data,
                    "PROTEIN_BINDER_AGENT_BINDCRAFT_DEFAULT_LENGTH",
                    str(bindcraft_cfg.get("default_binder_length", defaults.bindcraft_default_binder_length)),
                ),
                defaults.bindcraft_default_binder_length,
            ),
            bindcraft_default_num_designs=_to_int(
                _env_get(
                    data,
                    "PROTEIN_BINDER_AGENT_BINDCRAFT_DEFAULT_NUM_DESIGNS",
                    str(bindcraft_cfg.get("default_num_designs", defaults.bindcraft_default_num_designs)),
                ),
                defaults.bindcraft_default_num_designs,
            ),
            complexa_dir=complexa_dir,
            complexa_cli=_env_get(data, "PROTEIN_BINDER_AGENT_COMPLEXA_CLI", agent_cfg.get("complexa_cli", defaults.complexa_cli)),
            complexa_venv_python=_resolve_path(
                _env_get(data, "PROTEIN_BINDER_AGENT_COMPLEXA_PYTHON", agent_cfg.get("complexa_venv_python")),
                base_dir=repo_root,
            ),
            complexa_config_dir=_resolve_path(
                _env_get(data, "PROTEIN_BINDER_AGENT_COMPLEXA_CONFIG_DIR", agent_cfg.get("complexa_config_dir")),
                base_dir=Path(complexa_dir) if complexa_dir else repo_root,
            ),
            complexa_ckpt_path=_resolve_path(
                _env_get(data, "PROTEIN_BINDER_AGENT_COMPLEXA_CKPT_PATH", agent_cfg.get("complexa_ckpt_path")),
                base_dir=Path(complexa_dir) if complexa_dir else repo_root,
            ),
            complexa_ckpt_name=_env_get(
                data,
                "PROTEIN_BINDER_AGENT_COMPLEXA_CKPT_NAME",
                agent_cfg.get("complexa_ckpt_name", defaults.complexa_ckpt_name),
            )
            or defaults.complexa_ckpt_name,
            complexa_autoencoder_ckpt_path=_resolve_path(
                _env_get(
                    data,
                    "PROTEIN_BINDER_AGENT_COMPLEXA_AUTOENCODER_CKPT_PATH",
                    agent_cfg.get("complexa_autoencoder_ckpt_path"),
                ),
                base_dir=Path(complexa_dir) if complexa_dir else repo_root,
            ),
            complexa_timeout_seconds=_to_int(
                _env_get(
                    data,
                    "PROTEIN_BINDER_AGENT_COMPLEXA_TIMEOUT",
                    str(complexa_cfg.get("timeout_seconds", defaults.complexa_timeout_seconds)),
                ),
                defaults.complexa_timeout_seconds,
            ),
            complexa_default_pipeline=_env_get(
                data,
                "PROTEIN_BINDER_AGENT_COMPLEXA_DEFAULT_PIPELINE",
                complexa_cfg.get("default_pipeline", defaults.complexa_default_pipeline),
            )
            or defaults.complexa_default_pipeline,
            complexa_gen_njobs=_to_int(
                _env_get(data, "PROTEIN_BINDER_AGENT_COMPLEXA_GEN_NJOBS", str(complexa_cfg.get("gen_njobs", defaults.complexa_gen_njobs))),
                defaults.complexa_gen_njobs,
            ),
            complexa_eval_njobs=_to_int(
                _env_get(data, "PROTEIN_BINDER_AGENT_COMPLEXA_EVAL_NJOBS", str(complexa_cfg.get("eval_njobs", defaults.complexa_eval_njobs))),
                defaults.complexa_eval_njobs,
            ),
            complexa_validate_before_run=_to_bool(
                _env_get(data, "PROTEIN_BINDER_AGENT_COMPLEXA_VALIDATE", str(agent_cfg.get("complexa_validate_before_run", defaults.complexa_validate_before_run))),
                defaults.complexa_validate_before_run,
            ),
            mdanalysis_default_cutoff=float(
                _env_get(data, "PROTEIN_BINDER_AGENT_MDANALYSIS_CUTOFF", str(mda_cfg.get("default_cutoff", defaults.mdanalysis_default_cutoff)))
                or defaults.mdanalysis_default_cutoff
            ),
            mdanalysis_default_analysis=_env_get(
                data,
                "PROTEIN_BINDER_AGENT_MDANALYSIS_DEFAULT",
                mda_cfg.get("default_analysis", defaults.mdanalysis_default_analysis),
            )
            or defaults.mdanalysis_default_analysis,
            default_workflow=_env_get(
                data, "PROTEIN_BINDER_AGENT_DEFAULT_WORKFLOW", workflows_cfg.get("default_workflow", defaults.default_workflow)
            )
            or defaults.default_workflow,
            workflow_profiles=workflow_profiles or _default_workflows(),
        )

    def workflow_profile(self, name: str | None) -> dict[str, Any]:
        workflow_name = name or self.default_workflow
        if workflow_name in self.workflow_profiles:
            return dict(self.workflow_profiles[workflow_name])
        return dict(self.workflow_profiles.get(self.default_workflow, _default_workflows()["balanced"]))

    def complexa_checkpoint_overrides(self) -> dict[str, Any]:
        overrides: dict[str, Any] = {}
        if self.complexa_ckpt_path:
            overrides["ckpt_path"] = self.complexa_ckpt_path
        if self.complexa_ckpt_name:
            overrides["ckpt_name"] = self.complexa_ckpt_name
        if self.complexa_autoencoder_ckpt_path:
            overrides["autoencoder_ckpt_path"] = self.complexa_autoencoder_ckpt_path
        return overrides


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()

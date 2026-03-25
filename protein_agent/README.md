# Protein Binder Agent

This repo now exposes a usable binder-design agent that combines:

- `BindCraft` for hotspot-guided binder generation
- `Proteina-Complexa` for de novo complex generation
- `MDAnalysis` for post-generation scoring and ranking
- an OpenAI-compatible LLM planner/reasoner layer

The LLM environment variables are compatible with `esm3-agent`:

```bash
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://your-openai-compatible-endpoint/v1
OPENAI_MODEL=gpt-5.2
```

The agent also accepts the same `PROTEIN_AGENT_*` aliases used by `esm3-agent`:

```bash
PROTEIN_AGENT_OPENAI_API_KEY=...
PROTEIN_AGENT_OPENAI_BASE_URL=...
PROTEIN_AGENT_LLM_MODEL=gpt-5.2
```

## Layout

- `agent/`
  - planner, reasoner, chat helpers, service layer, and the high-level agent entrypoint
- `api/`
  - FastAPI app with direct endpoints and `/v1/chat/completions`
- `tools/`
  - BindCraft / Proteina-Complexa / MDAnalysis wrappers
- `pipeline/`
  - full design-and-rank orchestration
- `config/`
  - runtime YAML config for tool paths and workflow defaults

## Install

```bash
cd D:/protein-binder-agent/protein_agent
pip install -r requirements.txt
```

Then edit `config/agent_config.yaml` and point these paths to your local installs:

- `bindcraft_dir`
- `complexa_dir`
- `complexa_ckpt_path`
- `complexa_ckpt_name`
- `complexa_autoencoder_ckpt_path`
- optionally `complexa_cli` or `complexa_venv_python`

For your Linux server deployment, the current repo config is already aligned to:

```yaml
bindcraft_dir: /mnt/disk3/tio_nekton4/BindCraft/
complexa_dir: /mnt/disk3/tio_nekton4/Proteina-Complexa/
complexa_ckpt_path: /mnt/disk3/tio_nekton4/Proteina-Complexa/Protein-Target-160M-v1/
complexa_ckpt_name: complexa.ckpt
complexa_autoencoder_ckpt_path: /mnt/disk3/tio_nekton4/Proteina-Complexa/Protein-Target-160M-v1/complexa_ae.ckpt
```

## Server Deployment

From the repository root on the Linux server:

```bash
cp .env.example .env
vi .env
python3 -m pip install -r protein_agent/requirements.txt
bash start.sh
```

Useful management scripts at repo root:

```bash
bash start.sh
bash stop.sh
bash restart.sh
bash status.sh
bash smoke_test.sh
```

The startup scripts read `.env` and support these deployment-specific variables:

- `PROTEIN_BINDER_AGENT_RUNTIME_PYTHON`
- `PROTEIN_BINDER_AGENT_PID_FILE`
- `PROTEIN_BINDER_AGENT_LOG_DIR`
- `PROTEIN_BINDER_AGENT_API_HOST`
- `PROTEIN_BINDER_AGENT_API_PORT`
- `PROTEIN_BINDER_AGENT_BIOPYTHON_PYTHON`
- `PROTEIN_BINDER_AGENT_CONVERTED_STRUCTURES_DIR`

If `complexa` is not on `PATH`, set one of:

- `PROTEIN_BINDER_AGENT_COMPLEXA_CLI`
- `PROTEIN_BINDER_AGENT_COMPLEXA_PYTHON`

If BindCraft must run inside a specific Python environment, set:

- `PROTEIN_BINDER_AGENT_BINDCRAFT_PYTHON`

The BindCraft wrapper now tries to auto-detect a local environment with `pyrosetta`
under the BindCraft repo, but if that fails you still need to set
`PROTEIN_BINDER_AGENT_BINDCRAFT_PYTHON` explicitly.

## Run

CLI from repo root:

```bash
python main.py status
python main.py chat "Design a binder for /mnt/disk3/targets/PDL1.pdb"
python main.py pipeline /mnt/disk3/targets/PDL1.pdb --workflow balanced --hotspot A54,A56,A115
python main.py analyze /mnt/disk3/results/complex.pdb --analysis-type full_report
python main.py serve
```

Package entrypoint:

```bash
python -m protein_agent.main serve
```

## API

Direct endpoints:

- `POST /run_bindcraft`
- `POST /run_complexa`
- `POST /analyze_structure`
- `POST /run_pipeline`
- `GET /ui/status`
- `GET /v1/models`

OpenAI-compatible chat endpoint:

```bash
curl -X POST http://127.0.0.1:8200/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "protein-binder-design-agent",
    "messages": [
      {"role": "user", "content": "Use the full pipeline for /mnt/disk3/targets/PDL1.pdb and rank the binders"}
    ]
  }'
```

## Notes

- `BindCraft` is wrapped with the upstream-style target settings JSON and `bindcraft.py --settings ...` execution model.
- `Proteina-Complexa` is wrapped around the official `complexa validate` and `complexa design` CLI flow.
- The agent now automatically injects `ckpt_path`, `ckpt_name`, and `autoencoder_ckpt_path` into Complexa runs when they are configured.
- `.cif`, `.mmcif`, and `.ent` inputs are now normalized to `.pdb` before PDB-only workflows. The agent will use in-process BioPython when available, or the external interpreter from `PROTEIN_BINDER_AGENT_BIOPYTHON_PYTHON`.
- Proteina-Complexa pipeline YAMLs are now auto-discovered recursively if they are not directly under `configs/`.
- The root-level deployment scripts are Linux-oriented and intended for the server where `/mnt/disk3/tio_nekton4/...` exists.
- `Proteina-Complexa` still depends on its own task/config preparation model. If your target is not already prepared in that repo, you may need to add or register the target there first.
- `MDAnalysis` is used for ranking. The current full pipeline scores candidates with interface contacts, hydrogen-bond count, interface residue count, and a shape-complementarity proxy.

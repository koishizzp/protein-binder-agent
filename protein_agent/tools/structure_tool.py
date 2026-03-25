from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
from typing import Any

try:
    from Bio.PDB import MMCIFParser, PDBIO, PDBParser, Select
except Exception:  # noqa: BLE001
    MMCIFParser = None
    PDBIO = None
    PDBParser = None
    Select = object


PDB_SUFFIXES = {".pdb"}
CIF_SUFFIXES = {".cif", ".mmcif"}
COPY_TO_PDB_SUFFIXES = {".ent"}


class _ChainSelect(Select):
    def __init__(self, chain_id: str):
        self.chain_id = chain_id

    def accept_chain(self, chain):
        return chain.id == self.chain_id


def _suffix(path: str | Path) -> str:
    return Path(path).suffix.lower()


def is_pdb_path(path: str | Path) -> bool:
    return _suffix(path) in PDB_SUFFIXES


def is_cif_path(path: str | Path) -> bool:
    return _suffix(path) in CIF_SUFFIXES


def requires_pdb_conversion(path: str | Path) -> bool:
    return _suffix(path) in CIF_SUFFIXES | COPY_TO_PDB_SUFFIXES


def _load_structure(input_path: str):
    suffix = _suffix(input_path)
    if suffix in PDB_SUFFIXES | COPY_TO_PDB_SUFFIXES:
        if PDBParser is None:
            raise RuntimeError("BioPython PDBParser is unavailable")
        return PDBParser(QUIET=True).get_structure("structure", input_path)
    if suffix in CIF_SUFFIXES:
        if MMCIFParser is None:
            raise RuntimeError("BioPython MMCIFParser is unavailable")
        return MMCIFParser(QUIET=True).get_structure("structure", input_path)
    raise ValueError(f"Unsupported structure format: {input_path}")


def _convert_with_biopython(input_path: str, output_path: str) -> str:
    suffix = _suffix(input_path)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    if suffix in PDB_SUFFIXES:
        if Path(input_path).resolve() != destination.resolve():
            shutil.copyfile(input_path, output_path)
        return output_path

    if suffix in COPY_TO_PDB_SUFFIXES:
        shutil.copyfile(input_path, output_path)
        return output_path

    if PDBIO is None:
        raise RuntimeError("BioPython PDBIO is unavailable")
    structure = _load_structure(input_path)
    io = PDBIO()
    io.set_structure(structure)
    io.save(output_path)
    return output_path


def _converter_script_path() -> Path:
    return Path(__file__).resolve().parents[1] / "scripts" / "convert_structure.py"


def _convert_with_external_python(input_path: str, output_path: str, python_executable: str) -> str:
    script_path = _converter_script_path()
    if not script_path.exists():
        raise FileNotFoundError(f"Converter script not found: {script_path}")
    command = [python_executable, str(script_path), input_path, output_path]
    result = subprocess.run(command, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "external BioPython conversion failed")
    return output_path


def ensure_pdb_structure(
    input_path: str,
    *,
    output_dir: str,
    output_name: str | None = None,
    biopython_python: str | None = None,
) -> dict[str, Any]:
    source = Path(input_path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"Structure file not found: {source}")

    if is_pdb_path(source):
        return {
            "input_path": str(source),
            "resolved_path": str(source),
            "converted": False,
            "converter": None,
        }

    target_dir = Path(output_dir).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    target_name = output_name or f"{source.stem}.pdb"
    if not target_name.lower().endswith(".pdb"):
        target_name += ".pdb"
    destination = target_dir / target_name

    converter = "biopython"
    try:
        resolved = _convert_with_biopython(str(source), str(destination))
    except Exception as primary_error:  # noqa: BLE001
        if not biopython_python:
            raise RuntimeError(f"Failed to convert {source} to PDB via BioPython: {primary_error}") from primary_error
        converter = biopython_python
        resolved = _convert_with_external_python(str(source), str(destination), biopython_python)

    return {
        "input_path": str(source),
        "resolved_path": str(Path(resolved).resolve()),
        "converted": True,
        "converter": converter,
    }


def extract_chain(input_structure: str, output_pdb: str, chain_id: str) -> str:
    structure = _load_structure(input_structure)
    Path(output_pdb).parent.mkdir(parents=True, exist_ok=True)
    io = PDBIO()
    io.set_structure(structure)
    io.save(output_pdb, _ChainSelect(chain_id))
    return output_pdb

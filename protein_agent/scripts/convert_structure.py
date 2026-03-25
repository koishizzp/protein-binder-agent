from __future__ import annotations

import argparse
from pathlib import Path
import shutil

from Bio.PDB import MMCIFParser, PDBIO, PDBParser


def load_structure(path: str):
    suffix = Path(path).suffix.lower()
    if suffix in {".pdb", ".ent"}:
        return PDBParser(QUIET=True).get_structure("structure", path)
    if suffix in {".cif", ".mmcif"}:
        return MMCIFParser(QUIET=True).get_structure("structure", path)
    raise ValueError(f"Unsupported structure format: {path}")


def convert_structure(input_path: str, output_path: str) -> str:
    source = Path(input_path).expanduser().resolve()
    target = Path(output_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    if source.suffix.lower() == ".pdb":
        if source != target:
            shutil.copyfile(source, target)
        return str(target)

    if source.suffix.lower() == ".ent":
        shutil.copyfile(source, target)
        return str(target)

    structure = load_structure(str(source))
    io = PDBIO()
    io.set_structure(structure)
    io.save(str(target))
    return str(target)


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert protein structures to PDB using BioPython")
    parser.add_argument("input_path")
    parser.add_argument("output_path")
    args = parser.parse_args()
    print(convert_structure(args.input_path, args.output_path))


if __name__ == "__main__":
    main()

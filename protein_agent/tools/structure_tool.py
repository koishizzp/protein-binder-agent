from pathlib import Path

from Bio.PDB import PDBIO, PDBParser, Select


class _ChainSelect(Select):
    def __init__(self, chain_id: str):
        self.chain_id = chain_id

    def accept_chain(self, chain):
        return chain.id == self.chain_id


def extract_chain(input_pdb: str, output_pdb: str, chain_id: str) -> str:
    parser = PDBParser(QUIET=True)
    structure = parser.get_structure("target", input_pdb)
    Path(output_pdb).parent.mkdir(parents=True, exist_ok=True)
    io = PDBIO()
    io.set_structure(structure)
    io.save(output_pdb, _ChainSelect(chain_id))
    return output_pdb

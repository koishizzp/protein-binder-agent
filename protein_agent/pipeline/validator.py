def validate_ranking_row(row: dict) -> bool:
    required = {"pdb", "source", "score", "n_contacts", "n_hbonds", "sc_proxy"}
    return required.issubset(set(row.keys()))

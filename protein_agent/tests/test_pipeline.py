from pipeline.validator import validate_ranking_row


def test_validate_ranking_row():
    row = {
        "pdb": "a.pdb",
        "source": "bindcraft",
        "score": 1.0,
        "n_contacts": 10,
        "n_hbonds": 2,
        "sc_proxy": 0.5,
    }
    assert validate_ranking_row(row)

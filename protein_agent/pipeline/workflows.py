WORKFLOWS = {
    "balanced": {
        "description": "Run Proteina-Complexa and BindCraft, then score both branches with MDAnalysis.",
        "use_complexa": True,
        "use_bindcraft": True,
    },
    "complexa_only": {
        "description": "Use only Proteina-Complexa generation.",
        "use_complexa": True,
        "use_bindcraft": False,
    },
    "bindcraft_only": {
        "description": "Use only BindCraft generation.",
        "use_complexa": False,
        "use_bindcraft": True,
    },
}

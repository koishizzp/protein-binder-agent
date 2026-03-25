WORKFLOWS = {
    "balanced": {
        "description": "Complexa + BindCraft 双路生成并统一评估",
        "use_complexa": True,
        "use_bindcraft": True,
    },
    "complexa_only": {
        "description": "仅使用 Proteina-Complexa 生成",
        "use_complexa": True,
        "use_bindcraft": False,
    },
    "bindcraft_only": {
        "description": "仅使用 BindCraft 生成",
        "use_complexa": False,
        "use_bindcraft": True,
    },
}

"""Inventory categories and their equipment types.

The stored Asset.category remains the equipment type for compatibility.
"""
ASSET_GROUPS = {
    "computing": {"label": "Equipo de cómputo", "types": ("Computadora", "Laptop", "Tablet")},
    "printers": {"label": "Impresoras", "types": ("Impresora",)},
    "communication": {"label": "Comunicación", "types": ("Red", "Teléfono", "Radio")},
    "peripherals": {"label": "Periféricos", "types": ("Monitor",)},
    "other": {"label": "Otros", "types": ("Otro",)},
}
ASSET_TYPES = [kind for group in ASSET_GROUPS.values() for kind in group["types"]]


def group_for_type(kind):
    return next((key for key, group in ASSET_GROUPS.items() if kind in group["types"]), "other")

from __future__ import annotations

"""Topología del corredor. La usan el simulador, el enclavamiento y el frenado
para que la noción de 'bloque siguiente' sea única en todo el sistema.
"""

MAIN_LINE = [f"M{index:02d}" for index in range(1, 11)]
SIDING = ["S01", "S02", "S03"]
SWITCH_BLOCK = "M05"

_MAIN_INDEX = {block_id: index for index, block_id in enumerate(MAIN_LINE)}
_SIDING_INDEX = {block_id: index for index, block_id in enumerate(SIDING)}


def successors(block_id: str, switch_position: str) -> list[str]:
    """Bloques alcanzables legalmente desde `block_id` en un solo paso."""
    if block_id == SWITCH_BLOCK:
        if switch_position == "REVERSE":
            return ["S01"]
        return ["M06"]
    if block_id == "S03":
        return ["M07"]
    if block_id in _MAIN_INDEX:
        index = _MAIN_INDEX[block_id]
        if index + 1 < len(MAIN_LINE):
            return [MAIN_LINE[index + 1]]
        return []
    if block_id in _SIDING_INDEX:
        index = _SIDING_INDEX[block_id]
        if index + 1 < len(SIDING):
            return [SIDING[index + 1]]
        return ["M07"]
    return []


def progress_key(block_id: str, position_m: float) -> float:
    """Orden aproximado a lo largo del corredor, de cola a cabeza."""
    if block_id in _MAIN_INDEX:
        return _MAIN_INDEX[block_id] * 10_000 + position_m
    if block_id in _SIDING_INDEX:
        # El apartadero nace en M05 (índice 4) y reingresa antes de M07.
        branch = 4.2 + _SIDING_INDEX[block_id] * 0.2
        return branch * 10_000 + position_m
    return position_m


def interpolate(block: dict, position_m: float) -> tuple[float, float]:
    length = float(block["length_m"]) or 1.0
    fraction = min(1.0, max(0.0, float(position_m) / length))
    latitude = float(block["latitude_start"]) + fraction * (
        float(block["latitude_end"]) - float(block["latitude_start"])
    )
    longitude = float(block["longitude_start"]) + fraction * (
        float(block["longitude_end"]) - float(block["longitude_start"])
    )
    return latitude, longitude

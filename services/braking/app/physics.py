from __future__ import annotations

"""Curva de frenado de la PTC.

Convención de pendiente: grade_percent > 0 es descenso en el sentido de la
marcha y reduce la deceleración disponible. La distancia de parada incluye
el tiempo de reacción y un factor de seguridad. Si el cálculo no puede
completarse, la señal de fallo seguro es EMERGENCY_BRAKE.
"""

G = 9.80665
REACTION_S = 1.8
SAFETY_FACTOR = 1.35
MIN_DECEL = 0.35
REFERENCE_MASS_KG = 200_000.0


def deceleration(adhesion: float, grade_percent: float, mass_kg: float) -> float:
    usable_adhesion = max(0.15, min(1.0, adhesion))
    friction = 0.20 * usable_adhesion
    grade = grade_percent / 100.0
    raw = friction * G - G * grade
    mass_factor = min(1.0, REFERENCE_MASS_KG / max(mass_kg, 1.0))
    scaled = raw * (0.65 + 0.35 * mass_factor)
    return max(MIN_DECEL, scaled)


def stopping_distance(
    speed_kmh: float,
    adhesion: float,
    grade_percent: float,
    mass_kg: float,
) -> float:
    speed_mps = max(0.0, speed_kmh) / 3.6
    rate = deceleration(adhesion, grade_percent, mass_kg)
    reaction = speed_mps * REACTION_S
    braking = (speed_mps * speed_mps) / (2.0 * rate)
    return reaction + braking

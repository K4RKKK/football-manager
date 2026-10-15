"""Unités monétaires.

fmsave renvoie l'argent « dans l'unité stockée par la sauvegarde, qui n'est pas la devise
affichée par le jeu ». Nous ne devinons pas la conversion : l'utilisateur l'étalonne une fois
(valeur affichée en jeu d'un joueur connu ÷ valeur brute lue), et tant que ce n'est pas fait,
toute comparaison avec un montant exprimé en devise est refusée.
"""

from __future__ import annotations

from pydantic import BaseModel


class CurrencyCalibration(BaseModel):
    symbol: str = "€"
    # montant affiché = brut × factor
    factor: float | None = None
    reference: str | None = None  # ex. "Valeur de J. Exemple : 12 M€ vue le 01/03/2031"

    @property
    def calibrated(self) -> bool:
        return self.factor is not None and self.factor > 0

    def to_display(self, raw: float | None) -> float | None:
        if raw is None or not self.calibrated:
            return None
        return raw * self.factor  # type: ignore[operator]

    def to_raw(self, display_amount: float) -> int:
        if not self.calibrated:
            raise UncalibratedCurrency()
        return int(round(display_amount / self.factor))  # type: ignore[operator]

    def format(self, raw: float | None) -> str:
        if raw is None:
            return "non disponible"
        if not self.calibrated:
            number = f"{raw:,}".replace(",", " ")
            return f"{number} (unité brute de la sauvegarde, devise non étalonnée)"
        return format_amount(self.to_display(raw), self.symbol)  # type: ignore[arg-type]


class UncalibratedCurrency(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            "Devise non étalonnée : impossible de comparer un montant en euros aux valeurs brutes "
            "de la sauvegarde. Étalonnez la devise (Paramètres → Devise) avec la valeur affichée "
            "en jeu d'un joueur."
        )


def format_amount(value: float, symbol: str = "€") -> str:
    a = abs(value)
    if a >= 1_000_000:
        txt = f"{value / 1_000_000:.1f} M"
    elif a >= 1_000:
        txt = f"{value / 1_000:.0f} k"
    else:
        txt = f"{value:.0f} "
    return f"{txt.replace('.', ',')}{symbol}".replace(" M", " M").replace(" k", " k")


def calibrate(raw_value: int, displayed_value: float, symbol: str, reference: str) -> CurrencyCalibration:
    if raw_value <= 0 or displayed_value <= 0:
        raise ValueError("Les deux montants doivent être strictement positifs.")
    return CurrencyCalibration(symbol=symbol, factor=displayed_value / raw_value, reference=reference)

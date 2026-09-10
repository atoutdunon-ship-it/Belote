"""Point d'entree unique du moteur : transforme une saisie brute en score."""

from __future__ import annotations

from typing import Any, Mapping

from .classique import ClassiqueDeal, score_classique
from .coinche import CoincheDeal, score_coinche
from .rules import (
    ClassiqueRules,
    CoincheRules,
    DealScore,
    Declaration,
    GameType,
    Multiplier,
    RuleError,
    Side,
    TrumpMode,
)


def _side(value: Any) -> Side | None:
    if value in (None, "", "AUCUN"):
        return None
    try:
        return Side(str(value).upper())
    except ValueError as exc:  # pragma: no cover - garde-fou de saisie
        raise RuleError(f"Camp inconnu : {value!r}.") from exc


def _declarations(value: Any) -> tuple[Declaration, ...]:
    if not value:
        return ()
    try:
        return tuple(Declaration(str(v).upper()) for v in value)
    except ValueError as exc:
        raise RuleError(f"Annonce inconnue dans {value!r}.") from exc


def _trump(value: Any) -> TrumpMode:
    try:
        return TrumpMode(str(value or "ATOUT").upper())
    except ValueError as exc:
        raise RuleError(f"Mode d'atout inconnu : {value!r}.") from exc


def score_deal(
    game_type: GameType | str,
    payload: Mapping[str, Any],
    *,
    carry_in: int = 0,
    classique_rules: ClassiqueRules | None = None,
    coinche_rules: CoincheRules | None = None,
) -> DealScore:
    """Calcule le score d'une donne a partir de la saisie du capitaine de table.

    `payload` attend les cles : `taker`, `points_ns`, `points_ew`, et selon le
    jeu `contract`, `trump`, `multiplier`, `belote`, `capot`, `generale`,
    `declarations_ns`, `declarations_ew`.
    """
    game_type = GameType(str(game_type).upper())
    taker = _side(payload.get("taker"))
    if taker is None:
        raise RuleError("Le preneur doit etre renseigne.")

    try:
        points_ns = int(payload.get("points_ns", 0))
        points_ew = int(payload.get("points_ew", 0))
    except (TypeError, ValueError) as exc:
        raise RuleError("Les points doivent etre des entiers.") from exc

    common = {
        "taker": taker,
        "points_ns": points_ns,
        "points_ew": points_ew,
        "trump": _trump(payload.get("trump")),
        "belote": _side(payload.get("belote")),
        "capot": _side(payload.get("capot")),
        "declarations_ns": _declarations(payload.get("declarations_ns")),
        "declarations_ew": _declarations(payload.get("declarations_ew")),
    }

    if game_type is GameType.CLASSIQUE:
        return score_classique(ClassiqueDeal(carry_in=carry_in, **common), classique_rules)

    contract = payload.get("contract")
    if contract is None:
        raise RuleError("Le contrat annonce doit etre renseigne en coinche.")
    try:
        multiplier = Multiplier(int(payload.get("multiplier", 1)))
    except ValueError as exc:
        raise RuleError("Multiplicateur invalide (1 = simple, 2 = contre, 4 = surcontre).") from exc

    return score_coinche(
        CoincheDeal(
            contract=int(contract),
            multiplier=multiplier,
            generale=bool(payload.get("generale", False)),
            **common,
        ),
        coinche_rules,
    )

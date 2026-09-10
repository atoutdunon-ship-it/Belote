"""Calcul d'une donne de belote coinchee.

Reglement retenu par defaut :

* contrat annonce de 80 a 180 par pas de 10, plus Capot (252) et Generale (500) ;
* prise a la couleur, sans-atout (130 points) ou tout-atout (258 points), les
  points realises etant ramenes sur la base 162 pour comparer au contrat ;
* contrat reussi : le preneur marque la valeur du contrat, ses annonces et sa
  belote ; la defense ne marque que son eventuelle belote ;
* contrat chute : le preneur marque 0 (sa belote lui reste acquise) et la
  defense marque les points de plis, ses annonces et sa belote ;
* contre : tous les points attribues a la donne sont doubles ; surcontre : ils
  sont quadruples.
* capot / generale : le contrat n'est rempli que si le preneur realise
  effectivement les huit plis.
"""

from __future__ import annotations

from dataclasses import dataclass

from .rules import (
    BELOTE,
    CONTRACT_CAPOT,
    CONTRACT_GENERALE,
    CONTRACT_MIN,
    CONTRACT_STEP,
    CoincheRules,
    DealScore,
    Declaration,
    Multiplier,
    RuleError,
    Side,
    TOTAL_POINTS,
    TrumpMode,
    declarations_total,
    normalize_points,
)


@dataclass(frozen=True, slots=True)
class CoincheDeal:
    """Saisie d'une donne de coinche."""

    taker: Side
    contract: int
    points_ns: int
    points_ew: int
    trump: TrumpMode = TrumpMode.ATOUT
    multiplier: Multiplier = Multiplier.SIMPLE
    belote: Side | None = None
    capot: Side | None = None
    generale: bool = False
    declarations_ns: tuple[Declaration, ...] = ()
    declarations_ew: tuple[Declaration, ...] = ()

    def points(self, side: Side) -> int:
        return self.points_ns if side is Side.NS else self.points_ew

    def declarations(self, side: Side) -> tuple[Declaration, ...]:
        return self.declarations_ns if side is Side.NS else self.declarations_ew


def _check(deal: CoincheDeal, rules: CoincheRules) -> None:
    valid = set(range(CONTRACT_MIN, rules.contrat_max + 1, CONTRACT_STEP))
    valid |= {CONTRACT_CAPOT, CONTRACT_GENERALE}
    if deal.contract not in valid:
        raise RuleError(f"Contrat invalide : {deal.contract}.")
    if deal.points_ns < 0 or deal.points_ew < 0:
        raise RuleError("Les points de plis ne peuvent pas etre negatifs.")

    total = TOTAL_POINTS[deal.trump]
    if deal.capot is not None:
        if deal.points(deal.capot) != total or deal.points(deal.capot.other) != 0:
            raise RuleError(f"Capot annonce pour {deal.capot} : ce camp doit totaliser {total}.")
    elif deal.points_ns + deal.points_ew != total:
        raise RuleError(
            f"La somme des points doit valoir {total} "
            f"(saisi : {deal.points_ns} + {deal.points_ew})."
        )
    if deal.generale and deal.capot is None:
        raise RuleError("Une generale suppose la realisation des huit plis.")


def score_coinche(deal: CoincheDeal, rules: CoincheRules | None = None) -> DealScore:
    rules = rules or CoincheRules()
    _check(deal, rules)

    defense = deal.taker.other
    mult = int(deal.multiplier)

    def annonces(side: Side) -> int:
        return declarations_total(deal.declarations(side)) if rules.annonces_actives else 0

    def belote_of(side: Side) -> int:
        return BELOTE if deal.belote is side else 0

    realise_taker = (
        normalize_points(deal.points(deal.taker), deal.trump, rules.normaliser_sur_162)
        + annonces(deal.taker)
        + belote_of(deal.taker)
    )
    realise_defense = (
        normalize_points(deal.points(defense), deal.trump, rules.normaliser_sur_162)
        + annonces(defense)
        + belote_of(defense)
    )

    if deal.contract == CONTRACT_GENERALE:
        reussi = deal.generale and deal.capot is deal.taker
        valeur = rules.generale_points
    elif deal.contract == CONTRACT_CAPOT:
        reussi = deal.capot is deal.taker
        valeur = rules.capot_points
    else:
        reussi = realise_taker >= deal.contract
        valeur = deal.contract

    scores = {Side.NS: 0, Side.EW: 0}

    if reussi:
        issue = "CONTRAT_REUSSI"
        base = valeur
        if rules.variante == "CONTRAT_PLUS_REALISE" and deal.contract < CONTRACT_CAPOT:
            base += realise_taker
        scores[deal.taker] = (
            base + annonces(deal.taker) + belote_of(deal.taker)
        ) * mult
        # Le contrat reussi ne rapporte qu'au preneur. Une belote / rebelote
        # reste toutefois la securite de 20 points de son detenteur.
        scores[defense] = belote_of(defense) * mult
    else:
        issue = "CHUTE"
        # Le preneur chute ne marque pas son contrat. La defense recoit les
        # points de plis effectivement realises, avec ses annonces et belote.
        scores[defense] = (
            deal.points(defense) + annonces(defense) + belote_of(defense)
        ) * mult
        scores[deal.taker] = belote_of(deal.taker) * mult if rules.belote_acquise else 0

    return DealScore(
        ns=scores[Side.NS],
        ew=scores[Side.EW],
        carry=0,
        detail={
            "jeu": "COINCHE",
            "issue": issue,
            "preneur": deal.taker.value,
            "contrat": deal.contract,
            "atout": deal.trump.value,
            "multiplicateur": mult,
            "realise_preneur": realise_taker,
            "realise_defense": realise_defense,
        },
    )

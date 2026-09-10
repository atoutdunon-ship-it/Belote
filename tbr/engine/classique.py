"""Calcul d'une donne de belote classique (prise a la couleur).

Reglement retenu par defaut :

* 162 points par donne (152 points de cartes + 10 de der) ;
* le preneur remporte le contrat s'il totalise strictement plus que la defense ;
* egalite 81-81 : litige, la defense marque ses 81 points, ceux du preneur sont
  reportes sur la donne suivante au benefice du camp qui la remporte ;
* preneur dedans : 0 pour lui (la belote lui reste acquise), 162 pour la defense ;
* capot : 252 points pour le camp qui realise les huit plis.
"""

from __future__ import annotations

from dataclasses import dataclass

from .rules import (
    BELOTE,
    ClassiqueRules,
    DealScore,
    Declaration,
    RuleError,
    Side,
    TOTAL_POINTS,
    TrumpMode,
    declarations_total,
)


@dataclass(frozen=True, slots=True)
class ClassiqueDeal:
    """Saisie d'une donne de belote classique."""

    taker: Side
    points_ns: int
    points_ew: int
    trump: TrumpMode = TrumpMode.ATOUT
    belote: Side | None = None
    capot: Side | None = None
    declarations_ns: tuple[Declaration, ...] = ()
    declarations_ew: tuple[Declaration, ...] = ()
    #: Points en attente issus d'un litige sur la donne precedente.
    carry_in: int = 0

    def points(self, side: Side) -> int:
        return self.points_ns if side is Side.NS else self.points_ew

    def declarations(self, side: Side) -> tuple[Declaration, ...]:
        return self.declarations_ns if side is Side.NS else self.declarations_ew


def score_classique(deal: ClassiqueDeal, rules: ClassiqueRules | None = None) -> DealScore:
    rules = rules or ClassiqueRules()
    total = TOTAL_POINTS[deal.trump]

    if deal.points_ns < 0 or deal.points_ew < 0:
        raise RuleError("Les points de plis ne peuvent pas etre negatifs.")

    if deal.capot is not None:
        expected = {deal.capot: total, deal.capot.other: 0}
        if deal.points(deal.capot) != expected[deal.capot] or deal.points(deal.capot.other) != 0:
            raise RuleError(
                f"Capot annonce pour {deal.capot} : ce camp doit totaliser {total} points."
            )
    elif deal.points_ns + deal.points_ew != total:
        raise RuleError(
            f"La somme des points doit valoir {total} "
            f"(saisi : {deal.points_ns} + {deal.points_ew})."
        )

    defense = deal.taker.other

    def annonces(side: Side) -> int:
        return declarations_total(deal.declarations(side)) if rules.annonces_actives else 0

    def belote_of(side: Side) -> int:
        return BELOTE if deal.belote is side else 0

    def brut(side: Side) -> int:
        return deal.points(side) + annonces(side) + belote_of(side)

    scores = {Side.NS: 0, Side.EW: 0}
    carry_out = 0
    issue: str

    if deal.capot is not None:
        winner = deal.capot
        scores[winner] = rules.capot_points + annonces(winner) + belote_of(winner)
        scores[winner.other] = belote_of(winner.other) if rules.belote_acquise else 0
        issue = "CAPOT_PRENEUR" if winner is deal.taker else "CAPOT_DEFENSE"
        scores[winner] += deal.carry_in
    else:
        brut_taker, brut_defense = brut(deal.taker), brut(defense)
        if brut_taker > brut_defense:
            issue = "CONTRAT_REUSSI"
            scores[deal.taker] = brut_taker + deal.carry_in
            scores[defense] = brut_defense
        elif brut_taker < brut_defense:
            issue = "DEDANS"
            scores[defense] = (
                rules.dedans_points + annonces(defense) + belote_of(defense) + deal.carry_in
            )
            scores[deal.taker] = belote_of(deal.taker) if rules.belote_acquise else 0
        elif rules.litige_actif:
            issue = "LITIGE"
            scores[defense] = brut_defense
            scores[deal.taker] = belote_of(deal.taker) if rules.belote_acquise else 0
            carry_out = brut_taker + deal.carry_in
        else:  # egalite sans regle de litige : le preneur est dedans
            issue = "DEDANS"
            scores[defense] = rules.dedans_points + annonces(defense) + belote_of(defense)
            scores[deal.taker] = belote_of(deal.taker) if rules.belote_acquise else 0

    return DealScore(
        ns=scores[Side.NS],
        ew=scores[Side.EW],
        carry=carry_out,
        detail={
            "jeu": "CLASSIQUE",
            "issue": issue,
            "preneur": deal.taker.value,
            "atout": deal.trump.value,
            "brut_ns": brut(Side.NS),
            "brut_ew": brut(Side.EW),
            "carry_in": deal.carry_in,
        },
    )

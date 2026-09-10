"""Vocabulaire et constantes du jeu de belote.

Toutes les valeurs susceptibles de varier d'un club a l'autre sont regroupees ici
ou dans les dataclasses de configuration `ClassiqueRules` / `CoincheRules`, de
maniere a pouvoir adapter l'application a un reglement local sans toucher au
moteur de calcul.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum

# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #


class GameType(StrEnum):
    CLASSIQUE = "CLASSIQUE"
    COINCHE = "COINCHE"


class TournamentFormat(StrEnum):
    EQUIPES_FIXES = "EQUIPES_FIXES"
    MELEE = "MELEE"


class PairingMethod(StrEnum):
    """Strategie d'appariement d'une manche a l'autre."""

    SUISSE = "SUISSE"        # regroupe les joueurs de niveau proche (par score)
    ALEATOIRE = "ALEATOIRE"  # tirage au sort, toujours anti-repetition


class Side(StrEnum):
    """Les deux camps d'une table. NS = equipe 1, EW = equipe 2."""

    NS = "NS"
    EW = "EW"

    @property
    def other(self) -> "Side":
        return Side.EW if self is Side.NS else Side.NS


class TrumpMode(StrEnum):
    ATOUT = "ATOUT"              # prise a la couleur
    SANS_ATOUT = "SANS_ATOUT"
    TOUT_ATOUT = "TOUT_ATOUT"


class Multiplier(IntEnum):
    SIMPLE = 1
    CONTRE = 2
    SURCONTRE = 4


class Declaration(StrEnum):
    """Annonces de cartes (optionnelles, activables par tournoi)."""

    TIERCE = "TIERCE"
    CINQUANTE = "CINQUANTE"
    CENT = "CENT"
    CARRE_SIMPLE = "CARRE_SIMPLE"   # carre d'as, de 10, de rois ou de dames
    CARRE_NEUFS = "CARRE_NEUFS"
    CARRE_VALETS = "CARRE_VALETS"


DECLARATION_VALUES: dict[Declaration, int] = {
    Declaration.TIERCE: 20,
    Declaration.CINQUANTE: 50,
    Declaration.CENT: 100,
    Declaration.CARRE_SIMPLE: 100,
    Declaration.CARRE_NEUFS: 150,
    Declaration.CARRE_VALETS: 200,
}

# --------------------------------------------------------------------------- #
# Constantes de comptage
# --------------------------------------------------------------------------- #

DIX_DE_DER = 10
BELOTE = 20

#: Points de cartes disponibles selon le mode, dix de der inclus.
TOTAL_POINTS: dict[TrumpMode, int] = {
    TrumpMode.ATOUT: 162,        # 152 + 10
    TrumpMode.SANS_ATOUT: 130,   # 120 + 10
    TrumpMode.TOUT_ATOUT: 258,   # 248 + 10
}

BASE_POINTS = TOTAL_POINTS[TrumpMode.ATOUT]

#: Bonus de capot en belote classique : 162 + 90 = 252.
CAPOT_BONUS = 90
CAPOT_TOTAL_CLASSIQUE = BASE_POINTS + CAPOT_BONUS

#: Valeurs de contrat en coinche. Le capot coinché et le capot classique
#: valent tous deux 252 points (voir CAPOT_TOTAL_CLASSIQUE ci-dessus).
CONTRACT_MIN = 80
CONTRACT_MAX = 180
CONTRACT_STEP = 10
CONTRACT_CAPOT = 252
CONTRACT_GENERALE = 500

VALID_CONTRACTS: tuple[int, ...] = tuple(
    range(CONTRACT_MIN, CONTRACT_MAX + 1, CONTRACT_STEP)
) + (CONTRACT_CAPOT, CONTRACT_GENERALE)


# --------------------------------------------------------------------------- #
# Configuration des reglements
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ClassiqueRules:
    """Reglement de la belote classique (prise a la couleur)."""

    #: La belote reste acquise au preneur meme lorsqu'il est dedans.
    belote_acquise: bool = True
    #: Points marques par le camp qui realise un capot.
    capot_points: int = CAPOT_TOTAL_CLASSIQUE
    #: Le camp dedans donne l'integralite des points a l'adversaire.
    dedans_points: int = BASE_POINTS
    #: Gestion du litige (81-81) : les points du preneur sont reportes.
    litige_actif: bool = True
    #: Annonces de cartes comptabilisees.
    annonces_actives: bool = False


@dataclass(frozen=True, slots=True)
class CoincheRules:
    """Reglement de la belote coinchee."""

    #: Ramene les points realises sur la base 162 en SA / TA.
    normaliser_sur_162: bool = True
    #: CONTRAT : le preneur marque la valeur du contrat.
    #: CONTRAT_PLUS_REALISE : il marque le contrat + les points realises.
    variante: str = "CONTRAT"
    #: La belote est toujours acquise a son detenteur.
    belote_acquise: bool = True
    capot_points: int = CONTRACT_CAPOT
    generale_points: int = CONTRACT_GENERALE
    annonces_actives: bool = True
    #: Contrat maximum annoncable hors capot / generale.
    contrat_max: int = CONTRACT_MAX


@dataclass(frozen=True, slots=True)
class TiebreakRules:
    """Departage du classement, applique dans l'ordre des champs."""

    par_capots_reussis: bool = True
    par_meilleure_manche: bool = True
    par_capots_subis: bool = True


# --------------------------------------------------------------------------- #
# Structures partagees
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class DealScore:
    """Resultat chiffre d'une donne."""

    ns: int
    ew: int
    #: Points mis en attente par un litige, a reporter sur la donne suivante.
    carry: int = 0
    detail: dict[str, object] = field(default_factory=dict)

    def for_side(self, side: Side) -> int:
        return self.ns if side is Side.NS else self.ew


class RuleError(ValueError):
    """Saisie incoherente avec le reglement."""


def declarations_total(items: tuple[Declaration, ...] | list[Declaration]) -> int:
    return sum(DECLARATION_VALUES[d] for d in items)


def normalize_points(points: int, trump: TrumpMode, enabled: bool = True) -> int:
    """Ramene des points de cartes sur la base 162 points."""
    if not enabled or trump is TrumpMode.ATOUT:
        return points
    return round(points * BASE_POINTS / TOTAL_POINTS[trump])

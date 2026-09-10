"""Constitution des tables d'une manche.

Deux strategies :

* `MELEE`  : les joueurs changent de partenaire a chaque manche. L'appariement
  minimise les repetitions (avoir deja joue avec, puis avoir deja joue contre).
* `EQUIPES_FIXES` : les paires restent soudees, seules les oppositions changent.

Dans les deux cas l'ordre d'entree determine la philosophie du tirage :
classement decroissant pour un systeme suisse, ordre melange pour un tirage
aleatoire. L'anti-repetition s'applique toujours.
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from itertools import combinations
from typing import Iterable, Sequence

from .rules import RuleError

#: Poids relatifs des repetitions dans la fonction de cout.
POIDS_PARTENAIRE = 10
POIDS_ADVERSAIRE = 3
#: Taille de la fenetre de recherche autour du joueur courant.
FENETRE = 12


@dataclass(slots=True)
class PairingHistory:
    """Memoire des rencontres deja jouees dans le tournoi."""

    partners: Counter = field(default_factory=Counter)
    opponents: Counter = field(default_factory=Counter)

    @staticmethod
    def _key(a: int, b: int) -> tuple[int, int]:
        return (a, b) if a < b else (b, a)

    def add_table(self, ns: Sequence[int], ew: Sequence[int]) -> None:
        self.partners[self._key(*ns)] += 1
        self.partners[self._key(*ew)] += 1
        for a in ns:
            for b in ew:
                self.opponents[self._key(a, b)] += 1

    def partner_count(self, a: int, b: int) -> int:
        return self.partners[self._key(a, b)]

    def opponent_count(self, a: int, b: int) -> int:
        return self.opponents[self._key(a, b)]


@dataclass(frozen=True, slots=True)
class TableAssignment:
    table_number: int
    ns: tuple[int, int]
    ew: tuple[int, int]
    captain: int

    @property
    def players(self) -> tuple[int, int, int, int]:
        return (*self.ns, *self.ew)


_SPLITS = ((0, 1, 2, 3), (0, 2, 1, 3), (0, 3, 1, 2))


def _best_split(group: Sequence[int], history: PairingHistory) -> tuple[int, tuple, tuple]:
    """Retourne (cout, ns, ew) pour le meilleur decoupage d'un groupe de 4."""
    best: tuple[int, tuple, tuple] | None = None
    for i, j, k, m in _SPLITS:
        ns = (group[i], group[j])
        ew = (group[k], group[m])
        cost = POIDS_PARTENAIRE * (
            history.partner_count(*ns) + history.partner_count(*ew)
        ) + POIDS_ADVERSAIRE * sum(
            history.opponent_count(a, b) for a in ns for b in ew
        )
        if best is None or cost < best[0]:
            best = (cost, ns, ew)
    assert best is not None
    return best


def melee_tables(
    players: Sequence[int],
    history: PairingHistory | None = None,
    *,
    rng: random.Random | None = None,
    start_number: int = 1,
) -> list[TableAssignment]:
    """Compose les tables d'une manche en melee tournante."""
    if len(players) % 4 != 0 or not players:
        raise RuleError("Le nombre de joueurs doit etre un multiple de 4, superieur a 0.")
    history = history or PairingHistory()
    rng = rng or random.Random()

    remaining = list(players)
    tables: list[TableAssignment] = []
    number = start_number

    while remaining:
        head = remaining.pop(0)
        pool = remaining[:FENETRE]
        best_key: tuple[int, float] | None = None
        ns: tuple[int, int] = ()  # type: ignore[assignment]
        ew: tuple[int, int] = ()  # type: ignore[assignment]
        for trio in combinations(pool, 3):
            cost, cand_ns, cand_ew = _best_split((head, *trio), history)
            # Departage aleatoire leger pour eviter un tirage toujours identique.
            key = (cost, rng.random())
            if best_key is None or key < best_key:
                best_key, ns, ew = key, cand_ns, cand_ew
        if best_key is None:
            raise RuleError("Effectif insuffisant pour composer une table.")
        for p in (*ns, *ew):
            if p != head:
                remaining.remove(p)
        history.add_table(ns, ew)
        tables.append(TableAssignment(number, ns, ew, captain=ns[0]))
        number += 1

    return tables


def fixed_team_tables(
    teams: Sequence[tuple[int, tuple[int, int]]],
    history: PairingHistory | None = None,
    *,
    rng: random.Random | None = None,
    start_number: int = 1,
) -> list[TableAssignment]:
    """Compose les tables a partir d'equipes fixes `(team_id, (joueur_a, joueur_b))`."""
    if len(teams) % 2 != 0 or not teams:
        raise RuleError("Le nombre d'equipes doit etre pair, superieur a 0.")
    history = history or PairingHistory()
    rng = rng or random.Random()

    remaining = list(teams)
    tables: list[TableAssignment] = []
    number = start_number

    while remaining:
        _, ns = remaining.pop(0)
        best_key: tuple[int, float] | None = None
        best_idx = 0
        for idx, (_, candidate) in enumerate(remaining[:FENETRE]):
            cost = POIDS_ADVERSAIRE * sum(
                history.opponent_count(a, b) for a in ns for b in candidate
            )
            key = (cost, rng.random())
            if best_key is None or key < best_key:
                best_key, best_idx = key, idx
        _, ew = remaining.pop(best_idx)
        history.add_table(ns, ew)
        tables.append(TableAssignment(number, ns, ew, captain=ns[0]))
        number += 1

    return tables


def check_player_count(n: int) -> None:
    if n <= 0 or n % 4 != 0:
        raise RuleError(
            f"Le nombre de participants doit etre un multiple de 4 (recu : {n})."
        )


def rebuild_history(tables: Iterable[tuple[Sequence[int], Sequence[int]]]) -> PairingHistory:
    history = PairingHistory()
    for ns, ew in tables:
        history.add_table(ns, ew)
    return history

"""Calcul du classement individuel et par equipe.

Regle retenue : cumul des points sur l'ensemble des manches, departage par le
nombre de capots reussis, puis par la meilleure manche, puis par le nombre de
capots subis (le moins possible).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

from .rules import Side, TiebreakRules


@dataclass(frozen=True, slots=True)
class DealEntry:
    """Resultat d'une donne, tel qu'il alimente le classement."""

    round_index: int
    table_number: int
    deal_index: int
    ns: tuple[int, int]
    ew: tuple[int, int]
    score_ns: int
    score_ew: int
    capot: Side | None = None

    def players(self, side: Side) -> tuple[int, int]:
        return self.ns if side is Side.NS else self.ew

    def score(self, side: Side) -> int:
        return self.score_ns if side is Side.NS else self.score_ew


@dataclass(slots=True)
class PlayerStanding:
    player_id: int
    total: int = 0
    per_round: dict[int, int] = field(default_factory=dict)
    capots_reussis: int = 0
    capots_subis: int = 0
    donnes_jouees: int = 0
    rank: int = 0

    @property
    def meilleure_manche(self) -> int:
        return max(self.per_round.values(), default=0)

    def as_dict(self) -> dict:
        return {
            "player_id": self.player_id,
            "rank": self.rank,
            "total": self.total,
            "per_round": dict(sorted(self.per_round.items())),
            "meilleure_manche": self.meilleure_manche,
            "capots_reussis": self.capots_reussis,
            "capots_subis": self.capots_subis,
            "donnes_jouees": self.donnes_jouees,
        }


def _sort_key(s: PlayerStanding, tb: TiebreakRules) -> tuple:
    key: list[int] = [-s.total]
    if tb.par_capots_reussis:
        key.append(-s.capots_reussis)
    if tb.par_meilleure_manche:
        key.append(-s.meilleure_manche)
    if tb.par_capots_subis:
        key.append(s.capots_subis)
    return tuple(key)


def compute_standings(
    entries: Iterable[DealEntry],
    participants: Sequence[int] | None = None,
    tiebreak: TiebreakRules | None = None,
) -> list[PlayerStanding]:
    """Agrege les donnes en classement individuel, du premier au dernier."""
    tb = tiebreak or TiebreakRules()
    table: dict[int, PlayerStanding] = {p: PlayerStanding(p) for p in (participants or ())}

    for entry in entries:
        for side in (Side.NS, Side.EW):
            score = entry.score(side)
            for player in entry.players(side):
                st = table.setdefault(player, PlayerStanding(player))
                st.total += score
                st.per_round[entry.round_index] = st.per_round.get(entry.round_index, 0) + score
                st.donnes_jouees += 1
                if entry.capot is side:
                    st.capots_reussis += 1
                elif entry.capot is side.other:
                    st.capots_subis += 1

    ranked = sorted(table.values(), key=lambda s: (_sort_key(s, tb), s.player_id))
    previous_key = None
    previous_rank = 0
    for position, standing in enumerate(ranked, start=1):
        key = _sort_key(standing, tb)
        if key == previous_key:
            standing.rank = previous_rank  # ex aequo
        else:
            standing.rank = position
            previous_key, previous_rank = key, position
    return ranked


def compute_team_standings(
    entries: Iterable[DealEntry],
    teams: dict[int, tuple[int, int]],
    tiebreak: TiebreakRules | None = None,
) -> list[dict]:
    """Classement par equipe, pour les tournois en equipes fixes."""
    individual = {s.player_id: s for s in compute_standings(entries, tiebreak=tiebreak)}
    rows: list[dict] = []
    for team_id, members in teams.items():
        member = individual.get(members[0])
        if member is None:
            rows.append(
                {"team_id": team_id, "players": list(members), "total": 0,
                 "capots_reussis": 0, "capots_subis": 0, "per_round": {}}
            )
            continue
        rows.append(
            {
                "team_id": team_id,
                "players": list(members),
                "total": member.total,
                "capots_reussis": member.capots_reussis,
                "capots_subis": member.capots_subis,
                "per_round": dict(sorted(member.per_round.items())),
            }
        )
    rows.sort(key=lambda r: (-r["total"], -r["capots_reussis"], r["capots_subis"], r["team_id"]))
    for position, row in enumerate(rows, start=1):
        row["rank"] = position
    return rows

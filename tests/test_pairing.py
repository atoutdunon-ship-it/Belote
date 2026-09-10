import random

import pytest

from tbr.engine import (
    PairingHistory,
    RuleError,
    check_player_count,
    fixed_team_tables,
    melee_tables,
)


def test_effectif_multiple_de_quatre():
    check_player_count(16)
    with pytest.raises(RuleError):
        check_player_count(14)


def test_melee_couvre_tous_les_joueurs_sans_doublon():
    joueurs = list(range(1, 21))
    tables = melee_tables(joueurs, rng=random.Random(1))
    assert len(tables) == 5
    vus = [p for t in tables for p in t.players]
    assert sorted(vus) == joueurs
    assert [t.table_number for t in tables] == [1, 2, 3, 4, 5]
    assert all(t.captain in t.ns for t in tables)


def test_melee_evite_de_rejouer_avec_les_memes_partenaires():
    joueurs = list(range(1, 25))
    history = PairingHistory()
    rng = random.Random(7)
    for _ in range(4):
        for t in melee_tables(joueurs, history, rng=rng):
            pass
    # Sur 4 manches a 24 joueurs, aucun binome ne doit se repeter.
    assert max(history.partners.values()) == 1


def test_melee_refuse_un_effectif_invalide():
    with pytest.raises(RuleError):
        melee_tables([1, 2, 3])


def test_equipes_fixes():
    equipes = [(i, (2 * i - 1, 2 * i)) for i in range(1, 9)]
    history = PairingHistory()
    tables = fixed_team_tables(equipes, history, rng=random.Random(3))
    assert len(tables) == 4
    for t in tables:
        assert set(t.ns) in [set(m) for _, m in equipes]
        assert set(t.ew) in [set(m) for _, m in equipes]
    assert max(history.partners.values()) == 1

from tbr.engine import DealEntry, Side, TiebreakRules, compute_standings


def entry(round_index, ns, ew, s_ns, s_ew, capot=None, deal_index=1):
    return DealEntry(
        round_index=round_index,
        table_number=1,
        deal_index=deal_index,
        ns=ns,
        ew=ew,
        score_ns=s_ns,
        score_ew=s_ew,
        capot=capot,
    )


def test_cumul_par_joueur_et_par_manche():
    entries = [
        entry(1, (1, 2), (3, 4), 100, 62),
        entry(1, (1, 2), (3, 4), 90, 72, deal_index=2),
        entry(2, (1, 3), (2, 4), 120, 42),
    ]
    rows = {s.player_id: s for s in compute_standings(entries)}
    assert rows[1].total == 100 + 90 + 120
    assert rows[1].per_round == {1: 190, 2: 120}
    assert rows[2].total == 100 + 90 + 42
    assert rows[1].rank == 1


def test_capots_comptes_par_joueur():
    entries = [entry(1, (1, 2), (3, 4), 252, 0, capot=Side.NS)]
    rows = {s.player_id: s for s in compute_standings(entries)}
    assert rows[1].capots_reussis == 1 and rows[1].capots_subis == 0
    assert rows[3].capots_subis == 1 and rows[3].capots_reussis == 0


def test_departage_par_capots():
    entries = [
        entry(1, (1, 2), (3, 4), 252, 0, capot=Side.NS),
        entry(2, (3, 4), (1, 2), 252, 0),  # meme total pour 3 et 4, sans capot
    ]
    rows = compute_standings(entries, participants=[1, 2, 3, 4])
    par_joueur = {s.player_id: s for s in rows}
    assert par_joueur[1].total == par_joueur[3].total == 252
    assert par_joueur[1].rank < par_joueur[3].rank


def test_ex_aequo_partagent_le_rang():
    entries = [entry(1, (1, 2), (3, 4), 81, 81)]
    rows = compute_standings(entries, participants=[1, 2, 3, 4])
    assert {s.rank for s in rows} == {1}


def test_departage_desactivable():
    entries = [
        entry(1, (1, 2), (3, 4), 252, 0, capot=Side.NS),
        entry(2, (3, 4), (1, 2), 252, 0),
    ]
    rows = compute_standings(
        entries,
        participants=[1, 2, 3, 4],
        tiebreak=TiebreakRules(False, False, False),
    )
    assert {s.rank for s in rows} == {1}


def test_participants_sans_donne_apparaissent():
    rows = compute_standings([], participants=[7, 8])
    assert [s.player_id for s in rows] == [7, 8]
    assert all(s.total == 0 for s in rows)

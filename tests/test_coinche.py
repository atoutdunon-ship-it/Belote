import pytest

from tbr.engine import (
    CoincheDeal,
    CoincheRules,
    Multiplier,
    RuleError,
    Side,
    TrumpMode,
    score_coinche,
)


def deal(**kw):
    base = dict(taker=Side.NS, contract=100, points_ns=110, points_ew=52)
    base.update(kw)
    return CoincheDeal(**base)


def test_contrat_reussi_ne_marque_que_pour_le_preneur():
    s = score_coinche(deal())
    assert (s.ns, s.ew) == (100, 0)
    assert s.detail["issue"] == "CONTRAT_REUSSI"


def test_contrat_chute_donne_les_points_de_plis_a_la_defense():
    s = score_coinche(deal(points_ns=90, points_ew=72, contract=100))
    assert (s.ns, s.ew) == (0, 72)
    assert s.detail["issue"] == "CHUTE"


def test_contre_double_le_contrat_du_preneur():
    s = score_coinche(deal(multiplier=Multiplier.CONTRE))
    assert (s.ns, s.ew) == (200, 0)


def test_contre_double_aussi_la_belote_du_preneur():
    s = score_coinche(deal(multiplier=Multiplier.CONTRE, belote=Side.NS))
    assert (s.ns, s.ew) == ((100 + 20) * 2, 0)


def test_contre_multiplie_les_points_de_defense_sur_chute():
    s = score_coinche(deal(points_ns=80, points_ew=82, multiplier=Multiplier.CONTRE))
    assert (s.ns, s.ew) == (0, 82 * 2)


def test_contre_double_la_belote_du_preneur_meme_sil_chute():
    s = score_coinche(
        deal(points_ns=70, points_ew=92, contract=100, multiplier=Multiplier.CONTRE, belote=Side.NS)
    )
    assert (s.ns, s.ew) == (20 * 2, 92 * 2)


def test_surcontre():
    s = score_coinche(deal(multiplier=Multiplier.SURCONTRE))
    assert (s.ns, s.ew) == (400, 0)


def test_surcontre_quadruple_aussi_la_belote():
    s = score_coinche(deal(multiplier=Multiplier.SURCONTRE, belote=Side.NS))
    assert (s.ns, s.ew) == ((100 + 20) * 4, 0)


def test_belote_aide_a_realiser_le_contrat_et_ajoute_vingt_points():
    s = score_coinche(deal(points_ns=90, points_ew=72, contract=100, belote=Side.NS))
    assert s.detail["realise_preneur"] == 110
    assert (s.ns, s.ew) == (120, 0)


def test_belote_rebelote_securise_vingt_points_en_cas_de_chute():
    s = score_coinche(deal(points_ns=60, points_ew=102, contract=100, belote=Side.NS))
    assert (s.ns, s.ew) == (20, 102)


def test_belote_rebelote_de_la_defense_est_conservee_si_contrat_reussi():
    s = score_coinche(deal(belote=Side.EW))
    assert (s.ns, s.ew) == (100, 20)


def test_capot_annonce_reussi_vaut_252_points():
    s = score_coinche(deal(contract=252, points_ns=162, points_ew=0, capot=Side.NS))
    assert (s.ns, s.ew) == (252, 0)


def test_capot_annonce_manque_donne_les_points_a_la_defense():
    s = score_coinche(deal(contract=252, points_ns=150, points_ew=12))
    assert (s.ns, s.ew) == (0, 12)


def test_generale():
    s = score_coinche(
        deal(contract=500, points_ns=162, points_ew=0, capot=Side.NS, generale=True)
    )
    assert (s.ns, s.ew) == (500, 0)


def test_sans_atout_normalise_sur_162_pour_la_validation_du_contrat():
    # 100 points sur 130 disponibles => 125 sur la base 162.
    s = score_coinche(
        deal(contract=120, trump=TrumpMode.SANS_ATOUT, points_ns=100, points_ew=30)
    )
    assert s.detail["realise_preneur"] == 125
    assert (s.ns, s.ew) == (120, 0)


def test_variante_contrat_plus_realise():
    s = score_coinche(deal(), CoincheRules(variante="CONTRAT_PLUS_REALISE"))
    assert (s.ns, s.ew) == (100 + 110, 0)


def test_contrat_invalide():
    with pytest.raises(RuleError):
        score_coinche(deal(contract=95))


def test_somme_incoherente():
    with pytest.raises(RuleError):
        score_coinche(deal(points_ns=100, points_ew=100))

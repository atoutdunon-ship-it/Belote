from tbr.engine import ClassiqueDeal, ClassiqueRules, RuleError, Side, score_classique
import pytest


def deal(**kw):
    base = dict(taker=Side.NS, points_ns=100, points_ew=62)
    base.update(kw)
    return ClassiqueDeal(**base)


def test_contrat_reussi():
    s = score_classique(deal())
    assert (s.ns, s.ew) == (100, 62)
    assert s.detail["issue"] == "CONTRAT_REUSSI"


def test_belote_compte_dans_la_comparaison():
    # 80 contre 82 : la belote fait basculer le preneur au-dessus.
    s = score_classique(deal(points_ns=80, points_ew=82, belote=Side.NS))
    assert (s.ns, s.ew) == (100, 82)
    assert s.detail["issue"] == "CONTRAT_REUSSI"


def test_dedans():
    s = score_classique(deal(points_ns=60, points_ew=102))
    assert (s.ns, s.ew) == (0, 162)
    assert s.detail["issue"] == "DEDANS"


def test_dedans_belote_acquise():
    s = score_classique(deal(points_ns=60, points_ew=102, belote=Side.NS))
    assert (s.ns, s.ew) == (20, 162)


def test_litige_reporte_sur_la_donne_suivante():
    s = score_classique(deal(points_ns=81, points_ew=81))
    assert s.detail["issue"] == "LITIGE"
    assert (s.ns, s.ew) == (0, 81)
    assert s.carry == 81

    suivante = score_classique(deal(points_ns=100, points_ew=62, carry_in=s.carry))
    assert suivante.ns == 181


def test_capot():
    s = score_classique(deal(points_ns=162, points_ew=0, capot=Side.NS))
    assert (s.ns, s.ew) == (252, 0)
    assert s.detail["issue"] == "CAPOT_PRENEUR"


def test_capot_de_la_defense():
    s = score_classique(deal(points_ns=0, points_ew=162, capot=Side.EW))
    assert (s.ns, s.ew) == (0, 252)
    assert s.detail["issue"] == "CAPOT_DEFENSE"


def test_annonces_desactivees_par_defaut():
    from tbr.engine.rules import Declaration

    s = score_classique(deal(points_ns=100, points_ew=62, declarations_ns=(Declaration.CENT,)))
    assert s.ns == 100
    s2 = score_classique(
        deal(points_ns=100, points_ew=62, declarations_ns=(Declaration.CENT,)),
        ClassiqueRules(annonces_actives=True),
    )
    assert s2.ns == 200


def test_somme_incoherente_rejetee():
    with pytest.raises(RuleError):
        score_classique(deal(points_ns=100, points_ew=100))

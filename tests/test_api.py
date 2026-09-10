"""Parcours complet : creation, inscriptions, manches, saisie, cloisonnement."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tbr.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def auth(client, numero: int, pin: str) -> dict[str, str]:
    r = client.post("/api/auth/login", json={"numero": numero, "pin": pin})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def admin(client):
    return auth(client, 1, "1234")


@pytest.fixture(scope="module")
def tournoi(client, admin):
    r = client.post(
        "/api/tournaments",
        headers=admin,
        json={
            "nom": "Tournoi test",
            "game_type": "CLASSIQUE",
            "format": "MELEE",
            "nb_joueurs": 8,
            "nb_manches": 2,
            "donnes_par_manche": 2,
        },
    )
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    for i in range(8):
        rr = client.post(
            f"/api/tournaments/{tid}/registrations",
            headers=admin,
            json={"nom": f"Joueur {i + 1}"},
        )
        assert rr.status_code == 201, rr.text
    return tid


def test_effectif_non_multiple_de_quatre_refuse(client, admin):
    r = client.post(
        "/api/tournaments",
        headers=admin,
        json={"nom": "KO", "nb_joueurs": 6, "nb_manches": 1},
    )
    assert r.status_code == 422


def test_login_invalide(client):
    assert client.post("/api/auth/login", json={"numero": 1, "pin": "0000"}).status_code == 401


def test_parcours_complet(client, admin, tournoi):
    inscrits = client.get(f"/api/tournaments/{tournoi}/registrations", headers=admin).json()
    assert len(inscrits) == 8

    r = client.post(f"/api/tournaments/{tournoi}/start", headers=admin)
    assert r.status_code == 200, r.text
    manche = r.json()
    assert len(manche["tables"]) == 2

    # Le capitaine de la table 1 saisit les deux donnes.
    table = manche["tables"][0]
    capitaine_id = table["captain_id"]
    numero = next(
        j["dossard"] for j in table["ns"] + table["ew"] if j["id"] == capitaine_id
    )
    assert numero  # le capitaine possede bien un numero de joueur

    for index, (ns, ew) in enumerate([(100, 62), (81, 81)], start=1):
        rr = client.post(
            f"/api/tables/{table['id']}/deals",
            headers=admin,
            json={"index": index, "taker": "NS", "points_ns": ns, "points_ew": ew},
        )
        assert rr.status_code == 200, rr.text

    body = rr.json()
    assert body["total_ns"] == 100  # litige : les 81 du preneur sont en attente
    assert body["total_ew"] == 62 + 81
    assert body["donnes"][1]["carry"] == 81

    # Manche incomplete : la cloture est refusee.
    ko = client.post(f"/api/tournaments/{tournoi}/rounds/1/close", headers=admin)
    assert ko.status_code == 400

    table2 = manche["tables"][1]
    for index in (1, 2):
        client.post(
            f"/api/tables/{table2['id']}/deals",
            headers=admin,
            json={"index": index, "taker": "EW", "points_ns": 62, "points_ew": 100},
        )
    ok = client.post(f"/api/tournaments/{tournoi}/rounds/1/close", headers=admin)
    assert ok.status_code == 200

    r2 = client.post(f"/api/tournaments/{tournoi}/rounds", headers=admin)
    assert r2.status_code == 200
    assert r2.json()["index"] == 2

    classement = client.get(f"/api/tournaments/{tournoi}/standings", headers=admin).json()
    assert len(classement["joueurs"]) == 8
    assert classement["joueurs"][0]["rank"] == 1
    assert sum(j["total"] for j in classement["joueurs"]) > 0


def test_cloisonnement_des_scores(client, admin, tournoi):
    inscrits = client.get(f"/api/tournaments/{tournoi}/registrations", headers=admin).json()
    joueur = inscrits[0]
    # PIN par defaut attribue a la creation depuis l'ecran d'inscription.
    headers = auth(client, joueur["numero"], "0000")

    assert client.get(f"/api/tournaments/{tournoi}/standings", headers=headers).status_code == 403
    assert client.get(f"/api/tournaments/{tournoi}/rounds", headers=headers).status_code == 403
    assert client.get("/api/players", headers=headers).status_code == 403

    mine = client.get(f"/api/tournaments/{tournoi}/standings/me", headers=headers)
    assert mine.status_code == 200
    data = mine.json()
    assert data["classement"]["player_id"] == joueur["player_id"]
    assert "detail" in data

    table = client.get(f"/api/tournaments/{tournoi}/me/table", headers=headers)
    assert table.status_code == 200
    assert table.json()["mon_camp"] in ("NS", "EW")


def test_seul_le_capitaine_saisit(client, admin, tournoi):
    rounds = client.get(f"/api/tournaments/{tournoi}/rounds", headers=admin).json()
    table = rounds[-1]["tables"][0]
    non_capitaine = next(j for j in table["ns"] + table["ew"] if j["id"] != table["captain_id"])
    inscrits = client.get(f"/api/tournaments/{tournoi}/registrations", headers=admin).json()
    numero = next(i["numero"] for i in inscrits if i["player_id"] == non_capitaine["id"])
    headers = auth(client, numero, "0000")
    r = client.post(
        f"/api/tables/{table['id']}/deals",
        headers=headers,
        json={"index": 1, "taker": "NS", "points_ns": 100, "points_ew": 62},
    )
    assert r.status_code == 403


def test_saisie_incoherente_rejetee(client, admin, tournoi):
    rounds = client.get(f"/api/tournaments/{tournoi}/rounds", headers=admin).json()
    table = rounds[-1]["tables"][0]
    r = client.post(
        f"/api/tables/{table['id']}/deals",
        headers=admin,
        json={"index": 1, "taker": "NS", "points_ns": 100, "points_ew": 100},
    )
    assert r.status_code == 400
    assert "162" in r.json()["detail"]


def test_classement_publie_a_la_fin_du_tournoi(client, admin, tournoi):
    rounds = client.get(f"/api/tournaments/{tournoi}/rounds", headers=admin).json()
    derniere = rounds[-1]
    for table in derniere["tables"]:
        for index in (1, 2):
            rr = client.post(
                f"/api/tables/{table['id']}/deals",
                headers=admin,
                json={"index": index, "taker": "NS", "points_ns": 110, "points_ew": 52},
            )
            assert rr.status_code == 200, rr.text

    fin = client.post(
        f"/api/tournaments/{tournoi}/rounds/{derniere['index']}/close", headers=admin
    )
    assert fin.status_code == 200
    assert client.get(f"/api/tournaments/{tournoi}", headers=admin).json()["statut"] == "TERMINE"

    inscrits = client.get(f"/api/tournaments/{tournoi}/registrations", headers=admin).json()
    headers = auth(client, inscrits[0]["numero"], "0000")

    publie = client.get(f"/api/tournaments/{tournoi}/standings", headers=headers)
    assert publie.status_code == 200
    assert len(publie.json()["joueurs"]) == 8

    perso = client.get(f"/api/tournaments/{tournoi}/standings/me", headers=headers).json()
    assert perso["classement_publie"] is True

    # Les manches et la liste des joueurs restent reservees a l'administrateur.
    assert client.get(f"/api/tournaments/{tournoi}/rounds", headers=headers).status_code == 403
    assert client.get("/api/players", headers=headers).status_code == 403

"""Jeu de demonstration : `python -m tbr.seed`.

Cree 16 joueurs, un tournoi de coinche en melee (3 manches de 10 donnes) et
remplit la premiere manche de donnes tirees au hasard, de maniere a pouvoir
parcourir l'application immediatement.
"""

from __future__ import annotations

import random

from sqlalchemy import select

from .db import SessionLocal, init_db
from .engine import GameType, PairingMethod, Side, TournamentFormat
from .models import Player, Tournament, TournamentStatus
from .security import hash_pin
from . import services as svc

NOMS = [
    "Alice Dupont", "Bruno Marchand", "Carla Nunez", "David Legrand",
    "Elodie Perrin", "Fabien Roche", "Gisele Amar", "Hugo Vasseur",
    "Ines Pelletier", "Jean Morel", "Karine Bouvier", "Lucas Ferrand",
    "Maya Toussaint", "Nicolas Ravel", "Olivia Sanchez", "Pierre Garnier",
]


def random_deal(index: int, rng: random.Random) -> dict:
    taker = rng.choice(["NS", "EW"])
    if rng.random() < 0.06:
        capot = rng.choice(["NS", "EW"])
        pts_ns, pts_ew = (162, 0) if capot == "NS" else (0, 162)
        return {
            "index": index, "taker": taker, "points_ns": pts_ns, "points_ew": pts_ew,
            "trump": "ATOUT", "contract": 252 if taker == capot else 100,
            "multiplier": 1, "belote": None, "capot": capot, "generale": False,
            "declarations_ns": [], "declarations_ew": [],
        }
    pts_taker = rng.randint(40, 162)
    pts_ns = pts_taker if taker == "NS" else 162 - pts_taker
    return {
        "index": index,
        "taker": taker,
        "points_ns": pts_ns,
        "points_ew": 162 - pts_ns,
        "trump": "ATOUT",
        "contract": rng.choice([80, 90, 100, 110, 120, 130]),
        "multiplier": rng.choice([1, 1, 1, 2]),
        "belote": rng.choice([None, None, None, "NS", "EW"]),
        "capot": None,
        "generale": False,
        "declarations_ns": [],
        "declarations_ew": [],
    }


def main() -> None:
    rng = random.Random(20260910)
    init_db()
    with SessionLocal() as session:
        admin = session.execute(select(Player).where(Player.numero == 1)).scalar_one_or_none()
        if admin is None:
            admin = Player(numero=1, nom="Administrateur", pin_hash=hash_pin("1234"), is_admin=True)
            session.add(admin)
            session.flush()

        joueurs: list[Player] = []
        for i, nom in enumerate(NOMS, start=100):
            existing = session.execute(select(Player).where(Player.numero == i)).scalar_one_or_none()
            if existing is None:
                existing = Player(numero=i, nom=nom, pin_hash=hash_pin(f"{i % 10000:04d}"))
                session.add(existing)
                session.flush()
            joueurs.append(existing)

        tournament = Tournament(
            nom="Tournoi de demonstration",
            game_type=GameType.COINCHE.value,
            format=TournamentFormat.MELEE.value,
            pairing_method=PairingMethod.SUISSE.value,
            nb_joueurs=16,
            nb_manches=3,
            donnes_par_manche=10,
            annonces_actives=False,
            statut=TournamentStatus.BROUILLON,
            reglement={},
            created_by_id=admin.id,
        )
        session.add(tournament)
        session.flush()
        for p in joueurs:
            svc.register(session, tournament, p)

        rnd = svc.start_tournament(session, tournament)
        for table in rnd.tables:
            for index in range(1, tournament.donnes_par_manche + 1):
                svc.submit_deal(session, tournament, table, random_deal(index, rng), admin.id)
        svc.close_round(session, tournament, rnd)
        svc.create_round(session, tournament)
        session.commit()

        classement = svc.standings(session, tournament)
        print(f"Tournoi #{tournament.id} : {tournament.nom}")
        print(f"{'Rang':>4}  {'N°':>4}  {'Joueur':<22}{'Total':>7}{'Capots':>8}")
        for row in classement[:8]:
            print(
                f"{row['rank']:>4}  {row['dossard']:>4}  {row['nom']:<22}"
                f"{row['total']:>7}{row['capots_reussis']:>8}"
            )
        print("\nConnexion administrateur : numero 1 / PIN 1234")
        print("Connexion joueur : numero 100 a 115 / PIN = les 4 chiffres du numero (ex. 0100)")


if __name__ == "__main__":
    main()

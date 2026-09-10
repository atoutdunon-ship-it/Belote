"""Orchestration metier : tournois, manches, tables, donnes, classements."""

from __future__ import annotations

import random
from dataclasses import asdict
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .engine import (
    ClassiqueRules,
    CoincheRules,
    DealEntry,
    GameType,
    PairingHistory,
    PairingMethod,
    PlayerStanding,
    RuleError,
    Side,
    TiebreakRules,
    TournamentFormat,
    check_player_count,
    compute_standings,
    compute_team_standings,
    fixed_team_tables,
    melee_tables,
    score_deal,
)
from .models import (
    AuditLog,
    Deal,
    GameTable,
    Player,
    Registration,
    Round,
    RoundStatus,
    Team,
    Tournament,
    TournamentStatus,
)


class ServiceError(ValueError):
    """Erreur metier destinee a etre renvoyee telle quelle au client."""


# --------------------------------------------------------------------------- #
# Reglements
# --------------------------------------------------------------------------- #


def classique_rules(t: Tournament) -> ClassiqueRules:
    cfg = dict(t.reglement or {})
    return ClassiqueRules(
        belote_acquise=cfg.get("belote_acquise", True),
        capot_points=cfg.get("capot_points", 252),
        dedans_points=cfg.get("dedans_points", 162),
        litige_actif=cfg.get("litige_actif", True),
        annonces_actives=t.annonces_actives,
    )


def coinche_rules(t: Tournament) -> CoincheRules:
    cfg = dict(t.reglement or {})
    return CoincheRules(
        normaliser_sur_162=cfg.get("normaliser_sur_162", True),
        variante=cfg.get("variante", "CONTRAT"),
        belote_acquise=cfg.get("belote_acquise", True),
        capot_points=cfg.get("capot_points", 252),
        annonces_actives=t.annonces_actives,
        contrat_max=cfg.get("contrat_max", 180),
    )


def tiebreak_rules(t: Tournament) -> TiebreakRules:
    cfg = dict(t.reglement or {})
    return TiebreakRules(
        par_capots_reussis=cfg.get("departage_capots", True),
        par_meilleure_manche=cfg.get("departage_meilleure_manche", True),
        par_capots_subis=cfg.get("departage_capots_subis", True),
    )


# --------------------------------------------------------------------------- #
# Inscriptions
# --------------------------------------------------------------------------- #


def next_player_numero(session: Session) -> int:
    current = session.execute(select(Player.numero).order_by(Player.numero.desc())).scalars().first()
    return (current or 0) + 1


def register(
    session: Session,
    tournament: Tournament,
    player: Player,
    dossard: int | None = None,
    team_numero: int | None = None,
) -> Registration:
    if tournament.statut != TournamentStatus.BROUILLON:
        raise ServiceError("Les inscriptions sont closes : le tournoi a demarre.")
    existing = session.execute(
        select(Registration).where(
            Registration.tournament_id == tournament.id, Registration.player_id == player.id
        )
    ).scalar_one_or_none()
    if existing:
        raise ServiceError(f"{player.nom} est deja inscrit a ce tournoi.")

    count = session.execute(
        select(Registration).where(Registration.tournament_id == tournament.id)
    ).scalars().all()
    if len(count) >= tournament.nb_joueurs:
        raise ServiceError(
            f"Effectif complet : {tournament.nb_joueurs} participants annonces."
        )

    used = {r.dossard for r in count}
    if dossard is None:
        dossard = next(i for i in range(1, tournament.nb_joueurs + 1) if i not in used)
    elif dossard in used:
        raise ServiceError(f"Le numero de joueur {dossard} est deja attribue.")

    team: Team | None = None
    if tournament.format == TournamentFormat.EQUIPES_FIXES:
        numero = team_numero or ((dossard + 1) // 2)
        team = session.execute(
            select(Team).where(Team.tournament_id == tournament.id, Team.numero == numero)
        ).scalar_one_or_none()
        if team is None:
            team = Team(tournament_id=tournament.id, numero=numero, nom=f"Equipe {numero}")
            session.add(team)
            session.flush()
        elif len(team.members) >= 2:
            raise ServiceError(f"L'equipe {numero} est deja complete.")

    reg = Registration(
        tournament_id=tournament.id,
        player_id=player.id,
        dossard=dossard,
        team_id=team.id if team else None,
    )
    session.add(reg)
    session.flush()
    return reg


def registrations(session: Session, tournament_id: int) -> list[Registration]:
    stmt = (
        select(Registration)
        .where(Registration.tournament_id == tournament_id)
        .options(selectinload(Registration.player), selectinload(Registration.team))
        .order_by(Registration.dossard)
    )
    return list(session.execute(stmt).scalars())


# --------------------------------------------------------------------------- #
# Manches et tables
# --------------------------------------------------------------------------- #


def rounds_of(session: Session, tournament_id: int) -> list[Round]:
    """Manches lues en base : evite toute collection ORM devenue obsolete."""
    stmt = (
        select(Round)
        .where(Round.tournament_id == tournament_id)
        .options(selectinload(Round.tables).selectinload(GameTable.deals))
        .order_by(Round.index)
    )
    return list(session.execute(stmt).scalars())


def _history(session: Session, tournament_id: int) -> PairingHistory:
    history = PairingHistory()
    for table in _all_tables(session, tournament_id):
        history.add_table(table.ns, table.ew)
    return history


def _all_tables(session: Session, tournament_id: int) -> list[GameTable]:
    stmt = (
        select(GameTable)
        .join(Round)
        .where(Round.tournament_id == tournament_id)
        .options(selectinload(GameTable.deals))
        .order_by(Round.index, GameTable.numero)
    )
    return list(session.execute(stmt).scalars())


def _ordered_players(session: Session, tournament: Tournament) -> list[int]:
    regs = registrations(session, tournament.id)
    if tournament.pairing_method == PairingMethod.ALEATOIRE:
        ids = [r.player_id for r in regs]
        random.shuffle(ids)
        return ids
    standings = compute_standings(
        deal_entries(session, tournament.id),
        participants=[r.player_id for r in regs],
        tiebreak=tiebreak_rules(tournament),
    )
    return [s.player_id for s in standings]


def start_tournament(session: Session, tournament: Tournament) -> Round:
    if tournament.statut != TournamentStatus.BROUILLON:
        raise ServiceError("Ce tournoi a deja demarre.")
    regs = registrations(session, tournament.id)
    check_player_count(tournament.nb_joueurs)
    if len(regs) != tournament.nb_joueurs:
        raise ServiceError(
            f"{len(regs)} inscrits pour {tournament.nb_joueurs} annonces : "
            "completez l'effectif avant de lancer le tournoi."
        )
    if tournament.format == TournamentFormat.EQUIPES_FIXES:
        teams = {r.team_id for r in regs}
        if None in teams or len(teams) * 2 != len(regs):
            raise ServiceError("Toutes les equipes doivent compter exactement deux joueurs.")
        if len(teams) % 2 != 0:
            raise ServiceError("Le nombre d'equipes doit etre pair.")
    tournament.statut = TournamentStatus.EN_COURS
    session.flush()
    return create_round(session, tournament)


def create_round(session: Session, tournament: Tournament) -> Round:
    if tournament.statut == TournamentStatus.TERMINE:
        raise ServiceError("Ce tournoi est termine.")
    existing = rounds_of(session, tournament.id)
    if existing and existing[-1].statut != RoundStatus.CLOTUREE:
        raise ServiceError(
            f"La manche {existing[-1].index} doit etre cloturee avant d'en creer une nouvelle."
        )
    if len(existing) >= tournament.nb_manches:
        raise ServiceError(
            f"Le tournoi ne comporte que {tournament.nb_manches} manches."
        )

    index = len(existing) + 1
    rnd = Round(tournament_id=tournament.id, index=index)
    session.add(rnd)
    session.flush()

    history = _history(session, tournament.id)
    if tournament.format == TournamentFormat.EQUIPES_FIXES:
        regs = registrations(session, tournament.id)
        by_team: dict[int, list[int]] = {}
        for r in regs:
            by_team.setdefault(r.team_id, []).append(r.player_id)
        order = _team_order(session, tournament, by_team)
        assignments = fixed_team_tables(
            [(tid, (by_team[tid][0], by_team[tid][1])) for tid in order], history
        )
    else:
        assignments = melee_tables(_ordered_players(session, tournament), history)

    for a in assignments:
        session.add(
            GameTable(
                round_id=rnd.id,
                numero=a.table_number,
                ns_a_id=a.ns[0],
                ns_b_id=a.ns[1],
                ew_a_id=a.ew[0],
                ew_b_id=a.ew[1],
                captain_id=a.captain,
            )
        )
    session.flush()
    session.expire(tournament, ["rounds"])
    session.refresh(rnd)
    return rnd


def _team_order(session: Session, tournament: Tournament, by_team: dict[int, list[int]]) -> list[int]:
    if tournament.pairing_method == PairingMethod.ALEATOIRE:
        ids = list(by_team)
        random.shuffle(ids)
        return ids
    standings = {
        s.player_id: s.total
        for s in compute_standings(deal_entries(session, tournament.id))
    }
    return sorted(by_team, key=lambda tid: -sum(standings.get(p, 0) for p in by_team[tid]))


def close_round(session: Session, tournament: Tournament, rnd: Round) -> Round:
    attendu = tournament.donnes_par_manche
    incomplets = [t.numero for t in rnd.tables if len(t.deals) < attendu]
    if incomplets:
        raise ServiceError(
            "Manche incomplete : tables " + ", ".join(map(str, incomplets)) +
            f" (il faut {attendu} donnes par table)."
        )
    rnd.statut = RoundStatus.CLOTUREE
    if rnd.index >= tournament.nb_manches:
        tournament.statut = TournamentStatus.TERMINE
    session.flush()
    return rnd


# --------------------------------------------------------------------------- #
# Donnes
# --------------------------------------------------------------------------- #


def _rules_for(tournament: Tournament) -> dict[str, Any]:
    return {
        "classique_rules": classique_rules(tournament),
        "coinche_rules": coinche_rules(tournament),
    }


def recompute_table(session: Session, tournament: Tournament, table: GameTable) -> None:
    """Recalcule toute la table pour propager correctement les litiges."""
    rules = _rules_for(tournament)
    carry = 0
    for deal in sorted(table.deals, key=lambda d: d.index):
        result = score_deal(
            GameType(tournament.game_type), deal.saisie, carry_in=carry, **rules
        )
        deal.score_ns = result.ns
        deal.score_ew = result.ew
        deal.carry = result.carry
        deal.detail = dict(result.detail)
        deal.capot = deal.saisie.get("capot")
        carry = result.carry
    session.flush()


def submit_deal(
    session: Session,
    tournament: Tournament,
    table: GameTable,
    payload: dict[str, Any],
    author_id: int,
) -> Deal:
    if table.round.statut == RoundStatus.CLOTUREE:
        raise ServiceError("La manche est cloturee : la saisie est verrouillee.")
    index = int(payload["index"])
    if index > tournament.donnes_par_manche:
        raise ServiceError(
            f"Cette manche comporte {tournament.donnes_par_manche} donnes."
        )

    deal = next((d for d in table.deals if d.index == index), None)
    avant = _snapshot(deal) if deal else {}
    if deal is None:
        deal = Deal(table_id=table.id, index=index, saisi_par_id=author_id)
        session.add(deal)
        table.deals.append(deal)
    deal.saisie = dict(payload)
    deal.saisi_par_id = author_id
    session.flush()

    try:
        recompute_table(session, tournament, table)
    except RuleError as exc:
        session.rollback()
        raise ServiceError(str(exc)) from exc

    if avant:
        session.add(
            AuditLog(deal_id=deal.id, auteur_id=author_id, avant=avant, apres=_snapshot(deal))
        )
    session.flush()
    return deal


def _snapshot(deal: Deal | None) -> dict[str, Any]:
    if deal is None:
        return {}
    return {
        "saisie": dict(deal.saisie or {}),
        "score_ns": deal.score_ns,
        "score_ew": deal.score_ew,
    }


# --------------------------------------------------------------------------- #
# Classements
# --------------------------------------------------------------------------- #


def deal_entries(session: Session, tournament_id: int) -> list[DealEntry]:
    entries: list[DealEntry] = []
    stmt = (
        select(GameTable, Round.index)
        .join(Round, GameTable.round_id == Round.id)
        .where(Round.tournament_id == tournament_id)
        .options(selectinload(GameTable.deals))
        .order_by(Round.index, GameTable.numero)
    )
    for table, round_index in session.execute(stmt):
        for deal in table.deals:
            entries.append(
                DealEntry(
                    round_index=round_index,
                    table_number=table.numero,
                    deal_index=deal.index,
                    ns=table.ns,
                    ew=table.ew,
                    score_ns=deal.score_ns,
                    score_ew=deal.score_ew,
                    capot=Side(deal.capot) if deal.capot else None,
                )
            )
    return entries


def standings(session: Session, tournament: Tournament) -> list[dict[str, Any]]:
    regs = {r.player_id: r for r in registrations(session, tournament.id)}
    rows = compute_standings(
        deal_entries(session, tournament.id),
        participants=list(regs),
        tiebreak=tiebreak_rules(tournament),
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        reg = regs.get(row.player_id)
        data = row.as_dict()
        data["dossard"] = reg.dossard if reg else None
        data["nom"] = reg.player.nom if reg else None
        data["numero"] = reg.player.numero if reg else None
        out.append(data)
    return out


def team_standings(session: Session, tournament: Tournament) -> list[dict[str, Any]]:
    regs = registrations(session, tournament.id)
    by_team: dict[int, list[int]] = {}
    names: dict[int, str] = {}
    for r in regs:
        if r.team_id is None:
            continue
        by_team.setdefault(r.team_id, []).append(r.player_id)
        names[r.team_id] = r.team.nom if r.team else f"Equipe {r.team_id}"
    teams = {tid: (m[0], m[1]) for tid, m in by_team.items() if len(m) == 2}
    rows = compute_team_standings(
        deal_entries(session, tournament.id), teams, tiebreak_rules(tournament)
    )
    noms = {r.player_id: r.player.nom for r in regs}
    for row in rows:
        row["nom"] = names.get(row["team_id"], "")
        row["joueurs"] = [noms.get(p, "") for p in row["players"]]
    return rows


def player_standing(
    session: Session, tournament: Tournament, player_id: int
) -> dict[str, Any] | None:
    for row in standings(session, tournament):
        if row["player_id"] == player_id:
            row["participants"] = tournament.nb_joueurs
            return row
    return None


def player_history(session: Session, tournament: Tournament, player_id: int) -> list[dict[str, Any]]:
    """Detail des donnes d'un joueur : ses points, sans exposer ceux des autres."""
    result: list[dict[str, Any]] = []
    stmt = (
        select(GameTable, Round.index)
        .join(Round, GameTable.round_id == Round.id)
        .where(Round.tournament_id == tournament.id)
        .options(selectinload(GameTable.deals))
        .order_by(Round.index, GameTable.numero)
    )
    for table, round_index in session.execute(stmt):
        if player_id not in table.player_ids:
            continue
        side = Side.NS if player_id in table.ns else Side.EW
        partner = [p for p in (table.ns if side is Side.NS else table.ew) if p != player_id]
        result.append(
            {
                "manche": round_index,
                "table": table.numero,
                "camp": side.value,
                "partenaire_id": partner[0] if partner else None,
                "donnes": [
                    {
                        "index": d.index,
                        "points": d.score_ns if side is Side.NS else d.score_ew,
                        "points_adverses": d.score_ew if side is Side.NS else d.score_ns,
                        "issue": (d.detail or {}).get("issue"),
                        "capot": d.capot,
                    }
                    for d in sorted(table.deals, key=lambda x: x.index)
                ],
                "total": sum(
                    (d.score_ns if side is Side.NS else d.score_ew) for d in table.deals
                ),
            }
        )
    return result


def standing_to_dict(standing: PlayerStanding) -> dict[str, Any]:
    return standing.as_dict()


def tournament_summary(session: Session, t: Tournament) -> dict[str, Any]:
    inscrits = len(registrations(session, t.id))
    return {
        "id": t.id,
        "nom": t.nom,
        "game_type": t.game_type,
        "format": t.format,
        "pairing_method": t.pairing_method,
        "nb_joueurs": t.nb_joueurs,
        "nb_manches": t.nb_manches,
        "donnes_par_manche": t.donnes_par_manche,
        "annonces_actives": t.annonces_actives,
        "statut": t.statut,
        "inscrits": inscrits,
        "manches_jouees": len(rounds_of(session, t.id)),
    }


def serialize_table(session: Session, table: GameTable, tournament: Tournament) -> dict[str, Any]:
    noms = _player_names(session, table.player_ids)
    dossards = _dossards(session, tournament.id, table.player_ids)
    deals = sorted(table.deals, key=lambda d: d.index)
    return {
        "id": table.id,
        "numero": table.numero,
        "ns": [
            {"id": p, "nom": noms.get(p, ""), "dossard": dossards.get(p)} for p in table.ns
        ],
        "ew": [
            {"id": p, "nom": noms.get(p, ""), "dossard": dossards.get(p)} for p in table.ew
        ],
        "captain_id": table.captain_id,
        "total_ns": sum(d.score_ns for d in deals),
        "total_ew": sum(d.score_ew for d in deals),
        "donnes_attendues": tournament.donnes_par_manche,
        "donnes": [
            {
                "id": d.id,
                "index": d.index,
                "score_ns": d.score_ns,
                "score_ew": d.score_ew,
                "carry": d.carry,
                "capot": d.capot,
                "saisie": d.saisie,
                "detail": d.detail,
            }
            for d in deals
        ],
    }


def _player_names(session: Session, ids: Sequence[int]) -> dict[int, str]:
    rows = session.execute(select(Player.id, Player.nom).where(Player.id.in_(ids))).all()
    return {pid: nom for pid, nom in rows}


def _dossards(session: Session, tournament_id: int, ids: Sequence[int]) -> dict[int, int]:
    rows = session.execute(
        select(Registration.player_id, Registration.dossard).where(
            Registration.tournament_id == tournament_id, Registration.player_id.in_(ids)
        )
    ).all()
    return {pid: dossard for pid, dossard in rows}


__all__ = [name for name in dir() if not name.startswith("_")]

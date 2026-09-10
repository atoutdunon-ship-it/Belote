from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import or_, select

from ..engine import RuleError, TournamentFormat
from ..config import get_settings
from ..models import (
    GameTable,
    Player,
    Registration,
    Round,
    RoundStatus,
    Tournament,
    TournamentStatus,
)
from ..schemas import (
    AdminPasswordChangeIn,
    DealIn,
    LoginIn,
    PinChangeIn,
    PlayerIn,
    PlayerOut,
    RegistrationIn,
    TokenOut,
    TournamentIn,
)
from ..security import (
    AuthError,
    create_token,
    hash_password,
    hash_pin,
    validate_pin,
    verify_password,
    verify_pin,
)
from .. import services as svc
from .deps import AdminDep, PlayerDep, SessionDep, TournamentDep
from .ws import hub

api = APIRouter(prefix="/api")


def _boom(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# --------------------------------------------------------------------------- #
# Authentification
# --------------------------------------------------------------------------- #

auth = APIRouter(prefix="/auth", tags=["auth"])


@auth.post("/login", response_model=TokenOut)
def login(payload: LoginIn, session: SessionDep) -> TokenOut:
    if payload.identifiant is not None:
        settings = get_settings()
        player = session.execute(
            select(Player).where(Player.is_admin.is_(True), Player.nom == settings.admin_nom)
        ).scalar_one_or_none()
        authenticated = (
            payload.identifiant.casefold() == settings.admin_identifiant.casefold()
            and player is not None
            and player.actif
            and verify_password(payload.mot_de_passe or "", player.password_hash or "")
        )
    else:
        player = session.execute(
            select(Player).where(Player.numero == payload.numero)
        ).scalar_one_or_none()
        authenticated = (
            player is not None
            and not player.is_admin
            and player.actif
            and verify_pin(payload.pin or "", player.pin_hash)
        )
    if not authenticated or player is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Identifiants de connexion incorrects.")
    return TokenOut(
        access_token=create_token(player.id, player.numero, player.is_admin),
        player_id=player.id,
        numero=player.numero,
        nom=player.nom,
        is_admin=player.is_admin,
    )


@auth.get("/me", response_model=PlayerOut)
def me(player: PlayerDep) -> Player:
    return player


@auth.post("/pin", status_code=status.HTTP_204_NO_CONTENT)
def change_pin(payload: PinChangeIn, player: PlayerDep) -> Response:
    if player.is_admin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Utilisez la modification du mot de passe administrateur.",
        )
    if not verify_pin(payload.ancien_pin, player.pin_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Code PIN actuel incorrect.")
    try:
        player.pin_hash = hash_pin(payload.nouveau_pin)
    except AuthError as exc:
        raise _boom(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@auth.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_admin_password(payload: AdminPasswordChangeIn, player: PlayerDep) -> Response:
    if not player.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Reserve a l'administrateur.")
    if not verify_password(payload.ancien_mot_de_passe, player.password_hash or ""):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Mot de passe actuel incorrect.")
    try:
        player.password_hash = hash_password(payload.nouveau_mot_de_passe)
    except AuthError as exc:
        raise _boom(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- #
# Joueurs (administration)
# --------------------------------------------------------------------------- #

players = APIRouter(prefix="/players", tags=["joueurs"])


@players.get("", response_model=list[PlayerOut])
def list_players(session: SessionDep, _: AdminDep) -> list[Player]:
    return list(session.execute(select(Player).order_by(Player.numero)).scalars())


@players.post("", response_model=PlayerOut, status_code=status.HTTP_201_CREATED)
def create_player(payload: PlayerIn, session: SessionDep, _: AdminDep) -> Player:
    numero = payload.numero or svc.next_player_numero(session)
    if session.execute(select(Player).where(Player.numero == numero)).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, f"Le numero {numero} est deja utilise.")
    try:
        player = Player(
            numero=numero,
            nom=payload.nom.strip(),
            pin_hash=hash_pin(payload.pin),
            is_admin=payload.is_admin,
        )
    except AuthError as exc:
        raise _boom(exc) from exc
    session.add(player)
    session.flush()
    return player


@players.post("/{player_id}/pin", response_model=PlayerOut)
def reset_pin(player_id: int, payload: dict[str, str], session: SessionDep, _: AdminDep) -> Player:
    player = session.get(Player, player_id)
    if player is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Joueur introuvable.")
    try:
        player.pin_hash = hash_pin(validate_pin(payload.get("pin", "")))
    except AuthError as exc:
        raise _boom(exc) from exc
    return player


@players.delete("/{player_id}", response_model=PlayerOut)
def deactivate_player(player_id: int, session: SessionDep, admin: AdminDep) -> Player:
    player = session.get(Player, player_id)
    if player is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Joueur introuvable.")
    if player.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Impossible de se desactiver soi-meme.")
    player.actif = False
    return player


# --------------------------------------------------------------------------- #
# Tournois
# --------------------------------------------------------------------------- #

tournaments = APIRouter(prefix="/tournaments", tags=["tournois"])


@tournaments.get("")
def list_tournaments(session: SessionDep, player: PlayerDep) -> list[dict[str, Any]]:
    stmt = select(Tournament).order_by(Tournament.id.desc())
    if not player.is_admin:
        # Les joueurs connectes voient les inscriptions encore ouvertes pour
        # pouvoir rejoindre un tournoi, ainsi que leurs propres tournois.
        stmt = (
            stmt.outerjoin(
                Registration,
                (Registration.tournament_id == Tournament.id)
                & (Registration.player_id == player.id),
            )
            .where(
                or_(
                    Tournament.statut == TournamentStatus.BROUILLON,
                    Registration.player_id == player.id,
                )
            )
        )
    rows = list(session.execute(stmt).scalars())
    registered = {
        registration.tournament_id
        for registration in session.execute(
            select(Registration).where(Registration.player_id == player.id)
        ).scalars()
    }
    return [
        {**svc.tournament_summary(session, tournament), "est_inscrit": tournament.id in registered}
        for tournament in rows
    ]


@tournaments.post("", status_code=status.HTTP_201_CREATED)
def create_tournament(payload: TournamentIn, session: SessionDep, admin: AdminDep) -> dict[str, Any]:
    tournament = Tournament(
        nom=payload.nom.strip(),
        game_type=payload.game_type.value,
        format=payload.format.value,
        pairing_method=payload.pairing_method.value,
        nb_joueurs=payload.nb_joueurs,
        nb_manches=payload.nb_manches,
        donnes_par_manche=payload.donnes_par_manche,
        annonces_actives=payload.annonces_actives,
        reglement=payload.reglement,
        created_by_id=admin.id,
    )
    session.add(tournament)
    session.flush()
    return svc.tournament_summary(session, tournament)


@tournaments.get("/{tournament_id}")
def read_tournament(
    tournament: TournamentDep, session: SessionDep, _: PlayerDep
) -> dict[str, Any]:
    return svc.tournament_summary(session, tournament)


@tournaments.delete("/{tournament_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tournament(tournament: TournamentDep, session: SessionDep, _: AdminDep) -> Response:
    session.delete(tournament)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@tournaments.get("/{tournament_id}/registrations")
def list_registrations(
    tournament: TournamentDep, session: SessionDep, _: AdminDep
) -> list[dict[str, Any]]:
    return [
        {
            "id": r.id,
            "player_id": r.player_id,
            "numero": r.player.numero,
            "nom": r.player.nom,
            "dossard": r.dossard,
            "team_numero": r.team.numero if r.team else None,
            "team_nom": r.team.nom if r.team else None,
        }
        for r in svc.registrations(session, tournament.id)
    ]


@tournaments.post("/{tournament_id}/registrations", status_code=status.HTTP_201_CREATED)
def add_registration(
    payload: RegistrationIn, tournament: TournamentDep, session: SessionDep, _: AdminDep
) -> dict[str, Any]:
    player: Player | None = None
    if payload.player_id is not None:
        player = session.get(Player, payload.player_id)
    elif payload.numero is not None:
        player = session.execute(
            select(Player).where(Player.numero == payload.numero)
        ).scalar_one_or_none()
    if player is None and payload.nom:
        player = Player(
            numero=payload.numero or svc.next_player_numero(session),
            nom=payload.nom.strip(),
            pin_hash=hash_pin("0000"),
        )
        session.add(player)
        session.flush()
    if player is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Joueur introuvable.")
    try:
        reg = svc.register(session, tournament, player, payload.dossard, payload.team_numero)
    except svc.ServiceError as exc:
        raise _boom(exc) from exc
    return {
        "id": reg.id,
        "player_id": player.id,
        "numero": player.numero,
        "nom": player.nom,
        "dossard": reg.dossard,
        "team_numero": reg.team.numero if reg.team else None,
    }


@tournaments.post("/{tournament_id}/join", status_code=status.HTTP_201_CREATED)
def join_tournament(
    tournament: TournamentDep, session: SessionDep, player: PlayerDep
) -> dict[str, Any]:
    """Inscrit le joueur connecte a un tournoi dont les inscriptions sont ouvertes."""
    try:
        registration = svc.register(session, tournament, player)
    except svc.ServiceError as exc:
        raise _boom(exc) from exc
    return {
        "id": registration.id,
        "player_id": player.id,
        "numero": player.numero,
        "nom": player.nom,
        "dossard": registration.dossard,
        "team_numero": registration.team.numero if registration.team else None,
    }


@tournaments.delete(
    "/{tournament_id}/registrations/{registration_id}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_registration(
    registration_id: int, tournament: TournamentDep, session: SessionDep, _: AdminDep
) -> Response:
    reg = session.get(Registration, registration_id)
    if reg is None or reg.tournament_id != tournament.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Inscription introuvable.")
    if tournament.statut != TournamentStatus.BROUILLON:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Le tournoi a demarre.")
    session.delete(reg)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@tournaments.post("/{tournament_id}/start")
async def start(tournament: TournamentDep, session: SessionDep, _: AdminDep) -> dict[str, Any]:
    try:
        rnd = svc.start_tournament(session, tournament)
    except (svc.ServiceError, RuleError) as exc:
        raise _boom(exc) from exc
    session.commit()
    await hub.broadcast(tournament.id, "tournoi.demarre", {"manche": rnd.index})
    return _round_payload(session, tournament, rnd)


@tournaments.post("/{tournament_id}/rounds")
async def next_round(tournament: TournamentDep, session: SessionDep, _: AdminDep) -> dict[str, Any]:
    try:
        rnd = svc.create_round(session, tournament)
    except (svc.ServiceError, RuleError) as exc:
        raise _boom(exc) from exc
    session.commit()
    await hub.broadcast(tournament.id, "manche.creee", {"manche": rnd.index})
    return _round_payload(session, tournament, rnd)


@tournaments.get("/{tournament_id}/rounds")
def list_rounds(
    tournament: TournamentDep, session: SessionDep, _: AdminDep
) -> list[dict[str, Any]]:
    return [_round_payload(session, tournament, r) for r in tournament.rounds]


@tournaments.post("/{tournament_id}/rounds/{index}/close")
async def close_round(
    index: int, tournament: TournamentDep, session: SessionDep, _: AdminDep
) -> dict[str, Any]:
    rnd = next((r for r in tournament.rounds if r.index == index), None)
    if rnd is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Manche introuvable.")
    try:
        svc.close_round(session, tournament, rnd)
    except svc.ServiceError as exc:
        raise _boom(exc) from exc
    session.commit()
    await hub.broadcast(tournament.id, "manche.cloturee", {"manche": index})
    return _round_payload(session, tournament, rnd)


@tournaments.get("/{tournament_id}/standings")
def full_standings(
    tournament: TournamentDep, session: SessionDep, player: PlayerDep
) -> dict[str, Any]:
    """Classement complet : administrateur a tout moment, joueurs une fois le
    tournoi termine (la derniere manche cloturee publie le classement)."""
    if not player.is_admin:
        if tournament.statut != TournamentStatus.TERMINE:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Le classement complet est publie a la fin du tournoi.",
            )
        inscrit = session.execute(
            select(Registration).where(
                Registration.tournament_id == tournament.id,
                Registration.player_id == player.id,
            )
        ).scalar_one_or_none()
        if inscrit is None:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Vous n'etes pas inscrit a ce tournoi."
            )
    data: dict[str, Any] = {
        "tournoi": svc.tournament_summary(session, tournament),
        "joueurs": svc.standings(session, tournament),
    }
    if tournament.format == TournamentFormat.EQUIPES_FIXES:
        data["equipes"] = svc.team_standings(session, tournament)
    return data


@tournaments.get("/{tournament_id}/standings/me")
def my_standing(
    tournament: TournamentDep, session: SessionDep, player: PlayerDep
) -> dict[str, Any]:
    """Un joueur ne voit que sa propre ligne de classement."""
    row = svc.player_standing(session, tournament, player.id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vous n'etes pas inscrit a ce tournoi.")
    return {
        "tournoi": svc.tournament_summary(session, tournament),
        "classement": row,
        "detail": svc.player_history(session, tournament, player.id),
        "classement_publie": tournament.statut == TournamentStatus.TERMINE,
    }


@tournaments.get("/{tournament_id}/me/table")
def my_table(
    tournament: TournamentDep, session: SessionDep, player: PlayerDep
) -> dict[str, Any]:
    """Table en cours du joueur connecte, avec les donnes deja saisies."""
    rnd = next(
        (r for r in reversed(tournament.rounds) if r.statut == RoundStatus.EN_COURS), None
    )
    if rnd is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aucune manche en cours.")
    table = next((t for t in rnd.tables if player.id in t.player_ids), None)
    if table is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vous n'etes pas attable sur cette manche.")
    payload = svc.serialize_table(session, table, tournament)
    payload["manche"] = rnd.index
    payload["est_capitaine"] = table.captain_id == player.id or player.is_admin
    payload["mon_camp"] = "NS" if player.id in table.ns else "EW"
    return payload


api.include_router(auth)
api.include_router(players)
api.include_router(tournaments)


# --------------------------------------------------------------------------- #
# Tables et donnes
# --------------------------------------------------------------------------- #

tables = APIRouter(prefix="/tables", tags=["tables"])


def _load_table(session: SessionDep, table_id: int) -> GameTable:
    table = session.get(GameTable, table_id)
    if table is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Table introuvable.")
    return table


@tables.get("/{table_id}")
def read_table(table_id: int, session: SessionDep, player: PlayerDep) -> dict[str, Any]:
    table = _load_table(session, table_id)
    if not player.is_admin and player.id not in table.player_ids:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Table reservee a ses joueurs.")
    tournament = table.round.tournament
    payload = svc.serialize_table(session, table, tournament)
    payload["manche"] = table.round.index
    payload["est_capitaine"] = table.captain_id == player.id or player.is_admin
    return payload


@tables.post("/{table_id}/deals")
async def submit_deal(
    table_id: int, payload: DealIn, session: SessionDep, player: PlayerDep
) -> dict[str, Any]:
    table = _load_table(session, table_id)
    if not player.is_admin and player.id != table.captain_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Seuls le capitaine de table et l'administrateur peuvent saisir une donne.",
        )
    tournament = table.round.tournament
    try:
        svc.submit_deal(session, tournament, table, payload.model_dump(), player.id)
    except (svc.ServiceError, RuleError) as exc:
        raise _boom(exc) from exc
    session.commit()
    body = svc.serialize_table(session, table, tournament)
    await hub.broadcast(
        tournament.id,
        "donne.enregistree",
        {"table": table.numero, "manche": table.round.index, "index": payload.index},
    )
    return body


@tables.delete("/{table_id}/deals/{index}")
async def delete_deal(
    table_id: int, index: int, session: SessionDep, admin: AdminDep
) -> dict[str, Any]:
    table = _load_table(session, table_id)
    deal = next((d for d in table.deals if d.index == index), None)
    if deal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Donne introuvable.")
    if table.round.statut == RoundStatus.CLOTUREE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Manche cloturee.")
    table.deals.remove(deal)
    session.delete(deal)
    session.flush()
    tournament = table.round.tournament
    svc.recompute_table(session, tournament, table)
    session.commit()
    await hub.broadcast(tournament.id, "donne.supprimee", {"table": table.numero, "index": index})
    return svc.serialize_table(session, table, tournament)


api.include_router(tables)


def _round_payload(session, tournament: Tournament, rnd: Round) -> dict[str, Any]:
    return {
        "id": rnd.id,
        "index": rnd.index,
        "statut": rnd.statut,
        "tables": [svc.serialize_table(session, t, tournament) for t in rnd.tables],
    }

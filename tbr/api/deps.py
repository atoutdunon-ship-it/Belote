from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Player, Tournament
from ..security import AuthError, decode_token

bearer = HTTPBearer(auto_error=False)

SessionDep = Annotated[Session, Depends(get_session)]


def current_player(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)] = None,
) -> Player:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentification requise.")
    try:
        payload = decode_token(credentials.credentials)
    except AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    player = session.get(Player, int(payload["sub"]))
    if player is None or not player.actif:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Compte introuvable ou desactive.")
    return player


PlayerDep = Annotated[Player, Depends(current_player)]


def current_admin(player: PlayerDep) -> Player:
    if not player.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Reserve a l'administrateur.")
    return player


AdminDep = Annotated[Player, Depends(current_admin)]


def get_tournament(tournament_id: int, session: SessionDep) -> Tournament:
    tournament = session.get(Tournament, tournament_id)
    if tournament is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tournoi introuvable.")
    return tournament


TournamentDep = Annotated[Tournament, Depends(get_tournament)]

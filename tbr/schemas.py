from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .engine import GameType, PairingMethod, TournamentFormat


class LoginIn(BaseModel):
    numero: int
    pin: str


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    player_id: int
    numero: int
    nom: str
    is_admin: bool


class PinChangeIn(BaseModel):
    ancien_pin: str
    nouveau_pin: str


class PlayerIn(BaseModel):
    numero: int | None = Field(default=None, description="Attribue automatiquement si absent.")
    nom: str = Field(min_length=1, max_length=80)
    pin: str = "0000"
    is_admin: bool = False


class PlayerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    numero: int
    nom: str
    is_admin: bool
    actif: bool


class TournamentIn(BaseModel):
    nom: str = Field(min_length=1, max_length=120)
    game_type: GameType = GameType.CLASSIQUE
    format: TournamentFormat = TournamentFormat.MELEE
    pairing_method: PairingMethod = PairingMethod.SUISSE
    nb_joueurs: int = Field(ge=4, le=400)
    nb_manches: int = Field(default=3, ge=1, le=20)
    donnes_par_manche: int = Field(default=10, ge=1, le=30)
    annonces_actives: bool = False
    reglement: dict[str, Any] = Field(default_factory=dict)

    @field_validator("nb_joueurs")
    @classmethod
    def _multiple_de_quatre(cls, v: int) -> int:
        if v % 4 != 0:
            raise ValueError("Le nombre de participants doit etre un multiple de 4.")
        return v


class TournamentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nom: str
    game_type: str
    format: str
    pairing_method: str
    nb_joueurs: int
    nb_manches: int
    donnes_par_manche: int
    annonces_actives: bool
    statut: str
    inscrits: int = 0
    manches_jouees: int = 0


class RegistrationIn(BaseModel):
    player_id: int | None = None
    numero: int | None = None
    nom: str | None = None
    dossard: int | None = None
    team_numero: int | None = None


class RegistrationOut(BaseModel):
    id: int
    player_id: int
    numero: int
    nom: str
    dossard: int
    team_numero: int | None = None


class DealIn(BaseModel):
    index: int = Field(ge=1, le=30)
    taker: Literal["NS", "EW"]
    points_ns: int = Field(ge=0, le=300)
    points_ew: int = Field(ge=0, le=300)
    trump: Literal["ATOUT", "SANS_ATOUT", "TOUT_ATOUT"] = "ATOUT"
    contract: int | None = None
    multiplier: Literal[1, 2, 4] = 1
    belote: Literal["NS", "EW"] | None = None
    capot: Literal["NS", "EW"] | None = None
    generale: bool = False
    declarations_ns: list[str] = Field(default_factory=list)
    declarations_ew: list[str] = Field(default_factory=list)


class DealOut(BaseModel):
    id: int
    index: int
    score_ns: int
    score_ew: int
    carry: int
    capot: str | None
    saisie: dict[str, Any]
    detail: dict[str, Any]


class TableOut(BaseModel):
    id: int
    numero: int
    ns: list[dict[str, Any]]
    ew: list[dict[str, Any]]
    captain_id: int
    total_ns: int = 0
    total_ew: int = 0
    donnes: list[DealOut] = Field(default_factory=list)
    donnes_attendues: int = 10


class RoundOut(BaseModel):
    id: int
    index: int
    statut: str
    tables: list[TableOut] = Field(default_factory=list)


class StandingRow(BaseModel):
    rank: int
    player_id: int
    dossard: int | None = None
    nom: str | None = None
    total: int
    per_round: dict[int, int]
    meilleure_manche: int
    capots_reussis: int
    capots_subis: int
    donnes_jouees: int

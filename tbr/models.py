"""Modele de donnees (SQLAlchemy 2.0)."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TournamentStatus(StrEnum):
    BROUILLON = "BROUILLON"
    EN_COURS = "EN_COURS"
    TERMINE = "TERMINE"


class RoundStatus(StrEnum):
    EN_COURS = "EN_COURS"
    CLOTUREE = "CLOTUREE"


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    numero: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    nom: Mapped[str] = mapped_column(String(80))
    pin_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    registrations: Mapped[list["Registration"]] = relationship(
        back_populates="player", cascade="all, delete-orphan"
    )


class Tournament(Base):
    __tablename__ = "tournaments"

    id: Mapped[int] = mapped_column(primary_key=True)
    nom: Mapped[str] = mapped_column(String(120))
    game_type: Mapped[str] = mapped_column(String(20))
    format: Mapped[str] = mapped_column(String(20))
    pairing_method: Mapped[str] = mapped_column(String(20), default="SUISSE")
    nb_joueurs: Mapped[int] = mapped_column(Integer)
    nb_manches: Mapped[int] = mapped_column(Integer, default=3)
    donnes_par_manche: Mapped[int] = mapped_column(Integer, default=10)
    annonces_actives: Mapped[bool] = mapped_column(Boolean, default=False)
    statut: Mapped[str] = mapped_column(String(20), default=TournamentStatus.BROUILLON)
    reglement: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    registrations: Mapped[list["Registration"]] = relationship(
        back_populates="tournament", cascade="all, delete-orphan"
    )
    teams: Mapped[list["Team"]] = relationship(
        back_populates="tournament", cascade="all, delete-orphan"
    )
    rounds: Mapped[list["Round"]] = relationship(
        back_populates="tournament", cascade="all, delete-orphan", order_by="Round.index"
    )


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("tournament_id", "numero"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"))
    numero: Mapped[int] = mapped_column(Integer)
    nom: Mapped[str] = mapped_column(String(80), default="")

    tournament: Mapped[Tournament] = relationship(back_populates="teams")
    members: Mapped[list["Registration"]] = relationship(back_populates="team")


class Registration(Base):
    __tablename__ = "registrations"
    __table_args__ = (
        UniqueConstraint("tournament_id", "player_id"),
        UniqueConstraint("tournament_id", "dossard"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"))
    #: Numero de joueur attribue a l'inscription, propre au tournoi.
    dossard: Mapped[int] = mapped_column(Integer)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))

    tournament: Mapped[Tournament] = relationship(back_populates="registrations")
    player: Mapped[Player] = relationship(back_populates="registrations")
    team: Mapped[Team | None] = relationship(back_populates="members")


class Round(Base):
    __tablename__ = "rounds"
    __table_args__ = (UniqueConstraint("tournament_id", "index"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"))
    index: Mapped[int] = mapped_column(Integer)
    statut: Mapped[str] = mapped_column(String(20), default=RoundStatus.EN_COURS)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    tournament: Mapped[Tournament] = relationship(back_populates="rounds")
    tables: Mapped[list["GameTable"]] = relationship(
        back_populates="round", cascade="all, delete-orphan", order_by="GameTable.numero"
    )


class GameTable(Base):
    __tablename__ = "game_tables"
    __table_args__ = (UniqueConstraint("round_id", "numero"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("rounds.id", ondelete="CASCADE"))
    numero: Mapped[int] = mapped_column(Integer)
    ns_a_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    ns_b_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    ew_a_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    ew_b_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    captain_id: Mapped[int] = mapped_column(ForeignKey("players.id"))

    round: Mapped[Round] = relationship(back_populates="tables")
    deals: Mapped[list["Deal"]] = relationship(
        back_populates="table", cascade="all, delete-orphan", order_by="Deal.index"
    )

    @property
    def ns(self) -> tuple[int, int]:
        return (self.ns_a_id, self.ns_b_id)

    @property
    def ew(self) -> tuple[int, int]:
        return (self.ew_a_id, self.ew_b_id)

    @property
    def player_ids(self) -> tuple[int, int, int, int]:
        return (*self.ns, *self.ew)


class Deal(Base):
    __tablename__ = "deals"
    __table_args__ = (UniqueConstraint("table_id", "index"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("game_tables.id", ondelete="CASCADE"))
    index: Mapped[int] = mapped_column(Integer)
    saisie: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    score_ns: Mapped[int] = mapped_column(Integer, default=0)
    score_ew: Mapped[int] = mapped_column(Integer, default=0)
    carry: Mapped[int] = mapped_column(Integer, default=0)
    capot: Mapped[str | None] = mapped_column(String(2))
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    saisi_par_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    table: Mapped[GameTable] = relationship(back_populates="deals")


class AuditLog(Base):
    """Trace des corrections administratives sur une donne."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"))
    auteur_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"))
    avant: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    apres: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

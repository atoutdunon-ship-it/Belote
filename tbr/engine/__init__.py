"""Moteur metier de Team Belote & Re : regles, appariement, classement."""

from .classique import ClassiqueDeal, score_classique
from .coinche import CoincheDeal, score_coinche
from .pairing import (
    PairingHistory,
    TableAssignment,
    check_player_count,
    fixed_team_tables,
    melee_tables,
    rebuild_history,
)
from .rules import (
    ClassiqueRules,
    CoincheRules,
    DealScore,
    Declaration,
    GameType,
    Multiplier,
    PairingMethod,
    RuleError,
    Side,
    TiebreakRules,
    TournamentFormat,
    TrumpMode,
    VALID_CONTRACTS,
)
from .scoring import score_deal
from .standings import DealEntry, PlayerStanding, compute_standings, compute_team_standings

__all__ = [
    "ClassiqueDeal",
    "ClassiqueRules",
    "CoincheDeal",
    "CoincheRules",
    "DealEntry",
    "DealScore",
    "Declaration",
    "GameType",
    "Multiplier",
    "PairingHistory",
    "PairingMethod",
    "PlayerStanding",
    "RuleError",
    "Side",
    "TableAssignment",
    "TiebreakRules",
    "TournamentFormat",
    "TrumpMode",
    "VALID_CONTRACTS",
    "check_player_count",
    "compute_standings",
    "compute_team_standings",
    "fixed_team_tables",
    "melee_tables",
    "rebuild_history",
    "score_classique",
    "score_coinche",
    "score_deal",
]

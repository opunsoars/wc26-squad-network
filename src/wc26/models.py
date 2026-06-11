from __future__ import annotations

import datetime

from pydantic import BaseModel, model_validator


class Player(BaseModel):
    """A squad player resolved to a Transfermarkt ID."""

    name: str
    squad: str
    position: str
    club: str
    tm_id: str
    market_value_eur: int | None = None


class MatchLog(BaseModel):
    """One appearance for one player in one match."""

    player_tm_id: str
    match_id: str
    date: datetime.date
    competition: str
    team: str
    opponent: str
    minutes_played: int
    sub_on_minute: int | None = None
    sub_off_minute: int | None = None

    @property
    def on_minute(self) -> int:
        """Minute the player came on (0 if started)."""
        return self.sub_on_minute if self.sub_on_minute is not None else 0

    @property
    def off_minute(self) -> int:
        """Minute the player went off (90 if played to end, or sub_off_minute)."""
        return self.sub_off_minute if self.sub_off_minute is not None else 90

    @model_validator(mode="after")
    def _validate_interval(self) -> MatchLog:
        """Validate that on_minute is strictly less than off_minute."""
        if self.on_minute >= self.off_minute:
            raise ValueError(
                f"on_minute ({self.on_minute}) must be < off_minute ({self.off_minute})"
            )
        return self


class CoPlayEdge(BaseModel):
    """Weighted edge between two players in the same squad."""

    player_a_tm_id: str
    player_b_tm_id: str
    raw_shared_minutes: int
    weighted_shared_minutes: float


class SquadMetrics(BaseModel):
    """Aggregate network metrics for one squad."""

    squad: str
    density: float
    clustering: float
    avg_weighted_degree: float
    market_value_eur: int | None = None

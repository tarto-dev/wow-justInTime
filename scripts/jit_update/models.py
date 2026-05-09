"""Pydantic models for Raider.IO API responses."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AffixModifier(BaseModel):
    """A weekly modifier (affix) attached to a Mythic+ run."""

    model_config = ConfigDict(extra="ignore")

    id: int
    slug: str
    name: str | None = None


def affix_combo_slug(modifiers: list[AffixModifier]) -> str:
    """Return a deterministic slug joining affix slugs alphabetically with '-'.

    Used as the cell key in Data.lua: e.g. "fortified-xalataths-guile".
    """
    return "-".join(sorted(m.slug for m in modifiers))


class BossInfo(BaseModel):
    """Static info about a boss in a dungeon."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    slug: str
    name: str
    ordinal: int
    wow_encounter_id: int | None = Field(default=None, alias="wowEncounterId")


class Encounter(BaseModel):
    """A single boss encounter inside a logged run."""

    model_config = ConfigDict(extra="ignore")

    duration_ms: int
    is_success: bool
    approximate_relative_started_at: int
    approximate_relative_ended_at: int
    boss: BossInfo


class DungeonInfo(BaseModel):
    """Static info about a dungeon."""

    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    slug: str
    short_name: str = ""
    map_challenge_mode_id: int
    keystone_timer_ms: int
    num_bosses: int


class Run(BaseModel):
    """Top-level Mythic+ run as returned by /mythic-plus/runs."""

    model_config = ConfigDict(extra="ignore")

    keystone_run_id: int
    season: str
    status: str
    dungeon: DungeonInfo
    mythic_level: int
    clear_time_ms: int
    keystone_time_ms: int
    completed_at: datetime
    num_chests: int
    time_remaining_ms: int
    weekly_modifiers: list[AffixModifier] = Field(default_factory=list)

    @property
    def is_timed(self) -> bool:
        """True if the run finished within the keystone timer (chest count >= 1)."""
        return self.num_chests >= 1

    def affix_combo(self) -> str:
        """Return the alphabetically-sorted affix combo slug."""
        return affix_combo_slug(self.weekly_modifiers)


class _LoggedDetails(BaseModel):
    """Internal container for the encounters list inside RunDetails."""

    model_config = ConfigDict(extra="ignore")

    encounters: list[Encounter] = Field(default_factory=list)


class RunDetails(BaseModel):
    """Detailed run with per-boss encounter splits.

    Returned by /mythic-plus/run-details?id=X.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    keystone_run_id: int
    season: str
    mythic_level: int
    clear_time_ms: int
    keystone_time_ms: int
    num_chests: int
    time_remaining_ms: int
    weekly_modifiers: list[AffixModifier] = Field(default_factory=list)
    dungeon: DungeonInfo
    logged_details: _LoggedDetails = Field(default_factory=_LoggedDetails)

    @field_validator("logged_details", mode="before")
    @classmethod
    def _coerce_none_logged_details(cls, v: object) -> object:
        """Treat a null logged_details as an empty container (no encounters)."""
        if v is None:
            return _LoggedDetails()
        return v

    @property
    def encounters(self) -> list[Encounter]:
        """Return the list of boss encounters from the logged details."""
        return self.logged_details.encounters

    def boss_splits_ms(self) -> list[int | None]:
        """Return per-boss split times (relative ms), sorted by ordinal.

        Returns None for any boss whose encounter is not successful.
        Length = max ordinal + 1 (ordinals are 0-based in the Raider.IO API).
        """
        if not self.encounters:
            return []
        max_ordinal = max(e.boss.ordinal for e in self.encounters)
        result: list[int | None] = [None] * (max_ordinal + 1)
        for enc in self.encounters:
            idx = enc.boss.ordinal
            result[idx] = enc.approximate_relative_ended_at if enc.is_success else None
        return result


class ReferenceCell(BaseModel):
    """One cell of the reference table: (dungeon, level) -> splits.

    Schema v2 removes the per-affix-combo nesting that v1 had — the addon
    ignores the affix dimension in practice, so this cell sits directly
    under levels[L] in the rendered Data.lua. ``splits_source`` records
    how the boss splits were derived: real Raider.IO logged-encounter
    data, synthesized via observed ratios, or equidistant fallback.
    """

    model_config = ConfigDict(extra="ignore")

    sample_size: int
    clear_time_ms: int
    boss_splits_ms: list[int]
    splits_source: Literal["raiderio", "synthesized", "equidistant_fallback"]


class BlizzardMember(BaseModel):
    """A single character in a Blizzard mythic-keystone-leaderboard group."""

    model_config = ConfigDict(extra="ignore")

    profile: dict
    faction: dict | None = None
    specialization: dict | None = None


class BlizzardLeadingGroup(BaseModel):
    """One ranked group from /mythic-leaderboard/.../leading_groups."""

    model_config = ConfigDict(extra="ignore")

    ranking: int
    duration: int
    completed_timestamp: int
    keystone_level: int
    members: list[BlizzardMember] = Field(default_factory=list)
    mythic_rating: dict | None = None


class BlizzardLeaderboardResponse(BaseModel):
    """Full payload of a Blizzard mythic-keystone-leaderboard response."""

    model_config = ConfigDict(extra="ignore")

    period: int
    period_start_timestamp: int
    period_end_timestamp: int
    leading_groups: list[BlizzardLeadingGroup] = Field(default_factory=list)
    map_challenge_mode_id: int
    name: str


class BlizzardRun(BaseModel):
    """A normalized Mythic+ run discovered via Blizzard API.

    Decoupled from BlizzardLeadingGroup so the pipeline can carry the dungeon /
    region / realm / period context that the raw payload omits.
    """

    model_config = ConfigDict(extra="ignore")

    dungeon_slug: str
    region: str
    realm_id: int
    period: int
    keystone_level: int
    duration_ms: int
    completed_timestamp: int

    @classmethod
    def from_group(
        cls,
        group: "BlizzardLeadingGroup | dict",
        *,
        dungeon_slug: str,
        region: str,
        realm_id: int,
        period: int,
    ) -> "BlizzardRun":
        """Build a BlizzardRun from a leading_groups entry plus context."""
        if isinstance(group, dict):
            group = BlizzardLeadingGroup.model_validate(group)
        return cls(
            dungeon_slug=dungeon_slug,
            region=region,
            realm_id=realm_id,
            period=period,
            keystone_level=group.keystone_level,
            duration_ms=group.duration,
            completed_timestamp=group.completed_timestamp,
        )

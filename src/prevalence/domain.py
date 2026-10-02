"""Domain objects: priors, observations, and variants."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

PriorSource = Literal["SME", "data"]


class BetaPrior(BaseModel):
    """Beta(a, b) prior on a variant's prevalence, as raw parameters.

    ``source`` records where the prior came from (SME estimate or earlier data).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    a: float = Field(gt=0)
    b: float = Field(gt=0)
    source: PriorSource = "SME"

    @property
    def mean(self) -> float:
        return self.a / (self.a + self.b)


@dataclass(frozen=True)
class Observation:
    """``k`` cases with the variant out of ``n`` cases examined, in one stratum."""

    variant: str
    stratum: Optional[str]
    k: int
    n: int

    def __post_init__(self) -> None:
        if self.k < 0 or self.n < 0:
            raise ValueError(f"{self.variant}: k and n must be non-negative (k={self.k}, n={self.n})")
        if self.k > self.n:
            raise ValueError(f"{self.variant}: k ({self.k}) cannot exceed n ({self.n})")


@dataclass
class Variant:
    """A case variant with its resolved targets, prior, and observed counts.

    ``target_n`` and ``target_prob`` are already resolved: a per-variant override
    if one was configured, otherwise the run-level default. ``parent`` is metadata
    for rollups and grouping only; it does not affect the model.
    """

    name: str
    prior: BetaPrior
    target_n: int
    target_prob: float
    parent: Optional[str] = None
    observations: list[Observation] = field(default_factory=list)

    def add_observation(self, obs: Observation) -> None:
        if obs.variant != self.name:
            raise ValueError(f"Observation for '{obs.variant}' added to variant '{self.name}'")
        self.observations.append(obs)

    @property
    def has_data(self) -> bool:
        return any(o.n > 0 for o in self.observations)

    def total_counts(self) -> tuple[int, int]:
        """(k, n) summed across all strata and batches."""
        return (
            sum(o.k for o in self.observations),
            sum(o.n for o in self.observations),
        )

    def counts_by_stratum(self) -> dict[Optional[str], tuple[int, int]]:
        """(k, n) summed within each stratum."""
        totals: dict[Optional[str], tuple[int, int]] = {}
        for o in self.observations:
            k, n = totals.get(o.stratum, (0, 0))
            totals[o.stratum] = (k + o.k, n + o.n)
        return totals

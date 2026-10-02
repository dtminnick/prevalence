"""Abstract model interfaces.

The planner and reports depend only on these, so a PyMC-backed model can be
dropped in later without touching them.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

import numpy as np

from prevalence.domain import Variant


class Posterior(ABC):
    """Posterior belief about one variant's prevalence."""

    @abstractmethod
    def capture_probability(self, sample_size, target_n: int):
        """P(at least ``target_n`` occurrences in a sample of ``sample_size``).

        Accepts an int or an array of sample sizes and returns a float or array.
        """

    @abstractmethod
    def mean(self) -> float:
        """Posterior mean prevalence."""

    @abstractmethod
    def credible_interval(self, level: float = 0.9) -> tuple[float, float]:
        """Equal-tailed credible interval for prevalence."""


class PrevalenceModel(ABC):
    """Fits posteriors for a set of variants."""

    @abstractmethod
    def fit(self, variants: Sequence[Variant]) -> dict[str, Posterior]:
        """Return one posterior per variant name."""

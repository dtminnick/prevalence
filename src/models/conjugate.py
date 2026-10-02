"""Closed-form Beta-binomial model (v1)."""
from __future__ import annotations

from typing import Sequence

import numpy as np
from scipy.stats import beta, betabinom

from prevalence.domain import Variant
from prevalence.models.base import Posterior, PrevalenceModel


class BetaPosterior(Posterior):
    """Beta(a, b) posterior on prevalence.

    The number of occurrences X in a future sample of size S follows
    BetaBinomial(S, a, b), so P(X >= N) = betabinom.sf(N - 1, S, a, b).
    """

    def __init__(self, a: float, b: float) -> None:
        if a <= 0 or b <= 0:
            raise ValueError(f"Beta parameters must be positive (a={a}, b={b})")
        self.a = float(a)
        self.b = float(b)

    def capture_probability(self, sample_size, target_n: int):
        if target_n < 0:
            raise ValueError("target_n must be non-negative")
        sizes = np.asarray(sample_size)
        if np.any(sizes < 0):
            raise ValueError("sample_size must be non-negative")
        result = betabinom.sf(target_n - 1, sizes, self.a, self.b)
        return float(result) if np.ndim(result) == 0 else result

    def mean(self) -> float:
        return self.a / (self.a + self.b)

    def credible_interval(self, level: float = 0.9) -> tuple[float, float]:
        if not 0 < level < 1:
            raise ValueError("level must be between 0 and 1")
        tail = (1 - level) / 2
        return (
            float(beta.ppf(tail, self.a, self.b)),
            float(beta.ppf(1 - tail, self.a, self.b)),
        )

    def __repr__(self) -> str:
        return f"BetaPosterior(a={self.a}, b={self.b})"


class ConjugateBetaModel(PrevalenceModel):
    """Beta prior + counts (k of n) -> Beta(a + k, b + n - k) posterior.

    Counts are pooled across strata here; per-stratum and combined posteriors
    arrive with StratifiedPosterior (build step 4).
    """

    def fit(self, variants: Sequence[Variant]) -> dict[str, Posterior]:
        posteriors: dict[str, Posterior] = {}
        for variant in variants:
            k, n = variant.total_counts()
            posteriors[variant.name] = BetaPosterior(
                variant.prior.a + k,
                variant.prior.b + n - k,
            )
        return posteriors

import pytest
from pydantic import ValidationError

from prevalence.domain import BetaPrior, Observation, Variant


def test_prior_rejects_non_positive_parameters():
    with pytest.raises(ValidationError):
        BetaPrior(a=0, b=5)
    with pytest.raises(ValidationError):
        BetaPrior(a=1, b=-1)


def test_prior_rejects_unknown_source():
    with pytest.raises(ValidationError):
        BetaPrior(a=1, b=1, source="guess")


def test_prior_mean():
    assert BetaPrior(a=2, b=18).mean == pytest.approx(0.1)


def test_observation_validation():
    with pytest.raises(ValueError):
        Observation("v", "s", k=5, n=4)
    with pytest.raises(ValueError):
        Observation("v", "s", k=-1, n=4)


def make_variant():
    return Variant("NIGO", BetaPrior(a=2, b=18), target_n=20, target_prob=0.9)


def test_total_and_stratum_counts():
    v = make_variant()
    v.add_observation(Observation("NIGO", "401k", 38, 400))
    v.add_observation(Observation("NIGO", "403b", 12, 160))
    v.add_observation(Observation("NIGO", "401k", 2, 100))
    assert v.total_counts() == (52, 660)
    assert v.counts_by_stratum() == {"401k": (40, 500), "403b": (12, 160)}
    assert v.has_data


def test_variant_without_data():
    v = make_variant()
    assert not v.has_data
    assert v.total_counts() == (0, 0)


def test_add_observation_for_wrong_variant():
    with pytest.raises(ValueError):
        make_variant().add_observation(Observation("Other", None, 1, 2))

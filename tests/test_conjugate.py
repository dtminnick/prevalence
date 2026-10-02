import numpy as np
import pytest
from scipy.stats import beta

from prevalence.domain import BetaPrior, Observation, Variant
from prevalence.models import BetaPosterior, ConjugateBetaModel, ModelFactory


def test_posterior_update_arithmetic():
    v = Variant("NIGO", BetaPrior(a=2, b=18), target_n=20, target_prob=0.9)
    v.add_observation(Observation("NIGO", "401k", 38, 400))
    v.add_observation(Observation("NIGO", "403b", 12, 160))
    post = ConjugateBetaModel().fit([v])["NIGO"]
    assert (post.a, post.b) == (2 + 50, 18 + 560 - 50)


def test_no_data_posterior_equals_prior():
    v = Variant("X", BetaPrior(a=1, b=40), target_n=10, target_prob=0.9)
    post = ConjugateBetaModel().fit([v])["X"]
    assert (post.a, post.b) == (1, 40)
    assert post.mean() == pytest.approx(1 / 41)


def test_credible_interval_brackets_mean():
    lo, hi = BetaPosterior(5, 95).credible_interval(0.9)
    assert 0 < lo < 0.05 < hi < 1


def test_invalid_parameters():
    with pytest.raises(ValueError):
        BetaPosterior(0, 1)


def test_edge_cases():
    post = BetaPosterior(2, 38)
    assert post.capture_probability(100, 0) == pytest.approx(1.0)  # at least 0 is certain
    assert post.capture_probability(5, 6) == pytest.approx(0.0)  # cannot exceed S
    assert post.capture_probability(0, 1) == pytest.approx(0.0)
    with pytest.raises(ValueError):
        post.capture_probability(10, -1)
    with pytest.raises(ValueError):
        post.capture_probability(-5, 1)


def test_probability_never_decreases_with_sample_size():
    post = BetaPosterior(3, 97)
    sizes = np.arange(0, 3001, 25)
    probs = post.capture_probability(sizes, 20)
    assert np.all(np.diff(probs) >= -1e-12)
    assert probs[0] == 0.0
    # Capture probability is capped by uncertainty about p: at large S it approaches
    # P(p > N/S), not 1, because some posterior mass sits at very low prevalence.
    p_floor = 1 - beta.cdf(20 / 3000, 3, 97)
    assert probs[-1] == pytest.approx(p_floor, abs=0.02)
    assert probs[-1] < 1.0


def test_array_input_matches_scalar():
    post = BetaPosterior(3, 97)
    arr = post.capture_probability(np.array([100, 500, 1000]), 10)
    assert arr[1] == pytest.approx(post.capture_probability(500, 10))


@pytest.mark.parametrize(
    "a, b, S, N",
    [
        (3.0, 27.0, 200, 5),
        (20.0, 180.0, 100, 12),
        (1.0, 40.0, 1500, 20),
        (52.0, 528.0, 150, 15),
    ],
)
def test_closed_form_matches_monte_carlo(a, b, S, N):
    """Simulate p ~ Beta(a, b), X ~ Binomial(S, p) and compare P(X >= N)."""
    rng = np.random.default_rng(20261002)
    draws = 400_000
    p = rng.beta(a, b, size=draws)
    x = rng.binomial(S, p)
    simulated = np.mean(x >= N)

    exact = BetaPosterior(a, b).capture_probability(S, N)
    standard_error = np.sqrt(exact * (1 - exact) / draws)
    assert abs(simulated - exact) < max(5 * standard_error, 1e-3)


def test_factory():
    assert isinstance(ModelFactory.create("conjugate_beta"), ConjugateBetaModel)
    with pytest.raises(ValueError, match="Unknown model"):
        ModelFactory.create("nope")

import pytest

from prevalence.config import ConfigError, ConfigLoader, RunConfig

RUN = {
    "pilot": "p",
    "model": "conjugate_beta",
    "target_n": 20,
    "target_prob": 0.9,
    "sample_sizes": {"start": 50, "stop": 500, "step": 50},
    "max_practical_sample_size": 400,
    "population_per_window": 12000,
    "recommendation": {"borderline_multiple": 1.5},
}


def run_with(**overrides) -> dict:
    return {**RUN, **overrides}


def test_load_fixture_run(fixtures):
    run = ConfigLoader.load_run(fixtures / "run.yaml")
    assert run.target_n == 20
    assert run.stratum_dimension == "plan_type"
    assert run.stratum_shares == {"401k": 0.7, "403b": 0.3}
    assert run.sample_sizes.values()[:3] == [50, 100, 150]
    assert run.sample_sizes.values()[-1] == 5000


def test_defaults_are_unstratified_combined():
    run = RunConfig.model_validate(RUN)
    assert run.stratum_view == "combined"
    assert run.stratum_shares == {}
    assert run.output.excel is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"target_prob": 1.0},
        {"target_n": 0},
        {"max_practical_sample_size": 20000},
        {"sample_sizes": {"start": 500, "stop": 50, "step": 50}},
        {"stratum_view": "by_stratum"},  # no strata defined
        {"strata": {"plan_type": {"a": 0.5, "b": 0.4}}},  # shares != 1
        {"strata": {"x": {"a": 1.0}, "y": {"b": 1.0}}},  # two dimensions
        {"recommendation": {"borderline_multiple": 0.5}},
        {"typo_key": 1},
    ],
)
def test_invalid_run_configs_are_rejected(overrides):
    with pytest.raises(Exception):
        RunConfig.model_validate(run_with(**overrides))


def test_load_variants_and_overrides(fixtures):
    run = ConfigLoader.load_run(fixtures / "run.yaml")
    vcs = ConfigLoader.load_variants(fixtures / "variants.yaml")
    variants = {v.name: v for v in ConfigLoader.build_variants(run, vcs, [])}
    assert variants["NIGO"].target_n == 20  # run default
    assert variants["NIGO - Missing Plan Signature"].target_n == 10  # override
    assert variants["NIGO - Missing Plan Signature"].parent == "NIGO"
    assert variants["Not NIGO"].target_prob == 0.9


def write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text)
    return p


def test_variants_reject_duplicates_unknown_parent_and_cycles(tmp_path):
    base = "  - name: {n}\n    prior: {{a: 1, b: 1}}\n"
    dup = "variants:\n" + base.format(n="A") + base.format(n="A")
    with pytest.raises(ConfigError, match="duplicate"):
        ConfigLoader.load_variants(write(tmp_path, "dup.yaml", dup))

    unknown = "variants:\n" + base.format(n="A") + "    parent: Ghost\n"
    with pytest.raises(ConfigError, match="unknown parent"):
        ConfigLoader.load_variants(write(tmp_path, "unk.yaml", unknown))

    cycle = (
        "variants:\n"
        + base.format(n="A") + "    parent: B\n"
        + base.format(n="B") + "    parent: A\n"
    )
    with pytest.raises(ConfigError, match="cycle"):
        ConfigLoader.load_variants(write(tmp_path, "cyc.yaml", cycle))

    self_parent = "variants:\n" + base.format(n="A") + "    parent: A\n"
    with pytest.raises(ConfigError, match="cycle"):
        ConfigLoader.load_variants(write(tmp_path, "self.yaml", self_parent))


def test_load_observations_and_attach(fixtures):
    run = ConfigLoader.load_run(fixtures / "run.yaml")
    vcs = ConfigLoader.load_variants(fixtures / "variants.yaml")
    obs = ConfigLoader.load_observations(fixtures / "counts.csv")
    assert len(obs) == 2
    variants = {v.name: v for v in ConfigLoader.build_variants(run, vcs, obs)}
    assert variants["NIGO"].total_counts() == (50, 560)
    assert not variants["Not NIGO"].has_data


def test_counts_must_match_variants_and_strata(fixtures, tmp_path):
    run = ConfigLoader.load_run(fixtures / "run.yaml")
    vcs = ConfigLoader.load_variants(fixtures / "variants.yaml")

    bad_variant = write(tmp_path, "a.csv", "variant,stratum,k,n\nGhost,401k,1,10\n")
    with pytest.raises(ConfigError, match="unknown variant"):
        ConfigLoader.build_variants(run, vcs, ConfigLoader.load_observations(bad_variant))

    bad_stratum = write(tmp_path, "b.csv", "variant,stratum,k,n\nNIGO,457b,1,10\n")
    with pytest.raises(ConfigError, match="unknown stratum"):
        ConfigLoader.build_variants(run, vcs, ConfigLoader.load_observations(bad_stratum))

    no_stratum = write(tmp_path, "c.csv", "variant,stratum,k,n\nNIGO,,1,10\n")
    with pytest.raises(ConfigError, match="no stratum"):
        ConfigLoader.build_variants(run, vcs, ConfigLoader.load_observations(no_stratum))


def test_counts_file_errors(tmp_path):
    with pytest.raises(ConfigError, match="missing columns"):
        ConfigLoader.load_observations(write(tmp_path, "a.csv", "variant,k,n\nA,1,2\n"))
    with pytest.raises(ConfigError, match="line 2"):
        ConfigLoader.load_observations(write(tmp_path, "b.csv", "variant,stratum,k,n\nA,s,5,2\n"))
    with pytest.raises(ConfigError, match="not found"):
        ConfigLoader.load_observations(tmp_path / "nope.csv")

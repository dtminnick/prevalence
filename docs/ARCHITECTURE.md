# Architecture: Prevalence Estimator

Status: design phase. Storage is deferred (see DECISIONS.md D-008). This document describes the core model, planner, and reporting layers.

## 1. Model summary

For each variant (and stratum, if stratified):

- Prevalence: `p ~ Beta(a, b)`. Priors come from config (SME estimates) as raw `a`, `b`.
- Update with counts: `k` occurrences out of `n` cases gives posterior `Beta(a + k, b + n - k)`.
- Occurrences `X` in a future sample of size `S` follow `BetaBinomial(S, a', b')`.
- Capture probability: `P(X >= N) = betabinom.sf(N - 1, S, a', b')`.
- Minimum sample size: the smallest `S` with `P(X >= N) >= M`, found by binary search because the probability never decreases as `S` grows.
- A variant is flagged by comparing its minimum `S` with the practical sample-size limit and the population cap.

Variants may overlap, so each is modeled independently. Hierarchy (for example NIGO types) is metadata used for rollups only.

## 2. Classes

### Configuration
| Class | Responsibility |
|---|---|
| `RunConfig` | Pilot name, `target_n`, `target_prob`, sample-size grid, max practical sample size, population per window, stratum shares, `stratum_view` (`by_stratum`, `combined`, `both`) |
| `VariantConfig` | Name, optional `parent`, optional per-variant `target_n` / `target_prob`, prior |
| `ConfigLoader` | Reads YAML, validates (pydantic), returns config objects |

### Domain
| Class | Responsibility |
|---|---|
| `BetaPrior` | `a`, `b`, `source` (`SME` or `data`) |
| `Observation` | `variant`, `stratum`, `k`, `n` |
| `Variant` | Config plus observations; knows its parent for rollups |

### Models (swappable backend)
| Class | Responsibility |
|---|---|
| `Posterior` (abstract) | `capture_probability(sample_size, target_n)`, `mean()`, `credible_interval()` |
| `BetaPosterior` | Closed-form posterior with parameters `a'`, `b'` |
| `StratifiedPosterior` | One posterior per stratum plus stratum shares; combined view by convolving per-stratum Beta-binomial distributions |
| `PrevalenceModel` (abstract) | `fit(variants) -> dict[str, Posterior]` |
| `ConjugateBetaModel` | Closed-form update (v1) |
| `PyMCModel` (later) | Returns posteriors backed by draws, same interface |
| `ModelFactory` | Resolves `model: conjugate_beta` in YAML to a class |

### Planning
| Class | Responsibility |
|---|---|
| `CapturePlanner` | `capture_curve(posterior, grid)` and `minimum_sample_size(posterior, target_n, target_prob, max_s)` |
| `RecommendationPolicy` (abstract) | Maps minimum `S` and caps to a flag |
| `ThresholdPolicy` | Config-driven thresholds: Sample, Borderline, Synthetic / targeted search, plus an infeasible reason when the population cap is exceeded |

### Reporting
| Class | Responsibility |
|---|---|
| `PlanResult` | Dataclass: curve, minimum `S`, flag per variant (and stratum) |
| `Report` (abstract) | Renders a `PlanResult` as a table |
| `WorkingReport` | Full detail for the analyst |
| `StakeholderReport` | Flag, minimum sample size, plain-language labels |
| `ExcelExporter` | Writes either report to Excel |

### Orchestration
| Class | Responsibility |
|---|---|
| `PrevalenceRun` | Load config, build variants, fit, plan, report |
| `RunFingerprint` | Hash of config plus data; used later for duplicate-run rejection |

## 3. Config sketch

`configs/pilot_a/run.yaml`
```yaml
pilot: pilot_a
model: conjugate_beta
target_n: 20
target_prob: 0.90
sample_sizes: {start: 50, stop: 5000, step: 50}
max_practical_sample_size: 2000
population_per_window: 12000
stratum_view: both            # by_stratum | combined | both
strata:
  plan_type:
    401k: 0.7
    403b: 0.3
recommendation:
  borderline_multiple: 1.5    # min S up to 1.5x the practical limit
output:
  excel: true
```

`configs/pilot_a/variants.yaml`
```yaml
variants:
  - name: NIGO
    prior: {a: 2, b: 18, source: SME}
  - name: NIGO - Missing Plan Signature
    parent: NIGO
    prior: {a: 1, b: 40, source: SME}
    target_n: 10              # per-variant override
  - name: Not NIGO
    prior: {a: 18, b: 2, source: SME}
```

`data/pilot_a/counts.csv`
```
variant,stratum,k,n
NIGO,401k,38,400
NIGO,403b,12,160
```

All values above are illustrative placeholders.

## 4. Suggested layout

```
prevalence/
  configs/        run.yaml, variants.yaml per pilot
  data/           counts CSVs
  docs/           ARCHITECTURE.md, DECISIONS.md
  src/prevalence/
    config.py     config classes and loader
    domain.py     BetaPrior, Observation, Variant
    models/       base.py, conjugate.py, (pymc.py later)
    planner.py    CapturePlanner, policies
    reports.py    reports and Excel export
    run.py        PrevalenceRun, RunFingerprint
    cli.py
  tests/
```

## 5. Build order

1. Config and domain classes, with tests on YAML loading.
2. `BetaPosterior` and `ConjugateBetaModel`; validate closed-form capture probabilities against Monte Carlo simulation (keep as a permanent test).
3. `CapturePlanner` and the minimum-sample-size search.
4. `StratifiedPosterior` and the per-stratum / combined views.
5. `ThresholdPolicy`, the two reports, and Excel export.
6. `PrevalenceRun` and a thin CLI.
7. Later: storage, then optional PyMC backend and hierarchical / Dirichlet extensions.

## 6. Dependencies

numpy, scipy, pandas, pyyaml, pydantic, openpyxl, pytest. PyMC later.
